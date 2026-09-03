"""OCR pass over every image-only note that has not been OCR'd yet.

A note counts as image-only when:
  - its source_type is image, OR
  - its body is shorter than 30 chars (almost certainly an OCR miss)

For each such note we re-run OCR against the original source file (when the
source URL still points back to a file under data/uploads/) and overwrite the
.md body. Stdout is line-per-step so the SSE consumer can render a progress
bar.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

logging.basicConfig(level=logging.INFO, format="%(message)s")
_log = logging.getLogger("ocr_all")


def _emit(phase, **kw):
    print(json.dumps({"phase": phase, **kw}, ensure_ascii=False), flush=True)


def _should_ocr(text):
    if not text:
        return True
    return len(text.strip()) < 30


def main():
    _emit("started", script="ocr_all")
    from app.storage import db as _db
    from app.config import settings
    notes = _db.list_all_notes() if hasattr(_db, "list_all_notes") else []
    _emit("info", total=len(notes), unit="note")

    try:
        from app.tools.ocr import ocr_image
        ocr_available = True
    except Exception as e:
        _emit("info", ocr_available=False, reason=str(e)[:200])
        ocr_available = False

    if not ocr_available:
        _emit("done", processed=0, skipped=len(notes), reason="ocr not available")
        return 0

    uploads = Path(settings.data_dir) / "uploads"
    processed = skipped = failed = 0
    for note in notes:
        src = (note.get("source_type") or "").lower()
        body = note.get("text") or note.get("content") or ""
        if src != "image" and not _should_ocr(body):
            skipped += 1
            continue
        candidates = []
        if note.get("source_url"):
            candidates.append(Path(note["source_url"]))
        if note.get("content_path"):
            candidates.append(Path(note["content_path"]))
        candidates.append(uploads / str(note.get("id")))
        target = None
        for c in candidates:
            try:
                if c.is_file():
                    target = c
                    break
            except Exception:
                continue
        if target is None:
            _emit("skip", note_id=note.get("id"), reason="no source file")
            skipped += 1
            continue
        try:
            result = ocr_image(str(target), lang="chi_sim+eng")
            new_text = result.get("text") or ""
        except Exception as e:
            _emit("error", note_id=note.get("id"), detail=str(e)[:200])
            failed += 1
            continue
        if _db.update_note_text(note["id"], new_text):
            processed += 1
            _emit("progress", done=processed, total=len(notes), note_id=note.get("id"))
        else:
            failed += 1
    _emit("done", processed=processed, skipped=skipped, failed=failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
