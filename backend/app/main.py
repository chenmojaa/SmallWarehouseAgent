import logging
import os

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

logging.basicConfig(
  level=settings.log_level.upper(),
  format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = int(os.environ.get("HD_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
_ALLOWED_ORIGINS = [
  o.strip() for o in os.environ.get("HD_ALLOWED_ORIGINS", "").split(",") if o.strip()
] or ["http://127.0.0.1:5174", "http://localhost:5174"]

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

app.include_router(health_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(notes_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(sessions_router, prefix="/api")
app.include_router(custom_models_router, prefix="/api")


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
  logger.info("=" * 50)
