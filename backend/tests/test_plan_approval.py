"""HITL 计划审批链路测试：planner override 短路 / route_by_intent 强制 research /
_build_initial_state 泄露防护 / plan-preview 只读端点。

不依赖真实 LLM：router / planner 的 LLM 调用用 fake model 替换。
"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 用临时 DB，避免污染 data/notes.db
tmp = tempfile.mkdtemp()
os.environ["HD_DATA_DIR"] = tmp

from app.storage import db as dbm
dbm._engine = None  # reset engine if imported elsewhere
from app.config import settings
settings.sqlite_path = os.path.join(tmp, "test.db")


def _fake_router(intent: str, rewritten: str = ""):
  """返回一个 fake router_node，monkeypatch 用。"""
  def _node(state):
    return {"intent": intent, "rewritten_query": rewritten or state.get("query", ""),
            "step_count": state.get("step_count", 0) + 1}
  return _node


def test_planner_override_shortcircuit():
  """plan_override 存在时 planner 跳过 LLM（use_planner=False 也照样执行）。"""
  from app.agent.nodes import planner as planner_mod
  from app.config import settings as s

  called = {"llm": False}
  class FakeChat:
    def invoke(self, prompt):
      called["llm"] = True
      raise RuntimeError("LLM should not be called with override")
  orig = planner_mod._build_model
  planner_mod._build_model = lambda **kw: FakeChat()
  orig_enabled = s.planner_enabled
  s.planner_enabled = False  # 服务端也关掉，验证 override 优先级最高
  try:
    state = {
      "query": "对比 A 和 B",
      "use_planner": False,
      "step_count": 0,
      "plan_override": {"summary": "分别检索再对比",
                        "steps": ["A 的优缺点", "B 的优缺点", "", "  "]},
    }
    out = planner_mod.planner_node(state)
  finally:
    planner_mod._build_model = orig
    s.planner_enabled = orig_enabled

  assert called["llm"] is False, "override 必须跳过 LLM 调用"
  assert [p["query"] for p in out["plan"]] == ["A 的优缺点", "B 的优缺点"], out
  assert out["plan_summary"] == "分别检索再对比"
  assert out["step_count"] == 1
  print("PASS planner override shortcircuit")


def test_planner_override_caps_steps():
  """override 步数超过 planner_max_steps 时截断。"""
  from app.agent.nodes import planner as planner_mod
  from app.config import settings as s
  orig_max = s.planner_max_steps
  s.planner_max_steps = 2
  try:
    out = planner_mod.planner_node({
      "query": "q", "step_count": 0,
      "plan_override": {"summary": "", "steps": ["a", "b", "c", "d"]},
    })
  finally:
    s.planner_max_steps = orig_max
  assert [p["query"] for p in out["plan"]] == ["a", "b"], out
  print("PASS planner override caps steps")


def test_route_by_intent_override_forces_research():
  """route_by_intent：plan_override 存在时无条件走 research（router 重跑抖动防护）。"""
  from app.agent.nodes.router import route_by_intent
  assert route_by_intent({"intent": "chat", "plan_override": {"steps": ["x"]}}) == "research"
  assert route_by_intent({"intent": "chat"}) == "chat"  # 无 override 保持原行为
  assert route_by_intent({"intent": "ingest"}) == "ingest"
  print("PASS route_by_intent override")


def test_build_initial_state_resets_plan_override():
  """checkpointer 泄露防护：无 override 的轮次必须显式返回 None。"""
  from app.api.chat import ChatRequest, Message, PlanOverride, _build_initial_state

  def _body(override):
    return ChatRequest(messages=[Message(role="user", content="对比 A 和 B")],
                       plan_override=override)

  st1 = _build_initial_state(_body(PlanOverride(summary="s", steps=["a", " b", ""])),
                             "对比 A 和 B", "sess-1", None, None, None, None, None)
  assert st1["plan_override"] == {"summary": "s", "steps": ["a", "b"]}, st1["plan_override"]

  # 第二轮不带 override：必须是 None，而不是从上轮泄露
  st2 = _build_initial_state(_body(None), "下一个问题", "sess-1", None, None, None, None, None)
  assert st2["plan_override"] is None, st2["plan_override"]
  print("PASS _build_initial_state reset")


def test_preview_chat_intent_no_plan():
  """chat 意图 → needs_plan=False（不跑 planner）。"""
  from app.api import chat as chat_mod
  from app.api.chat import ChatRequest, Message
  import app.agent.nodes.router as router_mod
  import app.agent.nodes.planner as planner_mod

  assert hasattr(chat_mod, "plan_preview"), "plan_preview endpoint missing"
  orig_node = router_mod.router_node
  router_mod.router_node = _fake_router("chat", "你好呀")
  planner_called = {"n": 0}
  orig_planner = planner_mod.planner_node
  def _spy_planner(state):
    planner_called["n"] += 1
    return orig_planner(state)
  planner_mod.planner_node = _spy_planner
  try:
    res = chat_mod.plan_preview(
      ChatRequest(messages=[Message(role="user", content="你好")]), None)
  finally:
    router_mod.router_node = orig_node
    planner_mod.planner_node = orig_planner
  assert res["needs_plan"] is False
  assert res["intent"] == "chat"
  assert planner_called["n"] == 0, "chat 意图不应触发 planner"
  print("PASS preview chat intent")


def test_preview_research_returns_steps():
  """research 意图 → 返回 planner 步骤。"""
  from app.api import chat as chat_mod
  from app.api.chat import ChatRequest, Message
  import app.agent.nodes.router as router_mod
  import app.agent.nodes.planner as planner_mod

  orig_node, orig_planner = router_mod.router_node, planner_mod.planner_node
  router_mod.router_node = _fake_router("research", "对比 A 和 B 的要点")
  planner_mod.planner_node = lambda state: {
    "plan": [{"query": "A 的要点"}, {"query": "B 的要点"}],
    "plan_summary": "分别检索再对比", "step_count": 1}
  try:
    res = chat_mod.plan_preview(
      ChatRequest(messages=[Message(role="user", content="对比 A 和 B")]), None)
  finally:
    router_mod.router_node = orig_node
    planner_mod.planner_node = orig_planner
  assert res["needs_plan"] is True
  assert res["intent"] == "research"
  assert res["steps"] == ["A 的要点", "B 的要点"], res
  assert res["plan_summary"] == "分别检索再对比"
  print("PASS preview research steps")


def test_preview_no_persistence():
  """preview 端点只读：不建 session、不写消息。"""
  from app.api import chat as chat_mod
  from app.api.chat import ChatRequest, Message
  from app.storage.db import create_session, get_messages
  import app.agent.nodes.router as router_mod
  import app.agent.nodes.planner as planner_mod

  sess = create_session(title="preview-test")
  before = len(get_messages(sess.id))
  orig_node, orig_planner = router_mod.router_node, planner_mod.planner_node
  router_mod.router_node = _fake_router("research", "q")
  planner_mod.planner_node = lambda state: {"plan": [{"query": "q1"}],
                                            "plan_summary": "", "step_count": 1}
  try:
    res = chat_mod.plan_preview(
      ChatRequest(messages=[Message(role="user", content="研究一下 X")],
                  session_id=sess.id), None)
  finally:
    router_mod.router_node = orig_node
    planner_mod.planner_node = orig_planner
  assert res["needs_plan"] is True
  after = len(get_messages(sess.id))
  assert after == before, "preview 不得写入消息"
  print("PASS preview no persistence")


def test_preview_empty_query_400():
  """空 query 返回 400。"""
  from app.api import chat as chat_mod
  from app.api.chat import ChatRequest, Message
  from fastapi import HTTPException
  try:
    chat_mod.plan_preview(ChatRequest(messages=[Message(role="user", content="   ")]), None)
    raise AssertionError("expected 400")
  except HTTPException as e:
    assert e.status_code == 400
  print("PASS preview empty query 400")


if __name__ == "__main__":
  test_planner_override_shortcircuit()
  test_planner_override_caps_steps()
  test_route_by_intent_override_forces_research()
  test_build_initial_state_resets_plan_override()
  test_preview_chat_intent_no_plan()
  test_preview_research_returns_steps()
  test_preview_no_persistence()
  test_preview_empty_query_400()
  print("\nALL PLAN APPROVAL TESTS PASSED")
