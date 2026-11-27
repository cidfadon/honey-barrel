# Daily Watchlist Launcher - Error Map

Script: `scripts/daily_investment_watchlist_report_generator.sh`

This document maps:
- process exit codes returned by the script,
- `last_exit_code` values persisted in state/logs,
- retry/recovery behavior,
- quick diagnostics.

## 1. Process Exit Codes (shell return code)

The script returns different process-level exit codes depending on stage:

| Process exit code | Meaning | Typical trigger |
|---|---|---|
| `0` | Success or intentional skip | Normal completion, or lock skip in parallel-limit mode |
| `1` | Script-declared failure | Validation/runtime failure path with `last_exit_code=...` |
| `2` | Preconditions/config/runtime not ready | Missing commands, missing/running containers, MCP preflight/bootstrap failures |
| `3` | Lock wait timeout | Could not acquire parallel slot within `LOCK_WAIT_SECONDS` |
| `124` | `timeout` command elapsed | Hermes oneshot exceeded `RUN_TIMEOUT_SECONDS` |
| `143` | Process got SIGTERM (`128+15`) | Hermes oneshot terminated externally (restart/recreate/stop/TERM) |

Notes:
- `124` is produced by GNU `timeout` around Hermes oneshot.
- `143` is not the wrapper timeout path; it means termination signal reached the executed process.

## 2. `last_exit_code` Values Written by Script

The script persists `last_exit_code` in state and logs. These are semantic failure labels.

| `last_exit_code` | Meaning | Where it happens |
|---|---|---|
| `orders-before-check-failed` | Could not read Alpaca order count before run | pre-run guard |
| `hermes-mcp-unready` | Hermes or required MCP endpoints did not become ready | readiness gate |
| `timeout` | Hermes oneshot hit timeout and fallback did not recover | oneshot wrapper path |
| `empty-run-log` | Run log empty when output was expected | oneshot/output validation |
| `no-final-response` | Hermes output indicated no final response | output content guard |
| `invalid-execution-path` | Disallowed execution pattern matched log | execution integrity guard |
| `simulated-execution-detected` | Simulation/mock pattern detected in log | execution integrity guard |
| `missing-real-mcp-write-evidence` | No evidence of real write call or UUID order id | hard evidence gate |
| `orders-after-check-failed` | Could not read Alpaca order count after run | post-run guard |
| `no-new-order` | `orders_after <= orders_before` after retries | order delta requirement |
| `order-delta-not-verified` | Explicit final guard on order count growth failed | post-loop hard gate |
| `latest-order-check-failed` | Latest order metadata missing | metadata fetch guard |
| `order-id-format-invalid` | Latest order id is not UUID format | metadata validation |
| `latest-order-status-invalid` | Latest order status in forbidden set (`rejected`, `canceled`, `expired`, `suspended`, `stopped`) | order outcome validation |
| `missing-report` | JSON/MD reports not found after run | artifact existence check |
| `stale-report` | Latest reports are older than run start timestamp | artifact freshness check |
| `report-sizing-validation-failed:<reason>` | JSON report sizing metadata failed policy checks | report validation |
| `0` | Success | final success path |
| numeric value, e.g. `143` | raw non-zero command exit from oneshot branch | propagated when not mapped to another semantic label |

## 3. Non-Failure Skip States (important in logs)

These can look suspicious but are not always hard failures:

| Log marker | Behavior |
|---|---|
| `status=skipped reason=parallel-limit` | Script exits `0` immediately when lock wait is disabled for that mode |
| `status=skipped reason=lock-timeout` | Script exits `3` after waiting `LOCK_WAIT_SECONDS` |

## 4. Retry and Recovery Logic

The script can recover automatically in several cases:

- Timeout recovery:
  - If oneshot exits `124`, script may run direct Alpaca fallback when enabled.
  - If fallback succeeds, run can continue as success (`last_exit_code` set to `0`).
- Invalid/simulated output recovery:
  - If enabled, direct fallback write can convert failure path into recovery success.
- MCP unready recovery:
  - Script retries MCP readiness a configurable number of times before final failure.
- Order delta retries:
  - If no new order is observed, it retries until configured attempt cap.

Main controls:
- `RUN_TIMEOUT_SECONDS`
- `TIMEOUT_RETEST_ATTEMPTS`, `TIMEOUT_RETEST_DELAY_SECONDS`
- `MCP_UNREADY_RECOVERY_ATTEMPTS`, `MCP_UNREADY_RECOVERY_DELAY_SECONDS`
- `ORDER_RETEST_ATTEMPTS`, `ORDER_RETEST_DELAY_SECONDS`
- `DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE`
- `ALPACA_MIN_ORDER_NOTIONAL_USD` (minimum broker notional guardrail for BUY fallback)

## 5. Where to Read Evidence

- Aggregate timeline log:
  - `reports/.cron_state/daily_investment_watchlist_report_generator.log`
- Per-cycle detailed run log:
  - `reports/.cron_state/run_<cycle>.log`
