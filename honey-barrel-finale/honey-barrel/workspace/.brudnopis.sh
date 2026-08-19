# HERMES INTEGRATION, NOTES && Zapiski
# ++++++++++++++++++++++++++++++++++++

hermes setup
hermes doctor --fix

## TEST of MCPs
apt update && apt install -y strace vim && strace -f -e connect hermes mcp add toolbox --url http://mcp-toolbox:3001
apt update && apt install -y strace vim && strace -f -e connect hermes mcp add workspace --url http://workspace-mcp:3002

# Register MCP servers explicitly in Hermes config
docker compose exec hermes hermes mcp add analyst --url http://investment-analyst-api:8001/mcp
docker compose exec hermes hermes mcp add workspace --url http://workspace-mcp:3001/mcp
docker compose exec hermes hermes mcp add alpaca --url http://alpaca-mcp:3001/mcp
docker compose exec hermes hermes mcp add terminal --url http://stdio-terminal:3002/mcp

# Register toolbox MCP server explicitly in Hermes config, zostal wylaczony.
docker compose exec hermes hermes mcp add toolbox --url http://mcp-toolbox:3001/mcp

# Ubuj wszystkie sesje Hermes-a z Shella  
for i in `ps auwxf |grep "investment" |grep -v "grep" |awk '{ print $2 }'`; do echo "--- Killing $i ---" && sudo kill -9 $i ; done

# +dodaj dodac_do_dokumentacji.md

# ENVIRONMENT HINT
docker compose exec hermes hermes config set agent.environment_hint "You have 4 MCP servers connected: \
analyst, alpaca, workspace, terminal. RULES: 1. ALWAYS use MCP tools directly. Never simulate outputs. \
2. NEVER use python or terminal to emulate MCP functionality. 3. workspace MCP is the ONLY persistent state system. \
STATE: - workspace MCP stores watchlists, reports, cron history, and cached results. - All other MCP servers are \ 
stateless. WATCHLIST: - All modifications MUST go through analyst MCP: watchlist_add, watchlist_remove, watchlist_get, \
watchlist_snapshot. EXECUTION: - alpaca MCP is execution-only. - Requires explicit flag: execution_approved=true. \
OBSERVABILITY: - All MCP calls must be logged into workspace MCP with metadata: tool, payload, result_summary, latency. \
FAILURE MODE: - If MCP call fails, return error state. Do not hallucinate results. WORKSPACE: - Use workspace MCP as \
/workspace logical namespace for: state, reports, cron outputs, and skill artifacts."

# LANGUAGE
docker compose exec hermes hermes config set display.language pl

# Forcing it true disables IPv6 related issues
docker compose exec hermes hermes config set network.force_ipv4 true

##
## Usuwanie sesji Hermes-a z CLI
##
hermes sessions list --limit 1000 | awk '{print $NF}' | while read id; do
    hermes sessions delete "$id" --yes
done

##
## Po wprowadzeniu zmian w .env uruchom dla Hermes-a:
##
1. Uruchom full_stack_recompose.sh (razem z docker compose build !!)
2. Jezeli zmieniales IP Ollama Model provider, uruchom z nowym IP:

export OLLAMA_BASE_IP="$(awk -F= '/^OLLAMA_BASE_IP=/{print $2; exit}' .env)" \
  docker compose exec hermes hermes config set model.base_url http://${OLLAMA_BASE_IP}:11434/v1 \
  docker compose exec hermes hermes config set providers.base_url http://${OLLAMA_BASE_IP}:11434/v1 \
  docker compose exec hermes hermes config set auxiliary.vision.base_url http://${OLLAMA_BASE_IP}:11434/v1

3. Restart hermes container:

docker compose up -d --force-recreate hermes

##
##  FLY 
##
Admin URL: https://fly.io/apps/workspace-purple-tidepool-9054
Hostname: workspace-purple-tidepool-9054.fly.dev
? Create .dockerignore from 4 .gitignore files? Yes
Created /home/me/git-repo/honey-barrel-finale/workspace/.dockerignore from 4 .gitignore files.
Wrote config file fly.toml

