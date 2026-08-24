"""Answer node - LangChain ChatOpenAI with structured output and streaming."""
from __future__ import annotations

import re

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.llm.factory import _build_model
from app.agent.state import AgentState


ANSWER_INSTRUCTIONS = """You are a strict assistant. Answer the question using ONLY the reference material below.

Rules:
1. Use only the reference chunks; never fabricate facts.
2. Cite sources by index [n] matching the reference index below.
3. If the reference material is insufficient, say so explicitly.
4. Keep the answer concise.

Output format:
- Use Markdown for structure (bold, lists, headings, code blocks, tables).
- For flowcharts / sequence / class diagrams, use a fenced ```mermaid block.
- For images, use Markdown image syntax ![alt](url).
- Citations: collect every [n] you reference into ONE trailing line at the very end:
    来源：[n][m]...
  listing each unique reference exactly once. Do NOT embed [n] markers inside body sentences or list items.

Reference material:
<<CONTEXT>>

Question: <<QUESTION>>
"""


# Captures a citation marker like [1], [ 12 ], or [3]. We tolerate whitespace and
# trailing punctuation; out-of-range indices are dropped downstream.
_CITE_RE = re.compile(r"\[\s*(\d+)\s*\]")


def _format_context(chunks):
  if not chunks:
    return "(no reference material available)"
  out = []
  for i, c in enumerate(chunks, 1):
    title = c.get("title") or c.get("note_id", "?")
    out.append("[%d] source: %s\n%s" % (i, title, c.get("text", "")))
  return "\n\n---\n\n".join(out)


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
  instructions = ANSWER_INSTRUCTIONS.replace("<<CONTEXT>>", _format_context(chunks)).replace("<<QUESTION>>", question)
  msgs = [SystemMessage(content=instructions)]

  # Phase 1.1: feed recent conversation history into the prompt. Without this,
  # a follow-up like that-er-zi-ne gets answered in isolation because the LLM
  # never sees the previous turn. Window of 8 (~4 turns) covers normal
  # follow-ups without diluting attention or blowing up tokens.
  history = [
    m for m in (state.get("messages") or [])
    if m.get("role") in ("user", "assistant") and m.get("content")
  ]
  # The most-recent user turn is the current question; drop it here so we can
  # append it once at the end with consistent formatting.
  if history and history[-1]["role"] == "user" and history[-1]["content"] == question:
    history = history[:-1]
  for m in history[-8:]:
    if m["role"] == "user":
      msgs.append(HumanMessage(m["content"]))
    else:
      msgs.append(AIMessage(m["content"]))

  msgs.append(HumanMessage(content=question))
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
