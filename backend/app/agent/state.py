"""LangGraph state schema for the HEAR agent."""
from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
  # ---- conversation ----
  # Replace semantics (no reducer): chat.py seeds the full history from the DB
  # on every call (server is the source of truth), so the input must overwrite
  # whatever the checkpointer stored. With an operator.add reducer the seeded
  # history would be appended to the checkpointed copy and duplicate every turn.
  messages: list
  session_id: str

  # ---- long-term memory (§6.5) ----
  profile: dict                     # user profile facts, injected by chat.py
  summary: str                      # compressed summary of history outside the window

  # ---- current request ----
  query: str
  intent: str                       # chat | research | ingest | report (router output)
  rewritten_query: str              # router output: original query + 3-turn history resolved

  # ---- retrieval results ----
  retrieved_chunks: list
  skip_retrieval: bool              # fast-path: skip retrieve node for greetings
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
  embedding_model_override: str | None
  step_count: int
