# GenAI Ops Copilot Platform

An enterprise-grade, fully agentic AI platform for financial operations intelligence. The Copilot autonomously queries PACT case management, TLM SmartStream reconciliation, Great Expectations data quality, and a Notification server — then synthesises a structured **Issue / Root Cause Analysis / Resolution** report delivered in real time through a streaming React UI.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          React UI  (localhost:3000)                          │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  ChatBox                                                            │    │
│  │  ┌──────────────────────────────┐  ┌────────────────────────────┐  │    │
│  │  │  🔎 Investigation Trace      │  │  🔴 ISSUE                  │  │    │
│  │  │  (live step-by-step feed)    │  │  🔍 ROOT CAUSE ANALYSIS    │  │    │
│  │  │  📁 Querying PACT            │  │  ✅ RESOLUTION             │  │    │
│  │  │  📊 Querying TLM             │  │                            │  │    │
│  │  │  🧪 Querying GE              │  │  ⚡ latency_ms             │  │    │
│  │  │  📧 Querying Notifications   │  └────────────────────────────┘  │    │
│  │  └──────────────────────────────┘                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────┬───────────────────────────────────────────────┘
                               │  POST /ask/stream  (NDJSON)
                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend  (localhost:8000)                        │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Streaming Route  /ask/stream                                       │    │
│  │                                                                     │    │
│  │  Thread executor runs agentic loop off the event loop so Uvicorn   │    │
│  │  flushes each NDJSON line immediately via asyncio.Queue            │    │
│  └──────────────────────┬──────────────────────────────────────────────┘    │
│                         │                                                    │
│                         ▼                                                    │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Agentic Planning Loop  (_agentic_investigation_events)              │   │
│  │                                                                      │   │
│  │  ┌─────────────────┐    JSON     ┌──────────────────────────────┐   │   │
│  │  │  LLM Gateway    │◄──────────►│  tool_router_v1 prompt       │   │   │
│  │  │  (gpt-4o-mini)  │            │  Mandatory checklist:        │   │   │
│  │  └────────┬────────┘            │  1. PACT  2. TLM             │   │   │
│  │           │                     │  3. GE    4. Notifications   │   │   │
│  │           │ {"action":"tool",   └──────────────────────────────┘   │   │
│  │           │  "tool_name":...}                                       │   │
│  │           ▼                                                          │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │  MCP Gateway  — tool dispatcher                             │   │   │
│  │  │                                                             │   │   │
│  │  │  execute_tool(tool_name, args)                              │   │   │
│  │  │       │                                                     │   │   │
│  │  │       ├── mcp.get_case_by_id      ──►  PACT Server         │   │   │
│  │  │       ├── mcp.get_pact_cases      ──►  PACT Server         │   │   │
│  │  │       ├── mcp.get_tlm_breaks      ──►  TLM Server          │   │   │
│  │  │       ├── mcp.get_tlm_break_by_id ──►  TLM Server          │   │   │
│  │  │       ├── mcp.get_ge_results      ──►  GE Server           │   │   │
│  │  │       ├── mcp.get_ge_suite_result ──►  GE Server           │   │   │
│  │  │       ├── mcp.get_notification_templates ► Notif. Server   │   │   │
│  │  │       └── mcp.send_notification   ──►  Notif. Server       │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │           │                                                          │   │
│  │           │  observations[]  fed back into next planning step        │   │
│  │           ▼                                                          │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  LLM Gateway  — final synthesis                              │   │   │
│  │  │  agentic_final_synthesis_v1  or  tool_router_v1 final_answer │   │   │
│  │  │  → structured Issue / RCA / Resolution report                │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘

Additional REST Endpoints
  POST /ask              — synchronous (waits for full response)
  POST /notify           — send email via named template
  GET  /notify/templates — list available templates
  GET  /mcp/tools        — inspect registered MCP tool catalog
```

---

## Request Flow (step by step)

```
1.  User types query in React UI
2.  App.js  POST /ask/stream  with { query }
3.  FastAPI  starts async event_stream()
4.  Thread executor runs _agentic_investigation_events(query) off event loop
5.  Agentic loop:
      a. LLM receives: query + tool catalog metadata + prior observations
      b. LLM returns JSON: { "action": "tool", "tool_name": "mcp.get_case_by_id", "tool_args": {...} }
      c. MCPGateway.execute_tool() calls the correct MCP server function
      d. Result appended to observations[]
      e. Status event {"type":"status","message":"..."} pushed to asyncio.Queue
      f. Uvicorn flushes the NDJSON line → React receives it → live trace updates
      g. Steps a–f repeat until all 4 systems queried (mandatory checklist)
      h. LLM returns { "action": "final", "final_answer": "..." }