##
##  Hermes API tests
##
echo "Waiting for Hermes API server startup..." && for i in {1..30}; do \
curl -s -m 2 http://127.0.0.1:8642/health >/dev/null 2>&1 && echo "✓ API online" \
&& break; echo -n "."; sleep 2; done

## 
##  Uruchomienie skryptu daily_investment_watchlist_report_generator.sh
##  (przyklad z github-a)
s=$(docker inspect -f '{{.State.Health.Status}}' hermes 2>/dev/null || true); [[ "$s" == "healthy" ]] \
&& echo "ok" && echo "hermes_health=$(docker inspect -f '{{.State.Health.Status}}' hermes 2>/dev/null \
|| echo unknown)" && echo "ok"; LOCK_WAIT_SECONDS=120 RUN_TIMEOUT_SECONDS=3500 WATCHLIST_TICKERS='AAPL, GOOGL, AMZN' \
./daily_investment_watchlist_report_generator.sh --run-now

##
##  To samo w zasadzie, bez pre-testow.
##
LOCK_WAIT_SECONDS=119 RUN_TIMEOUT_SECONDS=3500 WATCHLIST_TICKERS='AAPL, GOOGL, AMZN' \ 
HERMES_MCP_BOOTSTRAP_STRICT=false ./daily_investment_watchlist_report_generator.sh --run-now

##
##  Uruchomienie polecenia Hermesowi CLI do uzycia Alpaca MCP calls wylacznie.
##
symbols='AAPL GOOGL AMZN NVDA MRVL SPCX'
for s in $symbols; do
  echo "=== BUY $s ==="
  docker exec hermes sh -lc "curl -fsS -X POST http://alpaca-mcp:3001/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"order_place_market","arguments":{"symbol":"$s","qty":0.01,"side":"buy","time_in_force":"day"}}}'"
  echo
  echo "=== SELL $s ==="
  docker exec hermes sh -lc "curl -fsS -X POST http://alpaca-mcp:3001/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"order_place_market","arguments":{"symbol":"$s","qty":0.01,"side":"sell","time_in_force":"day"}}}'"
  echo
  echo
 done

##
## Powiedz mi czy jest sens zmienic i skonsolidowac nasz PROMPT? W skrypcie wrapperze cronowym? Uscislic co tylko sie da i skrocic PROMPT?
##
## Nowy PROMPT 13/07/26
##
## PROMPT="Run skill investment-analysis-cycle (orkiestrator) for watchlist ${WATCHLIST_TICKERS}. Use only MCP tools and place at least one real Alpaca write order via order_place_market or order_place_limit. Do not use or mention alpaca-cli, curl, raw HTTP, local scripts, execute_code, delegate_task, or subagent/task decomposition. Do not ask clarification questions. If no real Alpaca MCP write can be executed, return FAILURE. Return verified order metadata from Alpaca: order_id, order_status, symbol, submitted_at. Save reports to /workspace/reports as investment_analysis_cycle_YYYYMMDD_HHMMSS.md and investment_analysis_cycle_YYYYMMDD_HHMMSS.json."
##
## ,pelne wywolanie:
## 
LOCK_WAIT_SECONDS=120 RUN_TIMEOUT_SECONDS=1800 WATCHLIST_TICKERS='AAPL, GOOGL, AMZN' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=true ORDER_RETEST_ATTEMPTS=2 ORDER_RETEST_DELAY_SECONDS=5 TIMEOUT_RETEST_ATTEMPTS=1 TIMEOUT_RETEST_DELAY_SECONDS=8 ./daily_investment_watchlist_report_generator.sh --run-now
##
##
##  Mega check of the last 20 lines of the log for cycle=328 status=failed|success|recovery|retest
grep -E 'cycle=328 status=failed|cycle=328 status=success|cycle=328 status=recovery|cycle=328 status=retest' reports/.cron_state/daily_investment_watchlist_report_generator.log | tail -n 20

##  Wait for the log to show cycle=328 status=failed|success
timeout 1200 sh -lc 'tail -n 0 -F reports/.cron_state/daily_investment_watchlist_report_generator.log | stdbuf -oL grep -m1 -E "cycle=328 status=(failed|success)"'

