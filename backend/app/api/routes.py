"""
API Routes — exposes ask, streaming ask, MCP metadata, and notification APIs.

This module now uses a fully agentic tool-planning loop where the LLM decides
which MCP tool to call next based on gateway metadata and prior observations.
"""

import asyncio
import json
import time
from typing import Any, Generator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.schemas import AskRequest, AskResponse, NotifyRequest, NotifyResponse
from app.mcp.notification_server import send_notification
from app.mcp.gateway import MCPGateway
from app.llm_gateway.gateway import LLMGateway

router = APIRouter()


def _pretty_json(data: object) -> str:
    return json.dumps(data, indent=2, default=str)


def _clip_text(text: str, max_chars: int = 2500) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated]"


def _clip_json(data: object, max_chars: int = 2500) -> str:
    return _clip_text(_pretty_json(data), max_chars=max_chars)


def _extract_json_obj(text: str) -> dict[str, Any]:
    """
    Parse a JSON object from model text.

    Supports plain JSON or JSON fenced in ```json blocks.
    """
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json", "", 1).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def _agentic_investigation_events(query: str) -> Generator[dict[str, Any], None, None]:
    """
    Run fully agentic planning loop and yield event dicts.

    Event types:
      - status
      - final
      - error
    """
    start = time.time()
    mcp = MCPGateway()
    llm = LLMGateway()

    max_steps = 12
    observations: list[dict[str, Any]] = []
    tools = mcp.list_tools()

    yield {"type": "status", "message": "Starting agentic planning..."}
    yield {"type": "status", "message": f"Loaded {len(tools)} MCP tools from gateway metadata"}

    final_answer: str | None = None

    for step in range(1, max_steps + 1):
        planner_observations = observations[-8:]
        yield {"type": "status", "message": f"Planning step {step}/{max_steps}"}

        planner_text = llm.invoke(
            prompt_name="tool_router_v1",
            system_prompt=(
                "You are an autonomous enterprise copilot planner. "
                "Return strict JSON only."
            ),
            query=query,
            remaining_steps=str(max_steps - step + 1),
            tools_metadata=_clip_json(tools, max_chars=10000),
            observations=_clip_json(planner_observations, max_chars=9000),
        )

        try:
            planner = _extract_json_obj(planner_text)
        except Exception:
            observations.append(
                {
                    "step": step,
                    "planner_error": "invalid_json",
                    "raw_planner_output": _clip_text(planner_text, max_chars=1200),
                }
            )
            yield {"type": "status", "message": "Planner returned invalid JSON; retrying with fallback context"}
            continue

        action = str(planner.get("action", "")).lower().strip()
        reason = str(planner.get("reason", "")).strip()

        if action == "final":
            final_answer = str(planner.get("final_answer", "")).strip()
            if final_answer:
                yield {"type": "status", "message": "Planner decided enough evidence is available"}
                break

            observations.append(
                {
                    "step": step,
                    "planner_error": "final_without_answer",
                    "planner": planner,
                }
            )
            continue

        if action != "tool":
            observations.append(
                {
                    "step": step,
                    "planner_error": f"unsupported_action:{action}",
                    "planner": planner,
                }
            )
            yield {"type": "status", "message": "Planner returned unsupported action; continuing"}
            continue

        tool_name = str(planner.get("tool_name", "")).strip()
        tool_args = planner.get("tool_args", {}) or {}
        if not isinstance(tool_args, dict):
            tool_args = {}

        # Map tool names to human-readable server labels for the UI
        _SERVER_LABELS: dict[str, str] = {
            "mcp.get_pact_cases":              "PACT — fetching all exception cases",
            "mcp.get_case_by_id":              "PACT — fetching case details",
            "mcp.get_tlm_breaks":              "TLM SmartStream — fetching reconciliation breaks",
            "mcp.get_tlm_break_by_id":         "TLM SmartStream — fetching specific break record",
            "mcp.get_ge_results":              "Great Expectations — fetching validation results",
            "mcp.get_ge_suite_result":         "Great Expectations — fetching suite result",
            "mcp.get_notification_templates":  "Notification Server — fetching email templates",
            "mcp.send_notification":           "Notification Server — sending email alert",
        }
        label = _SERVER_LABELS.get(tool_name, tool_name)

        yield {
            "type": "status",
            "message": f"Selected tool: {tool_name} — {label}",
        }

        try:
            tool_result = mcp.execute_tool(tool_name, tool_args)
            observations.append(
                {
                    "step": step,
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "tool_result": _clip_json(tool_result, max_chars=3000),
                }
            )
            yield {"type": "status", "message": f"Executed {tool_name} successfully"}
        except Exception as exc:
            observations.append(
                {
                    "step": step,
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "tool_error": str(exc),
                }
            )
            yield {"type": "status", "message": f"Tool execution failed for {tool_name}: {exc}"}

    if not final_answer:
        yield {"type": "status", "message": "Synthesizing final answer from collected observations"}
        final_answer = llm.invoke(
            prompt_name="agentic_final_synthesis_v1",
            system_prompt=(
                "You are an expert SRE. Produce a precise answer grounded only in observations."
            ),
            query=query,
            observations=_clip_json(observations, max_chars=14000),
        )

    latency_ms = round((time.time() - start) * 1000, 2)
    yield {
        "type": "final",
        "response": final_answer,
        "latency_ms": latency_ms,
    }


