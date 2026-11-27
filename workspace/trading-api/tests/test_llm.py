"""LLM endpoint tests using a stub instead of a real Ollama call."""
import json
from fastapi.testclient import TestClient

from app import ollama_client
from app.main import app

client = TestClient(app)


def _stub_completion(*_args, **_kwargs):
    return json.dumps({
        "action": "BUY", "ticker": "AAPL_US_EQ", "quantity": 1.0,
        "rationale": "Stubbed test response", "confidence": 0.9,
    })


def test_analyze_with_stubbed_llm(monkeypatch):
    monkeypatch.setattr(ollama_client, "call_ollama", _stub_completion)
    # The route imports the function at call-time via "from .ollama_client import call_ollama",
    # which actually creates a local reference — patch that too.
    from app.routes import llm as llm_route
    monkeypatch.setattr(llm_route, "call_ollama", _stub_completion)

    r = client.post("/api/analyze")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"]["action"] == "BUY"
    assert body["decision"]["ticker"] == "AAPL_US_EQ"
    assert 0 <= body["decision"]["confidence"] <= 1


def test_auto_trade_skips_when_auto_execute_false(monkeypatch):
    from app.routes import llm as llm_route
    monkeypatch.setattr(llm_route, "call_ollama", _stub_completion)

    r = client.post("/api/auto-trade")
    assert r.status_code == 200
    body = r.json()
    assert body["executed"] is False
    assert "AUTO_EXECUTE=false" in body["reason_if_skipped"]
