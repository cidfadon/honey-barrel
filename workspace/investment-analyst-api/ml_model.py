"""ML model for stock prediction."""
import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from config import MODEL_DIR, MIN_DATA_POINTS, TRAIN_TEST_SPLIT as SPLIT_RATIO
from feature_engineering import calculate_technical_indicators, create_labels, prepare_features


class StockPredictor:
    """ML model for stock price movement prediction."""

    def __init__(self, algorithm: str = "random_forest"):
        self.algorithm = algorithm
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = None
        self.models = {}  # Per-ticker models
        self.scalers = {}  # Per-ticker scalers
        self.feature_names_by_ticker = {}  # Per-ticker training feature order

    def train(
        self, df: pd.DataFrame, ticker: str, fundamentals: dict = None
    ) -> dict:
        """Train model on historical data."""
        ticker = ticker.upper()
        if len(df) < MIN_DATA_POINTS:
            return {
                "success": False,
                "error": f"Insufficient data: {len(df)} rows, need {MIN_DATA_POINTS}",
            }

        try:
            # Add technical indicators
            df_enriched = calculate_technical_indicators(df)

            # Prepare features
            features = prepare_features(df_enriched, fundamentals)

            # Create labels
            labels = create_labels(df_enriched)

            # Align features and labels by index
            common_index = features.index.intersection(labels.index)
            features = features.loc[common_index]
            labels = labels.loc[common_index]

            if len(features) < MIN_DATA_POINTS:
                return {
                    "success": False,
                    "error": f"Insufficient data after processing: {len(features)} rows",
                }

            # Store feature names
            self.feature_names = features.columns.tolist()

            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                features, labels, test_size=1 - SPLIT_RATIO, shuffle=False
            )

            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)

            # Train model
            # Ensure we have all classes (add dummy samples if needed for multi-class)
            unique_classes = set(y_train)
            if len(unique_classes) < 3:
                # Add synthetic samples for missing classes to ensure all classes are present
                missing_classes = set([0, 1, 2]) - unique_classes
                for cls in missing_classes:
                    dummy_sample = X_train_scaled[0:1] * 0  # Create zero vector
                    X_train_scaled = np.vstack([X_train_scaled, dummy_sample])
                    y_train = pd.concat([y_train, pd.Series([cls])], ignore_index=True)
            
            if self.algorithm == "random_forest":
                model = RandomForestClassifier(
                    n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
                )
            else:
                try:
                    import xgboost as xgb

                    model = xgb.XGBClassifier(
                        n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
                    )
                except ImportError:
                    # Fallback to Random Forest if XGBoost not available
                    model = RandomForestClassifier(
                        n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
                    )

            model.fit(X_train_scaled, y_train)

            # Evaluate
            train_score = model.score(X_train_scaled, y_train)
            test_score = model.score(X_test_scaled, y_test)

            # Store per-ticker model
            self.models[ticker] = model
            self.scalers[ticker] = scaler
            self.feature_names_by_ticker[ticker] = self.feature_names

            # Save model
            self._save_model(ticker, model, scaler)

            return {
                "success": True,
                "ticker": ticker,
                "train_score": float(train_score),
                "test_score": float(test_score),
                "samples": len(features),
                "features": self.feature_names,
                "trained_at": datetime.now().isoformat(),
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def predict(
        self, df: pd.DataFrame, ticker: str, fundamentals: dict = None
    ) -> dict:
        """Generate prediction for a stock."""
        try:
            ticker = ticker.upper()
            # Load model if not in memory
            if ticker not in self.models:
                self._load_model(ticker)

            if ticker not in self.models:
                train_result = self.train(df, ticker, fundamentals)
                if not train_result.get("success"):
                    return train_result

            model = self.models[ticker]
            scaler = self.scalers[ticker]

            # Prepare features from latest data
            df_enriched = calculate_technical_indicators(df)
            features = prepare_features(df_enriched, fundamentals)

            # Keep compatibility with previously trained models by matching
            # training feature schema/order loaded from metadata.
            expected_features = self.feature_names_by_ticker.get(ticker)
            if expected_features:
                for feature_name in expected_features:
                    if feature_name not in features.columns:
                        features[feature_name] = 0.5
                features = features.reindex(columns=expected_features, fill_value=0.5)
                features = features.fillna(0.5)

            if len(features) == 0:
                return {"success": False, "error": "No valid features to predict"}

            # Use latest data point
            latest_features = features.iloc[-1:].values
            latest_features_scaled = scaler.transform(latest_features)

            # Get prediction
            prediction = model.predict(latest_features_scaled)[0]
            probabilities = model.predict_proba(latest_features_scaled)[0]

            # Map to action (0=SELL, 1=HOLD, 2=BUY)
            action_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
            action = action_map.get(prediction, "HOLD")

            # Get confidence (highest probability)
            confidence = max(probabilities) if probabilities is not None else 0.0

            return {
                "success": True,
                "ticker": ticker,
                "action": action,
                "confidence": float(confidence),
                "probabilities": {
                    "BUY": float(probabilities[2]) if len(probabilities) > 2 else 0.0,
                    "HOLD": float(probabilities[1]) if len(probabilities) > 1 else 0.0,
                    "SELL": float(probabilities[0]) if len(probabilities) > 0 else 0.0,
                },
                "latest_price": float(df["Close"].iloc[-1]),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _save_model(self, ticker: str, model, scaler) -> None:
        """Persist model to disk."""
        ticker = ticker.upper()
        model_path = MODEL_DIR / f"{ticker}_model.pkl"
        scaler_path = MODEL_DIR / f"{ticker}_scaler.pkl"

        with open(model_path, "wb") as f:
            pickle.dump(model, f)

        with open(scaler_path, "wb") as f:
            pickle.dump(scaler, f)

        # Save metadata
        metadata = {
            "ticker": ticker,
            "algorithm": self.algorithm,
            "features": self.feature_names,
            "saved_at": datetime.now().isoformat(),
        }
        metadata_path = MODEL_DIR / f"{ticker.upper()}_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f)

    def _load_model(self, ticker: str) -> bool:
        """Load model from disk."""
        ticker = ticker.upper()
        model_path = MODEL_DIR / f"{ticker}_model.pkl"
        scaler_path = MODEL_DIR / f"{ticker}_scaler.pkl"

        if not model_path.exists() or not scaler_path.exists():
            return False

        try:
            with open(model_path, "rb") as f:
                self.models[ticker] = pickle.load(f)

            with open(scaler_path, "rb") as f:
                self.scalers[ticker] = pickle.load(f)

            metadata_path = MODEL_DIR / f"{ticker}_metadata.json"
            if metadata_path.exists():
                with open(metadata_path, "r") as f:
                    metadata = json.load(f)
                features = metadata.get("features")
                if isinstance(features, list) and features:
                    self.feature_names_by_ticker[ticker] = features

            return True
        except Exception:
            return False