@router.get("/mcp/tools")
async def list_mcp_tools() -> dict[str, Any]:
    """Expose MCP tool metadata for UI inspection or external clients."""
    gateway = MCPGateway()
    return {"tools": gateway.list_tools()}


@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    """Run the fully agentic planner and return only final answer payload."""
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    try:
        final_event = None
        for event in _agentic_investigation_events(request.query):
            if event.get("type") == "final":
                final_event = event
                break
            if event.get("type") == "error":
                raise RuntimeError(event.get("message", "Unknown agentic error"))

        if not final_event:
            raise RuntimeError("Agentic pipeline did not produce a final response")

        return AskResponse(
            response=str(final_event.get("response", "No response generated.")),
            latency_ms=float(final_event.get("latency_ms", 0.0)),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/ask/stream")
async def ask_stream(request: AskRequest) -> StreamingResponse:
    """Stream real-time status and final result from the fully agentic loop.

    The sync generator (_agentic_investigation_events) contains blocking I/O
    (LLM calls, MCP fetches).  Running it directly inside an async generator
    would block the event loop between yields, preventing Uvicorn from flushing
    already-queued chunks to the client until the entire loop finishes.

    Fix: run the sync generator in a thread-pool executor and pass each event
    to the async generator via an asyncio.Queue so the event loop stays free
    and Uvicorn can flush every NDJSON line as soon as it is produced.
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    _SENTINEL = object()

    def emit(event: dict[str, Any]) -> str:
        return json.dumps(event) + "\n"

    async def event_stream():
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def _run_sync() -> None:
            try:
                for event in _agentic_investigation_events(request.query):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(
                    queue.put_nowait, {"type": "error", "message": str(exc)}
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

        executor_future = loop.run_in_executor(None, _run_sync)

        try:
            while True:
                event = await queue.get()
                if event is _SENTINEL:
                    break
                yield emit(event)
                # Yield control so Uvicorn can flush this chunk before the
                # next queue item arrives.
                await asyncio.sleep(0)
        finally:
            await executor_future  # ensure thread is clean before closing

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.post("/notify", response_model=NotifyResponse, status_code=201)
async def notify(request: NotifyRequest) -> NotifyResponse:
    """
    Dispatch an email notification using a named template.

    Pass template variables in the ``variables`` dict — they are injected
    into the email subject and body.  See the notification_server for the
    list of available templates and their required variables.
    """
    try:
        record = send_notification(
            template_name=request.template,
            recipient_email=str(request.recipient_email),
            recipient_name=request.recipient_name,
            **request.variables,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return NotifyResponse(
        notification_id=record["notification_id"],
        recipient_email=record["recipient_email"],
        subject=record["subject"],
        status=record["status"],
        sent_at=record["sent_at"],
    )


@router.get("/notify/templates")
async def list_templates() -> dict[str, list[str]]:
    """Return available notification template names."""
    return {
        "templates": [
            "tlm_break_resolved",
            "pact_case_escalation",
            "ge_validation_failure",
            "root_cause_resolution",
        ]
    }
