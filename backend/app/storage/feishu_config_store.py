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


# ---- Full connection credentials (§per-user KB config) ----
# Each field resolves with priority: JSON store > env var. This lets every user
# point the app at their own Feishu app (App ID / Secret) and pick which wiki
# spaces to sync, without editing .env or restarting.
def get_app_id() -> str:
  data = _read()
  return (data.get("app_id") or "").strip() or (settings.feishu_app_id or "")


def get_app_secret() -> str:
  data = _read()
  return (data.get("app_secret") or "").strip() or (settings.feishu_app_secret or "")


def get_api_base() -> str:
  data = _read()
  return (data.get("api_base") or "").strip() or (settings.feishu_api_base or "https://open.feishu.cn")


def get_space_ids() -> list[str]:
  """Return the configured wiki space ids (empty = all visible spaces)."""
  data = _read()
  raw = (data.get("space_ids") or "").strip() or (settings.feishu_space_ids or "")
  return [s.strip() for s in raw.split(",") if s.strip()]


def is_configured() -> bool:
  """True when we have enough credentials to talk to Feishu at all."""
  return bool(get_app_id() and get_app_secret())


def is_enabled() -> bool:
  """Feishu is active when credentials exist (UI-config or env) and env flag is on.

  We treat a UI-configured app_id/secret as an explicit opt-in so a user who
  fills in the settings form does not also have to flip FEISHU_ENABLED in .env.
  """
  data = _read()
  if (data.get("app_id") or "").strip() and (data.get("app_secret") or "").strip():
    return True
  return settings.feishu_enabled


def get_config() -> dict:
  """Return all UI-configurable Feishu settings.

  The app_secret is masked in the response so it is never echoed back to the
  client in full.
  """
  secret = get_app_secret()
  return {
    "web_url": get_web_url(),
    "app_id": get_app_id(),
    "app_secret_set": bool(secret),
    "app_secret_masked": (secret[:4] + "****" + secret[-2:]) if len(secret) > 6 else ("****" if secret else ""),
    "api_base": get_api_base(),
    "space_ids": get_space_ids(),
    "enabled": is_enabled(),
    "configured": is_configured(),
    "sync_interval_min": settings.feishu_sync_interval_min,
  }


def update_config(patch: dict) -> dict:
  """Update UI-configurable Feishu settings and persist to disk.

  Writable keys: web_url, app_id, app_secret, api_base, space_ids. An empty
  app_secret value means "keep the existing one" so the UI can save other fields
  without re-typing the secret.
  """
  data = _read()
  if "web_url" in patch:
    data["web_url"] = (patch.get("web_url") or "").strip()
  if "app_id" in patch:
    data["app_id"] = (patch.get("app_id") or "").strip()
  if "api_base" in patch:
    data["api_base"] = (patch.get("api_base") or "").strip()
  if "space_ids" in patch:
    ids = patch.get("space_ids")
    if isinstance(ids, list):
      data["space_ids"] = ",".join(str(s).strip() for s in ids if str(s).strip())
    else:
      data["space_ids"] = (ids or "").strip()
  if patch.get("app_secret"):
    data["app_secret"] = str(patch["app_secret"]).strip()
  _write(data)
  return get_config()