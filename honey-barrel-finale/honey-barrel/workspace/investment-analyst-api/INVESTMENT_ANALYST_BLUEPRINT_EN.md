# INVESTMENT_ANALYST_BLUEPRINT.md

## 1. Purpose
This document defines the reference execution blueprint for the investment stack:
- investment-analyst (analysis)
- investment-broker (execution)
- investment-analysis-cycle (orchestration)

This blueprint is example-ready and can be used as a template for real runs.

## 2. Source Of Truth
Use this blueprint together with:
- /workspace/docs/DEFINITIVE_SKILLS_MANIFEST.md

If there is a conflict, MCP-only and success/failure rules from the manifest take precedence.

## 3. MCP-Only Rule
All analysis and execution actions must be done through MCP tools.

Allowed:
- analyst MCP tools for watchlist and analysis
- alpaca MCP tools for trading execution
- workspace MCP tools for report persistence and verification

Forbidden substitutes:
- curl/raw HTTP request construction
- alpaca-cli
- ad hoc Python/shell scripts for order placement
- simulation narrative presented as real execution

## 4. Roles And Boundaries

### 4.1 investment-analyst
Responsibility:
- manage watchlist
- produce BUY/SELL/HOLD signals with confidence and key metrics

Primary MCP toolset:
- watchlist_get, watchlist_add, watchlist_remove, watchlist_clear
- data_fetch, model_train, model_predict
- analyze_stock, analyze_watchlist

### 4.2 investment-broker
Responsibility:
- translate analyst signal into execution decision
- execute BUY/SELL through Alpaca MCP write tools
- verify order state and return auditable logs

Primary MCP toolset:
- Read: account_get, clock_get, positions_list, position_get, orders_list, order_get, quote_latest, bars_get
- Write: order_place_market, order_place_limit, order_cancel, position_close

### 4.3 investment-analysis-cycle
Responsibility:
- orchestrate end-to-end flow
- enforce hard success criteria
- build and persist final report

## 5. Inputs
Required:
- watchlist symbols, e.g. ["AAPL", "GOOGL", "AMZN", "NVDA", "MRVL", "SPCX"]

Optional:
- risk_mode: paper (default) or live
- buy_confidence_threshold: float in range [0,1]
- max_symbols_per_run: integer

## 6. Output Contract (Cycle)
The cycle returns a structured object with at least:
- status: success | failed
- run_id: string
- started_at: ISO timestamp
- completed_at: ISO timestamp
- execution_mode: paper | live
- watchlist_used: array[string]
- analyst_summary: object
- broker_summary: object
- orders_executed: array[object]
- report_write_verified: boolean
- failure_reasons: array[string]

Hard requirement for success:
- at least one confirmed Alpaca write success (order_place_market or order_place_limit)
- each executed order includes order_id, order_status, symbol, submitted_at
- report is persisted and verified as readable

## 7. Orchestration Flow

### Phase A: Intake And Validation
1. Validate input watchlist is non-empty.
2. Normalize symbols to uppercase.
3. Resolve risk mode and confidence threshold.

### Phase B: Analyst Phase
1. Call watchlist_get.
2. Sync watchlist using watchlist_add/watchlist_remove if requested.
3. Call analyze_watchlist.
4. Optionally call analyze_stock for symbols that need deeper justification.
5. Build analyst_summary and per-symbol signals.

### Phase C: Broker Phase
1. Read current account and market state using account_get and clock_get.
2. Read positions with positions_list.
3. For each symbol:
   - collect quote_latest and position_get
   - map signal to action BUY/SELL/HOLD
   - for BUY/SELL, execute write tool with retry policy
   - verify with order_get or orders_list
4. Collect attempt logs and per-symbol execution_status.

### Phase D: Report And Verification
1. Build JSON and/or Markdown report payload.
2. Write report into /workspace/reports.
3. Verify report existence and readability.
4. Return final status according to hard criteria.

