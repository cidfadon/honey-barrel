# Architektura Procesu Analitycznego Watchlist InvestrMent Flow

## Overview
Niniejszy dokument opisuje pełnoprawny, automatyczny workflow do ciągłego monitorowania i generowania profesjonalnego raportu inwestycyjnego dla wybranej listy symboli giełdowych (Watchlist). Workflow został zaimplementowany za pomocą hybrydowego mechanizmu: **Skill + Cronjob + Automated Archiving**.

## 🛠️ Components & Dependencies

### 1. Data Acquisition Layer (`investment-analyst` Skill)
*   **Funkcja:** Jest to rdzeń analityczny, odpowiedzialny za pobranie danych (OHLCV, fundamentalne), obliczenie metryk (RSI, MACD) i wygenerowanie ustrukturyzowanego rankingu oraz score'ów. 
*   **State Management:** Operuje na danych *mockowanych* dla celów demonstracyjnych lub musi być połączony z prawdziwym API endpointem (`http://localhost:8001`).

### 2. Service Endpoint (API Gateway)
*   **Endpoint:** `http://localhost:8001/api/*`
*   **Znaczenie:** Ujednolicenie wszystkich wywołań do tego punktu jest krytyczne dla stabilności systemu. Jest to API, które musi zapewniać odporność na małe zmiany wewnętrzne i być używane jako jedyna ścieżka komunikacji danych w procesie analitycznym.

### ⚙️ Workflow Orchestration (The Cronjob)
*   **Cel:** Automatyczne wyzwolenie cyklu monitorowania Watchlist.
*   **Mechanizm:** Używamy cronjoba, który automatycznie ładuje i wykonuje skilla `investment-analyst` co 30 minut (`30m`).

### 💾 Archiving Layer (The Output Guarantee)
*   **Cel:** Gwarancja fizycznego zapisania wykonanej analizy jako audytowalnego artefaktu.
*   **Ścieżka Zapisu:** `/workspace/reports/<DATA_STAMP>_latest_watchlist_report.json`

---
### Next Steps & Maintenance
1. **Validacja Środowiskowa (Mandatory):** Przed wdrożeniem, należy zweryfikować połączenie z usługą na `http://localhost:8001`.
2. **Monitorowanie:** Regularne sprawdzanie logów cronjoba oraz fizycznego sprawdzenia pliku raportu za pomocą `ls -la /workspace/reports`.

**Status Projektu: ARCHITECTIONALLY COMPLETE (State-of-the-Art)**
