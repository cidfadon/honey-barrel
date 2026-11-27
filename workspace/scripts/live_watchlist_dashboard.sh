#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

CRON_SNAPSHOT_FILE="${CRON_SNAPSHOT_FILE:-$ROOT/reports/.cron_state/crontab_mbednarski.txt}"
REPORTS_DIR="${REPORTS_DIR:-$ROOT/reports}"
REFRESH_SECONDS="${REFRESH_SECONDS:-20}"

print_usage() {
  cat <<'EOF'
Usage:
  live_watchlist_dashboard.sh [--once] [--watch] [--trading-only] [--refresh-seconds N]

Options:
  --once               Print one snapshot and exit (default).
  --watch              Refresh continuously using watch(1).
  --trading-only       Show only BUY/SELL rows (hide HOLD and NO_DATA rows).
  --refresh-seconds N  Refresh interval for --watch mode (default: 20).

Environment:
  CRON_SNAPSHOT_FILE   Path to cron snapshot file.
  REPORTS_DIR          Path to reports directory.
  REFRESH_SECONDS      Default refresh interval for --watch.
EOF
}

MODE="once"
TRADING_ONLY="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --once)
      MODE="once"
      shift
      ;;
    --watch)
      MODE="watch"
      shift
      ;;
    --trading-only)
      TRADING_ONLY="true"
      shift
      ;;
    --refresh-seconds)
      REFRESH_SECONDS="${2:-}"
      [[ "$REFRESH_SECONDS" =~ ^[0-9]+$ ]] || {
        echo "invalid --refresh-seconds value" >&2
        exit 2
      }
      shift 2
      ;;
    --help|-h)
      print_usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      print_usage
      exit 2
      ;;
  esac
done

render_snapshot() {
  python3 - "$CRON_SNAPSHOT_FILE" "$REPORTS_DIR" "$TRADING_ONLY" <<'PY'
import glob
import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

cron_file = sys.argv[1]
reports_dir = sys.argv[2]
trading_only = sys.argv[3].lower() == "true"

if not os.path.isfile(cron_file):
  print("+-------------------------------------------------------------+")
  print("| Live Watchlist Dashboard                                    |")
  print("+-------------------------------------------------------------+")
  print(f"Cron snapshot not found: {cron_file}")
  sys.exit(1)

with open(cron_file, encoding="utf-8", errors="ignore") as f:
  text = f.read()

tickers = []
for m in re.finditer(r"WATCHLIST_TICKERS='([^']+)'", text):
  t = m.group(1).strip().upper()
  if t and t not in tickers:
    tickers.append(t)

report_pattern = os.path.join(reports_dir, "investment_analysis_cycle_*.json")
reports = sorted(glob.glob(report_pattern), key=os.path.getmtime, reverse=True)

latest = {}
for path in reports:
  try:
    with open(path, encoding="utf-8") as f:
      d = json.load(f)
  except Exception:
    continue

  sym = str(d.get("symbol", "")).upper().strip()
  if not sym or sym not in tickers or sym in latest:
    continue

  action = str(d.get("action") or d.get("order_status") or "").upper().strip()
  status = str(d.get("order_status", "")).upper().strip()
  if action not in {"BUY", "SELL", "HOLD"}:
    if status in {"BUY", "SELL", "HOLD"}:
      action = status
    elif status == "ACCEPTED":
      side = str(d.get("action", "")).upper().strip() or "TRADE"
      action = side
    else:
      action = action or status or "UNKNOWN"

  latest[sym] = {
    "action": action,
    "status": status or "unknown",
    "submitted_at": str(d.get("submitted_at", "")),
    "file": os.path.relpath(path),
  }

  if len(latest) == len(tickers):
    break

now_local = datetime.now().astimezone()
now_ny = datetime.now(ZoneInfo("America/New_York"))

is_weekday = now_ny.weekday() < 5
open_h, open_m = 9, 30
close_h, close_m = 16, 0
mins = now_ny.hour * 60 + now_ny.minute
market_open = is_weekday and (open_h * 60 + open_m) <= mins < (close_h * 60 + close_m)

status_text = "OPEN" if market_open else "CLOSED"

counts = {"BUY": 0, "SELL": 0, "HOLD": 0, "OTHER": 0, "NO_DATA": 0}
for t in tickers:
  row = latest.get(t)
  if not row:
    counts["NO_DATA"] += 1
    continue
  action = row["action"]
  if action in counts:
    counts[action] += 1
  else:
    counts["OTHER"] += 1

line = "+-------------------------------------------------------------------------------------------+"
print(line)
print("| Live Watchlist Dashboard                                                                  |")
print(line)
print(f" Local time : {now_local.strftime('%Y-%m-%d %H:%M:%S %Z (%z)')}")
print(f" NY time    : {now_ny.strftime('%Y-%m-%d %H:%M:%S %Z (%z)')}  | Market: {status_text}")
print(f" Source     : {os.path.relpath(cron_file)}")
print(f" Tickers    : {len(tickers)} | BUY {counts['BUY']} | SELL {counts['SELL']} | HOLD {counts['HOLD']} | NO_DATA {counts['NO_DATA']}")
if trading_only:
  print(" View       : TRADING ONLY (BUY/SELL)")
print(line)
print(f" {'Ticker':<7} {'Signal':<8} {'Submitted At':<30} {'Report Link'}")
print(line)

def sort_key(t):
  row = latest.get(t)
  if not row:
    return (4, t)
  action = row["action"]
  pri = {"BUY": 0, "SELL": 1, "HOLD": 2}.get(action, 3)
  return (pri, t)

for t in sorted(tickers, key=sort_key):
  row = latest.get(t)
  if not row:
    if trading_only:
      continue
    print(f" {t:<7} {'NO_DATA':<8} {'-':<30} -")
    continue
  if trading_only and row["action"] not in {"BUY", "SELL"}:
    continue
  print(f" {t:<7} {row['action']:<8} {row['submitted_at']:<30} {row['file']}")

print(line)
print(" Tip: in VS Code terminal, Ctrl+Click path in 'Report Link' opens the report file.")
PY
}

if [[ "$MODE" == "watch" ]]; then
  command -v watch >/dev/null 2>&1 || {
    echo "watch command not found. Use --once or install watch." >&2
    exit 2
  }
  export CRON_SNAPSHOT_FILE REPORTS_DIR TRADING_ONLY
  if [[ "$TRADING_ONLY" == "true" ]]; then
    exec watch -n "$REFRESH_SECONDS" bash "$0" --once --trading-only
  fi
  exec watch -n "$REFRESH_SECONDS" bash "$0" --once
fi

render_snapshot
