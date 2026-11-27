"""Tests for ollama_client.extract_json — 0% direct coverage."""

import pytest

from app.ollama_client import extract_json


class TestExtractJson:
    def test_clean_json(self):
        result = extract_json('{"action":"BUY","ticker":"AAPL_US_EQ","confidence":0.9}')
        assert result["action"] == "BUY"
        assert result["ticker"] == "AAPL_US_EQ"

    def test_json_with_surrounding_text(self):
        text = 'Here is my analysis:\n{"action":"SELL","rationale":"overvalued","confidence":0.7}\nEnd.'
        result = extract_json(text)
        assert result["action"] == "SELL"
        assert result["confidence"] == 0.7

    def test_json_with_markdown_fences(self):
        text = '```json\n{"action":"HOLD","rationale":"sideways","confidence":0.5}\n```'
        result = extract_json(text)
        assert result["action"] == "HOLD"

    def test_no_json_raises_value_error(self):
        with pytest.raises(ValueError, match="No JSON"):
            extract_json("This is just plain text with no JSON")

    def test_only_open_brace_raises(self):
        with pytest.raises((ValueError, Exception)):
            extract_json("{broken json without closing")

    def test_nested_json_extracts_outer(self):
        text = '{"outer": {"inner": 1}, "val": 2}'
        result = extract_json(text)
        assert result["outer"] == {"inner": 1}
        assert result["val"] == 2

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="No JSON"):
            extract_json("")
