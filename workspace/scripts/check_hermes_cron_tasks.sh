#!/usr/bin/env bash
set -euo pipefail

# Short monitor for Hermes cron-triggered runs.
# Counts currently running jobs and correlates with CRON CMD lines from syslog.

echo -e "\n=== Starting cronjobs review for Hermes ===\n"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SCRIPT_MATCH="daily_investment_watchlist_report_generator.sh --run-now"
SYSLOG_FILE="${SYSLOG_FILE:-/var/log/syslog}"
LOG_LINES="${LOG_LINES:-3000}"
LOCK_SLOTS_DIR="${LOCK_SLOTS_DIR:-$ROOT/reports/.cron_state/daily_investment_watchlist_report_generator.lock.d}"
MAX_PARALLEL="${MAX_PARAREL_CRONTASKS_RUN:-}"

if ! command -v ps >/dev/null 2>&1; then
  echo "ERROR: ps command not available" >&2
  exit 2
fi

if ! command -v grep >/dev/null 2>&1; then
  echo "ERROR: grep command not available" >&2
  exit 2
fi

mapfile -t RUNNING_LINES < <(ps -eo pid=,etimes=,cmd= | grep -F "$SCRIPT_MATCH" | grep -v -E "grep|check_hermes_cron_tasks\.sh" || true)
RUNNING_COUNT="${#RUNNING_LINES[@]}"

detected_max_parallel=0
for line in "${RUNNING_LINES[@]}"; do
  if [[ "$line" =~ MAX_PARAREL_CRONTASKS_RUN=([0-9]+) ]]; then
    candidate_max="${BASH_REMATCH[1]}"
    if (( candidate_max > detected_max_parallel )); then
      detected_max_parallel="$candidate_max"
    fi
  fi
done

if (( detected_max_parallel > 0 )); then
  MAX_PARALLEL="$detected_max_parallel"
fi

if [[ ! "$MAX_PARALLEL" =~ ^[0-9]+$ ]] || (( MAX_PARALLEL <= 0 )); then
  MAX_PARALLEL=1
fi

echo "running_hermes_cron_tasks=$RUNNING_COUNT"

slot_active=0
slot_stale=0
declare -a SLOT_ACTIVE_LINES=()
declare -a SLOT_STALE_LINES=()

if [[ -d "$LOCK_SLOTS_DIR" ]]; then
  for pid_file in "$LOCK_SLOTS_DIR"/slot_*.pid; do
    [[ -f "$pid_file" ]] || continue
    slot_name="$(basename "$pid_file" .pid)"
    slot_pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ -z "$slot_pid" ]]; then
      slot_stale=$((slot_stale + 1))
      SLOT_STALE_LINES+=("$slot_name pid=missing")
      continue
    fi

    if kill -0 "$slot_pid" 2>/dev/null; then
      slot_active=$((slot_active + 1))
      SLOT_ACTIVE_LINES+=("$slot_name pid=$slot_pid")
    else
      slot_stale=$((slot_stale + 1))
      SLOT_STALE_LINES+=("$slot_name pid=$slot_pid")
    fi
  done
fi

echo "parallel_slots_active=$slot_active"
echo "parallel_slots_max=$MAX_PARALLEL"
echo "parallel_slots_stale=$slot_stale"

echo
if (( RUNNING_COUNT > 0 )); then
  echo "=== Running processes (pid etimes cmd) ==="
  printf '%s\n' "${RUNNING_LINES[@]}"
else
  echo "=== Running processes ==="
  echo "none"
fi

echo
echo "=== Parallel lock slots ==="
if (( slot_active > 0 )); then
  echo "active:"
  printf '%s\n' "${SLOT_ACTIVE_LINES[@]}"
else
  echo "active: none"
fi

if (( slot_stale > 0 )); then
  echo "stale:"
  printf '%s\n' "${SLOT_STALE_LINES[@]}"
else
  echo "stale: none"
fi

echo
if [[ -r "$SYSLOG_FILE" ]]; then
  echo "=== Recent CRON CMD entries (matching Hermes wrapper) ==="
  tail -n "$LOG_LINES" "$SYSLOG_FILE" \
    | grep -E "CRON.*CMD" \
    | grep -F "daily_investment_watchlist_report_generator.sh --run-now" \
    | tail -n 30 || true
else
  echo "=== Recent CRON CMD entries ==="
  echo "cannot read $SYSLOG_FILE (try: sudo SYSLOG_FILE=$SYSLOG_FILE $0)"
fi

echo
if (( RUNNING_COUNT > 0 )) && [[ -r "$SYSLOG_FILE" ]]; then
  echo "=== Possible ticker context from running commands ==="
  printf '%s\n' "${RUNNING_LINES[@]}" | sed -nE "s/.*WATCHLIST_TICKERS='([^']+)'.*/ticker=\1/p" | sort -u || true
fi
