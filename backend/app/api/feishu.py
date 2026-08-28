"""Feishu sync API: trigger manual sync, list available spaces."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.feishu_sync import sync_all, sync_space
from app.tools.feishu_client import FeishuClient, FeishuError
from app.storage import feishu_config_store as fcs


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feishu", tags=["feishu"])


class SyncResponse(BaseModel):
    space_id: str
    space_name: str
    synced: int
    updated: int
    skipped: int
    failed: int
    errors: list[str] = []


class SyncAllResponse(BaseModel):
    results: list[SyncResponse]


@router.get("/status")
def feishu_status():
    return {
        "enabled": fcs.is_enabled(),
        "app_id_set": bool(fcs.get_app_id()),
        "app_secret_set": bool(fcs.get_app_secret()),
        "api_base": fcs.get_api_base(),
        "space_ids": fcs.get_space_ids(),
        "sync_interval_min": settings.feishu_sync_interval_min,
    }


class FeishuConfigRequest(BaseModel):
    web_url: str | None = None
    app_id: str | None = None
    app_secret: str | None = None
    api_base: str | None = None
    space_ids: str | None = None


@router.get("/config")
def feishu_config():
    """Get UI-configurable Feishu settings (secret masked)."""
    return fcs.get_config()


@router.post("/config")
def feishu_config_update(body: FeishuConfigRequest):
    """Update UI-configurable Feishu settings.

    Only the provided fields are written. An empty/omitted app_secret keeps the
    stored one, so the UI can save other fields without re-typing the secret.
    """
    patch = {}
    if body.web_url is not None:
        patch["web_url"] = body.web_url
    if body.app_id is not None:
        patch["app_id"] = body.app_id
    if body.api_base is not None:
        patch["api_base"] = body.api_base
    if body.space_ids is not None:
        patch["space_ids"] = body.space_ids
    if body.app_secret:
        patch["app_secret"] = body.app_secret
    return fcs.update_config(patch)


@router.post("/test")
def feishu_test_connection():
    """Validate the configured credentials by fetching a tenant_access_token.

    Returns the list of visible wiki spaces on success so the user can confirm
    they are looking at the right tenant.
    """
    if not fcs.is_configured():
        raise HTTPException(status_code=400, detail="missing app_id or app_secret")
    client = FeishuClient()
    try:
        spaces = client.list_spaces()
        return {
            "ok": True,
            "spaces": [
                {"space_id": s.get("space_id"), "name": s.get("name")}
                for s in spaces
            ],
        }
    except FeishuError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")
    finally:
        client.close()


@router.get("/spaces")
def list_spaces():
    if not fcs.is_enabled():
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


class SyncRequest(BaseModel):
    space_id: str | None = None
    force_full: bool = False
    api_key: str | None = None


@router.post("/sync", response_model=SyncAllResponse)
def sync_now(body: SyncRequest | None = None, request: Request = None):
    """Trigger a sync right now.

    With no body params, syncs every configured space (or all visible spaces if
    none configured). Pass `space_id` to sync one, `force_full=true` to ignore
    revisions and re-ingest everything. The caller's embedding key is taken from
    the X-API-Key header (the frontend always sends it) so re-vectorization
    works even when the server has no stored key.
    """
    if not fcs.is_enabled():
        raise HTTPException(status_code=400, detail="feishu not enabled")
    body = body or SyncRequest()
    header_key = request.headers.get("X-API-Key") if request is not None else None
    api_key = body.api_key or (header_key or "").strip() or None
    try:
        if body.space_id:
            results = [sync_space(body.space_id, force_full=body.force_full,
                                  api_key=api_key)]
        else:
            results = sync_all(force_full=body.force_full, api_key=api_key)
        return SyncAllResponse(results=[
            SyncResponse(
                space_id=r.space_id,
                space_name=r.space_name,
                synced=r.synced,
                updated=r.updated,
                skipped=r.skipped,
                failed=r.failed,
                errors=r.errors,
            ) for r in results
        ])
    except FeishuError as e:
        raise HTTPException(status_code=502, detail=str(e))
