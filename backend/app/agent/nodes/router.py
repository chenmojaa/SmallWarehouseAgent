# -*- coding: utf-8 -*-
"""Router node: cheap, fast LLM call that classifies intent + rewrites query.

Design (per OPTIMIZATION.md section 2.5):
  - Use the cheapest available model (configured via HD_ROUTER_MODEL/HD_ROUTER_BASE_URL,
    or fall back to the main chat model).
  - Output a strict Pydantic object (RouterDecision) via LangChain structured output.
  - On ANY parse failure or LLM error -> default to intent="chat" with original query.
    Routing must NEVER block the main flow.
  - Rewritten query combines the latest user message with up to 3 prior turns of
    conversation so that pronoun follow-ups resolve correctly.
"""
from __future__ import annotations

import logging
import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.state import AgentState
from app.config import settings
from app.llm.factory import _build_model

_log = logging.getLogger(__name__)

Intent = Literal["chat", "research", "ingest", "report"]

# Fast-path patterns: skip the router LLM call for obvious greetings / small talk
# so the user gets an instant response instead of waiting 12+ seconds.
_FAST_CHAT_PATTERNS = re.compile(
    r"^(你好|hi|hello|嗨|喂|在吗|在么|早啊|早|早上好|下午好|晚上好|晚安"
    r"|谢谢|多谢|感谢|thanks|thank you|thx"
    r"|搜一下|搜索|查找|查一下|查查|查询|找一下|看看|搜搜"
    r"|再见|拜拜|bye|goodbye|回头见|回见"
    r"|你是谁|你是谁？|你叫什么|介绍一下自己|你能做什么|你有什么功能|what can you do|who are you"
    r"|你是谁\?|你是谁？"
    r")[!！。.…~～\s]*$",
    re.IGNORECASE
)


def _is_fast_chat(query: str) -> bool:
    """Return True if the query is a simple greeting / small talk that can skip the router."""
    return bool(_FAST_CHAT_PATTERNS.match(query.strip())) if query else False

ROUTER_PROMPT = """你是 HD 知识库的任务路由器。请阅读对话历史和最新消息,只输出一个 JSON 对象,不要任何其他文字:

{"intent": "<chat|research|ingest|report>", "rewritten_query": "<string>"}

Intent 分类规则:
- chat: 闲聊、简单事实问答、不需要综合多个来源
- research: 需要跨文档综合、对比多个方案、深入挖掘某个主题
- ingest: 消息包含 URL / 文件描述 / "保存这个" / "记住这个" / "加到我的知识库"
- report: 请求日报/周报/总结/某时间段汇总

rewritten_query 规则:
- 把最新消息与最近 3 轮对话合并,把代词("它"/"这个"/"上面那个")展开成完整独立的句子
- 只输出重写后的问题本身,不要回答它
- 语言保持与用户最新消息相同

示例:
历史: [user] 牛魔王的来历? [assistant] 牛魔王是...
输入: "他儿子呢?"
输出: {"intent": "research", "rewritten_query": "牛魔王的儿子(红孩儿)的背景是什么?"}
"""


class RouterDecision(BaseModel):
    intent: Intent = Field("chat", description="routing decision")
    rewritten_query: str = Field("", description="history-resolved complete question")


def _recent_history(messages, limit: int = 3) -> list[dict]:
    """Pull the last `limit` user/assistant turns as plain dicts."""
    out: list[dict] = []
    for m in reversed(messages or []):
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
            if len(out) >= limit * 2:
                break
    out.reverse()
    return out


def _response_text(response) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    return str(content or "")


def _parse_router_json(text: str) -> RouterDecision:
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("no JSON object in router response")
    return RouterDecision.model_validate_json(match.group(0))


def router_node(state: AgentState) -> dict:
    """Classify intent + rewrite query. NEVER raises; always returns a usable state."""
    query = (state.get("query") or "").strip()
    messages = state.get("messages") or []

    # Fast path: simple greetings / small talk skip the router LLM entirely.
    if _is_fast_chat(query):
        _log.info("router: fast-path chat (greeting detected)")
        return {
            "intent": "chat",
            "rewritten_query": query,
            "skip_retrieval": True,
            "step_count": state.get("step_count", 0) + 1,
        }

    # Router disabled -> chat with verbatim query.
    if not settings.router_enabled:
        return {
            "intent": "chat",
            "rewritten_query": query,
            "step_count": state.get("step_count", 0) + 1,
        }

    # Build cheap router model. Falls back to main chat model if env not set.
    try:
        chat = _build_model(
            provider=None,
            model=settings.router_model or state.get("model_override"),
            api_key=state.get("api_key_override"),
            base_url=settings.router_base_url or state.get("base_url_override") or None,
            reasoning_level=None,
        )
    except Exception as e:
        _log.warning("router: model init failed, falling back to chat: %s", e)
        return {"intent": "chat", "rewritten_query": query,
                "step_count": state.get("step_count", 0) + 1}

    history = _recent_history(messages, limit=3)
    history_str = "\n".join("[%s] %s" % (h["role"], h["content"][:200]) for h in history) or "(no prior turns)"
    user_payload = "%s\n\nHistory:\n%s\n\nInput: %s\n\nOutput JSON:" % (ROUTER_PROMPT, history_str, query)

    try:
        response = chat.invoke(user_payload)
        decision = _parse_router_json(_response_text(response))
    except Exception as e:
        _log.warning("router: JSON routing failed, falling back to chat: %s", e)
        return {"intent": "chat", "rewritten_query": query,
                "step_count": state.get("step_count", 0) + 1}

    rewritten = (decision.rewritten_query or "").strip() or query
    return {
        "intent": decision.intent,
        "rewritten_query": rewritten,
        "step_count": state.get("step_count", 0) + 1,
    }


def route_by_intent(state: AgentState) -> str:
    """Conditional edge dispatcher. Used by LangGraph after the router."""
    # HITL 计划审批：阶段 1 已判定 research 且用户已批准计划，
    # 阶段 2 无条件走 research（router 重跑抖动 / Plan 开关状态不影响执行）。
    if state.get("plan_override"):
        return "research"
    intent = (state.get("intent") or "chat").lower()
    # Plan Mode (Codex CLI / Claude Code parity): if the user toggled it on,
    # escalate chat-classified queries so the planner still gets a chance to
    # decompose a multi-step question.
    if state.get("use_planner") and intent == "chat":
        intent = "research"
    if state.get("skip_retrieval"):
        return "chat_no_rag"
    if intent in ("research", "ingest", "report"):
        return intent
    # Heuristic: if planner produced >=2 sub-queries for a chat-classified
    # question (e.g. "compare A vs B and tabulate it"), escalate to research
    # so the plan actually runs without forcing the LLM to label it research.
    plan = state.get("plan") or []
    if len(plan) >= 2:
        return "research"
    return "chat"
