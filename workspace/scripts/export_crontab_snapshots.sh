#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
REPORTS_DIR="$ROOT/reports"
STATE_DIR="$REPORTS_DIR/.cron_state"
SCRIPT_PATH="$ROOT/scripts/export_crontab_snapshots.sh"
LOG_FILE="$STATE_DIR/cron_crontab_snapshots.log"
SCHEDULE="${CRONTAB_SNAPSHOT_CRON_SCHEDULE:-*/15 * * * *}"
MARKER="# HB_CRONTAB_SNAPSHOT_EXPORT"

DEFAULT_CRON_USER="${CRONTAB_SNAPSHOT_USER:-${SUDO_USER:-${USER:-$(id -un)}}}"
USERS_CSV="${CRONTAB_SNAPSHOT_USERS:-$DEFAULT_CRON_USER}"
IFS=',' read -r -a USERS <<< "$USERS_CSV"

mkdir -p "$STATE_DIR"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--run-now|--install-cron|--remove-cron|--status|--help]

Options:
  --run-now       Export crontab snapshots now.
  --install-cron  Install/update user crontab entry for periodic snapshot export.
  --remove-cron   Remove snapshot export entry from user crontab.
  --status        Show configured schedule and matching crontab entries.
  --help          Show this help.
EOF
}

snapshot_user() {
  local user="$1"
  local out_file="$STATE_DIR/crontab_${user}.txt"
  local now_iso
  now_iso="$(date -Iseconds)"

  {
    echo "# crontab snapshot"
    echo "# user: ${user}"
    echo "# captured_at: ${now_iso}"
    echo ""

    if [[ "${user}" == "$(id -un)" ]]; then
      crontab -l 2>&1 || true
    else
      if crontab -l -u "$user" >/dev/null 2>&1; then
        crontab -l -u "$user" 2>&1 || true
      elif command -v sudo >/dev/null 2>&1; then
        sudo -n crontab -l -u "$user" 2>&1 || true
      else
        echo "cannot read crontab for user '${user}' (no sudo/crontab access)"
      fi
    fi
  } > "$out_file"

  echo "[$(date -Iseconds)] snapshot updated: $out_file"
}

run_now() {
  local user
  for user in "${USERS[@]}"; do
    snapshot_user "$user"
  done
}

install_cron() {
  local current tmp line
  current="$(crontab -l 2>/dev/null || true)"
  tmp="$(mktemp)"

  printf "%s\n" "$current" | rg -v "$MARKER" > "$tmp" || true
  line="$SCHEDULE cd \"$ROOT\" && \"$SCRIPT_PATH\" --run-now >> \"$LOG_FILE\" 2>&1 $MARKER"
  echo "$line" >> "$tmp"

  crontab "$tmp"
  rm -f "$tmp"

  echo "Installed crontab snapshot exporter."
  echo "Schedule: $SCHEDULE"
}

remove_cron() {
  local current tmp
  current="$(crontab -l 2>/dev/null || true)"
  tmp="$(mktemp)"

  printf "%s\n" "$current" | rg -v "$MARKER" > "$tmp" || true
  crontab "$tmp"
  rm -f "$tmp"

  echo "Removed crontab snapshot exporter entry."
}

status() {
  echo "Schedule: $SCHEDULE"
  echo "Marker: $MARKER"
  echo "Matching crontab entries:"
  (crontab -l 2>/dev/null || true) | rg "$MARKER|export_crontab_snapshots\.sh" || echo "(none)"
}

main() {
  case "${1:-}" in
    --run-now)
      run_now
      ;;
    --install-cron)
      install_cron
      ;;
    --remove-cron)
      remove_cron
      ;;
    --status)
      status
      ;;
    --help|-h)
      usage
      ;;
    "")
      usage
      exit 1
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
