# daily_investment_watchlist_report_generator.sh Guide.

## Purpose

`scripts/daily_investment_watchlist_report_generator.sh` is the orchestration wrapper for Honey-Barrel investment watchlist cycles.

Its responsibilities are:

- run one Hermes-driven investment analysis cycle for one watchlist symbol or a comma-separated symbol set,
- validate Hermes MCP readiness before execution,
- serialize or limit concurrent runs with slot-based file locks,
- capture run logs and persistent state,
- verify that a real Alpaca write happened when the cycle is expected to trade,
- fall back to direct Alpaca MCP execution when Hermes output is simulated, invalid, missing write evidence, or times out,
- write success or failure artifacts into `reports/`.

The script supports both manual execution (`--run-now`) and scheduled execution from `crontab`.

## Main Entry Points
Example:
```bash
scripts/daily_investment_watchlist_report_generator.sh --run-now
```

Supported options:

- `--run-now`: run one controlled cycle immediately.
- `--status`: print persisted state and crontab status.
- `--install-cron`: install one generic crontab entry for this job.
- `--remove-cron`: remove the generic crontab entry.
- `--print-cron-preset`: print the stable manual and cron preset.
- `--help`: print usage and environment overrides.

Important note:

- `--install-cron` installs a single generic line based on `DAILY_WATCHLIST_CRON_SCHEDULE`.
- The currently active production-like schedule in user crontab is a manually maintained set of staggered per-symbol entries, not the single generic line.
- Those active per-symbol cron entries use `RUN_TIMEOUT_SECONDS=1500` (25 minutes).

## Directory Layout And Artifacts

The script writes and reads from these locations:

- `reports/.cron_state/daily_investment_watchlist_report_generator.log`: aggregated master log.
- `reports/.cron_state/run_<cycle>.log`: per-cycle execution log.
- `reports/.cron_state/daily_investment_watchlist_report_generator.state`: persisted state.
- `reports/.cron_state/daily_investment_watchlist_report_generator.lock.d/`: slot-based parallel run lock files.
- `reports/investment_analysis_cycle_<timestamp>.json`: successful cycle artifact.
- `reports/investment_analysis_cycle_<timestamp>.md`: markdown mirror of the successful cycle.
- `reports/failed_watchlist_report_cycle_<cycle>.json`: failure artifact.
- `reports/<date>_latest_watchlist_report.json`: latest alias, updated on success and conditionally on failure.

## Core Execution Flow

At a high level, one cycle does the following:

1. Resolve runtime parameters and directories.
2. Acquire a parallel slot lock.
3. Check container/runtime prerequisites.
4. Check MCP reachability from the Hermes container.
5. Check Hermes MCP bootstrap health from `hermes mcp list`.
6. Read Alpaca order count before execution.
7. Run Hermes oneshot or, in direct-only mode, skip Hermes and call direct Alpaca fallback.
8. Validate output and detect invalid or simulated execution.
9. Recover through direct Alpaca fallback when enabled.
10. Verify report artifacts and latest order metadata.
11. Write success or failure JSON/Markdown artifacts.

## Locking And Concurrency

The script uses slot-based locking rather than a single global flock.

Key behavior:

- Lock files live in `reports/.cron_state/daily_investment_watchlist_report_generator.lock.d/`.
- Each acquired slot stores a corresponding `slot_<n>.pid` file.
- `MAX_PARAREL_CRONTASKS_RUN` controls how many runs may coexist.
- `LOCK_WAIT_SECONDS=0` means: do not wait, skip immediately if all slots are occupied.
- positive `LOCK_WAIT_SECONDS` means: wait until a slot frees up or exit with lock-timeout.

This mechanism is why stale or foreign processes can block manual tests even when the script itself is healthy.

## Current Script Defaults

As of the current workspace version, the script defaults are:

