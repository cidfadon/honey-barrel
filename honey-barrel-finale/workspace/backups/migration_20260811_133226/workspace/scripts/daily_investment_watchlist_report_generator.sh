#!/usr/bin/env bash
#
## So, lets call it "Investment Watchlist Report Generator" for now. This script is intended to be run as a cron job, 
## and will generate a daily investment watchlist report using the hermes agent. It will also ensure that only one 
## instance of the script is running at a time, and will log the output of each run to a log file.
##
## For Polish Team members :) A mowiac po naszemu, jest to wrapper uruchomiany z crona, który uruchamia hermesa w trybie oneshot z odpowiednim 
## promptem, egzekwuje prompt kupujac/sprzedajac/hold uzywajac odpowiednich SKILL-ow Hermesa, a następnie sprawdza, 
## czy nie bylo bledow ani halucynacji, oraz czy raport został wygenerowany poprawnie.
##
## A ponizej wiecej info jak komus przyjdzie do glowy to czytac dalej.. 
## (c) 2026 Honey Barrel Labs
##
## The script will also check the Alpaca orders before and after the run, and will ensure that at least one new order
## was placed during the run. If no new order was placed, the script will consider the run a failure, and will log 
## the output of the run to a log file. The script will also check the status of the latest order, and will consider 
## the run a failure if the latest order was rejected, canceled, expired, suspended, or stopped. The script will also 
## check the exit code of the hermes command, and will consider the run a failure if the exit code is non-zero 
## or if the run log is empty. The script will also check for invalid execution paths, and will consider the run a
## failure if any invalid execution paths are detected. The script will also check for simulated execution, and will
## consider the run a failure if any simulated execution is detected. The script will also check for
## any missing reports, and will consider the run a failure if any expected report is missing.
##
## More logic here: docs/INVESTMENT_ANALYST_CONFIDENCE_POLITYCS.md docs/INVESTMENT_ANALYST_PROCESS_OVERVIEW.md
##                  docs/INVESTMENT_ANALYST_BLUEPRINT.md 
##
## Thanks to Kuba for inspiration and guidance :)
##
## eg. Jak używać manual mode:
##
## - Wyswietl help:
##   daily_investment_watchlist_report_generator.sh --help
## - Domyślnie:
##   daily_investment_watchlist_report_generator.sh --run-now
## - Z krótszym czekaniem na lock:
##   LOCK_WAIT_SECONDS=300 daily_investment_watchlist_report_generator.sh --run-now
## - Z custom timeoutem cyklu:
##   LOCK_WAIT_SECONDS=300 RUN_TIMEOUT_SECONDS=3500 daily_investment_watchlist_report_generator.sh --run-now
##

set -euo pipefail

##
## ALL variables and parameters are/can be defined in .env file, which is loaded by the wrapper script.
## See .env for details.
##
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"                        # Absolute path to the directory containing this script.
ROOT="$(cd "$HERE/.." && pwd)"                                              # Absolute path to the root of the project.
STACK_ENV_FILE="${STACK_ENV_FILE:-$ROOT/.env}"                               # Optional path to stack-level .env file.

load_env_default() {
  local key="$1" line value

  # Preserve explicit cron or shell overrides.
  if [[ -n "${!key:-}" ]]; then
    return 0
  fi

  [[ -r "$STACK_ENV_FILE" ]] || return 0

  line="$(grep -E "^[[:space:]]*${key}=" "$STACK_ENV_FILE" | tail -n 1 || true)"
  [[ -n "$line" ]] || return 0

  value="${line#*=}"
  value="$(printf '%s' "$value" | sed -E 's/[[:space:]]+#.*$//' | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
  [[ -n "$value" ]] || return 0

  printf -v "$key" '%s' "$value"
  export "$key"
}

# Keep Hermes prompt sizing aligned with .env when cron line does not export these vars.
for _env_key in \
  BUY_CONFIDENCE_THRESHOLD \
  SELL_CONFIDENCE_THRESHOLD \
  BASE_NOTIONAL_PER_TRADE_USD \
  MAX_NOTIONAL_PER_SYMBOL_USD \
  ALPACA_MIN_ORDER_NOTIONAL_USD \
  MIN_TRADE_QTY \
  QTY_STEP; do
  load_env_default "$_env_key"
done
unset _env_key

REPORTS_DIR="$ROOT/reports"                                                 # Absolute path to the reports directory.
STATE_DIR="$REPORTS_DIR/.cron_state"                                        # Absolute path to the state directory.
STATE_FILE="$STATE_DIR/daily_investment_watchlist_report_generator.state"
LOG_FILE="$STATE_DIR/daily_investment_watchlist_report_generator.log"
LOCK_FILE="$STATE_DIR/daily_investment_watchlist_report_generator.lock"
LOCK_PID_FILE="$STATE_DIR/daily_investment_watchlist_report_generator.lock.pid"
LOCK_SLOTS_DIR="$STATE_DIR/daily_investment_watchlist_report_generator.lock.d"
JOB_NAME="Daily Investment Watchlist Report Generator"
SCHEDULE="${DAILY_WATCHLIST_CRON_SCHEDULE:-*/30 * * * *}"                   # Default cron schedule for the job (every 30 minutes).
HERMES_CONTAINER="${HERMES_CONTAINER_NAME:-hermes}"                         # Default container name for the Hermes agent.
ALPACA_MCP_CONTAINER="${ALPACA_MCP_CONTAINER_NAME:-alpaca-mcp}"             # Default container name for the Alpaca MCP service.
SCRIPT_PATH="$ROOT/scripts/daily_investment_watchlist_report_generator.sh" 
RUN_MODE="cron"
LOCK_WAIT_SECONDS="${LOCK_WAIT_SECONDS:-180}"                               # Default wait time for acquiring the lock before failing the run (in seconds).
MAX_PARAREL_CRONTASKS_RUN="${MAX_PARAREL_CRONTASKS_RUN:-15}"                 # Maximum number of parallel cron tasks allowed to run at the same time (to avoid overloading the system).
WATCHLIST_TICKERS="${WATCHLIST_TICKERS:-}"                              # Default watchlist tickers to use for the investment analysis cycle. Comma-separated list of stock symbols.
BUY_CONFIDENCE_THRESHOLD="${BUY_CONFIDENCE_THRESHOLD:-0.65}"                # Minimum confidence required before BUY execution is allowed.
SELL_CONFIDENCE_THRESHOLD="${SELL_CONFIDENCE_THRESHOLD:-0.65}"              # Maximum confidence threshold for SELL execution in fallback mode.
BASE_NOTIONAL_PER_TRADE_USD="${BASE_NOTIONAL_PER_TRADE_USD:-5.0}"           # Base trade notional used by the confidence sizing policy.
MAX_NOTIONAL_PER_SYMBOL_USD="${MAX_NOTIONAL_PER_SYMBOL_USD:-40}"           # Maximum per-symbol trade notional allowed by the confidence sizing policy.
MIN_TRADE_QTY="${MIN_TRADE_QTY:-0.05}"                                      # Minimum tradeable quantity after sizing.
QTY_STEP="${QTY_STEP:-0.01}"                                                # Quantity floor step applied after raw sizing.
ALPACA_MIN_ORDER_NOTIONAL_USD="${ALPACA_MIN_ORDER_NOTIONAL_USD:-1.10}"     # Minimum order notional required by broker.
DIRECT_FALLBACK_ACTION_OVERRIDE="${DIRECT_FALLBACK_ACTION_OVERRIDE:-auto}"  # Force direct fallback action: auto|buy|sell|hold.
DIRECT_FALLBACK_CONFIDENCE_SCORE="${DIRECT_FALLBACK_CONFIDENCE_SCORE:-$BUY_CONFIDENCE_THRESHOLD}" # Confidence score used by direct fallback when model output is unavailable.
MCP_PREFLIGHT_RETRIES="${MCP_PREFLIGHT_RETRIES:-3}"                         # Number of retries for MCP preflight checks before failing the run.
MCP_PREFLIGHT_RETRY_DELAY_SECONDS="${MCP_PREFLIGHT_RETRY_DELAY_SECONDS:-5}" # Delay between retries for MCP preflight checks before failing the run.
ORDERS_COUNT_RETRIES="${ORDERS_COUNT_RETRIES:-3}"                         # Number of retries for Alpaca orders count reads before failing the run.
ORDERS_COUNT_RETRY_DELAY_SECONDS="${ORDERS_COUNT_RETRY_DELAY_SECONDS:-5}" # Delay between Alpaca orders count retries.
HERMES_HEALTH_WAIT_SECONDS="${HERMES_HEALTH_WAIT_SECONDS:-45}"              # Time to wait for Hermes container to become healthy before failing the run.
HERMES_MCP_REQUIRED_COUNT="${HERMES_MCP_REQUIRED_COUNT:-4}"                 # Number of MCP servers required to be healthy before proceeding with the run.
HERMES_MCP_BOOTSTRAP_TIMEOUT_SECONDS="${HERMES_MCP_BOOTSTRAP_TIMEOUT_SECONDS:-45}" # Timeout for Hermes MCP bootstrap process.
HERMES_MCP_BOOTSTRAP_RETRIES="${HERMES_MCP_BOOTSTRAP_RETRIES:-2}"                  # Number of retries for Hermes MCP bootstrap process.
HERMES_MCP_BOOTSTRAP_STRICT="${HERMES_MCP_BOOTSTRAP_STRICT:-false}"                # Whether to enforce strict checks during Hermes MCP bootstrap.
DISABLE_TERMINAL_MCP_FOR_RUN="${DISABLE_TERMINAL_MCP_FOR_RUN:-false}"       # Whether to disable the terminal MCP server for this run (useful for testing and avoiding conflicts).
DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE="${DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE:-true}" # If true, execute direct Alpaca MCP write calls when skill output is simulated or lacks write evidence.
DIRECT_ALPACA_ONLY_MODE="${DIRECT_ALPACA_ONLY_MODE:-false}"                 # If true, skip Hermes oneshot and execute direct Alpaca MCP write flow only.
ORDER_RETEST_ATTEMPTS="${ORDER_RETEST_ATTEMPTS:-3}"                         # Number of attempts to retest failed orders.
ORDER_RETEST_DELAY_SECONDS="${ORDER_RETEST_DELAY_SECONDS:-5}"               # Delay between order retest attempts.
TIMEOUT_RETEST_ATTEMPTS="${TIMEOUT_RETEST_ATTEMPTS:-0}"                     # Number of attempts to retest timed-out operations.
TIMEOUT_RETEST_DELAY_SECONDS="${TIMEOUT_RETEST_DELAY_SECONDS:-8}"           # Delay between timeout retest attempts.
HERMES_PERSISTENT_READY_WARMUP="${HERMES_PERSISTENT_READY_WARMUP:-false}"   # Whether to prewarm Hermes MCP session before the real oneshot run.
HERMES_PERSISTENT_READY_TIMEOUT_SECONDS="${HERMES_PERSISTENT_READY_TIMEOUT_SECONDS:-60}"  # Timeout for Hermes prewarm run.
MCP_UNREADY_RECOVERY_ATTEMPTS="${MCP_UNREADY_RECOVERY_ATTEMPTS:-1}"               # Number of attempts to recover from unready MCP state.
MCP_UNREADY_RECOVERY_DELAY_SECONDS="${MCP_UNREADY_RECOVERY_DELAY_SECONDS:-6}"     # Delay between MCP unready recovery attempts.    
ANALYST_MCP_CONTAINER="${ANALYST_MCP_CONTAINER_NAME:-investment-analyst-api}"     # Default container name for the Investment Analyst MCP service.
WORKSPACE_MCP_CONTAINER="${WORKSPACE_MCP_CONTAINER_NAME:-workspace-mcp}"          # Default container name for the Workspace MCP service.
TOOLBOX_MCP_CONTAINER="${TOOLBOX_MCP_CONTAINER_NAME:-mcp-toolbox}"                # Default container name for the Toolbox MCP service.
TERMINAL_MCP_CONTAINER="${TERMINAL_MCP_CONTAINER_NAME:-stdio-terminal}"           # Default container name for the Terminal MCP service.
##
## Default PROMPT for running the investment analysis cycle.
##
## BACKUP-PROMPT="Use only MCP tools. Do not run any skill. Do not use narrative mode. Task for watchlist ${WATCHLIST_TICKERS}: 1) Call alpaca clock_get and quote_latest. 2) Compute confidence-based sizing using /workspace/docs/INVESTMENT_ANALYST_CONFIDENCE_POLITYCS.md with: buy_confidence_threshold=${BUY_CONFIDENCE_THRESHOLD}, base_notional_per_trade=${BASE_NOTIONAL_PER_TRADE_USD}, max_notional_per_symbol=${MAX_NOTIONAL_PER_SYMBOL_USD}, min_trade_qty=${MIN_TRADE_QTY}, qty_step=${QTY_STEP}. Use target_notional = min(base_notional_per_trade + max(0, confidence - buy_confidence_threshold) * 100, max_notional_per_symbol). Use final_qty = max(min_trade_qty, floor((target_notional / current_price) / qty_step) * qty_step). 3) Execute one real Alpaca write order now via order_place_market or order_place_limit using that final_qty. 4) Verify the order via alpaca read call. 5) Return compact JSON only with: order_id, order_status, symbol, submitted_at, current_price, final_qty, target_notional, confidence, sizing_rationale. If direct tool name is unavailable, call tools/list and use the exposed alias that ends with order_place_market or order_place_limit. If no real write is executed because X-Confirm confirmation is missing, set sizing_rationale exactly to: Order placement failed due to missing Alpaca confirmation credentials (X-Confirm: true). Required trade size calculated as a Market Order."
##
PROMPT="Use only MCP tools. Do not use narrative mode and don't ask for update. Run investment-analysis-cycle skill as an orchiestrator for task from watchlist ${WATCHLIST_TICKERS}: 1) Call alpaca clock_get and quote_latest. 2) Compute confidence-based sizing using /workspace/docs/INVESTMENT_ANALYST_CONFIDENCE_POLITYCS.md with: buy_confidence_threshold=${BUY_CONFIDENCE_THRESHOLD}, base_notional_per_trade=${BASE_NOTIONAL_PER_TRADE_USD}, max_notional_per_symbol=${MAX_NOTIONAL_PER_SYMBOL_USD}, min_trade_qty=${MIN_TRADE_QTY}, qty_step=${QTY_STEP}. Use target_notional = min(base_notional_per_trade + max(0, confidence - buy_confidence_threshold) * 100, max_notional_per_symbol). Use final_qty = max(min_trade_qty, floor((target_notional / current_price) / qty_step) * qty_step). 3) Execute one real Alpaca write order now via order_place_market or order_place_limit using that final_qty. 4) Verify the order via alpaca read call. 5) Return compact JSON only with: order_id, order_status, symbol, submitted_at, current_price, final_qty, target_notional, confidence, sizing_rationale. If direct tool name is unavailable, call tools/list and use the exposed alias that ends with order_place_market or order_place_limit. If no real write is executed because X-Confirm confirmation is missing, set sizing_rationale exactly to: Order placement failed due to missing Alpaca confirmation credentials (X-Confirm: true). Required trade size calculated as a Market Order."
FINANCIAL_STRATEGY_ENABLED="false"
FINANCIAL_STRATEGY_FILE=""
SIMULATION_PATTERN='simulat|Simulation/Data Aggregation|tool limitations|could not be executed via a specific tool call|conceptually followed|No trade executed|simulated-due-to-mcp-failure|mock_[a-zA-Z0-9_-]*|MOCK_TIMESTAMP|ORDER_[0-9]{10,}_[A-Z0-9_]+|"order_id"[[:space:]]*:[[:space:]]*"(mock_[^"]*|abc123def456|ORDER_[0-9]{10,}_[A-Z0-9_]+|MOCK_[^"]*|MOCK_TIMESTAMP[^"]*)"|"submitted_at"[[:space:]]*:[[:space:]]*"(YYYY|yyyy)-|absolute pathway|Alpaca SDK client library|programmatic tool execution within this sandbox environment failed|using the derived values from the successful simulation of the logic|providing the final compact JSON report as requested|real order was simulated|fulfilling the "Real-Execution Requirement"|backed by real tool output'
INVALID_EXECUTION_PATTERN='alpaca-cli|command not found|not found in the container|could not be found in PATH|execute_code|delegate_task|simulate and execute|subagent|Task 0 \(Analyst Phase\)|Task 1 \(Broker Phase\)|I need clarification|Timeout Adjustment|NameError: name '\''json'\'' is not defined'
##
## Require traces that look like an actual tool call, not just prompt text mentions.
##
REQUIRED_MCP_WRITE_PATTERN='"name"[[:space:]]*:[[:space:]]*"([a-zA-Z0-9_]*_)?(order_place_(market|limit)|position_close)"|tool[^\n]*([a-zA-Z0-9_]*_)?(order_place_(market|limit)|position_close)|([a-zA-Z0-9_]*_)?(order_place_(market|limit)|position_close)[[:space:]]*\('
UUID_ORDER_ID_PATTERN='[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
DIRECT_FALLBACK_CONFIDENCE=""
DIRECT_FALLBACK_ACTION=""
DIRECT_FALLBACK_TARGET_NOTIONAL=""
DIRECT_FALLBACK_CURRENT_PRICE=""
DIRECT_FALLBACK_FINAL_QTY=""
DIRECT_FALLBACK_LIMIT_PRICE=""
DIRECT_FALLBACK_SIZING_RATIONALE=""
DIRECT_FALLBACK_EXECUTED_WRITE="false"
DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED="true"
DIRECT_FALLBACK_SELECTED_SYMBOL=""
DIRECT_FALLBACK_SELECTED_SIGNAL=""
DIRECT_FALLBACK_SELECTION_SOURCE=""
GET_ORDERS_LAST_RESPONSE=""
GET_ORDERS_LAST_ERROR=""
LAST_FAILURE_REPORT_FILE=""
##
## END of variables and parameters definitions.
##