6.  Final event {"type":"final","response":"...","latency_ms":...} sent
7.  React attaches steps[] + response to message → renders Investigation Trace + report
```

---

## Components

### Frontend  (`frontend/`)

| File | Purpose |
|---|---|
| `src/App.js` | Root component. Manages `messages` and `activities` state. Reads NDJSON stream line-by-line, accumulates steps in a `useRef`, attaches them to the final message so the trace persists after loading ends. |
| `src/components/ChatBox.js` | Renders conversation history, live "Thinking…" activity list, and final `MessageBubble`. Contains `StepTimeline` (investigation trace) and `FormattedResponse` (Issue/RCA/Resolution sections with colour-coded borders). |
| `src/index.js` | React 18 `createRoot` entry point. |
| `public/index.html` | CRA HTML shell. |

---

### Backend  (`backend/app/`)

#### API Layer

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, CORS middleware (allows `localhost:3000`), mounts the API router. |
| `api/routes.py` | All HTTP endpoints. Contains `_agentic_investigation_events()` — the core sync generator that drives the planning loop and yields `status`/`final`/`error` event dicts. The `/ask/stream` endpoint wraps this in a thread executor + `asyncio.Queue` to keep the event loop unblocked. |
| `models/schemas.py` | Pydantic v2 models: `AskRequest`, `AskResponse`, `NotifyRequest` (with `EmailStr`), `NotifyResponse`. |

#### LLM Gateway  (`llm_gateway/`)

| File | Purpose |
|---|---|
| `gateway.py` | Single entry-point for all LLM calls. Orchestrates: render prompt → guardrail input → call provider → guardrail output → record telemetry. |
| `prompt_manager.py` | Versioned `string.Template` prompt registry. Key prompts: `tool_router_v1` (mandatory 4-system checklist + JSON planner output), `agentic_final_synthesis_v1` (narrative Issue/RCA/Resolution format). |
| `guardrails.py` | Input/output safety checks: max character limits (24 000 input, 8 000 output), PII pattern detection, blocked keyword filter. |
| `telemetry.py` | In-memory invocation log: prompt name, latency, token estimate, guardrail violations. |
| `providers/openai_provider.py` | Thin wrapper around the OpenAI Python SDK. Model: `gpt-4o-mini`. Reads `OPENAI_API_KEY` from environment. |

#### MCP Gateway  (`mcp/`)

| File | Purpose |
|---|---|
| `gateway.py` | Central registry and dispatcher. `MCPGateway` registers 4 servers and 8 tools. `list_tools()` exposes tool metadata to the LLM planner. `execute_tool(name, args)` routes each tool call to the correct server function. |
| `pact_server.py` | **PACT Case Management v3.1** mock. Returns 4 open exception cases including `PACT-2026-004421` (Settlement Fail AAPL, P1, $10,620,000 exposure). |
| `tlm_server.py` | **SmartStream TLM 7.4** mock. Returns 3 reconciliation breaks: unmatched UST trade, AAPL settlement fail (CRITICAL, SLA breached), EUR/USD nostro break. |
| `great_expectations_server.py` | **Great Expectations 0.18** mock. Returns 3 validation suite results with critical failures in `orders_fact` (null trade refs, schema drift) and `transactions_tlm` (stale timestamps). |
| `notification_server.py` | Email notification engine. Stores 4 templates: `tlm_break_resolved`, `pact_case_escalation`, `ge_validation_failure`, `root_cause_resolution`. `send_notification()` renders and dispatches them. |
| `data_quality_server.py` | Legacy generic DQ server (kept, not used by agentic flow). |
| `pipeline_server.py` | Legacy pipeline server (kept, not used by agentic flow). |
| `incident_server.py` | Legacy incident server (kept, not used by agentic flow). |

#### LangGraph Agents  (`agents/`)  — secondary flow

| File | Purpose |
|---|---|
| `graph.py` | LangGraph `StateGraph`. Nodes: `fetch → [tlm_agent, pact_agent, ge_agent, case_agent] → final_agent`. Used by the `/ask` synchronous endpoint as a fallback orchestration path. |
| `nodes.py` | Node functions for the graph. Each node calls the LLM Gateway with its domain-specific prompt. `case_agent_node` handles case-ID-specific investigations. |

---

## MCP Tool Catalog

| Tool | Server | Description |
|---|---|---|
| `mcp.get_pact_cases` | PACT | All open exception cases for today |
| `mcp.get_case_by_id` | PACT | Single case lookup by `case_id` |
| `mcp.get_tlm_breaks` | TLM | All reconciliation breaks |
| `mcp.get_tlm_break_by_id` | TLM | Single break lookup by `break_id` |
| `mcp.get_ge_results` | Great Expectations | Full checkpoint validation results |
| `mcp.get_ge_suite_result` | Great Expectations | Single suite result by `suite_name` |
| `mcp.get_notification_templates` | Notifications | List available email templates |
| `mcp.send_notification` | Notifications | Send email using a named template |

---

## Prompt Versions

| Prompt | Used by | Purpose |
|---|---|---|
| `tool_router_v1` | Agentic loop (every step) | LLM planning brain — selects next tool or returns final answer. Enforces mandatory 4-system checklist before `action=final`. |
| `agentic_final_synthesis_v1` | Agentic loop (step limit fallback) | Synthesises narrative Issue/RCA/Resolution from accumulated observations. |
| `tlm_analysis_v1` | LangGraph `tlm_agent_node` | Analyses TLM breaks for SLA status and remediation. |
| `pact_analysis_v1` | LangGraph `pact_agent_node` | Analyses PACT cases for investigation gaps and next actions. |
| `ge_analysis_v1` | LangGraph `ge_agent_node` | Analyses GE failures for upstream cause and downstream impact. |
| `case_resolution_v1` | LangGraph `case_agent_node` | Deep-dives a single case using cross-system evidence. |
| `root_cause_analysis_v1` | LangGraph `final_agent_node` | Combines TLM + PACT + GE analysis into a single RCA. |

---

## Output Format

Every copilot response is structured into three sections:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 ISSUE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Case ID, type, priority, financial exposure ($USD), affected trade/instrument

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 ROOT CAUSE ANALYSIS (RCA)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Narrative prose grounded in PACT + TLM + GE cross-system evidence.
Written as a post-incident report by a senior SRE.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ RESOLUTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Numbered action steps — Owner | Deadline
Closure Criteria: ...
Recommended Notification: <template> to <team>
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, vanilla CSS-in-JS |
| Backend | Python 3.11, FastAPI, Uvicorn |
| Streaming | `StreamingResponse` + `asyncio.Queue` + thread executor (NDJSON) |
| Orchestration | LangGraph `StateGraph` (secondary), custom agentic loop (primary) |
| LLM | OpenAI `gpt-4o-mini` via `openai` Python SDK |
| Prompt management | Versioned `string.Template` registry (`PromptManager`) |
| MCP servers | Pure Python in-memory mock servers |
| Validation | Pydantic v2 |
| Config | `python-dotenv` → `.env` |

---

## Project Structure

```
genai-ops-copilot/
├── backend/
│   ├── .env                              # OPENAI_API_KEY (git-ignored)
│   ├── requirements.txt
│   └── app/
│       ├── main.py                       # FastAPI app + CORS
│       ├── api/
│       │   └── routes.py                 # /ask  /ask/stream  /notify  /mcp/tools
│       ├── models/
│       │   └── schemas.py                # Pydantic request/response models
│       ├── agents/
│       │   ├── graph.py                  # LangGraph StateGraph
│       │   └── nodes.py                  # LangGraph node functions
│       ├── llm_gateway/
│       │   ├── gateway.py                # LLMGateway — single LLM call surface
│       │   ├── prompt_manager.py         # Versioned prompt registry
│       │   ├── guardrails.py             # Input/output safety checks
│       │   ├── telemetry.py              # In-memory invocation telemetry
│       │   └── providers/
│       │       └── openai_provider.py    # OpenAI SDK wrapper
│       └── mcp/
│           ├── gateway.py                # MCPGateway — tool registry + dispatcher
│           ├── pact_server.py            # PACT Case Management mock
│           ├── tlm_server.py             # SmartStream TLM mock
│           ├── great_expectations_server.py  # GE validation mock
│           └── notification_server.py    # Email notification engine
└── frontend/
    ├── public/
    │   └── index.html
    └── src/
        ├── index.js                      # React 18 entry point
        ├── App.js                        # State management + NDJSON stream reader
        └── components/
            └── ChatBox.js                # Chat UI + StepTimeline + FormattedResponse
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- OpenAI API key

