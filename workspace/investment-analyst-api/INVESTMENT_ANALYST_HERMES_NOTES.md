##
## Dodawanie spolek do listy watchlist
##
1) Wykonaj polecenie dodawania spółek APPL, GOOGL, NVDA i AMZN do listy obserwowanych (watchlist) za pomocą endpointu http://investment-analyst-api:8001 i POST /api/watchlist/add. Jeśli używasz MCP, wywołaj dokładnie tool watchlist_add, bez prefiksów typu mcp_analyst_. Po dodaniu wyswietl zawartosc watchlist.

##
## Jezeli trzeba przeprowadz ponowne czytanie manuali oraz kluczowych plikow APP
##
2) Przeczytaj pliki ../../workspace/FULL_NIBBLES-STACK_SETUP.md oraz ../../workspace/investment-analyst-api/README.md i ../../workspace/investment-analyst-api/api.py oraz ../../workspace/investment-analyst-api/mcp.py.

##
## Ustaw zadanie cronjob
##
3) Ustaw powtarzajace sie dzialanie narzedziem crontab, który automatycznie będzie wykonywał analizę całego zestawu spółek co 5 minut przez 8h, dbając o logowanie i powiadomienie po zakończeniu każdego cyklu. Uzyj metody dostepu do endpointu za pomoca Investment Analyst MCP. Pokaz mi status utworzonego crontaba i napisz kiedy nastepny check?