mkdir -p "$STATE_DIR"
mkdir -p "$LOCK_SLOTS_DIR"

print_help() {
  cat <<EOF
Usage: $(basename "$0") [option]

Options:
  --run-now        Run one controlled cycle now (waits for lock by default).
  --status         Show persisted state and crontab status.
  --install-cron   Install/update user crontab entry for this job.
  --remove-cron    Remove user crontab entry for this job.
  --print-cron-preset  Print stable cron preset command/entry.
  --help           Show this help.

Environment overrides:
  DAILY_WATCHLIST_CRON_SCHEDULE (default: */30 * * * *)
  HERMES_CONTAINER_NAME         (default: hermes)
  ALPACA_MCP_CONTAINER_NAME     (default: alpaca-mcp)
  RUN_TIMEOUT_SECONDS           (default: 1500)
  LOCK_WAIT_SECONDS             (default: 300, used by --run-now)
  MAX_PARAREL_CRONTASKS_RUN    (default: 1)
  WATCHLIST_TICKERS             (default: AAPL, GOOGL, AMZN)
  ALPACA_MIN_ORDER_NOTIONAL_USD (default: 1.00)
  MCP_PREFLIGHT_RETRIES         (default: 3)
  MCP_PREFLIGHT_RETRY_DELAY_SECONDS (default: 5)
  ORDERS_COUNT_RETRIES          (default: 3)
  ORDERS_COUNT_RETRY_DELAY_SECONDS (default: 2)
  HERMES_HEALTH_WAIT_SECONDS    (default: 45)
  HERMES_MCP_REQUIRED_COUNT     (default: 4)
  HERMES_MCP_BOOTSTRAP_TIMEOUT_SECONDS (default: 45)
  HERMES_MCP_BOOTSTRAP_RETRIES  (default: 2)
  HERMES_MCP_BOOTSTRAP_STRICT   (default: false; set true to fail-fast)
  DISABLE_TERMINAL_MCP_FOR_RUN  (default: false)
  DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE (default: true)
  DIRECT_ALPACA_ONLY_MODE        (default: false)
  ORDER_RETEST_ATTEMPTS         (default: 2; additional retries after first try)
  ORDER_RETEST_DELAY_SECONDS    (default: 5)
  TIMEOUT_RETEST_ATTEMPTS       (default: 0; additional retries after first timeout)
  TIMEOUT_RETEST_DELAY_SECONDS  (default: 8)
  HERMES_PERSISTENT_READY_WARMUP (default: false)
  HERMES_PERSISTENT_READY_TIMEOUT_SECONDS (default: 90)
  MCP_UNREADY_RECOVERY_ATTEMPTS (default: 1; additional retries after first MCP unready)
  MCP_UNREADY_RECOVERY_DELAY_SECONDS (default: 6)
  ANALYST_MCP_CONTAINER_NAME    (default: investment-analyst-api)
  WORKSPACE_MCP_CONTAINER_NAME  (default: workspace-mcp)
  TOOLBOX_MCP_CONTAINER_NAME    (default: mcp-toolbox)
  TERMINAL_MCP_CONTAINER_NAME   (default: stdio-terminal)
EOF
}

print_stable_cron_preset() {
  cat <<EOF
# Stable run-now preset (manual)
cd $ROOT && \\
LOCK_WAIT_SECONDS=300 \\
MAX_PARAREL_CRONTASKS_RUN=1 \\
WATCHLIST_TICKERS='AAPL' \\
HERMES_MCP_BOOTSTRAP_STRICT=false \\
DISABLE_TERMINAL_MCP_FOR_RUN=true \\
HERMES_PERSISTENT_READY_WARMUP=false \\
RUN_TIMEOUT_SECONDS=1500 \\
TIMEOUT_RETEST_ATTEMPTS=0 \\
DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true \\
DIRECT_ALPACA_ONLY_MODE=false \\
$SCRIPT_PATH --run-now

# Matching cron entry (every 30 min)
*/30 * * * * cd $ROOT && LOCK_WAIT_SECONDS=300 MAX_PARAREL_CRONTASKS_RUN=1 WATCHLIST_TICKERS='AAPL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=true HERMES_PERSISTENT_READY_WARMUP=false RUN_TIMEOUT_SECONDS=1500 TIMEOUT_RETEST_ATTEMPTS=0 DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true DIRECT_ALPACA_ONLY_MODE=false $SCRIPT_PATH --run-now >> $STATE_DIR/cron_AAPL.log 2>&1
EOF
}

require_cmds() {
  local cmd
  for cmd in docker timeout flock find stat tail grep python3; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      echo "missing required command: $cmd" >&2
      exit 2
    fi
  done
}

check_runtime_prereqs() {
  if ! docker inspect "$HERMES_CONTAINER" >/dev/null 2>&1; then
    echo "required container missing: $HERMES_CONTAINER" >&2
    exit 2
  fi
  if ! docker inspect "$ALPACA_MCP_CONTAINER" >/dev/null 2>&1; then
    echo "required container missing: $ALPACA_MCP_CONTAINER" >&2
    exit 2
  fi

  if [[ "$(docker inspect -f '{{.State.Running}}' "$HERMES_CONTAINER" 2>/dev/null || true)" != "true" ]]; then
    echo "required container not running: $HERMES_CONTAINER" >&2
    exit 2
  fi
  if [[ "$(docker inspect -f '{{.State.Running}}' "$ALPACA_MCP_CONTAINER" 2>/dev/null || true)" != "true" ]]; then
    echo "required container not running: $ALPACA_MCP_CONTAINER" >&2
    exit 2
  fi
}

check_mcp_from_hermes() {
  local probe attempt retries delay_seconds
  probe='for u in \
    http://alpaca-mcp:3001/health \
    http://investment-analyst-api:8001/health \
    http://workspace-mcp:3001/health \
    http://mcp-toolbox:3001/health \
    http://stdio-terminal:3002/health; do \
      curl -fsS "$u" >/dev/null || { echo "mcp_preflight_failed=$u"; exit 1; }; \
    done; \
    echo "mcp_preflight=ok"'
  retries="$MCP_PREFLIGHT_RETRIES"
  delay_seconds="$MCP_PREFLIGHT_RETRY_DELAY_SECONDS"
  [[ "$retries" =~ ^[0-9]+$ ]] || retries=3
  [[ "$delay_seconds" =~ ^[0-9]+$ ]] || delay_seconds=5
  (( retries > 0 )) || retries=1

  for (( attempt=1; attempt<=retries; attempt++ )); do
    if docker exec "$HERMES_CONTAINER" sh -lc "$probe" >/dev/null 2>&1; then
      return 0
    fi
    if (( attempt < retries )); then
      echo "mcp preflight attempt ${attempt}/${retries} failed; retrying in ${delay_seconds}s..." >&2
      timeout "$delay_seconds" tail -f /dev/null >/dev/null 2>&1 || true
    fi
  done

  echo "mcp preflight failed from hermes after ${retries} attempts; at least one MCP endpoint is unreachable" >&2
  return 1
}

wait_for_hermes_health() {
  local now deadline status
  now="$(date +%s)"
  deadline=$((now + HERMES_HEALTH_WAIT_SECONDS))

  while (( $(date +%s) < deadline )); do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$HERMES_CONTAINER" 2>/dev/null || true)"
    if [[ "$status" == "healthy" ]]; then
      return 0
    fi
    timeout 2 tail -f /dev/null >/dev/null 2>&1 || true
  done

  return 1
}

build_effective_mcp_servers() {
  local current
  current="$(docker exec "$HERMES_CONTAINER" sh -lc 'printf "%s" "$HERMES_MCP_SERVERS"' 2>/dev/null || true)"
  if [[ -z "$current" ]]; then
    current="$(docker exec "$HERMES_CONTAINER" sh -lc 'printf "%s" "$MCP_SERVERS"' 2>/dev/null || true)"
  fi
  if [[ "$DISABLE_TERMINAL_MCP_FOR_RUN" == "true" ]]; then
    # Remove terminal entry and normalize accidental repeated commas.
    current="$(printf '%s' "$current" | sed -E 's/(^|,)terminal=[^,]*(,|$)/\1/g; s/,,+/,/g; s/^,//; s/,$//')"
  fi
  printf '%s' "$current"
}

count_effective_mcp_servers() {
  local servers="${1:-}"
  python3 - <<'PY' "$servers"
import sys

raw = (sys.argv[1] or '').strip().strip(',')
entries = [part for part in raw.split(',') if part.strip() and '=' in part]
print(len(entries))
PY
}

prewarm_hermes_persistent_ready() {
  local timeout_seconds now warmup_prompt warmup_log warmup_exit_code
  if [[ "$DIRECT_ALPACA_ONLY_MODE" == "true" ]]; then
    return 0
  fi
  if [[ "$HERMES_PERSISTENT_READY_WARMUP" != "true" ]]; then
    return 0
  fi

  timeout_seconds="$HERMES_PERSISTENT_READY_TIMEOUT_SECONDS"
  [[ "$timeout_seconds" =~ ^[0-9]+$ ]] || timeout_seconds=90
  (( timeout_seconds > 0 )) || timeout_seconds=90
  now="$(date -Iseconds)"
  warmup_prompt="List available MCP servers and available investment-related skills only. Do not place orders. Do not write files. Exit after the summary."
  warmup_log="$STATE_DIR/prewarm_${cycle_count}_attempt_${attempt_index}.log"

  set +e
  timeout --signal=TERM --kill-after=15 "$timeout_seconds" \
    docker exec \
    -e HERMES_ONESHOT_PROMPT="$warmup_prompt" \
    -e HERMES_MCP_SERVERS="$effective_mcp_servers" \
    -e MCP_SERVERS="$effective_mcp_servers" \
    "$HERMES_CONTAINER" \
    sh -lc '/opt/hermes/bin/hermes --oneshot "$HERMES_ONESHOT_PROMPT"' > "$warmup_log" 2>&1
  warmup_exit_code=$?
  set -e

  if [[ $warmup_exit_code -eq 0 ]]; then
    echo "[$now] cycle=$cycle_count status=warmup action=hermes-persistent-ready result=success attempt=$attempt_index/$max_order_attempts duration_seconds=$(cycle_duration_seconds)" >> "$LOG_FILE"
    return 0
  fi

  echo "[$now] cycle=$cycle_count status=warmup action=hermes-persistent-ready result=non-fatal-failure exit_code=$warmup_exit_code attempt=$attempt_index/$max_order_attempts duration_seconds=$(cycle_duration_seconds)" >> "$LOG_FILE"
  return 0
}

