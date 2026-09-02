# -*- coding: utf-8 -*-
"""Planner node: decompose a research question into sub-queries (plan-and-execute).

设计（任务规划 / plan-and-execute）:
  - 在 router 之后、research 之前运行，把复杂问题分解为最多 planner_max_steps
    个子查询步骤，research 节点按计划逐步执行。
  - 使用 router 级廉价模型 + 原生 JSON 解析（沿用 router 的教训：不依赖
    structured output，避免 thinking 包裹导致的解析失败）。
  - 任何失败都返回空计划，research 自动回退到原有的启发式 follow-up 循环，
    规划永不阻塞主流程。
"""
from __future__ import annotations

import logging
import re

from app.agent.state import AgentState
from app.config import settings
from app.llm.factory import _build_model

_log = logging.getLogger(__name__)

PLANNER_PROMPT = """You are a research task planner. Read the question and output exactly one JSON object with NO other text:

{"plan_summary": "<one short sentence describing the overall approach>", "steps": [{"query": "<sub-question search query>"}, ...]}

Planning rules:
- Decompose the question into 1-4 concrete sub-questions that together cover the full scope.
- Each step's "query" is a standalone search query for a knowledge base, in the SAME language as the question.
- Sub-queries must be mutually complementary (different angles), NOT paraphrases of each other.
- The FIRST step should be the most direct formulation of the original question.
- If the question is simple and one search suffices, output exactly one step.
- Do NOT answer the question, only plan the searches.

Example:
Input: "对比一下我笔记里 A 方案和 B 方案的优缺点"
Output: {"plan_summary": "分别检索两个方案再对比", "steps": [{"query": "A 方案的优点和缺点"}, {"query": "B 方案的优点和缺点"}, {"query": "A 方案与 B 方案的对比结论"}]}
"""

_JSON_RE = re.compile(r"\{[\s\S]*\}")
_THINK_RE = re.compile(r"<think(?:ing)?>[\s\S]*?</think(?:ing)?>", re.IGNORECASE)


def _strip_think(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


def _parse_plan(text: str) -> dict:
    """Parse planner JSON; raises ValueError on any structural problem."""
    text = _strip_think(text)
    match = _JSON_RE.search(text)
    if not match:
        raise ValueError("no JSON object in planner response")
    import json
    obj = json.loads(match.group(0))
    if not isinstance(obj, dict):
        raise ValueError("planner JSON is not an object")
    steps_raw = obj.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError("planner JSON has no steps")
    queries = []
    for s in steps_raw:
        q = (s.get("query") if isinstance(s, dict) else s) or ""
        q = str(q).strip()
        if q and q not in queries:
            queries.append(q)
        if len(queries) >= max(1, int(settings.planner_max_steps)):
            break
    if not queries:
        raise ValueError("planner steps contain no usable query")
    summary = str(obj.get("plan_summary") or "").strip()
    return {"plan_summary": summary, "queries": queries}


def planner_node(state: AgentState) -> dict:
    """Decompose the rewritten query into a search plan. NEVER raises.

    Returns {"plan": [...], "plan_summary": str}. Empty plan on any failure
    lets research fall back to its heuristic follow-up loop.
    """
    query = (state.get("rewritten_query") or state.get("query") or "").strip()
    base_result = {
        "plan": [],
        "plan_summary": "",
        "step_count": state.get("step_count", 0) + 1,
    }
    # 请求级覆盖（前端 Plan 开关）优先于服务端 HD_PLANNER_ENABLED
    override = state.get("use_planner")
    enabled = settings.planner_enabled if override is None else bool(override)
    if not enabled or not query:
        return base_result

    try:
        chat = _build_model(
            provider=None,
            model=settings.router_model or state.get("model_override"),
            api_key=state.get("api_key_override"),
            base_url=settings.router_base_url or state.get("base_url_override") or None,
            reasoning_level=None,
        )
    except Exception as e:
        _log.warning("planner: model init failed: %s", e)
        return base_result

    payload = PLANNER_PROMPT + "\nQuestion: " + query + "\nOutput JSON:"
    try:
        resp = chat.invoke(payload)
        content = getattr(resp, "content", "")
        if isinstance(content, list):
            content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
        plan = _parse_plan(str(content or ""))
    except Exception as e:
        _log.warning("planner: JSON plan parsing failed, research will fall back: %s", e)
        return base_result

    _log.info("planner: %d step(s): %s", len(plan["queries"]), plan["queries"])
    return {
        "plan": [{"query": q} for q in plan["queries"]],
        "plan_summary": plan["plan_summary"],
        "step_count": state.get("step_count", 0) + 1,
    }
