# -*- coding: utf-8 -*-
"""_ToolStreamAgg 单元测试：工具路径的流式聚合器。

覆盖：纯文本流式、tool_call 分片聚合、并行工具调用、对象式分片、
坏 JSON 参数兜底、文本+工具混合时文本不泄漏。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.nodes.answer import _ToolStreamAgg


class _Chunk:
  def __init__(self, content="", tool_call_chunks=None, tool_calls=None):
    self.content = content
    self.tool_call_chunks = tool_call_chunks or []
    self.tool_calls = tool_calls or []


class _TCC:
  """对象式 ToolCallChunk（老版 langchain 行为）。"""

  def __init__(self, name=None, args=None, id=None, index=None):
    self.name, self.args, self.id, self.index = name, args, id, index


def test_text_only_streaming():
  agg = _ToolStreamAgg()
  out = [agg.add(_Chunk(content="你")), agg.add(_Chunk(content="好"))]
  tcs = agg.finish()
  assert agg.text == "你好"
  assert tcs == []
  assert out == ["你", "好"]


def test_tool_call_chunk_aggregation():
  agg = _ToolStreamAgg()
  agg.add(_Chunk(tool_call_chunks=[{
      "name": "mcp_invoke", "args": '{"ser', "id": "call_1", "index": 0}]))
  agg.add(_Chunk(tool_call_chunks=[{"args": 'ver": "fs"}'}]))
  agg.add(_Chunk(content="tool 之后出现的文本不转发"))
  tcs = agg.finish()
  assert len(tcs) == 1
  assert tcs[0]["name"] == "mcp_invoke"
  assert tcs[0]["args"] == {"server": "fs"}
  assert tcs[0]["id"] == "call_1"
  assert agg.text == ""


def test_parallel_tool_calls_by_index():
  agg = _ToolStreamAgg()
  agg.add(_Chunk(tool_call_chunks=[
      {"name": "tool_a", "args": "{}", "id": "a", "index": 0}]))
  agg.add(_Chunk(tool_call_chunks=[
      {"name": "tool_b", "args": '{"x": 1', "id": "b", "index": 1}]))
  agg.add(_Chunk(tool_call_chunks=[{"args": "}"}]))
  tcs = agg.finish()
  assert [t["name"] for t in tcs] == ["tool_a", "tool_b"]
  assert tcs[1]["args"] == {"x": 1}


def test_object_style_chunks():
  agg = _ToolStreamAgg()
  agg.add(_Chunk(tool_call_chunks=[
      _TCC(name="t", args="{}", id="i", index=0)]))
  tcs = agg.finish()
  assert tcs == [{"name": "t", "args": {}, "id": "i"}]


def test_pre_parsed_tool_calls():
  agg = _ToolStreamAgg()
  agg.add(_Chunk(tool_calls=[
      {"name": "t", "args": {"k": 1}, "id": "p"}]))
  agg.add(_Chunk(content="不应转发"))
  tcs = agg.finish()
  assert tcs == [{"name": "t", "args": {"k": 1}, "id": "p"}]
  assert agg.text == ""


def test_bad_json_args_fallback():
  agg = _ToolStreamAgg()
  agg.add(_Chunk(tool_call_chunks=[
      {"name": "t", "args": "not-json", "id": "x", "index": 0}]))
  tcs = agg.finish()
  assert tcs[0]["args"] == {}


def test_finish_is_idempotent():
  agg = _ToolStreamAgg()
  agg.add(_Chunk(tool_call_chunks=[
      {"name": "t", "args": "{}", "id": "x", "index": 0}]))
  first = agg.finish()
  second = agg.finish()
  assert first == second and len(first) == 1


if __name__ == "__main__":
  for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
    fn()
    print("PASS", fn.__name__)
  print("ALL PASSED")