### Backend
```bash
cd backend
pip install -r requirements.txt
# Create .env with your key:
echo "OPENAI_API_KEY=sk-proj-..." > .env
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm start          # opens http://localhost:3000
```

### Example queries
```
investigate case PACT-2026-004421
What is the root cause of today's settlement failures?
Are there any SLA breaches in TLM?
Show me all open PACT cases
What data quality issues did Great Expectations find today?
```

---

## Sample Output

```
🔎 Investigation trace
📁 Querying PACT — case details
✅ PACT case details received
📊 Querying TLM SmartStream — reconciliation breaks
✅ TLM breaks received
🧪 Querying Great Expectations — validation results
✅ GE validation results received
📧 Querying Notification Server — email templates
✅ Notification templates received
💡 Enough evidence collected — generating answer

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 ISSUE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PACT-2026-004421 | Settlement Exception | P1 | $10,620,000 | TRD-2026050498712

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 ROOT CAUSE ANALYSIS (RCA)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The settlement failure originated from a client short position in AAPL where
the automated securities lending mechanism was fully exhausted prior to the
settlement deadline...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ RESOLUTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Follow up with prime brokers — ops-settlements-team | 2026-05-06 10:00 UTC
2. Resolve GE data quality failures — data-quality-team | 2026-05-07 17:00 UTC
Closure Criteria: Borrow secured, settlement confirmed, data issues resolved.
Recommended Notification: ge_validation_failure → data-quality-team
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Copilot UI (React)                           │
│                   http://localhost:3000                              │
└────────────────────────────┬────────────────────────────────────────┘
                             │  POST /ask
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                                  │
│                   http://localhost:8000                              │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                  LangGraph Agent Graph                        │  │
│  │                                                              │  │
│  │   START ──► fetch ──┬──► dq_agent ──────┐                   │  │
│  │                     └──► pipeline_agent ─┴──► final_agent ──►END│
│  └──────────────────────────────────────────────────────────────┘  │
│           │                                       │                 │
│           ▼                                       ▼                 │
│  ┌─────────────────┐                   ┌──────────────────────┐    │
│  │   MCP Gateway   │                   │     LLM Gateway      │    │
│  │                 │                   │                      │    │
│  │ • DQ Server     │                   │ • Prompt Manager     │    │
│  │ • Pipeline Srv  │                   │ • Guardrails         │    │
│  │ • Incident Srv  │                   │ • Telemetry          │    │
│  └─────────────────┘                   │ • OpenAI Provider    │    │
│                                        └──────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
genai-ops-copilot/
│
├── backend/
│   ├── app/
│   │   ├── main.py                          # FastAPI app & CORS
│   │   ├── api/routes.py                    # POST /ask endpoint
│   │   ├── models/schemas.py                # Pydantic request/response models
│   │   ├── agents/
│   │   │   ├── graph.py                     # LangGraph StateGraph definition
│   │   │   └── nodes.py                     # Fetch, DQ, Pipeline, Final nodes
│   │   ├── mcp/
│   │   │   ├── gateway.py                   # MCPGateway aggregator
│   │   │   ├── data_quality_server.py       # Mock DQ data source
│   │   │   ├── pipeline_server.py           # Mock pipeline data source
│   │   │   └── incident_server.py           # Mock incident data source
│   │   └── llm_gateway/
│   │       ├── gateway.py                   # LLMGateway orchestrator
│   │       ├── prompt_manager.py            # Versioned prompt templates
│   │       ├── guardrails.py                # Input validation & output scrubbing
│   │       ├── telemetry.py                 # Token usage & latency logging
│   │       └── providers/
│   │           └── openai_provider.py       # OpenAI chat completions client
│   │
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── App.js                           # Root component & fetch logic
│   │   └── components/ChatBox.js            # Chat history + input form
│   └── package.json
│
└── README.md
```

