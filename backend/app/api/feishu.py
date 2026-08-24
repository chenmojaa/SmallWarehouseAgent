"""Feishu sync API: trigger manual sync, list available spaces."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.feishu_sync import sync_all, sync_space
from app.tools.feishu_client import FeishuClient, FeishuError


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feishu", tags=["feishu"])


class SyncResponse(BaseModel):
    space_id: str
    space_name: str
    synced: int
    skipped: int
    failed: int
    errors: list[str] = []


class SyncAllResponse(BaseModel):
    results: list[SyncResponse]


@router.get("/status")
def feishu_status():
    return {
        "enabled": settings.feishu_enabled,
        "app_id_set": bool(settings.feishu_app_id),
        "app_secret_set": bool(settings.feishu_app_secret),
        "api_base": settings.feishu_api_base,
        "space_ids": [s for s in (settings.feishu_space_ids or "").split(",") if s],
        "sync_interval_min": settings.feishu_sync_interval_min,
    }


@router.get("/spaces")
def list_spaces():
    if not settings.feishu_enabled:
        raise HTTPException(status_code=400, detail="feishu not enabled")
    try:
        client = FeishuClient()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"client init: {e}")
    try:
        items = client.list_spaces()
        return {"items": [
            {
                "space_id": s.get("space_id"),
                "name": s.get("name"),
                "description": s.get("description"),
                "visibility": s.get("visibility"),
                "space_type": s.get("space_type"),
            }
            for s in items
        ]}
    except FeishuError as e:
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        client.close()


@router.post("/sync", response_model=SyncAllResponse)
class SyncRequest(BaseModel):
    space_id: str | None = None
    force_full: bool = False


@router.post("/sync", response_model=SyncAllResponse)
def sync_now(body: SyncRequest | None = None):
    """Trigger a sync right now.

    With no body params, syncs every space listed in FEISHU_SPACE_IDS (or all
    visible spaces if that setting is empty). Pass `space_id` to sync one,
    `force_full=true` to ignore revisions and re-ingest everything.
    """
    if not settings.feishu_enabled:
        raise HTTPException(status_code=400, detail="feishu not enabled")
    body = body or SyncRequest()
    try:
        if body.space_id:
            results = [sync_space(body.space_id, force_full=body.force_full)]
        else:
            results = sync_all(force_full=body.force_full)
        return SyncAllResponse(results=[
            SyncResponse(
                space_id=r.space_id,
                space_name=r.space_name,
                synced=r.synced,
                skipped=r.skipped,
                failed=r.failed,
                errors=r.errors,
            ) for r in results
        ])
    except FeishuError as e:
        raise HTTPException(status_code=502, detail=str(e))
