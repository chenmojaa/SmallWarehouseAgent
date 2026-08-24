"""Retrieval injection: turn retrieved_chunks into a context block for the LLM.

Phase 4.2: this used to live as a private _format_context() inside answer.py.
Splitting it out makes the "retrieval injection" concern independently
testable and replaceable (e.g., adding token-budget truncation, switching
to a citation-aware re-ranker, supporting multiple rendering modes), without
touching the answer node itself.

The contract is intentionally minimal: in -> list of chunk dicts, out ->
string formatted for a single <<CONTEXT>> placeholder. Future middleware
hooks (pre/post-processing, token counting, dedup) belong in this module
so answer.py keeps doing one thing.
"""
from __future__ import annotations

from typing import Iterable


_EMPTY_CONTEXT = "(no reference material available)"
_SEPARATOR = "\n\n---\n\n"


def format_context(chunks: Iterable[dict] | None) -> str:
  """Render retrieved_chunks as a numbered reference block.

  Each chunk becomes ``[n] source: <title>\n<text>``. Numbers are 1-based
  and match the [n] citation tokens the answer prompt expects.
  """
  if not chunks:
    return _EMPTY_CONTEXT
  out = []
  for i, c in enumerate(chunks, 1):
    title = c.get("title") or c.get("note_id", "?")
    out.append("[%d] source: %s\n%s" % (i, title, c.get("text", "")))
  return _SEPARATOR.join(out)
