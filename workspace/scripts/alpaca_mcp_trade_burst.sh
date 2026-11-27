#!/usr/bin/env bash

## Aggressive Alpaca MCP trade burst script.
## This script is designed to perform a burst of Alpaca MCP trade orders using the Hermes agent.

set -euo pipefail

# Aggressive Alpaca MCP burst (paper-safe if ALPACA_MODE=paper in container).
# Sends alternating BUY/SELL market orders via MCP endpoint and verifies real order_id UUIDs.

HERMES_CONTAINER="${HERMES_CONTAINER_NAME:-hermes}"
ALPACA_MCP_CONTAINER="${ALPACA_MCP_CONTAINER_NAME:-alpaca-mcp}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
AUDIT_DIR="${MCP_AUDIT_DIR:-$ROOT/reports/.cron_state}"
AUDIT_FILE="${MCP_AUDIT_FILE:-$AUDIT_DIR/alpaca_mcp_calls_$(date +%Y%m%d_%H%M%S).log}"
SYMBOLS_STR="${BURST_SYMBOLS:-AAPL GOOGL AMZN NVDA MRVL SPCX}"
BURST_ROUNDS="${BURST_ROUNDS:-2}"
BURST_BOTH_SIDES="${BURST_BOTH_SIDES:-false}"
BUY_CONFIDENCE_THRESHOLD="${BUY_CONFIDENCE_THRESHOLD:-0.60}"
BASE_NOTIONAL_PER_TRADE_USD="${BASE_NOTIONAL_PER_TRADE_USD:-25}"
MAX_NOTIONAL_PER_SYMBOL_USD="${MAX_NOTIONAL_PER_SYMBOL_USD:-150}"
MIN_TRADE_QTY="${MIN_TRADE_QTY:-0.01}"
QTY_STEP="${QTY_STEP:-0.01}"
BURST_DEFAULT_CONFIDENCE="${BURST_DEFAULT_CONFIDENCE:-0.70}"
BURST_CONFIDENCE_MAP="${BURST_CONFIDENCE_MAP:-AAPL=0.74,GOOGL=0.72,AMZN=0.71,NVDA=0.84,MRVL=0.79,SPCX=0.68}"
SIM_PATTERN='simulat|mock_|MOCK_|ORDER_[0-9]{10,}_|YYYY-MM-DD|No trade executed|tool limitations'
UUID_PATTERN='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 2; }
}

log_mcp_call() {
  local symbol="$1"
  local side="$2"
  local result="$3"
  local order_id="$4"
  local reason="$5"
  local response="$6"
  local confidence="${7:-}"
  local target_notional="${8:-}"
  local final_qty="${9:-}"
  local now response_one_line

  now="$(date -Iseconds)"
  response_one_line="$(printf '%s' "$response" | tr '\n' ' ' | sed -E 's/[[:space:]]+/ /g' | cut -c1-600)"
  {
    echo "[$now] symbol=$symbol side=$side result=$result order_id=$order_id reason=$reason confidence=$confidence target_notional=$target_notional final_qty=$final_qty"
    echo "response=$response_one_line"
  } >> "$AUDIT_FILE"
}

get_symbol_confidence() {
  local symbol="$1"
  local map_entry
  IFS=',' read -r -a map_entries <<< "$BURST_CONFIDENCE_MAP"
  for map_entry in "${map_entries[@]}"; do
    if [[ "$map_entry" == "$symbol="* ]]; then
      printf '%s' "${map_entry#*=}"
      return 0
    fi
  done
  printf '%s' "$BURST_DEFAULT_CONFIDENCE"
}

get_confidence_multiplier() {
  local confidence="$1"
  awk -v c="$confidence" 'BEGIN {
    if (c < 0.60) print "0.0";
    else if (c < 0.70) print "1.0";
    else if (c < 0.80) print "1.5";
    else if (c < 0.90) print "2.0";
    else print "3.0";
  }'
}

get_latest_quote_price() {
  local symbol="$1"
  docker exec -e SYMBOL="$symbol" "$ALPACA_MCP_CONTAINER" python -c "import os, json, urllib.request; payload={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'quote_latest','arguments':{'symbol':os.environ['SYMBOL']}}}; req=urllib.request.Request('http://127.0.0.1:3001/mcp', data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'}); data=json.load(urllib.request.urlopen(req)); text=data['result']['content'][0]['text']; quote=json.loads(text); price=quote.get('bid_price') or quote.get('ask_price') or 0; print(price)" 2>/dev/null || true
}

