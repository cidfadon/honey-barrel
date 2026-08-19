"""Feature engineering for ML model."""
import pandas as pd
import numpy as np

from config import (
    FEATURE_INCLUDE_DIVIDEND_YIELD,
    FEATURE_INCLUDE_PE_RATIO,
    LABEL_BUY_THRESHOLD,
    LABEL_PREDICTION_DAYS,
    LABEL_SELL_THRESHOLD,
    MIN_DATA_POINTS,
    TECH_BB_STD_MULTIPLIER,
    TECH_MACD_FAST,
    TECH_MACD_SIGNAL,
    TECH_MACD_SLOW,
    TECH_RSI_PERIOD,
    TECH_SMA_LONG_WINDOW,
    TECH_SMA_MID_WINDOW,
)


def _rolling_window(
    n_rows: int,
    default: int,
    min_samples: int = MIN_DATA_POINTS,
    label_days: int = LABEL_PREDICTION_DAYS,
) -> int:
    """Shrink rolling windows so enough rows survive dropna() for training."""
    reserve = min_samples + label_days + 2
    max_allowed = n_rows - reserve
    if max_allowed < 2:
        return 2
    return min(default, max_allowed)


def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate technical indicators using pandas TA-Lib."""
    df = df.copy()

    # Ensure we have OHLCV columns
    if "Close" not in df.columns:
        raise ValueError("DataFrame must contain 'Close' column")

    n_rows = len(df)
    long_window = _rolling_window(n_rows, max(2, TECH_SMA_LONG_WINDOW), label_days=LABEL_PREDICTION_DAYS)
    mid_window = min(max(2, TECH_SMA_MID_WINDOW), long_window)
    rsi_period = max(2, min(max(2, TECH_RSI_PERIOD), mid_window))
    macd_fast = max(2, TECH_MACD_FAST)
    macd_slow = max(macd_fast + 1, TECH_MACD_SLOW)
    macd_signal = max(2, TECH_MACD_SIGNAL)
    bb_std_multiplier = float(TECH_BB_STD_MULTIPLIER)

    # RSI (Relative Strength Index)
    df["RSI_14"] = calculate_rsi(df["Close"], period=rsi_period)

    # Moving Averages
    df["SMA_20"] = df["Close"].rolling(window=mid_window).mean()
    df["SMA_50"] = df["Close"].rolling(window=long_window).mean()
    df["EMA_12"] = df["Close"].ewm(span=macd_fast, adjust=False).mean()
    df["EMA_26"] = df["Close"].ewm(span=macd_slow, adjust=False).mean()

    # MACD
    df["MACD"] = df["EMA_12"] - df["EMA_26"]
    df["MACD_Signal"] = df["MACD"].ewm(span=macd_signal, adjust=False).mean()
    df["MACD_Diff"] = df["MACD"] - df["MACD_Signal"]

    # Bollinger Bands
    bb_sma = df["Close"].rolling(window=mid_window).mean()
    bb_std = df["Close"].rolling(window=mid_window).std()
    df["BB_Upper"] = bb_sma + (bb_std * bb_std_multiplier)
    df["BB_Lower"] = bb_sma - (bb_std * bb_std_multiplier)
    df["BB_Position"] = (df["Close"] - df["BB_Lower"]) / (df["BB_Upper"] - df["BB_Lower"])

    # Price momentum and volatility
    df["Daily_Return"] = df["Close"].pct_change()
    df["Volatility"] = df["Daily_Return"].rolling(window=mid_window).std()
    df["Price_Range"] = (df["High"] - df["Low"]) / df["Close"]

    # Volume indicators
    if "Volume" in df.columns:
        df["Volume_MA"] = df["Volume"].rolling(window=mid_window).mean()
        df["Volume_Ratio"] = df["Volume"] / df["Volume_MA"]

    return df


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index."""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def prepare_features(df: pd.DataFrame, add_fundamentals: dict = None) -> pd.DataFrame:
    """Prepare and normalize features for ML model."""
    df = df.copy()

    # Drop rows with NaN values (from moving averages)
    df = df.dropna()

    # Select feature columns
    feature_cols = [
        "Close",
        "Volume",
        "High",
        "Low",
        "RSI_14",
        "SMA_20",
        "SMA_50",
        "MACD",
        "MACD_Signal",
        "MACD_Diff",
        "BB_Position",
        "Daily_Return",
        "Volatility",
        "Price_Range",
        "Volume_Ratio",
    ]

    # Filter to available columns
    available_cols = [col for col in feature_cols if col in df.columns]
    features = df[available_cols].copy()

    # Normalize features to 0-1 range
    for col in features.columns:
        min_val = features[col].min()
        max_val = features[col].max()
        if max_val > min_val:
            features[col] = (features[col] - min_val) / (max_val - min_val)
        else:
            features[col] = 0.5

    # Add fundamental features if provided
    if add_fundamentals:
        if FEATURE_INCLUDE_PE_RATIO and "pe_ratio" in add_fundamentals and add_fundamentals["pe_ratio"]:
            features["PE_Ratio"] = add_fundamentals["pe_ratio"]
        if FEATURE_INCLUDE_DIVIDEND_YIELD and "dividend_yield" in add_fundamentals and add_fundamentals["dividend_yield"]:
            features["Dividend_Yield"] = add_fundamentals["dividend_yield"]

    return features


def create_labels(df: pd.DataFrame, prediction_days: int = LABEL_PREDICTION_DAYS) -> pd.Series:
    """Create labels for training (BUY: 2, HOLD: 1, SELL: 0)."""
    # Calculate future return
    future_return = df["Close"].shift(-prediction_days) / df["Close"] - 1

    # Define thresholds (adjust based on risk tolerance)
    buy_threshold = LABEL_BUY_THRESHOLD
    sell_threshold = LABEL_SELL_THRESHOLD

    labels = pd.Series(index=df.index, dtype=int)
    labels[future_return > buy_threshold] = 2  # BUY
    labels[future_return < sell_threshold] = 0  # SELL
    labels[(future_return >= sell_threshold) & (future_return <= buy_threshold)] = 1  # HOLD

    # Remove last N rows (no future data for labels)
    labels = labels[:-prediction_days]
    
    # Return only valid labels (remove NaN)
    return labels.dropna()
