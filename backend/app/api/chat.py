"""Chat API: graph-driven orchestration with HD_USE_GRAPH fallback.

When HD_USE_GRAPH=true (default), LangGraph handles router + sub-agent dispatch,
and chat.py consumes the node events as SSE `stage` / domain events. After the
graph terminates, chat.py drives the LLM token stream via answer_node_stream.

When HD_USE_GRAPH=false, the legacy direct-call path is preserved (hybrid_search
+ answer_node_stream) for emergency rollback.
"""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.storage.hybrid import hybrid_search
from app.storage.db import create_session, append_message, get_messages, get_profile
from app.agent.graph import get_graph
from app.agent.nodes.answer import answer_node_stream
from app.agent.memory import summarize_overflow

router = APIRouter(tags=["chat"])
_log = logging.getLogger("chat")


class Message(BaseModel):
  role: str
  content: str


class ChatRequest(BaseModel):
  messages: list[Message]
  provider: str | None = None
  model: str | None = None
  use_rag: bool = True
  session_id: str | None = None
  base_url: str | None = None
  api_key: str | None = None
  reasoning_level: str | None = None
  embedding_model: str | None = None
  embedding_base_url: str | None = None


def _extract_query(messages):
  for m in reversed(messages):
    if m.role == "user" and m.content.strip():
      return m.content
  return ""


def _sse(event: str, payload) -> str:
  return "event: " + event + chr(10) + "data: " + json.dumps(payload, ensure_ascii=False) + chr(10) + chr(10)


def _build_initial_state(body: ChatRequest, query: str, session_id: str,
                         api_key, base_url, emb_key, emb_base, emb_model) -> dict:
  # Phase 2: server is the source of truth for conversation history.
  # We overwrite whatever the client sent with the messages we just persisted
  # to DB. Frontend may still send `messages` for legacy reasons (Phase 3
  # drops it), but we ignore it here.
  # chat.py persists the user turn to DB *before* this call, so the trailing
  # entry from get_messages is usually the current question. Append only when
  # the last message is not already the current query (defensive: covers the
  # rare case where the last inbound message was not a user role).
  history = get_messages(session_id, limit=16) if session_id else []
  if not history or history[-1] != {"role": "user", "content": query}:
    history.append({"role": "user", "content": query})

  # Long-term memory (§6.5): load the cross-session profile for this session's
  # user. Single-user local app -> one shared profile keyed by "default".
  profile = {}
  try:
    profile = get_profile("default")
  except Exception:
    pass

  # History summary (§6.3): only when the window overflows, compress the cut-off
  # older turns so follow-ups still see the gist. Best-effort, never blocks.
  summary = ""
  if len(history) > 12:
    try:
      summary = summarize_overflow(history)
    except Exception:
      summary = ""

  return {
    "messages": history,
    "session_id": session_id,
    "query": query,
    "retrieved_chunks": [],
    "provider_override": body.provider,
    "model_override": body.model,
    "base_url_override": base_url,
    "api_key_override": api_key,
    "reasoning_level_override": body.reasoning_level,
    "embedding_model_override": emb_model,
    "step_count": 0,
    "profile": profile,
    "summary": summary,
    # Per-turn fields must be reset: with a persistent SQLite checkpointer any
    # field absent from this input would leak from the previous turn's checkpoint
    # (e.g. a stale intent="ingest" re-routing a plain chat turn to the ingest node).
    "intent": "",
    "rewritten_query": "",
    "skip_retrieval": False,
    "research_iterations": 0,
    "research_notes": [],
    "ingest_result": {},
    "report_result": {},
    "answer": None,
    "citations": [],
  }


