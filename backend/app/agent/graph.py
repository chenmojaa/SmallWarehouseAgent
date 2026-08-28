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

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.agent.state import AgentState
from app.agent.nodes.ingest import ingest_node
from app.agent.nodes.report import report_node
from app.agent.nodes.research import research_node
from app.agent.nodes.retrieve import retrieve_node
from app.agent.nodes.router import route_by_intent, router_node


def build_graph():
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
  # Phase 3.2: attach a MemorySaver so the graph can persist state per
  # thread_id across calls. SQLite-backed AsyncSqliteSaver is the next step
  # (see CONTEXT_UPGRADE.md Phase 3); MemorySaver is enough to prove the
  # thread_id -> history recovery wiring works in this PR. The checkpointer
  # is shared as a module-level singleton so all callers of `graph` below
  # see the same one without rebuilding the compiled object.
  checkpointer = MemorySaver()
  return g.compile(checkpointer=checkpointer)


graph = build_graph()
