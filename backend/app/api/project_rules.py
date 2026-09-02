"""API surface for the AGENTS.md / project-rules integration.

GET  /api/project-rules   -> read the loaded text
POST /api/project-rules   -> upload a new AGENTS.md (replaces the active one)
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent.agents_md import project_rules, has_project_rules

_log = logging.getLogger(__name__)

router = APIRouter(tags=["project"])


class RulesUpdateReq(BaseModel):
    content: str


# Project layout is fixed: backend/app/api/<this file>.
# parents[0] = backend/app/api, parents[1] = backend/app, parents[2] = backend,
# parents[3] = repo root. AGENTS.md always lives at the repo root by convention.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CANONICAL_AGENTS_MD = _REPO_ROOT / "AGENTS.md"


@router.get("/project-rules")
def get_project_rules():
    text = project_rules()
    return {"exists": has_project_rules(), "chars": len(text), "content": text}


@router.post("/project-rules")
def write_project_rules(req: RulesUpdateReq):
    target = _CANONICAL_AGENTS_MD
    body = req.content or ""
    if len(body.encode("utf-8")) > 64 * 1024:
        raise HTTPException(status_code=413, detail="AGENTS.md must be <= 64KB")
    try:
        target.write_text(body, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"write failed: {e}")
    _log.info("AGENTS.md written: %d bytes -> %s", len(body), target)
    return {"ok": True, "path": str(target), "chars": len(body)}
