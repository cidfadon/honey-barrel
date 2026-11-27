# DEFINITIVE SKILLS MANIFEST

## 1. Cel dokumentu
Ten dokument definiuje kontrakt wykonawczy dla 3 skilli:
1. `investment-analyst`
2. `investment-broker`
3. `investment-analysis-cycle` (skill orkiestracyjny)

Manifest jest zrodlem prawdy dla:
- podzialu odpowiedzialnosci,
- kolejnosci krokow,
- zasad raportowania,
- polityki MCP-only (wylacznie narzedzia MCP, bez substytutow).

## 2. Zasada nadrzedna: MCP-only
Kazdy skill musi korzystac wylacznie z instrukcji i narzedzi dostarczanych przez serwery MCP.

Dozwolone:
- wywolania MCP tools z serwera `analyst` dla analizy i watchlisty,
- wywolania MCP tools z serwera `alpaca` dla egzekucji BUY/SELL,
- wywolania MCP tools z serwera `workspace` do zapisu i weryfikacji raportow.

Niedozwolone jako zastapienie MCP:
- `curl` i reczne wywolania HTTP,
- `alpaca-cli`,
- lokalne skrypty Python/shell realizujace logike biznesowa poza MCP,
- symulowana/narracyjna egzekucja transakcji.

Jezeli wymagane narzedzia MCP sa niedostepne, wynik musi byc jawnie oznaczony jako failed.

## 3. Serwery MCP i zakres odpowiedzialnosci

### 3.1 Serwer `analyst` (Investment Analyst API MCP)
Endpoint (Docker network):
- `http://investment-analyst-api:8001/mcp`

Skill korzystajacy bezposrednio:
- `investment-analyst`

Podstawowe narzedzia:
- `watchlist_get`, `watchlist_add`, `watchlist_remove`, `watchlist_clear`
- `data_fetch`, `model_train`, `model_predict`
- `analyze_stock`, `analyze_watchlist`

### 3.2 Serwer `alpaca` (Alpaca MCP)
Endpoint (Docker network):
- `http://alpaca-mcp:3001/mcp`

Skill korzystajacy bezposrednio:
- `investment-broker`

Narzedzia read:
- `account_get`, `clock_get`, `positions_list`, `position_get`
- `orders_list`, `order_get`, `quote_latest`, `bars_get`

Narzedzia write:
- `order_place_market`, `order_place_limit`, `order_cancel`, `position_close`

### 3.3 Serwer `workspace` (zapisy raportow)
Wykorzystanie:
- zapis raportow cyklu do `/workspace/reports`,
- weryfikacja, ze pliki istnieja i sa czytelne.

Skill korzystajacy:
- `investment-analysis-cycle` (lub delegowany krok raportowy).

## 4. Rola i kontrakt kazdego skilla

### 4.1 `investment-analyst`
Rola:
- zarzadzanie watchlista,
- analiza sygnalow BUY/SELL/HOLD,
- dostarczenie confidence i metryk uzasadniajacych.

Minimalny kontrakt wyjscia:
- `watchlist_used`: lista symboli,
- `signals`: per symbol: `action` (BUY/SELL/HOLD), `confidence`, metryki,
- `analyst_status`: `success|failed`,
- lista bledow MCP (jesli wystapily).

Reguly:
- przed analiza watchlisty najpierw `watchlist_get`,
- brak fallbackow do terminal/curl/raw HTTP,
- awaria MCP => jawny blad i brak sztucznego sukcesu.

### 4.2 `investment-broker`
Rola:
- zamiana sygnalow analitycznych na realna sciezke egzekucji,
- wykonanie BUY/SELL/HOLD przez MCP `alpaca`,
- walidacja rezultatu zlecenia.

Minimalny kontrakt wyjscia per symbol:
- `decision`: BUY/SELL/HOLD,
- `execution_status`: `executed|failed|skipped`,
- `attempt_logs`: lista prob MCP,
- dla `executed` wymagane: `order_id`, `order_status`, `symbol`, `submitted_at`.

Reguly:
- najpierw read tools (`account_get`, `clock_get`, etc.), potem write,
- retry policy obowiazkowe przed failed,
- duplicate protection przed ponowieniem write,
- bez symulacji jako sukces.

### 4.3 `investment-analysis-cycle` (orkiestrator)
Rola:
- uruchomienie calosci end-to-end,
- koordynacja flow analyst -> broker -> raport,
- egzekwowanie warunkow sukcesu cyklu.

