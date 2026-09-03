"""API surface for the AGENTS.md / project-rules integration.

GET  /api/project-rules          -> read the merged text + provenance list
POST /api/project-rules          -> upload a new AGENTS.md (replaces the active one)
POST /api/project-rules/resolve  -> layer-resolve from an explicit target_path
                                    (Codex-style multi-level walk-up preview)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent.agents_md import project_rules, has_project_rules

_log = logging.getLogger(__name__)

router = APIRouter(tags=["project"])


class RulesUpdateReq(BaseModel):
    content: str


class RulesResolveReq(BaseModel):
    target_path: Optional[str] = None
    extra_paths: list[str] | None = None


# Project layout is fixed: backend/app/api/<this file> -> 3 parents up = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CANONICAL_AGENTS_MD = _REPO_ROOT / "AGENTS.md"


@router.get("/project-rules")
def get_project_rules(target_path: Optional[str] = None):
    rs = project_rules(target_path=target_path)
    return {
        "exists": bool(rs.text),
        "chars": rs.total_chars,
        "content": rs.text,
        "sources": [s.as_dict() for s in rs.sources],
    }


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


@router.post("/project-rules/resolve")
def resolve_project_rules(req: RulesResolveReq):
    """Preview a layered rule load without touching anything on disk.

    Useful for the "preview while you type" UI on a per-file basis. Returns
    the merged text + the list of contributing files in target-first order,
    plus a flag indicating whether the resolved set differs from the global
    canonical load.
    """
    rs = project_rules(
        target_path=req.target_path,
        extra_paths=req.extra_paths,
    )
    canonical = project_rules(target_path=None)
    differs = [s.path for s in rs.sources] != [s.path for s in canonical.sources]
    return {
        "text": rs.text,
        "chars": rs.total_chars,
        "sources": [s.as_dict() for s in rs.sources],
        "differs_from_canonical": differs,
    }
