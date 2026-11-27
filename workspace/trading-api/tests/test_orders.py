from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_market_buy_persists_and_returns_t212_id():
    r = client.post("/api/orders/market", json={
        "ticker": "AAPL_US_EQ", "quantity": 1.0, "side": "BUY",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["order_id"] > 0
    assert body["t212"]["status"] == "ACCEPTED"
    assert body["t212"]["id"].startswith("mock-")


def test_market_rejects_invalid_payload():
    r = client.post("/api/orders/market", json={
        "ticker": "AAPL_US_EQ", "quantity": -1.0, "side": "BUY",
    })
    assert r.status_code == 422   # pydantic: quantity must be > 0


def test_cancel_order_mock():
    r = client.delete("/api/orders/mock-9999")
    assert r.status_code == 200
    assert r.json()["status"] == "CANCELLED"