compute_target_notional() {
  local confidence="$1"
  local multiplier
  multiplier="$(get_confidence_multiplier "$confidence")"
  awk -v base="$BASE_NOTIONAL_PER_TRADE_USD" -v maxn="$MAX_NOTIONAL_PER_SYMBOL_USD" -v mult="$multiplier" 'BEGIN {
    val = base * mult;
    if (val > maxn) val = maxn;
    printf "%.2f", val;
  }'
}

compute_final_qty() {
  local target_notional="$1"
  local latest_price="$2"
  awk -v notional="$target_notional" -v price="$latest_price" -v minq="$MIN_TRADE_QTY" -v step="$QTY_STEP" 'BEGIN {
    if (price <= 0) { print "0"; exit }
    raw = notional / price;
    floored = int(raw / step) * step;
    if (floored > 0 && floored < minq) floored = minq;
    if (floored <= 0) { print "0"; exit }
    printf "%.2f", floored;
  }'
}

get_orders_count() {
  docker exec "$ALPACA_MCP_CONTAINER" python -c "import os; from alpaca.trading.client import TradingClient; from alpaca.trading.requests import GetOrdersRequest; from alpaca.trading.enums import QueryOrderStatus; c=TradingClient(os.environ['ALPACA_API_KEY_ID'], os.environ['ALPACA_API_SECRET_KEY'], paper=(os.environ.get('ALPACA_MODE','paper')=='paper')); print(len(c.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.ALL, limit=500))))"
}

place_market_order_mcp() {
  local symbol="$1"
  local side="$2"
  local confidence="$3"
  local target_notional="$4"
  local final_qty="$5"
  local payload response order_id reason

  payload=$(printf '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"order_place_market","arguments":{"symbol":"%s","qty":%s,"side":"%s","time_in_force":"day"}}}' "$symbol" "$final_qty" "$side")

  response="$(docker exec "$HERMES_CONTAINER" sh -lc "curl -fsS -X POST http://alpaca-mcp:3001/mcp -H 'Content-Type: application/json' -d '$payload'" 2>/dev/null || true)"

  if [[ -z "$response" ]]; then
    log_mcp_call "$symbol" "$side" "FAIL" "" "empty-response" "$response" "$confidence" "$target_notional" "$final_qty"
    echo "FAIL symbol=$symbol side=$side reason=empty-response"
    return 1
  fi

  if printf '%s' "$response" | grep -Eiq "$SIM_PATTERN"; then
    log_mcp_call "$symbol" "$side" "FAIL" "" "simulated-pattern-detected" "$response" "$confidence" "$target_notional" "$final_qty"
    echo "FAIL symbol=$symbol side=$side reason=simulated-pattern-detected"
    return 1
  fi

  # MCP response can include UUID in several places (order_id, nested order.id, existing_order_id).
  order_id="$(printf '%s' "$response" | grep -Eo '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}' | head -n 1)"

  if [[ -z "$order_id" ]]; then
    log_mcp_call "$symbol" "$side" "FAIL" "" "missing-order-id" "$response" "$confidence" "$target_notional" "$final_qty"
    echo "FAIL symbol=$symbol side=$side reason=missing-order-id"
    return 1
  fi

  if [[ ! "$order_id" =~ $UUID_PATTERN ]]; then
    log_mcp_call "$symbol" "$side" "FAIL" "$order_id" "non-uuid-order-id" "$response" "$confidence" "$target_notional" "$final_qty"
    echo "FAIL symbol=$symbol side=$side reason=non-uuid-order-id order_id=$order_id"
    return 1
  fi

  if printf '%s' "$response" | grep -q '"error"'; then
    reason="mcp-error-response"
    log_mcp_call "$symbol" "$side" "REJECT" "$order_id" "$reason" "$response" "$confidence" "$target_notional" "$final_qty"
    echo "REJECT symbol=$symbol side=$side confidence=$confidence target_notional=$target_notional final_qty=$final_qty order_id=$order_id reason=mcp-error-response"
    return 1
  fi

  log_mcp_call "$symbol" "$side" "OK" "$order_id" "accepted" "$response" "$confidence" "$target_notional" "$final_qty"
  echo "OK symbol=$symbol side=$side confidence=$confidence target_notional=$target_notional final_qty=$final_qty order_id=$order_id"
  return 0
}

