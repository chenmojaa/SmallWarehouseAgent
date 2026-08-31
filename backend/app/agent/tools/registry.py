"""Aggregate agent tools + build the short "available capabilities" inventory.

Two artefacts:

  - ``load_tools()``        -> list of LangChain ``StructuredTool`` for tool-calling.
  - ``inventory_text()``    -> one short markdown section injected into the
                               answer system prompt so the model *knows* what
                               MCP servers / skills exist (without having to
                               round-trip through the registry first).

Both are deliberately best-effort: missing packages, broken MCP servers, or
absent skill folders must NEVER crash the agent loop.
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from app.config import settings
from app.agent.tools.skill_tools import build_skill_tools, list_skill_briefs
from app.agent.tools.mcp_tools import build_mcp_tools, list_mcp_briefs

_log = logging.getLogger(__name__)


def load_tools() -> list[BaseTool]:
  """Return all enabled tools for the current turn. Always returns a list."""
  if not settings.tools_enabled:
    return []
  tools: list[BaseTool] = []
  try:
    tools.extend(build_skill_tools())
  except Exception as e:
    _log.warning("skill tools load failed: %s", e)
  try:
    tools.extend(build_mcp_tools())
  except Exception as e:
    _log.warning("mcp tools load failed: %s", e)
  return [t for t in tools if isinstance(t, StructuredTool)]


def inventory_text() -> str:
  """Short, model-facing summary of available skills + MCP servers."""
  if not settings.tools_enabled:
    return ""
  blocks: list[str] = []
  skills = list_skill_briefs()
  mcps = list_mcp_briefs()
  if skills:
    rows = "\n".join("- %s (%s): %s" % (s["id"], s["name"], s.get("description") or "(no description)")
                     for s in skills[:25])
    blocks.append("[Installed skills]\n" + rows)
  if mcps:
    rows = "\n".join("- %s (%s): %s" % (m["id"], m["name"], m.get("description") or "(no description)")
                     for m in mcps[:25])
    blocks.append("[Enabled MCP servers]\n" + rows +
                  "\nUse mcp_list_servers to see command/args and mcp_discover_tools for declared tool names.")
  if not blocks:
    return ""
  return ("\n\nYou have the following external capabilities available via tool calls. "
          "Use them when they would clearly help, without forcing every turn:\n\n" +
          "\n\n".join(blocks))