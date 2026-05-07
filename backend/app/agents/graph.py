"""
LangGraph Agent Graph — wires together the fetch, TLM, PACT, GE, and final
agent nodes into a stateful, parallel-capable execution graph.

Graph flow:
    START
      └─► fetch
            ├─► tlm_agent       ─┐
            ├─► pact_agent      ─┼─► final_agent ─► END
            └─► ge_agent        ─┘
"""

import logging
from typing import Any, TypedDict

from langgraph.graph import StateGraph, START, END

from app.agents.nodes import (
    fetch_node,
    case_agent_node,
    tlm_agent_node,
    pact_agent_node,
    ge_agent_node,
    final_agent_node,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class GraphState(TypedDict, total=False):
    """
    Typed state shared across all graph nodes.

    All fields are optional so nodes can return partial updates.
    """
    query: str                      # Original user query
    case_id: str | None             # Case id extracted from query, if present
    case_details: dict[str, Any]    # Resolved PACT case details
    tlm: dict[str, Any]            # Raw TLM break data from MCP
    pact: dict[str, Any]           # Raw PACT case data from MCP
    great_expectations: dict[str, Any]  # Raw GE validation results from MCP
    case_investigation: str         # LLM case-specific investigation and resolution
    tlm_analysis: str              # LLM analysis of TLM breaks
    pact_analysis: str             # LLM analysis of PACT cases
    ge_analysis: str               # LLM analysis of GE validation results
    final_response: str            # Root cause + recommendation from final agent


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph():
    """
    Construct and compile the LangGraph StateGraph.

    Returns a compiled graph that can be invoked with:
        graph.invoke({"query": "..."})
    """
    builder = StateGraph(GraphState)

    # Register nodes
    builder.add_node("fetch", fetch_node)
    builder.add_node("case_agent", case_agent_node)
    builder.add_node("tlm_agent", tlm_agent_node)
    builder.add_node("pact_agent", pact_agent_node)
    builder.add_node("ge_agent", ge_agent_node)
    builder.add_node("final_agent", final_agent_node)

    # Wire edges
    builder.add_edge(START, "fetch")

    # Three parallel analysis branches after fetch
    builder.add_edge("fetch", "case_agent")
    builder.add_edge("fetch", "tlm_agent")
    builder.add_edge("fetch", "pact_agent")
    builder.add_edge("fetch", "ge_agent")

    # All three converge into the final root cause agent
    builder.add_edge("case_agent", "final_agent")
    builder.add_edge("tlm_agent", "final_agent")
    builder.add_edge("pact_agent", "final_agent")
    builder.add_edge("ge_agent", "final_agent")

    builder.add_edge("final_agent", END)

    graph = builder.compile()
    logger.info("LangGraph agent graph compiled successfully (TLM + PACT + GE)")
    return graph