require_cmd docker
require_cmd grep
require_cmd sed
require_cmd cut
require_cmd awk
mkdir -p "$AUDIT_DIR"

if ! [[ "$BURST_ROUNDS" =~ ^[0-9]+$ ]] || (( BURST_ROUNDS <= 0 )); then
  echo "BURST_ROUNDS must be a positive integer" >&2
  exit 2
fi

mode="$(docker exec "$ALPACA_MCP_CONTAINER" sh -lc 'printf "%s" "${ALPACA_MODE:-unset}"' 2>/dev/null || true)"
echo "alpaca_mode=${mode:-unset}"
echo "mcp_audit_file=$AUDIT_FILE"
echo "buy_confidence_threshold=$BUY_CONFIDENCE_THRESHOLD"
echo "base_notional_per_trade_usd=$BASE_NOTIONAL_PER_TRADE_USD"
echo "max_notional_per_symbol_usd=$MAX_NOTIONAL_PER_SYMBOL_USD"

orders_before="$(get_orders_count)"
echo "orders_before=$orders_before"

success_count=0
fail_count=0
ok_count=0
reject_count=0

read -r -a symbols <<< "$SYMBOLS_STR"

for ((round=1; round<=BURST_ROUNDS; round++)); do
  echo "round=$round/$BURST_ROUNDS"
  idx=0
  for symbol in "${symbols[@]}"; do
    idx=$((idx + 1))
    side="buy"
    confidence="$(get_symbol_confidence "$symbol")"
    target_notional="$(compute_target_notional "$confidence")"
    latest_price="$(get_latest_quote_price "$symbol")"
    final_qty="$(compute_final_qty "$target_notional" "$latest_price")"

    if awk -v c="$confidence" -v t="$BUY_CONFIDENCE_THRESHOLD" 'BEGIN { exit !(c < t) }'; then
      echo "SKIP symbol=$symbol reason=confidence-below-threshold confidence=$confidence threshold=$BUY_CONFIDENCE_THRESHOLD"
      continue
    fi

    if [[ -z "$latest_price" || "$latest_price" == "0" || "$final_qty" == "0" ]]; then
      log_mcp_call "$symbol" "$side" "SKIP" "" "sizing-unavailable" "" "$confidence" "$target_notional" "$final_qty"
      echo "SKIP symbol=$symbol reason=sizing-unavailable confidence=$confidence target_notional=$target_notional latest_price=${latest_price:-missing} final_qty=$final_qty"
      continue
    fi

    if [[ "$BURST_BOTH_SIDES" == "true" ]]; then
      if place_market_order_mcp "$symbol" buy "$confidence" "$target_notional" "$final_qty"; then
        success_count=$((success_count + 1))
        ok_count=$((ok_count + 1))
      else
        fail_count=$((fail_count + 1))
        reject_count=$((reject_count + 1))
      fi

      if place_market_order_mcp "$symbol" sell "$confidence" "$target_notional" "$final_qty"; then
        success_count=$((success_count + 1))
        ok_count=$((ok_count + 1))
      else
        fail_count=$((fail_count + 1))
        reject_count=$((reject_count + 1))
      fi
      continue
    fi

    # Balanced mode: one side per symbol per round, side flips each round.
    if (( (idx + round) % 2 == 0 )); then
      side="sell"
    fi

    if place_market_order_mcp "$symbol" "$side" "$confidence" "$target_notional" "$final_qty"; then
      success_count=$((success_count + 1))
      ok_count=$((ok_count + 1))
    else
      fail_count=$((fail_count + 1))
      reject_count=$((reject_count + 1))
    fi
  done
done

orders_after="$(get_orders_count)"
delta=$((orders_after - orders_before))

echo "orders_after=$orders_after"
echo "orders_delta=$delta"
echo "success_count=$success_count"
echo "fail_count=$fail_count"
echo "ok_count=$ok_count"
echo "reject_count=$reject_count"

if (( ok_count <= 0 )); then
  echo "result=FAILED reason=no-successful-order-placements"
  exit 1
fi

if (( delta <= 0 )); then
  echo "result=FAILED reason=no-new-orders-detected"
  exit 1
fi

echo "result=OK reason=real-mcp-write-burst-verified"
echo "audit_saved=$AUDIT_FILE"
