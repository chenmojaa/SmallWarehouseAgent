"""API surface for the Hooks system.

GET  /api/hooks          - list registered hooks + recent runs
POST /api/hooks          - replace the registry (UI: paste JSON)
POST /api/hooks/test     - dry-run a single event and return all hook results
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent import hooks as hooks_mod

_log = logging.getLogger(__name__)
router = APIRouter(tags=["hooks"])


class HooksSetReq(BaseModel):
    specs: list[dict]


class HooksTestReq(BaseModel):
    phase: str
    event: dict


@router.get("/hooks")
def get_hooks():
    return {
        "specs": hooks_mod.list_hooks(),
        "recent": hooks_mod.last_runs(),
    }


@router.post("/hooks")
def set_hooks(req: HooksSetReq):
    n = hooks_mod.set_hooks(req.specs or [])
    return {"ok": True, "count": n}


@router.post("/hooks/test")
def test_hooks(req: HooksTestReq):
    if req.phase not in (hooks_mod.PRE_TOOL_USE, hooks_mod.POST_TOOL_USE):
        raise HTTPException(status_code=400, detail=f"phase must be one of {hooks_mod.PRE_TOOL_USE!r} / {hooks_mod.POST_TOOL_USE!r}")
    if not isinstance(req.event, dict):
        raise HTTPException(status_code=400, detail="event must be an object")
    results = hooks_mod.fire(req.phase, req.event)
    blocked, reason = hooks_mod.is_blocked(results)
    return {
        "results": [r.__dict__ for r in results],
        "blocked": blocked,
        "reason": reason,
    }