##
## Reconcile :: Check the last 20 lines of the log for cycle=328 status=failed|success|recovery|retest  and show the run_328.log and wait for the log to show cycle=328 status=failed|success.
##
cycle="328" && grep -E 'cycle=${cicle} status=failed|cycle=${cicle} status=success|cycle=${cicle} status=recovery|cycle=${cycle} status=retest' /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/daily_investment_watchlist_report_generator.log | tail -n 20 && echo -e "\n\n Full run_${cycle}.log\n" && cat /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/run_${cycle}.log && echo -e "\n\n Oczekiwanie na rezultat cyklu ${cycle}\n" && tail -n 0 -F /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/daily_investment_watchlist_report_generator.log | stdbuf -oL grep -m1 -E "cycle=${cycle} status=(failed|success)"

## 
## Sprawdzenie crontaba (czy dobrze zapisany WATCHLIST_TICKERS)
##
crontab -l | grep -o "WATCHLIST_TICKERS='[^']*'"

##
## Opcjonalnie (jeśli chcesz wymusić inny limit/patht):
## 
MAX_PARAREL_CRONTASKS_RUN=5 LOCK_SLOTS_DIR=/home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/daily_investment_watchlist_report_generator.lock.d ./check_hermes_cron_tasks.sh

##
## Sprawdzanie wszystkich slotów locków i ich statusu (aktywny, nieaktywny, przeterminowany)
##
cd /home/me/git-repo/honey-barrel-finale/workspace && \
grep -RInE "order_id=|order_status=|order_symbol=|order_place_market|order_place_limit|"order_id"|"symbol"|"side"" reports/.cron_state/cron_*.log reports/.cron_state/run_*.log reports/.cron_state/daily_investment_watchlist_report_generator.log | grep -E "AAPL|GOOGL|AMZN|NVDA|MRVL|SPCX|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}" | sed -n '1,260p'

##
## Check if the MCP calls are real (not simulated) and return valid order_id UUIDs.
##
cd /home/me/git-repo/honey-barrel-finale/workspace && \
BURST_ROUNDS=1 BURST_SYMBOLS='MRVL SPCX' ./scripts/alpaca_mcp_trade_burst.sh

##
## (FINAL) Check if the MCP calls (for all SYMBOLS) are real (not simulated) and return valid order_id UUIDs.
##
cd /home/me/git-repo/honey-barrel-finale/workspace && \
BURST_ROUNDS=1 BURST_SYMBOLS='AAPL GOOGL AMZN NVDA MRVL SPCX' ./scripts/alpaca_mcp_trade_burst.sh

##
## (FINAL.1) for manual/testing cycle (--run-now) execution of wrapper script daily_investment_watchlist_report_generator.sh with all the necessary environment variables set. 
##
LOCK_WAIT_SECONDS=120 WATCHLIST_TICKERS='AAPL' HERMES_MCP_BOOTSTRAP_STRICT=false \ DISABLE_TERMINAL_MCP_FOR_RUN=true RUN_TIMEOUT_SECONDS=1200 HERMES_PERSISTENT_READY_WARMUP=true \ HERMES_PERSISTENT_READY_TIMEOUT_SECONDS=60 \
./scripts/daily_investment_watchlist_report_generator.sh --run-now

##
## (FINAL.2) 
##
cd /home/me/git-repo/honey-barrel-finale/workspace && \
LOCK_WAIT_SECONDS=120 \
WATCHLIST_TICKERS='AAPL' \
HERMES_MCP_BOOTSTRAP_STRICT=false \
DISABLE_TERMINAL_MCP_FOR_RUN=true \
RUN_TIMEOUT_SECONDS=1800 \
BUY_CONFIDENCE_THRESHOLD=0.60 \
BASE_NOTIONAL_PER_TRADE_USD=25 \
MAX_NOTIONAL_PER_SYMBOL_USD=100 \
MIN_TRADE_QTY=0.01 \
QTY_STEP=0.01 \
ORDER_RETEST_ATTEMPTS=3 \
ORDER_RETEST_DELAY_SECONDS=5 \
TIMEOUT_RETEST_ATTEMPTS=5 \
TIMEOUT_RETEST_DELAY_SECONDS=8 \
./scripts/daily_investment_watchlist_report_generator.sh --run-now

