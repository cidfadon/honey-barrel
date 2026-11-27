"""Tests for t212.py — T212MockClient and get_client factory."""

import pytest

from app.config import settings
from app.t212 import T212MockClient, get_client, T212HttpClient


class TestT212MockClient:
    def setup_method(self):
        self.client = T212MockClient()

    def test_cash_returns_200(self):
        status, body, lat = self.client.cash()
        assert status == 200
        assert "free" in body
        assert "currencyCode" in body
        assert body["currencyCode"] == "EUR"

    def test_positions_returns_list(self):
        status, positions, lat = self.client.positions()
        assert status == 200
        assert isinstance(positions, list)
        assert len(positions) >= 1
        tickers = [p["ticker"] for p in positions]
        assert "AAPL_US_EQ" in tickers

    def test_open_orders_empty(self):
        status, body, lat = self.client.open_orders()
        assert status == 200
        assert body == []

    def test_history_returns_items(self):
        status, body, lat = self.client.history(limit=10)
        assert status == 200
        assert "items" in body
        assert len(body["items"]) >= 1

    def test_place_market_returns_accepted(self):
        status, body, lat = self.client.place_market("AAPL_US_EQ", 1.0, False)
        assert status == 200
        assert body["status"] == "ACCEPTED"
        assert body["id"].startswith("mock-")

    def test_place_limit_returns_accepted(self):
        status, body, lat = self.client.place_limit("MSFT_US_EQ", 2.0, 400.0, "DAY")
        assert status == 200
        assert body["status"] == "ACCEPTED"
        assert body["limitPrice"] == 400.0

    def test_cancel_returns_cancelled(self):
        status, body, lat = self.client.cancel("mock-1234")
        assert status == 200
        assert body["status"] == "CANCELLED"
        assert body["id"] == "mock-1234"

    def test_new_id_increments(self):
        id1 = self.client._new_id()
        id2 = self.client._new_id()
        assert id1 != id2
        n1 = int(id1.split("-")[1])
        n2 = int(id2.split("-")[1])
        assert n2 == n1 + 1


class TestGetClient:
    def test_mock_mode_returns_mock_client(self, monkeypatch):
        monkeypatch.setattr(settings, "t212_mode", "mock")
        client = get_client()
        assert isinstance(client, T212MockClient)

    def test_demo_mode_returns_http_client(self, monkeypatch):
        monkeypatch.setattr(settings, "t212_mode", "demo")
        monkeypatch.setattr(settings, "t212_api_key", "test-key")
        monkeypatch.setattr(settings, "t212_api_secret", "test-secret")
        client = get_client()
        assert isinstance(client, T212HttpClient)
