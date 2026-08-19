from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..guardrails import check_daily_cap, check_notional, require_confirm_header_if_live
from ..models import Order, T212Call
from ..schemas import LimitOrderIn, MarketOrderIn
from ..t212 import T212Error, get_client

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _signed(qty: float, side: str) -> float:
    return qty if side == "BUY" else -qty


@router.post("/market")
def market_order(payload: MarketOrderIn, request: Request, db: Session = Depends(get_db)):
    require_confirm_header_if_live(request)
    check_daily_cap(db)
    check_notional(payload.quantity, price_hint=None)

    cli = get_client()
    try:
        status, body, lat = cli.place_market(
            payload.ticker, _signed(payload.quantity, payload.side), payload.extended_hours
        )
    except T212Error as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    db.add(T212Call(endpoint="/equity/orders/market", method="POST",
                    payload=payload.model_dump(), response=body,
                    http_status=status, latency_ms=lat))
    order = Order(
        t212_order_id=str(body.get("id")), ticker=payload.ticker, side=payload.side,
        qty=payload.quantity, order_type="MARKET",
        status=body.get("status", "UNKNOWN"), raw=body,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return {"order_id": order.id, "t212": body}


@router.post("/limit")
def limit_order(payload: LimitOrderIn, request: Request, db: Session = Depends(get_db)):
    require_confirm_header_if_live(request)
    check_daily_cap(db)
    check_notional(payload.quantity, price_hint=payload.limit_price)

    cli = get_client()
    try:
        status, body, lat = cli.place_limit(
            payload.ticker, _signed(payload.quantity, payload.side),
            payload.limit_price, payload.time_validity,
        )
    except T212Error as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    db.add(T212Call(endpoint="/equity/orders/limit", method="POST",
                    payload=payload.model_dump(), response=body,
                    http_status=status, latency_ms=lat))
    order = Order(
        t212_order_id=str(body.get("id")), ticker=payload.ticker, side=payload.side,
        qty=payload.quantity, order_type="LIMIT", limit_price=payload.limit_price,
        status=body.get("status", "UNKNOWN"), raw=body,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return {"order_id": order.id, "t212": body}


@router.delete("/{order_id}")
def cancel(order_id: str, request: Request, db: Session = Depends(get_db)):
    require_confirm_header_if_live(request)
    cli = get_client()
    try:
        status, body, lat = cli.cancel(order_id)
    except T212Error as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.add(T212Call(endpoint=f"/equity/orders/{order_id}", method="DELETE",
                    response=body, http_status=status, latency_ms=lat))
    db.commit()
    return body