---

## Setup

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |

---

### 1. Clone the repository

```bash
git clone <repo-url>
cd genai-ops-copilot
```

### 2. Backend setup

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### 3. Frontend setup

```bash
cd ../frontend
npm install
```

---

## Running the Application

### Start the backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

### Start the frontend

```bash
cd frontend
npm start
```

The UI will be available at `http://localhost:3000`.

---

## Example API Request

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "Why did the orders pipeline fail this morning?"}'
```

**Example response:**

```json
{
  "response": "**Root Cause:** The orders_ingestion_daily pipeline failed due to a SourceConnectionTimeout on the extract_orders_raw task, causing 34.2% null values in orders_fact and blocking downstream revenue aggregation.\n\n**Impact:** Revenue dashboard shows stale data; two P1/P2 incidents open.\n\n**Recommended Fix:**\n1. Investigate source DB connectivity...\n\n**Estimated Recovery Time:** 2–4 hours",
  "latency_ms": 3241.5
}
```

---

## Key Design Decisions

| Concern | Approach |
|---------|----------|
| **Security** | API keys via env vars only; guardrails block prompt injection |
| **Observability** | Structured telemetry logs per LLM call (tokens, latency) |
| **Extensibility** | Register new MCP servers or LLM providers without touching agent code |
| **Separation of concerns** | Gateway, agents, MCP, and API layers are fully decoupled |
| **Parallelism** | DQ and pipeline agents run in parallel LangGraph branches |