check_hermes_mcp_bootstrap() {
  local retries required_count timeout_seconds attempt output observed_count healthy_count enabled_count configured_count list_cmd effective_servers_for_bootstrap
  retries="$HERMES_MCP_BOOTSTRAP_RETRIES"
  required_count="$HERMES_MCP_REQUIRED_COUNT"
  timeout_seconds="$HERMES_MCP_BOOTSTRAP_TIMEOUT_SECONDS"
  [[ "$retries" =~ ^[0-9]+$ ]] || retries=2
  [[ "$required_count" =~ ^[0-9]+$ ]] || required_count=4
  [[ "$timeout_seconds" =~ ^[0-9]+$ ]] || timeout_seconds=45
  (( retries > 0 )) || retries=1
  if [[ "$DISABLE_TERMINAL_MCP_FOR_RUN" == "true" ]] && (( required_count > 1 )); then
    required_count=$((required_count - 1))
  fi

  effective_servers_for_bootstrap="${effective_mcp_servers:-}"
  if [[ -z "$effective_servers_for_bootstrap" ]]; then
    effective_servers_for_bootstrap="$(build_effective_mcp_servers)"
  fi

  configured_count="$(count_effective_mcp_servers "$effective_servers_for_bootstrap")"
  [[ "$configured_count" =~ ^[0-9]+$ ]] || configured_count=0
  if (( configured_count > 0 && required_count > configured_count )); then
    required_count="$configured_count"
  fi

  list_cmd='if command -v hermes >/dev/null 2>&1; then hermes mcp list; elif [ -x /opt/hermes/bin/hermes ]; then /opt/hermes/bin/hermes mcp list; else exit 127; fi'

  for (( attempt=1; attempt<=retries; attempt++ )); do
    output="$(docker exec "$HERMES_CONTAINER" sh -lc "$list_cmd" 2>&1 || true)"
    output="$(printf '%s\n' "$output" | sed -E 's/\x1B\[[0-9;]*[A-Za-z]//g')"

    observed_count="$(printf '%s\n' "$output" \
      | awk 'NF >= 2 && $2 ~ /^http/ {count++} END {print count+0}')"
    healthy_count="$(printf '%s\n' "$output" \
      | awk 'NF >= 2 && $2 ~ /^http/ && /enabled/ {count++} END {print count+0}')"

    # Fallback for atypical table formatting where URL is not in column 2.
    if (( observed_count == 0 )); then
      observed_count="$(printf '%s\n' "$output" | grep -E '[[:space:]]http[s]?://' | wc -l | awk '{print $1}')"
    fi
    if (( healthy_count == 0 )); then
      healthy_count="$(printf '%s\n' "$output" | grep -E '[[:space:]]http[s]?://' | grep -E 'enabled' | wc -l | awk '{print $1}')"
    fi

    enabled_count="$(printf '%s\n' "$output" | grep -E '[[:space:]]http[s]?://' | grep -F 'enabled' | wc -l | awk '{print $1}')"

    healthy_count="$(printf '%s' "$healthy_count" | tr -cd '0-9')"

    observed_count="$(printf '%s' "${observed_count:-}" | tr -cd '0-9')"
    enabled_count="$(printf '%s' "${enabled_count:-}" | tr -cd '0-9')"
    [[ -n "$observed_count" ]] || observed_count=0
    [[ -n "$healthy_count" ]] || healthy_count=0
    [[ -n "$enabled_count" ]] || enabled_count=0

    if (( enabled_count >= required_count || healthy_count >= required_count )); then
      return 0
    fi

    echo "hermes mcp bootstrap attempt ${attempt}/${retries} insufficient: observed=${observed_count:-0}, enabled_lines=${enabled_count:-0}, healthy_lines=${healthy_count:-0}, configured=${configured_count:-0}, required=${required_count}" >&2
    if (( attempt < retries )); then
      if docker restart "$HERMES_CONTAINER" >/dev/null 2>&1; then
        wait_for_hermes_health || true
        timeout "$timeout_seconds" tail -f /dev/null >/dev/null 2>&1 || true
      fi
    fi
  done

  echo "hermes mcp bootstrap failed: required ${required_count} MCP servers not observed" >&2
  return 1
}

ensure_hermes_ready_for_attempt() {
  if ! check_mcp_from_hermes; then
    echo "hermes mcp preflight is not ready for a oneshot attempt" >&2
    return 1
  fi

  if ! check_hermes_mcp_bootstrap; then
    echo "hermes mcp bootstrap is not ready for a oneshot attempt" >&2
    return 1
  fi

  return 0
}

append_timeout_diagnostics() {
  local now
  now="$(date -Iseconds)"
  {
    echo "[$now] timeout-diagnostics: run log was empty or incomplete"
    echo "--- hermes mcp preflight snapshot ---"
    docker exec "$HERMES_CONTAINER" sh -lc 'for u in \
      http://alpaca-mcp:3001/health \
      http://investment-analyst-api:8001/health \
      http://workspace-mcp:3001/health \
      http://mcp-toolbox:3001/health \
      http://stdio-terminal:3002/health; do \
        printf "%s => " "$u"; curl -fsS "$u" >/dev/null && echo ok || echo failed; \
      done' 2>&1 || true
    echo "--- hermes logs tail ---"
    docker logs "$HERMES_CONTAINER" --tail=120 2>&1 || true
  } >> "$run_log"
}

cycle_duration_seconds() {
  local now_epoch start_epoch
  now_epoch="$(date +%s)"
  start_epoch="${run_started_epoch:-$now_epoch}"
  if [[ "$start_epoch" =~ ^[0-9]+$ ]] && (( now_epoch >= start_epoch )); then
    echo "$((now_epoch - start_epoch))"
  else
    echo "0"
  fi
}

install_crontab_entry() {
  if ! command -v crontab >/dev/null 2>&1; then
    echo "crontab command not found" >&2
    exit 2
  fi

  local tmp cron_line cron_log_tag
  tmp="$(mktemp)"
  cron_log_tag="$(printf '%s' "$WATCHLIST_TICKERS" | tr ',' '_' | tr -cd '[:alnum:]_-' )"
  [[ -n "$cron_log_tag" ]] || cron_log_tag="watchlist"
  cron_line="$SCHEDULE cd $ROOT && LOCK_WAIT_SECONDS=$LOCK_WAIT_SECONDS MAX_PARAREL_CRONTASKS_RUN=$MAX_PARAREL_CRONTASKS_RUN WATCHLIST_TICKERS='$WATCHLIST_TICKERS' HERMES_MCP_BOOTSTRAP_STRICT=$HERMES_MCP_BOOTSTRAP_STRICT DISABLE_TERMINAL_MCP_FOR_RUN=$DISABLE_TERMINAL_MCP_FOR_RUN HERMES_PERSISTENT_READY_WARMUP=$HERMES_PERSISTENT_READY_WARMUP TIMEOUT_RETEST_ATTEMPTS=$TIMEOUT_RETEST_ATTEMPTS RUN_TIMEOUT_SECONDS=$RUN_TIMEOUT_SECONDS DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=$DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE DIRECT_ALPACA_ONLY_MODE=$DIRECT_ALPACA_ONLY_MODE $SCRIPT_PATH --run-now >> $STATE_DIR/cron_${cron_log_tag}.log 2>&1 # $JOB_NAME"

  crontab -l 2>/dev/null | grep -Fv "$JOB_NAME" > "$tmp" || true
  printf '%s\n' "$cron_line" >> "$tmp"
  crontab "$tmp"
  rm -f "$tmp"

  echo "installed_crontab=$cron_line"
}

remove_crontab_entry() {
  if ! command -v crontab >/dev/null 2>&1; then
    echo "crontab command not found" >&2
    exit 2
  fi

  local tmp
  tmp="$(mktemp)"
  crontab -l 2>/dev/null | grep -Fv "$JOB_NAME" > "$tmp" || true
  crontab "$tmp"
  rm -f "$tmp"
  echo "removed_crontab_entries_for=$JOB_NAME"
}

load_state() {
  cycle_count=0
  last_status="never-run"
  last_run_at=""
  last_exit_code=""
  detect_latest_report_artifacts
  if [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
  fi
}

persist_state() {
  cat > "$STATE_FILE" <<EOF
cycle_count=${cycle_count}
last_status=${last_status@Q}
last_run_at=${last_run_at@Q}
last_exit_code=${last_exit_code@Q}
last_json_report=${last_json_report@Q}
last_md_report=${last_md_report@Q}
EOF
}

print_status() {
  load_state
  echo "job_name=$JOB_NAME"
  echo "schedule=$SCHEDULE"
  echo "cycle_count=$cycle_count"
  echo "last_status=$last_status"
  echo "last_run_at=$last_run_at"
  echo "last_exit_code=$last_exit_code"
  echo "last_json_report=$last_json_report"
  echo "last_md_report=$last_md_report"
  if crontab -l 2>/dev/null | grep -Fq "$JOB_NAME"; then
    echo "crontab_status=installed"
  else
    echo "crontab_status=missing"
  fi
}

release_parallel_run_lock() {
  local fd slot
  fd="${LOCK_SLOT_FD:-}"
  slot="${LOCK_SLOT_INDEX:-}"

  if [[ -n "$fd" ]]; then
    eval "exec ${fd}>&-" || true
  fi
  if [[ -n "$slot" ]]; then
    rm -f "$LOCK_SLOTS_DIR/slot_${slot}.pid"
  fi
}

collect_parallel_lock_pids() {
  local pid_file pids pid
  pids=""
  for pid_file in "$LOCK_SLOTS_DIR"/slot_*.pid; do
    [[ -f "$pid_file" ]] || continue
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    [[ -n "$pid" ]] || continue
    if [[ -n "$pids" ]]; then
      pids+=";"
    fi
    pids+="$pid"
  done

  if [[ -n "$pids" ]]; then
    echo "$pids"
  else
    echo "unknown"
  fi
}

acquire_single_run_lock() {
  local now lock_wait_seconds max_parallel slot fd slot_file started_epoch elapsed_seconds holders wait_announced
  lock_wait_seconds="${1:-0}"
  now="$(date -Iseconds)"
  max_parallel="$MAX_PARAREL_CRONTASKS_RUN"
  [[ "$max_parallel" =~ ^[0-9]+$ ]] || max_parallel=5
  (( max_parallel > 0 )) || max_parallel=5
  [[ "$lock_wait_seconds" =~ ^[0-9]+$ ]] || lock_wait_seconds=0
  (( lock_wait_seconds >= 0 )) || lock_wait_seconds=0

  started_epoch="$(date +%s)"
  wait_announced=false

  while true; do
    for (( slot=1; slot<=max_parallel; slot++ )); do
      fd=$((200 + slot))
      slot_file="$LOCK_SLOTS_DIR/slot_${slot}.lock"
      eval "exec ${fd}>\"$slot_file\""
      if eval "flock -n ${fd}"; then
        LOCK_SLOT_FD="$fd"
        LOCK_SLOT_INDEX="$slot"
        echo "$$" > "$LOCK_SLOTS_DIR/slot_${slot}.pid"
        # Backward-compatible marker for any external tooling that still checks single pid file.
        echo "$$" > "$LOCK_PID_FILE"
        trap 'release_parallel_run_lock' EXIT
        return 0
      fi
      eval "exec ${fd}>&-"
    done

    holders="$(collect_parallel_lock_pids)"
    if (( lock_wait_seconds == 0 )); then
      echo "[$now] status=skipped reason=parallel-limit lock_holders=$holders max_parallel=$max_parallel duration_seconds=$(cycle_duration_seconds)" >> "$LOG_FILE"
      echo "skip: maximum parallel runs reached (${max_parallel}); holders=${holders}"
      exit 0
    fi

    elapsed_seconds=$(( $(date +%s) - started_epoch ))
    if (( elapsed_seconds >= lock_wait_seconds )); then
      echo "[$now] status=skipped reason=lock-timeout wait_seconds=$lock_wait_seconds lock_holders=$holders max_parallel=$max_parallel duration_seconds=$(cycle_duration_seconds)" >> "$LOG_FILE"
      echo "skip: lock wait timeout after ${lock_wait_seconds}s (holders=${holders}, max_parallel=${max_parallel})"
      exit 3
    fi

    if [[ "$wait_announced" != "true" ]]; then
      echo "wait: max parallel runs reached; waiting up to ${lock_wait_seconds}s for a free slot..."
      wait_announced=true
    fi
    timeout 1 tail -f /dev/null >/dev/null 2>&1 || true
  done
}

get_alpaca_orders_count() {
  local payload resp parsed retries delay_seconds attempt
  payload='{"jsonrpc":"2.0","id":2001,"method":"tools/call","params":{"name":"orders_list","arguments":{"status":"all","limit":500}}}'
  retries="$ORDERS_COUNT_RETRIES"
  delay_seconds="$ORDERS_COUNT_RETRY_DELAY_SECONDS"
  [[ "$retries" =~ ^[0-9]+$ ]] || retries=3
  [[ "$delay_seconds" =~ ^[0-9]+$ ]] || delay_seconds=2
  (( retries > 0 )) || retries=1
  (( delay_seconds >= 0 )) || delay_seconds=2

  GET_ORDERS_LAST_RESPONSE=""
  GET_ORDERS_LAST_ERROR=""

  for (( attempt=1; attempt<=retries; attempt++ )); do
    resp="$(curl -sS -X POST http://127.0.0.1:3003/mcp -H 'Content-Type: application/json' -d "$payload" 2>&1 || true)"
    parsed="$(printf '%s' "$resp" | python3 -c '
  import json
  import sys

  raw = sys.stdin.read()
  try:
    outer = json.loads(raw)
    if outer.get("error"):
      raise ValueError("jsonrpc-error:{}".format(outer.get("error")))
    text = outer["result"]["content"][0]["text"]
    orders = json.loads(text)
    if not isinstance(orders, list):
      raise ValueError("orders-payload-not-a-list")
    print(f"ok:{len(orders)}")
  except Exception as exc:
    print(f"error:{exc}")
  ' 2>&1)"

    if [[ "$parsed" =~ ^ok:([0-9]+)$ ]]; then
      printf '%s\n' "${BASH_REMATCH[1]}"
      return 0
    fi

    GET_ORDERS_LAST_RESPONSE="$resp"
    GET_ORDERS_LAST_ERROR="${parsed#error:}"

    if (( attempt < retries )); then
      echo "alpaca orders count attempt ${attempt}/${retries} failed; retrying in ${delay_seconds}s..." >&2
      if (( delay_seconds > 0 )); then
        timeout "$delay_seconds" tail -f /dev/null >/dev/null 2>&1 || true
      fi
    fi
  done

  return 1
}

append_alpaca_orders_diagnostics() {
  local phase="$1"
  {
    echo "[$(date -Iseconds)] alpaca-orders-diagnostics phase=${phase} last_error=${GET_ORDERS_LAST_ERROR:-unknown}"
    if [[ -n "${GET_ORDERS_LAST_RESPONSE:-}" ]]; then
      printf '%s\n' "$GET_ORDERS_LAST_RESPONSE"
    fi
    echo "--- alpaca-mcp health ---"
    curl -fsS http://127.0.0.1:3003/health 2>&1 || true
    echo "--- alpaca-mcp container ---"
    docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$ALPACA_MCP_CONTAINER" 2>&1 || true
  } >> "$LOG_FILE"
}

should_overwrite_latest_alias_with_failure() {
  local alias_file decision
  alias_file="$REPORTS_DIR/$(date +%F)_latest_watchlist_report.json"

  if [[ ! -r "$alias_file" ]]; then
    return 0
  fi

  decision="$(python3 - <<'PY' "$alias_file"
import json
import sys

path = sys.argv[1]
try:
    with open(path, 'r', encoding='utf-8') as handle:
        data = json.load(handle)
except Exception:
    print('replace')
    sys.exit(0)

status = str(data.get('status', '')).lower().strip()
action = str(data.get('action', '')).lower().strip()
executed_write = data.get('executed_write')
order_id = str(data.get('order_id', '')).strip().lower()

if status == 'failed':
    print('replace')
elif action in ('buy', 'sell', 'hold'):
    print('preserve')
elif isinstance(executed_write, bool):
    print('preserve')
elif order_id and order_id != 'none':
    print('preserve')
else:
    print('replace')
PY
)"

  [[ "$decision" == "replace" ]]
}

promote_failure_report_to_latest_alias_if_needed() {
  local failure_file="$1" alias_file
  alias_file="$REPORTS_DIR/$(date +%F)_latest_watchlist_report.json"
  if should_overwrite_latest_alias_with_failure; then
    cp "$failure_file" "$alias_file"
    chmod 644 "$alias_file" 2>/dev/null || true
    echo "[$(date -Iseconds)] latest_alias_update mode=failure action=promoted alias=$alias_file source=$failure_file" >> "$LOG_FILE"
  else
    echo "[$(date -Iseconds)] latest_alias_update mode=failure action=preserved-existing alias=$alias_file source=$failure_file" >> "$LOG_FILE"
  fi
}

