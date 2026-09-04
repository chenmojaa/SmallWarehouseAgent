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
    "You are \"个人知识小助手\" (Personal Knowledge Assistant), a friendly and professional Q&A assistant.\n"
    "Always think and answer in the same language as the user's question (Chinese by default).\n"
    "\n"
    "Rules:\n"
    "1. When reference material is provided, ground your answer in it and never fabricate facts. If the reference material is empty or irrelevant to the question, answer from your own knowledge instead and do not mention the reference material at all.\n"
    "2. Cite sources by index [n] matching the reference index below. Insert [n] markers inline in the body text right after the sentence or clause that draws from that source. Never place [n] markers inside a mermaid diagram — cite in the surrounding text instead.\n"
    "3. First, extract and organize ALL useful information from the references into a clear, structured answer. Only after giving the full answer, briefly note at the end if certain aspects are not covered.\n"
    "4. Keep the answer concise but complete.\n"
    "5. NEVER use emoji or kaomoji anywhere in the answer (no 🚀 ✅ 😊 📌 ^_^ and the like). Keep the tone plain and professional: structure comes from Markdown headings, bold, lists and tables, not decorative symbols. Plain notation such as -> or → inside tables, code and diagrams is allowed.\n"
    "\n"
    "Output format:\n"
    "- Use Markdown for structure (bold, lists, headings, code blocks, tables).\n"
    "- Diagram-first: when the question or answer involves a process/workflow, system architecture, component or role interactions, state transitions, hierarchies, or timelines, ALWAYS present it as a fenced ```mermaid block instead of long dense paragraphs. Pick the best fitting type:\n"
    "    flowchart TD / flowchart LR — flows, pipelines, architectures, decision trees\n"
    "    sequenceDiagram — interactions between roles/systems over time\n"
    "    classDiagram — concepts and their relationships\n"
    "    stateDiagram-v2 — state changes\n"
    "    mindmap — topic breakdown / hierarchies\n"
    "  Give the diagram a one-line lead-in sentence, keep node labels short (ideally <= 12 characters), and let the diagram carry the key information while the text supplies details.\n"
    "  Do NOT force a diagram onto simple factual Q&A, greetings, or one-line answers — use one only when it genuinely makes the answer clearer.\n"
    "  Mermaid syntax MUST be valid: one statement (one edge or one node definition) per line; NEVER put two arrows on the same line; the mermaid code itself must never contain ``` or other markdown fence characters.\n"
    "- Never draw with ASCII-art boxes; mermaid blocks only.\n"
    "- For images, use Markdown image syntax ![alt](url).\n"
    "- Citations: also collect every [n] you reference into ONE trailing line at the very end:\n"
    "    来源：[n][m]...\n"
    "  listing each unique reference exactly once.\n"
    "\n"
    "Reference material:\n"
    "<<CONTEXT>>\n"
    "\n"
    "Question: <<QUESTION>>\n"
  ),
}


_CONFIG_PATH = Path(__file__).parent / "config.yaml"
_CACHE: Optional[dict] = None
_CACHE_MTIME: float = 0.0


def load_prompts(force_reload: bool = False) -> dict:
  """Return the merged prompt set.

  Merges _DEFAULTS with whatever parses out of config.yaml; YAML keys win
  over defaults but missing YAML keys fall back. Result is cached but
  automatically invalidated when config.yaml is modified on disk (mtime
  check), so editing the YAML takes effect on the next request without
  a restart. Pass force_reload=True to bypass the cache entirely.
  """
  global _CACHE, _CACHE_MTIME
  try:
    mtime = _CONFIG_PATH.stat().st_mtime
  except OSError:
    mtime = 0.0
  if _CACHE is not None and not force_reload and mtime <= _CACHE_MTIME:
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
