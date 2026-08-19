#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
REPORTS_DIR="$ROOT/reports"
STATE_DIR="$REPORTS_DIR/.cron_state"
HOURLY_DIR="$REPORTS_DIR/hourly_watchlist"
SCRIPT_PATH="$ROOT/scripts/hourly_watchlist_runtime_report.sh"
STATE_FILE="$STATE_DIR/hourly_watchlist_runtime_report.state"

mkdir -p "$STATE_DIR" "$HOURLY_DIR"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--run-now|--help]

Options:
  --run-now   Generate one hourly runtime report now.
  --help      Show this help.
EOF
}

fetch_account_snapshot() {
  local output
  if output="$(python3 - <<'PY' 2>/dev/null
import json
import urllib.request

url = "http://127.0.0.1:3003/mcp"
payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "account_get", "arguments": {}}
}
req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=20) as resp:
    body = json.loads(resp.read().decode())
content = body.get("result", {}).get("content", [])
if not content:
    print("n/a\tn/a")
    raise SystemExit(0)
text_payload = content[0].get("text", "{}")
acct = json.loads(text_payload)
cash = acct.get("cash", "n/a")
bp = acct.get("buying_power", "n/a")
print(f"{cash}\t{bp}")
PY
)"; then
    echo "$output"
  else
    echo "n/a	n/a"
  fi
}

derive_run_status() {
  local file="$1"

  if ! [[ -f "$file" ]]; then
    echo "missing"
    return
  fi

  if ! rg -q "oneshot_exit_code=" "$file"; then
    echo "running"
    return
  fi

  if rg -q "oneshot_exit_code=124" "$file"; then
    echo "timeout"
    return
  fi

  if rg -qi '"status"[[:space:]]*:[[:space:]]*"FAILURE"|simulat|confirmation_required|no real write|failed' "$file"; then
    echo "failed"
    return
  fi

  if rg -qi '"order_id"[[:space:]]*:[[:space:]]*"[0-9a-fA-F-]{36}"|result=OK order_id=' "$file"; then
    echo "success"
    return
  fi

  if rg -q "oneshot_exit_code=0" "$file"; then
    echo "completed"
    return
  fi

  echo "unknown"
}

