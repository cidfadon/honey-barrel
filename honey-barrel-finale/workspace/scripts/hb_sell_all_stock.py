#!/usr/bin/env python3
"""Close all currently open stock positions via MCP gateway."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

MCP_URL = "http://127.0.0.1:3003/mcp"


def mcp_call(name: str, arguments: dict[str, Any] | None = None, *, confirm: bool = False, req_id: int = 1) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }
    headers = {"Content-Type": "application/json"}
    if confirm:
        headers["X-Confirm"] = "true"

    req = urllib.request.Request(
        MCP_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_text_content(result: dict[str, Any]) -> Any:
    text = (
        result.get("result", {})
        .get("content", [{}])[0]
        .get("text", "null")
    )
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def main() -> int:
    try:
        positions_resp = mcp_call("positions_list", req_id=1)
        if positions_resp.get("error"):
            print(f"ERROR positions_list: {positions_resp['error']}")
            return 1

        positions = parse_text_content(positions_resp)
        if not isinstance(positions, list):
            print(f"ERROR: unexpected positions payload: {positions}")
            return 1

        orders_resp = mcp_call("orders_list", {"status": "open", "limit": 200}, req_id=2)
        open_sell_symbols: set[str] = set()
        if not orders_resp.get("error"):
            orders = parse_text_content(orders_resp)
            if isinstance(orders, list):
                for order in orders:
                    symbol = str(order.get("symbol", "")).upper().strip()
                    side = str(order.get("side", "")).lower().strip()
                    if symbol and side == "sell":
                        open_sell_symbols.add(symbol)

        if not positions:
            print("No open positions to close.")
            return 0

        print(f"Open positions: {len(positions)}")
        closed = 0
        skipped = 0
        failed = 0

        for idx, pos in enumerate(positions, start=1):
            symbol = str(pos.get("symbol", "")).upper().strip()
            qty = pos.get("qty")
            side = pos.get("side")
            if not symbol:
                print(f"[{idx}] SKIP malformed position: {pos}")
                skipped += 1
                continue

            if symbol in open_sell_symbols:
                print(f"[{idx}] SKIP {symbol}: open sell order already exists")
                skipped += 1
                continue

            print(f"[{idx}] Closing {symbol} qty={qty} side={side} ...")
            close_resp = mcp_call(
                "position_close",
                {"symbol": symbol},
                confirm=True,
                req_id=1000 + idx,
            )

            if close_resp.get("error"):
                print(f"[{idx}] ERROR {symbol}: {close_resp['error']}")
                failed += 1
                continue

            parsed = parse_text_content(close_resp)
            if isinstance(parsed, dict):
                close_order = parsed.get("close_order", {})
                print(
                    f"[{idx}] OK {symbol}: order_id={close_order.get('id')} "
                    f"status={close_order.get('status')} side={close_order.get('side')} "
                    f"qty={close_order.get('qty')}"
                )
            else:
                print(f"[{idx}] OK {symbol}: {parsed}")
            closed += 1

        print(f"Summary: closed={closed} skipped={skipped} failed={failed}")
        return 1 if failed else 0

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTPError {exc.code}: {body}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