## 8. Retry Policy (Reference)
Read calls:
- max_attempts: 4
- backoff: [1, 2, 4] seconds

Write calls:
- max_attempts: 3
- backoff: [2, 5] seconds

Retryable errors:
- transient network errors
- HTTP 429
- HTTP 5xx
- temporary MCP transport errors

Non-retryable errors:
- validation and bad input (4xx except 429)
- insufficient buying power
- policy violations returned by server

Before write retry, perform duplicate protection:
1. check orders_list/order_get for already accepted order
2. if found, treat as success
3. never place duplicate order for same intended action

## 9. Decision Logic (Reference)
For each symbol:
1. Read analyst action and confidence.
2. BUY path:
   - require confidence >= threshold
   - verify account buying power
   - place market order; if transient failure persists, try limit order fallback
3. SELL path:
   - verify existing position
   - close/reduce with position_close or sell order
4. HOLD path:
   - no new order

Recommended risk controls:
- max position size per symbol
- max daily number of new entries
- skip BUY when market is closed unless strategy explicitly allows it

## 10. Audit Logging Contract
Each MCP attempt should include:
- tool_name
- attempt
- max_attempts
- error_class: retryable | non_retryable
- result: success | failed | skipped
- timestamp

These logs must be included in broker_summary for post-run audits.

## 11. Report Schema (Example)

```json
{
  "status": "success",
  "run_id": "iac_20260709_120001",
  "started_at": "2026-07-09T12:00:01Z",
  "completed_at": "2026-07-09T12:01:40Z",
  "execution_mode": "paper",
  "watchlist_used": ["AAPL", "GOOGL", "AMZN", "NVDA", "MRVL", "SPCX"],
  "analyst_summary": {
    "total": 6,
    "buy": 2,
    "sell": 1,
    "hold": 3,
    "signals": [
      {"symbol": "AAPL", "action": "BUY", "confidence": 0.74},
      {"symbol": "GOOGL", "action": "HOLD", "confidence": 0.62}
    ]
  },
  "broker_summary": {
    "executed": 1,
    "failed": 0,
    "skipped": 5,
    "attempt_logs": [
      {
        "tool_name": "order_place_market",
        "attempt": 1,
        "max_attempts": 3,
        "error_class": "retryable",
        "result": "success",
        "timestamp": "2026-07-09T12:01:01Z"
      }
    ]
  },
  "orders_executed": [
    {
      "symbol": "AAPL",
      "order_id": "9f1f6d11-1111-4cbf-aaaa-222222222222",
      "order_status": "accepted",
      "submitted_at": "2026-07-09T12:01:01Z"
    }
  ],
  "report_write_verified": true,
  "failure_reasons": []
}
```

## 12. Failure Semantics
Cycle must return status=failed if any of these occur:
1. no access to required MCP tools
2. no successful write order after retry policy exhaustion
3. missing required order metadata for executed trade
4. report write cannot be verified
5. an attempt to substitute MCP with CLI/curl/script execution

Failure response should preserve partial context:
- analyst outputs (if available)
- broker attempt logs
- explicit failure_reasons

## 13. Prompt Template (Example)
Use this as a run template for the orchestration skill:

Run investment-analysis-cycle for watchlist: AAPL, GOOGL, AMZN, NVDA, MRVL, SPCX.
Use MCP-only execution path.
Apply analyst phase first, then broker phase with retry policy and duplicate protection.
Require at least one real Alpaca write success and include order_id, order_status, symbol, submitted_at.
Persist final report to /workspace/reports and verify readability.
If any hard success condition is not met, return status=failed with explicit reasons.

## 14. Minimal Smoke Checklist
1. Analyze all symbols via analyst MCP.
2. Execute broker decisions via Alpaca MCP.
3. Confirm at least one successful write order.
4. Verify required order metadata fields.
5. Write and verify report readability.
6. Return success only when all hard conditions are satisfied.
