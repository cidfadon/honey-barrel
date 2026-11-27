#!/usr/bin/env bash
##
## (c) 2026 Honey Barrel Labs
## Overall health check for Honey Barrel stack.
##

set -u

WORKSPACE_DIR="/home/me/git-repo/honey-barrel/workspace"
cd "$WORKSPACE_DIR" || { echo "Failed to change directory to $WORKSPACE_DIR"; exit 1; }

SHORT_MODE=false
MAX_HERMES="${HERMES_MAX_PROCESSES:-0}"
OVERALL_EXIT=0
SUMMARY_LINES=""

add_summary() {
    local section="$1"
    local status="$2"
    local message="$3"

    printf -v SUMMARY_LINES "%s%-20s | %-4s | %s\n" "$SUMMARY_LINES" "$section" "$status" "$message"

    if [[ "$status" == "FAIL" ]]; then
        OVERALL_EXIT=1
    fi
}

read_env_value() {
    local key="$1"
    local env_file="$2"
    local line value

    [[ -f "$env_file" ]] || return 0

    line="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$env_file" | head -n 1 || true)"
    [[ -n "$line" ]] || return 0

    value="${line#*=}"
    value="${value%%#*}"
    value="${value//[[:space:]]/}"
    value="${value%\"}"
    value="${value#\"}"

    printf '%s' "$value"
}

show_help() {
    echo "Usage: $(basename "$0") [--short] [--max-hermes N] [--help]"
    echo ""
    echo "Runs overall stack health checks:"
    echo "  - docker compose services status"
    echo "  - investment-analyst-api Web GUI status from inside hermes container"
    echo "  - Ollama connectivity from hermes to OLLAMA_BASE_IP:11434"
    echo "  - enp0s8 IPv4 subnet check against OLLAMA_BASE_IP from .env"
    echo "  - running Hermes oneshot process count"
    echo "  - hb-procs output (if alias exists)"
    echo "  - hb-status output (if alias exists)"
    echo ""
    echo "Options:"
    echo "  --short           show only the last 30 lines of hb-procs and hb-status"
    echo "  --max-hermes N    fail when Hermes process count is greater than N"
    echo "                    default: HERMES_MAX_PROCESSES env or 0"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            show_help
            exit 0
            ;;
        --short)
            SHORT_MODE=true
            shift
            ;;
        --max-hermes)
            if [[ -z "${2:-}" || ! "${2:-}" =~ ^[0-9]+$ ]]; then
                echo "ERROR: --max-hermes requires a non-negative integer"
                exit 1
            fi
            MAX_HERMES="$2"
            shift 2
            ;;
        *)
            echo "ERROR: Unknown argument '$1'"
            show_help
            exit 1
            ;;
    esac
done

echo "== Honey Barrel Stack Health Check =="
echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "Workspace: $WORKSPACE_DIR"
echo "Short mode: $SHORT_MODE"
echo "Max Hermes threshold: $MAX_HERMES"
echo ""

ENV_FILE="$WORKSPACE_DIR/.env"
OLLAMA_BASE_IP="$(read_env_value "OLLAMA_BASE_IP" "$ENV_FILE")"

echo "[1/7] Docker compose status"
if docker compose ps >/dev/null 2>&1; then
    docker compose ps
    add_summary "docker-compose" "OK" "docker compose ps"
else
    echo "WARN: docker compose ps failed"
    add_summary "docker-compose" "FAIL" "docker compose ps failed"
fi

echo ""
echo "[2/7] investment-analyst-api Web GUI status from hermes container"
if ! docker compose ps --services --status running 2>/dev/null | grep -Fxq "hermes"; then
    echo "FAIL: hermes container is not running, cannot verify Web GUI from inside hermes"
    add_summary "analyst-web" "FAIL" "hermes is not running"
