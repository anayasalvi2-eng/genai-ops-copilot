"""
Agent Node Functions — each function is a node in the LangGraph state machine.

Nodes receive the current GraphState dict and return a partial dict with only
the keys they update.  LangGraph merges the returned dict back into the state.
"""

import json
import logging
import re
from typing import Any

from app.mcp.gateway import MCPGateway
from app.llm_gateway.gateway import LLMGateway

logger = logging.getLogger(__name__)

# MCP gateway has no external dependencies — safe to instantiate at import time.
_mcp_gateway = MCPGateway()

# LLM gateway requires OPENAI_API_KEY; defer construction until first use so
# that the .env file has been loaded by the time __init__ runs.
_llm_gateway: LLMGateway | None = None


def _get_llm_gateway() -> LLMGateway:
    """Return the shared LLMGateway, constructing it on first call."""
    global _llm_gateway
    if _llm_gateway is None:
        _llm_gateway = LLMGateway()
    return _llm_gateway


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pretty_json(data: Any) -> str:
    """Serialise data to an indented JSON string for prompt injection."""
    return json.dumps(data, indent=2, default=str)


def _extract_case_id(query: str) -> str | None:
    """Extract a PACT case id from free-text query (e.g. PACT-2026-004421)."""
    match = re.search(r"\bPACT-\d{4}-\d{4,}\b", query.upper())
    return match.group(0) if match else None


# ---------------------------------------------------------------------------
# Node: fetch
# ---------------------------------------------------------------------------

def fetch_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch node — calls the MCP Gateway to retrieve all enterprise data sources.

    Updates: tlm, pact, great_expectations
    """
    logger.info("fetch_node: fetching data from TLM, PACT, and Great Expectations MCP servers")
    all_data = _mcp_gateway.fetch_all()
    return {
        "tlm": all_data.get("tlm", {}),
        "pact": all_data.get("pact", {}),
        "great_expectations": all_data.get("great_expectations", {}),
    }


def case_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Case Agent — finds a PACT case by case_id in the query and investigates it.

    Updates: case_id, case_details, case_investigation
    """
    query = state.get("query", "")
    case_id = _extract_case_id(query)
    if not case_id:
        return {
            "case_id": None,
            "case_details": {},
            "case_investigation": "No explicit PACT case ID found in the query.",
        }

    pact_cases = state.get("pact", {}).get("cases", [])
    target_case = next(
        (c for c in pact_cases if str(c.get("case_id", "")).upper() == case_id),
        None,
    )

    if not target_case:
        available_ids = [c.get("case_id") for c in pact_cases][:10]
        return {
            "case_id": case_id,
            "case_details": {},
            "case_investigation": (
                f"Case {case_id} not found in PACT data. "
                f"Available cases: {available_ids}"
            ),
        }

    linked_break_id = target_case.get("linked_break")
    tlm_breaks = state.get("tlm", {}).get("breaks", [])
    related_break = next(
        (b for b in tlm_breaks if b.get("break_id") == linked_break_id),
        {},
    )

    linked_ge_suite = target_case.get("linked_ge_suite")
    ge_suites = state.get("great_expectations", {}).get("validation_results", [])
    related_ge = next(
        (g for g in ge_suites if g.get("suite_name") == linked_ge_suite),
        {},
    )

    analysis = _get_llm_gateway().invoke(
        prompt_name="case_resolution_v1",
        system_prompt=(
            "You are a senior financial operations investigator. "
            "Produce a concrete resolution plan with owners and deadlines."
        ),
        query=query,
        case_id=case_id,
        case_details=_pretty_json(target_case),
        related_tlm_break=_pretty_json(related_break),
        related_ge_result=_pretty_json(related_ge),
    )

    return {
        "case_id": case_id,
        "case_details": target_case,
        "case_investigation": analysis,
    }


# ---------------------------------------------------------------------------
# Node: tlm_agent
# ---------------------------------------------------------------------------

def tlm_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    TLM Agent — analyses SmartStream TLM transaction breaks via the LLM Gateway.

    Updates: tlm_analysis
    """
    logger.info("tlm_agent_node: analysing TLM reconciliation breaks")
    tlm_text = _pretty_json(state.get("tlm", {}))
    analysis = _get_llm_gateway().invoke(
        prompt_name="tlm_analysis_v1",
        system_prompt=(
            "You are a senior financial operations engineer. "
            "Be concise, structured, and focus on SLA risk and remediation."
        ),
        tlm=tlm_text,
    )
    return {"tlm_analysis": analysis}


# ---------------------------------------------------------------------------
# Node: pact_agent
# ---------------------------------------------------------------------------

def pact_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    PACT Agent — analyses exception cases from the PACT case management system.

    Updates: pact_analysis
    """
    logger.info("pact_agent_node: analysing PACT exception cases")
    pact_text = _pretty_json(state.get("pact", {}))
    analysis = _get_llm_gateway().invoke(
        prompt_name="pact_analysis_v1",
        system_prompt=(
            "You are a financial operations case manager. "
            "Be concise, structured, and focus on SLA risk and next best actions."
        ),
        pact=pact_text,
    )
    return {"pact_analysis": analysis}


# ---------------------------------------------------------------------------
# Node: ge_agent
# ---------------------------------------------------------------------------

def ge_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Great Expectations Agent — analyses GE checkpoint validation results.

    Updates: ge_analysis
    """
    logger.info("ge_agent_node: analysing Great Expectations validation results")
    ge_text = _pretty_json(state.get("great_expectations", {}))
    analysis = _get_llm_gateway().invoke(
        prompt_name="ge_analysis_v1",
        system_prompt=(
            "You are a senior data quality engineer. "
            "Be concise, structured, and focus on business impact and root cause."
        ),
        ge=ge_text,
    )
    return {"ge_analysis": analysis}


# ---------------------------------------------------------------------------
# Node: final_agent
# ---------------------------------------------------------------------------

def final_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Final Agent — aggregates TLM, PACT, and GE analyses into a root cause report.

    Updates: final_response
    """
    logger.info("final_agent_node: producing root cause analysis")
    response = _get_llm_gateway().invoke(
        prompt_name="root_cause_analysis_v1",
        system_prompt=(
            "You are an expert operations SRE specialising in financial data platforms. "
            "Provide a precise, structured root cause analysis."
        ),
        tlm_analysis=state.get("tlm_analysis", "Not available."),
        pact_analysis=state.get("pact_analysis", "Not available."),
        ge_analysis=state.get("ge_analysis", "Not available."),
        case_investigation=state.get("case_investigation", "No case-specific investigation requested."),
        query=state.get("query", ""),
    )
    return {"final_response": response}
