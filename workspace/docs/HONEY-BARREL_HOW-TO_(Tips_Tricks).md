# Honey-Barrel How-To (Tips & Tricks)

Praktyczny dokument operacyjny dla stacka Honey-Barrel.
Scalone i rozszerzone na bazie:
- `.brudnopis.sh`
- `dodac_do_dokumentacji.md`
- `dodac_beta_rozmowki_z_AI.txt`

## 1. Szybki start i orientacja

### Co jest czym
- `investment-analyst-api`: API + UI + raporty + endpointy pomocnicze
- `hermes`: orchestrator/agent uruchamiajacy flow z MCP
- `alpaca-mcp`: wykonanie zlecen i odczyt danych brokerskich
- `workspace-mcp`: warstwa stanu i artefaktow
- `reports/`: artefakty cykli, logi cron, hourly reports

### Najwazniejsze katalogi
- `reports/`
- `reports/.cron_state/`
- `reports/hourly_watchlist/`
- `docs/`
- `scripts/`

## 2. Hermes i MCP - setup

### Bazowe sprawdzenie Hermes
```bash
hermes setup
hermes doctor --fix
```

### Rejestracja MCP w Hermes
```bash
docker compose exec hermes hermes mcp add analyst --url http://investment-analyst-api:8001/mcp
docker compose exec hermes hermes mcp add workspace --url http://workspace-mcp:3001/mcp
docker compose exec hermes hermes mcp add alpaca --url http://alpaca-mcp:3001/mcp
docker compose exec hermes hermes mcp add terminal --url http://stdio-terminal:3002/mcp
```

### Wymuszenie jezyka i sieci
```bash
docker compose exec hermes hermes config set display.language pl
docker compose exec hermes hermes config set network.force_ipv4 true
```

### Czyszczenie sesji Hermes
```bash
hermes sessions list --limit 1000 | awk '{print $NF}' | while read id; do
  hermes sessions delete "$id" --yes
done
```

## 3. Operacje po zmianach .env

1. Uruchom `scripts/full_stack_recompose.sh` (z buildem kontenerow).
2. Jesli zmienia sie provider/model host, ustaw URL-e modelu w Hermes config.
3. Zrestartuj kontener Hermes.

Przyklad:
```bash
docker compose up -d --force-recreate hermes
```

## 4. Uruchamianie cykli watchlist

### Standardowy run reczny
```bash
LOCK_WAIT_SECONDS=120 RUN_TIMEOUT_SECONDS=1800 WATCHLIST_TICKERS='AAPL,GOOGL,AMZN' \
HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=true \
./scripts/daily_investment_watchlist_report_generator.sh --run-now
```

### Tryb direct-only (testowo)
```bash
WATCHLIST_TICKERS='AAPL' DIRECT_ALPACA_ONLY_MODE=true DIRECT_FALLBACK_ACTION_OVERRIDE=buy \
LOCK_WAIT_SECONDS=300 RUN_TIMEOUT_SECONDS=1500 HERMES_MCP_BOOTSTRAP_STRICT=false \
DISABLE_TERMINAL_MCP_FOR_RUN=true TIMEOUT_RETEST_ATTEMPTS=0 \
./scripts/daily_investment_watchlist_report_generator.sh --run-now
```

### Kluczowe flagi stabilnosci
- `DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true`
- `HERMES_MCP_BOOTSTRAP_STRICT=false` (wg scenariusza operacyjnego)
- `DISABLE_TERMINAL_MCP_FOR_RUN=true` (w wielu setupach zmniejsza konflikty)
- `MAX_PARAREL_CRONTASKS_RUN` ustaw ostroznie (patrz sekcja 10)

## 5. Diagnostyka i triage

### Ostatnie wpisy logow
```bash
tail -100 reports/.cron_state/daily_investment_watchlist_report_generator.log
tail -50 reports/.cron_state/daily_investment_watchlist_report_generator.log | grep -E "X-Confirm|confirmation|order_id|error|success"
```

### Najnowszy run log
```bash
tail -100 $(ls -t reports/.cron_state/run_*.log | head -1)
```

### Ostatnie nieudane artefakty
```bash
ls -1t reports/failed_watchlist_report_cycle_* | head -5
```

### Status lock slotow
```bash
for i in 1 2 3 4 5; do
  pid=$(cat reports/.cron_state/daily_investment_watchlist_report_generator.lock.d/slot_$i.pid 2>/dev/null)
  echo "Slot $i: PID=$pid - $(ps -p $pid -o state= 2>/dev/null || echo DEAD)"
done
```

## 6. Kill stale procesow (awaryjnie)

