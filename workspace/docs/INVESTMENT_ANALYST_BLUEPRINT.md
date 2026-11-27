# INVESTMENT ANALYST BLUEPRINT

## 1. Cel dokumentu
Ten dokument opisuje wzorcowy przebieg pelnego cyklu inwestycyjnego dla 3 skilli:
1. `investment-analyst` (analiza)
2. `investment-broker` (egzekucja)
3. `investment-analysis-cycle` (orkiestracja)

Blueprint jest dokumentem operacyjnym, ktory mozna wykorzystac bezposrednio jako szablon uruchomien.

## 2. Zrodla prawdy
Ten blueprint nalezy stosowac razem z:
- `/workspace/docs/DEFINITIVE_SKILLS_MANIFEST.md`
- `/workspace/docs/INVESTMENT_ANALYST_CONFIDENCE_POLITYCS.md`

W przypadku konfliktu interpretacyjnego pierwszenstwo ma manifest, w szczegolnosci zasada MCP-only i warunki `success|failed`.

## 3. Zasada MCP-only
Wszystkie operacje analizy i egzekucji musza byc realizowane przez narzedzia MCP.

Dozwolone:
- narzedzia MCP serwera `analyst` dla watchlisty i analizy,
- narzedzia MCP serwera `alpaca` dla egzekucji transakcji,
- narzedzia MCP serwera `workspace` dla zapisu i weryfikacji raportow.

Niedozwolone jako substytut MCP:
- `curl` i reczne skladanie zapytan HTTP,
- `alpaca-cli`,
- ad hoc skrypty Python/shell wykonujace zlecenia,
- opis symulacji przedstawiany jako realna egzekucja.

## 4. Role i granice odpowiedzialnosci

### 4.1 `investment-analyst`
Odpowiedzialnosc:
- zarzadzanie watchlista,
- generowanie sygnalow BUY/SELL/HOLD,
- dostarczenie confidence i metryk uzasadniajacych.

Podstawowe narzedzia MCP:
- `watchlist_get`, `watchlist_add`, `watchlist_remove`, `watchlist_clear`
- `data_fetch`, `model_train`, `model_predict`
- `analyze_stock`, `analyze_watchlist`

### 4.2 `investment-broker`
Odpowiedzialnosc:
- zamiana sygnalow analitycznych na decyzje egzekucyjne,
- wykonanie BUY/SELL przez write tools Alpaca,
- potwierdzenie stanu zlecen i zwrot logow audytowych.

Podstawowe narzedzia MCP:
- Read: `account_get`, `clock_get`, `positions_list`, `position_get`, `orders_list`, `order_get`, `quote_latest`, `bars_get`
- Write: `order_place_market`, `order_place_limit`, `order_cancel`, `position_close`

### 4.3 `investment-analysis-cycle`
Odpowiedzialnosc:
- orkiestracja przeplywu end-to-end,
- egzekwowanie twardych kryteriow sukcesu,
- budowa i trwale zapisanie raportu.

## 5. Wejscie
Wymagane:
- lista symboli, np. `AAPL, GOOGL, AMZN, NVDA, MRVL, SPCX`

Opcjonalne:
- `risk_mode`: `paper` (domyslnie) lub `live`
- `buy_confidence_threshold`: liczba w przedziale [0,1]
- `max_symbols_per_run`: limit liczby symboli na uruchomienie
- `base_notional_per_trade`: bazowa wartosc nominalna transakcji
- `max_notional_per_symbol`: gorny limit nominalu per symbol

## 6. Kontrakt wyjscia (cycle)
Cykl powinien zwracac strukture zawierajaca co najmniej:
- `status`: `success|failed`
- `run_id`
- `started_at`, `completed_at`
- `execution_mode`: `paper|live`
- `watchlist_used`
- `analyst_summary`
- `broker_summary`
- `orders_executed`
- `report_write_verified`
- `failure_reasons`

Warunek konieczny `success`:
1. co najmniej jedno potwierdzone powodzenie write tool Alpaca (`order_place_market` albo `order_place_limit`),
2. dla wykonanych zlecen obecne pola: `order_id`, `order_status`, `symbol`, `submitted_at`,
3. raport zapisany i zweryfikowany jako czytelny.

## 7. Przeplyw orkiestracji

### Faza A: Wejscie i walidacja
1. Zweryfikuj, ze watchlista nie jest pusta.
2. Znormalizuj symbole do wielkich liter.
3. Ustal `risk_mode` i prog confidence.

### Faza B: Analiza (`investment-analyst`)
1. Wywolaj `watchlist_get`.
2. Wykonaj synchronizacje listy przez `watchlist_add`/`watchlist_remove` (jesli wymagane).
3. Wywolaj `analyze_watchlist`.
4. Opcjonalnie wywolaj `analyze_stock` dla glebszego uzasadnienia wybranych symboli.
5. Zbuduj `analyst_summary` i sygnaly per symbol.

### Faza C: Egzekucja (`investment-broker`)
1. Odczytaj stan konta i rynku: `account_get`, `clock_get`.
2. Odczytaj pozycje: `positions_list`.
3. Dla kazdego symbolu:
	 - pobierz `quote_latest` i `position_get`,
	 - przypisz akcje BUY/SELL/HOLD,
	 - policz `target_notional` i `final_qty` zgodnie z polityka confidence-based,
	 - dla BUY/SELL wykonaj write tool z retry policy,
	 - potwierdz stan przez `order_get` lub `orders_list`.
4. Zapisz `attempt_logs` i `execution_status` per symbol.

### Faza D: Raport i weryfikacja
1. Zbuduj raport (JSON i/lub Markdown).
2. Zapisz raport do `/workspace/reports`.
3. Zweryfikuj istnienie i czytelnosc plikow raportu.
4. Zwroc finalny status zgodny z twardymi kryteriami.

