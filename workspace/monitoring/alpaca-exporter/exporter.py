#!/usr/bin/env python3
"""Alpaca Prometheus exporter.

Polls the investment-analyst-api to collect Alpaca account,
position and guardrail data and exposes Prometheus metrics on port 9111.
"""

import os
import time
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

import requests
from prometheus_client import (
    Gauge,
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s alpaca-exporter %(levelname)s %(message)s",
)
log = logging.getLogger("alpaca-exporter")

ANALYST_URL = os.getenv("ANALYST_URL", "http://investment-analyst-api:8001").rstrip("/")
EXPORTER_PORT = int(os.getenv("EXPORTER_PORT", "9111"))
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "20"))

registry = CollectorRegistry()

# --- Availability ---
alpaca_up = Gauge("alpaca_up", "Alpaca API availability via investment-analyst-api (1=up)", registry=registry)
alpaca_api_latency = Histogram(
    "alpaca_api_latency_seconds",
    "Latency of investment-analyst-api calls",
    ["endpoint"],
    registry=registry,
)

# --- Account ---
alpaca_account_equity = Gauge("alpaca_account_equity_usd", "Total account equity in USD", registry=registry)
alpaca_account_cash = Gauge("alpaca_account_cash_usd", "Available cash in USD", registry=registry)
alpaca_account_buying_power = Gauge("alpaca_account_buying_power_usd", "Buying power in USD", registry=registry)
alpaca_account_portfolio_value = Gauge("alpaca_account_portfolio_value_usd", "Total portfolio value in USD", registry=registry)
alpaca_account_long_market_value = Gauge("alpaca_account_long_market_value_usd", "Long positions market value in USD", registry=registry)
alpaca_account_last_equity = Gauge("alpaca_account_last_equity_usd", "Equity at last market close in USD", registry=registry)

# --- Portfolio metrics ---
alpaca_positions_total = Gauge("alpaca_positions_total", "Number of open positions", registry=registry)
alpaca_total_unrealized_pl = Gauge("alpaca_total_unrealized_pl_usd", "Total unrealized P&L in USD", registry=registry)
alpaca_total_cost_basis = Gauge("alpaca_total_cost_basis_usd", "Total cost basis of all positions in USD", registry=registry)
alpaca_weighted_unrealized_plpc = Gauge("alpaca_weighted_unrealized_plpc", "Weighted unrealized P&L as fraction", registry=registry)
alpaca_day_equity_change = Gauge("alpaca_day_equity_change_usd", "Equity change since last close in USD", registry=registry)
alpaca_day_equity_change_pct = Gauge("alpaca_day_equity_change_pct", "Equity change since last close as fraction", registry=registry)

# --- Per-position metrics ---
alpaca_position_market_value = Gauge("alpaca_position_market_value_usd", "Market value per position in USD", ["symbol"], registry=registry)
alpaca_position_unrealized_pl = Gauge("alpaca_position_unrealized_pl_usd", "Unrealized P&L per position in USD", ["symbol"], registry=registry)
alpaca_position_unrealized_plpc = Gauge("alpaca_position_unrealized_plpc", "Unrealized P&L fraction per position", ["symbol"], registry=registry)
alpaca_position_intraday_pl = Gauge("alpaca_position_intraday_pl_usd", "Intraday P&L per position in USD", ["symbol"], registry=registry)
alpaca_position_qty = Gauge("alpaca_position_qty", "Quantity held per position", ["symbol"], registry=registry)
alpaca_position_current_price = Gauge("alpaca_position_current_price_usd", "Current price per position in USD", ["symbol"], registry=registry)
alpaca_position_avg_entry_price = Gauge("alpaca_position_avg_entry_price_usd", "Average entry price per position in USD", ["symbol"], registry=registry)
alpaca_position_cost_basis = Gauge("alpaca_position_cost_basis_usd", "Cost basis per position in USD", ["symbol"], registry=registry)

# --- Guardrails ---
alpaca_guardrail_max_notional = Gauge("alpaca_guardrail_max_notional_usd", "Max allowed notional per order in USD", registry=registry)
alpaca_guardrail_remaining_buy = Gauge("alpaca_guardrail_remaining_buy_notional_usd", "Remaining buy budget today in USD", registry=registry)
alpaca_guardrail_buy_today = Gauge("alpaca_guardrail_buy_notional_today_usd", "Buy notional executed today in USD", registry=registry)
alpaca_guardrail_orders_today = Gauge("alpaca_guardrail_orders_today", "Number of orders executed today", registry=registry)
alpaca_guardrail_max_orders = Gauge("alpaca_guardrail_max_orders_per_day", "Maximum orders allowed per day", registry=registry)
alpaca_guardrail_auto_execute = Gauge("alpaca_guardrail_auto_execute", "Auto-execute mode enabled (1=yes)", registry=registry)

# --- Scrape health ---
alpaca_scrape_errors = Counter("alpaca_scrape_errors_total", "Failed scrapes", ["endpoint"], registry=registry)
alpaca_last_scrape = Gauge("alpaca_last_scrape_timestamp_seconds", "Unix timestamp of last successful scrape", registry=registry)