### Bezpieczniejszy wariant (TERM -> KILL)
```bash
pids=$(pgrep -f '/home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh' || true)
if [[ -n "$pids" ]]; then
  kill -TERM $pids
  sleep 1
  kill -KILL $pids 2>/dev/null || true
fi
```

### Gdy stack jest zapchany
```bash
pkill -9 -f "investment_watchlist" 2>/dev/null || true
pkill -9 -f "watchlist_report_generator" 2>/dev/null || true
pkill -9 -f "hermes --oneshot" 2>/dev/null || true
```

## 7. Cron - kontrola i sanity checks

### Snapshot crontab po zmianie wpisow

Widok `/reports/crontabs` nie czyta live `crontab -l`, tylko plik snapshotu:
- `reports/.cron_state/crontab_mbednarski.txt`

Dlatego po kazdej zmianie wpisow cron zrob odswiezenie snapshotu:

1. Zmien wpisy:
```bash
crontab -e
```

2. Potwierdz, ze wpisy sa zapisane:
```bash
crontab -l
```

3. Wygeneruj nowy snapshot recznie (natychmiast):
```bash
cd /home/me/git-repo/honey-barrel-finale/workspace
./scripts/export_crontab_snapshots.sh --run-now
```

4. Sprawdz naglowek i `captured_at`:
```bash
sed -n '1,12p' reports/.cron_state/crontab_mbednarski.txt
```

5. Odswiez UI:
- `/reports/crontabs`

Przyklad efektu po recznym odswiezeniu:
- `# captured_at: 2026-07-22T14:57:45+02:00`

### Automatyczne snapshoty (opcjonalnie)

Jezeli chcesz, aby snapshot odswiezal sie sam (domyslnie co 15 minut):

1. Instalacja exportera snapshotow do crontaba usera:
```bash
cd /home/me/git-repo/honey-barrel-finale/workspace
./scripts/export_crontab_snapshots.sh --install-cron
```

2. Weryfikacja statusu:
```bash
./scripts/export_crontab_snapshots.sh --status
crontab -l | rg "HB_CRONTAB_SNAPSHOT_EXPORT|export_crontab_snapshots\\.sh"
```

3. Usuniecie wpisu (jesli potrzebne):
```bash
./scripts/export_crontab_snapshots.sh --remove-cron
```

### Sprawdz watchlist ticker list z crontaba
```bash
crontab -l | grep -o "WATCHLIST_TICKERS='[^']*'"
```

### Wylacz wszystkie cronjoby (tymczasowo)
```bash
crontab -l | sed 's/^\([0-9].*\)/#\1/' | crontab -
```

### Potwierdzenie fallbacku w aktywnych wpisach
Upewnij sie, ze wpisy maja:
```text
DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true
```

## 8. Raporty i UI - jak czytac

### Glowne strony
- `/ui/reports/` - statyczny hub raportow
- `/reports/stack-summary` - liczniki stacku
- `/reports/match?...` - szybkie filtrowanie plikow
- `/reports/view/...` - viewer z tail mode i podswietlaniem

### Szybkie wzorce
- run logi:
```text
/reports/match?pattern=.cron_state/run_*.log&latest=20
```
- cron logi:
```text
/reports/match?pattern=.cron_state/cron_*.log&latest=20
```
- investment cycles:
```text
/reports/match?pattern=investment_analysis_cycle_*.json
/reports/match?pattern=investment_analysis_cycle_*.md
```
- failed cycles:
```text
/reports/match?pattern=failed_watchlist_report_cycle_*.json
```

## 9. Aliasy operacyjne (BETA)

Przydatne aliasy do `~/.bash_aliases`:

### Co robi kazdy alias
- `hb-buy-test`: szybki test BUY dla `AAPL` w trybie direct-only; najpierw pobiera `cash` i `buying_power`, potem odpala run-now i pokazuje tail loga generatora.
- `hb-buy-test-clean`: wariant jak wyzej, ale najpierw auto-anuluje wszystkie open ordery `AAPL` (przez MCP `order_cancel` z `X-Confirm`), potem uruchamia test BUY i tail loga.
- `hb-status`: szybki snapshot statusu HB; pobiera account, liczy open ordery ogolem i dla `AAPL`, wypisuje szczegoly open `AAPL`, a na koncu dokleja latest plik `.state`.
- `hb-procs`: pokazuje aktywne procesy zwiazane z cyklem watchlist/Hermes oneshot oraz ich laczna liczbe.
- `hb-procs-kill`: wyszukuje i wysyla `TERM` do procesow run-now/timeout/hermes oneshot, a potem pokazuje co jeszcze zostalo.
- `hb-hourly-report`: wymusza wygenerowanie hourly runtime report, wskazuje najnowszy plik i wypisuje jego zawartosc.

