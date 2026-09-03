"""Retrieve node - hybrid search + optional cross-encoder rerank.

Stage 1: hybrid_search() recalls a wider pool (top 50) from the SQLite store.
Stage 2: cross-encoder rerank() trims that pool to top 5. Rerank failure is
caught and the node falls back to the hybrid top-5 so a missing model never
breaks chat.
"""
import logging

from app.storage.hybrid import hybrid_search
from app.agent.state import AgentState

log = logging.getLogger(__name__)


def _read_content(m) -> str:
  if isinstance(m, dict):
    return m.get("content", "") or ""
  return getattr(m, "content", "") or ""


def _read_role(m) -> str:
  if isinstance(m, dict):
    return m.get("role", "") or ""
  return getattr(m, "role", "") or ""


def _hybrid_topk(query: str, api_key, base_url, emb_model) -> int:
  """How many candidates to recall from hybrid before rerank trims to top 5."""
  return 50


def retrieve_node(state: AgentState) -> dict:
  messages = state.get("messages") or []
  # Prefer the router-rewritten query when present; fall back to the last user
  # message verbatim (legacy behavior).
  rewritten = (state.get("rewritten_query") or "").strip()
  raw = (state.get("query") or "").strip()
  query = rewritten or raw
  if not query:
    for m in reversed(messages):
      if _read_role(m) == "user":
        c = _read_content(m).strip()
        if c:
          query = c
          break

  if not query:
    return {"retrieved_chunks": [], "step_count": state.get("step_count", 0) + 1}

  api_key = state.get("api_key_override")
  base_url = state.get("base_url_override")
  emb_model = state.get("embedding_model_override")
  try:
    chunks = hybrid_search(query, top_k=_hybrid_topk(query, api_key, base_url, emb_model),
                           api_key=api_key, base_url=base_url, model=emb_model)
  except Exception as e:
    log.warning("hybrid_search failed: %s", e)
    chunks = []

  # Stage 2: cross-encoder rerank. Best-effort; on any error fall back to the
  # first 5 hybrid hits so the answer node still has something to cite.
  if chunks:
    try:
      from app.agent.rerank import rerank
      cands = [dict(c) for c in chunks]  # shallow copy so original chunks stay intact
      reranked = rerank(query, cands, top_k=5)
      chunks = reranked
    except Exception as e:
      log.warning("rerank failed, falling back to hybrid top-5: %s", e)
      chunks = chunks[:5]
  else:
    chunks = chunks[:5]

  return {
    "retrieved_chunks": chunks,
    "step_count": state.get("step_count", 0) + 1,
  }
