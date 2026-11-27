"""Thin wrapper around the Ollama HTTP API."""
from __future__ import annotations

import json

import httpx

from .config import settings

ACTIVE_SYSTEM_PROMPT = (
    "You are an aggressive but disciplined portfolio assistant connected to a "
    "Trading212 brokerage. You ALWAYS propose exactly one actionable suggestion "
    "(BUY, SELL or HOLD) for each call. You MUST answer with a single valid JSON "
    "object and NOTHING ELSE, matching this schema:\n"
    '{"action":"BUY|SELL|HOLD","ticker":"AAPL_US_EQ",'
    '"quantity":1.0,"rationale":"...","confidence":0.0-1.0}\n'
    "Rules:\n"
    "- Use the Trading212 ticker format (e.g. AAPL_US_EQ, VUSA_EQ).\n"
    "- HOLD means action=HOLD and ticker/quantity may be null.\n"
    "- Confidence reflects your own certainty, calibrated honestly.\n"
    "- Never output markdown, comments or text outside the JSON object."
)


def call_ollama(prompt: str, system: str = ACTIVE_SYSTEM_PROMPT) -> str:
    """Call /api/generate and return the raw completion text."""
    url = f"{settings.resolved_ollama_url()}/api/generate"
    with httpx.Client(timeout=120) as c:
        r = c.post(url, json={
            "model": settings.ollama_model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": 0.6, "num_ctx": 8192},
        })
        r.raise_for_status()
        return r.json().get("response", "")


def extract_json(text: str) -> dict:
    """Best-effort extraction of the first {...} block from an LLM completion."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in LLM output: {text!r}")
    return json.loads(text[start : end + 1])
