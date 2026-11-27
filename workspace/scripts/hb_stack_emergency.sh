#!/usr/bin/env bash
##
## Honey Barrel emergency stack control (when docker compose is broken by ghost container metadata)
##
## Usage:
##   ./scripts/hb_stack_emergency.sh status
##   ./scripts/hb_stack_emergency.sh start
##   ./scripts/hb_stack_emergency.sh stop
##   ./scripts/hb_stack_emergency.sh health
##

set -u

WORKSPACE_DIR="/home/me/git-repo/honey-barrel/workspace"
cd "$WORKSPACE_DIR" || { echo "ERROR: cannot cd to $WORKSPACE_DIR"; exit 1; }

CORE_NAMES=(
  workspace
  alpaca-mcp
  workspace-mcp
  stdio-terminal
  mcp-toolbox
)

find_api_container() {
  local api_name

  api_name="$(docker ps -a --format '{{.Names}}' | rg -m1 '^investment-analyst-api$' || true)"
  if [[ -n "$api_name" ]]; then
    echo "$api_name"
    return 0
  fi

  api_name="$(docker ps -a --format '{{.Names}}' | rg -m1 'investment-analyst-api$' || true)"
  if [[ -n "$api_name" ]]; then
    echo "$api_name"
    return 0
  fi

  echo ""
  return 1
}

status_cmd() {
  echo "== Emergency status =="
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
  echo ""
  echo "== Created/Stopped candidates =="
  docker ps -a --format '{{.Names}}\t{{.Status}}' | rg 'investment-analyst-api|workspace|alpaca-mcp|workspace-mcp|stdio-terminal|mcp-toolbox|hermes' || true
  echo ""
  echo "== Dead records =="
  docker ps -a --filter status=dead --no-trunc --format '{{.ID}}|{{.Names}}|{{.Status}}|{{.Label "com.docker.compose.service"}}' || true
}

start_cmd() {
  local api_name
  api_name="$(find_api_container || true)"

  echo "== Starting core containers =="
  docker start "${CORE_NAMES[@]}" 2>/dev/null || true

  if [[ -n "$api_name" ]]; then
    echo "== Starting API container: $api_name =="
    docker start "$api_name" 2>/dev/null || true
  else
    echo "WARN: API container was not found."
    echo "Try once: docker compose up -d investment-analyst-api"
  fi

  echo "== Starting hermes =="
  docker start hermes 2>/dev/null || true

  echo ""
  status_cmd
}

stop_cmd() {
  local api_name
  api_name="$(find_api_container || true)"

  echo "== Stopping hermes first =="
  docker stop hermes 2>/dev/null || true

  if [[ -n "$api_name" ]]; then
    echo "== Stopping API container: $api_name =="
    docker stop "$api_name" 2>/dev/null || true
  fi

  echo "== Stopping core containers =="
  docker stop mcp-toolbox stdio-terminal workspace-mcp alpaca-mcp workspace 2>/dev/null || true

  echo ""
  status_cmd
}

health_cmd() {
  echo "== Health checks =="

  echo "- investment-analyst-api"
  curl -fsS http://127.0.0.1:18001/health || echo "health check failed"
  echo ""

  echo "- alpaca-mcp"
  curl -fsS http://127.0.0.1:3003/health || echo "health check failed"
  echo ""

  echo "- hermes"
  curl -fsS http://127.0.0.1:9119/health || echo "health check failed"
  echo ""
}

repair_hint() {
  echo ""
  echo "Permanent fix (requires root):"
  echo "  sudo systemctl restart docker"
  echo "  cd /home/me/git-repo/honey-barrel/workspace"
  echo "  docker compose down --remove-orphans"
  echo "  docker compose up -d"
}

main() {
  local cmd="${1:-status}"

  case "$cmd" in
    status)
      status_cmd
      ;;
    start)
      start_cmd
      ;;
    stop)
      stop_cmd
      ;;
    health)
      health_cmd
      ;;
    *)
      echo "Usage: $(basename "$0") {status|start|stop|health}"
      exit 1
      ;;
  esac

  repair_hint
}

main "$@"
