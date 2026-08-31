"""Authentication API: phone+password register / login / change password.

Token: stateless HMAC-signed token `userId.exp.signature`, secret persisted
in data/auth_secret so tokens survive restarts.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session as DBSession, select

from app.config import settings
from app.storage.db import User, get_engine

router = APIRouter(prefix="/auth", tags=["auth"])

PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 days

# ---- HMAC secret (persisted) ----
_SECRET_FILE = Path(settings.data_dir) / "auth_secret"
_secret_cache: Optional[str] = None


def _get_secret() -> str:
  global _secret_cache
  if _secret_cache is None:
    _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _SECRET_FILE.exists():
      _secret_cache = _SECRET_FILE.read_text(encoding="utf-8").strip()
    else:
      _secret_cache = secrets.token_hex(32)
      _SECRET_FILE.write_text(_secret_cache, encoding="utf-8")
  return _secret_cache


# ---- Password hashing ----
def _hash_password(password: str, salt: str) -> str:
  return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()


# ---- Token ----
def make_token(user_id: int) -> str:
  payload = f"{user_id}.{int(time.time()) + TOKEN_TTL_SECONDS}"
  sig = hmac.new(_get_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
  return f"{payload}.{sig}"


def verify_token(token: str) -> Optional[int]:
  """Return user_id if the token is valid and not expired, else None."""
  if not token:
    return None
  parts = token.split(".")
  if len(parts) != 3:
    return None
  user_id_s, exp_s, sig = parts
  payload = f"{user_id_s}.{exp_s}"
  expected = hmac.new(_get_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
  if not hmac.compare_digest(sig, expected):
    return None
  try:
    if int(exp_s) < time.time():
      return None
    return int(user_id_s)
  except ValueError:
    return None


# ---- Helpers ----
def _find_user_by_phone(session: DBSession, phone: str) -> Optional[User]:
  return session.exec(select(User).where(User.phone == phone)).first()


def _validate_phone(phone: str) -> str:
  phone = (phone or "").strip()
  if not PHONE_RE.match(phone):
    raise HTTPException(status_code=400, detail="手机号格式不正确")
  return phone


def _validate_password(password: str) -> str:
  if not password or len(password) < 6:
    raise HTTPException(status_code=400, detail="密码长度至少 6 位")
  return password


# ---- Request models ----
class RegisterReq(BaseModel):
  phone: str
  password: str


class LoginReq(BaseModel):
  account: str   # 手机号
  password: str


class ChangePasswordReq(BaseModel):
  phone: str
  new_password: str


# ---- Endpoints ----
@router.post("/register")
def register(req: RegisterReq):
  """Register with phone + password; phone is stored in the SQLite users table."""
  phone = _validate_phone(req.phone)
  password = _validate_password(req.password)
  with DBSession(get_engine()) as session:
    if _find_user_by_phone(session, phone):
      raise HTTPException(status_code=409, detail="该手机号已注册")
    salt = secrets.token_hex(16)
    user = User(phone=phone, password_salt=salt, password_hash=_hash_password(password, salt))
    session.add(user)
    session.commit()
    session.refresh(user)
    return {"ok": True, "user_id": user.id, "phone": user.phone, "token": make_token(user.id)}


@router.post("/login")
def login(req: LoginReq):
  """Login with account (phone) + password."""
  phone = (req.account or "").strip()
  password = req.password or ""
  with DBSession(get_engine()) as session:
    user = _find_user_by_phone(session, phone)
    if not user:
      raise HTTPException(status_code=401, detail="账号不存在，请先注册")
    if not hmac.compare_digest(user.password_hash, _hash_password(password, user.password_salt)):
      raise HTTPException(status_code=401, detail="密码错误")
    return {"ok": True, "user_id": user.id, "phone": user.phone, "token": make_token(user.id)}


@router.post("/change-password")
def change_password(req: ChangePasswordReq):
  """Change password: first checks whether the phone exists in the database."""
  phone = _validate_phone(req.phone)
  new_password = _validate_password(req.new_password)
  with DBSession(get_engine()) as session:
    user = _find_user_by_phone(session, phone)
    if not user:
      raise HTTPException(status_code=404, detail="该手机号不存在，无法修改密码")
    salt = secrets.token_hex(16)
    user.password_salt = salt
    user.password_hash = _hash_password(new_password, salt)
    user.updated_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    return {"ok": True}


@router.get("/me")
def me(request: Request):
  """Return current logged-in user; user_id is injected by the auth middleware."""
  user_id = getattr(request.state, "user_id", None)
  if user_id is None:
    raise HTTPException(status_code=401, detail="未登录")
  with DBSession(get_engine()) as session:
    user = session.get(User, user_id)
    if not user:
      raise HTTPException(status_code=401, detail="用户不存在")
    return {"user_id": user.id, "phone": user.phone}