primary_watchlist_symbol() {
  local first
  first="$(printf '%s' "$WATCHLIST_TICKERS" | tr ',' '\n' | sed -n '1p' | tr -d '[:space:]')"
  if [[ -z "$first" ]]; then
    first="AAPL"
  fi
  printf '%s' "$first"
}

infer_direct_fallback_action() {
  local confidence action override
  override="$(printf '%s' "$DIRECT_FALLBACK_ACTION_OVERRIDE" | tr '[:upper:]' '[:lower:]')"
  confidence="$DIRECT_FALLBACK_CONFIDENCE_SCORE"
  [[ "$confidence" =~ ^[0-9]+([.][0-9]+)?$ ]] || confidence="$BUY_CONFIDENCE_THRESHOLD"

  case "$override" in
    buy|sell|hold)
      action="$override"
      ;;
    *)
      action="$(python3 - <<'PY' "$confidence" "$BUY_CONFIDENCE_THRESHOLD" "$SELL_CONFIDENCE_THRESHOLD"
import sys

confidence = float(sys.argv[1])
buy_threshold = float(sys.argv[2])
sell_threshold = float(sys.argv[3])
if confidence >= buy_threshold:
    print("buy")
elif confidence <= sell_threshold:
    print("sell")
else:
    print("hold")
PY
)"
      ;;
  esac

  DIRECT_FALLBACK_CONFIDENCE="$confidence"
  DIRECT_FALLBACK_ACTION="$action"
}

infer_direct_fallback_signal_from_log() {
  local parsed
  parsed="$(python3 - <<'PY' "$run_log"
import json
import re
import sys

path = sys.argv[1]
priority = {"SELL": 3, "BUY": 2, "HOLD": 1}
best = None
watchlist = {
    token.strip().upper()
    for token in str(__import__("os").environ.get("WATCHLIST_TICKERS", "")).split(",")
    if token.strip()
}


def consider(symbol, signal, confidence, source):
  global best
  symbol = str(symbol or "").upper().strip()
  signal = str(signal or "").upper().strip()
  if not symbol:
    return
  if watchlist and symbol not in watchlist:
    return
  if signal not in priority:
    return
  try:
    confidence_value = float(confidence)
  except (TypeError, ValueError):
    confidence_value = -1.0
  candidate = (priority[signal], confidence_value, str(symbol or ""), signal, source)
  if best is None or candidate > best:
    best = candidate


with open(path, "r", encoding="utf-8", errors="ignore") as handle:
  for raw_line in handle:
    if "per_symbol_decisions" not in raw_line:
      continue
    line = raw_line.strip()
    if not line.startswith("{"):
      continue
    try:
      payload = json.loads(line)
    except Exception:
      continue

    decisions = payload.get("per_symbol_decisions")
    if isinstance(decisions, dict):
      for symbol, entry in decisions.items():
        if isinstance(entry, dict):
          consider(symbol, entry.get("signal"), entry.get("confidence"), "per_symbol_decisions")
        elif isinstance(entry, str):
          match = re.search(r"\b(BUY|SELL|HOLD)\b", entry, re.IGNORECASE)
          if match:
            consider(symbol, match.group(1), None, "per_symbol_decisions")
    elif isinstance(decisions, str):
      for symbol, signal in re.findall(r"([A-Z]{1,6})[^A-Z]*(BUY|SELL|HOLD)", decisions, re.IGNORECASE):
        consider(symbol, signal, None, "per_symbol_decisions")

if best is not None:
  _, confidence_value, symbol, signal, source = best
  print(f"{symbol}|{signal}|{confidence_value:.4f}|{source}")
PY
)"

  if [[ -z "$parsed" ]]; then
    return 1
  fi

  IFS='|' read -r DIRECT_FALLBACK_SELECTED_SYMBOL DIRECT_FALLBACK_SELECTED_SIGNAL DIRECT_FALLBACK_CONFIDENCE DIRECT_FALLBACK_SELECTION_SOURCE <<< "$parsed"
  return 0
}

symbol_position_qty() {
  local symbol="$1" payload resp
  payload="$(printf '{"jsonrpc":"2.0","id":1002,"method":"tools/call","params":{"name":"position_get","arguments":{"symbol":"%s"}}}' "$symbol")"
  resp="$(curl -sS -X POST http://127.0.0.1:3003/mcp -H 'Content-Type: application/json' -d "$payload" 2>/dev/null || true)"
  python3 - <<'PY' "$resp"
import json
import sys

raw = sys.argv[1]
qty = 0.0

try:
    outer = json.loads(raw)
    text = (((outer.get("result") or {}).get("content") or [{}])[0]).get("text")
    if text:
        position = json.loads(text)
        qty = float(position.get("qty") or 0.0)
except Exception:
    qty = 0.0

print(f"{max(0.0, qty):.8f}")
PY
}

compute_direct_alpaca_sizing() {
  local symbol="$1" confidence="$2" action_side="${3:-buy}" quote_payload quote_resp quote_price target_notional final_qty limit_price

  quote_payload="$(printf '{"jsonrpc":"2.0","id":1000,"method":"tools/call","params":{"name":"quote_latest","arguments":{"symbol":"%s"}}}' "$symbol")"
  quote_resp="$(curl -sS -X POST http://127.0.0.1:3003/mcp -H 'Content-Type: application/json' -d "$quote_payload" 2>&1 || true)"
  quote_price="$(python3 - <<'PY' "$quote_resp"
import json
import sys

raw = sys.argv[1]
try:
    outer = json.loads(raw)
    text = outer["result"]["content"][0]["text"]
    quote = json.loads(text)
    ask = quote.get("ask_price")
    bid = quote.get("bid_price")
    last = quote.get("last_price") or quote.get("price")
    values = [value for value in (ask, bid, last) if value not in (None, "")]
    if not values:
        raise ValueError("quote missing price")
    numeric = [float(value) for value in values]
    if ask not in (None, "") and bid not in (None, ""):
        price = (float(ask) + float(bid)) / 2.0
    else:
        price = numeric[0]
    if price <= 0:
        raise ValueError("non-positive price")
    print(f"{price:.4f}")
except Exception:
    print("")
PY
)"

  if [[ -z "$quote_price" ]]; then
    return 1
  fi

  target_notional="$(python3 - <<'PY' "$confidence" "$BUY_CONFIDENCE_THRESHOLD" "$BASE_NOTIONAL_PER_TRADE_USD" "$MAX_NOTIONAL_PER_SYMBOL_USD"
import sys

confidence = float(sys.argv[1])
threshold = float(sys.argv[2])
base_notional = float(sys.argv[3])
max_notional = float(sys.argv[4])
target = base_notional + max(0.0, confidence - threshold) * 100.0
target = min(target, max_notional)
print(f"{target:.2f}")
PY
)"

  final_qty="$(python3 - <<'PY' "$target_notional" "$quote_price" "$QTY_STEP" "$MIN_TRADE_QTY"
import math
import sys

target_notional = float(sys.argv[1])
quote_price = float(sys.argv[2])
qty_step = float(sys.argv[3])
min_trade_qty = float(sys.argv[4])
raw_qty = target_notional / quote_price
stepped_qty = math.floor(raw_qty / qty_step) * qty_step
final_qty = max(min_trade_qty, stepped_qty)
print(f"{final_qty:.4f}")
PY
)"

  limit_price="$(python3 - <<'PY' "$quote_price" "$action_side"
import sys

quote_price = float(sys.argv[1])
action_side = str(sys.argv[2]).lower()
multiplier = 1.01 if action_side == "buy" else 0.99
limit_price = round(quote_price * multiplier, 2)
print(f"{limit_price:.2f}")
PY
)"

  DIRECT_FALLBACK_CONFIDENCE="$confidence"
  DIRECT_FALLBACK_TARGET_NOTIONAL="$target_notional"
  DIRECT_FALLBACK_CURRENT_PRICE="$quote_price"
  DIRECT_FALLBACK_FINAL_QTY="$final_qty"
  DIRECT_FALLBACK_LIMIT_PRICE="$limit_price"
  DIRECT_FALLBACK_SIZING_RATIONALE="confidence-based sizing (${action_side}): target_notional=${target_notional} from confidence=${confidence} and price=${quote_price}; qty_step=${QTY_STEP}; final_qty=${final_qty}"

  {
    echo "[$(date -Iseconds)] direct_alpaca_sizing symbol=${symbol} confidence=${confidence} target_notional=${target_notional} current_price=${quote_price} final_qty=${final_qty} limit_price=${limit_price}"
    printf '%s\n' "$quote_resp"
  } >> "$run_log"
}

get_alpaca_account_snapshot() {
  local payload resp
  payload='{"jsonrpc":"2.0","id":2003,"method":"tools/call","params":{"name":"account_get","arguments":{}}}'
  resp="$(curl -sS -X POST http://127.0.0.1:3003/mcp -H 'Content-Type: application/json' -d "$payload" 2>&1 || true)"

  python3 - <<'PY' "$resp"
import json
import sys

raw = sys.argv[1]

def maybe_float(value):
  try:
    return float(value)
  except Exception:
    return None

try:
  payload = json.loads(raw)
  if payload.get("error"):
    raise ValueError(payload["error"])
  text = payload["result"]["content"][0]["text"]
  data = json.loads(text)
  if not isinstance(data, dict):
    raise ValueError("account-payload-not-dict")
  cash = maybe_float(data.get("cash"))
  buying_power = maybe_float(data.get("buying_power"))
  if cash is None and buying_power is None:
    raise ValueError("account-fields-missing")
  cash_text = "" if cash is None else f"{cash:.8f}"
  bp_text = "" if buying_power is None else f"{buying_power:.8f}"
  print(f"ok:{cash_text}:{bp_text}")
except Exception:
  print(f"error:{raw}")
PY
}

compute_buy_qty_from_budget() {
  local cash_budget="${1:-}" quote_price="${2:-}" qty_step="${3:-}" min_trade_qty="${4:-}"
  python3 - <<'PY' "$cash_budget" "$quote_price" "$qty_step" "$min_trade_qty"
import math
import sys

cash_budget = float(sys.argv[1])
quote_price = float(sys.argv[2])
qty_step = float(sys.argv[3])
min_trade_qty = float(sys.argv[4])

if cash_budget <= 0 or quote_price <= 0 or qty_step <= 0 or min_trade_qty <= 0:
  print("")
  raise SystemExit(0)

usable_notional = cash_budget * 0.98
raw_qty = usable_notional / quote_price
stepped_qty = math.floor(raw_qty / qty_step) * qty_step

if stepped_qty < min_trade_qty:
  print("")
else:
  print(f"{stepped_qty:.4f}")
PY
}

extract_buying_power_from_order_error() {
    local raw="${1:-}"
    python3 - <<'PY' "$raw"
import json
import sys

raw = sys.argv[1]

def maybe_float(value):
    try:
        return float(value)
    except Exception:
        return None

try:
    payload = json.loads(raw)
except Exception:
    print("")
    raise SystemExit(0)

bp = None
error = payload.get("error") if isinstance(payload, dict) else None
if isinstance(error, dict):
    data = error.get("data")
    if isinstance(data, dict):
        detail = data.get("detail")
        if isinstance(detail, str):
            try:
                detail_json = json.loads(detail)
            except Exception:
                detail_json = None
            if isinstance(detail_json, dict):
                bp = maybe_float(detail_json.get("buying_power"))
        if bp is None:
            bp = maybe_float(data.get("buying_power"))

if bp is None or bp <= 0:
    print("")
else:
    print(f"{bp:.8f}")
PY
}

compute_buy_qty_from_buying_power() {
    local buying_power="${1:-}" quote_price="${2:-}" qty_step="${3:-}" min_trade_qty="${4:-}"
    python3 - <<'PY' "$buying_power" "$quote_price" "$qty_step" "$min_trade_qty"
import math
import sys

buying_power = float(sys.argv[1])
quote_price = float(sys.argv[2])
qty_step = float(sys.argv[3])
min_trade_qty = float(sys.argv[4])

if buying_power <= 0 or quote_price <= 0 or qty_step <= 0 or min_trade_qty <= 0:
    print("")
    raise SystemExit(0)

# Keep a small safety margin so the order does not bounce on tiny price changes.
usable_notional = buying_power * 0.98
raw_qty = usable_notional / quote_price
stepped_qty = math.floor(raw_qty / qty_step) * qty_step

if stepped_qty < min_trade_qty:
    print("")
else:
    print(f"{stepped_qty:.4f}")
PY
}

compute_qty_for_min_notional() {
  local min_notional="${1:-}" quote_price="${2:-}" qty_step="${3:-}" min_trade_qty="${4:-}"
  python3 - <<'PY' "$min_notional" "$quote_price" "$qty_step" "$min_trade_qty"
import math
import sys

min_notional = float(sys.argv[1])
quote_price = float(sys.argv[2])
qty_step = float(sys.argv[3])
min_trade_qty = float(sys.argv[4])

if min_notional <= 0 or quote_price <= 0 or qty_step <= 0 or min_trade_qty <= 0:
  print("")
  raise SystemExit(0)

raw_qty = min_notional / quote_price
stepped_qty = math.ceil(raw_qty / qty_step) * qty_step
final_qty = max(min_trade_qty, stepped_qty)
print(f"{final_qty:.4f}")
PY
}

