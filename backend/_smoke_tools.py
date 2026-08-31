"""Smoke test: confirm answer_node_stream runs a tool-call loop with our tools."""
import asyncio
import json
from langchain_core.messages import AIMessage

from app.agent.nodes import answer as A
from app.agent.nodes.answer import answer_node_stream


class FakeTool:
  def __init__(self, name, output):
    self.name = name
    self._out = output
  async def ainvoke(self, _args):
    return self._out


class FakeChat:
  def __init__(self, scripted):
    self._scripted = list(scripted)
    self.last_msgs = None
  def bind_tools(self, tools):
    self._tools = tools
    return self
  async def ainvoke(self, msgs):
    self.last_msgs = msgs
    return self._scripted.pop(0)


async def main():
  tools = [
    FakeTool("mcp_list_servers", json.dumps({"enabled_servers": [{"server_id": "fetch"}], "count": 1}, ensure_ascii=False)),
  ]
  scripted = [
    AIMessage(
      content="",
      tool_calls=[{"id": "call_1", "name": "mcp_list_servers", "args": {}}],
    ),
    AIMessage(content="可用 MCP 服务器：fetch (1 个)."),
  ]
  fake = FakeChat(scripted)

  def _fake_build(_state):
    return fake, [{"role": "user", "content": "list MCP servers"}], [], tools, ""
  A._build_messages = _fake_build

  state = {
    "messages": [{"role": "user", "content": "list MCP servers"}],
    "query": "list MCP servers",
    "retrieved_chunks": [],
    "summary": "",
    "profile": {},
  }

  events = []
  async for ev in answer_node_stream(state):
    events.append(ev)

  types = [e[0] for e in events]
  print("event_types=", types)
  print("tool_calls=", [e[1] for e in events if e[0] == "tool_call"])
  print("tool_results=", [e[1] for e in events if e[0] == "tool_result"])
  done = next(e[1] for e in events if e[0] == "done")
  print("final_answer=", done.get("answer", "")[:120])
  last_msgs = fake.last_msgs or []
  print("msgs_at_end=", [(type(m).__name__, (getattr(m,"content","") or "")[:50]) for m in last_msgs])


if __name__ == "__main__":
  asyncio.run(main())