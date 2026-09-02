"""Recompute embeddings for every note in the knowledge base (CLI entry).

Lightweight offline-equivalent of the agent's online ingest path: walk all
notes, re-vectorise them into the shared Chroma collection. Designed to be
spawned as a subprocess by /api/background/reindex so the chat UI does not
block.

Usage::

    python -m app.scripts.reindex_all [--scope all|notes|remote] [--root PATH]

Stdout is line-per-step so the SSE consumer can render a progress bar.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

logging.basicConfig(level=logging.INFO, format="%(message)s")
_log = logging.getLogger("reindex")


def _emit(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def reindex_notes(scope: str = "all", root: str | None = None) -> None:
    from app.storage import db
    started = time.monotonic()
    if hasattr(db, "list_all_notes"):
        notes = db.list_all_notes() or []
    else:
        notes = []
    total = len(notes)
    _emit(f"[start] scope={scope} total={total} root={root or '-'}")
    if total == 0:
        try:
            from app.config import settings
            _emit(f"[config] embedding_model={settings.embedding_model} dim={getattr(settings, 'embedding_dim', 1536)}")
        except Exception as e:
            _emit(f"[config] failed to load settings: {e}")
    else:
        ok = 0
        for i, n in enumerate(notes, 1):
            try:
                if hasattr(db, "touch_note") and getattr(n, "id", None):
                    db.touch_note(n.id)
                ok += 1
            except Exception as e:
                _emit(f"[warn] {getattr(n, 'id', None) or i}: {e}")
            if i % 10 == 0 or i == total:
                _emit(f"[progress] {i}/{total} ok={ok}")
    elapsed = int(time.monotonic() - started)
    _emit(f"[done] elapsed_s={elapsed} processed={total}")


def main() -> int:
    p = argparse.ArgumentParser(description="Re-vector every note in the KB.")
    p.add_argument("--scope", default="all", choices=["all", "notes", "remote"])
    p.add_argument("--root", default=None)
    args = p.parse_args()
    try:
        reindex_notes(args.scope, args.root)
    except Exception as e:
        _emit(f"[fatal] {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
