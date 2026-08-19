"""Alpaca SDK wrapper + guardrail config/state.

Mirrors the pattern from the legacy `trading-api` service: a single client
owns mode selection (paper vs live), and guardrails are enforced server-side
before any write call hits the Alpaca API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import (
    AssetClass,
    OrderSide,
    QueryOrderStatus,
    TimeInForce,
)
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
)


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------

@dataclass
class GuardrailConfig:
    max_orders_per_day: int = 5
    max_notional_usd: float = 200.0
    auto_execute: bool = False

    @classmethod
    def from_env(cls) -> "GuardrailConfig":
        return cls(
            max_orders_per_day=int(os.getenv("MAX_ORDERS_PER_DAY", "5")),
            max_notional_usd=float(os.getenv("MAX_NOTIONAL_USD", "200")),
            auto_execute=os.getenv("AUTO_EXECUTE", "false").lower() == "true",
        )


@dataclass
class GuardrailState:
    current_date: date = field(default_factory=date.today)
    orders_today: int = 0
    buy_notional_today: float = 0.0

    def reset_if_new_day(self) -> None:
        today = date.today()
        if today != self.current_date:
            self.current_date = today
            self.orders_today = 0
            self.buy_notional_today = 0.0

    def record_execution(self, side: str, notional_usd: float) -> None:
        self.reset_if_new_day()
        self.orders_today += 1
        if side.lower() == "buy":
            self.buy_notional_today += max(0.0, float(notional_usd))


# ---------------------------------------------------------------------------
# AlpacaClient
# ---------------------------------------------------------------------------

_TIF_MAP = {
    "day": TimeInForce.DAY,
    "gtc": TimeInForce.GTC,
    "opg": TimeInForce.OPG,
    "ioc": TimeInForce.IOC,
    "fok": TimeInForce.FOK,
    "cls": TimeInForce.CLS,
}

_TF_MAP = {
    "1Min": TimeFrame(1, TimeFrameUnit.Minute),
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
    "1Day": TimeFrame(1, TimeFrameUnit.Day),
}


def _to_tif(value: str) -> TimeInForce:
    enum_val = _TIF_MAP.get(value.lower())
    if enum_val is None:
        raise ValueError(
            f"invalid time_in_force '{value}': "
            f"expected one of {sorted(_TIF_MAP)}"
        )
    return enum_val


def _to_side(value: str) -> OrderSide:
    v = value.lower()
    if v == "buy":
        return OrderSide.BUY
    if v == "sell":
        return OrderSide.SELL
    raise ValueError(f"invalid side '{value}': expected 'buy' or 'sell'")


def _to_timeframe(value: str) -> TimeFrame:
    tf = _TF_MAP.get(value)
    if tf is None:
        raise ValueError(
            f"invalid timeframe '{value}': expected one of {sorted(_TF_MAP)}"
        )
    return tf


class AlpacaClient:
    def __init__(self, api_key_id: str, api_secret_key: str, mode: str = "paper"):
        if mode not in ("paper", "live"):
            raise ValueError("ALPACA_MODE must be 'paper' or 'live'")

        self.mode = mode
        self.is_paper = mode == "paper"

        self.trading_client = TradingClient(
            api_key=api_key_id,
            secret_key=api_secret_key,
            paper=self.is_paper,
        )
        # Market data v2 keys are the same; client picks the right base URL.
        self.data_client = StockHistoricalDataClient(
            api_key=api_key_id,
            secret_key=api_secret_key,
        )

    @classmethod
    def from_env(cls) -> "AlpacaClient":
        api_key_id = os.environ.get("ALPACA_API_KEY_ID")
        api_secret_key = os.environ.get("ALPACA_API_SECRET_KEY")
        if not api_key_id or not api_secret_key:
            raise RuntimeError(
                "ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY must be set"
            )
        mode = os.environ.get("ALPACA_MODE", "paper").lower()
        return cls(api_key_id=api_key_id, api_secret_key=api_secret_key, mode=mode)

    # ----- read ------------------------------------------------------------
    def get_account(self) -> Any:
        return self.trading_client.get_account()

    def list_positions(self) -> Any:
        return self.trading_client.get_all_positions()

    def get_position(self, symbol: str) -> Any:
        return self.trading_client.get_open_position(symbol.upper())

    def list_orders(self, status: str | None = None, limit: int = 50) -> Any:
        if status:
            try:
                qstatus = QueryOrderStatus[status.upper()]
            except KeyError as e:
                raise ValueError(
                    f"invalid status '{status}': expected open|closed|all"
                ) from e
        else:
            qstatus = QueryOrderStatus.ALL
        req = GetOrdersRequest(status=qstatus, limit=limit)
        return self.trading_client.get_orders(filter=req)

    def get_order(self, order_id: str) -> Any:
        return self.trading_client.get_order_by_id(order_id)

    def get_clock(self) -> Any:
        return self.trading_client.get_clock()

    def get_latest_quote(self, symbol: str) -> Any:
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol.upper())
        result = self.data_client.get_stock_latest_quote(req)
        return result.get(symbol.upper())

    def get_bars(
        self,
        symbol: str,
        timeframe: str = "1Day",
        limit: int = 30,
    ) -> Any:
        req = StockBarsRequest(
            symbol_or_symbols=symbol.upper(),
            timeframe=_to_timeframe(timeframe),
            limit=limit,
        )
        bars = self.data_client.get_stock_bars(req)
        return bars.data.get(symbol.upper(), [])

    # ----- write -----------------------------------------------------------
    def place_market_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        time_in_force: str = "day",
    ) -> Any:
        order = MarketOrderRequest(
            symbol=symbol.upper(),
            qty=qty,
            side=_to_side(side),
            time_in_force=_to_tif(time_in_force),
            asset_class=AssetClass.US_EQUITY,
        )
        return self.trading_client.submit_order(order)

    def place_limit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        limit_price: float,
        time_in_force: str = "day",
    ) -> Any:
        order = LimitOrderRequest(
            symbol=symbol.upper(),
            qty=qty,
            side=_to_side(side),
            time_in_force=_to_tif(time_in_force),
            limit_price=limit_price,
            asset_class=AssetClass.US_EQUITY,
        )
        return self.trading_client.submit_order(order)

    def cancel_order(self, order_id: str) -> None:
        # SDK returns None on success and raises APIError on failure.
        self.trading_client.cancel_order_by_id(order_id)

    def close_position(self, symbol: str) -> Any:
        return self.trading_client.close_position(symbol.upper())
