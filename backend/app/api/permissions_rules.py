"""Per-tool permission rules CRUD (Codex CLI / Claude Code parity).

GET   /api/permissions/rules           -> merged default + user rules
PATCH /api/permissions/rules           -> set one rule at a time
                                        {"tool": "mcp:fs:fs_write", "decision": "ask|allow|deny|inherit"}
DELETE /api/permissions/rules/{tool}   -> reset a single rule back to default
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent import tool_permissions as perms

_log = logging.getLogger(__name__)
router = APIRouter(tags=["permissions"])


class RuleSetReq(BaseModel):
    tool: str
    decision: str   # allow | deny | ask | inherit


@router.get("/permissions/rules")
def api_list_rules():
    return {"items": perms.list_rules()}


@router.patch("/permissions/rules")
def api_set_rule(req: RuleSetReq):
    try:
        return perms.set_rule(req.tool, req.decision)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/permissions/rules/{tool_pattern}")
def api_delete_rule(tool_pattern: str):
    return perms.set_rule(tool_pattern, "inherit")
