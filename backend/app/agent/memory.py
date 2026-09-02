"""Long-term memory helpers (§6.3 summary, §6.5 profile, §6.6 fact extraction).

Three concerns live here:

  1. ``summarize_overflow`` - when the conversation history exceeds the sliding
     window, compress the cut-off older turns into a short summary string that
     is injected into the system prompt. Uses the cheap router model so it does
     not add meaningful latency/cost.
  2. Profile accessors - thin re-exports of the db layer so agent code does not
     import storage directly.
  3. ``extract_facts`` - 自动事实抽取：对话轮结束后用廉价模型从用户消息中
     抽取持久事实（偏好/背景/约束），写入 memory_facts 表供跨会话召回。
     抽取时把已有事实列进 prompt 让模型避免重复。

All are best-effort: any failure returns an empty result and never blocks the
main chat flow.
"""
from __future__ import annotations

import json
import logging
import re

from app.agent.context import trim_history, HISTORY_TOKEN_BUDGET
from app.storage.db import get_profile, save_profile  # re-exported

_log = logging.getLogger(__name__)

__all__ = ["summarize_overflow", "get_profile", "save_profile", "extract_facts"]

EXTRACT_PROMPT = """你是记忆抽取器。从下面的对话中提取关于用户的持久事实，用于跨会话长期记忆。

只提取对话中明确体现的用户信息，例如：
- 偏好（回答风格、语言、工具习惯）
- 背景（职业、技术栈、在做的项目）
- 约束（过敏、时间安排、明确说过"不要/总是"的事）
- 目标（正在学什么、准备做什么）

规则：
- 不要提取一次性问题本身（如"什么是RAG"不含用户信息）
- 不要推测，只记录对话中有依据的内容
- 每条事实一句完整的话，用与对话相同的语言
- 已有事实列表中的内容不要重复输出
- 没有新事实就输出 []

已有事实：
<<EXISTING>>

对话：
<<CONVERSATION>>

输出 JSON 数组（无其他文本），如 ["事实1", "事实2"]："""

_JSON_ARR_RE = re.compile(r"\[[\s\S]*\]")
_THINK_RE = re.compile(r"<think(?:ing)?>[\s\S]*?</think(?:ing)?>", re.IGNORECASE)


def extract_facts(history: list[dict], session_id: str | None = None) -> list[str]:
  """从对话历史抽取用户事实，写入 DB 并返回新增列表。NEVER raises。

  只看最近几轮（信息密度最高），跳过太短的寒暄轮。
  """
  try:
    from app.config import settings
    if not settings.memory_extraction_enabled:
      return []
    # 只抽最近 6 条 user/assistant 消息：新事实几乎总在近期对话里
    recent = [m for m in (history or []) if m.get("role") in ("user", "assistant")][-6:]
    if not recent:
      return []
    transcript = "\n".join(
      "%s: %s" % (m.get("role"), (m.get("content") or "")[:500]) for m in recent
    )
    if len(transcript.strip()) < 30:   # 寒暄/空轮，不值得一次 LLM 调用
      return []

    from app.storage.db import list_facts, save_facts
    existing = [f["content"] for f in list_facts(limit=50)]
    existing_str = "\n".join("- " + e for e in existing) or "(none)"

    from app.llm.factory import _build_model, invoke_with_retry
    chat = _build_model(
      provider=None,
      model=settings.router_model or None,
      base_url=settings.router_base_url or None,
    )
    prompt = (EXTRACT_PROMPT
              .replace("<<EXISTING>>", existing_str)
              .replace("<<CONVERSATION>>", transcript))
    resp = invoke_with_retry(chat, prompt)
    content = getattr(resp, "content", "") or ""
    if isinstance(content, list):
      content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    text = _THINK_RE.sub("", str(content)).strip()

    match = _JSON_ARR_RE.search(text)
    if not match:
      return []
    facts = json.loads(match.group(0))
    if not isinstance(facts, list):
      return []
    facts = [str(f).strip() for f in facts if isinstance(f, str) and str(f).strip()][:8]

    added = save_facts(facts, session_id=session_id)
    if added:
      _log.info("memory: extracted %d new fact(s): %s", added,
                [f[:40] for f in facts])
    return facts
  except Exception as e:
    _log.warning("memory: fact extraction failed (ignored): %s", e)
    return []


def summarize_overflow(history: list[dict],
                       max_messages: int = 12,
                       token_budget: int = HISTORY_TOKEN_BUDGET) -> str:
  """Return a short summary of the history that falls outside the window.

  Returns "" when nothing overflows or when summarization fails. The summary is
  capped at ~150 CJK chars per the plan (§6.3).
  """
  _recent, overflow = trim_history(history, max_messages=max_messages,
                                   token_budget=token_budget)
  if not overflow:
    return ""

  transcript = "\n".join(
    "%s: %s" % (m.get("role", "?"), (m.get("content") or "")[:200])
    for m in overflow[-12:]
  )

  try:
    from app.config import settings
    from app.llm.factory import _build_model, invoke_with_retry
    chat = _build_model(
      provider=None,
      model=settings.router_model or None,
      base_url=settings.router_base_url or None,
    )
    prompt = (
      "把以下对话压缩成一段不超过 150 字的中文摘要，保留关键结论与用户偏好，"
      "不要输出其他内容：\n" + transcript
    )
    resp = invoke_with_retry(chat, prompt)
    text = getattr(resp, "content", "") or ""
    if isinstance(text, list):
      text = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in text)
    return (text or "").strip()[:400]
  except Exception as e:
    _log.warning("memory: summarize failed: %s", e)
    return ""