- Persisted state:
  - `reports/.cron_state/daily_investment_watchlist_report_generator.state`

## 6. Quick Diagnostic Commands

Run from workspace root:

```bash
# Last failures with semantic exit reason
rg -n "status=failed exit_code=" reports/.cron_state/daily_investment_watchlist_report_generator.log

# Raw oneshot process exits (124 timeout, 143 SIGTERM, etc.)
rg -n "oneshot_exit_code=" reports/.cron_state/run_*.log

# Lock-related skips/timeouts
rg -n "status=skipped reason=(parallel-limit|lock-timeout)" reports/.cron_state/daily_investment_watchlist_report_generator.log

# Current persisted status
cat reports/.cron_state/daily_investment_watchlist_report_generator.state
```

## 7. Practical Interpretation Guide

- If you see many `124`:
  - Hermes oneshot runtime is exceeding `RUN_TIMEOUT_SECONDS`.
  - Tune timeout and/or reduce workload per run.

- If you see many `143`:
  - Process is being terminated (SIGTERM), often due to service restart/recreate/stop.
  - Correlate timestamps with `docker compose up/down/restart` and host automation.

- If you see `missing-real-mcp-write-evidence`:
  - Model output looked successful, but hard evidence of real write call/order UUID was absent.
  - Inspect run log around tool-call traces.

- If you see `stale-report` or `missing-report`:
  - Hermes run may have produced no fresh artifacts in `/workspace/reports`.
  - Validate mount permissions and report generation path.

## 8. Direct Fallback Reason Map (`direct_alpaca_fallback_result`)

When logs contain `direct_alpaca_fallback_result ...`, this is the fallback execution path summary.

Important:
- `success=true action=hold used_tool=none` means a controlled downgrade to `HOLD`.
- It does not mean a BUY/SELL order was placed.

Common `reason=` values:

| Reason | Meaning | Typical source text |
|---|---|---|
| `insufficient-buying-power` | BUY could not be executed due to lack of buying power; fallback downgraded to HOLD | `insufficient buying power`, `40310000`, `buying_power` |
| `below-min-order-notional` | BUY rejected because order notional was below broker minimum; fallback downgraded to HOLD | `cost basis must be >= minimal amount of order` |
| `buy-budget-exhausted` | BUY blocked by configured daily budget guardrail; fallback downgraded to HOLD | `max_buy_notional_exceeded`, `daily buy notional` |
| `budget-insufficient` | Pre-check already determined account budget too small to place compliant order | account cash / buying power checks |
| `hold-noop` | Strategy/fallback resolved directly to HOLD, no write expected | explicit HOLD path |
| `no-open-position` | SELL requested but no open position exists, so fallback downgraded to HOLD | positions check |
| `market-and-limit-failed` (with `success=false`) | Both market and limit attempts failed and no safe downgrade rule matched | broker/API/tool errors |

Quick grep:

```bash
rg -n "direct_alpaca_fallback_result" reports/.cron_state/run_*.log
```

Tuning note:
- If `below-min-order-notional` appears frequently, increase sizing inputs (`BASE_NOTIONAL_PER_TRADE_USD`, `MIN_TRADE_QTY`) or adjust `ALPACA_MIN_ORDER_NOTIONAL_USD` to match broker/account constraints.

## 9. Connectivity Checks (health_check_stack.sh)

Operational connectivity checks are available in:
- `scripts/health_check_stack.sh`

Relevant sections in summary output:

| Summary key | What it verifies | Typical success |
|---|---|---|
| `analyst-web` | From `hermes` container, HTTP reachability of `investment-analyst-api` Web GUI (`http://investment-analyst-api:8001/`, host mirror `http://localhost:18001`) | `HTTP 200/3xx @ localhost:18001` |
| `ollama-hermes` | From `hermes` container, curl to `http://OLLAMA_BASE_IP:11434/api/tags` | `HTTP 200 @ <OLLAMA_BASE_IP>:11434` |
| `enp0s8-net` | Host interface `enp0s8` IPv4 in the same `/24` subnet as `.env` `OLLAMA_BASE_IP` | `<ip> in <prefix>.x` |

Fast troubleshooting:

```bash
# Full short health snapshot
./scripts/health_check_stack.sh --short --max-hermes 15

# Direct backend probe used by Web GUI Ollama pill
curl -sS http://127.0.0.1:18001/api/stack/ollama-curl | sed -n '1,220p'

# Verify running env in investment-analyst-api container
docker compose exec -T investment-analyst-api sh -lc 'env | grep -E "^OLLAMA_BASE_(IP|URL)="'

# Verify hermes can reach Ollama endpoint directly
docker compose exec -T hermes sh -lc 'curl -sS --max-time 5 -o /dev/null -w "%{http_code}\n" "http://${OLLAMA_BASE_IP}:11434/api/tags"'
```

If `ollama-hermes` is `FAIL` but host curl works, recreate services to reload `.env` into container runtime:

```bash
docker compose up -d --force-recreate investment-analyst-api hermes
```