@router.post("/chat")
async def chat(body: ChatRequest, x_api_key: str | None = Header(None, alias="X-API-Key")):
  if not body.messages:
    raise HTTPException(status_code=400, detail="messages is empty")

  query = _extract_query(body.messages)
  api_key = (body.api_key or x_api_key or "").strip() or None
  base_url = (body.base_url or "").strip() or None
  emb_key = (body.api_key or x_api_key or "").strip() or None
  emb_base = (body.embedding_base_url or body.base_url or "").strip() or None
  emb_model = (body.embedding_model or "").strip() or None

  session_id = body.session_id
  if not session_id:
    title = (query[:50] + ("..." if len(query) > 50 else "")) if query else "New chat"
    sess = create_session(title=title)
    session_id = sess.id

  if query and body.messages[-1].role == "user":
    append_message(session_id, "user", query)

  initial_state = _build_initial_state(body, query, session_id, api_key, base_url,
                                       emb_key, emb_base, emb_model)
  t_req = time.perf_counter()

  async def generate():
    yield _sse("session", {"session_id": session_id})

    final_state = dict(initial_state)
    intent = "chat"
    rag_hits = 0
    early_done = False

    if settings.use_graph:
      yield _sse("stage", {"stage": "router", "status": "started"})
      t_router = time.perf_counter()
      # Phase 3.3: thread_id config makes the checkpointer in graph.py save
      # final state per session, so a later call with the same session_id can
      # resume from where this one left off. chat.py still seeds initial_state
      # from DB (Phase 2); the checkpointer supplements it for LangGraph-level
      # state continuity.
      graph_config = {"configurable": {"thread_id": session_id}} if session_id else None
      try:
        graph = await get_graph()
        async for event in graph.astream(initial_state, config=graph_config):
          for node_name, delta in (event or {}).items():
            if not isinstance(delta, dict):
              continue
            # Phase 3.1: state.messages uses Annotated[list, operator.add].
            # When a node returns {"messages": [...]} LangGraph accumulates
            # it under the hood, but the per-node delta in the stream event
            # is the new fragment only -- merging with update() would clobber
            # history. Extend in place for messages, update the rest.
            if "messages" in delta:
              msgs = delta.pop("messages") or []
              final_state.setdefault("messages", []).extend(msgs)
            final_state.update(delta)
            if node_name == "router":
              intent = delta.get("intent") or intent
              router_ms = (time.perf_counter() - t_router) * 1000
              yield _sse("stage", {"stage": "router", "status": "done",
                                   "intent": intent,
                                   "rewritten_query": delta.get("rewritten_query"),
                                   "ms": round(router_ms, 1)})
            elif node_name == "retrieve":
              rag_hits = len(delta.get("retrieved_chunks") or [])
              yield _sse("stage", {"stage": "rag_search", "status": "started"})
              yield _sse("stage", {"stage": "rag_search", "status": "done", "hits": rag_hits})
            elif node_name == "research":
              iters = int(delta.get("research_iterations") or 0)
              rag_hits = len(delta.get("retrieved_chunks") or [])
              yield _sse("stage", {"stage": "agent", "status": "started", "agent": "research"})
              yield _sse("stage", {"stage": "agent", "status": "done",
                                   "agent": "research", "iterations": iters, "hits": rag_hits})
            elif node_name == "ingest":
              yield _sse("stage", {"stage": "agent", "status": "done", "agent": "ingest"})
              yield _sse("ingest", delta.get("ingest_result") or {})
              early_done = True
            elif node_name == "report":
              yield _sse("stage", {"stage": "agent", "status": "done", "agent": "report"})
              yield _sse("report", delta.get("report_result") or {})
              early_done = True
      except Exception as e:
        _log.warning("graph.astream failed: %s", e)
        yield _sse("error", {"detail": "graph: %s: %s" % (type(e).__name__, e)})
        # fall through to a minimal legacy answer
        early_done = False
        intent = "chat"

      if early_done:
        yield "data: [DONE]" + chr(10) + chr(10)
        return

      # Phase 2: LLM token stream from final graph state (chat / research).
      yield _sse("stage", {"stage": "llm_stream", "status": "started"})
      text_parts: list[str] = []
      citations: list = []
      errored = False
      first_delta_logged = False
      try:
        async for kind, payload in answer_node_stream(final_state):
          if kind == "text_delta":
            text_parts.append(payload)
            if not first_delta_logged:
              first_delta_logged = True
              t_first = (time.perf_counter() - t_req) * 1000
              _log.info("chat ttft: graph=%s rag_hits=%d session=%s model=%s",
                        intent, rag_hits, session_id, body.model or "")
              _log.info("chat ttft_ms=%.0f", t_first)
            for line in payload.split(chr(10)):
              yield "data: " + line + chr(10)
            yield chr(10)
          elif kind == "done":
            citations = payload.get("citations") or []
          elif kind == "error":
            errored = True
            yield _sse("error", {"detail": payload})
      except Exception as e:
        errored = True
        yield _sse("error", {"detail": str(e)})

      yield _sse("stage", {"stage": "llm_stream", "status": "done"})
      if citations:
        yield _sse("citations", citations)
      yield "data: [DONE]" + chr(10) + chr(10)

      if not errored and text_parts:
        try:
          append_message(session_id, "assistant", "".join(text_parts),
                         citations if citations else None)
        except Exception:
          pass
      return

    # ---- Legacy path (HD_USE_GRAPH=false) ----
    yield _sse("stage", {"stage": "rag_search", "status": "started"})
    t_rag = time.perf_counter()
    retrieved = []
    if body.use_rag and query:
      try:
        retrieved = hybrid_search(query, top_k=5, api_key=emb_key,
                                  base_url=emb_base, model=emb_model)
      except Exception as e:
        _log.warning("hybrid_search failed: %s", e)
    initial_state["retrieved_chunks"] = retrieved
    rag_ms = (time.perf_counter() - t_rag) * 1000
    yield _sse("stage", {"stage": "rag_search", "status": "done",
                        "ms": round(rag_ms, 1), "hits": len(retrieved)})

    yield _sse("stage", {"stage": "llm_stream", "status": "started"})
    text_parts = []
    citations = []
    errored = False
    first_delta_logged = False
    try:
      async for kind, payload in answer_node_stream(initial_state):
        if kind == "text_delta":
          text_parts.append(payload)
          if not first_delta_logged:
            first_delta_logged = True
            t_first = (time.perf_counter() - t_req) * 1000
            _log.info("chat ttft (legacy): rag=%.0fms llm_first_delta=%.0fms hits=%d session=%s",
                      rag_ms, t_first, len(retrieved), session_id)
          for line in payload.split(chr(10)):
            yield "data: " + line + chr(10)
          yield chr(10)
        elif kind == "done":
          citations = payload.get("citations") or []
        elif kind == "error":
          errored = True
          yield _sse("error", {"detail": payload})
    except Exception as e:
      errored = True
      yield _sse("error", {"detail": str(e)})

    yield _sse("stage", {"stage": "llm_stream", "status": "done"})
    if citations:
      yield _sse("citations", citations)
    yield "data: [DONE]" + chr(10) + chr(10)

    if not errored and text_parts:
      try:
        append_message(session_id, "assistant", "".join(text_parts),
                       citations if citations else None)
      except Exception:
        pass

  return StreamingResponse(generate(), media_type="text/event-stream",
                          headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
