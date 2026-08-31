"""Context assembly: token budgeting + unified message building (§7, §8).

This module is the single place where "what goes into the LLM prompt" is
decided. It owns:

  1. ``format_context``  - render retrieved chunks as a numbered reference block
     with a token budget (drop lowest-score chunks when over budget).
  2. ``trim_history``    - sliding-window history trim; overflow goes to a
     summary string instead of being silently dropped.
  3. ``build_messages``  - assemble the final LangChain message list:
     system (persona + profile + summary + references) -> history -> question.

Token counting is a cheap heuristic (CJK chars ~1.5 tokens each, ASCII words
~1.3 tokens each) rather than a tiktoken dependency; it is only used to decide
when to truncate, never for billing.
"""
from __future__ import annotations

import json
import logging
from typing import Iterable

_log = logging.getLogger(__name__)

_EMPTY_CONTEXT = "(no reference material available)"
_SEPARATOR = "\n\n---\n\n"

# ---- Token budgets (§8) ----
# Rough CJK-aware estimate: 1 CJK char ~ 1.5 tokens, 1 ASCII word ~ 1.3 tokens.
CONTEXT_TOKEN_BUDGET = 3000   # total budget for the reference block
MAX_CHUNK_CHARS = 800         # hard cap per chunk regardless of budget
HISTORY_TOKEN_BUDGET = 2000   # budget for the conversation history block


def estimate_tokens(text: str) -> int:
  """Cheap token estimate without pulling in tiktoken."""
  if not text:
    return 0
  cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
  rest = len(text) - cjk
  return int(cjk * 1.5 + rest * 0.35)


def format_context(chunks: Iterable[dict] | None,
                   token_budget: int = CONTEXT_TOKEN_BUDGET) -> str:
  """Render retrieved_chunks as a numbered reference block, within token budget.

  Chunks are kept in their original (score-descending) order. If the block
  exceeds the budget, the lowest-score chunks at the tail are dropped first.
  Each chunk is also hard-capped at MAX_CHUNK_CHARS. Numbers are 1-based and
  match the [n] citation tokens the answer prompt expects.
  """
  chunk_list = list(chunks) if chunks else []
  if not chunk_list:
    return _EMPTY_CONTEXT

  # Pre-truncate each chunk, then accumulate until budget is hit.
  rendered: list[tuple[int, str]] = []  # (original index, text)
  used = 0
  for i, c in enumerate(chunk_list):
    text = (c.get("text") or "")[:MAX_CHUNK_CHARS]
    title = c.get("title") or c.get("note_id", "?")
    block = "[%d] source: %s\n%s" % (i + 1, title, text)
    cost = estimate_tokens(block)
    if used + cost > token_budget and rendered:
      _log.info("context: dropped %d/%d chunks over token budget (%d/%d tokens)",
                len(chunk_list) - len(rendered), len(chunk_list), used, token_budget)
      break
    rendered.append((i, block))
    used += cost

  if not rendered:
    return _EMPTY_CONTEXT
  return _SEPARATOR.join(block for _, block in rendered)


def trim_history(messages: list[dict],
                 max_messages: int = 12,
                 token_budget: int = HISTORY_TOKEN_BUDGET) -> tuple[list[dict], list[dict]]:
  """Split history into (kept_recent, overflow).

  Keeps the most recent ``max_messages`` messages that also fit within
  ``token_budget``. Returns (recent, overflow) where overflow is the older
  messages that were cut (oldest first) - callers may summarize them.
  """
  if not messages:
    return [], []

  recent: list[dict] = []
  used = 0
  for m in reversed(messages[-max_messages:]):
    cost = estimate_tokens(m.get("content") or "")
    if used + cost > token_budget and recent:
      break
    recent.append(m)
    used += cost
  recent.reverse()

  # `recent` is always a suffix of `messages`, so the overflow is the prefix.
  overflow = messages[: len(messages) - len(recent)]
  return recent, overflow


def _profile_line(profile: dict) -> str:
  """Compress the user profile dict into one short line for the system prompt."""
  if not profile:
    return ""
  try:
    return "[user profile] " + json.dumps(profile, ensure_ascii=False)[:300]
  except Exception:
    return ""


def _strip_citation_rules(text: str) -> str:
  """Remove citation-related rules from the system prompt when no chunks exist.

  Prevents the LLM from faithfully following "末尾输出 来源：[n][m]..." and
  emitting a bogus "来源：无" line when there is nothing to cite.
  """
  lines = text.split("\n")
  out: list[str] = []
  skip = False
  for line in lines:
    stripped = line.strip()
    low = stripped.lower()
    # Skip numbered rule "Cite sources by index [n]..."
    if low.startswith("cite sources"):
      continue
    # Skip the "Citations:" bullet under Output format (and its continuation)
    if low.startswith("citations:"):
      skip = True
      continue
    # Continuation of the citations bullet (indented or starts with "listing")
    if skip and (line.startswith("    ") or line.startswith("\t") or low.startswith("listing") or low.startswith("do not")):
      continue
    # Stop skipping when we hit a non-indented line that is not empty
    if skip and stripped and not line[0].isspace():
      skip = False
    if skip:
      continue
    out.append(line)
  return "\n".join(out)


def build_messages(instructions: str,
                   chunks: list,
                   history: list[dict],
                   question: str,
                   summary: str = "",
                   profile: dict | None = None) -> list:
  """Assemble the final LangChain message list (§7).

  Order is fixed: system (instructions + summary + profile + references)
  -> trimmed history -> current question. The ``<<CONTEXT>>`` and
  ``<<QUESTION>>`` placeholders in ``instructions`` are filled here.

  When there are no reference chunks, citation-related rules are stripped
  from the instructions so the LLM does not output a bogus "来源：无" line.
  """
  from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

  context_block = format_context(chunks)
  has_chunks = bool(chunks)
  sys_text = instructions.replace("<<CONTEXT>>", context_block)
  sys_text = sys_text.replace("<<QUESTION>>", question)

  # Strip citation rules when there is nothing to cite — otherwise the model
  # faithfully follows the prompt and emits "来源：无" at the end.
  if not has_chunks:
    sys_text = _strip_citation_rules(sys_text)

  parts = [sys_text]
  if summary:
    parts.append("[history summary] " + summary[:400])
  line = _profile_line(profile or {})
  if line:
    parts.append(line)

  msgs = [SystemMessage(content="\n\n".join(parts))]

  # History: drop the trailing entry if it duplicates the current question so
  # the question appears exactly once at the end.
  hist = list(history or [])
  if hist and hist[-1].get("role") == "user" and hist[-1].get("content") == question:
    hist = hist[:-1]
  recent, _overflow = trim_history(hist)
  for m in recent:
    if m.get("role") == "user":
      msgs.append(HumanMessage(m.get("content") or ""))
    else:
      msgs.append(AIMessage(m.get("content") or ""))

  msgs.append(HumanMessage(content=question))

  total = sum(estimate_tokens(getattr(m, "content", "") or "") for m in msgs)
  _log.info("context: built %d messages, ~%d tokens (history=%d, chunks=%d)",
            len(msgs), total, len(recent), len(chunks))
  return msgs
