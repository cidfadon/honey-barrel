"""MCP HTTP server mounted on the existing FastAPI app.

Speaks the same JSON-RPC 2.0 / SSE wire shape as mcp-toolbox, workspace-mcp
and alpaca-mcp, so Hermes registers it identically:

    hermes mcp add analyst --url http://investment-analyst-api:8001/mcp

Tools just call the in-process `DataFetcher`, `StockPredictor` and
`WatchListManager` — no self-loopback HTTP — so latency stays low and the
existing REST endpoints keep working unchanged.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal, Optional, Union

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sse_starlette.sse import EventSourceResponse

log = logging.getLogger("analyst-mcp")


# ---------------------------------------------------------------------------
# JSON-RPC plumbing
# ---------------------------------------------------------------------------

class JSONRPCRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    jsonrpc: Literal["2.0"]
    id: Optional[Union[int, str]] = None
    method: str
    params: Optional[dict[str, Any]] = None


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Optional[dict[str, Any]] = None


class JSONRPCResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: Optional[Union[int, str]] = None
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None


def _rpc_error(rpc_id: Any, code: int, message: str, data: dict | None = None) -> dict:
    return JSONRPCResponse(
        id=rpc_id, error=JSONRPCError(code=code, message=message, data=data)
    ).model_dump(exclude_none=True)


def _rpc_result(rpc_id: Any, result: Any) -> dict:
    return JSONRPCResponse(id=rpc_id, result=result).model_dump(exclude_none=True)


def _text_envelope(payload: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, default=str, ensure_ascii=False),
            }
        ]
    }


# ---------------------------------------------------------------------------
# Tool catalogue
# ---------------------------------------------------------------------------

def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "data_fetch",
            "description": (
                "Fetch historical OHLCV + fundamentals for a US equity. "
                "Uses Yahoo Finance with a 24h on-disk cache."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
        },
        {
            "name": "model_train",
            "description": "Train the BUY/SELL/HOLD model for a ticker on the last 90 days.",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
        },
        {
            "name": "model_predict",
            "description": (
                "Get a BUY/SELL/HOLD prediction with class probabilities. "
                "If no model is cached for the ticker, trains one automatically."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "force_retrain": {"type": "boolean", "default": False},
                },
                "required": ["ticker"],
            },
        },
        {
            "name": "analyze_stock",
            "description": (
                "Full pipeline for a single ticker: fetch -> train -> predict, "
                "with fundamentals attached. Use this when you want a complete "
                "trading recommendation, not just a raw prediction."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "force_retrain": {"type": "boolean", "default": False},
                },
                "required": ["ticker"],
            },
        },
        {
            "name": "analyze_watchlist",
            "description": (
                "Run prediction across every ticker in the watch list and "
                "return aggregated buy/sell/hold counts."
            ),
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "watchlist_get",
            "description": "List all tickers currently in the watch list.",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "watchlist_add",
            "description": "Add a ticker to the watch list (SQLite, persisted).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "name": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["ticker"],
            },
        },
        {
            "name": "watchlist_remove",
            "description": "Remove a ticker from the watch list.",
            "inputSchema": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"],
            },
        },
        {
            "name": "watchlist_clear",
            "description": "Drop every ticker from the watch list.",
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        },
    ]


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

def _require_str(args: dict[str, Any], key: str) -> str:
    val = args.get(key)
    if not isinstance(val, str) or not val.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_argument", "key": key, "expected": "string"},
        )
    return val.strip()


async def _dispatch(
    data_fetcher,
    predictor,
    watchlist_mgr,
    params: dict[str, Any],
) -> dict[str, Any]:
    name = params.get("name")
    args: dict[str, Any] = params.get("arguments") or {}

    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "missing_tool_name"},
        )

    # --- data ----------------------------------------------------------------
    if name == "data_fetch":
        ticker = _require_str(args, "ticker")
        df = data_fetcher.fetch_historical_data(ticker, use_cache=True)
        if df is None or df.empty:
            return _text_envelope({"success": False, "error": f"no data for {ticker}"})
        fundamentals = data_fetcher.fetch_fundamentals(ticker)
        return _text_envelope(
            {
                "success": True,
                "ticker": ticker,
                "data_points": len(df),
                "latest_close": float(df["Close"].iloc[-1]) if "Close" in df else None,
                "fundamentals": fundamentals,
            }
        )

    # --- model ---------------------------------------------------------------
    if name == "model_train":
        ticker = _require_str(args, "ticker")
        df = data_fetcher.fetch_historical_data(ticker, use_cache=True)
        if df is None or df.empty:
            return _text_envelope({"success": False, "error": f"no data for {ticker}"})
        fundamentals = data_fetcher.fetch_fundamentals(ticker)
        return _text_envelope(predictor.train(df, ticker, fundamentals))

    if name == "model_predict":
        ticker = _require_str(args, "ticker")
        force_retrain = bool(args.get("force_retrain", False))

        df = data_fetcher.fetch_historical_data(ticker, use_cache=True)
        if df is None or df.empty:
            return _text_envelope({"success": False, "error": f"no data for {ticker}"})

        fundamentals = data_fetcher.fetch_fundamentals(ticker)
        if force_retrain:
            train_res = predictor.train(df, ticker, fundamentals)
            if not train_res.get("success"):
                return _text_envelope({"success": False, "error": train_res.get("error")})
        return _text_envelope(predictor.predict(df, ticker, fundamentals))

    # --- analysis ------------------------------------------------------------
    if name == "analyze_stock":
        ticker = _require_str(args, "ticker")
        force_retrain = bool(args.get("force_retrain", False))

        df = data_fetcher.fetch_historical_data(ticker, use_cache=True)
        if df is None or df.empty:
            return _text_envelope({"success": False, "error": f"no data for {ticker}"})

        fundamentals = data_fetcher.fetch_fundamentals(ticker)
        train_res = predictor.train(df, ticker, fundamentals) if force_retrain else \
            predictor.train(df, ticker, fundamentals)
        pred_res = predictor.predict(df, ticker, fundamentals)
        return _text_envelope(
            {
                "success": pred_res.get("success", False),
                "ticker": ticker,
                "training": train_res if train_res.get("success") else None,
                "prediction": pred_res,
                "fundamentals": fundamentals,
            }
        )

    if name == "analyze_watchlist":
        tickers = watchlist_mgr.get_tickers()
        analyses: list[dict[str, Any]] = []
        for t in tickers:
            try:
                df = data_fetcher.fetch_historical_data(t, use_cache=True)
                if df is None or df.empty:
                    analyses.append({"ticker": t, "error": "no data"})
                    continue
                fundamentals = data_fetcher.fetch_fundamentals(t)
                pred = predictor.predict(df, t, fundamentals)
                if pred.get("success"):
                    analyses.append(
                        {
                            "ticker": t,
                            "action": pred.get("action"),
                            "confidence": pred.get("confidence"),
                            "price": pred.get("latest_price"),
                        }
                    )
                else:
                    analyses.append({"ticker": t, "error": pred.get("error")})
            except Exception as e:  # noqa: BLE001
                analyses.append({"ticker": t, "error": str(e)})

        return _text_envelope(
            {
                "success": True,
                "stocks": analyses,
                "count": len(analyses),
                "recommendations": {
                    "buy": sum(1 for s in analyses if s.get("action") == "BUY"),
                    "sell": sum(1 for s in analyses if s.get("action") == "SELL"),
                    "hold": sum(1 for s in analyses if s.get("action") == "HOLD"),
                },
            }
        )

    # --- watchlist -----------------------------------------------------------
    if name == "watchlist_get":
        return _text_envelope(watchlist_mgr.get_watchlist())

    if name == "watchlist_add":
        ticker = _require_str(args, "ticker")
        return _text_envelope(
            watchlist_mgr.add_stock(
                ticker,
                args.get("name"),
                args.get("notes") or "",
            )
        )

    if name == "watchlist_remove":
        ticker = _require_str(args, "ticker")
        return _text_envelope(watchlist_mgr.remove_stock(ticker))

    if name == "watchlist_clear":
        return _text_envelope(watchlist_mgr.clear_watchlist())

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": "unknown_tool", "name": name},
    )


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

async def _sse_stream():
    yield {"event": "connected", "data": '{"type":"connected"}'}
    while True:
        await asyncio.sleep(15)
        yield {"event": "keep-alive", "data": "ping"}


def build_mcp_router(data_fetcher, predictor, watchlist_mgr) -> APIRouter:
    """Return an APIRouter that exposes GET /mcp (SSE) and POST /mcp (JSON-RPC)."""
    router = APIRouter()

    @router.get("/mcp")
    async def mcp_sse() -> EventSourceResponse:
        return EventSourceResponse(_sse_stream())

    @router.post("/mcp")
    async def mcp_post(request: Request):
        raw = await request.json()
        rpc_id = raw.get("id") if isinstance(raw, dict) else None

        try:
            msg = JSONRPCRequest(**raw)
        except Exception as e:  # noqa: BLE001
            return JSONResponse(
                _rpc_error(rpc_id, -32600, "Invalid Request", {"detail": str(e)})
            )

        method, params = msg.method, msg.params or {}
        log.debug("MCP REQUEST method=%s id=%s", method, msg.id)

        try:
            if method == "initialize":
                return JSONResponse(
                    _rpc_result(
                        msg.id,
                        {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {
                                "name": "investment-analyst-mcp",
                                "version": "1.0.0",
                            },
                        },
                    )
                )

            if method in ("notifications/initialized", "notifications/cancelled"):
                return JSONResponse(content=None, status_code=204)

            if method == "ping":
                return JSONResponse(_rpc_result(msg.id, {}))

            if method == "tools/list":
                return JSONResponse(_rpc_result(msg.id, {"tools": list_tools()}))

            if method == "tools/call":
                result = await _dispatch(
                    data_fetcher, predictor, watchlist_mgr, params
                )
                return JSONResponse(_rpc_result(msg.id, result))

            return JSONResponse(
                _rpc_error(msg.id, -32601, f"Method not found: {method}")
            )

        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, dict) else {"detail": e.detail}
            return JSONResponse(
                _rpc_error(
                    msg.id, e.status_code, str(detail.get("error", "error")), detail
                )
            )
        except Exception as e:  # noqa: BLE001
            log.exception("Unhandled MCP error")
            return JSONResponse(
                _rpc_error(msg.id, -32603, "Internal error", {"detail": str(e)})
            )

    return router


def attach_mcp(
    app: FastAPI,
    *,
    data_fetcher,
    predictor,
    watchlist_mgr,
) -> None:
    """Mount the MCP routes onto an existing FastAPI app."""
    app.include_router(
        build_mcp_router(data_fetcher, predictor, watchlist_mgr)
    )
