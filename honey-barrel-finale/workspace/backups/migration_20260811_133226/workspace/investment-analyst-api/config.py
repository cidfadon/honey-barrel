"""Configuration management for Investment Analyst API."""
import os
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
	raw = os.getenv(name)
	if raw is None:
		return default
	return raw.strip().lower() in {"1", "true", "yes", "on"}

# API Configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8001"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Data Configuration
DATA_CACHE_DIR = Path(os.getenv("DATA_CACHE_DIR", "/data/cache"))
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/data/models"))
WATCHLIST_DB = Path(os.getenv("WATCHLIST_DB", "/data/watchlist.db"))

# ML Configuration
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "90"))  # 3 months
TRAIN_TEST_SPLIT = float(os.getenv("TRAIN_TEST_SPLIT", "0.8"))
MIN_DATA_POINTS = int(os.getenv("MIN_DATA_POINTS", "30"))

# Feature Engineering / Labeling Configuration
TECH_SMA_MID_WINDOW = int(os.getenv("TECH_SMA_MID_WINDOW", "20"))
TECH_SMA_LONG_WINDOW = int(os.getenv("TECH_SMA_LONG_WINDOW", "50"))
TECH_RSI_PERIOD = int(os.getenv("TECH_RSI_PERIOD", "14"))
TECH_MACD_FAST = int(os.getenv("TECH_MACD_FAST", "12"))
TECH_MACD_SLOW = int(os.getenv("TECH_MACD_SLOW", "26"))
TECH_MACD_SIGNAL = int(os.getenv("TECH_MACD_SIGNAL", "9"))
TECH_BB_STD_MULTIPLIER = float(os.getenv("TECH_BB_STD_MULTIPLIER", "2.0"))

LABEL_PREDICTION_DAYS = int(os.getenv("LABEL_PREDICTION_DAYS", "1"))
LABEL_BUY_THRESHOLD = float(os.getenv("LABEL_BUY_THRESHOLD", "0.02"))
LABEL_SELL_THRESHOLD = float(os.getenv("LABEL_SELL_THRESHOLD", "-0.02"))

FEATURE_INCLUDE_PE_RATIO = _env_bool("FEATURE_INCLUDE_PE_RATIO", True)
FEATURE_INCLUDE_DIVIDEND_YIELD = _env_bool("FEATURE_INCLUDE_DIVIDEND_YIELD", True)

# Yahoo Finance Configuration
YAHOO_TIMEOUT = int(os.getenv("YAHOO_TIMEOUT", "10"))
YAHOO_CACHE_HOURS = int(os.getenv("YAHOO_CACHE_HOURS", "24"))
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

# Model Configuration
MODEL_ALGORITHM = os.getenv("MODEL_ALGORITHM", "xgboost")  # or "random_forest"
MODEL_RETRAIN_HOURS = int(os.getenv("MODEL_RETRAIN_HOURS", "24"))

# Create directories if they don't exist
DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
