# -*- coding: utf-8 -*-
"""In-stream tool permission approval broker (default permission mode).

When the agent runs in "default" permission mode, local-capability tool calls
(mcp_invoke on stdio servers) must be approved by the user before execution:

  1. answer.py's tool loop yields a ``permission_request`` event (forwarded to
     the frontend as an SSE ``permission`` event) and then awaits the decision.
  2. The frontend shows an allow/deny dialog and POSTs to
     ``/api/chat/permission``.
  3. ``resolve()`` fulfils the future; the tool loop resumes. No decision
     within ``TIMEOUT_SEC`` counts as a denial.

Single-user local app: a module-level dict of pending futures is enough.
"""
from __future__ import annotations

import asyncio
import uuid

TIMEOUT_SEC = 120.0

_pending: dict[str, "asyncio.Future[bool]"] = {}


def create_request() -> tuple[str, "asyncio.Future[bool]"]:
  """Register a new pending approval; returns (request_id, future)."""
  rid = uuid.uuid4().hex
  loop = asyncio.get_running_loop()
  fut: "asyncio.Future[bool]" = loop.create_future()
  _pending[rid] = fut
  return rid, fut


async def wait_decision(request_id: str, timeout: float = TIMEOUT_SEC) -> bool:
  """Await the user's decision; timeout or abort counts as denial."""
  fut = _pending.get(request_id)
  if fut is None:
    return False
  try:
    return bool(await asyncio.wait_for(fut, timeout))
  except (asyncio.TimeoutError, asyncio.CancelledError):
    return False
  finally:
    _pending.pop(request_id, None)


def resolve(request_id: str, approve: bool) -> bool:
  """Frontend calls this via POST /api/chat/permission."""
  fut = _pending.pop(request_id, None)
  if fut is None or fut.done():
    return False
  fut.set_result(bool(approve))
  return True


def cancel_all() -> None:
  """Drop every pending request (e.g. client disconnected mid-ask)."""
  for fut in list(_pending.values()):
    if not fut.done():
      fut.set_result(False)
  _pending.clear()
