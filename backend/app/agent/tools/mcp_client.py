"""Minimal stdio JSON-RPC 2.0 client for MCP servers.

We deliberately avoid pulling in `mcp` / `langchain-mcp-adapters`; the protocol
surface we need is tiny and predictable:

  - initialize / notifications/initialized
  - tools/list
  - tools/call

Each call spawns the server fresh, performs the handshake, executes exactly one
`tools/call`, then closes the process. Stdio MCP servers are idle between calls
so the overhead is acceptable; for hot paths callers should cache the process.

Failure modes: any non-zero return code, timeout, or unexpected JSON is
returned as a string for the LLM rather than raised; tool-call errors must
never crash the streaming loop.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

_log = logging.getLogger(__name__)

_CLIENT_VERSION = "0.1.0"
_PROTOCOL_VERSION = "2024-11-05"


@dataclass
class MCPServerSpec:
  server_id: str
  command: str
  args: list[str]
  env: dict[str, str]
  description: str = ""

  @classmethod
  def from_registry_entry(cls, entry: dict) -> "MCPServerSpec":
    return cls(
      server_id=str(entry.get("id") or entry.get("name") or "mcp"),
      command=str(entry.get("command") or ""),
      args=[str(a) for a in (entry.get("args") or [])],
      env={str(k): str(v) for k, v in (entry.get("env") or {}).items()},
      description=str(entry.get("description") or ""),
    )


def _read_message(stream, timeout: float) -> dict | None:
  """Read one Content-Length framed JSON-RPC message from `stream`."""
  import select
  deadline = time.time() + timeout
  headers: dict[str, str] = {}
  # Read headers.
  while True:
    remaining = deadline - time.time()
    if remaining <= 0:
      return None
    ready, _, _ = select.select([stream], [], [], min(remaining, 5.0))
    if not ready:
      return None
    line = stream.readline()
    if not line:
      return None
    line = line.decode("utf-8", errors="replace").rstrip("\r\n")
    if line == "":
      break  # headers complete
    if ":" in line:
      k, v = line.split(":", 1)
      headers[k.strip().lower()] = v.strip()
  length = int(headers.get("content-length") or 0)
  if length <= 0:
    return None
    # body
    buf = b""
    while len(buf) < length:
      remaining = deadline - time.time()
      if remaining <= 0:
        return None
      ready, _, _ = select.select([stream], [], [], min(remaining, 5.0))
      if not ready:
        return None
      chunk = stream.read(length - len(buf))
      if not chunk:
        return None
      buf += chunk
  try:
    return json.loads(buf.decode("utf-8", errors="replace"))
  except json.JSONDecodeError:
    return None


def _write_message(proc: subprocess.Popen, msg: dict) -> None:
  payload = json.dumps(msg, ensure_ascii=False).encode("utf-8")
  header = ("Content-Length: %d\r\n\r\n" % len(payload)).encode("ascii")
  if proc.stdin is None:
    raise RuntimeError("subprocess stdin unavailable")
  proc.stdin.write(header + payload)
  proc.stdin.flush()


def _spawn(spec: MCPServerSpec, cwd: str | None) -> subprocess.Popen:
  full_env = dict(os.environ)
  full_env.update(spec.env)
  creationflags = 0
  if os.name == "nt":
    # Avoid showing console flashes for stdio MCP servers (npx, uvx, etc.).
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
  return subprocess.Popen(
    [spec.command, *spec.args],
    cwd=cwd,
    env=full_env,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    bufsize=0,
    creationflags=creationflags,
  )


def _handshake(proc: subprocess.Popen, init_timeout: float) -> bool:
  _write_message(proc, {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": _PROTOCOL_VERSION,
      "capabilities": {},
      "clientInfo": {"name": "small-warehouse-agent", "version": _CLIENT_VERSION},
    },
  })
  resp = _read_message(proc.stdout, init_timeout)
  if not resp or "result" not in resp:
    return False
  # notifications/initialized (no response expected).
  _write_message(proc, {
    "jsonrpc": "2.0",
    "method": "notifications/initialized",
    "params": {},
  })
  return True


def list_tools(spec: MCPServerSpec, init_timeout: float, call_timeout: float,
               cwd: str | None = None) -> list[dict]:
  """Return [{name, description, input_schema}, ...] for the given stdio MCP server."""
  try:
    proc = _spawn(spec, cwd)
  except (OSError, ValueError) as e:
    _log.warning("mcp %s: spawn failed: %s", spec.server_id, e)
    return []
  try:
    if not _handshake(proc, init_timeout):
      _log.warning("mcp %s: handshake failed", spec.server_id)
      return []
    _write_message(proc, {
      "jsonrpc": "2.0",
      "id": 2,
      "method": "tools/list",
      "params": {},
    })
    resp = _read_message(proc.stdout, call_timeout)
    if not resp:
      return []
    tools = ((resp.get("result") or {}).get("tools") or [])
    return [t for t in tools if isinstance(t, dict) and isinstance(t.get("name"), str)]
  finally:
    try:
      proc.terminate()
    except Exception:
      pass


def call_tool(spec: MCPServerSpec, tool_name: str, arguments: dict,
              init_timeout: float, call_timeout: float,
              cwd: str | None = None) -> str:
  """Invoke one tool on the stdio MCP server. Returns a string for the LLM."""
  try:
    proc = _spawn(spec, cwd)
  except (OSError, ValueError) as e:
    return "[mcp error] failed to start server %s: %s" % (spec.server_id, e)
  try:
    if not _handshake(proc, init_timeout):
      return "[mcp error] handshake failed for %s" % spec.server_id
    _write_message(proc, {
      "jsonrpc": "2.0",
      "id": 2,
      "method": "tools/call",
      "params": {"name": tool_name, "arguments": arguments or {}},
    })
    resp = _read_message(proc.stdout, call_timeout)
    if not resp:
      return "[mcp error] no response from %s within %.1fs" % (spec.server_id, call_timeout)
    if "error" in resp:
      err = resp["error"]
      return "[mcp error] %s: %s" % (err.get("code"), err.get("message") or err)
    result = resp.get("result") or {}
    content = result.get("content")
    if isinstance(content, list):
      parts: list[str] = []
      for item in content:
        if isinstance(item, dict):
          if item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append(item["text"])
          else:
            parts.append(json.dumps(item, ensure_ascii=False))
        elif isinstance(item, str):
          parts.append(item)
      return "\n".join(parts) or json.dumps(result, ensure_ascii=False)
    if isinstance(content, str):
      return content
    return json.dumps(result, ensure_ascii=False)
  finally:
    try:
      proc.terminate()
    except Exception:
      pass