- `DAILY_WATCHLIST_CRON_SCHEDULE=*/30 * * * *`
- `LOCK_WAIT_SECONDS=120`
- `MAX_PARAREL_CRONTASKS_RUN=1`
- `WATCHLIST_TICKERS=AAPL`
- `BUY_CONFIDENCE_THRESHOLD=0.60`
- `SELL_CONFIDENCE_THRESHOLD=0.40`
- `BASE_NOTIONAL_PER_TRADE_USD=25`
- `MAX_NOTIONAL_PER_SYMBOL_USD=100`
- `MIN_TRADE_QTY=0.01`
- `QTY_STEP=0.01`
- `MCP_PREFLIGHT_RETRIES=3`
- `MCP_PREFLIGHT_RETRY_DELAY_SECONDS=5`
- `ORDERS_COUNT_RETRIES=3`
- `ORDERS_COUNT_RETRY_DELAY_SECONDS=2`
- `HERMES_HEALTH_WAIT_SECONDS=45`
- `HERMES_MCP_REQUIRED_COUNT=4`
- `HERMES_MCP_BOOTSTRAP_TIMEOUT_SECONDS=45`
- `HERMES_MCP_BOOTSTRAP_RETRIES=2`
- `HERMES_MCP_BOOTSTRAP_STRICT=false`
- `DISABLE_TERMINAL_MCP_FOR_RUN=false`
- `DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true`
- `DIRECT_ALPACA_ONLY_MODE=false`
- `ORDER_RETEST_ATTEMPTS=3`
- `ORDER_RETEST_DELAY_SECONDS=5`
- `TIMEOUT_RETEST_ATTEMPTS=0`
- `TIMEOUT_RETEST_DELAY_SECONDS=8`
- `HERMES_PERSISTENT_READY_WARMUP=false`
- `HERMES_PERSISTENT_READY_TIMEOUT_SECONDS=60`
- `MCP_UNREADY_RECOVERY_ATTEMPTS=1`
- `MCP_UNREADY_RECOVERY_DELAY_SECONDS=6`

Container defaults used by the wrapper:

- `HERMES_CONTAINER_NAME=hermes`
- `ALPACA_MCP_CONTAINER_NAME=alpaca-mcp`
- `ANALYST_MCP_CONTAINER_NAME=investment-analyst-api`
- `WORKSPACE_MCP_CONTAINER_NAME=workspace-mcp`
- `TOOLBOX_MCP_CONTAINER_NAME=mcp-toolbox`
- `TERMINAL_MCP_CONTAINER_NAME=stdio-terminal`

## Important Runtime Flags

### Hermes / MCP control

- `HERMES_MCP_REQUIRED_COUNT`: minimum number of enabled MCP servers required by bootstrap.
- `HERMES_MCP_BOOTSTRAP_STRICT`: when `true`, fail immediately if bootstrap threshold is not met.
- `DISABLE_TERMINAL_MCP_FOR_RUN`: removes terminal MCP from the effective runtime list for the run.
- `HERMES_PERSISTENT_READY_WARMUP`: optional warmup oneshot before the real cycle.

### Scheduling / control

- `LOCK_WAIT_SECONDS`: lock wait ceiling.
- `MAX_PARAREL_CRONTASKS_RUN`: slot count for concurrent runs.
- `RUN_TIMEOUT_SECONDS`: timeout for the Hermes oneshot in the main cycle.
- `TIMEOUT_RETEST_ATTEMPTS`: number of timeout retries after the first timeout.

### Trading and sizing

- `WATCHLIST_TICKERS`: symbol set for the cycle.
- `BUY_CONFIDENCE_THRESHOLD` and `SELL_CONFIDENCE_THRESHOLD`: decision thresholds.
- `BASE_NOTIONAL_PER_TRADE_USD`, `MAX_NOTIONAL_PER_SYMBOL_USD`, `MIN_TRADE_QTY`, `QTY_STEP`: sizing policy parameters.

### Recovery / fallback

- `DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE`: enables direct Alpaca recovery for invalid, simulated, missing-write, and timeout cases.
- `DIRECT_ALPACA_ONLY_MODE`: bypass Hermes oneshot entirely and execute only the direct Alpaca flow.
- `DIRECT_FALLBACK_ACTION_OVERRIDE`: force `buy`, `sell`, `hold`, or keep `auto`.
- `DIRECT_FALLBACK_CONFIDENCE_SCORE`: fallback confidence score when no model output is available.

## Hermes Bootstrap Behavior

The script checks Hermes readiness in two phases:

1. network preflight against the MCP endpoints from inside the Hermes container,
2. bootstrap verification by parsing `hermes mcp list` and counting enabled servers.

The bootstrap logic now:

- prefers the real count of enabled MCP servers from `hermes mcp list`,
- clamps the required threshold to the effective configured server count for the run,
- works correctly even before the run-level `effective_mcp_servers` variable is initialized.

## Direct Alpaca Fallback Behavior

Direct fallback is the emergency execution path used when Hermes output is unusable or the oneshot times out.

It performs the following steps:

1. choose a symbol and action,
2. fetch latest quote,
3. compute confidence-based sizing,
4. attempt a market order,
5. if buying power is insufficient, optionally adapt quantity down,
6. if needed, attempt a limit order,
7. write success artifacts directly from the fallback path.

Important implementation details:

