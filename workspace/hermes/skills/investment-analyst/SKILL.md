# Investment Analyst

Use Investment Analyst MCP tools for watchlist management and stock analysis.
Do not use Terminal, `curl`, raw HTTP calls, or ad hoc Python scripts for normal analyst operations.

## MCP Endpoint
Inside Docker network:
- `http://investment-analyst-api:8001/mcp`

## Allowed MCP Tools
- `watchlist_get`
- `watchlist_add`
- `watchlist_remove`
- `watchlist_clear`
- `data_fetch`
- `model_train`
- `model_predict`
- `analyze_stock`
- `analyze_watchlist`

## Required Operating Rules
1. Prefer MCP tools directly; do not emulate them through Terminal.
2. Use `watchlist_get` before modifying or analyzing the list.
3. Use `analyze_stock` when you need a full per-symbol recommendation with fundamentals.
4. Use `analyze_watchlist` for a full portfolio sweep and aggregate counts.
5. If an MCP tool fails, return the failure clearly; do not fall back to `curl` or manual endpoint construction.

## Watchlist Workflow
1. Read the current list with `watchlist_get`.
2. Add missing symbols with `watchlist_add`.
3. Remove stale symbols with `watchlist_remove` when requested.
4. Use `watchlist_clear` only when the task explicitly requires a full reset.

## Analysis Workflow
For a single symbol:
1. Optionally run `data_fetch` if you want to confirm data freshness.
2. Run `analyze_stock` with the ticker.
3. Extract `prediction`, `confidence`, probabilities, and fundamentals.

For a watchlist cycle:
1. Run `watchlist_get`.
2. Run `analyze_watchlist` for the full list.
3. If the caller needs symbol-level justification, follow with `analyze_stock` for the symbols that matter most.

## Output Contract
Return concise structured results containing:
- watchlist used
- per-symbol action (`BUY`, `SELL`, `HOLD`)
- confidence
- key supporting metrics or fundamentals when available
- any MCP tool failure that prevented completion

## Dashboard
The analyst dashboard is available at:
- host: `http://localhost:18001/ui/`
- Docker network: `http://investment-analyst-api:8001/ui/`