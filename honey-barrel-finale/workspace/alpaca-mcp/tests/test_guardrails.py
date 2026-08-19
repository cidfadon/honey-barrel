"""Tests for alpaca-mcp guardrails — order cap & notional enforcement."""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

# Add the alpaca-mcp package root so ``from app.…`` works.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.alpaca_client import GuardrailConfig, GuardrailState
from app.guardrails import enforce_order_guardrails


# ---------------------------------------------------------------------------
# GuardrailConfig / GuardrailState unit tests
# ---------------------------------------------------------------------------

class TestGuardrailConfig:
    def test_defaults(self):
        cfg = GuardrailConfig()
        assert cfg.max_orders_per_day == 5
        assert cfg.max_notional_usd == 200.0
        assert cfg.auto_execute is False

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("MAX_ORDERS_PER_DAY", "10")
        monkeypatch.setenv("MAX_NOTIONAL_USD", "500.0")
        monkeypatch.setenv("AUTO_EXECUTE", "true")
        cfg = GuardrailConfig.from_env()
        assert cfg.max_orders_per_day == 10
        assert cfg.max_notional_usd == 500.0
        assert cfg.auto_execute is True


class TestGuardrailState:
    def test_initial_state(self):
        state = GuardrailState()
        assert state.orders_today == 0
        assert state.buy_notional_today == 0.0
        assert state.sell_notional_today == 0.0
        assert state.current_date == date.today()

    def test_increment_orders(self):
        state = GuardrailState()
        state.record_execution("buy", 10.0)
        state.record_execution("sell", 15.0)
        assert state.orders_today == 2
        assert state.buy_notional_today == 10.0
        assert state.sell_notional_today == 15.0

    def test_reset_if_new_day(self):
        state = GuardrailState()
        state.orders_today = 5
        state.buy_notional_today = 42.5
        state.sell_notional_today = 12.0
        state.current_date = date.today() - timedelta(days=1)
        state.reset_if_new_day()
        assert state.orders_today == 0
        assert state.buy_notional_today == 0.0
        assert state.sell_notional_today == 0.0
        assert state.current_date == date.today()

    def test_no_reset_same_day(self):
        state = GuardrailState()
        state.orders_today = 3
        state.buy_notional_today = 17.25
        state.sell_notional_today = 5.5
        state.current_date = date.today()
        state.reset_if_new_day()
        assert state.orders_today == 3
        assert state.buy_notional_today == 17.25
        assert state.sell_notional_today == 5.5


# ---------------------------------------------------------------------------
# enforce_order_guardrails
# ---------------------------------------------------------------------------

class TestEnforceOrderGuardrails:
    def _cfg(self, max_orders: int = 5, max_notional: float = 200.0):
        return GuardrailConfig(
            max_orders_per_day=max_orders,
            max_notional_usd=max_notional,
            auto_execute=False,
        )

    def test_passes_when_under_both_caps(self):
        cfg = self._cfg()
        state = GuardrailState()
        enforce_order_guardrails(cfg, state, side="buy", notional_usd=50.0)
        state.record_execution("buy", 50.0)
        assert state.orders_today == 1
        assert state.buy_notional_today == 50.0

    def test_blocks_when_orders_at_cap(self):
        cfg = self._cfg(max_orders=2)
        state = GuardrailState()
        state.orders_today = 2
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            enforce_order_guardrails(cfg, state, side="buy", notional_usd=10.0)
        assert exc.value.status_code == 403
        assert "max_orders_per_day" in str(exc.value.detail)

    def test_blocks_when_notional_exceeds_cap(self):
        cfg = self._cfg(max_notional=100.0)
        state = GuardrailState()
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            enforce_order_guardrails(cfg, state, side="buy", notional_usd=150.0)
        assert exc.value.status_code == 403
        assert "max_buy_notional" in str(exc.value.detail)

    def test_blocks_when_daily_buy_budget_exhausted(self):
        cfg = self._cfg(max_notional=100.0)
        state = GuardrailState()
        state.record_execution("buy", 60.0)
        state.record_execution("buy", 40.0)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            enforce_order_guardrails(cfg, state, side="buy", notional_usd=1.0)
        assert exc.value.status_code == 403
        assert "remaining_buy_notional" in str(exc.value.detail)

    def test_increments_after_pass(self):
        cfg = self._cfg()
        state = GuardrailState()
        enforce_order_guardrails(cfg, state, side="buy", notional_usd=10.0)
        state.record_execution("buy", 10.0)
        enforce_order_guardrails(cfg, state, side="sell", notional_usd=10.0)
        state.record_execution("sell", 10.0)
        assert state.orders_today == 2
        assert state.buy_notional_today == 10.0
        assert state.sell_notional_today == 10.0

    def test_day_rollover_resets_counter(self):
        cfg = self._cfg(max_orders=1)
        state = GuardrailState()
        state.orders_today = 1
        state.buy_notional_today = 99.0
        state.sell_notional_today = 77.0
        state.current_date = date.today() - timedelta(days=1)
        # After day rollover the counter resets, so this should pass
        enforce_order_guardrails(cfg, state, side="buy", notional_usd=10.0)
        assert state.orders_today == 0
        assert state.buy_notional_today == 0.0
        assert state.sell_notional_today == 0.0
        assert state.current_date == date.today()