- all Alpaca write calls include `X-Confirm: true`,
- success artifacts are written as `execution_mode: direct_alpaca_fallback`,
- if buying power is too low, the path can downgrade to `hold` rather than fail hard,
- in current script behavior, a Hermes oneshot timeout can trigger immediate direct fallback when `DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true`.

## Timeout Behavior

Current script behavior for oneshot timeout:

- Hermes oneshot is wrapped by `timeout --signal=TERM --kill-after=30 "$RUN_TIMEOUT_SECONDS" ...`.
- If exit code `124` is returned, the script first treats it as `timeout`.
- When `DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true`, it now attempts direct Alpaca recovery immediately.
- Only if direct fallback fails does the script continue through timeout failure handling.
- Default timeout retests are currently disabled: `TIMEOUT_RETEST_ATTEMPTS=0`.

This makes runtime more deterministic and prevents the same long oneshot from being repeated unnecessarily.

## Report Validation And Failure Modes

The wrapper is intentionally strict.

It can fail a run when:

- the Hermes oneshot exits non-zero,
- the run log is empty,
- no final response is produced,
- invalid execution markers are detected,
- simulated execution markers are detected,
- no real write evidence is found when one is expected,
- latest order state is invalid or report validation fails.

Failure artifacts are written to `reports/failed_watchlist_report_cycle_<cycle>.json`.

## Current Active Crontab Entries

The active user crontab observed during documentation differs from current script defaults.

Observed active schedule:

- `AAPL`: `0,30 * * * *`
- `GOOGL`: `5,35 * * * *`
- `AMZN`: `10,40 * * * *`
- `NVDA`: `15,45 * * * *`
- `MRVL`: `20,50 * * * *`
- `SPCX`: `25,55 * * * *`

Observed shared runtime flags in active crontab entries:

- `LOCK_WAIT_SECONDS=120`
- `MAX_PARAREL_CRONTASKS_RUN=3`
- `HERMES_MCP_BOOTSTRAP_STRICT=false`
- `DISABLE_TERMINAL_MCP_FOR_RUN=true`
- `HERMES_PERSISTENT_READY_WARMUP=false`
- `TIMEOUT_RETEST_ATTEMPTS=0`
- `RUN_TIMEOUT_SECONDS=1500` in the active cron entries and as the script default for manual runs unless overridden.
- `DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=false`
- `DIRECT_ALPACA_ONLY_MODE=false`

Important implication:

- the live crontab currently disables direct Alpaca recovery on Hermes skill failure or timeout,
- even though the script defaults now enable that recovery path.

In other words: manual runs and cron runs can behave differently unless the cron entries are updated to match the script defaults.

## Manual Commands Worth Keeping

Useful operational commands:

```bash
docker exec hermes sh -lc 'if command -v hermes >/dev/null 2>&1; then hermes mcp list | grep "enabled" | wc -l; else /opt/hermes/bin/hermes mcp list | grep "enabled" | wc -l; fi'
```

```bash
tail -100 /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/daily_investment_watchlist_report_generator.log | grep -E "X-Confirm|confirmation|order_id|error|success" | tail -50
```

```bash
for i in 1 2 3 4 5; do pid=$(cat /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/daily_investment_watchlist_report_generator.lock.d/slot_$i.pid 2>/dev/null); echo "Slot $i: PID=$pid - $(ps -p $pid -o state= 2>/dev/null || echo 'DEAD')"; done
```

```bash
tail -100 $(ls -t /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/run_*.log 2>/dev/null | head -1) && echo "---REPORTS---" && ls -lt /home/me/git-repo/honey-barrel-finale/workspace/reports/*.json 2>/dev/null | head -3
```

```bash
docker exec hermes sh -lc '/opt/hermes/bin/hermes --oneshot "List available MCP servers only."' | sed -n '1,40p'
```

## Practical Recommendations

- Treat the script defaults and active crontab overrides as two separate sources of truth.
- If you want deterministic scheduled behavior, sync crontab flags with script defaults intentionally.
- If Hermes oneshots are long-running or unstable, keep `TIMEOUT_RETEST_ATTEMPTS=0` and rely on direct Alpaca fallback.
- Use `DIRECT_ALPACA_ONLY_MODE=true` for tight debugging of the execution path without Hermes reasoning.
- Watch `run_<cycle>.log` first; check the master log second.

## Related Files

- `scripts/daily_investment_watchlist_report_generator.sh`
- `docs/INVESTMENT_ANALYST_CONFIDENCE_POLITYCS.md`
- `docs/INVESTMENT_ANALYST_BLUEPRINT.md`
- `reports/.cron_state/daily_investment_watchlist_report_generator.log`
- `reports/.cron_state/run_<cycle>.log`