## 8. Polityka retry (referencyjna)
Read tools:
- `max_attempts`: 4
- `backoff`: 1s, 2s, 4s

Write tools:
- `max_attempts`: 3
- `backoff`: 2s, 5s

Bledy retryable:
- timeouty i przejsciowe bledy sieci,
- HTTP 429,
- HTTP 5xx,
- przejsciowe bledy transportu MCP.

Bledy non-retryable:
- bledy walidacji (4xx poza 429),
- brak buying power,
- naruszenie polityki serwera.

Przed ponowieniem write obowiazuje duplicate protection:
1. sprawdz `orders_list` i/lub `order_get`,
2. jesli docelowe zlecenie juz istnieje, uznaj krok za sukces,
3. nie skladaj duplikatu tego samego zlecenia.

## 9. Logika decyzyjna (referencyjna)
Dla kazdego symbolu:
1. Odczytaj `action` i `confidence` z analyst output.
2. BUY:
	 - wymagaj confidence >= prog,
	 - policz `target_notional`, `raw_qty` i `final_qty` zgodnie z `/workspace/docs/INVESTMENT_ANALYST_CONFIDENCE_POLITYCS.md`,
	 - zweryfikuj buying power,
	 - najpierw `order_place_market`, a przy przejsciowych problemach fallback do `order_place_limit`.
3. SELL:
	 - zweryfikuj istnienie pozycji,
	 - zastosuj confidence-based redukcje pozycji lub pelne zamkniecie,
	 - wykonaj redukcje/zamkniecie przez `position_close` lub zlecenie sprzedazy.
4. HOLD:
	 - bez nowego zlecenia.

### 9.1 Polityka sizingu (obowiazkowa)
Confidence nie moze byc tylko progiem wejscia.
Po przekroczeniu progu BUY broker musi:
1. wyliczyc `target_notional`,
2. wyliczyc `final_qty`,
3. zapisac `sizing_rationale`,
4. zastosowac guardrails konta i ekspozycji.

Referencja implementacyjna:
- `/workspace/docs/INVESTMENT_ANALYST_CONFIDENCE_POLITYCS.md`

## 10. Kontrakt logowania audytowego
Kazda proba MCP powinna zawierac:
- `tool_name`
- `attempt`
- `max_attempts`
- `error_class`: `retryable|non_retryable`
- `result`: `success|failed|skipped`
- `timestamp`

Logi musza trafic do `broker_summary`.

## 11. Przykladowy schemat raportu

```json
{
	"status": "success",
	"run_id": "iac_20260709_120001",
	"started_at": "2026-07-09T12:00:01Z",
	"completed_at": "2026-07-09T12:01:40Z",
	"execution_mode": "paper",
	"watchlist_used": ["AAPL", "GOOGL", "AMZN", "NVDA", "MRVL", "SPCX"],
	"analyst_summary": {
		"total": 6,
		"buy": 2,
		"sell": 1,
		"hold": 3,
		"signals": [
			{"symbol": "AAPL", "action": "BUY", "confidence": 0.74},
			{"symbol": "GOOGL", "action": "HOLD", "confidence": 0.62}
		]
	},
	"broker_summary": {
		"executed": 1,
		"failed": 0,
		"skipped": 5,
		"sizing_policy": "confidence-based-notional-v1",
		"attempt_logs": [
			{
				"tool_name": "order_place_market",
				"attempt": 1,
				"max_attempts": 3,
				"error_class": "retryable",
				"result": "success",
				"timestamp": "2026-07-09T12:01:01Z"
			}
		]
	},
	"orders_executed": [
		{
			"symbol": "AAPL",
			"confidence": 0.74,
			"target_notional": 37.5,
			"final_qty": 0.18,
			"sizing_rationale": "confidence 0.74 mapped to multiplier 1.5 under paper policy",
			"order_id": "9f1f6d11-1111-4cbf-aaaa-222222222222",
			"order_status": "accepted",
			"submitted_at": "2026-07-09T12:01:01Z"
		}
	],
	"report_write_verified": true,
	"failure_reasons": []
}
```

## 12. Semantyka failure
Cykl musi zwrocic `status=failed`, gdy wystapi dowolny warunek:
1. brak dostepu do wymaganych MCP tools,
2. brak skutecznego write po wyczerpaniu retry,
3. brak wymaganych metadanych zlecenia,
4. brak potwierdzenia zapisu raportu,
5. proba zastapienia MCP przez CLI/curl/skrypty.

Odpowiedz failure powinna zawierac:
- analyst outputs (jesli dostepne),
- broker attempt logs,
- jawne `failure_reasons`.

## 13. Szablon promptu (przyklad)
Uruchom `investment-analysis-cycle` dla watchlisty: AAPL, GOOGL, AMZN, NVDA, MRVL, SPCX.
Uzyj sciezki MCP-only.
Wykonaj najpierw faze analyst, potem broker z retry policy i duplicate protection.
Wymagaj co najmniej jednego realnego write sukcesu Alpaca oraz pol: `order_id`, `order_status`, `symbol`, `submitted_at`.
Zapisz raport do `/workspace/reports` i zweryfikuj jego czytelnosc.
Jesli jakikolwiek warunek sukcesu nie jest spelniony, zwroc `status=failed` z powodami.

## 14. Minimalna checklista smoke
1. Analiza wszystkich symboli przez MCP analyst.
2. Egzekucja decyzji przez MCP alpaca.
3. Potwierdzenie co najmniej jednego skutecznego write.
4. Potwierdzenie wymaganych metadanych zlecenia.
5. Zapis i weryfikacja raportu.
6. Zwrot `success` tylko po spelnieniu wszystkich twardych warunkow.

