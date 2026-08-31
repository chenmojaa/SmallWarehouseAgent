"""Answer node - LangChain ChatOpenAI with structured output and streaming."""
from __future__ import annotations

import re

from app.llm.factory import _build_model
from app.agent.state import AgentState
from app.agent.prompts import get_answer_instructions
from app.agent.context import build_messages


# Phase 4.1: prompt now lives in app/agent/prompts/config.yaml with a built-in
# default fallback in prompts/__init__.py. The variable keeps the same name
# so the rest of this file and any downstream import see no change. Resolved
# once at import; runtime retuning via YAML requires a process restart.
ANSWER_INSTRUCTIONS = get_answer_instructions()


# Captures a citation marker like [1], [ 12 ], or [3]. We tolerate whitespace and
# trailing punctuation; out-of-range indices are dropped downstream.
_CITE_RE = re.compile(r"\[\s*(\d+)\s*\]")


def _build_messages(state: AgentState):
  chat = _build_model(
    provider=state.get("provider_override"),
    model=state.get("model_override"),
    api_key=state.get("api_key_override"),
    base_url=state.get("base_url_override"),
    reasoning_level=state.get("reasoning_level_override"),
  )
  chunks = state.get("retrieved_chunks") or []
  question = state.get("query", "") or "(no question)"
  history = [
    m for m in (state.get("messages") or [])
    if m.get("role") in ("user", "assistant") and m.get("content")
  ]
  # Unified assembly (§7): system prompt + summary + profile + token-budgeted
  # references + sliding-window history + question. Replaces the old inline
  # [-8:] slice which had no token cap and could blow small-model contexts.
  msgs = build_messages(
    instructions=ANSWER_INSTRUCTIONS,
    chunks=chunks,
    history=history,
    question=question,
    summary=state.get("summary") or "",
    profile=state.get("profile") or None,
  )
  return chat, msgs, chunks


def _citations_from_text(text: str, chunks: list) -> list:
  """Extract cited chunks in first-seen order from `[n]` markers.

  Bad indices and out-of-range references are silently skipped so a stray
  bracket in the LLM's prose cannot poison the citations card.
  """
  if not text or not chunks:
    return []
  seen: set = set()
  out: list = []
  for m in _CITE_RE.finditer(text):
    idx = int(m.group(1)) - 1
    if idx < 0 or idx >= len(chunks) or idx in seen:
      continue
    seen.add(idx)
    c = chunks[idx]
    out.append({
      "note_id": c.get("note_id"),
      "title": c.get("title"),
      "chunk_index": c.get("chunk_index"),
      "snippet": (c.get("text") or "")[:240],
      "score": c.get("final_score"),
      "source_type": c.get("source_type", ""),
      "source_url": c.get("source_url", ""),
    })
  return out


def answer_node(state: AgentState) -> dict:
  """Non-streaming variant: a single structured call returns text + citations."""
  chat, msgs, chunks = _build_messages(state)
  # We import lazily because with_structured_output requires LangChain core.
  from langchain_core.output_parsers import PydanticOutputParser
  from app.agent.schemas import AnswerResult

  structured = chat.with_structured_output(AnswerResult)
  result = structured.invoke(msgs)
  citations = [c.model_dump() for c in (result.citations or [])] or _citations_from_text(result.text, chunks)
  return {
    "answer": result.text,
    "citations": citations,
    "step_count": state.get("step_count", 0) + 1,
  }


async def answer_node_stream(state: AgentState):
  """Stream the answer as one LLM call, then derive citations from `[n]` markers.

  Single-pass: avoids the previous double-call (text stream + structured re-call)
  which doubled latency and tokens on providers that don't share KV cache between
  the two requests.
  """
  chat, msgs, chunks = _build_messages(state)
  full_text = ""
  try:
    async for chunk in chat.astream(msgs):
      delta = getattr(chunk, "content", "") or ""
      if delta:
        full_text += delta
        yield ("text_delta", delta)
  except Exception as e:
    yield ("error", "%s: %s" % (type(e).__name__, e))
    return
  yield ("done", {"answer": full_text, "citations": _citations_from_text(full_text, chunks)})
