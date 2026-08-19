#!/bin/bash

cycle=${1}
LOG_DIR="/home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state"

[[ -z "$cycle" ]] && echo "ERROR: Missing cycle number argument." && echo -e "\nUsage: $(basename "$0") [cycle_number]\n" && exit 1

grep -E "cycle=${cycle} status=failed|cycle=${cycle} status=success|cycle=${cycle} \
status=recovery|cycle=${cycle} status=retest" $LOG_DIR/daily_investment_watchlist_report_generator.log \
| tail -n 20 && echo -e "\n\n Full run_${cycle}.log\n" && cat $LOG_DIR/run_${cycle}.log \
&& echo -e "\n\n Oczekiwanie na rezultat cyklu ${cycle}\n" && tail -n 0 -F \
 $LOG_DIR/daily_investment_watchlist_report_generator.log \
| stdbuf -oL grep -m1 -E "cycle=${cycle} status=(failed|success)"

##
## Narazie tyle..
##
exit 0

