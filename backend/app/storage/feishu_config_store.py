"""File-backed persistence for UI-configurable Feishu settings.

Stored in <backend>/data/feishu_config.json. Atomic writes.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app.config import settings

_log = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _config_path() -> Path:
  return _BACKEND_ROOT / "data" / "feishu_config.json"


def _read() -> dict:
  p = _config_path()
  if not p.exists():
    return {}
  try:
    with open(p, "r", encoding="utf-8") as f:
      return json.load(f)
  except (OSError, json.JSONDecodeError):
    return {}


def _write(data: dict) -> None:
  p = _config_path()
  p.parent.mkdir(parents=True, exist_ok=True)
  tmp = p.with_suffix(p.suffix + ".tmp")
  with open(tmp, "w", encoding="utf-8", newline="\n") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.flush()
    try:
      os.fsync(f.fileno())
    except OSError:
      pass
  os.replace(tmp, p)


def get_web_url() -> str:
  """Return the configured Feishu web URL.

  Priority: JSON store > env var (FEISHU_WEB_URL).
  """
  data = _read()
  url = data.get("web_url", "")
  if url:
    return url
  return settings.feishu_web_url or ""


def set_web_url(url: str) -> None:
  """Update the Feishu web URL and persist to disk."""
  data = _read()
  data["web_url"] = url.strip()
  _write(data)


def get_config() -> dict:
  """Return all UI-configurable Feishu settings."""
  return {
    "web_url": get_web_url(),
    "enabled": settings.feishu_enabled,
    "api_base": settings.feishu_api_base,
    "sync_interval_min": settings.feishu_sync_interval_min,
  }


def update_config(patch: dict) -> dict:
  """Update UI-configurable Feishu settings. Only 'web_url' is writable."""
  if "web_url" in patch:
    set_web_url(patch["web_url"])
  return get_config()