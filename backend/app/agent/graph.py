"""LangGraph graph: router -> (retrieve|research|ingest|report) -> answer.

Per OPTIMIZATION.md section 2.4. The router classifies intent and rewrites the
query for downstream nodes. ingest/report terminate at END without going through
the answer node; retrieve and research both feed retrieved_chunks into answer.

HD_USE_GRAPH=false (env) keeps the legacy direct-call path in chat.py active;
default is graph-driven.
"""
from __future__ import annotations

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.agent.state import AgentState
from app.agent.nodes.answer import answer_node
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
  g.add_node("answer", answer_node)

  g.add_edge(START, "router")
  g.add_conditional_edges("router", route_by_intent, {
    "chat": "retrieve",
    "research": "research",
    "ingest": "ingest",
    "report": "report",
  })
  g.add_edge("retrieve", "answer")
  g.add_edge("research", "answer")
  g.add_edge("answer", END)
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