##
## (FINAL.3) wraz z wylaczeniem zwisajacych sesji..
##
kill -TERM $(ps ax -o pid=,cmd= | grep -E "daily_investment_watchlist_report_generator.sh --run-now|hermes --oneshot" | grep -v grep | awk '{print $1}') 2>/dev/null || true && sleep 1 && kill -KILL $(ps ax -o pid=,cmd= | grep -E "daily_investment_watchlist_report_generator.sh --run-now|hermes --oneshot" | grep -v grep | awk '{print $1}') 2>/dev/null || true && \
LOCK_WAIT_SECONDS=120 WATCHLIST_TICKERS='AAPL' HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=true HERMES_PERSISTENT_READY_WARMUP=false RUN_TIMEOUT_SECONDS=1800 BUY_CONFIDENCE_THRESHOLD=0.60 BASE_NOTIONAL_PER_TRADE_USD=25 MAX_NOTIONAL_PER_SYMBOL_USD=100 MIN_TRADE_QTY=0.01 QTY_STEP=0.01 ORDER_RETEST_ATTEMPTS=2 ORDER_RETEST_DELAY_SECONDS=5 TIMEOUT_RETEST_ATTEMPTS=1 TIMEOUT_RETEST_DELAY_SECONDS=8 ./scripts/daily_investment_watchlist_report_generator.sh --run-now

##
## Disable all set cronjob tasks.
##
crontab -l | sed 's/^\([0-9].*\)/#\1/' | crontab -

##
## KURNA TO NAS BLOKOWALO
##
Znaleźliśmy przyczynę: hermes --oneshot uruchamia file -b /usr/bin/python3.13, ale w kontenerze brakuje binarki file, więc podproces kończy się OSError:2 i cały oneshot się klinuje. Sprawdzam teraz Dockerfile, żeby trwale to naprawić i od razu zweryfikować testem Say OK.

##
## Check OLLAMA..
##
IP='10.70.138.237' && echo '--- hermes container check ---' && docker exec hermes sh -lc 'timeout 8 curl -sS http://${IP}:11434/api/tags \
| head -c 300; echo'

##
## Jak przebudowac kontenery Hermes i Alpaca, aby wartosci mem_limit, memswap_limit i cpus byly wprowadzone w docker-compose.yml i nie trzeba bylo ich recznie ustawic w docker run?
##
docker compose build hermes alpaca-mcp && docker compose up -d --force-recreate hermes alpaca-mcp && \ 
echo '--- effective limits ---' && docker inspect -f '{{.Name}} mem={{.HostConfig.Memory}} memswap={{.HostConfig.MemorySwap}} cpus={{.HostConfig.NanoCpus}}' hermes alpaca-mcp && \ 
echo '--- running status ---' && docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' \
| grep -E 'hermes|alpaca-mcp'

##
## Alpaca-MCP >> Alpaca-API proxy
##
Ja:
Mam pomysl, alpaca-mcp oprocz call-i do MCP moze przyjmowac rowniez call-e do Alpaca API (np. order_place_market)
realnie wysylajac do Alpaca API calle poza SKILL-ami i bez halucynacji. 
W takim przypadku Alpaca MCP dziala jako proxy do Alpaca API i zwraca prawdziwe order_id UUIDs. 
Dopisz do skryptu daily_investment_watchlist_report_generator.sh wywolanie realnych call-i do Alpaca API, w przypadku kiedy SKILL-e zawioda.

Odp:
Jasne, dopiszę fallback w wrapperze: gdy oneshot/skill nie dostarczy realnego write, skrypt wykona bezpośredni 
tools/call do alpaca-mcp (order_place_market) i zapisze prawdziwe order_id do logu cyklu. 
Zaraz to zaimplementuję i sprawdzę składnię.


