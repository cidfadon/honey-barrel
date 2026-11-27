"""Extended guardrails tests — covers require_confirm_header_if_live and check_daily_cap."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.config import settings
from app.guardrails import check_daily_cap, check_notional, require_confirm_header_if_live


# ---------------------------------------------------------------------------
# require_confirm_header_if_live
# ---------------------------------------------------------------------------

class TestRequireConfirmHeaderIfLive:
    def test_noop_when_not_live(self, monkeypatch):
        monkeypatch.setattr(settings, "t212_mode", "mock")
        request = MagicMock()
        request.headers.get.return_value = None
        require_confirm_header_if_live(request)  # should not raise

    def test_passes_when_live_and_header_present(self, monkeypatch):
        monkeypatch.setattr(settings, "t212_mode", "live")
        request = MagicMock()
        request.headers.get.return_value = "yes"
        require_confirm_header_if_live(request)  # should not raise

    def test_raises_428_when_live_and_no_header(self, monkeypatch):
        monkeypatch.setattr(settings, "t212_mode", "live")
        request = MagicMock()
        request.headers.get.return_value = None
        with pytest.raises(HTTPException) as exc:
            require_confirm_header_if_live(request)
        assert exc.value.status_code == 428

    def test_raises_428_when_live_and_wrong_header(self, monkeypatch):
        monkeypatch.setattr(settings, "t212_mode", "live")
        request = MagicMock()
        request.headers.get.return_value = "no"
        with pytest.raises(HTTPException) as exc:
            require_confirm_header_if_live(request)
        assert exc.value.status_code == 428


# ---------------------------------------------------------------------------
# check_daily_cap
# ---------------------------------------------------------------------------

class TestCheckDailyCap:
    def _make_session(self, order_count: int):
        """Return a mock DB session that says `order_count` orders exist today."""
        session = MagicMock()
        query = session.query.return_value
        query.filter.return_value.scalar.return_value = order_count
        return session

    def test_passes_when_under_cap(self):
        db = self._make_session(0)
        check_daily_cap(db)  # should not raise

    def test_raises_429_when_at_cap(self, monkeypatch):
        monkeypatch.setattr(settings, "max_orders_per_day", 3)
        db = self._make_session(3)
        with pytest.raises(HTTPException) as exc:
            check_daily_cap(db)
        assert exc.value.status_code == 429

    def test_raises_429_when_over_cap(self, monkeypatch):
        monkeypatch.setattr(settings, "max_orders_per_day", 2)
        db = self._make_session(5)
        with pytest.raises(HTTPException) as exc:
            check_daily_cap(db)
        assert exc.value.status_code == 429


# ---------------------------------------------------------------------------
# check_notional edge cases
# ---------------------------------------------------------------------------

class TestCheckNotionalEdgeCases:
    def test_none_price_hint_passes(self):
        check_notional(qty=999.0, price_hint=None)  # should not raise

    def test_exact_boundary_passes(self, monkeypatch):
        monkeypatch.setattr(settings, "max_notional_eur", 100.0)
        check_notional(qty=1.0, price_hint=100.0)  # equal to cap, not over

    def test_just_over_boundary_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "max_notional_eur", 100.0)
        with pytest.raises(HTTPException) as exc:
            check_notional(qty=1.0, price_hint=100.01)
        assert exc.value.status_code == 412