Warunek konieczny sukcesu cyklu:
- co najmniej jedno realne powodzenie write tool Alpaca (`order_place_market` lub `order_place_limit`),
- potwierdzone metadane zlecenia (`order_id`, `order_status`, `symbol`, `submitted_at`),
- raport zapisany i zweryfikowany jako czytelny.

## 5. Orkiestracja: sekwencja referencyjna

### Faza A: Inicjalizacja wejscia
1. Odczytaj watchliste wejsciowa.
2. Ustal `risk_mode` (`paper` domyslnie, albo `live`).
3. Ustal opcjonalny prog confidence.

### Faza B: Analiza (`investment-analyst`)
1. `watchlist_get`
2. Synchronizacja listy (`watchlist_add`/`watchlist_remove` jesli potrzebne)
3. `analyze_watchlist`
4. Opcjonalnie `analyze_stock` dla symboli wymagajacych dodatkowego uzasadnienia

Artefakt fazy B:
- sygnaly i confidence per symbol,
- status wykonania analyst phase.

### Faza C: Egzekucja (`investment-broker`)
1. Stan konta i rynku: `account_get`, `clock_get`, `positions_list`
2. Dla kazdego symbolu:
	- walidacja (`quote_latest`, `position_get`),
	- decyzja BUY/SELL/HOLD,
	- write tool (gdy BUY/SELL) z retry policy,
	- potwierdzenie przez `order_get` lub `orders_list`.
3. Rejestr prob i klasyfikacja bledow.

Artefakt fazy C:
- execution_status per symbol,
- potwierdzone metadane zlecen,
- attempt logs.

### Faza D: Raport i walidacja (`investment-analysis-cycle`)
1. Zapis raportu do `/workspace/reports` (json lub md).
2. Weryfikacja zapisu:
	- potwierdzenie istnienia pliku,
	- odczyt poczatkowych bajtow/wierszy,
	- flaga `report_write_verified=true|false`.
3. Zwrot finalnego statusu cyklu.

## 6. Twarde reguly statusu

### 6.1 Kiedy `status=success`
Wylacznie gdy wszystkie warunki sa spelnione:
1. analiza zostala wykonana,
2. co najmniej jedno realne zlecenie Alpaca write zakonczone powodzeniem,
3. sa kompletne metadane zlecenia,
4. raport zapisany i zweryfikowany.

### 6.2 Kiedy `status=failed`
Kazdy z warunkow powoduje failed:
1. brak dostepu do wymaganych MCP tools,
2. brak skutecznego write po wyczerpaniu retry,
3. brak metadanych zlecenia,
4. brak potwierdzenia zapisu raportu,
5. proba zastapienia MCP przez CLI/curl/skrypt lokalny.

## 7. Kontrakt przekazywania danych miedzy skillami

### 7.1 Wejscie brokera z analysta
Broker powinien otrzymac co najmniej:
- `symbol`,
- `action` (BUY/SELL/HOLD),
- `confidence`,
- opcjonalne metryki uzasadniajace.

### 7.2 Wejscie orkiestratora z brokera
Orkiestrator musi otrzymac:
- `execution_status` per symbol,
- metadane zlecen dla executed,
- attempt logs,
- podsumowanie bledow retryable/non-retryable.

## 8. Zakazane antywzorce
1. Oznaczenie cyklu jako success bez realnego write do Alpaca.
2. Raport sukcesu oparty o symulacje.
3. Pomijanie weryfikacji `order_get`/`orders_list` po write.
4. Brak logow prob MCP.
5. Brak walidacji zapisu raportu.

## 9. Minimalna checklista wykonania cyklu
1. Odczytaj watchliste.
2. Uruchom analize na wszystkich symbolach.
3. Uruchom brokera z retry policy i duplicate protection.
4. Potwierdz co najmniej jedno realne powodzenie write (`order_place_market` lub `order_place_limit`).
5. Potwierdz metadane zlecenia (`order_id`, `order_status`, `symbol`, `submitted_at`).
6. Zapisz raport do `/workspace/reports`.
7. Zweryfikuj czytelnosc raportu.
8. Ustaw finalny status `success` albo `failed` zgodnie z regulami.

## 10. Relacja do blueprintow
Przy decyzjach i formacie raportu obowiazuja rowniez:
- blueprint `/workspace/docs/INVESTMENT_ANALYST_BLUEPRINT.md`
- niniejszy manifest: `/workspace/docs/DEFINITIVE_SKILLS_MANIFEST.md`

W razie konfliktu interpretacyjnego dotyczacego sciezki wykonania, pierwszenstwo ma zasada MCP-only i warunki sukcesu z tego manifestu.
