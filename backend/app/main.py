import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.api.health import router as health_router
from app.api.chat import router as chat_router
from app.api.settings import router as settings_router
from app.api.notes import router as notes_router
from app.api.search import router as search_router
from app.api.sessions import router as sessions_router
from app.api.custom_models import router as custom_models_router
from app.api.feishu import router as feishu_router
from app.api.skills import router as skills_router
from app.api.auth import router as auth_router
from app.api.mcp import router as mcp_router
from app.api.memory import router as memory_router

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_root = logging.getLogger()
_root.setLevel(settings.log_level.upper())
_stream = logging.StreamHandler()
_stream.setFormatter(_fmt)
_root.addHandler(_stream)
# Rotating file handler: 10MB x 5 backups (per OPTIMIZATION.md \u00a73)
_file = RotatingFileHandler(
  LOG_DIR / "hd.log",
  maxBytes=10 * 1024 * 1024,
  backupCount=5,
  encoding="utf-8",
)
_file.setFormatter(_fmt)
_root.addHandler(_file)
logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = int(os.environ.get("HD_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
_ALLOWED_ORIGINS = [
  o.strip() for o in os.environ.get("HD_ALLOWED_ORIGINS", "").split(",") if o.strip()
] or [
  "http://127.0.0.1:5174", "http://localhost:5174",
  "https://11gv92qt74799.vicp.fun",
]

app = FastAPI(
  title="HEAR Agent",
  description="Personal knowledge base with multi-LLM + RAG + chat history",
  version="0.6.0",
)

app.add_middleware(
  CORSMiddleware,
  allow_origins=_ALLOWED_ORIGINS,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)


@app.middleware("http")
async def _limit_upload_size(request: Request, call_next):
  cl = request.headers.get("content-length")
  if cl and cl.isdigit() and int(cl) > MAX_UPLOAD_BYTES:
    return JSONResponse(
      status_code=413,
      content={"detail": "payload too large (>%d bytes)" % MAX_UPLOAD_BYTES},
    )
  return await call_next(request)


@app.middleware("http")
async def _require_auth(request: Request, call_next):
  """Protect all /api routes except /api/auth/* and /api/health.

  Accepts `Authorization: Bearer <token>` or `X-Auth-Token: <token>`.
  Sets request.state.user_id on success so endpoints can identify the user.
  """
  path = request.url.path
  is_auth_endpoint = path.startswith("/api/auth") and path != "/api/auth/me"
  if path.startswith("/api") and not is_auth_endpoint and path != "/api/health":
    from app.api.auth import verify_token
    token = (request.headers.get("authorization") or "").strip()
    if token.lower().startswith("bearer "):
      token = token[7:].strip()
    if not token:
      token = (request.headers.get("x-auth-token") or "").strip()
    user_id = verify_token(token)
    if user_id is None:
      return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})
    request.state.user_id = user_id
  return await call_next(request)


@app.middleware("http")
async def _mirror_api_key(request: Request, call_next):
  """Persist the per-request API key server-side (best effort).

  The frontend sends the user's key on every request via X-API-Key. Background
  jobs (Feishu auto-sync re-vectorization) have no request context, so the first
  time we see a key we also store it in llm_config_store. This makes background
  embedding work regardless of which domain the user opened the app from.
  """
  key = (request.headers.get("x-api-key") or "").strip()
  if key:
    try:
      from app.storage import llm_config_store as _lcs
      if not _lcs.get_api_key():
        _lcs.update_config({"api_key": key})
    except Exception:
      pass
  return await call_next(request)

app.include_router(health_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(notes_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(custom_models_router, prefix="/api")
app.include_router(feishu_router, prefix="/api")
app.include_router(skills_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(memory_router, prefix="/api")

app.include_router(mcp_router, prefix='/api')

# ---- Serve frontend static files (for 花生壳 / production) ----
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
  from fastapi.staticfiles import StaticFiles
  app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")
  # Favicon & other root-level static files
  for _f in _FRONTEND_DIST.glob("*"):
    if _f.is_file():
      _name = _f.name
      app.mount(f"/{_name}", StaticFiles(directory=str(_FRONTEND_DIST)), name=f"static_{_name}")

  @app.get("/{_:path}")
  async def _spa_fallback(_: str):
    """Serve index.html for SPA client-side routing. Non-API GET requests fall here."""
    from fastapi.responses import FileResponse
    return FileResponse(_FRONTEND_DIST / "index.html")

  @app.get("/")
  async def _root():
    from fastapi.responses import FileResponse
    return FileResponse(_FRONTEND_DIST / "index.html")

  logger.info(f"Frontend static files mounted from {_FRONTEND_DIST}")


@app.on_event("startup")
async def _startup():
  logger.info("=" * 50)
  logger.info("HEAR Agent starting up (v0.6 + LangChain + LangGraph + multi-format)")
  logger.info(f"LLM:      {settings.llm_provider}/{settings.llm_model}")
  logger.info(f"Embedding:{settings.embedding_provider}/{settings.embedding_model}")
  logger.info(f"Storage:  SQLite={settings.sqlite_path}")
  logger.info(f"Server:   http://{settings.host}:{settings.port}")
  logger.info("Supported file types: pdf, docx, pptx, xlsx, csv, html, txt/md, images(OCR)")
  try:
    from app.tools.ocr import _find_tesseract
    tess = _find_tesseract()
    if tess:
      from pathlib import Path
      td = Path(tess).parent / "tessdata"
      langs = sorted([p.stem for p in td.glob("*.traineddata")]) if td.exists() else []
      logger.info(f"OCR:      tesseract={tess}, langs={langs}")
      if "chi_sim" not in langs:
        logger.info("OCR hint: Chinese OCR needs chi_sim.traineddata in tessdata/")
    else:
      logger.info("OCR:      tesseract NOT installed (image OCR disabled)")
  except Exception as e:
    logger.info(f"OCR check failed: {e}")

  # ---- Feishu background sync ----
  # The loop always starts and re-checks the runtime config each tick, so a user
  # who fills in the Feishu settings form after boot gets syncing without a
  # restart. When not configured/enabled the tick is a cheap no-op.
  if settings.feishu_sync_interval_min > 0:
    import asyncio
    from app.feishu_sync import sync_all
    from app.storage import feishu_config_store as _fcs
    interval_s = max(60, settings.feishu_sync_interval_min * 60)
    async def _feishu_loop():
      logger.info(f"Feishu background sync loop started, interval={interval_s}s")
      while True:
        try:
          if _fcs.is_enabled():
            results = await asyncio.to_thread(sync_all)
            for r in results:
              logger.info(
                f"Feishu sync [{r.space_name}]: synced={r.synced} skipped={r.skipped} failed={r.failed}"
              )
        except Exception as e:
          logger.warning(f"Feishu background sync failed: {type(e).__name__}: {e}")
        await asyncio.sleep(interval_s)
    asyncio.create_task(_feishu_loop())
  else:
    logger.info("Feishu sync interval=0 (manual sync only)")

  logger.info("=" * 50)
