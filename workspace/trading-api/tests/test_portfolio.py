from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz():
    r = client.get("/api/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_portfolio_returns_mock_data():
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    body = r.json()
    assert "snapshot_id" in body
    assert body["cash"]["currencyCode"] == "EUR"
    tickers = [p["ticker"] for p in body["positions"]]
    assert "AAPL_US_EQ" in tickers


def test_open_orders_empty_in_mock():
    r = client.get("/api/orders")
    assert r.status_code == 200
    assert r.json() == []


def test_history_mock_has_one_item():
    r = client.get("/api/history?limit=10")
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1
