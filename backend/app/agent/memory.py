"""Long-term memory helpers (§6.3 summary, §6.5 profile).

Two concerns live here:

  1. ``summarize_overflow`` - when the conversation history exceeds the sliding
     window, compress the cut-off older turns into a short summary string that
     is injected into the system prompt. Uses the cheap router model so it does
     not add meaningful latency/cost.
  2. Profile accessors - thin re-exports of the db layer so agent code does not
     import storage directly.

Both are best-effort: any failure returns an empty result and never blocks the
main chat flow.
"""
from __future__ import annotations

import logging

from app.agent.context import trim_history, HISTORY_TOKEN_BUDGET
from app.storage.db import get_profile, save_profile  # re-exported

_log = logging.getLogger(__name__)

__all__ = ["summarize_overflow", "get_profile", "save_profile"]


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
    from app.llm.factory import _build_model
    chat = _build_model(
      provider=None,
      model=settings.router_model or None,
      base_url=settings.router_base_url or None,
    )
    prompt = (
      "把以下对话压缩成一段不超过 150 字的中文摘要，保留关键结论与用户偏好，"
      "不要输出其他内容：\n" + transcript
    )
    resp = chat.invoke(prompt)
    text = getattr(resp, "content", "") or ""
    if isinstance(text, list):
      text = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in text)
    return (text or "").strip()[:400]
  except Exception as e:
    _log.warning("memory: summarize failed: %s", e)
    return ""
