#!/usr/bin/env bash
set -euo pipefail

# Summarize launcher run logs from reports/.cron_state/run_*.log.
# Classifies each run as completed / in-progress / interrupted.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
STATE_DIR="${STATE_DIR:-$ROOT/reports/.cron_state}"
REPORTS_DIR="$(cd "$STATE_DIR/.." && pwd)"
LINK_DIR="${LINK_DIR:-$REPORTS_DIR}"
LIMIT=20
ONLY_ACTIVE=0
PRUNE_STALE=0
USAGE="usage: $0 [positive_limit] [--only-active] [--prune-stale]"

for arg in "$@"; do
  case "$arg" in
    --only-active)
      ONLY_ACTIVE=1
      ;;
    --prune-stale)
      PRUNE_STALE=1
      ;;
    ''|*[!0-9]*)
      echo "$USAGE" >&2
      exit 2
      ;;
    *)
      LIMIT="$arg"
      ;;
  esac
done

if [[ ! "$LIMIT" =~ ^[0-9]+$ ]] || (( LIMIT <= 0 )); then
  echo "$USAGE" >&2
  exit 2
fi

if [[ ! -d "$STATE_DIR" ]]; then
  echo "missing_state_dir=$STATE_DIR" >&2
  exit 2
fi

if [[ ! -d "$LINK_DIR" ]]; then
  echo "missing_link_dir=$LINK_DIR" >&2
  exit 2
fi

run_links_created=0
run_links_skipped_non_symlink=0
cron_links_created=0
cron_links_skipped_non_symlink=0
stale_links_pruned=0
stale_links_skipped_non_symlink=0
shopt -s nullglob
for src in "$STATE_DIR"/run_*.log; do
  base="$(basename "$src")"
  dst="$LINK_DIR/$base"
  if [[ -e "$dst" && ! -L "$dst" ]]; then
    run_links_skipped_non_symlink=$((run_links_skipped_non_symlink + 1))
    continue
  fi
  ln -sfn "$src" "$dst"
  run_links_created=$((run_links_created + 1))
done

for src in "$STATE_DIR"/cron_*.log; do
  base="$(basename "$src")"
  dst="$LINK_DIR/$base"
  if [[ -e "$dst" && ! -L "$dst" ]]; then
    cron_links_skipped_non_symlink=$((cron_links_skipped_non_symlink + 1))
    continue
  fi
  ln -sfn "$src" "$dst"
  cron_links_created=$((cron_links_created + 1))
done

if (( PRUNE_STALE == 1 )); then
  for dst in "$LINK_DIR"/run_*.log "$LINK_DIR"/cron_*.log; do
    [[ -e "$dst" || -L "$dst" ]] || continue
    base="$(basename "$dst")"
    src="$STATE_DIR/$base"

    if [[ ! -L "$dst" ]]; then
      stale_links_skipped_non_symlink=$((stale_links_skipped_non_symlink + 1))
      continue
    fi

    # Remove report-root symlinks that no longer have matching source logs.
    if [[ ! -e "$src" || ! -e "$dst" ]]; then
      rm -f "$dst"
      stale_links_pruned=$((stale_links_pruned + 1))
    fi
  done
fi
shopt -u nullglob

mapfile -t RUN_FILES < <(ls -1t "$STATE_DIR"/run_*.log 2>/dev/null | head -n "$LIMIT" || true)

if (( ${#RUN_FILES[@]} == 0 )); then
  echo "no run logs found in $STATE_DIR"
  exit 0
fi

printf "run_file\tcycle\twatchlist\tstarted\tstatus\tlast_exit\thas_report\tsize_bytes\n"

count_total=0
count_in_progress=0
count_completed=0
count_completed_with_report=0
count_interrupted=0

for file in "${RUN_FILES[@]}"; do
  base="$(basename "$file")"
  size="$(stat -c%s "$file" 2>/dev/null || echo 0)"

  first_line="$(head -n 1 "$file" 2>/dev/null || true)"
  started="$(printf '%s\n' "$first_line" | sed -nE 's/^\[([^]]+)\].*/\1/p')"
  cycle="$(printf '%s\n' "$first_line" | sed -nE 's/.*cycle=([0-9]+).*/\1/p')"
  [[ -n "$cycle" ]] || cycle="-"
  [[ -n "$started" ]] || started="-"

  watchlist="$(rg -n "^watchlist=" "$file" -m 1 2>/dev/null | sed -nE 's/^[0-9]+:watchlist=(.*)/\1/p' || true)"
  [[ -n "$watchlist" ]] || watchlist="-"

  has_report="no"
  if rg -q "direct_alpaca_fallback_reports_written" "$file" 2>/dev/null; then
    has_report="yes"
  fi

  last_exit="$(rg -o "oneshot_exit_code=[0-9]+" "$file" 2>/dev/null | tail -n 1 | sed 's/oneshot_exit_code=//' || true)"
  [[ -n "$last_exit" ]] || last_exit="-"

  status="in-progress"

  if [[ "$has_report" == "yes" ]]; then
    # In this launcher, report emission is usually the practical completion marker.
    if [[ "$last_exit" == "0" || "$last_exit" == "-" ]]; then
      status="completed-with-report"
    else
      status="completed-with-report-exit-$last_exit"
    fi
  elif [[ "$last_exit" == "0" ]]; then
    status="completed"
  elif [[ "$last_exit" == "124" ]]; then
    status="interrupted-timeout"
  elif [[ "$last_exit" == "143" ]]; then
    status="interrupted-sigterm"
  elif [[ "$last_exit" != "-" ]]; then
    status="interrupted-exit-$last_exit"
  fi

  if (( ONLY_ACTIVE == 1 )) && [[ "$status" != "in-progress" ]]; then
    continue
  fi

  count_total=$((count_total + 1))

  case "$status" in
    in-progress)
      count_in_progress=$((count_in_progress + 1))
      ;;
    completed)
      count_completed=$((count_completed + 1))
      ;;
    completed-with-report* )
      count_completed_with_report=$((count_completed_with_report + 1))
      ;;
    interrupted* )
      count_interrupted=$((count_interrupted + 1))
      ;;
  esac

  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
    "$base" "$cycle" "$watchlist" "$started" "$status" "$last_exit" "$has_report" "$size"
done

echo
echo "summary_total=$count_total"
echo "summary_in_progress=$count_in_progress"
echo "summary_completed=$count_completed"
echo "summary_completed_with_report=$count_completed_with_report"
echo "summary_interrupted=$count_interrupted"
echo "run_log_links_dir=$LINK_DIR"
echo "run_log_links_synced=$run_links_created"
echo "run_log_links_skipped_non_symlink=$run_links_skipped_non_symlink"
echo "cron_symbol_links_synced=$cron_links_created"
echo "cron_symbol_links_skipped_non_symlink=$cron_links_skipped_non_symlink"
echo "stale_link_prune_enabled=$PRUNE_STALE"
echo "stale_links_pruned=$stale_links_pruned"
echo "stale_links_skipped_non_symlink=$stale_links_skipped_non_symlink"
