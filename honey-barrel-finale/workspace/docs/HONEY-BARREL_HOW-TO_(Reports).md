# Honey-Barrel How-To (Reports)

Dokument techniczny dla operatorow stacka, opisujacy warstwe nawigacji raportowej wystawiana przez `investment-analyst-api`.

## 1. Rola UI Reports Navigator

`UI Reports Navigator` jest operatorowym frontendem do obserwacji stanu raportow i logow cykli. Nie generuje danych i nie modyfikuje procesu wykonawczego. Jego zadaniem jest szybkie dojscie do tych samych artefaktow, ktore normalnie lezalyby w `reports/`, ale z lepsza priorytetyzacja i z gotowymi trybami triage.

Navigator jest przydatny w sytuacjach, gdy trzeba:

- sprawdzic ostatni cykl bez recznego przeszukiwania katalogow,
- wejsc w logi cron/run i od razu przejsc do koncowki,
- odfiltrowac szum i zobaczyc tylko sygnaly alarmowe,
- zweryfikowac, czy cykl zostawil realny zapis, czy tylko artefakt blednego/symulowanego przebiegu,
- skrocic czas dojscia do stack summary i report artifacts.

## 2. Punkt wejscia i warstwa serwowania

Glowne wejscie:

- `/ui/reports/` - dynamiczny widok serwowany przez `investment-analyst-api`

Powiazane endpointy raportowe:

- `/reports/list?path=...` - listowanie katalogu raportow
- `/reports/match?pattern=...` - filtrowanie po wzorcu globowym
- `/reports/view/{report_path}` - viewer z trybem podgladu i odswiezania
- `/reports/file/{report_path}` - surowy odczyt pliku
- `/reports/stack-summary` - zbiorczy stan stacka i licznikow

W praktyce `/ui/reports/` jest warstwa indeksujaca, a nie data store. Zrodlem prawdy pozostaje filesystem pod `reports/`.

## 3. Mapa Navigatora

Aktualny layout Navigatora ma osiem glownych kafelkow:

1. `reports/` - wejscie do root katalogu raportow.
2. `reports/hourly_watchlist/` - katalog markdownowych raportow hourly.
3. `/reports/.cron_state/cron_*.log` - cron execution logs.
4. `/reports/.cron_state/run_*.log` - pelne logi przebiegu cykli.
5. `cron logs (Latest 20)` - szybki podglad najnowszych cron logow.
6. `run logs (Latest 20)` - szybki podglad najnowszych run logow.
7. `honey-barrel stack summary` - agregowany stan stacka.
8. `daily_investment_watchlist_report_generator.log` - wyrózniony kafelek generatora z trybem alerts-only.

Taka kolejnosc jest celowa. Najpierw dostajesz ogolny stan i najnowsze logi, a dopiero na koncu specjalny tor do generatora watchlist, ktory zwykle jest najwazniejszy w triage cyklu.

## 4. Dedykowany log generatora

Najistotniejszy operatorowo kafelek prowadzi do:

- `.cron_state/daily_investment_watchlist_report_generator.log`

Link docelowy:

- `/reports/view/.cron_state/daily_investment_watchlist_report_generator.log?tail=1&latest=200&refresh=5&alerts_only=1`

Semantyka parametrow:

- `tail=1` - start od koncowki logu, czyli od najbardziej operacyjnie uzytecznych wpisow,
- `latest=200` - ograniczenie powierzchni odczytu do ostatnich 200 linii,
- `refresh=5` - odswiezanie co 5 sekund dla logu zywego,
- `alerts_only=1` - tryb, w ktorym viewer eksponuje linie o wartosci diagnostycznej zamiast pelnego szumu.

W UI ten kafelek ma klase `featured`, co odroznia go wizualnie i zmniejsza czas dojscia w trakcie awarii albo nieudanych cykli.

## 5. Interpretacja widokow

### `/reports/view/...`

To podstawowy viewer do analizy pojedynczego pliku. Dla plikow `.log` typowy tryb to `tail + refresh`, a dla logow generatora dodatkowo `alerts_only`.

### `/reports/match?...`

To widok do szybkiego zawężania po patternie. Nadaje się do:

- logow cron,
- logow run,
- pelnych cykli,
- artefaktow failed-cycle.

### `/reports/stack-summary`

To widok kontroli stanu stacka. Operator uzywa go wtedy, gdy chce sprawdzic liczniki, stan wysokiego poziomu i szybki kontekst bez wchodzenia w pelne logi.

### `/reports/file/...`

To surowy odczyt pliku, bez logiki viewerowej. Przydatny, gdy potrzebujesz pliku w czystej postaci.

## 6. Co operator powinien wyciagac z logow

W triage najbardziej licza sie sygnaly typu:

- `timeout`
- `error`
- `confirmation_required`
- brak write evidence
- brak final response
- simulated execution
- recovery fallback

W praktyce log generatora i `run_*.log` odpowiadaja na inne pytania:

- `run_*.log` pokazuje przebieg konkretnego uruchomienia,
- `daily_investment_watchlist_report_generator.log` pokazuje zebrany tor operacyjny i sygnaly alarmowe,
- `failed_watchlist_report_cycle_*.json` daje skondensowany artefakt awarii,
- `*_latest_watchlist_report.json` daje ostatni dostepny alias stanu.

## 7. Operatorowy workflow triage

### Start od Navigatora

1. Wejdz na `/ui/reports/`.
2. Otworz `run logs (Latest 20)`.
3. Ustal, ktory cykl jest ostatni i czy w ogole doszedl do finalizacji.

### Analiza awarii generatora

1. Wejdz na `/ui/reports/`.
2. Kliknij `daily_investment_watchlist_report_generator.log`.
3. Przeczytaj tylko alarmowe wpisy i koncowke logu.
4. Jesli sygnal wskazuje na timeout lub fallback, przejdz do `run_*.log` i failure artifact.

### Kontrola stanu po serii cykli

1. Otworz `reports/stack-summary`.
2. Zweryfikuj liczniki i stan globalny.
3. Porownaj z najnowszym `run_*.log` oraz `failed_watchlist_report_cycle_*.json`.

## 8. Zasieg i ograniczenia

Navigator nie zastępuje:

- analizy shellowej w `reports/`,
- debugowania Python/FastAPI,
- analizy logiki w `scripts/`,
- hermesowych raportow analitycznych.

To jest warstwa pierwszego kontaktu dla operatora, a nie system masowego przetwarzania logow.

## 9. Warstwa statyczna i dynamiczna

Repozytorium ma dwa spójne punkty prezentacji:

- dynamiczny `/ui/reports/` z `investment-analyst-api`,
- statyczny hub w `investment-analyst-api/static/reports/index.html`.

Z perspektywy operatora dynamiczny Navigator jest glowny. Statyczny hub jest zapasowym i równoległym punktem dostepu, ale powinien zachowywac ten sam jezyk linkow i podobny priorytet kafelkow.

## 10. Minimalna procedura awaryjna

Jesli czas jest krytyczny, operator powinien wejsc w tej kolejnosci:

1. `/ui/reports/`
2. `run logs (Latest 20)`
3. `daily_investment_watchlist_report_generator.log`
4. `reports/stack-summary`
5. `failed_watchlist_report_cycle_*.json`

Ta sciezka minimalizuje czas dojscia od ogolnego stanu stacka do konkretnego sygnalu awarii.