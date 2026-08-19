"""Tests for StockPredictor auto-train-on-predict behavior."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml_model import StockPredictor


def _ohlcv(n: int = 100, base: float = 150.0) -> pd.DataFrame:
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


@pytest.fixture
def model_dir(tmp_path, monkeypatch):
    import config as cfg
    import ml_model as ml_mod

    model_path = tmp_path / "models"
    model_path.mkdir()
    monkeypatch.setattr(cfg, "MODEL_DIR", model_path)
    monkeypatch.setattr(ml_mod, "MODEL_DIR", model_path)
    return model_path


class TestPredictAutoTrain:
    def test_predict_trains_when_no_model_exists(self, model_dir):
        predictor = StockPredictor()
        df = _ohlcv(n=61)
        result = predictor.predict(df, "TEST")

        assert result["success"] is True
        assert result["ticker"] == "TEST"
        assert result["action"] in {"BUY", "HOLD", "SELL"}
        assert (model_dir / "TEST_model.pkl").exists()
        assert (model_dir / "TEST_scaler.pkl").exists()

    def test_predict_returns_train_error_when_auto_train_fails(self, model_dir):
        predictor = StockPredictor()
        df = _ohlcv(n=10)
        result = predictor.predict(df, "SHORT")

        assert result["success"] is False
        assert "Insufficient data" in result["error"]
