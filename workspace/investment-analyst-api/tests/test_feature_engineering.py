"""Tests for feature_engineering module — pure math, no external deps."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Allow imports from the investment-analyst-api package root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from feature_engineering import (
    calculate_rsi,
    calculate_technical_indicators,
    create_labels,
    prepare_features,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ohlcv(n: int = 100, base: float = 150.0) -> pd.DataFrame:
    """Generate a simple OHLCV DataFrame with a slight uptrend."""
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = [base + i * 0.5 + (i % 7) for i in range(n)]
    return pd.DataFrame(
        {
            "Open": [c - 1.0 for c in close],
            "High": [c + 2.0 for c in close],
            "Low": [c - 2.0 for c in close],
            "Close": close,
            "Volume": [1_000_000 + i * 1000 for i in range(n)],
        },
        index=dates,
    )


# ---------------------------------------------------------------------------
# calculate_rsi
# ---------------------------------------------------------------------------

class TestCalculateRSI:
    def test_returns_series_of_correct_length(self):
        prices = pd.Series([100 + i for i in range(30)])
        rsi = calculate_rsi(prices, period=14)
        assert len(rsi) == len(prices)

    def test_rsi_bounded_0_100(self):
        prices = pd.Series([100 + i * 0.3 for i in range(50)])
        rsi = calculate_rsi(prices, period=14).dropna()
        assert (rsi >= 0).all() and (rsi <= 100).all()

    def test_monotonically_rising_prices_give_high_rsi(self):
        prices = pd.Series(range(1, 51), dtype=float)
        rsi = calculate_rsi(prices, period=14).dropna()
        assert rsi.iloc[-1] > 70

    def test_monotonically_falling_prices_give_low_rsi(self):
        prices = pd.Series(list(range(50, 0, -1)), dtype=float)
        rsi = calculate_rsi(prices, period=14).dropna()
        assert rsi.iloc[-1] < 30


# ---------------------------------------------------------------------------
# calculate_technical_indicators
# ---------------------------------------------------------------------------

class TestCalculateTechnicalIndicators:
    def test_adds_expected_columns(self):
        df = _ohlcv(100)
        result = calculate_technical_indicators(df)
        expected_cols = {
            "RSI_14", "SMA_20", "SMA_50", "EMA_12", "EMA_26",
            "MACD", "MACD_Signal", "MACD_Diff",
            "BB_Upper", "BB_Lower", "BB_Position",
            "Daily_Return", "Volatility", "Price_Range",
            "Volume_MA", "Volume_Ratio",
        }
        assert expected_cols.issubset(set(result.columns))

    def test_does_not_modify_original(self):
        df = _ohlcv(60)
        original_cols = set(df.columns)
        calculate_technical_indicators(df)
        assert set(df.columns) == original_cols

    def test_raises_without_close_column(self):
        df = pd.DataFrame({"Open": [1, 2, 3], "Volume": [100, 200, 300]})
        with pytest.raises(ValueError, match="Close"):
            calculate_technical_indicators(df)

    def test_works_without_volume_column(self):
        df = _ohlcv(60).drop(columns=["Volume"])
        result = calculate_technical_indicators(df)
        assert "Volume_MA" not in result.columns
        assert "MACD" in result.columns

    def test_short_history_leaves_enough_rows_for_training(self):
        from config import MIN_DATA_POINTS

        df = _ohlcv(61)
        enriched = calculate_technical_indicators(df)
        features = prepare_features(enriched)
        labels = create_labels(enriched)
        common = features.index.intersection(labels.index)
        assert len(common) >= MIN_DATA_POINTS


# ---------------------------------------------------------------------------
# prepare_features
# ---------------------------------------------------------------------------

class TestPrepareFeatures:
    def test_drops_nan_rows(self):
        df = calculate_technical_indicators(_ohlcv(100))
        features = prepare_features(df)
        assert not features.isnull().any().any()

    def test_values_normalised_0_1(self):
        df = calculate_technical_indicators(_ohlcv(100))
        features = prepare_features(df)
        for col in features.columns:
            assert features[col].min() >= -1e-9
            assert features[col].max() <= 1.0 + 1e-9

    def test_constant_column_gets_0_5(self):
        df = calculate_technical_indicators(_ohlcv(100))
        df["Close"] = 100.0
        df = calculate_technical_indicators(df)
        features = prepare_features(df)
        if "Close" in features.columns:
            assert (features["Close"] == 0.5).all()

    def test_adds_fundamentals(self):
        df = calculate_technical_indicators(_ohlcv(100))
        fundamentals = {"pe_ratio": 25.0, "dividend_yield": 0.02}
        features = prepare_features(df, add_fundamentals=fundamentals)
        assert "PE_Ratio" in features.columns
        assert "Dividend_Yield" in features.columns


# ---------------------------------------------------------------------------
# create_labels
# ---------------------------------------------------------------------------

class TestCreateLabels:
    def test_labels_are_0_1_2(self):
        df = _ohlcv(100)
        labels = create_labels(df, prediction_days=1)
        assert set(labels.unique()).issubset({0, 1, 2})

    def test_length_shorter_by_prediction_days(self):
        df = _ohlcv(100)
        labels = create_labels(df, prediction_days=3)
        # After removing NaN and last N rows, length should be <= 100 - 3
        assert len(labels) <= len(df) - 3

    def test_buy_label_for_big_upswing(self):
        prices = list(range(100, 150))
        prices[-1] = prices[-2] + 100  # huge jump on last day
        df = pd.DataFrame(
            {
                "Open": prices,
                "High": [p + 1 for p in prices],
                "Low": [p - 1 for p in prices],
                "Close": prices,
                "Volume": [1_000_000] * len(prices),
            },
            index=pd.date_range("2024-01-01", periods=len(prices)),
        )
        labels = create_labels(df, prediction_days=1)
        # The day before the big jump should be labeled BUY (2)
        assert labels.iloc[-1] == 2
