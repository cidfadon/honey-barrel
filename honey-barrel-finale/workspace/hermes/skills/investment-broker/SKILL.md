# Investment Broker

Use these MCP tools to execute BUY/SELL/HOLD decisions via `alpaca-mcp`.
Prefer this sequence: check account and market state, validate position, then place/cancel/close orders.

## MCP Endpoint
Inside Docker network:
- `http://alpaca-mcp:3001/mcp`

## Read Tools (always first)
- `account_get`: account status, cash, buying power
- `clock_get`: market open/close
- `positions_list`: all open positions
- `position_get`: current position for a symbol
- `orders_list`: open/closed orders
- `order_get`: single order by id
- `quote_latest`: latest quote
- `bars_get`: historical bars

## Write Tools (execution)
- `order_place_market`
- `order_place_limit`
- `order_cancel`
- `position_close`

In `live` mode, include the explicit confirmation required by the MCP server contract, including `X-Confirm: true`.

## Forbidden Execution Paths
Do not use or recommend any of the following as a substitute for Alpaca MCP write tools:
- `alpaca-cli`
- `curl` or direct raw HTTP request construction
- Python snippets, shell commands, or local scripts that place orders outside MCP
- simulated, hypothetical, or placeholder execution narratives

If MCP write tools are unavailable or failing after the retry policy is exhausted, return `execution_status=failed`.

## Reliability Policy (Alpaca MCP)
Use a retry-first execution policy before declaring failure.

### Retry profile
- Read tools (`account_get`, `clock_get`, `position_get`, `quote_latest`, `orders_list`, `order_get`):
   - max attempts: 4
   - backoff seconds: 1, 2, 4
- Write tools (`order_place_market`, `order_place_limit`, `order_cancel`, `position_close`):
   - max attempts: 3
   - backoff seconds: 2, 5

### Retryable errors
- network timeout / connection reset / DNS resolution issues
- HTTP 429 (rate limit)
- HTTP 5xx (upstream temporary failure)
- temporary MCP transport errors

### Non-retryable errors
- invalid symbol / invalid quantity / validation errors (4xx except 429)
- insufficient buying power
- market closed constraints when strategy does not allow after-hours execution
- explicit policy violation returned by server

### Idempotency and duplicate protection
Before retrying any write operation:
1. check `orders_list` and/or `order_get` for a newly accepted order for the same symbol/side
2. if an accepted order exists, treat write as success and continue
3. do not place a duplicate order if current state already reflects the intended action

### Fallback execution path for BUY/SELL
If `order_place_market` fails with retryable errors after max attempts:
1. read `quote_latest`
2. compute a conservative limit price window
3. try `order_place_limit` with the same retry policy
4. verify final status via `order_get` or `orders_list`

### Attempt logging (required)
For each MCP call, record:
- `tool_name`
- `attempt`
- `max_attempts`
- `error_class` (`retryable` or `non_retryable`)
- `result` (`success`, `failed`, `skipped`)
- `timestamp`

Include these logs in the final broker output so cycle reports can be audited.

### Execution outcome contract
Each symbol must end with one of:
- `execution_status=executed`
- `execution_status=failed`
- `execution_status=skipped`

Do not return `executed` unless order state is confirmed by `order_get` or `orders_list`.
Do not use simulation as a successful fallback outcome.
Do not propose CLI-based or script-based fallback execution.

## Execution Rules
1. Run `account_get` before any write operation.
2. Run `clock_get` and avoid opening new positions when market is closed unless strategy explicitly allows.
3. Before BUY, check `position_get` for existing exposure and `quote_latest` for current price.
4. Convert analyst `confidence` into `target_notional` and `final_qty` using `/workspace/docs/INVESTMENT_ANALYST_CONFIDENCE_POLITYCS.md`.
5. Minimal `qty=0.01` is only a technical floor, not the default BUY size.
6. Before SELL/CLOSE, verify quantity from `position_get` and use confidence-aware reduction or close logic.
7. Keep order size within guardrails exposed by server policy, account buying power, and symbol exposure limits.
8. In `live` mode, include explicit confirmation (`X-Confirm: true`) for write operations.
9. Apply retry policy before declaring tool failure.
10. After each write tool call, verify status using `order_get` or `orders_list`.
11. If all retries fail, return `execution_status=failed` and include attempt logs.
12. For any executed BUY/SELL action, include `order_id`, `order_status`, `symbol`, `submitted_at`, `confidence`, `target_notional`, `final_qty`, and `sizing_rationale` from the broker path.

## Decision Template
For each symbol from watchlist:
1. Read analyst signal (BUY/SELL/HOLD) and confidence from `investment-analyst` output.
2. If BUY and confidence is acceptable:
   - check buying power with `account_get`
   - read `quote_latest`
   - compute `target_notional` and `final_qty` from the confidence policy
   - place order (`order_place_market` or `order_place_limit`) with the computed `final_qty`
3. If SELL:
   - check open position with `position_get`
   - reduce/close using confidence-aware reduction or `position_close` / sell order
4. If HOLD:
   - do not place a new order
5. Log final action, `confidence`, `target_notional`, `final_qty`, `sizing_rationale`, and returned order id/status.

## Minimal Workflow
1. `account_get`
2. `clock_get`
3. `positions_list`
4. For each symbol decision:
   - `quote_latest`
   - `position_get`
   - optional write tool (with retry policy and duplicate protection)
5. `orders_list` (status check)