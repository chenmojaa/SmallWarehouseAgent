"""embed_all alias of reindex_all --scope=notes.

Exposed via /api/background/start {"kind": "embed_all"} for the Re-embed
notes button on the Settings page. Functionally identical to reindex with
scope=notes - recomputes embeddings without pulling remote sources.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from app.scripts import reindex_all as _r
sys.argv = [sys.argv[0], "--scope", "notes"] + sys.argv[1:]
sys.exit(_r.main())
