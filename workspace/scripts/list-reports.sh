#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="/home/me/git-repo/honey-barrel/workspace"

cd ${WORKSPACE}

echo "--- List of last 10 files in reports/* ---"
ls -ltr reports/* |tail -10
last_line=`ls -A1 reports/* |tail -1`
echo -e "\n"

echo "--- List of last 10 files in reports/investment_analysis_cycle_* ---"
ls -ltr reports/investment_analysis_cycle_* |tail -10
last_line_investment=`ls -A1 reports/investment_analysis_cycle_* |tail -1`
echo -e "\n"

echo "--- List of last 10 files in reports/failed_watchlist_report_cycle* ---"
ls -ltr reports/failed_watchlist_report_cycle_* |tail -10
last_line_failed=`ls -A1 reports/failed_watchlist_report_cycle_* |tail -1`
echo -e "\n"

echo "--- List of last 10 files in reports/.cron_state/* ---"
last_line_cron=`ls -A1 reports/.cron_state/* |tail -1`
ls -ltr reports/.cron_state/* |tail -10
echo -e "\n"

echo "--- List of last 10 files in reports/.cron_state/run* ---"
last_line_cron_run=`ls -A1 reports/.cron_state/run* |tail -1`
ls -ltr reports/.cron_state/run* |tail -10
echo -e "\n"

echo "--- Important general log: daily_investment_watchlist_report_generator.log ---"
last_daily_report="reports/.cron_state/daily_investment_watchlist_report_generator.log"
ls -ltr reports/.cron_state/daily_investment_watchlist_report_generator.log
echo -e "\n"

for line in ${last_line} ${last_line_investment} ${last_line_failed} ${last_line_cron} ${last_line_cron_run} ${last_daily_report};
do
    echo "--- Last file: "${line}" ---"
    cat ${WORKSPACE}/${line}
    echo -e "\n"

done

exit 0
