# alpaca-mcp

A small FastAPI service that re-exposes a curated subset of the Alpaca
Trading + Market Data v2 APIs (US equities) as **MCP tools** over HTTP
(JSON-RPC 2.0). Wire-compatible with `mcp-toolbox` and `workspace-mcp`,
so Hermes registers it the same way:

```bash
hermes mcp add alpaca --url http://alpaca-mcp:3001/mcp
```

## Tools

| Class | Tool                  | Notes |
|-------|-----------------------|-------|
| read  | `account_get`         | account status, cash, buying power |
| read  | `positions_list`      | all open positions |
| read  | `position_get`        | single symbol |
| read  | `orders_list`         | filterable by `status` (open/closed/all) |
| read  | `order_get`           | by id |
| read  | `clock_get`           | market open/close |
| read  | `quote_latest`        | NBBO latest quote |
| read  | `bars_get`            | historical bars (1Min..1Day) |
| write | `order_place_market`  | requires `X-Confirm: true` in live mode |
| write | `order_place_limit`   | requires `X-Confirm: true` in live mode |
| write | `order_cancel`        | requires `X-Confirm: true` in live mode |
| write | `position_close`      | requires `X-Confirm: true` in live mode |

## Guardrails

Applied server-side **before** any write call:

| Var                    | Default | Effect                                                  |
|------------------------|---------|---------------------------------------------------------|
| `MAX_ORDERS_PER_DAY`   | 5       | Reject when today's order count is already ≥ this value |
| `MAX_NOTIONAL_USD`     | 200     | Reject when est. notional > cap (uses latest quote)     |
| `AUTO_EXECUTE`         | false   | Surface flag for higher-level callers                   |
| `ALPACA_MODE`          | paper   | `paper` → paper-api.alpaca.markets, `live` → api.alpaca.markets |

In **live** mode every write tool also requires the HTTP header
`X-Confirm: true`. Hermes' MCP CLI sends this when you confirm the call
interactively; programmatic callers must set it explicitly.

## Endpoints

| Method | Path     | Purpose                                       |
|--------|----------|-----------------------------------------------|
| GET    | /health  | docker compose healthcheck                    |
| GET    | /mcp     | SSE keep-alive (some MCP clients open it)     |
| POST   | /mcp     | JSON-RPC 2.0 entrypoint                       |

## Smoke test (from inside the docker network)

```bash
# health
curl -fsS http://alpaca-mcp:3001/health | jq

# tools/list
curl -fsS -X POST http://alpaca-mcp:3001/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | jq

# account_get
curl -fsS -X POST http://alpaca-mcp:3001/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"account_get","arguments":{}}}' | jq
```