generate_report() {
  local now_iso now_epoch hour_key prev_hour_key next_hour_key
  now_iso="$(date -Iseconds)"
  now_epoch="$(date +%s)"
  hour_key="$(date +"%Y%m%d_%H00")"
  prev_hour_key="$(date -d "1 hour ago" +"%Y%m%d_%H00")"
  next_hour_key="$(date -d "1 hour" +"%Y%m%d_%H00")"

  local report_file prev_report next_report
  report_file="$HOURLY_DIR/hourly_watchlist_${hour_key}.md"
  prev_report="$HOURLY_DIR/hourly_watchlist_${prev_hour_key}.md"
  next_report="$HOURLY_DIR/hourly_watchlist_${next_hour_key}.md"

  local start_cash="n/a"
  local start_bp="n/a"
  if [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE" || true
    start_cash="${last_end_cash:-n/a}"
    start_bp="${last_end_buying_power:-n/a}"
  fi

  local end_snapshot end_cash end_bp
  end_snapshot="$(fetch_account_snapshot)"
  IFS=$'\t' read -r end_cash end_bp <<< "$end_snapshot"

  local proc_count
  proc_count="$(ps -eo args | egrep "investment-analyst|daily_investment|hermes --oneshot|timeout --signal=TERM --kill-after=30|HERMES_ONESHOT_PROMPT=Use" | grep -v grep | wc -l | tr -d ' ')"

  mapfile -t run_files < <(find "$STATE_DIR" -maxdepth 1 -type f -name 'run_*.log' -mmin -60 | sort -V)
  local run_count="${#run_files[@]}"

  local run_ids_csv=""
  local runs_block=""
  local failed_artifacts_block=""
  local success_artifacts_block=""
  local run_log_rel failed_artifact_abs failed_artifact_rel success_json_abs success_md_abs success_json_rel success_md_rel
  local file base run_id status
  for file in "${run_files[@]}"; do
    base="$(basename "$file")"
    run_id="${base#run_}"
    run_id="${run_id%.log}"
    status="$(derive_run_status "$file")"
    run_log_rel="../.cron_state/$base"
    failed_artifact_abs="$REPORTS_DIR/failed_watchlist_report_cycle_${run_id}.json"
    failed_artifact_rel="../failed_watchlist_report_cycle_${run_id}.json"

    if [[ -z "$run_ids_csv" ]]; then
      run_ids_csv="[$run_id]($run_log_rel)"
    else
      run_ids_csv="$run_ids_csv, [$run_id]($run_log_rel)"
    fi

    runs_block+="| [$run_id]($run_log_rel) | $status | [$run_log_rel]($run_log_rel) |"$'\n'

    if [[ -f "$failed_artifact_abs" ]]; then
      failed_artifacts_block+="- Run [$run_id]($run_log_rel): [$failed_artifact_rel]($failed_artifact_rel)"$'\n'
    fi

    success_json_abs="$(grep -Eo 'json=/[^[:space:]]*investment_analysis_cycle_[0-9_]+\.json' "$file" | tail -n1 | cut -d= -f2- || true)"
    success_md_abs="$(grep -Eo 'md=/[^[:space:]]*investment_analysis_cycle_[0-9_]+\.md' "$file" | tail -n1 | cut -d= -f2- || true)"
    if [[ -n "$success_json_abs" && -f "$success_json_abs" ]]; then
      success_json_rel="../$(basename "$success_json_abs")"
      if [[ -n "$success_md_abs" && -f "$success_md_abs" ]]; then
        success_md_rel="../$(basename "$success_md_abs")"
        success_artifacts_block+="- Run [$run_id]($run_log_rel): [$success_json_rel]($success_json_rel), [$success_md_rel]($success_md_rel)"$'\n'
      else
        success_artifacts_block+="- Run [$run_id]($run_log_rel): [$success_json_rel]($success_json_rel)"$'\n'
      fi
    elif [[ -n "$success_md_abs" && -f "$success_md_abs" ]]; then
      success_md_rel="../$(basename "$success_md_abs")"
      success_artifacts_block+="- Run [$run_id]($run_log_rel): [$success_md_rel]($success_md_rel)"$'\n'
    fi
  done

  if [[ -z "$run_ids_csv" ]]; then
    run_ids_csv="none"
    runs_block="| none | n/a | n/a |"
  fi

  local prev_name next_name
  prev_name="$(basename "$prev_report")"
  next_name="$(basename "$next_report")"

  cat > "$report_file" <<EOF
# Hourly Watchlist Runtime Report

- Generated at: $now_iso
- Window: last 60 minutes
- Runs in last hour: $run_count
- Run IDs: $run_ids_csv
- Start Cash: $start_cash
- Start Buying Power: $start_bp
- End Cash: $end_cash
- End Buying Power: $end_bp
- Active matching processes now: $proc_count
- Previous hourly report: [$prev_name](./$prev_name)
- Next hourly report: [$next_name](./$next_name)

## Runs
| Run ID | Derived status | Log file |
|---|---|---|
$runs_block

${failed_artifacts_block:+## Failure Artifacts
$failed_artifacts_block}

${success_artifacts_block:+## Success Artifacts
$success_artifacts_block}
EOF

  cat > "$STATE_FILE" <<EOF
last_report_file='$report_file'
last_end_cash='$end_cash'
last_end_buying_power='$end_bp'
last_generated_at='$now_iso'
EOF

  echo "generated_report=$report_file"
}

case "${1:-}" in
  --help)
    usage
    ;;
  --run-now|"")
    generate_report
    ;;
  *)
    echo "Unknown option: $1" >&2
    usage
    exit 2
    ;;
esac