execute_direct_alpaca_fallback_write() {
  local symbol qty market_payload market_resp limit_payload limit_resp close_payload close_resp used_tool order_id position_qty override_mode buying_power adaptive_qty adaptive_payload adaptive_resp budget_candidate min_required_qty required_notional
  symbol="$(primary_watchlist_symbol)"
  DIRECT_FALLBACK_EXECUTED_WRITE="false"
  DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED="true"
  override_mode="$(printf '%s' "$DIRECT_FALLBACK_ACTION_OVERRIDE" | tr '[:upper:]' '[:lower:]')"
  if [[ "$override_mode" == "auto" ]] && infer_direct_fallback_signal_from_log; then
    symbol="${DIRECT_FALLBACK_SELECTED_SYMBOL:-$symbol}"
    DIRECT_FALLBACK_ACTION="$(printf '%s' "$DIRECT_FALLBACK_SELECTED_SIGNAL" | tr '[:upper:]' '[:lower:]')"
    DIRECT_FALLBACK_SELECTION_SOURCE="${DIRECT_FALLBACK_SELECTION_SOURCE:-per_symbol_decisions}"
  else
    if [[ "$override_mode" == "auto" ]]; then
      position_qty="$(symbol_position_qty "$symbol")"
      if python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) > 0 else 1)' "$position_qty"; then
        DIRECT_FALLBACK_ACTION="sell"
        DIRECT_FALLBACK_CONFIDENCE="$SELL_CONFIDENCE_THRESHOLD"
        DIRECT_FALLBACK_SELECTION_SOURCE="position_get(open_position)"
      else
        infer_direct_fallback_action
        DIRECT_FALLBACK_SELECTION_SOURCE="default_confidence"
      fi
    else
      infer_direct_fallback_action
      DIRECT_FALLBACK_SELECTION_SOURCE="override:${override_mode}"
    fi
  fi

  {
    echo "[$(date -Iseconds)] direct_alpaca_fallback_decision symbol=${symbol} action=${DIRECT_FALLBACK_ACTION} confidence=${DIRECT_FALLBACK_CONFIDENCE} source=${DIRECT_FALLBACK_SELECTION_SOURCE}"
  } >> "$run_log"

  if [[ "$DIRECT_FALLBACK_ACTION" == "hold" ]]; then
    compute_direct_alpaca_sizing "$symbol" "$DIRECT_FALLBACK_CONFIDENCE" "buy" >/dev/null 2>&1 || true
    DIRECT_FALLBACK_TARGET_NOTIONAL="0"
    DIRECT_FALLBACK_FINAL_QTY="0"
    DIRECT_FALLBACK_SIZING_RATIONALE="hold decision: confidence=${DIRECT_FALLBACK_CONFIDENCE} between sell_threshold=${SELL_CONFIDENCE_THRESHOLD} and buy_threshold=${BUY_CONFIDENCE_THRESHOLD}; no write tool executed"
    DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED="false"
    {
      echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=hold used_tool=none order_id=none reason=hold-noop source=${DIRECT_FALLBACK_SELECTION_SOURCE:-default}"
    } >> "$run_log"
    {
      echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=hold used_tool=none order_id=none reason=hold-noop source=${DIRECT_FALLBACK_SELECTION_SOURCE:-default}"
    } >> "$LOG_FILE"
    return 0
  fi

  if ! compute_direct_alpaca_sizing "$symbol" "$DIRECT_FALLBACK_CONFIDENCE" "$DIRECT_FALLBACK_ACTION"; then
    {
      echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=false reason=sizing-unavailable symbol=${symbol}"
    } >> "$LOG_FILE"
    return 1
  fi

  qty="$DIRECT_FALLBACK_FINAL_QTY"
  [[ "$qty" =~ ^[0-9]+([.][0-9]+)?$ ]] || qty="$MIN_TRADE_QTY"

  if [[ "$DIRECT_FALLBACK_ACTION" == "buy" ]]; then
    account_snapshot="$(get_alpaca_account_snapshot || true)"
    budget_candidate=""
    if [[ "$account_snapshot" =~ ^ok:([^:]*)[:]([^:]*)$ ]]; then
      account_cash="${BASH_REMATCH[1]}"
      account_buying_power="${BASH_REMATCH[2]}"
      if [[ -n "$account_cash" ]] && [[ -n "$account_buying_power" ]]; then
        budget_candidate="$(python3 - <<'PY' "$account_cash" "$account_buying_power"
import sys

cash = float(sys.argv[1])
buying_power = float(sys.argv[2])
print(f"{max(0.0, min(cash, buying_power)):.8f}")
PY
)"
      elif [[ -n "$account_cash" ]]; then
        budget_candidate="$account_cash"
      elif [[ -n "$account_buying_power" ]]; then
        budget_candidate="$account_buying_power"
      fi

      if [[ -n "$budget_candidate" ]] && [[ -n "${DIRECT_FALLBACK_CURRENT_PRICE:-}" ]]; then
        preflight_qty="$(compute_buy_qty_from_budget "$budget_candidate" "$DIRECT_FALLBACK_CURRENT_PRICE" "$QTY_STEP" "$MIN_TRADE_QTY")"
        if [[ -n "$preflight_qty" ]] && python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) < float(sys.argv[2]) else 1)' "$preflight_qty" "$qty"; then
          qty="$preflight_qty"
          DIRECT_FALLBACK_FINAL_QTY="$preflight_qty"
          DIRECT_FALLBACK_TARGET_NOTIONAL="$(python3 -c 'import sys; print(f"{float(sys.argv[1]) * float(sys.argv[2]):.2f}")' "$preflight_qty" "$DIRECT_FALLBACK_CURRENT_PRICE")"
          DIRECT_FALLBACK_SIZING_RATIONALE="confidence-based sizing (buy) preflight-adjusted to available budget=${budget_candidate}; final_qty=${preflight_qty}"
          {
            echo "[$(date -Iseconds)] direct_alpaca_fallback_preflight_budget symbol=${symbol} cash=${account_cash:-} buying_power=${account_buying_power:-} budget=${budget_candidate} adjusted_qty=${preflight_qty}"
          } >> "$run_log"
        fi
      fi

      if [[ -n "$budget_candidate" ]] && python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) < float(sys.argv[2]) else 1)' "$budget_candidate" "$(python3 -c 'import sys; print(f"{float(sys.argv[1]) * float(sys.argv[2]):.8f}")' "$qty" "$DIRECT_FALLBACK_CURRENT_PRICE")"; then
        DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED="false"
        DIRECT_FALLBACK_ACTION="hold"
        DIRECT_FALLBACK_TARGET_NOTIONAL="0"
        DIRECT_FALLBACK_FINAL_QTY="0"
        DIRECT_FALLBACK_SIZING_RATIONALE="buy signal downgraded to hold: available budget=${budget_candidate} below required notional; no write tool executed"
        {
          echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=hold used_tool=none order_id=none reason=budget-insufficient cash=${account_cash:-} buying_power=${account_buying_power:-}"
        } >> "$run_log"
        {
          echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=hold used_tool=none order_id=none reason=budget-insufficient cash=${account_cash:-} buying_power=${account_buying_power:-}"
        } >> "$LOG_FILE"
        return 0
      fi
    fi

    if [[ -n "${DIRECT_FALLBACK_CURRENT_PRICE:-}" ]]; then
      min_required_qty="$(compute_qty_for_min_notional "$ALPACA_MIN_ORDER_NOTIONAL_USD" "$DIRECT_FALLBACK_CURRENT_PRICE" "$QTY_STEP" "$MIN_TRADE_QTY")"
      if [[ -n "$min_required_qty" ]] && python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) > float(sys.argv[2]) else 1)' "$min_required_qty" "$qty"; then
        qty="$min_required_qty"
        DIRECT_FALLBACK_FINAL_QTY="$min_required_qty"
        DIRECT_FALLBACK_TARGET_NOTIONAL="$(python3 -c 'import sys; print(f"{float(sys.argv[1]) * float(sys.argv[2]):.2f}")' "$min_required_qty" "$DIRECT_FALLBACK_CURRENT_PRICE")"
        DIRECT_FALLBACK_SIZING_RATIONALE="confidence-based sizing (buy) raised to broker minimum order notional=${ALPACA_MIN_ORDER_NOTIONAL_USD}; final_qty=${min_required_qty}"
        {
          echo "[$(date -Iseconds)] direct_alpaca_fallback_min_notional_adjust symbol=${symbol} min_notional=${ALPACA_MIN_ORDER_NOTIONAL_USD} adjusted_qty=${min_required_qty}"
        } >> "$run_log"
      fi
    fi

    if [[ -n "$budget_candidate" ]] && [[ -n "${DIRECT_FALLBACK_CURRENT_PRICE:-}" ]]; then
      required_notional="$(python3 -c 'import sys; print(f"{float(sys.argv[1]) * float(sys.argv[2]):.8f}")' "$qty" "$DIRECT_FALLBACK_CURRENT_PRICE")"
      if python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) < float(sys.argv[2]) else 1)' "$budget_candidate" "$required_notional"; then
        DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED="false"
        DIRECT_FALLBACK_ACTION="hold"
        DIRECT_FALLBACK_TARGET_NOTIONAL="0"
        DIRECT_FALLBACK_FINAL_QTY="0"
        DIRECT_FALLBACK_SIZING_RATIONALE="buy signal downgraded to hold: available budget=${budget_candidate} below broker minimum order notional requirement=${required_notional}; no write tool executed"
        {
          echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=hold used_tool=none order_id=none reason=below-min-order-notional"
        } >> "$run_log"
        {
          echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=hold used_tool=none order_id=none reason=below-min-order-notional"
        } >> "$LOG_FILE"
        return 0
      fi
    fi
  fi

  if [[ "$DIRECT_FALLBACK_ACTION" == "sell" ]]; then
    close_payload="$(printf '{"jsonrpc":"2.0","id":1000,"method":"tools/call","params":{"name":"position_close","arguments":{"symbol":"%s"}}}' "$symbol")"
    close_resp="$(curl -sS -X POST http://127.0.0.1:3003/mcp -H 'Content-Type: application/json' -H 'X-Confirm: true' -d "$close_payload" 2>&1 || true)"
    {
      echo "[$(date -Iseconds)] direct_alpaca_fallback_close_attempt symbol=${symbol} action=sell"
      echo "{\"name\":\"position_close\",\"arguments\":{\"symbol\":\"${symbol}\"}}"
      printf '%s\n' "$close_resp"
    } >> "$run_log"

    if printf '%s' "$close_resp" | grep -Eq "$UUID_ORDER_ID_PATTERN"; then
      used_tool="position_close"
      order_id="$(printf '%s' "$close_resp" | grep -Eo "$UUID_ORDER_ID_PATTERN" | head -n1)"
      DIRECT_FALLBACK_EXECUTED_WRITE="true"
      {
        echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=sell used_tool=${used_tool} order_id=${order_id:-missing}"
      } >> "$run_log"
      {
        echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=sell used_tool=${used_tool} order_id=${order_id:-missing}"
      } >> "$LOG_FILE"
      return 0
    fi

    if printf '%s' "$close_resp" | grep -Eiq 'position.*not.*found|no position|404|not found'; then
      DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED="false"
      DIRECT_FALLBACK_ACTION="hold"
      DIRECT_FALLBACK_TARGET_NOTIONAL="0"
      DIRECT_FALLBACK_FINAL_QTY="0"
      DIRECT_FALLBACK_SIZING_RATIONALE="sell signal downgraded to hold: no open position found for ${symbol}; no write tool executed"
      {
        echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=hold used_tool=none order_id=none reason=no-open-position"
      } >> "$run_log"
      {
        echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=hold used_tool=none order_id=none reason=no-open-position"
      } >> "$LOG_FILE"
      return 0
    fi
  fi

  market_payload="$(printf '{"jsonrpc":"2.0","id":1001,"method":"tools/call","params":{"name":"order_place_market","arguments":{"symbol":"%s","qty":%s,"side":"%s","time_in_force":"day"}}}' "$symbol" "$qty" "$DIRECT_FALLBACK_ACTION")"
  market_resp="$(curl -sS -X POST http://127.0.0.1:3003/mcp -H 'Content-Type: application/json' -H 'X-Confirm: true' -d "$market_payload" 2>&1 || true)"

  {
    echo "[$(date -Iseconds)] direct_alpaca_fallback_attempt symbol=${symbol} action=${DIRECT_FALLBACK_ACTION} confidence=${DIRECT_FALLBACK_CONFIDENCE} target_notional=${DIRECT_FALLBACK_TARGET_NOTIONAL} current_price=${DIRECT_FALLBACK_CURRENT_PRICE} qty=${qty}"
    echo "{\"name\":\"order_place_market\",\"arguments\":{\"symbol\":\"${symbol}\",\"qty\":${qty},\"side\":\"${DIRECT_FALLBACK_ACTION}\",\"time_in_force\":\"day\"}}"
    printf '%s\n' "$market_resp"
  } >> "$run_log"

  if printf '%s' "$market_resp" | grep -Eq "$UUID_ORDER_ID_PATTERN"; then
    used_tool="order_place_market"
    order_id="$(printf '%s' "$market_resp" | grep -Eo "$UUID_ORDER_ID_PATTERN" | head -n1)"
    DIRECT_FALLBACK_EXECUTED_WRITE="true"
    {
      echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=${DIRECT_FALLBACK_ACTION} used_tool=${used_tool} order_id=${order_id:-missing}"
    } >> "$run_log"
    {
      echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=${DIRECT_FALLBACK_ACTION} used_tool=${used_tool} order_id=${order_id:-missing}"
    } >> "$LOG_FILE"
    return 0
  fi

  if [[ "$DIRECT_FALLBACK_ACTION" == "buy" ]] && printf '%s' "$market_resp" | grep -Eiq 'insufficient buying power|40310000|buying_power'; then
    buying_power="$(extract_buying_power_from_order_error "$market_resp")"
    adaptive_qty=""
    if [[ -n "$buying_power" ]] && [[ -n "${DIRECT_FALLBACK_CURRENT_PRICE:-}" ]]; then
      adaptive_qty="$(compute_buy_qty_from_buying_power "$buying_power" "$DIRECT_FALLBACK_CURRENT_PRICE" "$QTY_STEP" "$MIN_TRADE_QTY")"
    fi

    if [[ -n "$adaptive_qty" ]] && python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) < float(sys.argv[2]) else 1)' "$adaptive_qty" "$qty"; then
      adaptive_payload="$(printf '{"jsonrpc":"2.0","id":1002,"method":"tools/call","params":{"name":"order_place_market","arguments":{"symbol":"%s","qty":%s,"side":"%s","time_in_force":"day"}}}' "$symbol" "$adaptive_qty" "$DIRECT_FALLBACK_ACTION")"
      adaptive_resp="$(curl -sS -X POST http://127.0.0.1:3003/mcp -H 'Content-Type: application/json' -H 'X-Confirm: true' -d "$adaptive_payload" 2>&1 || true)"

      {
        echo "[$(date -Iseconds)] direct_alpaca_fallback_retry_buying_power symbol=${symbol} prior_qty=${qty} adjusted_qty=${adaptive_qty} buying_power=${buying_power}"
        echo "{\"name\":\"order_place_market\",\"arguments\":{\"symbol\":\"${symbol}\",\"qty\":${adaptive_qty},\"side\":\"${DIRECT_FALLBACK_ACTION}\",\"time_in_force\":\"day\"}}"
        printf '%s\n' "$adaptive_resp"
      } >> "$run_log"

      if printf '%s' "$adaptive_resp" | grep -Eq "$UUID_ORDER_ID_PATTERN"; then
        used_tool="order_place_market"
        order_id="$(printf '%s' "$adaptive_resp" | grep -Eo "$UUID_ORDER_ID_PATTERN" | head -n1)"
        DIRECT_FALLBACK_EXECUTED_WRITE="true"
        DIRECT_FALLBACK_FINAL_QTY="$adaptive_qty"
        DIRECT_FALLBACK_TARGET_NOTIONAL="$(python3 -c 'import sys; print(f"{float(sys.argv[1]) * float(sys.argv[2]):.2f}")' "$adaptive_qty" "$DIRECT_FALLBACK_CURRENT_PRICE")"
        DIRECT_FALLBACK_SIZING_RATIONALE="confidence-based sizing (buy) adjusted to available buying power=${buying_power}; final_qty=${adaptive_qty}"
        {
          echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=${DIRECT_FALLBACK_ACTION} used_tool=${used_tool} order_id=${order_id:-missing} source=buying-power-adjustment"
        } >> "$run_log"
        {
          echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=${DIRECT_FALLBACK_ACTION} used_tool=${used_tool} order_id=${order_id:-missing} source=buying-power-adjustment"
        } >> "$LOG_FILE"
        return 0
      fi
    fi
  fi

  limit_payload="$(printf '{"jsonrpc":"2.0","id":1003,"method":"tools/call","params":{"name":"order_place_limit","arguments":{"symbol":"%s","qty":%s,"side":"%s","limit_price":%s,"time_in_force":"day"}}}' "$symbol" "$qty" "$DIRECT_FALLBACK_ACTION" "$DIRECT_FALLBACK_LIMIT_PRICE")"
  limit_resp="$(curl -sS -X POST http://127.0.0.1:3003/mcp -H 'Content-Type: application/json' -H 'X-Confirm: true' -d "$limit_payload" 2>&1 || true)"

  {
    echo "[$(date -Iseconds)] direct_alpaca_fallback_limit_attempt symbol=${symbol} action=${DIRECT_FALLBACK_ACTION} qty=${qty} limit_price=${DIRECT_FALLBACK_LIMIT_PRICE}"
    echo "{\"name\":\"order_place_limit\",\"arguments\":{\"symbol\":\"${symbol}\",\"qty\":${qty},\"side\":\"${DIRECT_FALLBACK_ACTION}\",\"limit_price\":${DIRECT_FALLBACK_LIMIT_PRICE},\"time_in_force\":\"day\"}}"
    printf '%s\n' "$limit_resp"
  } >> "$run_log"

  if ! printf '%s' "$limit_resp" | grep -Eq "$UUID_ORDER_ID_PATTERN"; then
    if [[ "$DIRECT_FALLBACK_ACTION" == "buy" ]] && printf '%s\n%s' "$market_resp" "$limit_resp" | grep -Eiq 'max_buy_notional_exceeded|daily buy notional|would exceed configured max_notional_usd'; then
      DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED="false"
      DIRECT_FALLBACK_ACTION="hold"
      DIRECT_FALLBACK_TARGET_NOTIONAL="0"
      DIRECT_FALLBACK_FINAL_QTY="0"
      DIRECT_FALLBACK_SIZING_RATIONALE="buy signal downgraded to hold: daily BUY budget exhausted (max_buy_notional_exceeded); no write tool executed"
      {
        echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=hold used_tool=none order_id=none reason=buy-budget-exhausted"
      } >> "$run_log"
      {
        echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=hold used_tool=none order_id=none reason=buy-budget-exhausted"
      } >> "$LOG_FILE"
      return 0
    fi

    if [[ "$DIRECT_FALLBACK_ACTION" == "buy" ]] && printf '%s\n%s' "$market_resp" "$limit_resp" | grep -Eiq 'cost basis must be (\\u003e=|>=) minimal amount of order|minimal amount of order'; then
      DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED="false"
      DIRECT_FALLBACK_ACTION="hold"
      DIRECT_FALLBACK_TARGET_NOTIONAL="0"
      DIRECT_FALLBACK_FINAL_QTY="0"
      DIRECT_FALLBACK_SIZING_RATIONALE="buy signal downgraded to hold: order notional below broker minimum (cost basis must be >= minimal amount of order); no write tool executed"
      {
        echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=hold used_tool=none order_id=none reason=below-min-order-notional"
      } >> "$run_log"
      {
        echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=hold used_tool=none order_id=none reason=below-min-order-notional"
      } >> "$LOG_FILE"
      return 0
    fi

    if [[ "$DIRECT_FALLBACK_ACTION" == "buy" ]] && printf '%s\n%s' "$market_resp" "$limit_resp" | grep -Eiq 'insufficient buying power|40310000|buying_power'; then
      DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED="false"
      DIRECT_FALLBACK_ACTION="hold"
      DIRECT_FALLBACK_TARGET_NOTIONAL="0"
      DIRECT_FALLBACK_FINAL_QTY="0"
      DIRECT_FALLBACK_SIZING_RATIONALE="buy signal downgraded to hold: insufficient buying power; no write tool executed"
      {
        echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=hold used_tool=none order_id=none reason=insufficient-buying-power"
      } >> "$run_log"
      {
        echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=hold used_tool=none order_id=none reason=insufficient-buying-power"
      } >> "$LOG_FILE"
      return 0
    fi

    {
      echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=false reason=market-and-limit-failed"
    } >> "$LOG_FILE"
    return 1
  fi

  used_tool="order_place_limit"
  order_id="$(printf '%s' "$limit_resp" | grep -Eo "$UUID_ORDER_ID_PATTERN" | head -n1)"
  DIRECT_FALLBACK_EXECUTED_WRITE="true"
  {
    echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=${DIRECT_FALLBACK_ACTION} used_tool=${used_tool} order_id=${order_id:-missing}"
  } >> "$run_log"
  {
    echo "[$(date -Iseconds)] direct_alpaca_fallback_result success=true action=${DIRECT_FALLBACK_ACTION} used_tool=${used_tool} order_id=${order_id:-missing}"
  } >> "$LOG_FILE"
  return 0
}

