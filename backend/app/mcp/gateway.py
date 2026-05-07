"""
MCP Gateway — registry and dispatcher for MCP servers and MCP tools.

This gateway now exposes two separate capabilities:
1. Server-level fetch APIs (for compatibility with existing graph flows)
2. Tool-level metadata and execution APIs for fully agentic planning
"""

import logging
from typing import Any, Callable

from app.mcp.tlm_server import get_tlm_data
from app.mcp.pact_server import get_pact_data
from app.mcp.great_expectations_server import get_great_expectations_data
from app.mcp.notification_server import get_notification_data, send_notification

logger = logging.getLogger(__name__)


class MCPGateway:
    """
    Multi-source Context Provider Gateway.

    - Registers MCP servers and fetches their data.
    - Exposes MCP tool metadata for LLM planning.
    - Executes tools selected by an agentic planner.
    """

    def __init__(self) -> None:
        self._servers: dict[str, Callable[[], dict[str, Any]]] = {}
        self._tools: dict[str, dict[str, Any]] = {}
        self._register_defaults()
        self._register_default_tools()

    def _register_defaults(self) -> None:
        """Register all enterprise domain MCP servers."""
        self.register("tlm", get_tlm_data)
        self.register("pact", get_pact_data)
        self.register("great_expectations", get_great_expectations_data)
        self.register("notifications", get_notification_data)

    def _register_default_tools(self) -> None:
        """Register built-in MCP tools exposed to the LLM planner."""
        self._tools = {
            "mcp.get_pact_cases": {
                "name": "mcp.get_pact_cases",
                "description": "Get all PACT cases for current operational window.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
                "output_schema": {"type": "object", "properties": {"cases": {"type": "array"}}},
                "server": "pact",
            },
            "mcp.get_case_by_id": {
                "name": "mcp.get_case_by_id",
                "description": "Find a single PACT case by case_id.",
                "input_schema": {
                    "type": "object",
                    "properties": {"case_id": {"type": "string"}},
                    "required": ["case_id"],
                },
                "output_schema": {"type": "object", "properties": {"case": {"type": "object"}}},
                "server": "pact",
            },
            "mcp.get_tlm_breaks": {
                "name": "mcp.get_tlm_breaks",
                "description": "Get all TLM reconciliation breaks.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
                "output_schema": {"type": "object", "properties": {"breaks": {"type": "array"}}},
                "server": "tlm",
            },
            "mcp.get_tlm_break_by_id": {
                "name": "mcp.get_tlm_break_by_id",
                "description": "Find a single TLM break by break_id.",
                "input_schema": {
                    "type": "object",
                    "properties": {"break_id": {"type": "string"}},
                    "required": ["break_id"],
                },
                "output_schema": {"type": "object", "properties": {"break": {"type": "object"}}},
                "server": "tlm",
            },
            "mcp.get_ge_results": {
                "name": "mcp.get_ge_results",
                "description": "Get Great Expectations checkpoint and validation results.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
                "output_schema": {
                    "type": "object",
                    "properties": {"validation_results": {"type": "array"}},
                },
                "server": "great_expectations",
            },
            "mcp.get_ge_suite_result": {
                "name": "mcp.get_ge_suite_result",
                "description": "Find Great Expectations result for a specific suite_name.",
                "input_schema": {
                    "type": "object",
                    "properties": {"suite_name": {"type": "string"}},
                    "required": ["suite_name"],
                },
                "output_schema": {"type": "object", "properties": {"suite": {"type": "object"}}},
                "server": "great_expectations",
            },
            "mcp.get_notification_templates": {
                "name": "mcp.get_notification_templates",
                "description": "List available notification email templates.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
                "output_schema": {
                    "type": "object",
                    "properties": {"available_templates": {"type": "array"}},
                },
                "server": "notifications",
            },
            "mcp.send_notification": {
                "name": "mcp.send_notification",
                "description": "Send a notification email using a named template.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "template": {"type": "string"},
                        "recipient_email": {"type": "string"},
                        "recipient_name": {"type": "string"},
                        "variables": {"type": "object"},
                    },
                    "required": ["template", "recipient_email", "recipient_name"],
                },
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "notification_id": {"type": "string"},
                        "status": {"type": "string"},
                    },
                },
                "server": "notifications",
            },
        }

    def register(self, name: str, handler: Callable[[], dict[str, Any]]) -> None:
        """Register a new MCP server callable under the given name."""
        if name in self._servers:
            logger.warning("MCPGateway: overwriting existing server '%s'", name)
        self._servers[name] = handler
        logger.info("MCPGateway: registered server '%s'", name)

    def fetch(self, name: str) -> dict[str, Any]:
        """Fetch data from a single named server."""
        if name not in self._servers:
            raise ValueError(f"MCPGateway: unknown server '{name}'")
        try:
            data = self._servers[name]()
            logger.debug("MCPGateway: fetched data from '%s'", name)
            return data
        except Exception as exc:
            logger.error("MCPGateway: error fetching '%s': %s", name, exc)
            raise

    def fetch_all(self) -> dict[str, dict[str, Any]]:
        """Fetch data from all registered servers and return as a keyed dict."""
        results: dict[str, dict[str, Any]] = {}
        for name in self._servers:
            results[name] = self.fetch(name)
        return results

    def list_tools(self) -> list[dict[str, Any]]:
        """Return MCP tool metadata used by agentic planners."""
        return list(self._tools.values())

    def execute_tool(self, tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a named MCP tool with validated arguments."""
        args = args or {}
        if tool_name not in self._tools:
            raise ValueError(f"MCPGateway: unknown tool '{tool_name}'")

        if tool_name == "mcp.get_pact_cases":
            pact = self.fetch("pact")
            return {"cases": pact.get("cases", []), "summary": pact.get("summary", {})}

        if tool_name == "mcp.get_case_by_id":
            case_id = str(args.get("case_id", "")).upper()
            if not case_id:
                raise ValueError("mcp.get_case_by_id requires 'case_id'")
            pact = self.fetch("pact")
            case = next(
                (c for c in pact.get("cases", []) if str(c.get("case_id", "")).upper() == case_id),
                None,
            )
            return {"case": case, "found": case is not None}

        if tool_name == "mcp.get_tlm_breaks":
            tlm = self.fetch("tlm")
            return {"breaks": tlm.get("breaks", []), "summary": tlm.get("summary", {})}

        if tool_name == "mcp.get_tlm_break_by_id":
            break_id = str(args.get("break_id", ""))
            if not break_id:
                raise ValueError("mcp.get_tlm_break_by_id requires 'break_id'")
            tlm = self.fetch("tlm")
            brk = next((b for b in tlm.get("breaks", []) if b.get("break_id") == break_id), None)
            return {"break": brk, "found": brk is not None}

        if tool_name == "mcp.get_ge_results":
            ge = self.fetch("great_expectations")
            return {
                "checkpoint_name": ge.get("checkpoint_name"),
                "overall_success": ge.get("overall_success"),
                "validation_results": ge.get("validation_results", []),
                "summary": ge.get("summary", {}),
            }

        if tool_name == "mcp.get_ge_suite_result":
            suite_name = str(args.get("suite_name", ""))
            if not suite_name:
                raise ValueError("mcp.get_ge_suite_result requires 'suite_name'")
            ge = self.fetch("great_expectations")
            suite = next(
                (v for v in ge.get("validation_results", []) if v.get("suite_name") == suite_name),
                None,
            )
            return {"suite": suite, "found": suite is not None}

        if tool_name == "mcp.get_notification_templates":
            notifications = self.fetch("notifications")
            return {
                "available_templates": notifications.get("available_templates", []),
                "summary": notifications.get("summary", {}),
            }

        if tool_name == "mcp.send_notification":
            template = str(args.get("template", ""))
            recipient_email = str(args.get("recipient_email", ""))
            recipient_name = str(args.get("recipient_name", ""))
            variables = args.get("variables", {}) or {}

            if not template or not recipient_email or not recipient_name:
                raise ValueError(
                    "mcp.send_notification requires 'template', 'recipient_email', and 'recipient_name'"
                )

            record = send_notification(
                template_name=template,
                recipient_email=recipient_email,
                recipient_name=recipient_name,
                **variables,
            )
            return record

        raise ValueError(f"MCPGateway: unsupported tool '{tool_name}'")