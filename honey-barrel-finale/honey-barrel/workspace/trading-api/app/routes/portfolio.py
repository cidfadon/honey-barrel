import csv
import io
import os
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import DailyTradingLog, LLMAnalysis, Order, PortfolioSnapshot, T212Call
from ..t212 import get_client

router = APIRouter(prefix="/api", tags=["portfolio"])

# ---------------------------------------------------------------------------
# Log directory — written alongside the DB so it's always accessible
# ---------------------------------------------------------------------------
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "daily_logs")


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


# ---------------------------------------------------------------------------
# Daily Trading Log
# ---------------------------------------------------------------------------

class DailyLogIn(BaseModel):
    trade_date: Optional[str] = None   # "YYYY-MM-DD"; defaults to today (UTC)
    profit: Optional[float] = None
    notes: Optional[str] = None


def _build_csv(orders: list, analyses: list, snapshot: dict) -> str:
    """Return a CSV string with one row per order enriched with analysis data."""
    buf = io.StringIO()
    fieldnames = [
        "trade_date", "order_ts", "order_id", "t212_order_id",
        "ticker", "side", "qty", "order_type", "limit_price", "status",
        "analysis_ts", "strategy", "llm_action", "llm_ticker",
        "llm_qty", "llm_confidence", "llm_rationale",
        "cash_free", "cash_invested", "cash_result",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    cash_info = snapshot.get("cash") or {}

    # Build a lookup: order_id -> first matching analysis
    analysis_by_order: dict = {}
    for a in analyses:
        oid = a.get("triggered_order_id")
        if oid is not None and oid not in analysis_by_order:
            analysis_by_order[oid] = a

    for o in orders:
        a = analysis_by_order.get(o.get("id"), {})
        dec = a.get("decision") or {}
        writer.writerow({
            "trade_date": o.get("ts", "")[:10],
            "order_ts": o.get("ts", ""),
            "order_id": o.get("id", ""),
            "t212_order_id": o.get("t212_order_id", ""),
            "ticker": o.get("ticker", ""),
            "side": o.get("side", ""),
            "qty": o.get("qty", ""),
            "order_type": o.get("order_type", ""),
            "limit_price": o.get("limit_price", ""),
            "status": o.get("status", ""),
            "analysis_ts": a.get("ts", ""),
            "strategy": a.get("model", ""),
            "llm_action": dec.get("action", ""),
            "llm_ticker": dec.get("ticker", ""),
            "llm_qty": dec.get("quantity", ""),
            "llm_confidence": dec.get("confidence", ""),
            "llm_rationale": dec.get("rationale", ""),
            "cash_free": cash_info.get("free", ""),
            "cash_invested": cash_info.get("invested", ""),
            "cash_result": cash_info.get("result", ""),
        })

    return buf.getvalue()


def _collect_day_data(trade_date: str, db: Session) -> tuple:
    """Return (snapshot_dict, orders_list, analyses_list, strategy) for a given date."""
    day_start = datetime.fromisoformat(f"{trade_date}T00:00:00+00:00")
    day_end   = datetime.fromisoformat(f"{trade_date}T23:59:59+00:00")

    snap = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.ts >= day_start, PortfolioSnapshot.ts <= day_end)
        .order_by(PortfolioSnapshot.ts.desc())
        .first()
    )
    snap_dict = {"cash": snap.cash, "positions": snap.positions} if snap else {}

    order_rows = (
        db.query(Order)
        .filter(Order.ts >= day_start, Order.ts <= day_end)
        .order_by(Order.ts.asc())
        .all()
    )
    orders_list = [
        {
            "id": o.id, "ts": o.ts.isoformat(), "t212_order_id": o.t212_order_id,
            "ticker": o.ticker, "side": o.side, "qty": float(o.qty),
            "order_type": o.order_type,
            "limit_price": float(o.limit_price) if o.limit_price else None,
            "status": o.status,
        }
        for o in order_rows
    ]

    analysis_rows = (
        db.query(LLMAnalysis)
        .filter(LLMAnalysis.ts >= day_start, LLMAnalysis.ts <= day_end)
        .order_by(LLMAnalysis.ts.asc())
        .all()
    )
    analyses_list = [
        {
            "id": a.id, "ts": a.ts.isoformat(), "model": a.model,
            "decision": a.decision, "triggered_order_id": a.triggered_order_id,
        }
        for a in analysis_rows
    ]

    if analyses_list:
        from collections import Counter
        strategy = Counter(a["model"] for a in analyses_list).most_common(1)[0][0]
    else:
        strategy = ""

    return snap_dict, orders_list, analyses_list, strategy