def _get(path: str, timeout: int = 15) -> tuple[dict | None, float]:
    url = f"{ANALYST_URL}{path}"
    start = time.monotonic()
    try:
        r = requests.get(url, timeout=timeout)
        latency = time.monotonic() - start
        if r.status_code == 200:
            return r.json(), latency
        return None, latency
    except Exception as exc:
        latency = time.monotonic() - start
        log.warning("GET %s failed: %s", path, exc)
        return None, latency


def _float(v) -> float:
    try:
        if v is None:
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _scrape() -> bool:
    ok = False

    # /api/trading/portfolio — account + positions
    data, lat = _get("/api/trading/portfolio")
    alpaca_api_latency.labels(endpoint="/api/trading/portfolio").observe(lat)
    if data and data.get("success"):
        acc = data.get("account") or {}
        alpaca_account_equity.set(_float(acc.get("equity")))
        alpaca_account_cash.set(_float(acc.get("cash")))
        alpaca_account_buying_power.set(_float(acc.get("buying_power")))
        alpaca_account_portfolio_value.set(_float(acc.get("portfolio_value")))
        alpaca_account_long_market_value.set(_float(acc.get("long_market_value")))
        alpaca_account_last_equity.set(_float(acc.get("last_equity")))

        met = data.get("metrics") or {}
        alpaca_positions_total.set(_float(met.get("open_positions")))
        alpaca_total_unrealized_pl.set(_float(met.get("total_unrealized_pl")))
        alpaca_total_cost_basis.set(_float(met.get("total_cost_basis")))
        alpaca_weighted_unrealized_plpc.set(_float(met.get("weighted_unrealized_plpc")))
        alpaca_day_equity_change.set(_float(met.get("day_equity_change")))
        alpaca_day_equity_change_pct.set(_float(met.get("day_equity_change_pct")))

        for pos in data.get("positions") or []:
            sym = str(pos.get("symbol") or "").upper()
            if not sym:
                continue
            alpaca_position_market_value.labels(symbol=sym).set(_float(pos.get("market_value")))
            alpaca_position_unrealized_pl.labels(symbol=sym).set(_float(pos.get("unrealized_pl")))
            alpaca_position_unrealized_plpc.labels(symbol=sym).set(_float(pos.get("unrealized_plpc")))
            alpaca_position_intraday_pl.labels(symbol=sym).set(_float(pos.get("unrealized_intraday_pl")))
            alpaca_position_qty.labels(symbol=sym).set(_float(pos.get("qty")))
            alpaca_position_current_price.labels(symbol=sym).set(_float(pos.get("current_price")))
            alpaca_position_avg_entry_price.labels(symbol=sym).set(_float(pos.get("avg_entry_price")))
            alpaca_position_cost_basis.labels(symbol=sym).set(_float(pos.get("cost_basis")))

        ok = True
    else:
        alpaca_scrape_errors.labels(endpoint="/api/trading/portfolio").inc()

    # /api/trading/guardrails
    data, lat = _get("/api/trading/guardrails")
    alpaca_api_latency.labels(endpoint="/api/trading/guardrails").observe(lat)
    if data and data.get("success"):
        alpaca_guardrail_max_notional.set(_float(data.get("max_notional_usd")))
        alpaca_guardrail_remaining_buy.set(_float(data.get("remaining_buy_notional_usd")))
        alpaca_guardrail_buy_today.set(_float(data.get("buy_notional_today")))
        alpaca_guardrail_orders_today.set(_float(data.get("orders_today")))
        alpaca_guardrail_max_orders.set(_float(data.get("max_orders_per_day")))
        alpaca_guardrail_auto_execute.set(1.0 if data.get("auto_execute") else 0.0)
        ok = True
    else:
        alpaca_scrape_errors.labels(endpoint="/api/trading/guardrails").inc()

    return ok


def _collect_loop():
    while True:
        try:
            success = _scrape()
            alpaca_up.set(1 if success else 0)
            if success:
                alpaca_last_scrape.set(time.time())
        except Exception as exc:
            log.error("Unexpected scrape error: %s", exc)
            alpaca_up.set(0)
        time.sleep(SCRAPE_INTERVAL)


class MetricsHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path in ("/metrics", "/metrics/"):
            output = generate_latest(registry)
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(output)))
            self.end_headers()
            self.wfile.write(output)
        elif self.path in ("/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok\n")
        else:
            self.send_response(404)
            self.end_headers()


def main():
    log.info("Alpaca exporter starting on port %d → %s", EXPORTER_PORT, ANALYST_URL)
    t = threading.Thread(target=_collect_loop, daemon=True, name="alpaca-collect")
    t.start()
    server = HTTPServer(("0.0.0.0", EXPORTER_PORT), MetricsHandler)
    log.info("Serving /metrics on http://0.0.0.0:%d", EXPORTER_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    main()
