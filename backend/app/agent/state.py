"""LangGraph state schema for the HEAR agent."""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict, total=False):
  # ---- conversation ----
  # Phase 3.1: Annotated[list, operator.add] makes LangGraph concatenate per-node
  # message deltas instead of replacing the whole list. Without this annotation
  # a node returning {"messages": [m]} would clobber history; with it the same
  # node appends m to the existing list. Required for the checkpointer-driven
  # cross-call accumulation planned for Phase 3.5.
  messages: Annotated[list, operator.add]
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
