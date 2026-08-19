"""MCP tool catalogue + dispatcher for alpaca-mcp.

Tool result envelope follows the MCP convention used by mcp-toolbox and
workspace-mcp: ``{"content": [{"type": "text", "text": "..."}]}``.

Write tools (anything that places, modifies, cancels, or closes) require
``X-Confirm: true`` on the HTTP request when the server is running in
``ALPACA_MODE=live``.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status

from .alpaca_client import AlpacaClient, GuardrailConfig, GuardrailState
from .guardrails import enforce_order_guardrails


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

WRITE_TOOLS = frozenset(
    {
        "order_place_market",
        "order_place_limit",
        "order_cancel",
        "position_close",
    }
)


def list_tools() -> list[dict[str, Any]]:
    return [
        # ---- read ----
        {
            "name": "account_get",
            "description": "Retrieve Alpaca trading account information.",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "positions_list",
            "description": "List all open positions.",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "position_get",
            "description": "Get the open position for a single symbol.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol"}
                },
                "required": ["symbol"],
            },
        },
        {
            "name": "orders_list",
            "description": "List orders (optionally filtered by status).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "default": "all",
                    },
                    "limit": {"type": "integer", "default": 50},
                },
                "required": [],
            },
        },
        {
            "name": "order_get",
            "description": "Retrieve a specific order by id.",
            "inputSchema": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
        {
            "name": "clock_get",
            "description": "Get the Alpaca market clock (open/close times).",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "quote_latest",
            "description": "Latest NBBO quote for a symbol.",
            "inputSchema": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
        {
            "name": "bars_get",
            "description": "Historical bars for a symbol.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "timeframe": {
                        "type": "string",
                        "enum": ["1Min", "5Min", "15Min", "1Hour", "1Day"],
                        "default": "1Day",
                    },
                    "limit": {"type": "integer", "default": 30},
                },
                "required": ["symbol"],
            },
        },
        # ---- write ----
        {
            "name": "order_place_market",
            "description": (
                "Place a market order for a US equity symbol. Requires "
                "X-Confirm: true header in live mode."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "qty": {"type": "number", "exclusiveMinimum": 0},
                    "side": {"type": "string", "enum": ["buy", "sell"]},
                    "time_in_force": {
                        "type": "string",
                        "enum": ["day", "gtc", "opg", "ioc", "fok", "cls"],
                        "default": "day",
                    },
                },
                "required": ["symbol", "qty", "side"],
            },
        },
        {
            "name": "order_place_limit",
            "description": (
                "Place a limit order for a US equity symbol. Requires "
                "X-Confirm: true header in live mode."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "qty": {"type": "number", "exclusiveMinimum": 0},
                    "side": {"type": "string", "enum": ["buy", "sell"]},
                    "limit_price": {"type": "number", "exclusiveMinimum": 0},
                    "time_in_force": {
                        "type": "string",
                        "enum": ["day", "gtc", "opg", "ioc", "fok", "cls"],
                        "default": "day",
                    },
                },
                "required": ["symbol", "qty", "side", "limit_price"],
            },
        },
        {
            "name": "order_cancel",
            "description": (
                "Cancel an open order by id. Requires X-Confirm: true header "
                "in live mode."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
        {
            "name": "position_close",
            "description": (
                "Close (liquidate) an open position for a single symbol. "
                "Requires X-Confirm: true header in live mode."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_text_envelope(payload: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, default=str, ensure_ascii=False),
            }
        ]
    }


def _model_to_dict(obj: Any) -> Any:
    """Best-effort serialise an alpaca-py SDK model into a plain dict."""
    if obj is None:
        return None
    if isinstance(obj, (list, tuple)):
        return [_model_to_dict(o) for o in obj]
    # alpaca-py uses Pydantic v2 BaseModel under the hood
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "__dict__"):
        return {k: _model_to_dict(v) for k, v in obj.__dict__.items()}
    return obj


def _require_confirmation(client: AlpacaClient, header_value: str | None) -> None:
    if client.mode != "live":
        return
    if not header_value or header_value.strip().lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "confirmation_required",
                "message": (
                    "Live trading requires the 'X-Confirm: true' header on "
                    "any write tool call (place/cancel/close)."
                ),
            },
        )


def _estimate_market_notional(
    client: AlpacaClient, symbol: str, qty: float, side: str
) -> float:
    """Use the latest quote so the guardrail compares apples to apples.

    Buy → ask price (worst case fill); Sell → bid price.
    Falls back to qty * 1.0 if the quote endpoint errors out, which keeps
    behaviour conservative when market data is unavailable.
    """
    try:
        q = client.get_latest_quote(symbol)
    except Exception:  # noqa: BLE001 — guardrail must not break on data hiccup
        return float(qty)

    if q is None:
        return float(qty)

    price = q.ask_price if side.lower() == "buy" else q.bid_price
    if not price or price <= 0:
        # NBBO sometimes reports 0 outside RTH; fall back to the other side.
        price = q.bid_price if side.lower() == "buy" else q.ask_price
    if not price or price <= 0:
        return float(qty)
    return float(qty) * float(price)


def _remaining_buy_notional(config: GuardrailConfig, state: GuardrailState) -> float:
    state.reset_if_new_day()
    return max(0.0, float(config.max_notional_usd) - float(state.buy_notional_today))


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

async def handle_tool_call(
    alpaca: AlpacaClient,
    config: GuardrailConfig,
    state: GuardrailState,
    params: dict[str, Any],
    x_confirm_header: str | None = None,
) -> dict[str, Any]:
    name = params.get("name")
    args: dict[str, Any] = params.get("arguments") or {}

    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "missing_tool_name"},
        )

    if name in WRITE_TOOLS:
        _require_confirmation(alpaca, x_confirm_header)

    # ---- read -----------------------------------------------------------
    if name == "account_get":
        return _to_text_envelope(_model_to_dict(alpaca.get_account()))

    if name == "positions_list":
        return _to_text_envelope(_model_to_dict(alpaca.list_positions()))

    if name == "position_get":
        symbol = _required_str(args, "symbol")
        return _to_text_envelope(_model_to_dict(alpaca.get_position(symbol)))

    if name == "orders_list":
        status_arg = args.get("status")
        limit = int(args.get("limit", 50))
        return _to_text_envelope(
            _model_to_dict(alpaca.list_orders(status=status_arg, limit=limit))
        )

    if name == "order_get":
        return _to_text_envelope(
            _model_to_dict(alpaca.get_order(_required_str(args, "order_id")))
        )

    if name == "clock_get":
        return _to_text_envelope(_model_to_dict(alpaca.get_clock()))

    if name == "quote_latest":
        return _to_text_envelope(
            _model_to_dict(alpaca.get_latest_quote(_required_str(args, "symbol")))
        )

    if name == "bars_get":
        return _to_text_envelope(
            _model_to_dict(
                alpaca.get_bars(
                    symbol=_required_str(args, "symbol"),
                    timeframe=str(args.get("timeframe", "1Day")),
                    limit=int(args.get("limit", 30)),
                )
            )
        )

    # ---- write ----------------------------------------------------------
    if name == "order_place_market":
        symbol = _required_str(args, "symbol")
        qty = _required_pos_number(args, "qty")
        side = _required_str(args, "side")
        tif = str(args.get("time_in_force", "day"))

        notional = _estimate_market_notional(alpaca, symbol, qty, side)
        enforce_order_guardrails(config, state, side=side, notional_usd=notional)

        order = alpaca.place_market_order(
            symbol=symbol, qty=qty, side=side, time_in_force=tif
        )
        state.record_execution(side, notional)
        return _to_text_envelope(
            {
                "order": _model_to_dict(order),
                "estimated_notional_usd": notional,
                "remaining_buy_notional_usd": _remaining_buy_notional(config, state),
            }
        )

    if name == "order_place_limit":
        symbol = _required_str(args, "symbol")
        qty = _required_pos_number(args, "qty")
        side = _required_str(args, "side")
        limit_price = _required_pos_number(args, "limit_price")
        tif = str(args.get("time_in_force", "day"))

        notional = float(qty) * float(limit_price)
        enforce_order_guardrails(config, state, side=side, notional_usd=notional)

        order = alpaca.place_limit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            limit_price=limit_price,
            time_in_force=tif,
        )
        state.record_execution(side, notional)
        return _to_text_envelope(
            {
                "order": _model_to_dict(order),
                "notional_usd": notional,
                "remaining_buy_notional_usd": _remaining_buy_notional(config, state),
            }
        )

    if name == "order_cancel":
        alpaca.cancel_order(_required_str(args, "order_id"))
        return _to_text_envelope({"status": "cancelled"})

    if name == "position_close":
        order = alpaca.close_position(_required_str(args, "symbol"))
        return _to_text_envelope({"close_order": _model_to_dict(order)})

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": "unknown_tool", "name": name},
    )


# ---------------------------------------------------------------------------
# Tiny argument helpers (system-boundary validation only)
# ---------------------------------------------------------------------------

def _required_str(args: dict[str, Any], key: str) -> str:
    val = args.get(key)
    if not isinstance(val, str) or not val.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_argument", "key": key, "expected": "string"},
        )
    return val.strip()


def _required_pos_number(args: dict[str, Any], key: str) -> float:
    val = args.get(key)
    if not isinstance(val, (int, float)) or isinstance(val, bool) or val <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_argument",
                "key": key,
                "expected": "positive number",
            },
        )
    return float(val)
