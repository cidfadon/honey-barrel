from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PortfolioSnapshot, T212Call
from ..t212 import get_client

router = APIRouter(prefix="/api", tags=["portfolio"])


def _log_call(db: Session, endpoint: str, method: str, status: int, body, latency: int) -> None:
    db.add(T212Call(endpoint=endpoint, method=method, http_status=status,
                    response=body, latency_ms=latency))


@router.get("/portfolio")
def portfolio(db: Session = Depends(get_db)):
    cli = get_client()
    cs, cash, lat1 = cli.cash()
    ps, pos, lat2 = cli.positions()
    _log_call(db, "/equity/account/cash", "GET", cs, cash, lat1)
    _log_call(db, "/equity/positions",    "GET", ps, pos, lat2)
    snap = PortfolioSnapshot(cash=cash, positions=pos)
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return {"snapshot_id": snap.id, "cash": cash, "positions": pos}


@router.get("/orders")
def open_orders(db: Session = Depends(get_db)):
    cli = get_client()
    status, body, lat = cli.open_orders()
    _log_call(db, "/equity/orders", "GET", status, body, lat)
    db.commit()
    return body


@router.get("/history")
def history(limit: int = 50, db: Session = Depends(get_db)):
    cli = get_client()
    status, body, lat = cli.history(limit=limit)
    _log_call(db, "/equity/history/orders", "GET", status, body, lat)
    db.commit()
    return body
