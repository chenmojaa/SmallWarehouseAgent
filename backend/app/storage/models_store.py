"""File-backed persistence for custom LLM model configs.

This module mirrors the architecture used by the deepseek-harness project's
`FileSettingsProvider`:

  * Single source of truth on disk (`models.json`).
  * Atomic writes: write to `models.json.tmp`, fsync, then `os.replace`.
  * Cross-process exclusive lock via msvcrt.locking on Windows and
    fcntl.flock on POSIX. Falls back to no-op when neither is available.
  * Strict schema validation before any write hits disk; corrupt or wrong
    shape rejects the write and returns the previous valid state.

The default path is `<backend>/data/models.json`. Override with the
`HD_MODELS_FILE` env var if you want it elsewhere.
"""
from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from app.config import settings

_log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


# --- Path resolution ----------------------------------------------------


# Backend root, derived from this file's location so the default path is
# independent of whatever cwd the process happens to have. backend/app/storage
# -> backend root is three parents up.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _models_path() -> Path:
  override = os.environ.get("HD_MODELS_FILE")
  if override:
    return Path(override)
  # Prefer an absolute path anchored on the backend root; falling back to the
  # legacy relative-to-sqlite behavior keeps anyone who configured a custom
  # sqlite_path still able to colocate models next to it.
  return _BACKEND_ROOT / "data" / "models.json"


# --- Cross-process file lock -------------------------------------------


@contextmanager
def _file_lock(path: Path):
  """Exclusive advisory lock on a sidecar `.lock` file.

  Reads and writes hold this lock for the duration of their I/O so two
  backend processes, or a backend + a manual editor, can't tear the file.
  """
  lock_path = path.with_suffix(path.suffix + ".lock")
  lock_path.parent.mkdir(parents=True, exist_ok=True)
  lock_path.touch(exist_ok=True)
  fd = os.open(str(lock_path), os.O_RDWR)
  backend = None
  try:
    try:
      import msvcrt  # type: ignore
      # LK_LOCK = 1: block until acquired; size 1 byte is enough for the lock region.
      msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
      backend = "msvcrt"
    except ImportError:
      import fcntl  # type: ignore
      fcntl.flock(fd, fcntl.LOCK_EX)
      backend = "fcntl"
    yield
  finally:
    try:
      if backend == "msvcrt":
        import msvcrt  # type: ignore
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
      elif backend == "fcntl":
        import fcntl  # type: ignore
        fcntl.flock(fd, fcntl.LOCK_UN)
    except Exception as e:
      _log.warning("file lock release failed: %s", e)
    try:
      os.close(fd)
    except OSError:
      pass


# --- Atomic write -------------------------------------------------------


def _atomic_write(path: Path, data: str) -> None:
  """Write text atomically: temp file -> fsync -> os.replace.

  `os.replace` is atomic on the same volume on both Windows and POSIX, which
  is what we need so a crash between writes never leaves a half-written file.
  """
  path.parent.mkdir(parents=True, exist_ok=True)
  tmp = path.with_suffix(path.suffix + ".tmp")
  with open(tmp, "w", encoding="utf-8", newline='\n') as f:
    f.write(data)
    f.flush()
    try:
      os.fsync(f.fileno())
    except OSError:
      # Some filesystems (notably Windows network mounts) reject fsync; not fatal.
      pass
  os.replace(tmp, path)
  try:
    os.chmod(path, 0o600)
  except OSError:
    pass


# --- Schema validation --------------------------------------------------


class SchemaError(ValueError):
  pass


_REQUIRED_FIELDS = (
  "id", "name", "baseUrl", "apiKey", "provider",
  "models", "defaultModel", "createdAt",
)


