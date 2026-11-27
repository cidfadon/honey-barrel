"""Tests for watchlist.py — SQLite CRUD, no network calls."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Patch config side-effects (directory creation) before importing
_test_tmp = tempfile.mkdtemp()
os.environ["DATA_CACHE_DIR"] = os.path.join(_test_tmp, "cache")
os.environ["MODEL_DIR"] = os.path.join(_test_tmp, "models")

# Allow imports from the investment-analyst-api package root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config as cfg


@pytest.fixture(autouse=True)
def _tmp_watchlist_db(tmp_path, monkeypatch):
    """Point WATCHLIST_DB at a temp file for every test."""
    db_path = tmp_path / "test_watchlist.db"
    monkeypatch.setattr(cfg, "WATCHLIST_DB", db_path)
    # Also patch the local reference inside the watchlist module
    import watchlist as wl_mod
    monkeypatch.setattr(wl_mod, "WATCHLIST_DB", db_path)
    yield


def _mgr():
    from watchlist import WatchListManager
    return WatchListManager()


class TestAddStock:
    def test_add_returns_success(self):
        mgr = _mgr()
        result = mgr.add_stock("AAPL", name="Apple Inc", notes="tech blue chip")
        assert result["success"] is True
        assert result["ticker"] == "AAPL"

    def test_add_uppercases_ticker(self):
        mgr = _mgr()
        mgr.add_stock("msft")
        tickers = mgr.get_tickers()
        assert "MSFT" in tickers

    def test_add_duplicate_fails(self):
        mgr = _mgr()
        mgr.add_stock("AAPL")
        result = mgr.add_stock("AAPL")
        assert result["success"] is False
        assert "already" in result["error"]


class TestRemoveStock:
    def test_remove_existing(self):
        mgr = _mgr()
        mgr.add_stock("GOOG")
        result = mgr.remove_stock("GOOG")
        assert result["success"] is True
        assert mgr.get_tickers() == []

    def test_remove_nonexistent(self):
        mgr = _mgr()
        result = mgr.remove_stock("NOPE")
        assert result["success"] is False


class TestGetWatchlist:
    def test_empty_on_fresh_db(self):
        mgr = _mgr()
        result = mgr.get_watchlist()
        assert result["success"] is True
        assert result["count"] == 0
        assert result["stocks"] == []

    def test_returns_all_added_stocks(self):
        mgr = _mgr()
        mgr.add_stock("AAPL")
        mgr.add_stock("MSFT")
        result = mgr.get_watchlist()
        assert result["count"] == 2
        tickers = {s["ticker"] for s in result["stocks"]}
        assert tickers == {"AAPL", "MSFT"}


class TestGetTickers:
    def test_returns_list_of_strings(self):
        mgr = _mgr()
        mgr.add_stock("TSLA")
        tickers = mgr.get_tickers()
        assert isinstance(tickers, list)
        assert "TSLA" in tickers


class TestClearWatchlist:
    def test_clear_removes_everything(self):
        mgr = _mgr()
        mgr.add_stock("A")
        mgr.add_stock("B")
        mgr.add_stock("C")
        result = mgr.clear_watchlist()
        assert result["success"] is True
        assert mgr.get_tickers() == []

    def test_clear_on_empty_is_ok(self):
        mgr = _mgr()
        result = mgr.clear_watchlist()
        assert result["success"] is True
