"""Hybrid search: vector (Chroma) + keyword (FTS5) -> dedupe + rerank."""
from __future__ import annotations

import logging
import re

from app.embeddings.factory import embed_texts
from app.storage.vector import search as vector_search

# Relevance thresholds. Anything below these is treated as noise and
# dropped before the LLM sees it, so turns like "my name is X" no
# longer get a fake citation card.
MIN_FINAL_SCORE = 0.18   # 0.7 * vec + 0.3 * kw
MIN_DIM_SCORE = 0.18     # max(vec_score, kw_score)
from app.storage.db import fts_search


def _make_key(note_id: str, chunk_index: int) -> str:
  return f"{note_id}#{chunk_index}"


def _fts_escape(query: str) -> str:
  """Make a string safe for SQLite FTS5 MATCH.

  FTS5 treats double quotes and a few ASCII chars as syntax. Strip them and
  wrap the cleaned string in double quotes so the engine treats it as a phrase
  and tokenizes CJK characters correctly even for 2-3 char queries.
  """
  if not query:
    return ""
  s = query.strip()
  if not s:
    return ""
  # FTS5 reserved chars: " ( ) * ^ : AND OR NOT NEAR
  for ch in (chr(34), '(', ')', '*', '^', ':'):
    s = s.replace(ch, ' ')
  s = s.strip()
  if not s:
    return ""
  return chr(34) + s + chr(34)



def hybrid_search(
  query: str,
  top_k: int = 5,
  api_key: str | None = None,
  base_url: str | None = None,
  model: str | None = None,
  min_score: float = MIN_FINAL_SCORE,
  min_dim_score: float = MIN_DIM_SCORE,
  source_type: str | None = None,
  tag: str | None = None,
  date_from: str | None = None,
  date_to: str | None = None,
  rerank: bool = False,
  expand: bool = False,
) -> list[dict]:
  """Combine vector + keyword search, dedupe, return top_k.

  base_url lets the caller reuse the same OpenAI-compatible endpoint that
  chat is using, so embeddings stay consistent with whatever was at ingest.
  """
  # vector search
  vec_hits: list[dict] = []
  try:
    emb = embed_texts([query], api_key=api_key, base_url=base_url, model=model, mode="query")[0]
    vec_hits = vector_search(emb, top_k=top_k * 2)
    for h in vec_hits:
      d = h.get("distance")
      h["vec_score"] = max(0.0, 1.0 - (d if d is not None else 1.0))
  except Exception as e:
    # MiniMax rejects type="query" on embo-01 with status_code=2013.
    # Fall back to type="db" (ingestion mode) which is the only one MiniMax embo-01 accepts.
    try:
      emb = embed_texts([query], api_key=api_key, base_url=base_url, model=model, mode="db")[0]
      vec_hits = vector_search(emb, top_k=top_k * 2)
      for h in vec_hits:
        d = h.get("distance")
        h["vec_score"] = max(0.0, 1.0 - (d if d is not None else 1.0))
    except Exception as e2:
      logging.getLogger(__name__).warning("hybrid_search vector embed failed (query mode: %s; db fallback: %s)", e, e2)

  # keyword search (FTS5 / BM25)
  kw_hits = []
  try:
    safe_q = _fts_escape(query)
    if safe_q:
      kw_hits = fts_search(safe_q, top_k=top_k * 2)
      for h in kw_hits:
        s = h.get("score") or 0.0
        h["kw_score"] = 1.0 / (1.0 + abs(s))
  except Exception as e:
    logging.getLogger(__name__).warning("hybrid_search fts failed: %s", e)

  # merge + dedupe by (note_id, chunk_index)
  merged = {}
  for h in vec_hits:
    k = _make_key(h["note_id"], h["chunk_index"])
    merged[k] = {
      "note_id": h["note_id"],
      "chunk_index": h["chunk_index"],
      "text": h["text"],
      "vec_score": h.get("vec_score", 0.0),
      "kw_score": 0.0,
    }
  for h in kw_hits:
    k = _make_key(h["note_id"], h["chunk_index"])
    if k in merged:
      merged[k]["kw_score"] = h.get("kw_score", 0.0)
    else:
      merged[k] = {
        "note_id": h["note_id"],
        "chunk_index": h["chunk_index"],
        "text": h["text"],
        "vec_score": 0.0,
        "kw_score": h.get("kw_score", 0.0),
      }

  # combined: vector 0.7 + keyword 0.3
  scored = [
    (
      0.7 * v["vec_score"] + 0.3 * v["kw_score"],
      max(v["vec_score"], v["kw_score"]),
      v,
    )
    for v in merged.values()
  ]
  ranked = sorted(scored, key=lambda t: t[0], reverse=True)

  from app.storage.db import get_note_title, get_note_meta
  results = []
  for final_s, dim_s, r in ranked:
    r["title"] = get_note_title(r["note_id"])
    r["final_score"] = round(final_s, 4)
    # Relevance gate: drop pure-noise chunks so conversational queries
    # (e.g. "my name is X") no longer get fake citation cards.
    if final_s < min_score:
      continue
    if dim_s < min_dim_score:
      continue
    # Attach source metadata for frontend display (uploaded vs feishu)
    meta = get_note_meta(r["note_id"])
    if meta:
      r["source_type"] = meta["source_type"]
      r["source_url"] = meta["source_url"]
    results.append(r)
    if len(results) >= top_k:
      break
  return results


def filter_by_meta(results, source_type=None, tag=None, date_from=None, date_to=None):
  """Post-filter merged results by note metadata. No-op if no filters given."""
  if not any([source_type, tag, date_from, date_to]):
    return results
  from datetime import datetime
  from app.storage.db import get_note_meta
  out = []
  df = None
  dt = None
  try:
    if date_from: df = datetime.fromisoformat(date_from)
    if date_to:   dt = datetime.fromisoformat(date_to)
  except Exception:
    pass
  for r in results:
    meta = get_note_meta(r["note_id"]) or {}
    if source_type and meta.get("source_type") != source_type:
      continue
    if tag:
      tags = (meta.get("tags") or "").split(",")
      if tag not in [t.strip() for t in tags if t.strip()]:
        continue
    if df or dt:
      ts = meta.get("created_at")
      if ts:
        try:
          d = datetime.fromisoformat(str(ts).replace("Z", ""))
          if df and d < df: continue
          if dt and d > dt: continue
        except Exception:
          pass
    out.append(r)
  return out


def hybrid_search_with_expansion(query, top_k=5, **kwargs):
  """hybrid_search + optional query expansion + optional rerank."""
  from app.agent.retrieval_quality import expand_query, rerank
  if kwargs.get("expand"):
    variants = expand_query(query)
    merged_acc = []
    seen = set()
    for v in variants:
      sub = hybrid_search(v, top_k=top_k, **{k: vv for k, vv in kwargs.items() if k not in ("expand", "rerank")})
      for r in sub:
        k = "%s#%s" % (r["note_id"], r["chunk_index"])
        if k not in seen:
          seen.add(k)
          r["_expansion_variant"] = v
          merged_acc.append(r)
    results = merged_acc[:top_k * 2]
  else:
    results = hybrid_search(query, top_k=top_k, **{k: vv for k, vv in kwargs.items() if k not in ("expand", "rerank")})

  if kwargs.get("rerank") and len(results) > 1:
    results = rerank(query, results)
  return results[:top_k]
