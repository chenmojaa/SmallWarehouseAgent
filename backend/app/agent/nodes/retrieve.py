"""Retrieve node - hybrid search for relevant chunks."""
from app.storage.hybrid import hybrid_search
from app.agent.state import AgentState


def _read_content(m) -> str:
  if isinstance(m, dict):
    return m.get("content", "") or ""
  return getattr(m, "content", "") or ""


def _read_role(m) -> str:
  if isinstance(m, dict):
    return m.get("role", "") or ""
  return getattr(m, "role", "") or ""


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
  try:
    chunks = hybrid_search(query, top_k=5, api_key=api_key, base_url=base_url)
  except Exception:
    chunks = []
  return {
    "retrieved_chunks": chunks,
    "step_count": state.get("step_count", 0) + 1,
  }
