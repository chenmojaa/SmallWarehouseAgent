"""LangGraph graph: router -> (retrieve|research|ingest|report).

Per OPTIMIZATION.md section 2.4. The router classifies intent and rewrites the
query for downstream nodes. ingest/report terminate at END. Retrieval nodes
populate ``retrieved_chunks`` and also terminate at END; chat.py then streams
the answer with ``answer_node_stream`` so reasoning models do not have to pass
through a separate structured-output call.

HD_USE_GRAPH=false (env) keeps the legacy direct-call path in chat.py active;
default is graph-driven.
"""
from __future__ import annotations

import os

import aiosqlite
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent.state import AgentState
from app.config import settings
from app.agent.nodes.ingest import ingest_node
from app.agent.nodes.report import report_node
from app.agent.nodes.research import research_node
from app.agent.nodes.retrieve import retrieve_node
from app.agent.nodes.router import route_by_intent, router_node


def _build_workflow() -> StateGraph:
  g = StateGraph(AgentState)
  g.add_node("router", router_node)
  g.add_node("retrieve", retrieve_node)
  g.add_node("research", research_node)
  g.add_node("ingest", ingest_node)
  g.add_node("report", report_node)

  g.add_edge(START, "router")
  g.add_conditional_edges("router", route_by_intent, {
    "chat": "retrieve",
    "chat_no_rag": END,
    "research": "research",
    "ingest": "ingest",
    "report": "report",
  })
  g.add_edge("retrieve", END)
  g.add_edge("research", END)
  g.add_edge("ingest", END)
  g.add_edge("report", END)
  return g


# ---- Lazy async graph singleton ----
# AsyncSqliteSaver.__init__ calls asyncio.get_running_loop(), so the saver (and
# therefore the compiled graph) cannot be constructed at import time. We build it
# once on first async use and cache it. The aiosqlite connection is opened lazily
# by the saver and lives for the process lifetime.
_graph = None
_conn = None


async def get_graph():
  """Return the compiled graph, building the SQLite checkpointer on first call."""
  global _graph, _conn
  if _graph is None:
    ckpt_path = os.path.join(settings.data_dir, "checkpoints.sqlite")
    os.makedirs(settings.data_dir, exist_ok=True)
    _conn = aiosqlite.connect(ckpt_path)
    checkpointer = AsyncSqliteSaver(_conn)
    _graph = _build_workflow().compile(checkpointer=checkpointer)
  return _graph
