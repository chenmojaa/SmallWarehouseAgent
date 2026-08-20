"""Chat API with per-request overrides and LangGraph streaming."""
import json
import logging
import time
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.storage.hybrid import hybrid_search
from app.storage.db import create_session, append_message
from app.agent.state import AgentState
from app.agent.nodes.retrieve import retrieve_node
from app.agent.nodes.answer import answer_node_stream

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


def _extract_query(messages: list[Message]) -> str:
  for m in reversed(messages):
    if m.role == "user" and m.content.strip():
      return m.content
  return ""


def _sse(event: str, payload) -> str:
  return "event: " + event + chr(10) + "data: " + json.dumps(payload, ensure_ascii=False) + chr(10) + chr(10)


@router.post("/chat")
async def chat(body: ChatRequest, x_api_key: str | None = Header(None, alias="X-API-Key")):
  if not body.messages:
    raise HTTPException(status_code=400, detail="messages is empty")

  query = _extract_query(body.messages)
  effective_api_key = (body.api_key or x_api_key or "").strip() or None
  effective_base_url = (body.base_url or "").strip() or None
  effective_emb_key = (body.api_key or x_api_key or "").strip() or None
  effective_emb_base = (body.embedding_base_url or body.base_url or "").strip() or None
  effective_emb_model = (body.embedding_model or "").strip() or None

  session_id = body.session_id
  if not session_id:
    title = (query[:50] + ("..." if len(query) > 50 else "")) if query else "New chat"
    sess = create_session(title=title)
    session_id = sess.id

  if query and body.messages[-1].role == "user":
    append_message(session_id, "user", query)

  initial_state = {
    "messages": [m.model_dump() for m in body.messages],
    "session_id": session_id,
    "query": query,
    "retrieved_chunks": [],
    "provider_override": body.provider,
    "model_override": body.model,
    "base_url_override": effective_base_url,
    "api_key_override": effective_api_key,
    "reasoning_level_override": body.reasoning_level,
    "step_count": 0,
  }

  t_req = time.perf_counter()

  async def generate():
    yield _sse("session", {"session_id": session_id})
    yield _sse("stage", {"stage": "rag_search", "status": "started"})

    t_rag_start = time.perf_counter()
    retrieved = []
    if body.use_rag and query:
      try:
        retrieved = hybrid_search(query, top_k=5, api_key=effective_emb_key, base_url=effective_emb_base, model=effective_emb_model)
      except Exception as e:
        _log.warning("hybrid_search failed: %s", e)
        retrieved = []
    initial_state["retrieved_chunks"] = retrieved
    t_rag_ms = (time.perf_counter() - t_rag_start) * 1000
    yield _sse("stage", {"stage": "rag_search", "status": "done", "ms": round(t_rag_ms, 1), "hits": len(retrieved)})
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
            _log.info("chat ttft: rag=%.0fms llm_first_delta_from_req=%.0fms rag_hits=%d session=%s model=%s", t_rag_ms, t_first, len(retrieved), session_id, body.model or "")
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
      full_text = "".join(text_parts)
      try:
        append_message(session_id, "assistant", full_text, citations if citations else None)
      except Exception:
        pass

  return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
