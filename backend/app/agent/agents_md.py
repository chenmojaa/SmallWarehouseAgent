"""AGENTS.md / project-context loader.

Implements the same layered-context convention Codex CLI + Claude Code use:
a flat ``AGENTS.md`` file (or ``.agents.md`` / ``CLAUDE.md``) at the project
root becomes standing instructions for the agent. Path resolution matches
the AGENTS.md spec: search upwards from the active file's parent; merge in
priority order.

This module also exposes ``project_rules()`` which returns the loaded text
formatted for prompt injection. The loader never raises - any malformed
file yields an empty string and a debug-level log entry.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable

_log = logging.getLogger(__name__)

# Candidate filenames in priority order. Codex / Claude both treat these
# as standing-instruction files and we accept any of them.
_CANDIDATES = ("AGENTS.md", ".agents.md", "CLAUDE.md", ".claude.md")

# Cap so a multi-MB rules file does not blow up the context budget.
_MAX_BYTES = 32 * 1024

# Project root discovery: walk up looking for the marker.
_DEFAULT_SEARCH_DEPTH = 6


def _read_text(path: Path) -> str | None:
    try:
        if not path.is_file():
            return None
        size = path.stat().st_size
        if size > _MAX_BYTES:
            data = path.read_bytes()[:_MAX_BYTES]
            _log.info("agents_md truncated: %s (%d > %d bytes)", path, size, _MAX_BYTES)
            return data.decode("utf-8", errors="ignore") + "\n\n[... truncated ...]"
        return path.read_text(encoding="utf-8")
    except Exception as e:
        _log.debug("agents_md read failed for %s: %s", path, e)
        return None


def _find_agents_md(start: Path, max_depth: int = _DEFAULT_SEARCH_DEPTH) -> Path | None:
    """Walk up directories looking for an AGENTS.md (or variant) file."""
    cur = start.resolve()
    for _ in range(max_depth + 1):
        for name in _CANDIDATES:
            candidate = cur / name
            if candidate.is_file():
                return candidate
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def _find_cwd_agents() -> str:
    """Pick the closest AGENTS.md relative to CWD via walk-up."""
    start = Path(os.getcwd())
    found = _find_agents_md(start)
    if found:
        return "<source>" + str(found) + "</source>\n" + (_read_text(found) or "")
    return ""


def _merge_parts(parts: Iterable[str]) -> str:
    out: list[str] = []
    for p in parts:
        if p and p.strip():
            out.append(p.strip())
    return "\n\n---\n\n".join(out)


def project_rules(extra_paths: list[str] | None = None) -> str:
    """Return concatenated project-level instructions.

    Sources, in priority order (later wins):
        1. Per-call ``extra_paths`` (explicit attachments)
        2. CWD / walk-up discovery of AGENTS.md / .agents.md / CLAUDE.md

    Each source is wrapped in an XML-ish fence so the answer node can reason
    about provenance.
    """
    parts: list[str] = []
    for raw in extra_paths or []:
        if not raw:
            continue
        p = Path(raw)
        if p.is_file():
            parts.append("<source>" + str(p) + "</source>\n" + (_read_text(p) or ""))
    parts.append(_find_cwd_agents())
    return _merge_parts(parts)


def has_project_rules() -> bool:
    """Quick check used by the API to expose a 'rules attached' indicator."""
    return bool(project_rules())


__all__ = ["project_rules", "has_project_rules"]