write_direct_fallback_reports() {
  local order_id="$1"
  local order_status="$2"
  local order_symbol="$3"
  local order_submitted="$4"
  local order_confidence="${5:-$BUY_CONFIDENCE_THRESHOLD}"
  local order_target_notional="${6:-$BASE_NOTIONAL_PER_TRADE_USD}"
  local order_final_qty="${7:-$MIN_TRADE_QTY}"
  local order_sizing_rationale="${8:-minimum trade qty guardrail applied by direct Alpaca fallback write path}"
  local order_current_price="${9:-}"
  local order_action="${10:-${DIRECT_FALLBACK_ACTION:-buy}}"
  local order_executed_write="${11:-${DIRECT_FALLBACK_EXECUTED_WRITE:-false}}"
  local ts host_json host_md

  ts="$(date +%Y%m%d_%H%M%S)"
  host_json="$REPORTS_DIR/investment_analysis_cycle_${ts}.json"
  host_md="$REPORTS_DIR/investment_analysis_cycle_${ts}.md"
  cat > "$host_json" <<EOF
{
  "order_id": "${order_id}",
  "order_status": "${order_status}",
  "symbol": "${order_symbol}",
  "submitted_at": "${order_submitted}",
  "action": "${order_action}",
  "executed_write": ${order_executed_write},
  "current_price": ${order_current_price:-null},
  "final_qty": ${order_final_qty},
  "target_notional": ${order_target_notional},
  "confidence": ${order_confidence},
  "sizing_rationale": "${order_sizing_rationale}",
  "execution_mode": "direct_alpaca_fallback"
}
EOF

  cat > "$host_md" <<EOF
# Investment Analysis Cycle (Direct Alpaca Fallback)

- symbol: ${order_symbol}
- order_id: ${order_id}
- order_status: ${order_status}
- submitted_at: ${order_submitted}
- action: ${order_action}
- executed_write: ${order_executed_write}
- current_price: ${order_current_price:-n/a}
- final_qty: ${order_final_qty}
- target_notional: ${order_target_notional}
- confidence: ${order_confidence}
- sizing_rationale: ${order_sizing_rationale}
EOF

  chmod 644 "$host_json" "$host_md"
  {
    echo "[$(date -Iseconds)] direct_alpaca_fallback_reports_written json=$host_json md=$host_md"
  } >> "$run_log"
}

get_latest_alpaca_order_meta() {
  local payload resp
  payload='{"jsonrpc":"2.0","id":2002,"method":"tools/call","params":{"name":"orders_list","arguments":{"status":"all","limit":1}}}'
  resp="$(curl -sS -X POST http://127.0.0.1:3003/mcp -H 'Content-Type: application/json' -d "$payload" 2>/dev/null || true)"
  python3 - <<'PY' "$resp"
import json
import sys

raw = sys.argv[1]
try:
  outer = json.loads(raw)
  text = outer["result"]["content"][0]["text"]
  orders = json.loads(text)
  if not orders:
    print("")
  else:
    order = orders[0]
    print(f"{order.get('id','')}|{order.get('status','')}|{order.get('symbol','')}|{order.get('submitted_at','')}|{order.get('side','')}")
except Exception:
  print("")
PY
}

validate_report_sizing_metadata() {
  local report_json="$1"
  local validation_output validation_status

  validation_output="$(python3 - "$report_json" "${latest_order_id:-}" "${latest_order_symbol:-}" "${latest_order_side:-}" "$BUY_CONFIDENCE_THRESHOLD" "$BASE_NOTIONAL_PER_TRADE_USD" "$MAX_NOTIONAL_PER_SYMBOL_USD" "$MIN_TRADE_QTY" "$QTY_STEP" <<'PY'
import json
import math
import re
import sys

path, latest_order_id, latest_order_symbol, latest_order_side, buy_threshold, base_notional, max_notional, min_trade_qty, qty_step = sys.argv[1:10]
buy_threshold = float(buy_threshold)
base_notional = float(base_notional)
max_notional = float(max_notional)
min_trade_qty = float(min_trade_qty)
qty_step = float(qty_step)
simulation_pattern = re.compile(r"simulat|mock_|test_[0-9]{8}|via simulated mcp api", re.IGNORECASE)
minimum_rationale_pattern = re.compile(r"min|minimum|guardrail|fraction|step|precision|lot|price|cap", re.IGNORECASE)

def walk(value):
  if isinstance(value, dict):
    yield value
    for nested in value.values():
      yield from walk(nested)
  elif isinstance(value, list):
    for item in value:
      yield from walk(item)

def all_strings(value):
  if isinstance(value, str):
    yield value
  elif isinstance(value, dict):
    for nested in value.values():
      yield from all_strings(nested)
  elif isinstance(value, list):
    for item in value:
      yield from all_strings(item)

def as_float(value):
  try:
    return float(value)
  except (TypeError, ValueError):
    return None

with open(path, 'r', encoding='utf-8') as handle:
  data = json.load(handle)

for text in all_strings(data):
  if simulation_pattern.search(text):
    print("status=error")
    print("reason=report-simulation-marker-detected")
    sys.exit(0)

required = ("final_qty", "target_notional", "confidence", "sizing_rationale")
best_node = None
best_score = -1
for node in walk(data):
  if not isinstance(node, dict):
    continue
  score = 0
  if latest_order_id and str(node.get("order_id", "")) == latest_order_id:
    score += 100
  if latest_order_symbol and str(node.get("symbol", "")) == latest_order_symbol:
    score += 20
  score += sum(10 for key in required if key in node)
  if any(key in node for key in required) or "order_id" in node or "symbol" in node:
    if score > best_score:
      best_score = score
      best_node = node

if best_node is None:
  print("status=error")
  print("reason=report-sizing-node-missing")
  sys.exit(0)

missing = [key for key in required if best_node.get(key) in (None, "")]
if missing:
  print("status=error")
  print("reason=report-sizing-fields-missing:" + ",".join(missing))
  sys.exit(0)

report_order_id = str(best_node.get("order_id", ""))
report_symbol = str(best_node.get("symbol", ""))
if latest_order_id and report_order_id and report_order_id != latest_order_id:
  print("status=error")
  print("reason=report-order-id-mismatch")
  sys.exit(0)
if latest_order_symbol and report_symbol and report_symbol != latest_order_symbol:
  print("status=error")
  print("reason=report-symbol-mismatch")
  sys.exit(0)

confidence = as_float(best_node.get("confidence"))
target_notional = as_float(best_node.get("target_notional"))
final_qty = as_float(best_node.get("final_qty"))
sizing_rationale = str(best_node.get("sizing_rationale", ""))
current_price = as_float(best_node.get("current_price"))
action = str(best_node.get("action", "")).lower().strip()
if not action and latest_order_side in ("buy", "sell", "hold"):
  action = latest_order_side
if action not in ("buy", "sell", "hold"):
  action = "buy"

if confidence is None or not (0.0 <= confidence <= 1.0):
  print("status=error")
  print("reason=report-confidence-invalid")
  sys.exit(0)
if action == "buy" and confidence < buy_threshold:
  print("status=error")
  print("reason=report-confidence-below-threshold")
  sys.exit(0)

if target_notional is None:
  print("status=error")
  print("reason=report-target-notional-invalid")
  sys.exit(0)
if final_qty is None:
  print("status=error")
  print("reason=report-final-qty-invalid")
  sys.exit(0)

if action == "hold":
  if target_notional < 0 or final_qty < 0:
    print("status=error")
    print("reason=report-hold-values-invalid")
    sys.exit(0)
else:
  if target_notional <= 0:
    print("status=error")
    print("reason=report-target-notional-invalid")
    sys.exit(0)
  if final_qty <= 0:
    print("status=error")
    print("reason=report-final-qty-invalid")
    sys.exit(0)

if action == "buy":
  expected_target_notional = min(base_notional + max(0.0, confidence - buy_threshold) * 100.0, max_notional)
  preflight_budget_adjusted = (
    "preflight-adjusted to available budget" in sizing_rationale.lower()
    or "adjusted to available buying power" in sizing_rationale.lower()
  )
  if math.fabs(target_notional - expected_target_notional) > 0.011 and not (
    preflight_budget_adjusted and target_notional <= (expected_target_notional + 0.011)
  ):
    print("status=error")
    print("reason=report-target-notional-policy-mismatch")
    print(f"expected_target_notional={expected_target_notional:.2f}")
    sys.exit(0)

if action == "buy" and current_price is not None and current_price > 0:
  expected_final_qty = max(min_trade_qty, math.floor((target_notional / current_price) / qty_step) * qty_step)
  if math.fabs(final_qty - expected_final_qty) > 0.011:
    print("status=error")
    print("reason=report-final-qty-policy-mismatch")
    print(f"expected_final_qty={expected_final_qty:.4f}")
    print(f"current_price={current_price:.4f}")
    sys.exit(0)

if latest_order_side == "buy" and confidence >= buy_threshold and final_qty <= (min_trade_qty + 1e-9):
  if not minimum_rationale_pattern.search(sizing_rationale):
    print("status=error")
    print("reason=report-min-qty-without-rationale")
    sys.exit(0)

print("status=ok")
print(f"confidence={confidence:.4f}")
print(f"target_notional={target_notional:.2f}")
print(f"final_qty={final_qty:.4f}")
print("sizing_rationale=" + sizing_rationale.replace("\n", " ")[:300])
PY
)"

  validation_status="$(printf '%s\n' "$validation_output" | sed -n 's/^status=//p' | head -n 1)"
  report_validation_reason="$(printf '%s\n' "$validation_output" | sed -n 's/^reason=//p' | head -n 1)"
  report_validation_confidence="$(printf '%s\n' "$validation_output" | sed -n 's/^confidence=//p' | head -n 1)"
  report_validation_target_notional="$(printf '%s\n' "$validation_output" | sed -n 's/^target_notional=//p' | head -n 1)"
  report_validation_final_qty="$(printf '%s\n' "$validation_output" | sed -n 's/^final_qty=//p' | head -n 1)"
  report_validation_sizing_rationale="$(printf '%s\n' "$validation_output" | sed -n 's/^sizing_rationale=//p' | head -n 1)"

  [[ "$validation_status" == "ok" ]]
}

