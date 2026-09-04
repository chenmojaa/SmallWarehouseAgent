"""Custom LLM model config REST API.

Persists model configs to a single JSON file on disk (`data/models.json`)
through an atomic write + cross-process file lock. This is what makes the
config survive host swaps, browser changes, and incognito mode — the file
is the source of truth, not localStorage.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.storage.models_store import (
  list_models,
  create_model,
  update_model,
  delete_model,
  get_selected_id,
  set_selected_id,
  models_file_path,
)

_log = logging.getLogger(__name__)
router = APIRouter(tags=["custom-models"])
def _mask_model(m: dict) -> dict:
  """Return a copy of m with apiKey replaced by a non-reversible marker.

  Keeps the original key on disk via models_store; only the network response
  is sanitized so a stolen bearer token cannot leak plaintext provider keys.
  """
  if not isinstance(m, dict):
    return m
  out = dict(m)
  k = out.get("apiKey")
  if isinstance(k, str) and k:
    if len(k) <= 8:
      masked = "*" * len(k)
    else:
      masked = k[:2] + "*" * (len(k) - 6) + k[-4:]
    out["apiKey"] = masked
    out["apiKeySet"] = True
  else:
    out["apiKey"] = ""
    out["apiKeySet"] = False
  return out





class SubModelSpec(BaseModel):
  name: str
  reasoning: str = "medium"


class CreateCustomModelRequest(BaseModel):
  name: str = Field(..., min_length=1, max_length=120)
  baseUrl: str = Field(..., min_length=1)
  apiKey: str = Field(..., min_length=1)
  provider: str = Field(..., min_length=1)
  models: list[SubModelSpec] = Field(..., min_length=1)
  defaultModel: Optional[str] = None
  embeddingModel: Optional[str] = None


class UpdateCustomModelRequest(BaseModel):
  name: Optional[str] = None
  baseUrl: Optional[str] = None
  apiKey: Optional[str] = None
  provider: Optional[str] = None
  models: Optional[list[SubModelSpec]] = None
  defaultModel: Optional[str] = None
  embeddingModel: Optional[str] = None


class SelectRequest(BaseModel):
  id: Optional[str] = None


@router.get("/custom-models")
async def api_list():
  items = [_mask_model(m) for m in list_models()]
  return {"items": items, "selected_id": get_selected_id(), "path": models_file_path()}


@router.post("/custom-models")
async def api_create(body: CreateCustomModelRequest):
  try:
    return _mask_model(create_model(body.model_dump()))
  except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))


@router.patch("/custom-models/{model_id}")
async def api_update(model_id: str, body: UpdateCustomModelRequest):
  patch = body.model_dump(exclude_unset=True)
  result = update_model(model_id, patch)
  if not result:
    raise HTTPException(status_code=404, detail="Model not found")
  return _mask_model(result)


@router.delete("/custom-models/{model_id}")
async def api_delete(model_id: str):
  ok = delete_model(model_id)
  if not ok:
    raise HTTPException(status_code=404, detail="Model not found")
  return {"deleted": model_id}


@router.post("/custom-models/selected")
async def api_select(body: SelectRequest):
  target = body.id
  if target is not None:
    if not any(m.get("id") == target for m in list_models()):
      raise HTTPException(status_code=404, detail="Model not found")
  set_selected_id(target)
  return {"selected": target}


@router.get("/custom-models/selected")
async def api_get_selected():
  return {"selected": get_selected_id()}