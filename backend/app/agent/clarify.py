# -*- coding: utf-8 -*-
"""In-stream query clarification broker (model-driven, always on).

When the router detects an ambiguous query (e.g. "帮我调研哪吒" — 哪吒汽车?
动漫角色?), chat.py pauses the graph, emits a SSE ``clarify`` event with a
question + candidate options, and awaits the user's answer:

  1. chat.py's graph loop sees ``clarify_request`` in the router delta,
     registers a pending future via ``create_request()`` and yields the
     SSE event.
  2. The frontend shows a small dialog (options + free-text input) and
     POSTs to ``/api/chat/clarify``.
  3. ``resolve()`` fulfils the future; chat.py refines the query with the
     answer and re-runs the graph (``skip_clarify`` prevents re-asking).
     No answer within ``TIMEOUT_SEC`` counts as "skip" (original query).

Single-user local app: a module-level dict of pending futures is enough.
"""
from __future__ import annotations

import asyncio
import uuid

TIMEOUT_SEC = 300.0

_pending: dict[str, "asyncio.Future[str]"] = {}


def create_request() -> tuple[str, "asyncio.Future[str]"]:
  """Register a new pending clarification; returns (request_id, future)."""
  rid = uuid.uuid4().hex
  loop = asyncio.get_running_loop()
  fut: "asyncio.Future[str]" = loop.create_future()
  _pending[rid] = fut
  return rid, fut


async def wait_answer(request_id: str, timeout: float = TIMEOUT_SEC) -> str:
  """Await the user's answer; timeout / abort / skip all return ''."""
  fut = _pending.get(request_id)
  if fut is None:
    return ""
  try:
    return str(await asyncio.wait_for(fut, timeout) or "")
  except (asyncio.TimeoutError, asyncio.CancelledError):
    return ""
  finally:
    _pending.pop(request_id, None)


def resolve(request_id: str, answer: str) -> bool:
  """Frontend calls this via POST /api/chat/clarify. Empty answer = skip.

  只 set_result 不 pop：wait_answer 可能尚未开始 await（先 resolve 后 wait
  的场景），future 留在 _pending 里由 wait_answer 的 finally 统一清理；
  fut.done() 检查防止重复 resolve。
  """
  fut = _pending.get(request_id)
  if fut is None or fut.done():
    return False
  fut.set_result(str(answer or "").strip())
  return True


def cancel_all() -> None:
  """Drop every pending request (e.g. client disconnected mid-ask)."""
  for fut in list(_pending.values()):
    if not fut.done():
      fut.set_result("")
  _pending.clear()
