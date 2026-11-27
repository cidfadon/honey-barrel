import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import api


def test_resolve_financial_strategy_file_allows_docs_strategies(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    strategies_dir = docs_dir / "strategies"
    strategies_dir.mkdir(parents=True)
    target = strategies_dir / "test.md"
    target.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(api, "_DOCS_DIR", docs_dir.resolve())
    resolved = api._resolve_financial_strategy_file(str(target))

    assert resolved == target.resolve()


def test_compose_prompt_with_optional_strategy_includes_content(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    strategies_dir = docs_dir / "strategies"
    strategies_dir.mkdir(parents=True)
    target = strategies_dir / "test.md"
    target.write_text("Strategy body", encoding="utf-8")

    monkeypatch.setattr(api, "_DOCS_DIR", docs_dir.resolve())
    prompt = api._compose_prompt_with_optional_strategy("Base prompt", True, str(target))

    assert "Base prompt" in prompt
    assert "=== FINANCIAL STRATEGY ===" in prompt
    assert "Strategy body" in prompt


def test_compose_prompt_with_optional_strategy_supports_multiple_files(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    strategies_dir = docs_dir / "strategies"
    strategies_dir.mkdir(parents=True)
    first = strategies_dir / "first.md"
    second = strategies_dir / "second.md"
    first.write_text("First strategy", encoding="utf-8")
    second.write_text("Second strategy", encoding="utf-8")

    monkeypatch.setattr(api, "_DOCS_DIR", docs_dir.resolve())
    prompt = api._compose_prompt_with_optional_strategy("Base prompt", True, ["first.md", "second.md"])

    assert "Base prompt" in prompt
    assert "First strategy" in prompt
    assert "Second strategy" in prompt
