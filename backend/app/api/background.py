"""Background-task routes (long-running jobs that don't block the UI).

Codex CLI / Claude Code both support "background agent" tasks that run in a
sandbox without blocking the chat UI. We expose two routes:

  POST /api/background/reindex  -> spawn a subprocess that re-vectors the
                                  entire knowledge base and stream progress
                                  back as SSE (Phase 1 of background parity).

  GET  /api/background/jobs     -> list recently finished jobs + their tail
                                  state so the UI can show "last reindex took
                                  12 minutes".

SSE event taxonomy:
  event: background
  data: {"phase": "started"|"progress"|"done"|"error", "job_id", ...}
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_log = logging.getLogger(__name__)
router = APIRouter(tags=["background"])


# In-memory job log keyed by job_id; survives the request that spawned it
# but resets on server restart. For multi-process deployments the user should
# back this with Redis / Postgres but the local-first design is single-process.
_jobs: dict[str, dict] = {}


def _jobs_path() -> Path:
    """Persist per-job state to disk so the UI can recover after a reload."""
    from app.config import settings
    p = Path(settings.data_dir) / "background_jobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _tail_file(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 4096))
            return f.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


async def _produce(cmd: list[str], job_id: str, q: "asyncio.Queue[str]") -> None:
    """Background-task producer: pipe subprocess stdout into an asyncio queue.

    Lives in its own coroutine so the StreamingResponse generator can stay
    synchronous. Errors land in the queue as ``{"phase": "error", ...}``
    events and never propagate.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=os.getcwd(),
    )
    started = time.monotonic()
    await q.put(json.dumps({"phase": "started", "job_id": job_id, "pid": proc.pid}))
    if proc.stdout is not None:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            await q.put(json.dumps({
                "phase": "progress",
                "job_id": job_id,
                "line": text,
                "elapsed_s": int(time.monotonic() - started),
            }))
    rc = await proc.wait()
    await q.put(json.dumps({
        "phase": "done",
        "job_id": job_id,
        "exit_code": rc,
        "elapsed_s": int(time.monotonic() - started),
    }))


class ReindexRequest(BaseModel):
  scope: Optional[str] = None     # "all" | "notes" | "remote" - default "all"
  root_path: Optional[str] = None


@router.post("/background/reindex")
async def api_background_reindex(body: ReindexRequest):
  """Spawn a background reindex and stream its progress as SSE."""
  job_id = "bg_" + uuid.uuid4().hex[:12]
  # Snapshot how many files there are so the consumer can render a progress
  # bar from the streamed line counts.
  from app.storage import db as _db
  total = _db.note_count() if hasattr(_db, "note_count") else 0
  script = ["-m", "app.scripts.reindex_all"]
  if body.scope:
    script += ["--scope", body.scope]
  if body.root_path:
    script += ["--root", body.root_path]
  import sys as _sys
  cmd = [_sys.executable or "python"] + script
  job_dir = _jobs_path()
  log_path = job_dir / (job_id + ".log")
  _jobs[job_id] = {
    "id": job_id,
    "kind": "reindex",
    "started_at": time.time(),
    "log": str(log_path),
  }
  with open(log_path, "wb") as lf:
    pass  # truncate / create

  def generate():
    """Sync SSE generator. Drives the async producer in the background.
    Each iter pulls one JSON-encoded event from the queue and emits an SSE
    frame. Falls back to a final error frame if the producer dies early.
    """
    loop = asyncio.new_event_loop()
    q: "asyncio.Queue[str]" = asyncio.Queue(maxsize=128)
    logf = open(log_path, "ab", buffering=0)

    def _emit(raw: str) -> str:
      logf.write(raw.encode("utf-8") + b"\n")
      return "event: background\ndata: " + raw + "\n\n"

    async def _runner():
      try:
        await _produce(cmd, job_id, q)
      except Exception as e:
        await q.put(json.dumps({"phase": "error", "job_id": job_id, "detail": repr(e)[:300]}))
      finally:
        await q.put("__DONE__")
        try:
          loop.stop()
        except Exception:
          pass

    fut = asyncio.run_coroutine_threadsafe(_runner(), loop)
    t_end = time.time() + 600  # hard cap; reindex shouldn't take > 10 min
    try:
      while True:
        if time.time() > t_end:
          yield _emit(json.dumps({"phase": "error", "job_id": job_id, "detail": "timeout"}))
          break
        try:
          raw = loop.run_until_complete(asyncio.wait_for(q.get(), timeout=1.0))
        except asyncio.TimeoutError:
          continue
        if raw == "__DONE__":
          break
        yield _emit(raw)
    finally:
      try: loop.call_soon_threadsafe(loop.stop)
      except Exception: pass
      try: fut.cancel()
      except Exception: pass
      logf.close()
      loop.close()
    yield "event: done\ndata: {}\n\n"

  return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/background/jobs")
async def api_background_jobs():
  """List recently-finished background jobs + tail of their log."""
  out = []
  for jid, meta in _jobs.items():
    out.append({
      "id": jid,
      "kind": meta.get("kind"),
      "started_at": meta.get("started_at"),
      "log": _tail_file(Path(meta["log"])) if meta.get("log") else "",
    })
  # Newest first
  out.sort(key=lambda j: j.get("started_at") or 0, reverse=True)
  return {"items": out}