### Wpisy aliasow z `~/.bash_aliases`
```bash
alias hb-buy-test='cd /home/me/git-repo/honey-barrel-finale/workspace && python3 -c "import json,urllib.request as u;M=\"http://127.0.0.1:3003/mcp\";P={\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"account_get\",\"arguments\":{}}};R=json.loads(u.urlopen(u.Request(M,data=json.dumps(P).encode(),headers={\"Content-Type\":\"application/json\"}),timeout=20).read().decode());A=json.loads(R[\"result\"][\"content\"][0][\"text\"]);print(\"cash=\",A.get(\"cash\"),\"buying_power=\",A.get(\"buying_power\"))" && WATCHLIST_TICKERS=AAPL DIRECT_ALPACA_ONLY_MODE=true DIRECT_FALLBACK_ACTION_OVERRIDE=buy LOCK_WAIT_SECONDS=0 MAX_PARAREL_CRONTASKS_RUN=5 RUN_TIMEOUT_SECONDS=1500 HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=true TIMEOUT_RETEST_ATTEMPTS=0 /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now && tail -n 20 /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/daily_investment_watchlist_report_generator.log'

alias hb-buy-test-clean='cd /home/me/git-repo/honey-barrel-finale/workspace && python3 -c "import json,urllib.request as u;M=\"http://127.0.0.1:3003/mcp\";C=lambda n,a=None,c=False,i=1:json.loads(u.urlopen(u.Request(M,data=json.dumps({\"jsonrpc\":\"2.0\",\"id\":i,\"method\":\"tools/call\",\"params\":{\"name\":n,\"arguments\":a or {}}}).encode(),headers={\"Content-Type\":\"application/json\",**({\"X-Confirm\":\"true\"} if c else {})}),timeout=20).read().decode());O=json.loads(C(\"orders_list\",{\"status\":\"open\",\"limit\":50},False,1)[\"result\"][\"content\"][0][\"text\"]);[C(\"order_cancel\",{\"order_id\":o[\"id\"]},True,100+k) for k,o in enumerate([x for x in O if str(x.get(\"symbol\",\"\")).upper()==\"AAPL\"],1)];A=json.loads(C(\"account_get\",{},False,2)[\"result\"][\"content\"][0][\"text\"]);print(\"cash=\",A.get(\"cash\"),\"buying_power=\",A.get(\"buying_power\"))" && WATCHLIST_TICKERS=AAPL DIRECT_ALPACA_ONLY_MODE=true DIRECT_FALLBACK_ACTION_OVERRIDE=buy LOCK_WAIT_SECONDS=0 MAX_PARAREL_CRONTASKS_RUN=5 RUN_TIMEOUT_SECONDS=1500 HERMES_MCP_BOOTSTRAP_STRICT=false DISABLE_TERMINAL_MCP_FOR_RUN=true TIMEOUT_RETEST_ATTEMPTS=0 /home/me/git-repo/honey-barrel-finale/workspace/scripts/daily_investment_watchlist_report_generator.sh --run-now && tail -n 20 /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/daily_investment_watchlist_report_generator.log'

alias hb-status='cd /home/me/git-repo/honey-barrel-finale/workspace && python3 -c "import json,urllib.request as u;M=\"http://127.0.0.1:3003/mcp\";C=lambda n,a=None,i=1:json.loads(u.urlopen(u.Request(M,data=json.dumps({\"jsonrpc\":\"2.0\",\"id\":i,\"method\":\"tools/call\",\"params\":{\"name\":n,\"arguments\":a or {}}}).encode(),headers={\"Content-Type\":\"application/json\"}),timeout=20).read().decode());A=json.loads(C(\"account_get\",{},1)[\"result\"][\"content\"][0][\"text\"]);O=json.loads(C(\"orders_list\",{\"status\":\"open\",\"limit\":50},2)[\"result\"][\"content\"][0][\"text\"]);aapl=[o for o in O if str(o.get(\"symbol\",\"\")).upper()==\"AAPL\"];print(\"cash=\",A.get(\"cash\"),\"buying_power=\",A.get(\"buying_power\"));print(\"open_orders_total=\",len(O),\"open_aapl=\",len(aapl));[print(\"aapl_open\",x.get(\"id\"),x.get(\"status\"),x.get(\"qty\"),x.get(\"filled_qty\")) for x in aapl]" && echo "--- latest state ---" && cat /home/me/git-repo/honey-barrel-finale/workspace/reports/.cron_state/daily_investment_watchlist_report_generator.state'

alias hb-procs='ps auwxf |egrep -E "investment-analyst|daily_investment|hermes --oneshot|timeout --signal=TERM --kill-after=30|HERMES_ONESHOT_PROMPT=Use" |grep -v "grep" && echo -e "\n-- Processes number: --" && ps auwxf |egrep -E "investment-analyst|daily_investment|hermes --oneshot|timeout --signal=TERM --kill-after=30|HERMES_ONESHOT_PROMPT=Use" |grep -v "grep" |wc -l'

alias hb-procs-kill='P=$(ps -eo pid,args | egrep "daily_investment_watchlist_report_generator.sh --run-now|timeout --signal=TERM --kill-after=30 1500 docker exec|/opt/hermes/bin/hermes --oneshot" | grep -v -E "grep|hb-procs-kill" | awk "{print \$1}" | tr "\n" " "); if [ -n "$P" ]; then echo "Killing PIDs: $P"; kill -TERM $P; else echo "No matching watchlist processes found."; fi; echo -e "\n-- Remaining: --"; hb-procs'

alias hb-hourly-report='cd /home/me/git-repo/honey-barrel-finale/workspace && /home/me/git-repo/honey-barrel-finale/workspace/scripts/hourly_watchlist_runtime_report.sh --run-now && L=$(ls -1t /home/me/git-repo/honey-barrel-finale/workspace/reports/hourly_watchlist/hourly_watchlist_*.md 2>/dev/null | head -n 1); echo "--- latest hourly report: $L ---"; [ -n "$L" ] && cat "$L"'
```

