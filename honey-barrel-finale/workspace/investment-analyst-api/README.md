# Investment Analyst System

Investment Analyst is a FastAPI-based service that combines ML stock analysis with an operator-friendly web terminal and Alpaca trading integration.

It exposes three interfaces from one backend:

- REST API (`/api/*`) for direct integration.
- MCP endpoint (`/mcp`) for Hermes/OpenClaw agents (JSON-RPC 2.0).
- Web terminal (`/ui/`) for manual operation and monitoring.

## What The System Does

1. Fetches market data (Yahoo by default, with fallback behavior).
2. Builds features and runs ML prediction (`BUY`/`HOLD`/`SELL`).
3. Manages a watchlist and batch analysis workflows.
4. Integrates with `alpaca-mcp` for order execution and guardrails.
5. Serves a single-page terminal UI with trading controls.

## High-Level Architecture

```text
Web UI (/ui/)            Hermes/OpenClaw (/mcp)
       |                         |
       +----------- HTTP --------+
                       |
            Investment Analyst API (FastAPI)
            - data_fetcher.py (Yahoo + fallback/cache)
            - feature_engineering.py
            - ml_model.py (XGBoost / RF)
            - watchlist.py (SQLite)
            - api.py (REST + trading proxy + static UI)
            - mcp.py (MCP tools)
                       |
               alpaca-mcp (JSON-RPC + /health + /guardrails)
                       |
                    Alpaca account
```

## Core Capabilities

### Analysis Layer

- Historical OHLCV fetch with caching.
- Fundamental data enrichment.
- Technical indicators and feature engineering.
- Model training and inference per ticker.
- Batch analysis for the full watchlist.

### Trading Layer (via alpaca-mcp)

- Place market orders from UI/API (`BUY` and `SELL`).
- Runtime guardrail checks (`max_notional_usd`, `max_orders_per_day`).
- UI receives guardrail-derived `max BUY`/`max SELL` limits.
- `max SELL` is position-aware (limited by held shares from Alpaca positions).
- Guardrail update modes:
  - Runtime update.
  - Persist to `.env` + restart `alpaca-mcp` in one action.

### Web Terminal UX

- Health strip with API/data/model status.
- Watchlist, analyze-all, prediction detail panel, chart, fundamentals.
- Manual order quantity input with `-`, `+`, `MAX` controls.
- Disabled-state explanations (for blocked `BUY`).
- Trading limits menu (`SAVE + RESTART`).
- Retrain cycle counter + `RESET` and last update indicator under `AUTO-REFRESH`.
- Position visibility for selected symbol (how many shares are available to sell).

## API Surface

### Health and UI

- `GET /health`
- `GET /` (redirect to `/ui/`)
- `GET /ui/`

### Data and Models

- `GET /api/data/fetch?ticker=...`
- `GET /api/data/series?ticker=...&points=...`
- `POST /api/model/train`
- `POST /api/model/predict`
- `POST /api/analyze/stock`
- `POST /api/analyze/watchlist?force_retrain=true|false`

### Watchlist

- `GET /api/watchlist`
- `POST /api/watchlist/add`
- `DELETE /api/watchlist/remove?ticker=...`
- `DELETE /api/watchlist/clear`

### Trading and Guardrails

- `POST /api/trading/order`
- `GET /api/trading/guardrails?ticker=...`
- `POST /api/trading/guardrails`
- `POST /api/trading/guardrails/persist`

### MCP Endpoint

- `GET /mcp` (SSE keepalive)
- `POST /mcp` (JSON-RPC 2.0)

## Key Trading Payload Notes

`GET /api/trading/guardrails?ticker=XYZ` returns enriched fields used by the UI:

- `buy_max_qty`
- `sell_max_qty`
- `sell_max_qty_by_notional`
- `sell_max_qty_by_position`
- `position_qty`
- `buy_estimated_unit_price`
- `sell_estimated_unit_price`

This allows the UI to show both capital constraints and actual share availability.

## Configuration

Important environment variables include:

```bash
# API
API_HOST=0.0.0.0
API_PORT=8001
DEBUG=false

# Data / model
DEMO_MODE=false
MODEL_ALGORITHM=xgboost
LOOKBACK_DAYS=90
MIN_DATA_POINTS=30
YAHOO_CACHE_HOURS=24

# Trading integration
DOCKER_SOCKET_PATH=/var/run/docker.sock
STACK_ENV_FILE=/workspace/.env
ALPACA_MCP_CONTAINER_NAME=alpaca-mcp
```

`MAX_NOTIONAL_USD` is consumed by `alpaca-mcp` guardrails and can be updated through the UI.

## Running

### In Docker Compose (recommended)

From workspace root:

```bash
docker compose up -d --build
```

UI is exposed at:

```text
http://127.0.0.1:18001/ui/
```

### Local API development

```bash
pip install -r requirements.txt
python -m uvicorn api:app --reload --host 0.0.0.0 --port 8001
```

## Quick Checks

```bash
# API health
curl -fsS http://127.0.0.1:18001/health

# Watchlist
curl -X POST http://127.0.0.1:18001/api/watchlist/add \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL"}'

# Analyze one ticker
curl -X POST http://127.0.0.1:18001/api/analyze/stock \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","force_retrain":false}'

# Guardrails with ticker context (includes position-aware sell data)
curl -fsS "http://127.0.0.1:18001/api/trading/guardrails?ticker=AAPL"
```

## Troubleshooting

- If UI changes are not visible, rebuild the `investment-analyst-api` container.
- During restarts, temporary browser errors like `ERR_CONNECTION_RESET` are expected.
- If trading endpoints fail, verify `alpaca-mcp` health and service connectivity.
- If data source falls back, check `/health` fields:
  - `configured_data_source`
  - `data_source`
  - `last_fetch_error`

## Notes

- This project is for research/operations tooling, not financial advice.
- Keep guardrails enabled in all non-test environments.
