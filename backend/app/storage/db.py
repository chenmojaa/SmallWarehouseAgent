"""SQLite metadata store (SQLModel) + FTS5 + ChatSession/ChatMessage."""
from __future__ import annotations

import os
import json
import re
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field, SQLModel, create_engine, Session, select, text
from app.config import settings


class Note(SQLModel, table=True):
  __tablename__ = "notes"
  id: str = Field(primary_key=True)
  title: str
  source_type: str
  source_url: Optional[str] = None
  content_path: Optional[str] = None
  summary: Optional[str] = None
  tags: Optional[str] = None
  word_count: int = 0
  chunk_count: int = 0
  created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
  embedded: bool = False
  source_revision: Optional[str] = None   # remote obj_edit_time / etag for incremental sync
  source_updated_at: Optional[datetime] = None   # when we last saw a remote update


class ChatSession(SQLModel, table=True):
  __tablename__ = "chat_sessions"
  id: str = Field(primary_key=True)
  title: str = "新对话"
  created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
  updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatMessage(SQLModel, table=True):
  __tablename__ = "chat_messages"
  id: Optional[int] = Field(default=None, primary_key=True)
  session_id: str = Field(index=True)
  role: str  # user | assistant | system
  content: str
  citations_json: Optional[str] = None
  created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserProfile(SQLModel, table=True):
  """Long-term user profile (§6.5): cross-session facts/preferences as JSON."""
  __tablename__ = "user_profiles"
  user_id: str = Field(primary_key=True)
  facts_json: str = "{}"
  updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class User(SQLModel, table=True):
  """Login account: phone is the account identifier, password stored as PBKDF2 hash."""
  __tablename__ = "users"
  id: Optional[int] = Field(default=None, primary_key=True)
  phone: str = Field(unique=True, index=True)
  password_salt: str
  password_hash: str
  created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
  updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

_engine = None


