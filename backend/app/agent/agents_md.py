"""AGENTS.md / project-context loader.

Mirrors the Codex CLI / Claude Code semantics: standing instructions live in
one or more ``AGENTS.md`` (or ``.agents.md`` / ``CLAUDE.md``) files. We
support layered loading -- a request can pick up rules from a target directory
plus any ancestor up to a configurable depth, and the result includes a list
of provenance entries so the UI can show which files contributed.

Layering rule (Codex-compatible):
  * Each source is read in **target-first** order so deeper / more specific
    rules come BEFORE broader ones in the merged prompt.
  * Per-file content is trimmed to ``_MAX_BYTES`` (32 KB) and capped at
    8 sources total. Anything that fails to read is silently skipped so the
    loader never raises into the calling agent.

Public surface:
  * ``project_rules(extra_paths=, target_path=) -> RuleSet``
  * ``RuleSet.text`` is the merged string ready for prompt injection.
  * ``RuleSet.sources`` is a list of ``RuleSource`` (path, depth, chars).
  * ``RuleSet.total_chars`` plus convenience ``has_project_rules()``.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Optional

_log = logging.getLogger(__name__)

# Candidate filenames in priority order. Codex / Claude both treat these
# as standing-instruction files and we accept any of them.
_CANDIDATES = ("AGENTS.md", ".agents.md", "CLAUDE.md", ".claude.md")

# Cap so a multi-MB rules file does not blow up the context budget.
_MAX_BYTES = 32 * 1024

# Project root discovery: walk up looking for the marker.
_DEFAULT_SEARCH_DEPTH = 6

# Maximum number of sources we ever fold together so the merged prompt stays
# bounded.
_MAX_SOURCES = 8


@dataclass
class RuleSource:
    """One contributing file in a layered rule load."""
    path: str
    depth: int          # 0 = target_path itself, +1 per parent walked up
    chars: int
    truncated: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RuleSet:
    """Layered rule set: merged text + provenance list."""
    text: str = ""
    sources: list[RuleSource] = field(default_factory=list)

    @property
    def total_chars(self) -> int:
        return len(self.text)

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "sources": [s.as_dict() for s in self.sources],
            "total_chars": self.total_chars,
        }


def _read_text(path: Path) -> tuple[str | None, bool]:
    """Return (content, truncated). truncated=False means the file fit."""
    try:
        if not path.is_file():
            return None, False
        size = path.stat().st_size
        if size > _MAX_BYTES:
            data = path.read_bytes()[:_MAX_BYTES]
            _log.info("agents_md truncated: %s (%d > %d bytes)", path, size, _MAX_BYTES)
            return data.decode("utf-8", errors="ignore") + "\n\n[... truncated ...]", True
        return path.read_text(encoding="utf-8"), False
    except Exception as e:
        _log.debug("agents_md read failed for %s: %s", path, e)
        return None, False


def _discover_at(directory: Path) -> Path | None:
    """Return the first marker file inside ``directory`` (or None)."""
    for name in _CANDIDATES:
        cand = directory / name
        if cand.is_file():
            return cand
    return None


def _gather_sources(target: Path, max_depth: int) -> list[tuple[Path, int]]:
    """Walk target + its ancestors up to ``max_depth`` and return existing
    marker files as ``(path, depth)`` pairs -- 0 = target itself, +1 per step.
    Stops the moment we fall out of the filesystem root."""
    out: list[tuple[Path, int]] = []
    cur = target.resolve()
    for d in range(max_depth + 1):
        found = _discover_at(cur)
        if found is not None:
            out.append((found, d))
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
        if d >= _MAX_SOURCES - 1:
            break
    return out


def _merge_parts(parts: Iterable[str]) -> str:
    out: list[str] = []
    for p in parts:
        if p and p.strip():
            out.append(p.strip())
    return "\n\n---\n\n".join(out)


def project_rules(
    extra_paths: list[str] | None = None,
    target_path: str | None = None,
) -> RuleSet:
    """Layered project-rules load.

    1. Explicit extra_paths the caller asked for (highest priority in the prompt)
    2. Walk-up discovery from target_path (or os.getcwd()) -> repo root

    Returns a :class:`RuleSet`. The loader never raises; broken files are
    silently skipped.
    """
    sources: list[RuleSource] = []
    blocks: list[str] = []

    # 1) explicit attachments ------------------------------------------------------
    for raw in extra_paths or []:
        if not raw:
            continue
        p = Path(raw)
        if not p.is_file():
            continue
        text, truncated = _read_text(p)
        if text is None:
            continue
        sources.append(RuleSource(path=str(p), depth=0, chars=len(text), truncated=truncated))
        blocks.append("<source>" + str(p) + "</source>\n" + text)
        if len(sources) >= _MAX_SOURCES:
            break

    # 2) walk-up discovery ---------------------------------------------------------
    start = Path(target_path) if target_path else Path(os.getcwd())
    if start.is_file():
        start = start.parent
    if not sources or len(sources) < _MAX_SOURCES:
        discovered = _gather_sources(start, _DEFAULT_SEARCH_DEPTH)
        for path, depth in discovered:
            if any(s.path == str(path) for s in sources):
                continue  # already loaded via extra_paths
            text, truncated = _read_text(path)
            if text is None:
                continue
            sources.append(RuleSource(path=str(path), depth=depth + 1, chars=len(text), truncated=truncated))
            blocks.append("<source>" + str(path) + " @depth=" + str(depth) + "</source>\n" + text)
            if len(sources) >= _MAX_SOURCES:
                break

    text = _merge_parts(blocks)
    return RuleSet(text=text, sources=sources)


def has_project_rules(extra_paths: list[str] | None = None,
                      target_path: str | None = None) -> bool:
    return bool(project_rules(extra_paths=extra_paths, target_path=target_path).text)


# Back-compat -- existing callers kept working via these thin shims -----------
def project_rules_text(*args, **kwargs) -> str:
    """Compatibility shim: returns just the merged text."""
    return project_rules(*args, **kwargs).text


__all__ = [
    "RuleSource",
    "RuleSet",
    "project_rules",
    "has_project_rules",
    "project_rules_text",
]
