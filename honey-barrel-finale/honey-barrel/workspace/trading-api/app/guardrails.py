"""Safety checks executed BEFORE any order leaves the container."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .models import Order


def require_confirm_header_if_live(request: Request) -> None:
    if settings.t212_mode == "live" and request.headers.get("x-confirm") != "yes":
        raise HTTPException(
            status_code=428,
            detail="X-Confirm: yes header is required in live mode.",
        )


def check_daily_cap(db: Session) -> None:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    count = db.query(func.count(Order.id)).filter(Order.ts >= since).scalar() or 0
    if count >= settings.max_orders_per_day:
        raise HTTPException(
            status_code=429,
            detail=f"Daily order cap ({settings.max_orders_per_day}) reached.",
        )


def check_notional(qty: float, price_hint: float | None) -> None:
    if price_hint is None:
        return
    notional = abs(qty) * price_hint
    if notional > settings.max_notional_eur:
        raise HTTPException(
            status_code=412,
            detail=f"Notional {notional:.2f} exceeds MAX_NOTIONAL_EUR={settings.max_notional_eur}",
        )