recover_hermes_after_timeout() {
  local now
  now="$(date -Iseconds)"
  if docker restart "$HERMES_CONTAINER" >/dev/null 2>&1; then
    if wait_for_hermes_health; then
      echo "[$now] cycle=$cycle_count status=recovery action=hermes-restart result=success health=healthy duration_seconds=$(cycle_duration_seconds)" >> "$LOG_FILE"
    else
      echo "[$now] cycle=$cycle_count status=recovery action=hermes-restart result=success health=not-healthy-within-${HERMES_HEALTH_WAIT_SECONDS}s duration_seconds=$(cycle_duration_seconds)" >> "$LOG_FILE"
    fi
  else
    echo "[$now] cycle=$cycle_count status=recovery action=hermes-restart result=failed duration_seconds=$(cycle_duration_seconds)" >> "$LOG_FILE"
  fi
}

recover_mcp_stack_after_unready() {
  local now delay_seconds container seen results hermes_health
  now="$(date -Iseconds)"
  delay_seconds="$MCP_UNREADY_RECOVERY_DELAY_SECONDS"
  [[ "$delay_seconds" =~ ^[0-9]+$ ]] || delay_seconds=6
  (( delay_seconds >= 0 )) || delay_seconds=6

  seen=" "
  results=""
  for container in \
    "$HERMES_CONTAINER" \
    "$ALPACA_MCP_CONTAINER" \
    "$ANALYST_MCP_CONTAINER" \
    "$WORKSPACE_MCP_CONTAINER" \
    "$TOOLBOX_MCP_CONTAINER" \
    "$TERMINAL_MCP_CONTAINER"; do
    [[ -n "$container" ]] || continue
    if [[ "$seen" == *" $container "* ]]; then
      continue
    fi
    seen+="$container "

    if ! docker inspect "$container" >/dev/null 2>&1; then
      results+="$container:missing,"
      continue
    fi

    if docker restart "$container" >/dev/null 2>&1; then
      results+="$container:restarted,"
    else
      results+="$container:restart-failed,"
    fi
  done

  if wait_for_hermes_health; then
    hermes_health="healthy"
  else
    hermes_health="not-healthy-within-${HERMES_HEALTH_WAIT_SECONDS}s"
  fi

  {
    echo "[$now] cycle=$cycle_count status=recovery action=mcp-stack-restart result=$results hermes_health=$hermes_health duration_seconds=$(cycle_duration_seconds)"
  } >> "$LOG_FILE"

  if (( delay_seconds > 0 )); then
    timeout "$delay_seconds" tail -f /dev/null >/dev/null 2>&1 || true
  fi
}

write_failure_report() {
  local failure_file alias_file
  alias_file="$REPORTS_DIR/$(date +%F)_latest_watchlist_report.json"
  failure_file="$REPORTS_DIR/failed_watchlist_report_cycle_${cycle_count}.json"
  cat > "$failure_file" <<EOF
{
  "job_name": "$JOB_NAME",
  "schedule": "$SCHEDULE",
  "cycle_count": $cycle_count,
  "status": "failed",
  "failed_at": "$last_run_at",
  "duration_seconds": "$(cycle_duration_seconds)",
  "exit_code": "$last_exit_code",
  "orders_before": "${orders_before:-}",
  "orders_after": "${orders_after:-}",
  "order_id": "${latest_order_id:-}",
  "order_status": "${latest_order_status:-}",
  "order_side": "${latest_order_side:-}",
  "report_validation_confidence": "${report_validation_confidence:-}",
  "report_validation_target_notional": "${report_validation_target_notional:-}",
  "report_validation_final_qty": "${report_validation_final_qty:-}",
  "report_validation_sizing_rationale": "${report_validation_sizing_rationale:-}",
  "report_validation_reason": "${report_validation_reason:-}",
  "invalid_json_report": "${last_json_report:-}",
  "invalid_md_report": "${last_md_report:-}",
  "latest_alias": "$alias_file",
  "run_log": "$run_log",
  "report_write_verified": false,
  "note": "Cycle failed before producing a verified investment analysis report artifact."
}
EOF
  chmod 644 "$failure_file" 2>/dev/null || true
  LAST_FAILURE_REPORT_FILE="$failure_file"
  promote_failure_report_to_latest_alias_if_needed "$failure_file"
}

detect_latest_report_artifacts() {
  local latest_json latest_md
  latest_json="$(find "$REPORTS_DIR" -maxdepth 1 -type f -name 'investment_analysis_cycle_*.json' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1 | cut -d' ' -f2- || true)"
  latest_md="$(find "$REPORTS_DIR" -maxdepth 1 -type f -name 'investment_analysis_cycle_*.md' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n 1 | cut -d' ' -f2- || true)"

  if [[ -n "$latest_json" ]]; then
    last_json_report="$latest_json"
  fi
  if [[ -n "$latest_md" ]]; then
    last_md_report="$latest_md"
  fi
}

capture_invalid_report_artifacts() {
  local container_json container_md host_json_candidate host_md_candidate json_mtime md_mtime

  container_json="$(docker exec "$HERMES_CONTAINER" sh -lc 'ls -1t /workspace/reports/investment_analysis_cycle_*.json 2>/dev/null | head -n 1' || true)"
  container_md="$(docker exec "$HERMES_CONTAINER" sh -lc 'ls -1t /workspace/reports/investment_analysis_cycle_*.md 2>/dev/null | head -n 1' || true)"

  if [[ -n "$container_json" ]]; then
    host_json_candidate="$REPORTS_DIR/$(basename "$container_json")"
    if [[ -r "$host_json_candidate" ]]; then
      json_mtime="$(stat -c %Y "$host_json_candidate" 2>/dev/null || true)"
      if [[ "$json_mtime" =~ ^[0-9]+$ ]] && (( json_mtime >= run_started_epoch )); then
        last_json_report="$host_json_candidate"
      fi
    fi
  fi

  if [[ -n "$container_md" ]]; then
    host_md_candidate="$REPORTS_DIR/$(basename "$container_md")"
    if [[ -r "$host_md_candidate" ]]; then
      md_mtime="$(stat -c %Y "$host_md_candidate" 2>/dev/null || true)"
      if [[ "$md_mtime" =~ ^[0-9]+$ ]] && (( md_mtime >= run_started_epoch )); then
        last_md_report="$host_md_candidate"
      fi
    fi
  fi
}

if [[ "${1:-}" == "--run-now" ]]; then
  RUN_MODE="manual"
elif [[ -n "${1:-}" && "${1:-}" != "--status" && "${1:-}" != "--install-cron" && "${1:-}" != "--remove-cron" && "${1:-}" != "--print-cron-preset" && "${1:-}" != "--help" && "${1:-}" != "-h" ]]; then
  echo "unknown option: ${1}" >&2
  print_help
  exit 2
fi

if [[ "${1:-}" == "--status" ]]; then
  require_cmds
  print_status
  exit 0
fi

if [[ "${1:-}" == "--install-cron" ]]; then
  require_cmds
  install_crontab_entry
  exit 0
fi

if [[ "${1:-}" == "--remove-cron" ]]; then
  require_cmds
  remove_crontab_entry
  exit 0
fi

if [[ "${1:-}" == "--print-cron-preset" ]]; then
  print_stable_cron_preset
  exit 0
fi

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  print_help
  exit 0
fi

require_cmds
check_runtime_prereqs
if ! check_mcp_from_hermes; then
  exit 2
fi
if ! check_hermes_mcp_bootstrap; then
  if [[ "$HERMES_MCP_BOOTSTRAP_STRICT" == "true" ]]; then
    exit 2
  fi
  echo "warning: hermes mcp bootstrap check is below threshold; continuing because HERMES_MCP_BOOTSTRAP_STRICT=false" >&2
fi

if [[ "$RUN_MODE" == "manual" ]]; then
  acquire_single_run_lock "$LOCK_WAIT_SECONDS"
else
  acquire_single_run_lock
fi

load_state
cycle_count=$((cycle_count + 1))
last_run_at="$(date -Iseconds)"
run_started_epoch="$(date +%s)"
run_log="$STATE_DIR/run_${cycle_count}.log"
touch "$run_log"
{
  echo "[$(date -Iseconds)] cycle=$cycle_count status=started run_mode=$RUN_MODE"
  echo "watchlist=${WATCHLIST_TICKERS}"
} > "$run_log"
RUN_TIMEOUT_SECONDS="${RUN_TIMEOUT_SECONDS:-1500}"

orders_before="$(get_alpaca_orders_count 2>/dev/null || true)"
if [[ ! "$orders_before" =~ ^[0-9]+$ ]]; then
  last_status="failed"
  last_exit_code="orders-before-check-failed"
  append_alpaca_orders_diagnostics "orders-before"
  detect_latest_report_artifacts
  persist_state
  write_failure_report
  {
    echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code duration_seconds=$(cycle_duration_seconds)"
  } >> "$LOG_FILE"
  exit 1
fi

max_order_attempts="$ORDER_RETEST_ATTEMPTS"
order_retest_delay="$ORDER_RETEST_DELAY_SECONDS"
max_timeout_attempts="$TIMEOUT_RETEST_ATTEMPTS"
timeout_retest_delay="$TIMEOUT_RETEST_DELAY_SECONDS"
max_mcp_unready_attempts="$MCP_UNREADY_RECOVERY_ATTEMPTS"
[[ "$max_order_attempts" =~ ^[0-9]+$ ]] || max_order_attempts=2
[[ "$order_retest_delay" =~ ^[0-9]+$ ]] || order_retest_delay=5
[[ "$max_timeout_attempts" =~ ^[0-9]+$ ]] || max_timeout_attempts=1
[[ "$timeout_retest_delay" =~ ^[0-9]+$ ]] || timeout_retest_delay=8
[[ "$max_mcp_unready_attempts" =~ ^[0-9]+$ ]] || max_mcp_unready_attempts=1
(( max_order_attempts >= 0 )) || max_order_attempts=0
(( order_retest_delay >= 0 )) || order_retest_delay=5
(( max_timeout_attempts >= 0 )) || max_timeout_attempts=1
(( timeout_retest_delay >= 0 )) || timeout_retest_delay=8
(( max_mcp_unready_attempts >= 0 )) || max_mcp_unready_attempts=1
max_order_attempts=$((max_order_attempts + 1))
max_timeout_attempts=$((max_timeout_attempts + 1))
max_mcp_unready_attempts=$((max_mcp_unready_attempts + 1))
effective_mcp_servers="$(build_effective_mcp_servers)"
echo "effective_mcp_servers=${effective_mcp_servers}" >> "$run_log"