##
##  Przyklady:
##
Uzywajac Investment Analyst MCP endpoint (http://investment-analyst-api:8001/mcp) oraz investment-analyst i watchlist-analysis-cycle-report skills, wykonaj polecenie dodawania spółek APPL, GOOGL, NVDA, AMZN, SPCX, MRVL do listy obserwowanych (watchlist).
Analizuj caly zestaw spolek przy uzyciu skilla investment-analyst i crontab-a "Watchlist Retraining Monitor (5m)", ktory powinien byc wykonywany co 5min.

## W innej formie
Using Investment Analyst MCP endpoint:
http://investment-analyst-api:8001/mcp
Execute the following workflow:

1. Add the following tickers to the investment analyst watchlist:
   - AAPL
   - GOOGL
   - NVDA
   - AMZN
   - SPCX
   - MRVL

2. Verify that all tickers exist in the watchlist.

3. Run full watchlist analysis using:
   - investment-analyst skill
   - watchlist-analysis-cycle-report skill

4. Ensure the cron job:
   "Watchlist Retraining Monitor (5m)"
   is configured and active.

5. Verify execution interval:
   every 5 minutes.

6. Trigger one manual cycle run now and return:
   - watchlist status
   - model retraining status
   - analyzed symbols
   - generated reports
   - errors if any

## Po implementacji Blueprint for investment-analyst skill:
Run investment-analyst skill for watchlist:                                                                                     
AAPL, GOOGL, NVDA, AMZN, MRVL, SPCX                                                                                             
Return full ranking + explanation per symbol.


## alpaca-mcp
Przeczytaj pliki ../../workspace/alpaca-mcp/README.md i ../../workspace/docker-compose.yml (sekcje serwisu alpaca-mcp) tak aby pozyskac wiedze z zakresu nowego skill investment-broker.

Utworz 2 skills: investment-analyst i investment-broker, ktory za posrednictwem alpaca-mcp bedzie kupowal/sprzedawal akcje obserwowanych spolek, investment-broker bedzie rowniez podejmowal decyzje.

##
## Od poczatku
##
Przeanalizuj jak dziala aplikacja investment-analyst-api i Investment Analyst API, ktore sa rowniez opisane w ./investment-analyst-api/README.md oraz opisie blueprint skill ./investment-analyst-api/INVESTMENT_ANALYST_BLUEPRINT.md.

Prosze zaplanowac cyklicznie job co 30 minut i wygenerowac raport latest_watchlist_report.json w katalogu /workspace/reports/yyyy-mm-dd_latest_watchlist_report.json

Wykonaj pełny cykl skilla 'investment-analyst' z watchlistą ['AAPL','GOOGL','AMZN','NVDA','MRVL','SPCX'] analizujac akcje spolek. Uzyj blueprinta ./investment-analyst-api/INVESTMENT_ANALYST_BLUEPRINT.md do wycwiczenia konsekwentnej analizy akcji spolek i podejmowania decyzji przy uzyciu skilli investment-analyst oraz investment-broker. Uzyj skilla investment-broker do przeprowadzenia akcji BUY/SELL/HOLD dla kazdej ze spolek z watchlist, nastepnie wygeneruj raport i zapisz do /workspace/reports.

Zaplanuj cyklicznie zadanie co 30 minut (wykorzystaj crontab 'Daily Investment Watchlist Report Generator'). Monitoruj to zadanie i potwierdz wykonanie ze statusem i licznikiem cykli.


##
## Prompt dla skill-a investment-analysis-cycle
##
Proszę uruchom skill investment-analysis-cycle dla watchlisty: AAPL, GOOGL, AMZN, NVDA, MRVL, SPCX.
Wymagania:

- Użyj investment-analyst do analizy sygnałów BUY/SELL/HOLD oraz confidence.
- Użyj investment-broker do decyzji i realnego wykonania akcji.
- Wymagane jest co najmniej jedno realne wywołanie Alpaca write tool (`order_place_market` lub `order_place_limit`).
- Jeśli execution endpointy lub MCP są niedostępne, zakończ run statusem FAILURE (bez fallback simulation).
- Jedyna dozwolona ścieżka wykonania zlecenia to write tool przez `alpaca-mcp`; nie używaj ani nie sugeruj `alpaca-cli`, `curl`, własnych skryptów shell/Python ani pseudo-wykonania opisowego.
- Uwzględnij zasady z blueprintów:
  /workspace/investment-analyst-api/INVESTMENT_ANALYST_BLUEPRINT.md
  /workspace/docs/DEFINITIVE_SKILLS_MANIFEST.md
- Zapisz raport do /workspace/reports jako:
  investment_analysis_cycle_YYYYMMDD_HHMMSS.md
  investment_analysis_cycle_YYYYMMDD_HHMMSS.json
- Na końcu zwróć:
  pełną ścieżkę zapisanych plików,
  podsumowanie decyzji per symbol,
   metadane potwierdzonego orderu z Alpaca (`order_id`, `order_status`, `symbol`, `submitted_at`).

stat /home/me/git-repo/honey-barrel-finale/workspace/docker-compose.yml && pwd && docker compose exec -T hermes sh -lc 'rm -f /workspace/reports/investment_analysis_cycle_* && /opt/hermes/bin/hermes --oneshot "Run skill investment-analysis-cycle for watchlist AAPL, GOOGL, AMZN, NVDA, MRVL, SPCX. Use investment-analyst for BUY/SELL/HOLD with confidence, then investment-broker for real trade execution decisions. You MUST execute at least one real Alpaca write tool call (order_place_market or order_place_limit) and include order_id, order_status, symbol, submitted_at from Alpaca in the output. If MCP/execution is unavailable, return FAILURE and do not claim success. Follow rules from /workspace/investment-analyst-api/INVESTMENT_ANALYST_BLUEPRINT.md and /workspace/docs/DEFINITIVE_SKILLS_MANIFEST.md. Save reports to /workspace/reports with names investment_analysis_cycle_YYYYMMDD_HHMMSS.md and investment_analysis_cycle_YYYYMMDD_HHMMSS.json." && ls -lt /workspace/reports/investment_analysis_cycle_* && for f in $(ls -t /workspace/reports/investment_analysis_cycle_* | head -n 2); do stat -c "%y | %u:%g %U:%G | %n" "$f"; done' && popd >/dev/null

docker compose exec -T hermes sh -lc '/opt/hermes/bin/hermes --oneshot "Run skill investment-analysis-cycle for watchlist AAPL, GOOGL, AMZN, NVDA, MRVL, SPCX. Use investment-analyst for BUY/SELL/HOLD with confidence, then investment-broker for real action decisions. Enforce broker retry policy. Require at least one real Alpaca order. If no real order can be placed, return FAILURE. Save reports to /workspace/reports and return file paths with order_id/order_status metadata."'

docker exec hermes sh -lc '/opt/hermes/bin/hermes --oneshot "Run skill investment-analysis-cycle for watchlist AAPL, GOOGL, AMZN, NVDA, MRVL, SPCX. Enforce broker retry policy and include attempt logs. Save markdown and json report to /workspace/reports and verify files exist/readable before claiming success."' && echo '--- Wykonalem zadanie ---' 2>/dev/null || true

Zaplanuj cyklicznie zadanie co 30 minut (wykorzystaj crontab 'Daily Investment Watchlist Report Generator'). Monitoruj to zadanie i potwierdz wykonanie ze statusem i licznikiem cykli.

##
## Zaostrzony Prompt
##
## Run skill investment-analysis-cycle for watchlist AAPL, GOOGL, AMZN, NVDA, MRVL, SPCX. Use Alpaca MCP write tools, only valid execution path. You MUST execute at least one real Alpaca MCP write tool call (order_place_market or order_place_limit) and include the returned order_id and order status from Alpaca API in the report. Never use or mention alpaca-cli, curl, raw HTTP, local shell/Python scripts, or simulated execution as a substitute. If a real Alpaca MCP order cannot be created, return FAILURE and do not claim success, do not hallucinate. Enforce broker retry policy and include attempt logs. Follow rules from /workspace/docs/DEFINITIVE_SKILLS_MANIFEST.md and /workspace/docs/INVESTMENT_ANALYST_BLUEPRINT.md. Save reports to /workspace/reports with names investment_analysis_cycle_YYYYMMDD_HHMMSS.md and investment_analysis_cycle_YYYYMMDD_HHMMSS.json.

