"""Trading212 client with three back-ends: live, demo, mock."""
from __future__ import annotations

import base64
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import settings, t212_base_url


class T212Error(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Real client (used in demo + live)
# ---------------------------------------------------------------------------
class T212HttpClient:
    def __init__(self) -> None:
        creds = f"{settings.t212_api_key}:{settings.t212_api_secret}".encode()
        self._headers = {
            "Authorization": "Basic " + base64.b64encode(creds).decode(),
            "Content-Type": "application/json",
            "User-Agent": "openclaw-t212/1.0",
        }
        self._base = t212_base_url()
        self._client = httpx.Client(timeout=15.0, headers=self._headers)

    @retry(
        reraise=True,
        retry=retry_if_exception_type(httpx.HTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
    )
    def _request(self, method: str, path: str, json: Any = None) -> tuple[int, Any, int]:
        t0 = time.perf_counter()
        r = self._client.request(method, f"{self._base}{path}", json=json)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text}
        if r.status_code >= 400:
            raise T212Error(f"{method} {path} -> {r.status_code}: {body}")
        return r.status_code, body, latency_ms

    # --- read ----------------------------------------------------------------
    def cash(self):       return self._request("GET", "/equity/account/cash")
    def positions(self):  return self._request("GET", "/equity/positions")
    def open_orders(self):return self._request("GET", "/equity/orders")
    def history(self, limit: int = 50):
        return self._request("GET", f"/equity/history/orders?limit={limit}")

    # --- write ---------------------------------------------------------------
    def place_market(self, ticker: str, signed_qty: float, extended_hours: bool):
        return self._request("POST", "/equity/orders/market", json={
            "ticker": ticker, "quantity": signed_qty, "extendedHours": extended_hours,
        })

    def place_limit(self, ticker: str, signed_qty: float, limit_price: float, time_validity: str):
        return self._request("POST", "/equity/orders/limit", json={
            "ticker": ticker, "quantity": signed_qty,
            "limitPrice": limit_price, "timeValidity": time_validity,
        })

    def cancel(self, order_id: str):
        return self._request("DELETE", f"/equity/orders/{order_id}")


# ---------------------------------------------------------------------------
# Mock client (used in T212_MODE=mock for safe local dev)
# ---------------------------------------------------------------------------
class T212MockClient:
    """Returns deterministic canned data — never calls Trading212."""

    def __init__(self) -> None:
        self._next_order_id = 1000

    def cash(self):
        return 200, {"free": 4321.55, "total": 5180.12, "ppl": 12.4, "result": 858.57,
                     "invested": 5000.0, "blocked": 0, "currencyCode": "EUR"}, 5

    def positions(self):
        return 200, [
            {"ticker": "AAPL_US_EQ", "quantity": 4.5,  "averagePrice": 170.10, "currentPrice": 188.20, "ppl": 81.45},
            {"ticker": "MSFT_US_EQ", "quantity": 2.0,  "averagePrice": 320.00, "currentPrice": 415.10, "ppl": 190.20},
            {"ticker": "VUSA_EQ",    "quantity": 12.0, "averagePrice":  78.30, "currentPrice":  85.40, "ppl":  85.20},
        ], 4

    def open_orders(self):
        return 200, [], 3

    def history(self, limit: int = 50):
        return 200, {"items": [
            {"id": "h1", "ticker": "AAPL_US_EQ", "filledQuantity": 1, "type": "MARKET",
             "status": "FILLED", "filledValue": 178.10},
        ], "nextPageCursor": None}, 4

    def _new_id(self) -> str:
        self._next_order_id += 1
        return f"mock-{self._next_order_id}"

    def place_market(self, ticker, signed_qty, extended_hours):
        return 200, {"id": self._new_id(), "ticker": ticker, "quantity": signed_qty,
                     "type": "MARKET", "status": "ACCEPTED"}, 6

    def place_limit(self, ticker, signed_qty, limit_price, time_validity):
        return 200, {"id": self._new_id(), "ticker": ticker, "quantity": signed_qty,
                     "limitPrice": limit_price, "timeValidity": time_validity,
                     "type": "LIMIT", "status": "ACCEPTED"}, 6

    def cancel(self, order_id):
        return 200, {"id": order_id, "status": "CANCELLED"}, 3


def get_client():
    if settings.t212_mode == "mock":
        return T212MockClient()
    return T212HttpClient()
