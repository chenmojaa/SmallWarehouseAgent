"""Server-side persistence for the user's LLM / embedding API key.

The frontend keeps the key in localStorage and sends it per-request via the
X-API-Key header, which works for interactive chat. But background jobs
(Feishu auto-sync re-vectorization) run without any request context and had no
key, so automatic re-embedding always failed.

This store lets the frontend also save the key server-side (masked on read) so
background processes can embed. Priority for embedding key resolution:
request-provided > .env > this store.
"""
from __future__ import annotations

import json
import os
import threading

from app.config import settings

_LOCK = threading.Lock()


def _path() -> str:
  return os.path.join(settings.data_dir, "llm_config.json")


def _read() -> dict:
  try:
    with open(_path(), "r", encoding="utf-8") as f:
      return json.load(f)
  except Exception:
    return {}


def _write(data: dict) -> None:
  os.makedirs(settings.data_dir, exist_ok=True)
  tmp = _path() + ".tmp"
  with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
  os.replace(tmp, _path())


def get_api_key() -> str:
  with _LOCK:
    return (_read().get("api_key") or "").strip()


def get_base_url() -> str:
  with _LOCK:
    return (_read().get("base_url") or "").strip()


def get_config() -> dict:
  key = get_api_key()
  return {
    "api_key_set": bool(key),
    "api_key_masked": (key[:4] + "****" + key[-2:]) if len(key) > 6 else ("****" if key else ""),
    "base_url": get_base_url(),
  }


def update_config(patch: dict) -> dict:
  with _LOCK:
    data = _read()
    if patch.get("api_key"):
      data["api_key"] = str(patch["api_key"]).strip()
    if "base_url" in patch:
      data["base_url"] = (patch.get("base_url") or "").strip()
    _write(data)
  return get_config()
