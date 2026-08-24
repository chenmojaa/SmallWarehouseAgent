"""Feishu sync orchestrator with incremental revision-based updates.

Walks every node in each configured wiki space, fetches content, parses to
Markdown, and ingests into the project's local KB via the same pipeline used
for file uploads.

Deduplication: a note is identified by its source_url
(`feishu://wiki/{space_id}/{node_token}` or `feishu://bitable/{app_token}/{table_id}`).

Incremental sync: per-note `source_revision` stores the Feishu obj_edit_time /
last-modify version. If a remote revision matches the stored one, the note is
skipped. Otherwise the old chunks are dropped and the content is re-ingested
under the SAME note id (preserving identity / RAG references).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from sqlmodel import Session as SqlSession, select

from app.config import settings
from app.storage.db import Note, get_engine, update_note_revision
from app.storage.vector import delete_note_chunks
from app.tools.chunk import chunk_text
from app.tools.feishu_client import FeishuClient, FeishuError
from app.tools.ingest import _ingest
from app.tools.parse_feishu_doc import parse_feishu_bitable, parse_feishu_docx

_log = logging.getLogger(__name__)

SOURCE_TYPE_DOCX = "feishu_docx"
SOURCE_TYPE_BITABLE = "feishu_bitable"


@dataclass
class SyncResult:
    space_id: str
    space_name: str
    synced: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def _space_source_url(space_id: str, node_token: str) -> str:
    return f"feishu://wiki/{space_id}/{node_token}"


def _bitable_source_url(app_token: str, table_id: str) -> str:
    return f"feishu://bitable/{app_token}/{table_id}"


def _find_note(source_url: str) -> Note | None:
    engine = get_engine()
    with SqlSession(engine) as s:
        stmt = select(Note).where(Note.source_url == source_url)
        return s.exec(stmt).first()


def _node_revision(node: dict) -> str | None:
    """Pick the strongest revision-like field from a Feishu wiki node object."""
    for k in ("obj_edit_time", "obj_edit_version", "edit_time", "updated_at", "version"):
        v = node.get(k)
        if v:
            return str(v)
    return None


def _drop_and_reingest(existing: Note, new_title: str, new_content: str,
                       source_type: str, revision: str | None,
                       api_key, base_url, embedding_model) -> Note:
    """Replace a note's content + chunks while preserving its id."""
    note_id = existing.id
    # 1. Drop existing chunks (Chroma + FTS5)
    try:
        delete_note_chunks(note_id)
    except Exception as e:
        _log.warning("feishu sync: delete_note_chunks(%s) failed: %s", note_id, e)
    # 2. Overwrite on-disk markdown
    try:
        if existing.content_path and os.path.exists(existing.content_path):
            with open(existing.content_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        else:
            # Content path was lost; fall back to creating a new file path.
            new_path = os.path.join(settings.notes_dir, note_id + ".md")
            os.makedirs(settings.notes_dir, exist_ok=True)
            with open(new_path, "w", encoding="utf-8") as f:
                f.write(new_content)
    except Exception as e:
        _log.warning("feishu sync: content write failed: %s", e)

    # 3. Re-chunk + embed + add chunks (back to Chroma + FTS5)
    chunks = chunk_text(new_content)
    try:
        if chunks:
            from app.embeddings.factory import embed_texts as _embed
            embeddings = _embed(chunks, api_key=api_key, base_url=base_url, model=embedding_model)
            from app.storage.vector import add_chunks
            n_chunks = add_chunks(note_id, chunks, embeddings)
            embedded = True
        else:
            n_chunks = 0
            embedded = False
    except Exception as e:
        _log.warning("feishu sync: re-embed failed: %s", e)
        n_chunks = 0
        embedded = False

    # 4. Update Note row
    engine = get_engine()
    with SqlSession(engine) as s:
        stmt = select(Note).where(Note.id == note_id)
        n = s.exec(stmt).first()
        if not n:
            return existing  # row vanished; nothing we can do
        n.title = new_title[:500]
        n.word_count = len(new_content)
        n.chunk_count = n_chunks
        n.embedded = embedded
        n.source_type = source_type
        update_note_revision(note_id, revision)
        s.add(n)
        s.commit()
        s.refresh(n)
        return n


def _sync_docx_node(client: FeishuClient, space_id: str, node: dict,
                    api_key, base_url, embedding_model,
                    force_full: bool = False) -> tuple[str, str, str | None]:
    """Sync one docx node. Returns (token, status, error).

    status: 'synced' (new) | 'updated' (revision changed) | 'skipped' (no change) | 'failed'.
    """
    node_token = node.get("node_token")
    title = node.get("title") or node_token
    obj_token = node.get("obj_token")
    if not obj_token:
        return node_token, "failed", "no obj_token on node"
    source_url = _space_source_url(space_id, node_token)
    revision = _node_revision(node)

    existing = _find_note(source_url)
    if existing and not force_full:
        if revision and existing.source_revision == revision:
            return node_token, "skipped", None
        # revision changed (or unknown -> treat as update)
        try:
            raw = client.get_docx_raw_content(obj_token)
            parsed = parse_feishu_docx(obj_token, title, raw)
            _drop_and_reingest(existing, parsed["title"], parsed["content"],
                              SOURCE_TYPE_DOCX, revision,
                              api_key, base_url, embedding_model)
            return node_token, "updated", None
        except Exception as e:
            return node_token, "failed", f"{type(e).__name__}: {e}"

    # First-time ingest
    try:
        raw = client.get_docx_raw_content(obj_token)
        parsed = parse_feishu_docx(obj_token, title, raw)
        note = _ingest(
            title=parsed["title"],
            content=parsed["content"],
            source_type=SOURCE_TYPE_DOCX,
            source_url=source_url,
            api_key=api_key, base_url=base_url, embedding_model=embedding_model,
        )
        if revision:
            update_note_revision(note.id, revision)
        return node_token, "synced", None
    except Exception as e:
        return node_token, "failed", f"{type(e).__name__}: {e}"


def _sync_bitable_for_node(client: FeishuClient, node: dict,
                           api_key, base_url, embedding_model,
                           force_full: bool = False) -> list[tuple[str, str, str | None]]:
    """Sync every table inside a bitable."""
    results = []
    app_token = node.get("obj_token")
    title = node.get("title") or app_token
    if not app_token:
        return [(node.get("node_token"), "failed", "no obj_token on bitable node")]
    revision = _node_revision(node)
    try:
        tables = client.list_bitable_tables(app_token)
    except Exception as e:
        return [(node.get("node_token"), "failed", f"list tables: {type(e).__name__}: {e}")]
    for t in tables:
        table_id = t.get("table_id")
        table_name = t.get("name") or table_id
        source_url = _bitable_source_url(app_token, table_id)
        existing = _find_note(source_url)
        if existing and not force_full:
            if revision and existing.source_revision == revision:
                results.append((table_id, "skipped", None))
                continue
            try:
                fields = client.list_bitable_fields(app_token, table_id)
                records = client.list_bitable_records(app_token, table_id)
                parsed = parse_feishu_bitable(title, table_name, fields, records)
                _drop_and_reingest(existing, parsed["title"], parsed["content"],
                                  SOURCE_TYPE_BITABLE, revision,
                                  api_key, base_url, embedding_model)
                results.append((table_id, "updated", None))
                continue
            except Exception as e:
                results.append((table_id, "failed", f"{table_name}: {type(e).__name__}: {e}"))
                continue
        try:
            fields = client.list_bitable_fields(app_token, table_id)
            records = client.list_bitable_records(app_token, table_id)
            parsed = parse_feishu_bitable(title, table_name, fields, records)
            note = _ingest(
                title=parsed["title"],
                content=parsed["content"],
                source_type=SOURCE_TYPE_BITABLE,
                source_url=source_url,
                api_key=api_key, base_url=base_url, embedding_model=embedding_model,
            )
            if revision:
                update_note_revision(note.id, revision)
            results.append((table_id, "synced", None))
        except Exception as e:
            results.append((table_id, "failed", f"{table_name}: {type(e).__name__}: {e}"))
    return results


def sync_space(space_id: str, client: FeishuClient | None = None,
               api_key: str | None = None, base_url: str | None = None,
               embedding_model: str | None = None,
               force_full: bool = False) -> SyncResult:
    """Sync every node in one wiki space. Incremental by default."""
    own_client = client is None
    client = client or FeishuClient()
    result = SyncResult(space_id=space_id, space_name="")
    try:
        spaces = {s.get("space_id"): s.get("name") for s in client.list_spaces()}
        result.space_name = spaces.get(space_id, space_id)

        for node in client.walk_nodes(space_id):
            obj_type = node.get("obj_type")
            if obj_type == "docx":
                _, st, err = _sync_docx_node(client, space_id, node, api_key, base_url,
                                            embedding_model, force_full=force_full)
                if st == "synced":
                    result.synced += 1
                elif st == "updated":
                    result.updated += 1
                elif st == "skipped":
                    result.skipped += 1
                else:
                    result.failed += 1
                    if err:
                        result.errors.append(f"{node.get('title')}: {err}")
            elif obj_type == "bitable":
                for _, st, err in _sync_bitable_for_node(client, node, api_key, base_url,
                                                        embedding_model,
                                                        force_full=force_full):
                    if st == "synced":
                        result.synced += 1
                    elif st == "updated":
                        result.updated += 1
                    elif st == "skipped":
                        result.skipped += 1
                    else:
                        result.failed += 1
                        if err:
                            result.errors.append(err)
            else:
                result.skipped += 1
    finally:
        if own_client:
            client.close()
    return result


def sync_all(api_key: str | None = None, base_url: str | None = None,
             embedding_model: str | None = None,
             force_full: bool = False) -> list[SyncResult]:
    """Sync every space listed in settings.feishu_space_ids (or all visible)."""
    configured = [s.strip() for s in (settings.feishu_space_ids or "").split(",") if s.strip()]
    client = FeishuClient()
    try:
        spaces = client.list_spaces()
        if configured:
            spaces = [s for s in spaces if s.get("space_id") in configured]
        results = []
        for s in spaces:
            sid = s.get("space_id")
            try:
                results.append(sync_space(sid, client=client, api_key=api_key,
                                          base_url=base_url,
                                          embedding_model=embedding_model,
                                          force_full=force_full))
            except FeishuError as e:
                results.append(SyncResult(space_id=sid, space_name=s.get("name", sid),
                                          failed=1, errors=[str(e)]))
        return results
    finally:
        client.close()