## 10. Rownoleglosc i stabilnosc

Praktyczny wniosek z runow:
- `MAX_PARAREL_CRONTASKS_RUN=2` jest zwykle dobrym kompromisem
- `=1` dla maksymalnej stabilnosci
- `=3+` latwo wchodzi w lock contention i timeouty przy dlugich cyklach

Jesli stale widzisz duzo timeoutow (124/143) i lock wait:
1. Zmniejsz rownoleglosc
2. Skracaj watchliste per cykl
3. Upewnij sie, ze fallback jest wlaczony

## 11. Typowe problemy i szybkie fixy

### Problem: Hermes oneshot sie zawiesza
Objaw: procesy wisza, brak finalizacji runa.

Check:
```bash
ps aux | grep -E "hermes --oneshot|daily_investment_watchlist_report_generator.sh --run-now" | grep -v grep
```

Fix:
- kill stale procesow
- restart hermes
- sprawdz MCP bootstrap

### Problem: symulowane odpowiedzi zamiast real write
Objaw: narracyjny JSON, brak realnego `order_id`.

Fix:
- wymus fallback (`DIRECT_ALPACA_FALLBACK_ON_SKILL_FAILURE=true`)
- nie uznawaj mock/simulated output za sukces
- waliduj `executed_write` i status orderu

### Problem: locki nie schodza
Fix:
```bash
rm -rf reports/.cron_state/daily_investment_watchlist_report_generator.lock.d
mkdir -p reports/.cron_state/daily_investment_watchlist_report_generator.lock.d
```

## 12. Kontrolowany smoke test (pre-session)

Przed wazna sesja wykonaj:
1. sprawdzenie MCP count
2. konto (cash/buying power)
3. jeden run na pojedynczym symbolu (`AAPL`)
4. walidacje:
- jest nowy `run_*.log`
- jest nowy `investment_analysis_cycle_*.json/.md` albo poprawny hold bez błedu
- brak stale lockow i runaway procesow

## 13. Fly / deploy notatki

Przyklady notatek deploy:
- admin URL Fly
- hostname app
- generowanie `.dockerignore`

Te informacje trzymaj aktualne wraz z data i ownerem zmiany.

## 14. Dobre praktyki

- Uzywaj jednej konwencji uruchamiania runow (spojny zestaw env vars).
- Trzymaj krotka checkliste "go/no-go" przed godzinami szczytu.
- Dokumentuj kazdy incident: objaw -> przyczyna -> fix -> command proof.
- Po kazdej istotnej zmianie: `py_compile` + restart + smoke test endpointow.

## 15. Minimalna checklista dzienna

```text
[ ] MCP serwery online
[ ] Hermes healthy
[ ] Crontab poprawny (watchlist + fallback)
[ ] Brak stale lockow
[ ] Brak wiszacych oneshotow
[ ] Cash / Buying power OK
[ ] Ostatni cycle bez krytycznych bledow
[ ] /reports/stack-summary bez anomalii
```

---

Dokument "living". Aktualizuj po kazdej zmianie operacyjnej, ktora realnie poprawila stabilnosc albo skraca czas diagnozy.