else
    ANALYST_WEB_GUI_URL="http://investment-analyst-api:8001/"
    ANALYST_WEB_STATUS_CODE="$(docker compose exec -T hermes sh -lc "curl -sS --max-time 5 -o /dev/null -w '%{http_code}' \"$ANALYST_WEB_GUI_URL\"" 2>/dev/null || true)"

    if [[ "$ANALYST_WEB_STATUS_CODE" =~ ^(200|301|302|307|308)$ ]]; then
        echo "investment-analyst-api Web GUI reachable from hermes container: $ANALYST_WEB_GUI_URL (HTTP $ANALYST_WEB_STATUS_CODE, host: http://localhost:18001)"
        add_summary "analyst-web" "OK" "HTTP $ANALYST_WEB_STATUS_CODE @ localhost:18001"
    else
        echo "FAIL: investment-analyst-api Web GUI is not reachable from hermes container: $ANALYST_WEB_GUI_URL (HTTP ${ANALYST_WEB_STATUS_CODE:-n/a})"
        add_summary "analyst-web" "FAIL" "localhost:18001 unreachable from hermes"
    fi
fi

echo ""
echo "[3/7] Ollama connectivity from hermes to OLLAMA_BASE_IP:11434"
if [[ -z "$OLLAMA_BASE_IP" ]]; then
    echo "FAIL: OLLAMA_BASE_IP is missing in $ENV_FILE"
    add_summary "ollama-hermes" "FAIL" "missing OLLAMA_BASE_IP in .env"
elif ! docker compose ps --services --status running 2>/dev/null | grep -Fxq "hermes"; then
    echo "FAIL: hermes container is not running, cannot verify hermes -> ollama connectivity"
    add_summary "ollama-hermes" "FAIL" "hermes is not running"
else
    OLLAMA_PROBE_URL="http://${OLLAMA_BASE_IP}:11434/api/tags"
    OLLAMA_STATUS_CODE="$(docker compose exec -T hermes sh -lc "curl -sS --max-time 5 -o /dev/null -w '%{http_code}' \"$OLLAMA_PROBE_URL\"" 2>/dev/null || true)"

    if [[ "$OLLAMA_STATUS_CODE" =~ ^(200|301|302|307|308)$ ]]; then
        echo "hermes -> ollama connectivity OK: $OLLAMA_PROBE_URL (HTTP $OLLAMA_STATUS_CODE)"
        add_summary "ollama-hermes" "OK" "HTTP $OLLAMA_STATUS_CODE @ ${OLLAMA_BASE_IP}:11434"
    else
        echo "FAIL: hermes cannot reach ollama: $OLLAMA_PROBE_URL (HTTP ${OLLAMA_STATUS_CODE:-n/a})"
        add_summary "ollama-hermes" "FAIL" "${OLLAMA_BASE_IP}:11434 unreachable from hermes"
    fi
fi

echo ""
echo "[4/7] enp0s8 subnet check vs OLLAMA_BASE_IP"

if [[ -z "$OLLAMA_BASE_IP" ]]; then
    echo "FAIL: OLLAMA_BASE_IP is missing in $ENV_FILE"
    add_summary "enp0s8-net" "FAIL" "missing OLLAMA_BASE_IP in .env"
else
    OLLAMA_SUBNET_PREFIX="$(echo "$OLLAMA_BASE_IP" | cut -d. -f1-3)"
    ENP0S8_IPS="$(ip -4 -o addr show dev enp0s8 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"

    if [[ -z "$ENP0S8_IPS" ]]; then
        echo "FAIL: interface enp0s8 has no IPv4 address"
        add_summary "enp0s8-net" "FAIL" "no IPv4 on enp0s8"
    else
        MATCHED_IP=""
        while IFS= read -r IFACE_IP; do
            [[ -z "$IFACE_IP" ]] && continue
            IFACE_PREFIX="$(echo "$IFACE_IP" | cut -d. -f1-3)"
            if [[ "$IFACE_PREFIX" == "$OLLAMA_SUBNET_PREFIX" ]]; then
                MATCHED_IP="$IFACE_IP"
                break
            fi
        done <<< "$ENP0S8_IPS"

        if [[ -n "$MATCHED_IP" ]]; then
            echo "enp0s8 IPv4 matches Ollama subnet: $MATCHED_IP in ${OLLAMA_SUBNET_PREFIX}.x"
            add_summary "enp0s8-net" "OK" "${MATCHED_IP} in ${OLLAMA_SUBNET_PREFIX}.x"
        else
            echo "FAIL: enp0s8 IPv4 is outside Ollama subnet ${OLLAMA_SUBNET_PREFIX}.x"
            echo "enp0s8 IPv4 addresses: $(echo "$ENP0S8_IPS" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
            add_summary "enp0s8-net" "FAIL" "enp0s8 outside ${OLLAMA_SUBNET_PREFIX}.x"
        fi
    fi
