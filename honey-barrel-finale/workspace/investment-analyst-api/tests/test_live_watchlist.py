import asyncio
import json
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.responses import HTMLResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import api
from live_watchlist import build_html_page, build_snapshot


def test_build_snapshot_uses_latest_reports_for_each_ticker(tmp_path):
    cron_snapshot = tmp_path / "crontab.txt"
    cron_snapshot.write_text("WATCHLIST_TICKERS='AAPL,MSFT'\n", encoding="utf-8")

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    aapl_report = {
        "symbol": "AAPL",
        "action": "BUY",
        "order_status": "ACCEPTED",
        "submitted_at": "2026-01-01T00:00:00Z",
    }
    (reports_dir / "investment_analysis_cycle_20260101_000001.json").write_text(
        json.dumps(aapl_report),
        encoding="utf-8",
    )

    msft_report = {
        "symbol": "MSFT",
        "action": "HOLD",
        "order_status": "",
        "current_price": 321.1234,
        "final_qty": 0,
        "submitted_at": "2026-01-01T00:05:00Z",
    }
    (reports_dir / "investment_analysis_cycle_20260101_000002.json").write_text(
        json.dumps(msft_report),
        encoding="utf-8",
    )

    payload = build_snapshot(str(cron_snapshot), str(reports_dir), "all", str(tmp_path))

    assert payload["total_tickers"] == 2
    assert payload["counts"]["BUY"] == 1
    assert payload["counts"]["HOLD"] == 1
    assert payload["counts"]["NO_DATA"] == 0
    signals = {row["ticker"]: row["signal"] for row in payload["rows"]}
    assert signals == {"AAPL": "BUY", "MSFT": "HOLD"}
    row_by_ticker = {row["ticker"]: row for row in payload["rows"]}
    assert row_by_ticker["MSFT"]["price"] == 321.1234
    assert "qty" not in row_by_ticker["MSFT"]


def test_build_snapshot_includes_recent_non_watchlist_transactions(tmp_path):
    cron_snapshot = tmp_path / "crontab.txt"
    cron_snapshot.write_text("WATCHLIST_TICKERS='AAPL'\n", encoding="utf-8")

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    (reports_dir / "investment_analysis_cycle_20260101_000001.json").write_text(
        json.dumps({
            "symbol": "AAPL",
            "action": "BUY",
            "order_status": "ACCEPTED",
            "submitted_at": "2026-01-01T00:00:00Z",
            "current_price": 10.50,
        }),
        encoding="utf-8",
    )
    (reports_dir / "investment_analysis_cycle_20260101_000002.json").write_text(
        json.dumps({
            "symbol": "FFAI",
            "action": "SELL",
            "order_status": "FILLED",
            "submitted_at": "2026-01-01T00:01:00Z",
            "execution_price": 5.01,
        }),
        encoding="utf-8",
    )

    payload = build_snapshot(str(cron_snapshot), str(reports_dir), "all", str(tmp_path))

    rows = {row["ticker"]: row for row in payload["rows"]}
    assert rows["AAPL"]["signal"] == "BUY"
    assert rows["FFAI"]["signal"] == "SELL"
    assert rows["FFAI"]["price"] == 5.01


def test_build_snapshot_includes_historical_alpaca_orders_file(tmp_path):
    cron_snapshot = tmp_path / "crontab.txt"
    cron_snapshot.write_text("WATCHLIST_TICKERS='AAPL'\n", encoding="utf-8")

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    history_path = reports_dir / "alpaca_orders_history.jsonl"
    history_path.write_text(
        json.dumps({
            "symbol": "FFAI",
            "side": "buy",
            "status": "filled",
            "submitted_at": "2026-08-17T14:02:03+01:00",
            "filled_avg_price": 5.01,
            "qty": 1.0,
        }) + "\n",
        encoding="utf-8",
    )

    payload = build_snapshot(str(cron_snapshot), str(reports_dir), "all", str(tmp_path))

    rows = {row["ticker"]: row for row in payload["rows"]}
    assert rows["FFAI"]["signal"] == "BUY"
    assert rows["FFAI"]["price"] == 5.01
    assert rows["FFAI"]["status"] == "FILLED"


def test_build_snapshot_keeps_transaction_when_latest_signal_is_hold(tmp_path):
    cron_snapshot = tmp_path / "crontab.txt"
    cron_snapshot.write_text("WATCHLIST_TICKERS='AAPL'\n", encoding="utf-8")

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    (reports_dir / "investment_analysis_cycle_20260101_000001.json").write_text(
        json.dumps({
            "symbol": "AAPL",
            "action": "BUY",
            "order_status": "FILLED",
            "submitted_at": "2026-01-01T00:00:00Z",
            "execution_price": 10.25,
        }),
        encoding="utf-8",
    )
    (reports_dir / "investment_analysis_cycle_20260101_000002.json").write_text(
        json.dumps({
            "symbol": "AAPL",
            "action": "HOLD",
            "order_status": "HOLD",
            "submitted_at": "2026-01-01T00:05:00Z",
            "current_price": 10.55,
        }),
        encoding="utf-8",
    )

    payload = build_snapshot(str(cron_snapshot), str(reports_dir), "all", str(tmp_path))

    buy_rows = [row for row in payload["rows"] if row["ticker"] == "AAPL" and row["signal"] == "BUY"]
    hold_rows = [row for row in payload["rows"] if row["ticker"] == "AAPL" and row["signal"] == "HOLD"]
    assert buy_rows
    assert hold_rows


def test_build_html_page_contains_internal_api_endpoints():
    html = build_html_page()

    assert "Live Watchlist Dashboard" in html
    assert "/api/snapshot" in html
    assert "/report" in html
    assert "<th>Qty</th>" not in html


def test_parse_report_session_summary_normalizes_strategy_to_filename(tmp_path):
    report_path = tmp_path / "investment_analysis_cycle_20260101_000001.json"
    report_path.write_text(
        json.dumps(
            {
                "symbol": "AAPL",
                "action": "BUY",
                "order_status": "FILLED",
                "submitted_at": "2026-01-01T00:00:00Z",
                "financial_strategy_file": "strategies/OPENING_RANGE_BREAKOUT_STRATEGY.md",
            }
        ),
        encoding="utf-8",
    )

    summary = api._parse_report_session_summary(report_path)

    assert summary is not None
    assert summary["financial_strategy"] == "OPENING_RANGE_BREAKOUT_STRATEGY.md"


def test_parse_report_session_summary_uses_first_strategy_filename_from_list(tmp_path):
    report_path = tmp_path / "investment_analysis_cycle_20260101_000002.json"
    report_path.write_text(
        json.dumps(
            {
                "symbol": "MSFT",
                "action": "SELL",
                "order_status": "FILLED",
                "submitted_at": "2026-01-01T00:10:00Z",
                "financial_strategy_files": [
                    "docs/strategies/OPENING_RANGE_BREAKOUT_STRATEGY.md",
                    "docs/strategies/SECONDARY_RULESET.md",
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = api._parse_report_session_summary(report_path)

    assert summary is not None
    assert summary["financial_strategy"] == "OPENING_RANGE_BREAKOUT_STRATEGY.md"


def test_live_watchlist_route_serves_internal_html():
    response = asyncio.run(api.live_watchlist())

    assert isinstance(response, HTMLResponse)
    assert response.status_code == 200
    body = response.body.decode("utf-8")
    assert "Live Watchlist Dashboard" in body
    assert "/api/snapshot" in body
