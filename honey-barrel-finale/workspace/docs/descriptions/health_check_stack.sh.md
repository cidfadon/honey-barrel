[workspace @ubuntoserver]: mbednarski$ ./scripts/health_check_stack.sh --short --max-hermes 30
== Honey Barrel Stack Health Check ==
Timestamp: 2026-07-29 14:53:19 CEST
Workspace: /home/me/git-repo/honey-barrel-finale/workspace
Short mode: true
Max Hermes threshold: 30

[1/7] Docker compose status
NAME                     IMAGE                                       COMMAND                  SERVICE                  CREATED             STATUS                       PORTS
alpaca-mcp               honey-barrel-stack-alpaca-mcp               "uvicorn app.main:ap…"   alpaca-mcp               3 hours ago         Up 3 hours (healthy)         0.0.0.0:3003->3001/tcp
hermes                   honey-barrel-stack-hermes                   "/usr/local/bin/herm…"   hermes                   3 hours ago         Up 3 hours (healthy)         0.0.0.0:8642->8642/tcp, 0.0.0.0:9119->9119/tcp
investment-analyst-api   honey-barrel-stack-investment-analyst-api   "python -m uvicorn a…"   investment-analyst-api   About an hour ago   Up About an hour (healthy)   127.0.0.1:18001->8001/tcp
mcp-toolbox              honey-barrel-stack-mcp-toolbox              "/sbin/tini -- node …"   mcp-toolbox              3 hours ago         Up 3 hours (healthy)         0.0.0.0:3006->3001/tcp
stdio-terminal           honey-barrel-stack-stdio-terminal           "docker-entrypoint.s…"   stdio-terminal           3 hours ago         Up 3 hours (healthy)         3002/tcp
workspace                alpine:3.20                                 "tail -f /dev/null"      workspace                3 hours ago         Up 3 hours (healthy)         
workspace-mcp            honey-barrel-stack-workspace-mcp            "/sbin/tini -- node …"   workspace-mcp            3 hours ago         Up 3 hours (healthy)         0.0.0.0:3002->3001/tcp

[2/7] investment-analyst-api Web GUI status from hermes container
investment-analyst-api Web GUI reachable from hermes container: http://investment-analyst-api:8001/ (HTTP 307, host: http://localhost:18001)

[3/7] Ollama connectivity from hermes to OLLAMA_BASE_IP:11434
hermes -> ollama connectivity OK: http://10.185.223.237:11434/api/tags (HTTP 200)

[4/7] enp0s8 subnet check vs OLLAMA_BASE_IP
enp0s8 IPv4 matches Ollama subnet: 10.185.223.226 in 10.185.223.x

[5/7] Running Hermes processes
Running Hermes processes: 11
Hermes runtime list (longest -> shortest):
PID      ELAPSED   STAT   SYMBOL  LOG
237325   00:21:16 Sl     NFLX    /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_NFLX.log
239747   00:19:15 Sl     NOK     /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_NOK.log
242925   00:17:14 Sl     NU      /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_NU.log
245336   00:15:15 Sl     NVDA    /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_NVDA.log
248248   00:13:14 Sl     OPEN    /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_OPEN.log
251069   00:11:14 Sl     PATH    /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_PATH.log
253569   00:09:13 Sl     PLTR    /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_PLTR.log
256715   00:07:13 Sl     PYPL    /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_PYPL.log
259415   00:05:14 Sl     SMCI    /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_SMCI.log
262306   00:03:13 Sl     SOFI    /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_SOFI.log
265460   00:01:15 Sl     TSLA    /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/cron_TSLA.log

[6/7] hb-procs snapshot
-- Processes number: --
66

[7/7] hb-status snapshot
cash= 27.37 buying_power= 27.37
open_orders_total= 7 open_aapl= 0
--- latest state ---
cycle_count=1241
last_status='success'
last_run_at='2026-07-29T14:30:05+02:00'
last_exit_code='0'
last_json_report='/home/me/git-repo/honey-barrel-finale/workspace/reports/investment_analysis_cycle_20260729_145131.json'
last_md_report='/home/me/git-repo/honey-barrel-finale/workspace/reports/investment_analysis_cycle_20260729_145131.md'

== Summary ==
Section              | Sts  | Details
----------------------------------------------
docker-compose       | OK   | docker compose ps
analyst-web          | OK   | HTTP 307 @ localhost:18001
ollama-hermes        | OK   | HTTP 200 @ 10.185.223.237:11434
enp0s8-net           | OK   | 10.185.223.226 in 10.185.223.x
hermes-procs         | OK   | count=11, threshold=30
hb-procs             | OK   | alias available
hb-status            | OK   | alias available

Health check finished: OK
[workspace @ubuntoserver]: mbednarski$ 