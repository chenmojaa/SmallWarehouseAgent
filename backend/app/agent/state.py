"""LangGraph state schema for the HEAR agent."""
from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
  # ---- conversation ----
  messages: list
  session_id: str

  # ---- current request ----
  query: str
  intent: str                       # chat | research | ingest | report (router output)
  rewritten_query: str              # router output: original query + 3-turn history resolved

  # ---- retrieval results ----
  retrieved_chunks: list
  research_iterations: int          # how many rounds research agent ran
  research_notes: list              # intermediate follow-up queries produced during research

  # ---- ingest agent output ----
  ingest_result: dict               # {title, tags, summary, note_id, duplicate_of, ...}

  # ---- report agent output ----
  report_result: dict               # {note_id, period, counts, summary}

  # ---- final answer ----
  answer: str | None
  citations: list

  # ---- per-request overrides ----
  provider_override: str | None
  model_override: str | None
  base_url_override: str | None
  api_key_override: str | None
  reasoning_level_override: str | None
  step_count: int
