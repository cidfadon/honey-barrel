"""Server-side guardrails enforced before any Alpaca write call."""

from __future__ import annotations

from fastapi import HTTPException, status

from .alpaca_client import GuardrailConfig, GuardrailState


def enforce_order_guardrails(
    config: GuardrailConfig,
    state: GuardrailState,
    side: str,
    notional_usd: float,
) -> None:
    """Raise HTTP 403 if the requested order violates daily/notional caps."""
    state.reset_if_new_day()

    if state.orders_today >= config.max_orders_per_day:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "max_orders_per_day_exceeded",
                "message": (
                    f"Maximum number of orders per day "
                    f"({config.max_orders_per_day}) has been reached."
                ),
                "orders_today": state.orders_today,
            },
        )

    if side.lower() == "buy":
        remaining_buy_notional = max(0.0, float(config.max_notional_usd) - float(state.buy_notional_today))
        if notional_usd > remaining_buy_notional:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "max_buy_notional_exceeded",
                    "message": (
                        f"Daily BUY notional ${state.buy_notional_today:.2f} plus this order ${notional_usd:.2f} "
                        f"would exceed configured max_notional_usd ${config.max_notional_usd:.2f}."
                    ),
                    "notional_usd": notional_usd,
                    "max_notional_usd": config.max_notional_usd,
                    "buy_notional_today": state.buy_notional_today,
                    "remaining_buy_notional_usd": remaining_buy_notional,
                },
            )

    if side.lower() != "buy" and notional_usd > config.max_notional_usd:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "max_notional_exceeded",
                "message": (
                    f"Order notional ${notional_usd:.2f} exceeds configured "
                    f"max_notional_usd ${config.max_notional_usd:.2f}."
                ),
                "notional_usd": notional_usd,
                "max_notional_usd": config.max_notional_usd,
            },
        )
