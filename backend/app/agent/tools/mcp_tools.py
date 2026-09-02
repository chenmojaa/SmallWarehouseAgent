"""LangChain tool wrappers around locally registered MCP servers.

We expose three aggregation tools rather than N tools per server:

  - ``mcp_list_servers``: list enabled servers (id, description, transport).
  - ``mcp_discover_tools``: list a server's declared tools.
  - ``mcp_invoke``: call one tool on a server.

Session reuse: agent turns often invoke the same server 5+ times. Spawning
npx + JSON-RPC handshake costs 2-3s per call, so we keep one live
``MCPSession`` per server for the duration of a turn (see ``_sessions`` /
``reset_mcp_sessions``). Sessions are reset by answer.py at the start of
each request, so no process outlives its turn by more than the request
lifetime. A dead process is transparently respawned by MCPSession itself.
"""
from __future__ import annotations

import json
import logging
import os
import re
import string
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.config import settings
from app.agent.tools.mcp_client import MCPServerSpec, MCPSession

_log = logging.getLogger(__name__)

# 项目根目录（默认权限模式下 filesystem 唯一免询问的授权范围）
_PROJECT_ROOT = str(Path(__file__).resolve().parents[4])

# 当前请求的权限模式与用户已批准的额外目录。
# 单用户本地应用，模块级状态足够；answer.py 在每次请求开始时重置。
_perm: dict = {"mode": "default", "extra_dirs": []}

# 疑似本地路径的值（Windows 盘符 / POSIX 绝对路径 / UNC）
_PATH_RE = re.compile(r"^([A-Za-z]:[\\/]|[\\/]{2}|/)")


def set_permission_mode(mode: str) -> None:
  """Reset per-request permission context ('default' | 'full').

  Also closes any pooled MCP sessions: the spawned filesystem server was
  configured with the previous permission's allowed-dirs, so it must not be
  reused across permission modes.
  """
  _perm["mode"] = "full" if mode == "full" else "default"
  _perm["extra_dirs"] = []
  reset_mcp_sessions()


# ---- Session pool (per-request, per-server) ----
# key: server_id, value: MCPSession. Reused across mcp_invoke/mcp_discover_tools
# calls within one agent turn; closed on permission change and turn start.
_sessions: dict[str, MCPSession] = {}


_current_session_id: str | None = None


def set_session_id(sid: str | None) -> None:
  """Tag subsequent log_mcp_call rows with this session id (called per request)."""
  global _current_session_id
  _current_session_id = sid


def _log_mcp_call(*, server_id, tool_name, arguments, status, latency_ms, result_preview=None, error=None):
  try:
    from app.storage.db import log_mcp_call
    log_mcp_call(_current_session_id, server_id, tool_name, arguments, status, latency_ms, result_preview, error)
  except Exception:
    pass


def reset_mcp_sessions() -> None:
  """Close all pooled sessions (called at the start of each request)."""
  for sess in _sessions.values():
    try:
      sess.close()
    except Exception:  # pragma: no cover - best-effort cleanup
      pass
  _sessions.clear()


def _session_for(match: dict) -> MCPSession:
  """Return (creating if needed) the pooled session for one server."""
  sid = str(match.get("id") or match.get("name"))
  sess = _sessions.get(sid)
  # Spec embeds the CURRENT allowed-dirs; if the session's args differ
  # (e.g. user just approved an extra drive), rebuild it.
  spec = _spec_for(match)
  if sess is not None and sess.spec.args == spec.args:
    return sess
  if sess is not None:
    sess.close()
  sess = MCPSession(
    spec,
    cwd=_PROJECT_ROOT,
    init_timeout=settings.mcp_init_timeout_sec,
    call_timeout=settings.mcp_call_timeout_sec,
  )
  _sessions[sid] = sess
  return sess


