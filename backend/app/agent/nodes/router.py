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
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.state import AgentState
from app.config import settings
from app.llm.factory import _build_model

_log = logging.getLogger(__name__)

Intent = Literal["chat", "research", "ingest", "report"]

ROUTER_PROMPT = """You are HD knowledge base task router. Read the conversation history and the latest message, and output exactly one JSON object with NO other text:

{"intent": "<chat|research|ingest|report>", "rewritten_query": "<string>"}

Intent rules:
- chat: small talk, simple factual questions, no synthesis required
- research: needs cross-document synthesis, comparing multiple options, deep-diving a subject
- ingest: message contains URL / file description / "save this" / "remember this" / "add to my KB"
- report: requests daily/weekly/summary reports, period rollups

rewritten_query rules:
- combine the latest user message with up to 3 prior turns, expanding pronouns
  ("it" / "this" / "that one above") into a complete standalone sentence
- output ONLY the rewritten question itself, do NOT answer it

Example:
History: [user] What is the origin of the Bull Demon King? [assistant] The Bull Demon King is...
Input: "What about his son?"
Output: {"intent": "research", "rewritten_query": "What is the background of the Bull Demon King's son (Red Boy)?"}
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


def router_node(state: AgentState) -> dict:
    """Classify intent + rewrite query. NEVER raises; always returns a usable state."""
    query = (state.get("query") or "").strip()
    messages = state.get("messages") or []

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
        structured = chat.with_structured_output(RouterDecision)
        decision: RouterDecision = structured.invoke(user_payload)
    except Exception as e:
        _log.warning("router: structured output failed, falling back to chat: %s", e)
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
    intent = (state.get("intent") or "chat").lower()
    if intent in ("research", "ingest", "report"):
        return intent
    return "chat"