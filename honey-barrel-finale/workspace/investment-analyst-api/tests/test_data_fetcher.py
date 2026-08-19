"""Regression tests for DataFetcher history normalization."""

import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

# Patch config side-effects (directory creation) before importing
_test_tmp = tempfile.mkdtemp()
os.environ["DATA_CACHE_DIR"] = os.path.join(_test_tmp, "cache")
os.environ["MODEL_DIR"] = os.path.join(_test_tmp, "models")

# Allow imports from the investment-analyst-api package root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_fetcher import DataFetcher


def _fetcher() -> DataFetcher:
    return DataFetcher()


def test_normalize_history_handles_price_ticker_multiindex_columns():
    fetcher = _fetcher()
    index = pd.date_range("2026-01-01", periods=2, freq="D")
    columns = pd.MultiIndex.from_tuples(
        [
            ("Open", "AAPL"),
            ("High", "AAPL"),
            ("Low", "AAPL"),
            ("Close", "AAPL"),
            ("Volume", "AAPL"),
        ]
    )
    df = pd.DataFrame(
        [[100.0, 101.0, 99.0, 100.5, 1_000_000], [101.0, 102.0, 100.0, 101.5, 1_100_000]],
        index=index,
        columns=columns,
    )

    normalized = fetcher._normalize_history(df)

    assert list(normalized.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert normalized.empty is False


def test_normalize_history_handles_ticker_price_multiindex_columns():
    fetcher = _fetcher()
    index = pd.date_range("2026-01-01", periods=2, freq="D")
    columns = pd.MultiIndex.from_tuples(
        [
            ("AAPL", "Open"),
            ("AAPL", "High"),
            ("AAPL", "Low"),
            ("AAPL", "Close"),
            ("AAPL", "Volume"),
        ]
    )
    df = pd.DataFrame(
        [[100.0, 101.0, 99.0, 100.5, 1_000_000], [101.0, 102.0, 100.0, 101.5, 1_100_000]],
        index=index,
        columns=columns,
    )

    normalized = fetcher._normalize_history(df)

    assert list(normalized.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert normalized.empty is False
