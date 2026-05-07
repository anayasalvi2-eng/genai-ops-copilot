"""
Prompt Manager — stores versioned prompt templates and renders them with
variable injection.

Templates are stored in-memory for simplicity.  In production these would be
loaded from a database or a prompt registry service (e.g. LangSmith Hub).
"""

import logging
from string import Template

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in prompt templates — versioned by name
# ---------------------------------------------------------------------------
_PROMPT_REGISTRY: dict[str, str] = {
    # Analyse TLM transaction lifecycle breaks
    "tlm_analysis_v1": (
        "You are a senior financial operations engineer specialising in settlement "
        "and transaction lifecycle management (TLM / SmartStream).\n"
        "Analyse the following TLM reconciliation break report. For each break identify:\n"
        "- The break type and root cause\n"
        "- SLA status and penalty risk\n"
        "- Recommended remediation action and urgency\n\n"
        "TLM Break Report:\n$tlm"
    ),
    # Analyse PACT exception cases
    "pact_analysis_v1": (
        "You are a financial operations case manager.\n"
        "Analyse the following PACT exception cases. For each case identify:\n"
        "- Current investigation status and gaps\n"
        "- SLA risk and financial exposure\n"
        "- Next best action for the operations team\n\n"
        "PACT Cases:\n$pact"
    ),
    # Analyse Great Expectations validation results
    "ge_analysis_v1": (
        "You are a senior data quality engineer with expertise in Great Expectations.\n"
        "Analyse the following GE checkpoint results. For each failed expectation identify:\n"
        "- What the failure means in business terms\n"
        "- Likely upstream cause (pipeline issue, schema drift, source system problem)\n"
        "- Severity and downstream impact\n\n"
        "Great Expectations Results:\n$ge"
    ),
    # Case-specific investigation and resolution
    "case_resolution_v1": (
        "You are a senior operations investigator.\n"
        "Investigate the requested PACT case in detail and produce a concrete resolution.\n\n"
        "## User Query\n$query\n\n"
        "## Case ID\n$case_id\n\n"
        "## PACT Case Details\n$case_details\n\n"
        "## Related TLM Break\n$related_tlm_break\n\n"
        "## Related Great Expectations Result\n$related_ge_result\n\n"
        "Return:\n"
        "**Case Summary:** <current status and risk>\n\n"
        "**Investigation Findings:** <root cause and cross-system evidence>\n\n"
        "**Resolution Plan:** <numbered steps with owner and ETA>\n\n"
        "**Closure Criteria:** <what must be true before closing the case>"
    ),
    # LLM planner for fully agentic tool selection
    "tool_router_v1": (
        "You are the planning brain for an enterprise GenAI Ops Copilot.\n"
        "Your job is to call MCP tools one by one to build a COMPLETE investigation before answering.\n\n"
        "MANDATORY INVESTIGATION CHECKLIST — you MUST collect ALL of the following before action='final':\n"
        "  1. PACT case details (mcp.get_case_by_id or mcp.get_pact_cases)\n"
        "  2. TLM reconciliation breaks (mcp.get_tlm_breaks or mcp.get_tlm_break_by_id)\n"
        "  3. Great Expectations validation results (mcp.get_ge_results or mcp.get_ge_suite_result)\n"
        "  4. Notification templates (mcp.get_notification_templates) — to suggest the correct alert email\n"
        "Only set action='final' after ALL four systems above have been queried.\n\n"
        "RULES:\n"
        "- Output ONLY valid JSON — no markdown, no extra text.\n"
        "- Never call the same tool twice with the same arguments.\n"
        "- Never invent tool names; use only names from the tool metadata.\n"
        "- Always format currency amounts as USD with $$ sign and comma separators (e.g. $$10,620,000).\n"
        "- When action='final', write final_answer using EXACTLY this structure:\n"
        "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  🔴 ISSUE\n"
        "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  <case summary: id, type, priority, financial exposure, affected trade>\n\n"
        "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  🔍 ROOT CAUSE ANALYSIS (RCA)\n"
        "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  <Write 3-5 sentences of flowing narrative prose — no labels like 'PACT:' or 'TLM:'.\n"
        "   Explain what happened, why it happened, and how the evidence from PACT, TLM and GE\n"
        "   corroborates the root cause. Read like an incident report written by a senior SRE.>\n\n"
        "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  ✅ RESOLUTION\n"
        "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  <numbered action steps with owner + deadline>\n"
        "  Closure Criteria: <what must be true to close the case>\n"
        "  Recommended Notification: <which template to send and to whom>\n\n"
        "JSON schema:\n"
        "{\n"
        "  \"action\": \"tool\" | \"final\",\n"
        "  \"reason\": \"short rationale\",\n"
        "  \"tool_name\": \"mcp.get_case_by_id\",\n"
        "  \"tool_args\": {},\n"
        "  \"final_answer\": \"<structured report>\"\n"
        "}\n\n"
        "## User Query\n$query\n\n"
        "## Remaining Steps\n$remaining_steps\n\n"
        "## Available MCP Tools\n$tools_metadata\n\n"
        "## Observations So Far\n$observations"
    ),
    # Synthesis prompt when planner reaches step limit without finalizing
    "agentic_final_synthesis_v1": (
        "You are an expert operations SRE specialising in financial data platforms.\n"
        "Synthesize a high-confidence investigation report using ONLY the tool observations below.\n"
        "If data is missing, call that out explicitly and state the next best action.\n\n"
        "## User Query\n$query\n\n"
        "## Tool Observations\n$observations\n\n"
        "Respond using EXACTLY this structure (no extra sections):\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔴 ISSUE\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<Concise description of the problem: case ID, type, priority, financial exposure, SLA status, and affected instruments/trades>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔍 ROOT CAUSE ANALYSIS (RCA)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<Write 3-5 sentences of flowing narrative prose — no labels like 'PACT:' or 'TLM:'.\n"
        " Explain what happened, why it happened, and how the cross-system evidence (PACT case,\n"
        " TLM break, GE validation failures) corroborates the root cause.\n"
        " Write as a senior SRE authoring a post-incident report.>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ RESOLUTION\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<Numbered action plan with owner, concrete steps, and deadlines.\n"
        "End with Closure Criteria: what must be true before the case is closed.>"
    ),
    # Combined root cause analysis across all three domains
    "root_cause_analysis_v1": (
        "You are an expert operations SRE specialising in financial data platforms.\n"
        "You have been given analysis from three systems: TLM (transaction breaks), "
        "PACT (exception cases), and Great Expectations (data validation).\n\n"
        "## TLM Analysis\n$tlm_analysis\n\n"
        "## PACT Case Analysis\n$pact_analysis\n\n"
        "## Great Expectations Analysis\n$ge_analysis\n\n"
        "## Case Investigation\n$case_investigation\n\n"
        "## User Query\n$query\n\n"
        "Produce a structured root cause analysis in the following format:\n\n"
        "**Root Cause:** <single concise sentence>\n\n"
        "**Affected Systems:** <list: TLM / PACT / GE suites impacted>\n\n"
        "**Financial Exposure:** <total USD exposure and penalty risk>\n\n"
        "**Impact:** <business and operational impact>\n\n"
        "**Recommended Fix:** <numbered action plan with owners and deadlines>\n\n"
        "**Estimated Recovery Time:** <estimate>"
    ),
}


class PromptManager:
    """
    Manages versioned prompt templates with safe variable substitution.
    """

    def __init__(self) -> None:
        self._registry: dict[str, str] = dict(_PROMPT_REGISTRY)

    def register(self, name: str, template: str) -> None:
        """Register a new prompt template or overwrite an existing one."""
        self._registry[name] = template
        logger.info("PromptManager: registered template '%s'", name)

    def render(self, name: str, **variables: str) -> str:
        """
        Render a named template by substituting ``$key`` placeholders.

        Raises:
            KeyError: if the template name is not found.
            ValueError: if a required variable is missing.
        """
        if name not in self._registry:
            raise KeyError(f"PromptManager: template '{name}' not found in registry.")

        template = Template(self._registry[name])
        try:
            rendered = template.substitute(variables)
        except KeyError as exc:
            raise ValueError(
                f"PromptManager: missing variable {exc} for template '{name}'."
            ) from exc

        logger.debug("PromptManager: rendered template '%s'", name)
        return rendered

    def list_templates(self) -> list[str]:
        """Return the names of all registered templates."""
        return list(self._registry.keys())