def add_approved_dirs_from(args: dict) -> list[str]:
  """After user approval, register the drive roots of any paths in tool args.

  E.g. approving list_directory("D:\\photos\\2024") grants D:\\ for the rest
  of this turn, so follow-up reads inside the same drive are not re-blocked
  by the filesystem server's allowed-dirs check.
  """
  added: list[str] = []
  for v in (args or {}).values():
    if not isinstance(v, str) or not _PATH_RE.match(v):
      continue
    m = re.match(r"^([A-Za-z]):", v)
    root = (m.group(1) + ":\\") if m else "/"
    if root not in _perm["extra_dirs"] and os.path.exists(root):
      _perm["extra_dirs"].append(root)
      added.append(root)
  return added


def _all_drive_roots() -> list[str]:
  """完全访问模式：本机所有可用盘符根目录。"""
  if os.name == "nt":
    return [f"{c}:\\" for c in string.ascii_uppercase if os.path.exists(f"{c}:\\")]
  return ["/"]


def _is_filesystem_server(match: dict) -> bool:
  cmd = " ".join([str(match.get("command") or "")] + [str(a) for a in (match.get("args") or [])])
  return "server-filesystem" in cmd


def _spec_for(match: dict) -> MCPServerSpec:
  """Build the spawn spec, applying the permission mode to filesystem servers.

  filesystem server takes allowed directories as trailing positional args:
  npx -y @modelcontextprotocol/server-filesystem <dir> [<dir>...]
  """
  spec = MCPServerSpec.from_registry_entry(match)
  if not _is_filesystem_server(match):
    return spec
  pkg_idx = next((i for i, a in enumerate(spec.args) if "server-filesystem" in str(a)), -1)
  if pkg_idx < 0:
    return spec
  if _perm["mode"] == "full":
    allowed = _all_drive_roots()
  else:
    allowed = [_PROJECT_ROOT] + list(_perm["extra_dirs"])
  spec.args = spec.args[:pkg_idx + 1] + allowed
  return spec


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
      _log_mcp_call(server_id=server_id, tool_name=tool_name, arguments=arguments, status="error", latency_ms=0, error="bad json: %s" % e)
      return "[mcp error] arguments is not valid JSON: %s" % e
    if not isinstance(args_obj, dict):
      _log_mcp_call(server_id=server_id, tool_name=tool_name, arguments=arguments, status="error", latency_ms=0, error="args not dict")
      return "[mcp error] arguments must be a JSON object, got %s" % type(args_obj).__name__
    import time as _time
    _t0 = _time.time()
    sess = _session_for(match)
    out = sess.call(tool_name, args_obj)
    _latency_ms = int((_time.time() - _t0) * 1000)
    if isinstance(out, str) and out.startswith("[mcp error]"):
      _log_mcp_call(server_id=server_id, tool_name=tool_name, arguments=args_obj, status="error", latency_ms=_latency_ms, error=out[:200])
    elif isinstance(out, str) and "timeout" in out.lower():
      _log_mcp_call(server_id=server_id, tool_name=tool_name, arguments=args_obj, status="timeout", latency_ms=_latency_ms, error=out[:200])
    else:
      _log_mcp_call(server_id=server_id, tool_name=tool_name, arguments=args_obj, status="ok", latency_ms=_latency_ms, result_preview=out)
    return out

  def _discover(server_id: str) -> str:
    match = next((it for it in _read_servers()
                  if (it.get("id") == server_id or it.get("name") == server_id)
                  and it.get("enabled")), None)
    if not match or match.get("transport") != "stdio":
      return "[mcp error] server %r not enabled or unsupported." % server_id
    declared = _session_for(match).list_tools()
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
      "Call one named tool on an MCP server (the server process stays warm "
      "across calls within this turn, so repeated calls are fast). Pass "
      "arguments as a JSON string (default {}). Returns the textual result "
      "from the server. Use mcp_list_servers to find server_id; use "
      "mcp_discover_tools to learn a server's declared tools. "
      "TIP: prefer batch tools when a server offers them (e.g. "
      "read_multiple_files instead of many read_text_file calls) to reduce "
      "round trips."
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