def get_engine():
  global _engine
  if _engine is None:
    os.makedirs(os.path.dirname(settings.sqlite_path), exist_ok=True)
    _engine = create_engine(
      f"sqlite:///{settings.sqlite_path}",
      echo=False,
      connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(_engine)
    _init_fts(_engine)
    _migrate_notes(_engine)
  return _engine


def _init_fts(engine):
  """Create the FTS5 virtual table if it doesn't exist yet."""
  with engine.begin() as conn:
    conn.execute(text("""
      CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
        note_id UNINDEXED,
        chunk_index UNINDEXED,
        content,
        tokenize = "unicode61 remove_diacritics 2"
      )
    """))


def _migrate_notes(engine):
  """Idempotent column adds for existing Note tables.

  SQLModel.metadata.create_all only creates missing tables, not missing columns.
  Swallow 'duplicate column' / 'already exists' errors so this is safe to call
  on every startup. Re-raise on any other failure.
  """
  statements = [
    "ALTER TABLE notes ADD COLUMN source_revision TEXT",
    "ALTER TABLE notes ADD COLUMN source_updated_at DATETIME",
  ]
  with engine.begin() as conn:
    for stmt in statements:
      try:
        conn.execute(text(stmt))
      except Exception as e:
        msg = str(e).lower()
        if "duplicate column" not in msg and "already exists" not in msg:
          raise


def get_session() -> Session:
  return Session(get_engine())


# === FTS5 helpers ===
def add_fts(note_id: str, chunk_index: int, content: str):
  with get_engine().begin() as conn:
    conn.execute(
      text("INSERT INTO chunk_fts (note_id, chunk_index, content) VALUES (:nid, :idx, :c)"),
      {"nid": note_id, "idx": chunk_index, "c": content},
    )


def delete_fts(note_id: str) -> int:
  with get_engine().begin() as conn:
    result = conn.execute(
      text("DELETE FROM chunk_fts WHERE note_id = :nid"),
      {"nid": note_id},
    )
  return result.rowcount or 0


def fts_search(query: str, top_k: int = 5) -> list[dict]:
  """Two-pass FTS5 search that survives both ASCII and CJK queries.

  Pass 1: phrase match against the whole query (works for ASCII tokens and
  for CJK when the query spans a whole content phrase).
  Pass 2: per-token OR match -- splits CJK into single chars because
  unicode61 produces single-char tokens for CJK; ASCII tokens are kept
  whole. Falls back to LIKE if FTS5 still refuses to parse.

  Always returns at least an empty list, never raises on a bad query.
  """
  if not query or not query.strip():
    return []
  raw = query.strip()
  cleaned = raw
  for ch in (chr(34), chr(40), chr(41), chr(42), chr(94), chr(58)):
    cleaned = cleaned.replace(ch, chr(32))
  cleaned = cleaned.strip()
  if not cleaned:
    return []
  tokens = []
  for tok in cleaned.split():
    if not tok:
      continue
    if all(ord(c) > 0x4E00 and ord(c) < 0x9FFF for c in tok):
      tokens.extend(list(tok))
    else:
      tokens.append(tok)
  seen = set()
  uniq_tokens = []
  for t in tokens:
    if t and t not in seen:
      seen.add(t)
      uniq_tokens.append(t)
  base_sql = (
    "SELECT note_id, chunk_index, content, bm25(chunk_fts) AS score "
    "FROM chunk_fts "
    "WHERE chunk_fts MATCH __MATCH__ "
    "ORDER BY score "
    "LIMIT :k"
  )
  by_key = {}

  def _absorb(rows):
    for r in rows:
      key = (r.note_id, r.chunk_index)
      hit = {"note_id": r.note_id, "chunk_index": r.chunk_index, "text": r.content, "score": float(r.score) if r.score is not None else 0.0}
      if key in by_key:
        by_key[key]["score"] = min(by_key[key]["score"], hit["score"])
      else:
        by_key[key] = hit

  with get_engine().begin() as conn:
    phrase_dq = cleaned.replace(chr(34), chr(34) + chr(34))
    phrase_dq = chr(34) + phrase_dq + chr(34)
    try:
      sql1 = base_sql.replace("__MATCH__", chr(39) + phrase_dq + chr(39))
      rows = conn.execute(text(sql1), {"k": top_k}).all()
      _absorb(rows)
    except Exception:
      pass
    if len(by_key) < top_k and uniq_tokens:
      try:
        or_expr = " OR ".join(uniq_tokens).replace(chr(34), "")
        sql2 = base_sql.replace("__MATCH__", chr(39) + or_expr + chr(39))
        rows = conn.execute(text(sql2), {"k": top_k}).all()
        _absorb(rows)
      except Exception:
        pass
    if not by_key:
      try:
        like_q = "%" + cleaned + "%"
        for r in conn.execute(text("SELECT note_id, chunk_index, content, 0.0 AS score FROM chunk_fts WHERE content LIKE :q LIMIT :k"), {"q": like_q, "k": top_k}).all():
          _absorb([r])
      except Exception:
        pass

  ranked = sorted(by_key.values(), key=lambda h: h["score"])[:top_k]
  return ranked



def get_note_title(note_id: str) -> str | None:
  with get_session() as s:
    n = s.get(Note, note_id)
    return n.title if n else None


def get_note_meta(note_id: str) -> dict | None:
  """Return {source_type, source_url} for a note, or None if not found."""
  with get_session() as s:
    n = s.get(Note, note_id)
    if not n:
      return None
    return {"source_type": n.source_type, "source_url": n.source_url or ""}


def update_note_revision(note_id: str, revision: str | None,
                         updated_at: datetime | None = None) -> bool:
  """Update a note's source_revision + source_updated_at. Returns True on hit."""
  with get_session() as s:
    n = s.get(Note, note_id)
    if not n:
      return False
    n.source_revision = revision
    n.source_updated_at = updated_at or datetime.now(timezone.utc)
    s.add(n)
    s.commit()
    s.refresh(n)
    return True


# === Chat Session helpers ===
def list_sessions(limit: int = 100) -> list[dict]:
  with get_session() as s:
    rows = s.exec(
      select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(limit)
    ).all()
    out = []
    for r in rows:
      # 取最后一条消息作为 preview
      last = s.exec(
        select(ChatMessage).where(ChatMessage.session_id == r.id).order_by(ChatMessage.id.desc()).limit(1)
      ).first()
      msg_count = s.exec(
        select(ChatMessage).where(ChatMessage.session_id == r.id)
      ).all()
      # Some models (e.g. DeepSeek-class) sometimes leave <think>... unclosed
      # in the streamed text, which then leaks into the sidebar preview. Strip
      # the leading <think> block so the preview reads as the actual answer.
      preview_text = _strip_think(last.content) if last else ""
      out.append({
        "id": r.id,
        "title": r.title,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
        "message_count": len(msg_count),
        "preview": (preview_text[:60] + ("..." if preview_text and len(preview_text) > 60 else "")),
      })
  return out


_THINK_RE = re.compile(r"<think>[\s\S]*?(</think>|$)", re.IGNORECASE)
def _strip_think(s: str) -> str:
  """Drop a leading <think>...</think> block (paired OR unclosed trailing).

  Mirrors the frontend's stripThink so the sidebar preview agrees with what
  the user actually sees inside MessageBubble."""
  if not s:
    return ""
  return _THINK_RE.sub("", s, count=1).strip()


def get_session_with_messages(session_id: str) -> dict | None:
  with get_session() as s:
    sess = s.get(ChatSession, session_id)
    if not sess:
      return None
    msgs = s.exec(
      select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
    ).all()
  return {
    "id": sess.id,
    "title": sess.title,
    "created_at": sess.created_at.isoformat(),
    "updated_at": sess.updated_at.isoformat(),
    "messages": [
      {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "citations": json.loads(m.citations_json) if m.citations_json else None,
        "created_at": m.created_at.isoformat(),
      }
      for m in msgs
    ],
  }

def get_messages(session_id: str, limit: int = 16) -> list[dict]:
  """Return the last ``limit`` messages for a session as {role, content}.

  Phase 2 server-side context source of truth (see CONTEXT_UPGRADE.md
  Phase 2.1). Ordered oldest -> newest so callers can feed the result
  straight into a LangChain message list. Excludes the 'system' role
  because the answer node injects its own system prompt.
  """
  with get_session() as s:
    rows = s.exec(
      select(ChatMessage)
      .where(ChatMessage.session_id == session_id)
      .order_by(ChatMessage.id.desc())
      .limit(limit)
    ).all()
  return [
    {"role": m.role, "content": m.content}
    for m in reversed(rows)
    if m.role in ("user", "assistant")
  ]


def create_session(title: str = "新对话") -> ChatSession:
  from uuid import uuid4
  sid = "s_" + uuid4().hex[:12]
  sess = ChatSession(id=sid, title=title[:100])
  with get_session() as s:
    s.add(sess)
    s.commit()
    s.refresh(sess)
  return sess


def delete_session(session_id: str) -> bool:
  with get_session() as s:
    sess = s.get(ChatSession, session_id)
    if not sess:
      return False
    msgs = s.exec(select(ChatMessage).where(ChatMessage.session_id == session_id)).all()
    for m in msgs:
      s.delete(m)
    s.delete(sess)
    s.commit()
  return True


def rename_session(session_id: str, title: str) -> bool:
  with get_session() as s:
    sess = s.get(ChatSession, session_id)
    if not sess:
      return False
    sess.title = title[:100]
    sess.updated_at = datetime.now(timezone.utc)
    s.add(sess)
    s.commit()
  return True


def touch_session(session_id: str) -> None:
  with get_session() as s:
    sess = s.get(ChatSession, session_id)
    if sess:
      sess.updated_at = datetime.now(timezone.utc)
      s.add(sess)
      s.commit()


def append_message(session_id: str, role: str, content: str, citations: list | None = None) -> ChatMessage:
  from sqlmodel import Session as SqlSession
  msg = ChatMessage(
    session_id=session_id,
    role=role,
    content=content,
    citations_json=json.dumps(citations, ensure_ascii=False) if citations else None,
  )
  with get_session() as s:
    s.add(msg)
    s.commit()
    s.refresh(msg)
    # 同时 touch session.updated_at
    sess = s.get(ChatSession, session_id)
    if sess:
      sess.updated_at = datetime.now(timezone.utc)
      s.add(sess)
      s.commit()
  return msg


def update_message_citations(message_id: int, citations: list) -> None:
  with get_session() as s:
    msg = s.get(ChatMessage, message_id)
    if msg:
      msg.citations_json = json.dumps(citations, ensure_ascii=False)
      s.add(msg)
      s.commit()


# === Long-term user profile (§6.5) ===
def get_profile(user_id: str) -> dict:
  """Return the stored profile facts for a user ({} when absent)."""
  with get_session() as s:
    row = s.get(UserProfile, user_id)
    if not row:
      return {}
    try:
      return json.loads(row.facts_json)
    except Exception:
      return {}


def save_profile(user_id: str, facts: dict) -> None:
  """Upsert the profile facts for a user."""
  with get_session() as s:
    row = s.get(UserProfile, user_id)
    payload = json.dumps(facts, ensure_ascii=False)
    if row:
      row.facts_json = payload
      row.updated_at = datetime.now(timezone.utc)
      s.add(row)
    else:
      s.add(UserProfile(user_id=user_id, facts_json=payload))
    s.commit()
