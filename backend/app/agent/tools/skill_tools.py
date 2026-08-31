"""LangChain tool wrappers around locally installed agent skills.

Each installed skill (``backend/data/skills/installed/<id>/SKILL.md``) is exposed
as a `StructuredTool` so the model can load its instructions on demand. We do
NOT try to dynamically generate skill behaviour - the model reads the SKILL.md
content as guidance and the actual code/scripts inside the skill folder are the
human-authored actions the model describes.

Two tools are exposed per skill:
  - ``load_skill_<id>`` returns the SKILL.md body verbatim.
  - ``invoke_skill_<id>`` returns a one-line stub so the model knows the skill
    is callable; the real "call" is the SKILL.md instructions.

We intentionally do NOT execute skill scripts inside the agent loop unless the
user explicitly asks for it (that becomes a separate explicit endpoint).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.config import settings

_log = logging.getLogger(__name__)


def _skills_root() -> Path:
  return Path(settings.data_dir) / "skills" / "installed"


def _read_skill(skill_id: str, max_chars: int = 8000) -> str | None:
  """Return SKILL.md body, trimmed. ``None`` if not found or too large."""
  skill_root = _skills_root()
  # Prefer <id>/SKILL.md, fall back to search.
  candidate = skill_root / skill_id / "SKILL.md"
  if not candidate.exists():
    matches = list(skill_root.glob("%s/SKILL.md" % skill_id))
    if not matches:
      return None
    candidate = matches[0]
  try:
    text = candidate.read_text(encoding="utf-8")
  except OSError as e:
    _log.warning("skill %s: cannot read SKILL.md: %s", skill_id, e)
    return None
  if len(text) > max_chars:
    return text[:max_chars] + "\n\n... (truncated; full file at %s)" % candidate
  return text


def _list_installed_skills() -> list[dict]:
  """Best-effort read of the registry, mirroring app/api/skills.py::_load_installed."""
  import json
  registry = Path(settings.data_dir) / "skills" / "installed.json"
  if not registry.exists():
    return []
  try:
    payload = json.loads(registry.read_text(encoding="utf-8-sig"))
  except (OSError, ValueError):
    return []
  items = payload.get("installed", []) if isinstance(payload, dict) else []
  return [it for it in items if isinstance(it, dict) and isinstance(it.get("id"), str)]


class _LoadSkillInput(BaseModel):
  skill_id: str = Field(description="The id of the installed skill, e.g. ``docx``.")


class _InvokeSkillInput(BaseModel):
  skill_id: str = Field(description="The id of the installed skill to invoke.")
  task: str = Field(description="What you want the skill to help with. The skill's instructions will be returned alongside your task so you can follow them.")


def build_skill_tools() -> list[StructuredTool]:
  """Return one ``load_skill`` and one ``invoke_skill`` tool per installed skill."""
  tools: list[StructuredTool] = []
  installed = _list_installed_skills()
  if not installed:
    return tools

  def _load_skill(skill_id: str) -> str:
    body = _read_skill(skill_id)
    if body is None:
      return "Skill %r is not installed. Run the skills API to install it." % skill_id
    return "[SKILL.md for %s]\n%s" % (skill_id, body)

  def _invoke_skill(skill_id: str, task: str) -> str:
    body = _read_skill(skill_id)
    if body is None:
      return "Skill %r is not installed." % skill_id
    prefix = "[skill %s invoked: read the SKILL.md below and produce the requested output. Do NOT execute scripts.]" % skill_id
    return "%s\n\n[task]\n%s\n\n[skill instructions]\n%s" % (prefix, task, body)

  # Single shared tools that accept the id; cleaner than N dynamic tools per skill.
  tools.append(StructuredTool.from_function(
    func=_load_skill,
    name="load_skill",
    description=(
      "Load the SKILL.md (instructions + capabilities) for an installed skill. "
      "Use this when you want to know what a skill can do before invoking it. "
      "Input: { skill_id: string }."
    ),
    args_schema=_LoadSkillInput,
  ))
  tools.append(StructuredTool.from_function(
    func=_invoke_skill,
    name="invoke_skill",
    description=(
      "Invoke an installed skill by id with a task description. Returns the "
      "skill's SKILL.md plus your task so you can follow the skill's documented "
      "workflow and produce the result yourself. Use after `load_skill` if you "
      "are unsure of the skill's contract. Input: { skill_id: string, task: string }."
    ),
    args_schema=_InvokeSkillInput,
  ))
  return tools


def list_skill_briefs() -> list[dict[str, Any]]:
  """Return ``[{id, name, description}]`` for the system prompt inventory."""
  out: list[dict[str, Any]] = []
  for it in _list_installed_skills():
    out.append({
      "id": it.get("id"),
      "name": it.get("name", it.get("id")),
      "description": (it.get("description") or "")[:200],
    })
  return out