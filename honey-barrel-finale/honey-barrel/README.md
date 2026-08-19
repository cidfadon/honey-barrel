🧠 HONEY-BARREL STACK — Architektura komunikacji (HTTP + MCP + Event Flow)

0. Warstwa ogólna

System składa się z 4 głównych warstw:

[ UI Layer ]
    ├── OpenClaw UI (18789) *(disabled for now, fully working)
    └── Investment Analyst UI (18001/ui)

[ Orchestration Layer ]
    ├── Hermes (MCP Runtime + Docker Control + Workspace Access)

[ Service Layer ]
    ├── Investment Analyst API (ML + Data + UI backend)

[ External Layer ]
    └── Ollama (external host: ${OLLAMA_BASE_IP}:11434)


🔄 1. Główny flow request/response (OpenClaw → Hermes → tools)
Flow A: User prompt (agent execution)
User
  ↓
OpenClaw UI (18789)
  ↓ HTTP
OpenClaw Backend
  ↓ MCP / HTTP
Hermes Runtime (8642)
  ↓
MCP Router
  ↓
Tool / Skill Execution Layer
  ├── Investment Analyst API
  ├── Workspace filesystem
  ├── Docker exec
  └── External LLM (Ollama)


Szczegółowy request/response

1. OpenClaw → Hermes
POST /mcp/run
Host: hermes:8642
Content-Type: application/json

{
  "session_id": "...",
  "agent": "codex-home",
  "input": "analyze AAPL trend"
}


2. Hermes → tool routing

Hermes wykonuje:

parsing intent
selection of MCP tool
context injection (/workspace)
optional docker exec


3. Hermes → Investment Analyst API (HTTP tool call)
POST http://investment-analyst-api:8001/analyze

lub:

GET /ui/
GET /predict?symbol=AAPL


4. Investment Analyst → response
{
  "symbol": "AAPL",
  "prediction": "BUY",
  "confidence": 0.78,
  "model": "xgboost",
  "features": {
    "rsi": 62,
    "macd": 1.2
  }
}


5. Hermes → OpenClaw
{
  "result": "...",
  "source": "investment-analyst",
  "trace_id": "abc123"
}


6. OpenClaw → UI render
chat update
agent trace visualization
tool output rendering


⚙️ 2. Investment Analyst Flow (UI + API)
Flow B: User analytics session
User
  ↓
Investment Analyst UI (18001/ui)
  ↓
Backend API (FastAPI / Node / Python ML)
  ↓
Feature pipeline
  ↓
XGBoost model inference
  ↓
Yahoo Finance connector
  ↓
Cache layer (disk)
  ↓
Response JSON → UI
Data pipeline
Yahoo Finance
   ↓
OHLCV data fetch
   ↓
Cache (24h TTL)
   ↓
Feature engineering
   ↓
Model inference (XGBoost, 90d lookback)
   ↓
Prediction output


🤖 3. Ollama (external LLM layer)
Flow C: LLM inference
Hermes / OpenClaw
   ↓ HTTP
OLLAMA_BASE_IP:11434
   ↓
External Ollama Server (Windows host)
   ↓
Response (chat completion / embeddings)
   ↓
Hermes → agent context
Example request
POST http://${OLLAMA_BASE_IP}:11434/api/chat


📡 4. Event Flow (system internal)

Hermes pełni rolę runtime + event routera.

Event bus model
Agent Event
  ↓
Hermes Event Dispatcher
  ↓
┌─────────────────────────────┐
│ event types                │
├─────────────────────────────┤
│ tool_call                  │
│ workspace_read            │
│ docker_exec               │
│ model_inference           │
│ llm_request (ollama)      │
└─────────────────────────────┘
Event lifecycle
event.created
   ↓
event.routed
   ↓
event.executing
   ↓
event.completed
   ↓
event.returned_to_agent


🧩 5. Workspace integration layer
Shared volume model
Hermes  ─────┐
OpenClaw ────┼──> /workspace
Investment   ─┘
Analyst
Przykładowe operacje
/workspace/
  ├── sessions/
  ├── logs/
  ├── datasets/
  ├── models/
  └── scripts/

Hermes może:

czytać pliki
zapisywać artefakty
uruchamiać skrypty
persistować modele ML


🔐 6. Security / boundary model
Trust zones
ZONE 1: UI
- OpenClaw
- Investment UI

ZONE 2: Runtime
- Hermes (privileged, docker.sock)

ZONE 3: Data/ML
- Investment Analyst

ZONE 4: External
- Ollama host
- Yahoo Finance
Kluczowy punkt

Hermes = root-level execution layer

privileged: true
SYS_ADMIN
docker.sock

To oznacza:

pełna kontrola nad hostem przez agent runtime


🧭 7. End-to-end flow (najważniejszy diagram)
            ┌─────────────────────┐
            │     User / UI       │
            └─────────┬───────────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
┌───────▼────────┐        ┌─────────▼─────────┐
│  OpenClaw UI   │        │ Investment UI     │
│   :18789       │        │   :18001/ui       │
└───────┬────────┘        └─────────┬─────────┘
        │                           │
        └─────────────┬─────────────┘
                      │
              ┌───────▼────────┐
              │     Hermes     │
              │   :8642 MCP    │
              └───────┬────────┘
                      │
     ┌────────────────┼──────────────────┐
     │                │                  │
┌────▼─────┐   ┌──────▼────────┐  ┌─────▼─────┐
│Workspace │   │ Investment API │  │ Docker    │
│ FS       │   │ ML Engine     │  │ Runtime   │
└────┬─────┘   └──────┬────────┘  └─────┬─────┘
     │                │                 │
     └────────────┬───┴──────┬──────────┘
                  │          │
          ┌───────▼──────────▼───────┐
          │ External Services        │
          │ - Ollama (${IP}:11434)   │
          │ - Yahoo Finance          │
          └──────────────────────────┘


📌 8. Wnioski architektoniczne
System jest hybrydowym agent runtime + ML platform
Hermes jest centralnym execution kernel
OpenClaw i Investment Analyst to dwa niezależne UI
Ollama jest całkowicie zewnętrzna w tej obsadzie *(running on MS WINDOWS 11 Home)
Workspace jest shared mutable state

