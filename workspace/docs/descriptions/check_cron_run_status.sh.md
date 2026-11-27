# check_cron_run_status.sh

Short diagnostic helper for launcher cycles in `reports/.cron_state/run_*.log`.

## What it does

1. Reads the latest `run_*.log` files (default: 20).
2. Classifies each run as:
- `in-progress`
- `completed`
- `completed-with-report`
- `completed-with-report-exit-*`
- `interrupted-*`
3. Prints a tabular view with cycle, watchlist symbol, start time, exit marker, and report presence.
4. Prints summary counters at the end.
5. Creates/refreshes symlinks in `reports/` for all `run_*.log` files, for easier navigation from reports directory.

## Usage

```bash
./scripts/check_cron_run_status.sh
./scripts/check_cron_run_status.sh 50
./scripts/check_cron_run_status.sh --only-active
./scripts/check_cron_run_status.sh 50 --only-active
```

Optional env vars:

- `STATE_DIR` (default: `workspace/reports/.cron_state`)
- `LINK_DIR` (default: `workspace/reports`)

Example:

```bash
LINK_DIR=/home/me/git-repo/honey-barrel-finale/workspace/reports \
  ./scripts/check_cron_run_status.sh 30 --only-active
```

## Output notes

- `has_report=yes` means a fallback report write marker was found.
- `last_exit=143` often means a terminated subprocess marker; if report was written, status is treated as completed-with-report variant.
- `--only-active` filters output to rows with `status=in-progress`.
- Symlink lines in output:
  - `run_log_links_dir=...`
  - `run_log_links_synced=...`
  - `run_log_links_skipped_non_symlink=...`