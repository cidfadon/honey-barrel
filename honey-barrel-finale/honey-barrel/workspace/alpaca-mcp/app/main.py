"""alpaca-mcp — HTTP MCP server (JSON-RPC 2.0 over POST /mcp).

Wire-compatible with mcp-toolbox and workspace-mcp:
    GET  /health  -> liveness (used by docker compose healthcheck)
    GET  /mcp     -> SSE keep-alive
    POST /mcp     -> JSON-RPC 2.0 (initialize, tools/list, tools/call, ping,
                     notifications/initialized, notifications/cancelled)

Hermes registers it via:
    hermes mcp add alpaca --url http://alpaca-mcp:3001/mcp
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Literal, Optional, Union

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sse_starlette.sse import EventSourceResponse

from .alpaca_client import AlpacaClient, GuardrailConfig, GuardrailState
from .tools import handle_tool_call, list_tools

LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("alpaca-mcp")


# ---------------------------------------------------------------------------
# JSON-RPC models (Pydantic v2)
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


class GuardrailsUpdateRequest(BaseModel):
    max_notional_usd: float = Field(gt=0)


def _rpc_error(rpc_id: Any, code: int, message: str, data: dict | None = None) -> dict:
    return JSONRPCResponse(
        id=rpc_id, error=JSONRPCError(code=code, message=message, data=data)
    ).model_dump(exclude_none=True)


def _rpc_result(rpc_id: Any, result: Any) -> dict:
    return JSONRPCResponse(id=rpc_id, result=result).model_dump(exclude_none=True)


# ---------------------------------------------------------------------------
# Lifespan: build the Alpaca client + guardrails once at startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.alpaca = AlpacaClient.from_env()
    app.state.guardrail_config = GuardrailConfig.from_env()
    app.state.guardrail_state = GuardrailState()
    log.info(
        "alpaca-mcp ready (mode=%s, max_orders/day=%d, max_notional_usd=%.2f)",
        app.state.alpaca.mode,
        app.state.guardrail_config.max_orders_per_day,
        app.state.guardrail_config.max_notional_usd,
    )
    yield


app = FastAPI(title="alpaca-mcp", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, Any]:
    cfg: GuardrailConfig = app.state.guardrail_config
    state: GuardrailState = app.state.guardrail_state
    return {
        "ok": True,
        "service": "alpaca-mcp",
        "mode": app.state.alpaca.mode,
        "tools": len(list_tools()),
        "guardrails": {
            "max_orders_per_day": cfg.max_orders_per_day,
            "max_notional_usd": cfg.max_notional_usd,
            "auto_execute": cfg.auto_execute,
            "orders_today": state.orders_today,
            "buy_notional_today": state.buy_notional_today,
            "remaining_buy_notional_usd": max(0.0, cfg.max_notional_usd - state.buy_notional_today),
        },
    }


@app.post("/guardrails")
async def update_guardrails(payload: GuardrailsUpdateRequest) -> dict[str, Any]:
    cfg: GuardrailConfig = app.state.guardrail_config
    cfg.max_notional_usd = float(payload.max_notional_usd)
    return {
        "ok": True,
        "service": "alpaca-mcp",
        "mode": app.state.alpaca.mode,
        "guardrails": {
            "max_orders_per_day": cfg.max_orders_per_day,
            "max_notional_usd": cfg.max_notional_usd,
            "auto_execute": cfg.auto_execute,
            "orders_today": app.state.guardrail_state.orders_today,
            "buy_notional_today": app.state.guardrail_state.buy_notional_today,
            "remaining_buy_notional_usd": max(0.0, cfg.max_notional_usd - app.state.guardrail_state.buy_notional_today),
            "runtime_only": True,
        },
    }


# ---------------------------------------------------------------------------
# GET /mcp — SSE keep-alive (kept for parity with mcp-toolbox / workspace-mcp)
# ---------------------------------------------------------------------------

async def _sse_stream():
    yield {"event": "connected", "data": '{"type":"connected"}'}
    while True:
        await asyncio.sleep(15)
        yield {"event": "keep-alive", "data": "ping"}


@app.get("/mcp")
async def mcp_sse() -> EventSourceResponse:
    return EventSourceResponse(_sse_stream())


# ---------------------------------------------------------------------------
# POST /mcp — JSON-RPC 2.0
# ---------------------------------------------------------------------------

@app.post("/mcp")
async def mcp_post(
    request: Request,
    x_confirm: Optional[str] = Header(default=None, alias="X-Confirm"),
):
    raw = await request.json()
    rpc_id = raw.get("id") if isinstance(raw, dict) else None

    try:
        msg = JSONRPCRequest(**raw)
    except Exception as e:
        return JSONResponse(
            _rpc_error(rpc_id, -32600, "Invalid Request", {"detail": str(e)})
        )

    log.debug("MCP REQUEST method=%s id=%s", msg.method, msg.id)
    method = msg.method
    params = msg.params or {}

    try:
        if method == "initialize":
            return JSONResponse(
                _rpc_result(
                    msg.id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "alpaca-mcp", "version": "1.0.0"},
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
            result = await handle_tool_call(
                app.state.alpaca,
                app.state.guardrail_config,
                app.state.guardrail_state,
                params,
                x_confirm_header=x_confirm,
            )
            return JSONResponse(_rpc_result(msg.id, result))

        return JSONResponse(
            _rpc_error(msg.id, -32601, f"Method not found: {method}")
        )

    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, dict) else {"detail": e.detail}
        return JSONResponse(
            _rpc_error(msg.id, e.status_code, str(detail.get("error", "error")), detail)
        )
    except Exception as e:  # noqa: BLE001
        log.exception("Unhandled MCP error")
        return JSONResponse(
            _rpc_error(msg.id, -32603, "Internal error", {"detail": str(e)})
        )