fi

echo ""
echo "[5/7] Running Hermes processes"
HERMES_PROCS="$(ps -eo pid=,stat=,etimes=,args= | awk '
    /hermes --oneshot Use only/ && $0 !~ /awk|grep/ {
        pid = $1
        stat = $2
        etimes = $3
        symbol = "-"

        if (match($0, /watchlist [A-Z0-9._-]+/)) {
            symbol = substr($0, RSTART, RLENGTH)
            sub(/^watchlist /, "", symbol)
        }

        print pid"\t"etimes"\t"stat"\t"symbol
    }
' | sort -k2,2nr)"

if [[ -n "$HERMES_PROCS" ]]; then
    HERMES_COUNT="$(printf "%s\n" "$HERMES_PROCS" | wc -l | tr -d ' ')"
else
    HERMES_COUNT=0
fi

echo "Running Hermes processes: ${HERMES_COUNT}"

if (( HERMES_COUNT > 0 )); then
    echo "Hermes runtime list (longest -> shortest):"
    echo "PID      ELAPSED   STAT   SYMBOL  LOG"

    while IFS=$'\t' read -r PID ETIMES STAT SYMBOL; do
        [[ -z "$PID" ]] && continue
        HOURS=$((ETIMES / 3600))
        MINUTES=$(((ETIMES % 3600) / 60))
        SECONDS=$((ETIMES % 60))
        LOG_PATH="-"
        if [[ "$SYMBOL" != "-" ]]; then
            LOG_PATH="$WORKSPACE_DIR/reports/.cron_state/cron_${SYMBOL}.log"
        fi
        printf "%-8s %02d:%02d:%02d %-6s %-7s %s\n" "$PID" "$HOURS" "$MINUTES" "$SECONDS" "$STAT" "$SYMBOL" "$LOG_PATH"
    done <<< "$HERMES_PROCS"
else
    echo "Hermes runtime list: no matching processes"
fi

if (( HERMES_COUNT > MAX_HERMES )); then
    echo "FAIL: Hermes processes (${HERMES_COUNT}) exceed threshold (${MAX_HERMES})"
    add_summary "hermes-procs" "FAIL" "count=${HERMES_COUNT}, threshold=${MAX_HERMES}"
else
    add_summary "hermes-procs" "OK" "count=${HERMES_COUNT}, threshold=${MAX_HERMES}"
fi

echo ""
echo "[6/7] hb-procs snapshot"
if bash -ic 'type hb-procs >/dev/null 2>&1'; then
    if [[ "$SHORT_MODE" == "true" ]]; then
        echo "-- Processes number: --"
        bash -ic 'hb-procs' | tail -n 1
    else
        bash -ic 'hb-procs'
    fi
    add_summary "hb-procs" "OK" "alias available"
else
    echo "WARN: alias hb-procs is not available in current shell config"
    add_summary "hb-procs" "WARN" "alias missing"
fi

echo ""
echo "[7/7] hb-status snapshot"
if bash -ic 'type hb-status >/dev/null 2>&1'; then
    if [[ "$SHORT_MODE" == "true" ]]; then
        bash -ic 'hb-status' | tail -n 30
    else
        bash -ic 'hb-status'
    fi
    add_summary "hb-status" "OK" "alias available"
else
    echo "WARN: alias hb-status is not available in current shell config"
    add_summary "hb-status" "WARN" "alias missing"
fi

echo ""
echo "== Summary =="
echo "Section              | Sts  | Details"
echo "----------------------------------------------"
printf "%s" "$SUMMARY_LINES"
echo ""
if [[ $OVERALL_EXIT -eq 0 ]]; then
    echo "Health check finished: OK"
else
    echo "Health check finished: FAIL"
fi

exit $OVERALL_EXIT
