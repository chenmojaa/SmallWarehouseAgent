# -*- coding: utf-8 -*-
"""Report agent: pull recent notes (last N days), group by tag, summarize via LLM,
and ingest the generated report back as a note.

Design (per OPTIMIZATION.md section 2.8):
  - Triggered by router intent="report" with optional user message ("this week").
  - If the message mentions a period (e.g. "this month", "last 7 days"), parse it.
    Otherwise default to the last 7 days.
  - Generate Markdown report with sections grouped by tag (max 8 tags).
  - Ingest the report as a new note so it can be retrieved later.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session as SqlSession, select

from app.agent.state import AgentState
from app.config import settings
from app.llm.factory import _build_model
from app.storage.db import Note, get_engine
from app.tools.ingest import ingest_text

_log = logging.getLogger(__name__)

_PERIOD_PATTERNS = [
    (re.compile(r"\u4e0a\u4e2a\u6708|last\s*month", re.IGNORECASE), 30),
    (re.compile(r"\u4e0a\u5468|last\s*week", re.IGNORECASE), 7),
    (re.compile(r"\u8fd9\u4e2a\u6708|this\s*month", re.IGNORECASE), 30),
    (re.compile(r"\u672c\u5468|this\s*week", re.IGNORECASE), 7),
    (re.compile(r"\u8fd1\s*(\d+)\s*\u5929|last\s*(\d+)\s*days?", re.IGNORECASE), None),
    (re.compile(r"\u8fd1\s*(\d+)\s*\u4e2a\u6708", re.IGNORECASE), None),
]


def _detect_days(text: str, default: int = 7) -> int:
    for pat, val in _PERIOD_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        if val is not None:
            return val
        try:
            n = int(next(g for g in m.groups() if g))
            unit = pat.pattern
            return n * 30 if "\u6708" in unit or "month" in unit else n
        except Exception:
            continue
    return default


def _recent_notes(days: int) -> list[Note]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    engine = get_engine()
    with SqlSession(engine) as s:
        stmt = select(Note).where(Note.created_at >= cutoff).order_by(Note.created_at.desc())
        return list(s.exec(stmt).all())


def _group_by_tag(notes: list[Note], max_groups: int = 8) -> dict[str, list[Note]]:
    groups: dict[str, list[Note]] = {}
    for n in notes:
        raw_tags = n.tags or ""
        tag_list = [t.strip() for t in re.split(r"[,;\u3001]", raw_tags) if t.strip()] or ["\u672a\u5206\u7c7b"]
        for t in tag_list[:3]:  # cap per-note tag contribution
            groups.setdefault(t, []).append(n)
    # Keep top N groups by note count
    ranked = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    return dict(ranked[:max_groups])


def _summarize_with_llm(period_label: str, groups: dict[str, list[Note]], chat) -> str:
    """Cheap LLM call -> Markdown report."""
    sections = []
    for tag, notes in groups.items():
        titles = [n.title for n in notes[:8] if n.title]
        summaries = [(n.summary or "")[:80] for n in notes[:8]]
        sections.append("## %s (%d \u7bc7)\n- %s" % (tag, len(notes), "\n- ".join(titles)))
    raw = "\n\n".join(sections) or "(no notes in this period)"
    prompt = (
        "\u4f60\u662f\u5468\u62a5\u8d77\u8349\u673a\u3002\u4ee5\u4e0b\u662f\u8fd1 %s \u7684\u77e5\u8bc6\u5e93\u53d8\u52a8\uff0c\u8bf7\u751f\u6210\u4e00\u4efd\u4e2d\u6587\u5468\u62a5\u3002\n"
        "\u8981\u6c42\uff1a\n"
        "- Markdown \u7ed3\u6784\uff0c\u9876\u90e8\u4e00\u884c\u6807\u9898\u3001\u4e0b\u9762 3-5 \u6bb5\u603b\u89c8\n"
        "- \u6309 tag \u5206\u7ec4\u5217\u70b9\u8981\u70b9\uff08\u91cd\u8981\u53d8\u52a8 / \u53ef\u80fd\u7684\u5173\u8054 / \u4e0b\u4e00\u6b65\u52a8\u4f5c\uff09\n"
        "- \u603b\u957f\u5ea6 \u22642000 \u5b57\n\n%s" % (period_label, raw)
    )
    try:
        resp = chat.invoke(prompt)
        text = getattr(resp, "content", None) or str(resp)
        return (text or raw).strip()
    except Exception as e:
        _log.warning("report: llm summarize failed: %s", e)
        return "# %s\n\n%s" % (period_label, raw)


def report_node(state: AgentState) -> dict:
    """Build a period report and persist it as a new note."""
    query = state.get("query") or state.get("rewritten_query") or ""
    days = _detect_days(query, default=7)
    period_label = "\u8fd1 %d \u5929" % days
    notes = _recent_notes(days)
    if not notes:
        return {
            "report_result": {"ok": True, "empty": True, "period_days": days,
                              "message": "%s \u5185\u65e0\u65b0\u5165\u5e93\u5185\u5bb9" % period_label},
            "step_count": state.get("step_count", 0) + 1,
        }

    groups = _group_by_tag(notes)
    try:
        chat = _build_model(
            provider=None,
            model=state.get("model_override"),
            api_key=state.get("api_key_override"),
            base_url=state.get("base_url_override"),
            reasoning_level=None,
        )
        body = _summarize_with_llm(period_label, groups, chat)
    except Exception as e:
        _log.warning("report: model init failed: %s", e)
        body = "# %s\n\n%s" % (period_label, "\n\n".join(
            "## %s (%d \u7bc7)\n- %s" % (t, len(ns), "\n- ".join(n.title for n in ns[:8]))
            for t, ns in groups.items()))

    title = "\u5468\u62a5 / %s\u3001\u603b %d \u7bc7" % (
        datetime.now().strftime("%Y-%m-%d"), len(notes))
    try:
        note = ingest_text(
            body,
            title=title,
            api_key=state.get("api_key_override"),
            base_url=state.get("base_url_override"),
        )
        note_id = note.id
    except Exception as e:
        _log.warning("report: ingest_text failed: %s", e)
        note_id = None

    return {
        "report_result": {
            "ok": True,
            "empty": False,
            "period_days": days,
            "note_id": note_id,
            "counts": {"notes": len(notes), "tags": len(groups)},
            "summary": body[:300],
        },
        "step_count": state.get("step_count", 0) + 1,
    }