attempt_index=1
timeout_attempt_index=1
mcp_unready_attempt_index=1
order_delta_verified=false
DIRECT_FALLBACK_EXECUTED_WRITE="false"
DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED="true"
while true; do
  if ! ensure_hermes_ready_for_attempt; then
    if (( mcp_unready_attempt_index < max_mcp_unready_attempts )); then
      {
        echo "[$(date -Iseconds)] cycle=$cycle_count status=retest reason=hermes-mcp-unready mcp_unready_attempt=$mcp_unready_attempt_index/$max_mcp_unready_attempts duration_seconds=$(cycle_duration_seconds)"
        docker logs "$HERMES_CONTAINER" --tail=40 2>&1 || true
      } >> "$LOG_FILE"
      recover_mcp_stack_after_unready
      mcp_unready_attempt_index=$((mcp_unready_attempt_index + 1))
      continue
    fi

    last_status="failed"
    last_exit_code="hermes-mcp-unready"
    detect_latest_report_artifacts
    capture_invalid_report_artifacts
    persist_state
    write_failure_report
    {
      echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code attempt=$attempt_index/$max_order_attempts timeout_attempt=$timeout_attempt_index/$max_timeout_attempts mcp_unready_attempt=$mcp_unready_attempt_index/$max_mcp_unready_attempts duration_seconds=$(cycle_duration_seconds)"
      docker logs "$HERMES_CONTAINER" --tail=40 2>&1 || true
    } >> "$LOG_FILE"
    exit 1
  fi

  prewarm_hermes_persistent_ready || true

  set +e
  command_exit_code=255
  if [[ "$DIRECT_ALPACA_ONLY_MODE" == "true" ]]; then
    execute_direct_alpaca_fallback_write >> "$run_log" 2>&1
    command_exit_code=$?
    echo "[$(date -Iseconds)] direct_only_mode=true direct_fallback_exit_code=$command_exit_code" >> "$run_log"
  else
    final_prompt="$PROMPT"
    if [[ "$FINANCIAL_STRATEGY_ENABLED" == "true" ]] && [[ -n "$FINANCIAL_STRATEGY_FILE" ]]; then
      IFS=',' read -r -a strategy_files <<< "$FINANCIAL_STRATEGY_FILE"
      strategy_sections=""
      for strategy_entry in "${strategy_files[@]}"; do
        strategy_entry="${strategy_entry//[$'\r\n']/}"
        strategy_entry="$(echo "$strategy_entry" | xargs)"
        [[ -z "$strategy_entry" ]] && continue

        strategy_path=""
        if [[ "$strategy_entry" = /* ]]; then
          strategy_path="$strategy_entry"
        else
          strategy_path="$ROOT/docs/strategies/$strategy_entry"
        fi
        if [[ -f "$strategy_path" ]]; then
          strategy_content="$(cat "$strategy_path")"
          strategy_sections+="

=== FINANCIAL STRATEGY ===
Source: docs/strategies/$(basename "$strategy_path")

$strategy_content"
        fi
      done
      if [[ -n "$strategy_sections" ]]; then
        final_prompt="$PROMPT$strategy_sections"
      fi
    fi
    timeout --signal=TERM --kill-after=30 "$RUN_TIMEOUT_SECONDS" \
      docker exec \
      -e HERMES_ONESHOT_PROMPT="$final_prompt" \
      -e HERMES_MCP_SERVERS="$effective_mcp_servers" \
      -e MCP_SERVERS="$effective_mcp_servers" \
      "$HERMES_CONTAINER" \
      sh -lc '/opt/hermes/bin/hermes --oneshot "$HERMES_ONESHOT_PROMPT"' >> "$run_log" 2>&1
    command_exit_code=$?
  fi
  set -e
  printf '[%s] oneshot_exit_code=%s\n' "$(date -Iseconds)" "$command_exit_code" >> "$run_log"

  if [[ ${command_exit_code:-255} -ne 0 ]]; then
    last_status="failed"
    detect_latest_report_artifacts
    capture_invalid_report_artifacts
    if [[ ${command_exit_code:-255} -eq 124 || ${command_exit_code:-255} -eq 143 || ${command_exit_code:-255} -eq 137 ]]; then
      timeout_recovered_with_fallback="false"
      if [[ ! -s "$run_log" ]]; then
        append_timeout_diagnostics
      fi
      if [[ "$DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE" == "true" ]] && execute_direct_alpaca_fallback_write >> "$run_log" 2>&1; then
        echo "[$(date -Iseconds)] cycle=$cycle_count status=recovery action=direct-alpaca-fallback reason=oneshot-timeout result=success duration_seconds=$(cycle_duration_seconds)" >> "$LOG_FILE"
        last_status="success"
        last_exit_code="0"
        command_exit_code=0
        timeout_recovered_with_fallback="true"
      else
        last_exit_code="timeout"
      fi
      recover_hermes_after_timeout
      if [[ "$timeout_recovered_with_fallback" == "true" ]]; then
        echo "[$(date -Iseconds)] cycle=$cycle_count status=recovery action=hermes-timeout-cleanup result=success reason=post-timeout-fallback duration_seconds=$(cycle_duration_seconds)" >> "$LOG_FILE"
      fi
    elif [[ ! -s "$run_log" ]]; then
      last_exit_code="empty-run-log"
    elif grep -Fq "no final response was produced" "$run_log"; then
      last_exit_code="no-final-response"
    else
      last_exit_code="$command_exit_code"
    fi

    if [[ ${command_exit_code:-255} -ne 0 ]]; then
      if [[ "$last_exit_code" == "timeout" ]] && (( timeout_attempt_index < max_timeout_attempts )); then
        {
          echo "[$(date -Iseconds)] cycle=$cycle_count status=retest reason=timeout timeout_attempt=$timeout_attempt_index/$max_timeout_attempts duration_seconds=$(cycle_duration_seconds)"
          tail -n 20 "$run_log"
        } >> "$LOG_FILE"
        timeout_attempt_index=$((timeout_attempt_index + 1))
        if (( timeout_retest_delay > 0 )); then
          timeout "$timeout_retest_delay" tail -f /dev/null >/dev/null 2>&1 || true
        fi
        continue
      fi

      persist_state
      write_failure_report
      {
        echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code attempt=$attempt_index/$max_order_attempts timeout_attempt=$timeout_attempt_index/$max_timeout_attempts duration_seconds=$(cycle_duration_seconds)"
        tail -n 40 "$run_log"
      } >> "$LOG_FILE"
      exit "${command_exit_code:-255}"
    fi
  fi

  if [[ ! -s "$run_log" ]]; then
    last_status="failed"
    last_exit_code="empty-run-log"
    detect_latest_report_artifacts
    persist_state
    write_failure_report
    {
      echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code orders_before=$orders_before attempt=$attempt_index/$max_order_attempts duration_seconds=$(cycle_duration_seconds)"
    } >> "$LOG_FILE"
    exit 1
  fi

  if grep -Fq "no final response was produced" "$run_log"; then
    last_status="failed"
    last_exit_code="no-final-response"
    detect_latest_report_artifacts
    capture_invalid_report_artifacts
    persist_state
    write_failure_report
    {
      echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code orders_before=$orders_before attempt=$attempt_index/$max_order_attempts duration_seconds=$(cycle_duration_seconds)"
      tail -n 40 "$run_log"
    } >> "$LOG_FILE"
    exit 1
  fi

  if grep -Eiq "$INVALID_EXECUTION_PATTERN" "$run_log"; then
    if [[ "$DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE" == "true" ]] && execute_direct_alpaca_fallback_write; then
      echo "[$(date -Iseconds)] cycle=$cycle_count status=recovery action=direct-alpaca-fallback reason=invalid-execution-path result=success duration_seconds=$(cycle_duration_seconds)" >> "$LOG_FILE"
    else
      last_status="failed"
      last_exit_code="invalid-execution-path"
      detect_latest_report_artifacts
      capture_invalid_report_artifacts
      persist_state
      write_failure_report
      {
        echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code orders_before=$orders_before attempt=$attempt_index/$max_order_attempts duration_seconds=$(cycle_duration_seconds)"
        tail -n 40 "$run_log"
      } >> "$LOG_FILE"
      exit 1
    fi
  fi

  if grep -Eiq "$SIMULATION_PATTERN" "$run_log"; then
    if [[ "$DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE" == "true" ]] && execute_direct_alpaca_fallback_write; then
      echo "[$(date -Iseconds)] cycle=$cycle_count status=recovery action=direct-alpaca-fallback reason=simulation-detected result=success duration_seconds=$(cycle_duration_seconds)" >> "$LOG_FILE"
    else
      last_status="failed"
      last_exit_code="simulated-execution-detected"
      last_json_report=""
      last_md_report=""
      capture_invalid_report_artifacts
      persist_state
      write_failure_report
      {
        echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code orders_before=$orders_before attempt=$attempt_index/$max_order_attempts duration_seconds=$(cycle_duration_seconds)"
        tail -n 40 "$run_log"
      } >> "$LOG_FILE"
      exit 1
    fi
  fi

  # Hard gate: only proceed if run log contains evidence of a real Alpaca MCP write call and UUID order id.
  if [[ "$DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED" == "true" ]] && ( ! grep -Eiq "$REQUIRED_MCP_WRITE_PATTERN" "$run_log" || ! grep -Eq "$UUID_ORDER_ID_PATTERN" "$run_log" ); then
    if [[ "$DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE" == "true" ]] && execute_direct_alpaca_fallback_write; then
      echo "[$(date -Iseconds)] cycle=$cycle_count status=recovery action=direct-alpaca-fallback reason=missing-write-evidence result=success duration_seconds=$(cycle_duration_seconds)" >> "$LOG_FILE"
    fi
  fi

  if [[ "$DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED" == "true" ]] && ( ! grep -Eiq "$REQUIRED_MCP_WRITE_PATTERN" "$run_log" || ! grep -Eq "$UUID_ORDER_ID_PATTERN" "$run_log" ); then
    last_status="failed"
    last_exit_code="missing-real-mcp-write-evidence"
    last_json_report=""
    last_md_report=""
    capture_invalid_report_artifacts
    persist_state
    write_failure_report
    {
      echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code orders_before=$orders_before attempt=$attempt_index/$max_order_attempts duration_seconds=$(cycle_duration_seconds)"
      tail -n 40 "$run_log"
    } >> "$LOG_FILE"
    exit 1
  fi

  orders_after="$(get_alpaca_orders_count 2>/dev/null || true)"
  if [[ ! "$orders_after" =~ ^[0-9]+$ ]]; then
    last_status="failed"
    last_exit_code="orders-after-check-failed"
    last_json_report=""
    last_md_report=""
    append_alpaca_orders_diagnostics "orders-after"
    capture_invalid_report_artifacts
    persist_state
    write_failure_report
    {
      echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code orders_before=$orders_before attempt=$attempt_index/$max_order_attempts duration_seconds=$(cycle_duration_seconds)"
      tail -n 40 "$run_log"
    } >> "$LOG_FILE"
    exit 1
  fi

  if (( orders_after > orders_before )); then
    order_delta_verified=true
    break
  fi

  if [[ "$DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED" != "true" ]]; then
    order_delta_verified=true
    echo "[$(date -Iseconds)] cycle=$cycle_count status=success reason=no-write-expected action=${DIRECT_FALLBACK_ACTION:-hold} orders_before=$orders_before orders_after=$orders_after duration_seconds=$(cycle_duration_seconds)" >> "$LOG_FILE"
    break
  fi

  if (( attempt_index < max_order_attempts )); then
    {
      echo "[$(date -Iseconds)] cycle=$cycle_count status=retest reason=no-new-order attempt=$attempt_index/$max_order_attempts orders_before=$orders_before orders_after=$orders_after duration_seconds=$(cycle_duration_seconds)"
      tail -n 20 "$run_log"
    } >> "$LOG_FILE"
    attempt_index=$((attempt_index + 1))
    if (( order_retest_delay > 0 )); then
      timeout "$order_retest_delay" tail -f /dev/null >/dev/null 2>&1 || true
    fi
    continue
  fi

  last_status="failed"
  last_exit_code="no-new-order"
  last_json_report=""
  last_md_report=""
  capture_invalid_report_artifacts
  persist_state
  write_failure_report
  {
    echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code orders_before=$orders_before orders_after=$orders_after attempt=$attempt_index/$max_order_attempts duration_seconds=$(cycle_duration_seconds)"
    tail -n 40 "$run_log"
  } >> "$LOG_FILE"
  exit 1
done

# Explicitly require order count growth before parsing/accepting reported order metadata.
if [[ "$order_delta_verified" != "true" ]]; then
  last_status="failed"
  last_exit_code="order-delta-not-verified"
  last_json_report=""
  last_md_report=""
  capture_invalid_report_artifacts
  persist_state
  write_failure_report
  {
    echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code orders_before=$orders_before orders_after=$orders_after duration_seconds=$(cycle_duration_seconds)"
    tail -n 40 "$run_log"
  } >> "$LOG_FILE"
  exit 1
fi

if [[ "$DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED" != "true" ]]; then
  latest_order_id="none"
  latest_order_status="hold"
  latest_order_symbol="$(primary_watchlist_symbol)"
  latest_order_submitted="$last_run_at"
  latest_order_side="${DIRECT_FALLBACK_ACTION:-hold}"
else
  latest_order_meta="$(get_latest_alpaca_order_meta 2>/dev/null || true)"
  IFS='|' read -r latest_order_id latest_order_status latest_order_symbol latest_order_submitted latest_order_side <<< "$latest_order_meta"
fi

if [[ "$DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED" == "true" ]] && [[ -z "${latest_order_id:-}" || -z "${latest_order_status:-}" ]]; then
  last_status="failed"
  last_exit_code="latest-order-check-failed"
  last_json_report=""
  last_md_report=""
  capture_invalid_report_artifacts
  persist_state
  write_failure_report
  {
    echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code orders_before=$orders_before orders_after=$orders_after duration_seconds=$(cycle_duration_seconds)"
    tail -n 40 "$run_log"
  } >> "$LOG_FILE"
  exit 1
fi

if [[ "$DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED" == "true" ]] && [[ ! "$latest_order_id" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
  last_status="failed"
  last_exit_code="order-id-format-invalid"
  last_json_report=""
  last_md_report=""
  capture_invalid_report_artifacts
  persist_state
  write_failure_report
  {
    echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code order_id=$latest_order_id order_status=$latest_order_status duration_seconds=$(cycle_duration_seconds)"
    tail -n 40 "$run_log"
  } >> "$LOG_FILE"
  exit 1
fi

if [[ "$DIRECT_FALLBACK_WRITE_EVIDENCE_REQUIRED" == "true" ]]; then
  case "$latest_order_status" in
    rejected|canceled|expired|suspended|stopped)
      last_status="failed"
      last_exit_code="latest-order-status-invalid"
      last_json_report=""
      last_md_report=""
      capture_invalid_report_artifacts
      persist_state
      write_failure_report
      {
        echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code order_id=$latest_order_id order_status=$latest_order_status duration_seconds=$(cycle_duration_seconds)"
        tail -n 40 "$run_log"
      } >> "$LOG_FILE"
      exit 1
      ;;
  esac
fi

if grep -Fq "direct_alpaca_fallback_result success=true" "$run_log"; then
  write_direct_fallback_reports "$latest_order_id" "$latest_order_status" "$latest_order_symbol" "$latest_order_submitted" "${DIRECT_FALLBACK_CONFIDENCE:-$BUY_CONFIDENCE_THRESHOLD}" "${DIRECT_FALLBACK_TARGET_NOTIONAL:-$BASE_NOTIONAL_PER_TRADE_USD}" "${DIRECT_FALLBACK_FINAL_QTY:-$MIN_TRADE_QTY}" "${DIRECT_FALLBACK_SIZING_RATIONALE:-minimum trade qty guardrail applied by direct Alpaca fallback write path}" "${DIRECT_FALLBACK_CURRENT_PRICE:-}" "${DIRECT_FALLBACK_ACTION:-buy}" "${DIRECT_FALLBACK_EXECUTED_WRITE:-false}"
fi

latest_json="$(docker exec "$HERMES_CONTAINER" sh -lc 'ls -1t /workspace/reports/investment_analysis_cycle_*.json 2>/dev/null | head -n 1')"
latest_md="$(docker exec "$HERMES_CONTAINER" sh -lc 'ls -1t /workspace/reports/investment_analysis_cycle_*.md 2>/dev/null | head -n 1')"

if [[ -z "$latest_json" || -z "$latest_md" ]]; then
  last_status="failed"
  last_exit_code="missing-report"
  last_json_report="$latest_json"
  last_md_report="$latest_md"
  persist_state
  write_failure_report
  {
    echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code duration_seconds=$(cycle_duration_seconds)"
    tail -n 40 "$run_log"
  } >> "$LOG_FILE"
  exit 1
fi

docker exec "$HERMES_CONTAINER" sh -lc "test -r '$latest_json' && test -r '$latest_md' && head -c 1 '$latest_json' >/dev/null && head -c 1 '$latest_md' >/dev/null"
docker exec "$HERMES_CONTAINER" sh -lc "chmod 644 '$latest_json' '$latest_md'"

host_json="$REPORTS_DIR/$(basename "$latest_json")"
host_md="$REPORTS_DIR/$(basename "$latest_md")"
json_mtime="$(stat -c %Y "$host_json")"
md_mtime="$(stat -c %Y "$host_md")"

if (( json_mtime < run_started_epoch || md_mtime < run_started_epoch )); then
  last_status="failed"
  last_exit_code="stale-report"
  last_json_report="$host_json"
  last_md_report="$host_md"
  persist_state
  write_failure_report
  {
    echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code json_mtime=$json_mtime md_mtime=$md_mtime run_started_epoch=$run_started_epoch duration_seconds=$(cycle_duration_seconds)"
    tail -n 40 "$run_log"
  } >> "$LOG_FILE"
  exit 1
fi

dated_alias="/workspace/reports/$(date +%F)_latest_watchlist_report.json"
docker exec "$HERMES_CONTAINER" sh -lc "cp '$latest_json' '$dated_alias' && chmod 644 '$dated_alias' && test -r '$dated_alias' && head -c 1 '$dated_alias' >/dev/null"

host_alias="$REPORTS_DIR/$(date +%F)_latest_watchlist_report.json"
test -r "$host_json"
test -r "$host_md"
test -r "$host_alias"

if ! validate_report_sizing_metadata "$host_json"; then
  last_status="failed"
  last_exit_code="report-sizing-validation-failed:${report_validation_reason:-unknown}"
  last_json_report="$host_json"
  last_md_report="$host_md"
  persist_state
  write_failure_report
  {
    echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code order_id=$latest_order_id order_status=$latest_order_status order_side=${latest_order_side:-} order_symbol=$latest_order_symbol duration_seconds=$(cycle_duration_seconds)"
    tail -n 40 "$run_log"
  } >> "$LOG_FILE"
  exit 1
fi

last_status="success"
last_exit_code="0"
last_json_report="$host_json"
last_md_report="$host_md"
persist_state

{
  echo "[$last_run_at] cycle=$cycle_count status=$last_status exit_code=$last_exit_code json=$host_json md=$host_md alias=$host_alias order_id=$latest_order_id order_status=$latest_order_status order_side=${latest_order_side:-} order_symbol=$latest_order_symbol order_submitted_at=$latest_order_submitted confidence=${report_validation_confidence:-} target_notional=${report_validation_target_notional:-} final_qty=${report_validation_final_qty:-} sizing_rationale=${report_validation_sizing_rationale:-} orders_before=$orders_before orders_after=$orders_after duration_seconds=$(cycle_duration_seconds)"
  tail -n 20 "$run_log"
} >> "$LOG_FILE"

echo "cycle_count=$cycle_count"
echo "status=$last_status"
echo "duration_seconds=$(cycle_duration_seconds)"
echo "json_report=$host_json"
echo "md_report=$host_md"
echo "latest_alias=$host_alias"
