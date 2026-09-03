"""Cross-encoder reranking using BAAI/bge-reranker-v2-m3.

Wraps a sentence-transformers CrossEncoder. Loaded lazily on first call so
the heavy model download (~2 GB) only happens when retrieval actually needs
it, and so unit tests / cold-start smoke tests can skip it.

Disable at runtime with the environment variable RERANK_ENABLED=0.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Optional

_MODEL_NAME = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
_model_lock = threading.Lock()
_model_singleton: Optional[Any] = None


def _is_enabled() -> bool:
    flag = os.environ.get("RERANK_ENABLED", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def _get_model():
    """Lazy-load the cross-encoder once, guarded by a lock for thread safety."""
    global _model_singleton
    if _model_singleton is None:
        with _model_lock:
            if _model_singleton is None:
                from sentence_transformers import CrossEncoder
                _model_singleton = CrossEncoder(_MODEL_NAME)
    return _model_singleton


def rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """Score each candidate against `query` and return the top_k highest-scoring.

    Each candidate dict must contain a `text` field. Adds `_rerank_score`
    (float) to every input dict and to the returned ones. Input order is
    not preserved; the input list is sorted in place and sliced.
    """
    if not candidates:
        return []
    if not _is_enabled():
        for c in candidates:
            c.setdefault("_rerank_score", 0.0)
        return candidates[: max(0, top_k)]
    pairs = [(query, c.get("text", "") or "") for c in candidates]
    model = _get_model()
    scores = model.predict(pairs).tolist()
    for cand, score in zip(candidates, scores):
        cand["_rerank_score"] = float(score)
    candidates.sort(key=lambda x: x.get("_rerank_score", 0.0), reverse=True)
    return candidates[: max(0, top_k)]
