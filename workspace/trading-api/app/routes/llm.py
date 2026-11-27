import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..guardrails import check_daily_cap, check_notional, require_confirm_header_if_live
from ..models import LLMAnalysis, Order, PortfolioSnapshot, T212Call
from ..ollama_client import call_ollama, extract_json
from ..schemas import LLMDecision
from ..t212 import get_client

router = APIRouter(prefix="/api", tags=["llm"])


def _snapshot(db: Session) -> PortfolioSnapshot:
    cli = get_client()
    _, cash, _ = cli.cash()
    _, pos, _ = cli.positions()
    snap = PortfolioSnapshot(cash=cash, positions=pos)
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def _run_llm(snap: PortfolioSnapshot, db: Session) -> tuple[LLMAnalysis, LLMDecision]:
    prompt = (
        "Current Trading212 portfolio:\n"
        f"Cash: {json.dumps(snap.cash)}\n"
        f"Positions: {json.dumps(snap.positions)}\n\n"
        "Propose exactly ONE action (BUY/SELL/HOLD) as a JSON object."
    )
    completion = call_ollama(prompt)
    try:
        decision = LLMDecision.model_validate(extract_json(completion))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM output invalid: {exc}") from exc

    row = LLMAnalysis(
        snapshot_id=snap.id, model=settings.ollama_model,
        prompt=prompt, completion=completion, decision=decision.model_dump(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, decision


@router.post("/analyze")
def analyze(db: Session = Depends(get_db)):
    snap = _snapshot(db)
    row, decision = _run_llm(snap, db)
    return {
        "snapshot_id": snap.id, "analysis_id": row.id,
        "completion": row.completion, "decision": decision.model_dump(),
    }


@router.post("/auto-trade")
def auto_trade(request: Request, db: Session = Depends(get_db)):
    require_confirm_header_if_live(request)
    snap = _snapshot(db)
    row, decision = _run_llm(snap, db)

    if decision.action == "HOLD":
        return {"snapshot_id": snap.id, "analysis_id": row.id, "executed": False,
                "decision": decision.model_dump(), "reason_if_skipped": "LLM said HOLD",
                "completion": row.completion}

    if not settings.auto_execute:
        return {"snapshot_id": snap.id, "analysis_id": row.id, "executed": False,
                "decision": decision.model_dump(),
                "reason_if_skipped": "AUTO_EXECUTE=false", "completion": row.completion}

    if not decision.ticker or not decision.quantity:
        raise HTTPException(status_code=400, detail="LLM decision missing ticker/quantity")

    check_daily_cap(db)
    check_notional(decision.quantity, price_hint=None)

    cli = get_client()
    qty = decision.quantity if decision.action == "BUY" else -decision.quantity
    status, body, lat = cli.place_market(decision.ticker, qty, extended_hours=False)
    db.add(T212Call(endpoint="/equity/orders/market", method="POST",
                    payload=decision.model_dump(), response=body,
                    http_status=status, latency_ms=lat))
    order = Order(
        t212_order_id=str(body.get("id")), ticker=decision.ticker,
        side=decision.action, qty=decision.quantity, order_type="MARKET",
        status=body.get("status", "UNKNOWN"), raw=body,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    row.triggered_order_id = order.id
    db.commit()
    return {"snapshot_id": snap.id, "analysis_id": row.id, "executed": True,
            "order_id": order.id, "decision": decision.model_dump(),
            "completion": row.completion}


# --- Ollama proxy (used by OpenClaw for free-form chat) --------------------
@router.post("/llm/generate")
def llm_generate(body: dict):
    """Pass-through proxy to Ollama /api/generate so OpenClaw doesn't need
    direct access to the backend network."""
    url = f"{settings.resolved_ollama_url()}/api/generate"
    with httpx.Client(timeout=120) as c:
        r = c.post(url, json={**body, "model": body.get("model", settings.ollama_model)})
        return r.json()
