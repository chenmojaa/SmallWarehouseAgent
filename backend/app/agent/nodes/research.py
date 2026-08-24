# -*- coding: utf-8 -*-
"""Research agent: multi-round retrieval + follow-up query generation.

Design (per OPTIMIZATION.md section 2.6):
  - Loop up to MAX_ITER (default 3) rounds, each round: hybrid_search -> dedupe -> accumulate.
  - Stop early when collected chunks >= research_target_chunks (default 8).
  - When more chunks are needed, ask the router-tier model for one follow-up query
    that fills the gap based on what titles/snippets we already have.
  - On any LLM failure, return whatever was collected so far (graceful degradation).
"""
from __future__ import annotations

import logging
from typing import Any

from app.agent.state import AgentState
from app.config import settings
from app.storage.hybrid import hybrid_search
from app.llm.factory import _build_model

_log = logging.getLogger(__name__)

FOLLOWUP_PROMPT = """You are a research assistant. You have already gathered these reference snippets from the knowledge base:

<<COLLECTED>>

Original question: <<ORIG

Suggest ONE follow-up search query (in the SAME language as the original question, in a complete sentence) that would help find the missing angle. Output ONLY the query, no preamble."""


def _snippet(c: dict[str, Any]) -> str:
    return (c.get("text") or c.get("snippet") or "")[:120]


def _seen_key(c: dict[str, Any]) -> tuple[str, int]:
    return (str(c.get("note_id") or ""), int(c.get("chunk_index") or -1))


def _generate_followup(collected: list[dict[str, Any]], original: str,
                       chat) -> str | None:
    """Ask the cheap router-tier model for the next angle to search."""
    if not collected:
        return None
    titles = [c.get("title") or c.get("note_id") for c in collected[:8]]
    snippets = [_snippet(c) for c in collected[:8]]
    collected_str = "\n".join("- [%s] %s" % (t, s) for t, s in zip(titles, snippets))
    payload = FOLLOWUP_PROMPT.replace("<<COLLECTED>>", collected_str).replace("<<ORIG>>", original)
    try:
        resp = chat.invoke(payload)
        text = getattr(resp, "content", None) or str(resp)
        return (text or "").strip().splitlines()[0][:200].strip() or None
    except Exception as e:
        _log.warning("research: follow-up generation failed: %s", e)
        return None


def research_node(state: AgentState) -> dict:
    """Multi-round retrieval. Returns accumulated chunks + research metadata."""
    query = (state.get("rewritten_query") or state.get("query") or "").strip()
    if not query:
        return {"retrieved_chunks": [], "research_iterations": 0,
                "research_notes": [], "step_count": state.get("step_count", 0) + 1}

    max_iter = max(1, int(settings.research_max_iter))
    target = max(1, int(settings.research_target_chunks))
    api_key = state.get("api_key_override")
    base_url = state.get("base_url_override")

    collected: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    queries: list[str] = []
    iterations_done = 0

    for i in range(max_iter):
        if i == 0:
            q = query
        elif queries:
            q = queries[i] if i < len(queries) else queries[-1]
        else:
            break
        try:
            hits = hybrid_search(q, top_k=5, api_key=api_key, base_url=base_url, model=None)
        except Exception as e:
            _log.warning("research: hybrid_search failed for q=%r: %s", q[:60], e)
            hits = []
        new_chunks = [c for c in hits if _seen_key(c) not in seen]
        for c in new_chunks:
            seen.add(_seen_key(c))
        collected.extend(new_chunks)
        iterations_done = i + 1
        if len(collected) >= target:
            break
        # Need more material; try to get a follow-up angle.
        try:
            chat = _build_model(
                provider=None,
                model=settings.router_model or state.get("model_override"),
                api_key=state.get("api_key_override"),
                base_url=settings.router_base_url or state.get("base_url_override") or None,
                reasoning_level=None,
            )
        except Exception as e:
            _log.warning("research: follow-up model init failed: %s", e)
            break
        next_q = _generate_followup(collected, query, chat)
        if not next_q or next_q == q or next_q in queries:
            break
        queries.append(next_q)

    return {
        "retrieved_chunks": collected,
        "research_iterations": iterations_done,
        "research_notes": queries,
        "step_count": state.get("step_count", 0) + 1,
    }