"""Prompt loader.

Phase 4.1: answer.py used to hardcode ANSWER_INSTRUCTIONS at the top of the
module. Moving it to YAML lets the answer style be retuned without a code
change. Loading order, later wins:

  1. _DEFAULTS below (last-resort fallback if config.yaml is missing or
     malformed; preserves behaviour from before Phase 4.1)
  2. backend/app/agent/prompts/config.yaml (the file you edit day-to-day)
  3. Per-request override passed via state["answer_instructions_override"]
     (added in a follow-up if needed; not wired in Phase 4.1)

The loader is intentionally tiny and dependency-free at import time (yaml
is imported lazily inside load_prompts) so a missing/broken config file
cannot crash agent import.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


_DEFAULTS = {
  "answer_instructions": (
    "You are a strict assistant. Answer the question using ONLY the reference material below.\n"
    "\n"
    "Rules:\n"
    "1. Use only the reference chunks; never fabricate facts.\n"
    "2. Cite sources by index [n] matching the reference index below.\n"
    "3. If the reference material is insufficient, say so explicitly.\n"
    "4. Keep the answer concise.\n"
    "\n"
    "Output format:\n"
    "- Use Markdown for structure (bold, lists, headings, code blocks, tables).\n"
    "- For flowcharts / sequence / class diagrams, use a fenced ```mermaid block.\n"
    "- For images, use Markdown image syntax ![alt](url).\n"
    "- Citations: collect every [n] you reference into ONE trailing line at the very end:\n"
    "    来源：[n][m]...\n"
    "  listing each unique reference exactly once. Do NOT embed [n] markers inside body sentences or list items.\n"
    "\n"
    "Reference material:\n"
    "<<CONTEXT>>\n"
    "\n"
    "Question: <<QUESTION>>\n"
  ),
}


_CONFIG_PATH = Path(__file__).parent / "config.yaml"
_CACHE: Optional[dict] = None


def load_prompts(force_reload: bool = False) -> dict:
  """Return the merged prompt set.

  Merges _DEFAULTS with whatever parses out of config.yaml; YAML keys win
  over defaults but missing YAML keys fall back. Result is cached after
  first call; pass force_reload=True to re-read the file (handy in tests).
  """
  global _CACHE
  if _CACHE is not None and not force_reload:
    return _CACHE
  merged = dict(_DEFAULTS)
  if _CONFIG_PATH.exists():
    try:
      import yaml
      with _CONFIG_PATH.open("r", encoding="utf-8") as f:
        file_cfg = yaml.safe_load(f) or {}
      if isinstance(file_cfg, dict):
        for k, v in file_cfg.items():
          if isinstance(v, str) and v.strip():
            merged[k] = v
    except Exception:
      # Bad YAML must never break the agent. Defaults stay in place.
      pass
  _CACHE = merged
  return merged


def get_answer_instructions() -> str:
  """Convenience accessor used by answer.py."""
  return load_prompts().get("answer_instructions", _DEFAULTS["answer_instructions"])