@router.post("/daily-log")
def save_daily_log(payload: DailyLogIn, db: Session = Depends(get_db)):
    """Collect all data for a trading day, write a CSV log file, and persist
    a DailyTradingLog row (insert or update)."""
    trade_date = payload.trade_date or date.today().isoformat()

    snap_dict, orders_list, analyses_list, strategy = _collect_day_data(trade_date, db)

    os.makedirs(_LOG_DIR, exist_ok=True)
    log_filename = f"trading_log_{trade_date}.csv"
    log_path = os.path.join(_LOG_DIR, log_filename)
    csv_content = _build_csv(orders_list, analyses_list, snap_dict)
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        f.write(csv_content)

    existing = db.query(DailyTradingLog).filter_by(trade_date=trade_date).first()
    now = datetime.now(timezone.utc)
    if existing:
        existing.strategy   = strategy
        existing.snapshot   = snap_dict
        existing.orders     = orders_list
        existing.analyses   = analyses_list
        existing.profit     = payload.profit if payload.profit is not None else existing.profit
        existing.notes      = payload.notes  if payload.notes  is not None else existing.notes
        existing.log_file   = log_filename
        existing.updated_at = now
        db.commit()
        db.refresh(existing)
        row = existing
    else:
        row = DailyTradingLog(
            trade_date=trade_date, strategy=strategy,
            snapshot=snap_dict, orders=orders_list, analyses=analyses_list,
            profit=payload.profit, notes=payload.notes,
            log_file=log_filename, created_at=now, updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

    return {
        "trade_date": trade_date,
        "strategy": strategy,
        "orders_count": len(orders_list),
        "analyses_count": len(analyses_list),
        "profit": float(row.profit) if row.profit is not None else None,
        "log_file": log_filename,
    }


@router.get("/daily-logs")
def list_daily_logs(db: Session = Depends(get_db)):
    """Return all daily logs ordered newest-first (summary for Historical Trends view)."""
    rows = db.query(DailyTradingLog).order_by(DailyTradingLog.trade_date.desc()).all()
    return [
        {
            "id": r.id,
            "trade_date": r.trade_date,
            "strategy": r.strategy,
            "orders_count": len(r.orders or []),
            "analyses_count": len(r.analyses or []),
            "profit": float(r.profit) if r.profit is not None else None,
            "notes": r.notes,
            "log_file": r.log_file,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@router.get("/daily-logs/{trade_date}")
def get_daily_log(trade_date: str, db: Session = Depends(get_db)):
    """Return full detail for a single trading day (all snapshot/order/analysis columns)."""
    row = db.query(DailyTradingLog).filter_by(trade_date=trade_date).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"No log for {trade_date}")
    return {
        "id": row.id,
        "trade_date": row.trade_date,
        "strategy": row.strategy,
        "snapshot": row.snapshot,
        "orders": row.orders,
        "analyses": row.analyses,
        "profit": float(row.profit) if row.profit is not None else None,
        "notes": row.notes,
        "log_file": row.log_file,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/daily-logs/{trade_date}/csv", response_class=PlainTextResponse)
def get_daily_log_csv(trade_date: str, db: Session = Depends(get_db)):
    """Download the raw CSV log file for a trading day."""
    log_path = os.path.join(_LOG_DIR, f"trading_log_{trade_date}.csv")
    if os.path.exists(log_path):
        with open(log_path, encoding="utf-8") as f:
            return PlainTextResponse(content=f.read(), media_type="text/csv")
    row = db.query(DailyTradingLog).filter_by(trade_date=trade_date).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"No log for {trade_date}")
    csv_content = _build_csv(row.orders or [], row.analyses or [], row.snapshot or {})
    return PlainTextResponse(content=csv_content, media_type="text/csv")
