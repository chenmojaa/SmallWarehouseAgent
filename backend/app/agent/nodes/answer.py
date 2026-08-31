"""Answer node - LangChain chat model with optional tool-calling.

Two entry points are kept on purpose:

  - ``answer_node`` (non-streaming, structured output via AnswerResult). This is
    only used by legacy code paths that want a JSON answer; tool-calling is
    not combined with ``with_structured_output`` because most providers will not
    return tool_calls when constrained to a JSON schema.

  - ``answer_node_stream`` is what chat.py drives. When ``settings.tools_enabled``
    is on AND there is at least one registered tool (skills or MCP), we bind
    the tools to the chat model and run a tool-call loop:

      1. invoke the model with the current message list
      2. if the response has ``tool_calls`` -> execute them, append a
         ``ToolMessage`` for each, continue
      3. the first response *without* tool_calls is the final answer; we emit
         the body as one ``text_delta`` event and yield ``done`` with citations

    A small capability inventory is appended to the answer system prompt so the
    model knows which MCP servers / skills exist without having to call the
    registry first.
"""
from __future__ import annotations

import re

from app.llm.factory import _build_model
from app.agent.state import AgentState
from app.agent.prompts import get_answer_instructions
from app.agent.context import build_messages
from app.agent.tools import load_tools, inventory_text
from app.config import settings


ANSWER_INSTRUCTIONS = get_answer_instructions()

_CITE_RE = re.compile(r"\[\s*(\d+)\s*\]")


def _coerce(content) -> str:
  """Normalise LangChain message content (str | list[dict] | None) to str."""
  if content is None:
    return ""
  if isinstance(content, str):
    return content
  if isinstance(content, list):
    parts = []
    for part in content:
      if isinstance(part, dict):
        if part.get("type") == "text" and isinstance(part.get("text"), str):
          parts.append(part["text"])
        else:
          parts.append(str(part))
      else:
        parts.append(str(part))
    return "".join(parts)
  return str(content)


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
  tools = load_tools() if settings.tools_enabled else []
  inventory = inventory_text() if settings.tools_enabled else ""
  msgs = build_messages(
    instructions=ANSWER_INSTRUCTIONS,
    chunks=chunks,
    history=history,
    question=question,
    summary=state.get("summary") or "",
    profile=state.get("profile") or None,
  )
  if inventory:
    from langchain_core.messages import SystemMessage
    if msgs and isinstance(msgs[0], SystemMessage):
      msgs[0] = SystemMessage(content=(msgs[0].content or "") + inventory)
    else:
      msgs = [SystemMessage(content=inventory)] + msgs
  return chat, msgs, chunks, tools, inventory


def _citations_from_text(text: str, chunks: list) -> list:
  if not text or not chunks:
    return []
  seen: set = set()
  indices: list[int] = []
  for m in _CITE_RE.finditer(text):
    idx = int(m.group(1)) - 1
    if idx < 0 or idx >= len(chunks) or idx in seen:
      continue
    seen.add(idx)
    indices.append(idx)
  indices.sort()
  out: list = []
  for idx in indices:
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


def _tool_by_name(tools, name: str):
  for t in tools:
    if getattr(t, "name", None) == name:
      return t
  return None


def answer_node(state: AgentState) -> dict:
  """Non-streaming variant: single structured call. No tool-calling here."""
  chat, msgs, chunks, _tools, _inventory = _build_messages(state)
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
  """Stream the answer as one LLM call, then derive citations from [n] markers.

  Tool-calling path: when tools are available we bind them and run a tool-call
  loop. ``tool_call`` and ``tool_result`` SSE events surface every invocation
  (the frontend can ignore them silently). The first non-tool-call response is
  emitted as a single ``text_delta`` event followed by ``done``.
  """
  chat, msgs, chunks, tools, _inventory = _build_messages(state)
  full_text = ""

  if tools and settings.tools_enabled:
    from langchain_core.messages import ToolMessage
    bound = chat.bind_tools(tools)
    max_steps = max(1, int(getattr(settings, "tools_max_steps", 4) or 4))

    for _step in range(max_steps):
      try:
        resp = await bound.ainvoke(msgs)
      except Exception as e:
        yield ("error", "%s: %s" % (type(e).__name__, e))
        return

      tcs = list(getattr(resp, "tool_calls", None) or [])
      if not tcs:
        full_text = _coerce(getattr(resp, "content", ""))
        if full_text:
          yield ("text_delta", full_text)
        break

      yield ("tool_calls_batch", {
        "count": len(tcs),
        "names": [tc.get("name") for tc in tcs],
      })
      msgs = msgs + [resp]
      for tc in tcs:
        name = tc.get("name") or "unknown_tool"
        args = tc.get("args") or {}
        tc_id = tc.get("id") or ""
        yield ("tool_call", {"name": name, "args": args})
        tool = _tool_by_name(tools, name)
        if tool is None:
          observation = "[tool error] unknown tool %r" % name
          ok = False
        else:
          try:
            out = await tool.ainvoke(args)
            observation = out if isinstance(out, str) else str(out)
            ok = True
          except Exception as e:
            observation = "[tool error] %s: %s" % (type(e).__name__, e)
            ok = False
        snippet = observation[:300] if isinstance(observation, str) else str(observation)[:300]
        yield ("tool_result", {"name": name, "ok": ok, "snippet": snippet})
        msgs = msgs + [ToolMessage(content=observation, tool_call_id=tc_id)]
    else:
      # ran out of steps without a text answer; force one last pass
      try:
        resp = await bound.ainvoke(msgs)
        full_text = _coerce(getattr(resp, "content", ""))
        if full_text:
          yield ("text_delta", full_text)
      except Exception as e:
        yield ("error", "%s: %s" % (type(e).__name__, e))
        return
  else:
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