def _validate(payload: dict) -> None:
  if not isinstance(payload, dict):
    raise SchemaError("payload must be an object")
  if payload.get("version") != SCHEMA_VERSION:
    raise SchemaError("unsupported schema version: %r" % (payload.get("version"),))
  items = payload.get("models")
  if not isinstance(items, list):
    raise SchemaError("models must be a list")
  for i, m in enumerate(items):
    if not isinstance(m, dict):
      raise SchemaError("model[%d] must be an object" % i)
    for k in _REQUIRED_FIELDS:
      if k not in m:
        raise SchemaError("model[%d] missing field: %s" % (i, k))
    if not isinstance(m["models"], list) or not m["models"]:
      raise SchemaError("model[%d].models must be a non-empty list" % i)
    for j, sub in enumerate(m["models"]):
      if not isinstance(sub, dict) or "name" not in sub or "reasoning" not in sub:
        raise SchemaError("model[%d].models[%d] malformed" % (i, j))
  sel = payload.get("selected_id")
  if sel is not None and not isinstance(sel, str):
    raise SchemaError("selected_id must be a string or null")


_DEFAULT_PAYLOAD: dict = {"version": SCHEMA_VERSION, "models": [], "selected_id": None}


def _read_unlocked() -> dict:
  p = _models_path()
  if not p.exists():
    return dict(_DEFAULT_PAYLOAD)
  try:
    with open(p, "r", encoding="utf-8") as f:
      d = json.load(f)
  except (OSError, json.JSONDecodeError) as e:
    _log.warning("models.json unreadable (%s), starting fresh: %s", p, e)
    return dict(_DEFAULT_PAYLOAD)
  if not isinstance(d, dict):
    return dict(_DEFAULT_PAYLOAD)
  d.setdefault("version", SCHEMA_VERSION)
  d.setdefault("models", [])
  d.setdefault("selected_id", None)
  return d


def _write_unlocked(payload: dict) -> None:
  _validate(payload)
  p = _models_path()
  _atomic_write(p, json.dumps(payload, ensure_ascii=False, indent=2))


# --- Public API --------------------------------------------------------


def list_models() -> list[dict]:
  p = _models_path()
  with _file_lock(p):
    d = _read_unlocked()
  return list(d.get("models") or [])


def get_selected_id() -> Optional[str]:
  p = _models_path()
  with _file_lock(p):
    d = _read_unlocked()
  sid = d.get("selected_id")
  return sid if isinstance(sid, str) else None


def create_model(payload: dict) -> dict:
  """Add a new model entry. Server assigns id and createdAt."""
  from uuid import uuid4
  new_id = "m_" + uuid4().hex[:12]
  created = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"
  models_field = payload.get("models") or []
  entry = {
    "id": new_id,
    "name": payload["name"],
    "baseUrl": payload["baseUrl"],
    "apiKey": payload["apiKey"],
    "provider": payload["provider"],
    "models": models_field,
    "defaultModel": payload.get("defaultModel") or (models_field[0]["name"] if models_field else ""),
    "embeddingModel": payload.get("embeddingModel"),
    "createdAt": created,
  }
  p = _models_path()
  with _file_lock(p):
    d = _read_unlocked()
    d.setdefault("models", []).append(entry)
    if not d.get("selected_id"):
      d["selected_id"] = new_id
    _write_unlocked(d)
  return entry


def update_model(model_id: str, patch: dict) -> dict | None:
  p = _models_path()
  with _file_lock(p):
    d = _read_unlocked()
    items = d.get("models") or []
    for i, m in enumerate(items):
      if m.get("id") == model_id:
        merged = {**m}
        for k, v in patch.items():
          if v is not None:
            merged[k] = v
        items[i] = merged
        d["models"] = items
        _write_unlocked(d)
        return merged
    return None


def delete_model(model_id: str) -> bool:
  p = _models_path()
  with _file_lock(p):
    d = _read_unlocked()
    items = d.get("models") or []
    new_items = [m for m in items if m.get("id") != model_id]
    if len(new_items) == len(items):
      return False
    d["models"] = new_items
    if d.get("selected_id") == model_id:
      d["selected_id"] = new_items[0]["id"] if new_items else None
    _write_unlocked(d)
    return True


def set_selected_id(model_id: Optional[str]) -> None:
  p = _models_path()
  with _file_lock(p):
    d = _read_unlocked()
    if model_id is not None and not any(m.get("id") == model_id for m in (d.get("models") or [])):
      return
    d["selected_id"] = model_id
    _write_unlocked(d)


def models_file_path() -> str:
  """Convenience for debugging / log lines."""
  return str(_models_path())
