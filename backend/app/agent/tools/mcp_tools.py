"""LangChain tool wrappers around locally registered MCP servers.

We expose two aggregation tools rather than N tools per server:

  - ``mcp_list_servers``: list enabled servers (id, description, transport).
  - ``mcp_invoke``: spawn server, perform JSON-RPC handshake, call one tool.

This keeps the model-facing tool surface small while still letting the model
reason about which servers/tools are available. Discovery is cheap because it
re-uses the same JSON-RPC handshake ``mcp_client.list_tools``.

We do NOT pre-warm a long-lived process per server: spawning once per call is
simple, robust, and good enough at MVP scale. Hot-path optimisation is an
explicit follow-up.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.config import settings
from app.agent.tools.mcp_client import MCPServerSpec, call_tool, list_tools

_log = logging.getLogger(__name__)


def _registry_path() -> Path:
  return Path(settings.data_dir) / "mcp" / "servers.json"


def _read_servers() -> list[dict]:
  path = _registry_path()
  if not path.exists():
    return []
  try:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
  except (OSError, ValueError):
    return []
  items = payload.get("servers", []) if isinstance(payload, dict) else []
  return [it for it in items if isinstance(it, dict)]


def _enabled_servers() -> list[dict]:
  return [it for it in _read_servers() if it.get("enabled") and it.get("transport") == "stdio"]


class _MCPInvokeInput(BaseModel):
  server_id: str = Field(description="MCP server id (use mcp_list_servers to discover).")
  tool_name: str = Field(description="Tool name exposed by that MCP server.")
  arguments: str = Field(
    default="{}",
    description="JSON-encoded arguments object for the tool call. Default {}.",
  )


class _MCPDiscoverInput(BaseModel):
  server_id: str = Field(description="MCP server id to inspect. Returns its declared tools.")


def build_mcp_tools() -> list[StructuredTool]:
  """Return ``mcp_invoke`` + ``mcp_list_servers`` + ``mcp_discover_tools`` tools."""
  tools: list[StructuredTool] = []

  def _list() -> str:
    rows = []
    for it in _enabled_servers():
      rows.append({
        "server_id": it.get("id") or it.get("name"),
        "name": it.get("name") or it.get("id"),
        "description": (it.get("description") or "")[:240],
        "command": it.get("command"),
        "args": it.get("args") or [],
      })
    return json.dumps({"enabled_servers": rows, "count": len(rows)}, ensure_ascii=False)

  def _invoke(server_id: str, tool_name: str, arguments: str) -> str:
    # Resolve server.
    match = next((it for it in _read_servers()
                  if (it.get("id") == server_id or it.get("name") == server_id)
                  and it.get("enabled")), None)
    if not match:
      return "[mcp error] server %r not enabled or unknown." % server_id
    if match.get("transport") != "stdio":
      return "[mcp error] transport %r not yet supported by the agent (only stdio is wired)." % match.get("transport")
    try:
      args_obj = json.loads(arguments) if arguments else {}
    except ValueError as e:
      return "[mcp error] arguments is not valid JSON: %s" % e
    if not isinstance(args_obj, dict):
      return "[mcp error] arguments must be a JSON object, got %s" % type(args_obj).__name__
    spec = MCPServerSpec.from_registry_entry(match)
    return call_tool(
      spec,
      tool_name,
      args_obj,
      init_timeout=settings.mcp_init_timeout_sec,
      call_timeout=settings.mcp_call_timeout_sec,
    )

  def _discover(server_id: str) -> str:
    match = next((it for it in _read_servers()
                  if (it.get("id") == server_id or it.get("name") == server_id)
                  and it.get("enabled")), None)
    if not match or match.get("transport") != "stdio":
      return "[mcp error] server %r not enabled or unsupported." % server_id
    spec = MCPServerSpec.from_registry_entry(match)
    declared = list_tools(
      spec,
      init_timeout=settings.mcp_init_timeout_sec,
      call_timeout=settings.mcp_call_timeout_sec,
    )
    return json.dumps({"server_id": server_id, "tools": declared, "count": len(declared)},
                      ensure_ascii=False)

  tools.append(StructuredTool.from_function(
    func=_list,
    name="mcp_list_servers",
    description=(
      "List enabled MCP servers known to this agent. Returns JSON: "
      "[{server_id, name, description, command, args}, ...]. Use this first "
      "to discover which external capabilities you can call."
    ),
  ))
  tools.append(StructuredTool.from_function(
    func=_invoke,
    name="mcp_invoke",
    description=(
      "Spawn a stdio MCP server, perform the JSON-RPC handshake, and call one "
      "named tool. Pass arguments as a JSON string (default {}). Returns the "
      "textual result from the server. Use mcp_list_servers to find server_id; "
      "use mcp_discover_tools to learn a server's declared tools."
    ),
    args_schema=_MCPInvokeInput,
  ))
  tools.append(StructuredTool.from_function(
    func=_discover,
    name="mcp_discover_tools",
    description=(
      "Return the declared tools (name, description, input_schema) of an "
      "enabled MCP server. Use before calling mcp_invoke when you are not "
      "sure what a server exposes."
    ),
    args_schema=_MCPDiscoverInput,
  ))
  return tools


def list_mcp_briefs() -> list[dict[str, Any]]:
  """Return ``[{id, name, description}]`` for the system prompt inventory."""
  out: list[dict[str, Any]] = []
  for it in _enabled_servers():
    out.append({
      "id": it.get("id") or it.get("name"),
      "name": it.get("name") or it.get("id"),
      "description": (it.get("description") or "")[:200],
    })
  return out