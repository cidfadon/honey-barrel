"""Data fetcher for stock data from Yahoo Finance."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
import yfinance as yf

from config import DATA_CACHE_DIR, DEMO_MODE, LOOKBACK_DAYS, YAHOO_CACHE_HOURS, YAHOO_TIMEOUT

LOGGER = logging.getLogger(__name__)


class DataFetcher:
    """Fetch and cache stock data from Yahoo Finance."""

    def __init__(self):
        self.cache_dir = DATA_CACHE_DIR
        self.lookback_days = LOOKBACK_DAYS
        self.cache_hours = YAHOO_CACHE_HOURS
        self.timeout = YAHOO_TIMEOUT
        self.demo_mode = DEMO_MODE
        self.last_data_source = "unknown"
        self.last_fetch_at: Optional[str] = None
        self.last_fetch_error: Optional[str] = None

    def _get_cache_path(self, ticker: str) -> Path:
        """Get cache file path for a ticker."""
        return self.cache_dir / f"{ticker.upper()}_history.json"

    def _is_cache_valid(self, ticker: str) -> bool:
        """Check if cached data is still valid."""
        cache_path = self._get_cache_path(ticker)
        if not cache_path.exists():
            return False

        cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        return cache_age < timedelta(hours=self.cache_hours)

    def _normalize_history(self, data: pd.DataFrame) -> pd.DataFrame:
        """Normalize yfinance output so downstream code always sees standard OHLCV columns."""
        if isinstance(data.columns, pd.MultiIndex):
            data = data.copy()
            data.columns = data.columns.get_level_values(-1)

        if "Adj Close" in data.columns and "Close" not in data.columns:
            data = data.rename(columns={"Adj Close": "Close"})

        return data

    def _http_get_json(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        """Fetch JSON with browser-like headers."""
        default_headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/",
        }
        if headers:
            default_headers.update(headers)
        response = requests.get(url, headers=default_headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _download_nasdaq_history(self, ticker: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Download history from Nasdaq's free public JSON API."""
        url = (
            f"https://api.nasdaq.com/api/quote/{ticker.upper()}/historical"
            f"?assetclass=stocks&fromdate={start_date:%Y-%m-%d}&todate={end_date:%Y-%m-%d}&limit=9999"
        )
        payload = self._http_get_json(url)
        rows = (((payload or {}).get("data") or {}).get("tradesTable") or {}).get("rows") or []
        if not rows:
            return pd.DataFrame()

        records: list[dict[str, Any]] = []
        for row in rows:
            try:
                records.append(
                    {
                        "Date": pd.to_datetime(row.get("date")),
                        "Open": self._parse_nasdaq_number(row.get("open")),
                        "High": self._parse_nasdaq_number(row.get("high")),
                        "Low": self._parse_nasdaq_number(row.get("low")),
                        "Close": self._parse_nasdaq_number(row.get("close")),
                        "Volume": self._parse_nasdaq_number(row.get("volume")),
                    }
                )
            except Exception:
                continue

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame.from_records(records).dropna(subset=["Date"]).set_index("Date").sort_index()
        return df[[column for column in ["Open", "High", "Low", "Close", "Volume"] if column in df.columns]]

    @staticmethod
    def _parse_nasdaq_number(value: Any) -> float:
        """Parse Nasdaq numeric values such as '$298.01' or '85,962,200'."""
        if value in (None, "", "N/A", "na", "NA"):
            return float("nan")
        text = str(value).replace("$", "").replace(",", "").strip()
        if not text or text == "-":
            return float("nan")
        try:
            return float(text)
        except ValueError:
            return float("nan")

    def _download_nasdaq_fundamentals(self, ticker: str) -> dict[str, Any]:
        """Fetch free quote metadata from Nasdaq's public JSON API."""
        url = f"https://api.nasdaq.com/api/quote/{ticker.upper()}/info?assetclass=stocks"
        payload = self._http_get_json(url)
        data = (payload or {}).get("data") or {}
        primary = data.get("primaryData") or {}
        stats = data.get("keyStats") or {}

        range_text = ((stats.get("fiftyTwoWeekHighLow") or {}).get("value") or "")
        high = low = None
        if "-" in range_text:
            low_text, high_text = [part.strip() for part in range_text.split("-", 1)]
            low = self._parse_nasdaq_number(low_text)
            high = self._parse_nasdaq_number(high_text)

        return {
            "ticker": ticker.upper(),
            "pe_ratio": None,
            "market_cap": None,
            "dividend_yield": None,
            "earnings_growth": None,
            "roe": None,
            "debt_to_equity": None,
            "profit_margin": None,
            "fifty_two_week_high": high,
            "fifty_two_week_low": low,
            "beta": None,
            "sector": None,
            "industry": None,
            "long_name": data.get("companyName") or ticker.upper(),
            "currency": primary.get("currency") or "USD",
            "fetch_time": datetime.now().isoformat(),
        }

    def _download_yahoo_history(self, ticker: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Download history with a timeout and a fallback strategy."""
        stock = yf.Ticker(ticker)
        history = None

        attempts: list[tuple[str, dict[str, Any]]] = [
            (
                "download",
                {
                    "tickers": ticker,
                    "period": f"{max(self.lookback_days, 1)}d",
                    "interval": "1d",
                    "auto_adjust": False,
                    "actions": True,
                    "progress": False,
                    "threads": False,
                },
            ),
            (
                "history",
                {
                    "start": start_date,
                    "end": end_date,
                    "auto_adjust": False,
                    "actions": True,
                },
            ),
        ]

        for method_name, kwargs in attempts:
            for attempt in range(3):
                try:
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        if method_name == "download":
                            future = executor.submit(yf.download, **kwargs)
                        else:
                            future = executor.submit(stock.history, **kwargs)
                        history = future.result(timeout=self.timeout)

                    if history is not None and not history.empty:
                        history = self._normalize_history(history)
                        return history

                    LOGGER.debug("Yahoo returned empty %s data for %s on attempt %s", method_name, ticker, attempt + 1)
                    time.sleep(1)
                except FutureTimeoutError:
                    LOGGER.warning("Yahoo fetch timed out for %s via %s (attempt %s/3)", ticker, method_name, attempt + 1)
                    if attempt < 2:
                        time.sleep(2)
                        continue
                    raise TimeoutError(f"Yahoo Finance request timed out after {self.timeout}s")
                except Exception:
                    if attempt < 2:
                        time.sleep(2)
                        continue
                    raise

        return history if history is not None else pd.DataFrame()

    def fetch_historical_data(self, ticker: str, use_cache: bool = True) -> Optional[pd.DataFrame]:
        """Fetch historical price and volume data."""
        if use_cache and self._is_cache_valid(ticker):
            try:
                return self._load_from_cache(ticker)
            except Exception as exc:
                LOGGER.warning("Cache load failed for %s: %s", ticker, exc)

        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.lookback_days)

        if self.demo_mode:
            data = self._generate_mock_data(ticker, start_date, end_date)
            if data is not None:
                self.last_data_source = "demo"
                self.last_fetch_at = datetime.now().isoformat()
                self.last_fetch_error = None
                if use_cache:
                    self._save_to_cache(ticker, data, source="demo")
            return data

        try:
            data = self._download_yahoo_history(ticker, start_date, end_date)

            if data is None or data.empty:
                try:
                    data = self._download_nasdaq_history(ticker, start_date, end_date)
                except Exception as nasdaq_exc:
                    LOGGER.warning("Nasdaq fetch failed for %s: %s", ticker, nasdaq_exc)
                    data = pd.DataFrame()

                if data is None or data.empty:
                    self.last_data_source = "demo"
                    self.last_fetch_at = datetime.now().isoformat()
                    self.last_fetch_error = "Yahoo returned empty/invalid history"
                    return self._generate_mock_data(ticker, start_date, end_date)

                self.last_data_source = "nasdaq"
                self.last_fetch_at = datetime.now().isoformat()
                self.last_fetch_error = None
                if use_cache:
                    self._save_to_cache(ticker, data, source="nasdaq")
                return data

            required_cols = ["Open", "High", "Low", "Close", "Volume"]
            missing_cols = [column for column in required_cols if column not in data.columns]
            if missing_cols:
                try:
                    data = self._download_nasdaq_history(ticker, start_date, end_date)
                except Exception as nasdaq_exc:
                    LOGGER.warning("Nasdaq fetch failed for %s: %s", ticker, nasdaq_exc)
                    data = pd.DataFrame()

                if data is None or data.empty:
                    self.last_data_source = "demo"
                    self.last_fetch_at = datetime.now().isoformat()
                    self.last_fetch_error = f"Yahoo missing required columns: {missing_cols}"
                    return self._generate_mock_data(ticker, start_date, end_date)

                self.last_data_source = "nasdaq"
                self.last_fetch_at = datetime.now().isoformat()
                self.last_fetch_error = None
                if use_cache:
                    self._save_to_cache(ticker, data, source="nasdaq")
                return data

            data = data.sort_index()
            if use_cache:
                self._save_to_cache(ticker, data, source="yahoo")

            self.last_data_source = "yahoo"
            self.last_fetch_at = datetime.now().isoformat()
            self.last_fetch_error = None
            return data
        except Exception as exc:
            LOGGER.warning("Error fetching data for %s: %s", ticker, exc)
            self.last_data_source = "demo"
            self.last_fetch_at = datetime.now().isoformat()
            self.last_fetch_error = str(exc)
            return self._generate_mock_data(ticker, start_date, end_date)

    def _generate_mock_data(self, ticker: str, start_date, end_date) -> Optional[pd.DataFrame]:
        """Generate mock OHLCV data for demonstration purposes."""
        try:
            dates = pd.date_range(start=start_date, end=end_date, freq="D")
            base_price = 150.0
            return pd.DataFrame(
                {
                    "Open": [base_price + (i % 10) - 5 for i in range(len(dates))],
                    "High": [base_price + 5 + (i % 10) - 5 for i in range(len(dates))],
                    "Low": [base_price - 5 + (i % 10) - 5 for i in range(len(dates))],
                    "Close": [base_price + 2 + (i % 10) - 5 for i in range(len(dates))],
                    "Volume": [1_000_000 + (i * 10_000) % 5_000_000 for i in range(len(dates))],
                    "Dividends": [0.0] * len(dates),
                    "Stock Splits": [0.0] * len(dates),
                },
                index=dates,
            )
        except Exception as exc:
            LOGGER.error("Failed to generate mock data for %s: %s", ticker, exc)
            return None

    def _safe_fast_info(self, stock: yf.Ticker) -> dict[str, Any]:
        """Read yfinance fast_info without letting transient failures escape."""
        try:
            fast_info = getattr(stock, "fast_info", None)
            return dict(fast_info) if fast_info is not None else {}
        except Exception:
            return {}

    def _safe_info(self, stock: yf.Ticker) -> dict[str, Any]:
        """Read yfinance info without letting transient failures escape."""
        try:
            info = stock.info or {}
            return dict(info)
        except Exception:
            try:
                getter = getattr(stock, "get_info", None)
                return dict(getter()) if callable(getter) else {}
            except Exception:
                return {}

    def fetch_fundamentals(self, ticker: str) -> dict:
        """Fetch fundamental data (P/E, Market Cap, Dividend Yield, etc.)."""
        stock = yf.Ticker(ticker)
        fast_info = self._safe_fast_info(stock)
        info = self._safe_info(stock)

        fundamentals = {
            "ticker": ticker.upper(),
            "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
            "market_cap": info.get("marketCap") or fast_info.get("market_cap") or fast_info.get("marketCap"),
            "dividend_yield": info.get("dividendYield") or fast_info.get("dividendYield"),
            "earnings_growth": info.get("earningsGrowth"),
            "roe": info.get("returnOnEquity"),
            "debt_to_equity": info.get("debtToEquity"),
            "profit_margin": info.get("profitMargins"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh") or fast_info.get("yearHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow") or fast_info.get("yearLow"),
            "beta": info.get("beta"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "long_name": info.get("longName") or info.get("shortName") or ticker.upper(),
            "currency": info.get("currency") or fast_info.get("currency") or "USD",
            "fetch_time": datetime.now().isoformat(),
        }

        if any(value is not None for key, value in fundamentals.items() if key not in {"ticker", "long_name", "currency", "fetch_time"}):
            return fundamentals

        try:
            nasdaq = self._download_nasdaq_fundamentals(ticker)
            nasdaq["fetch_time"] = datetime.now().isoformat()
            return nasdaq
        except Exception as exc:
            LOGGER.warning("Nasdaq fundamentals failed for %s: %s", ticker, exc)
            self.last_fetch_error = self.last_fetch_error or "Yahoo fundamentals unavailable"
            return fundamentals

    def _save_to_cache(self, ticker: str, data: pd.DataFrame, source: str = "yahoo") -> None:
        """Save data to cache."""
        cache_path = self._get_cache_path(ticker)
        payload = {
            "source": source,
            "saved_at": datetime.now().isoformat(),
            "fetch_error": self.last_fetch_error,
            "data": json.loads(data.to_json(date_format="iso", orient="split")),
        }
        with cache_path.open("w", encoding="utf-8") as file_handle:
            json.dump(payload, file_handle)

    def _load_from_cache(self, ticker: str) -> pd.DataFrame:
        """Load data from cache."""
        cache_path = self._get_cache_path(ticker)

        with cache_path.open("r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)

        if isinstance(payload, dict) and "data" in payload and "source" in payload:
            split = payload["data"]
            df = pd.DataFrame(split["data"], columns=split["columns"])
            df.index = pd.to_datetime(split["index"])
            self.last_data_source = str(payload.get("source") or "unknown")
            self.last_fetch_at = payload.get("saved_at")
            self.last_fetch_error = payload.get("fetch_error")
            return df

        self.last_data_source = "unknown"
        self.last_fetch_at = datetime.fromtimestamp(cache_path.stat().st_mtime).isoformat()
        self.last_fetch_error = None
        return pd.read_json(cache_path)

    def get_last_data_source(self) -> str:
        """Return the source used by the latest successful historical fetch."""
        return self.last_data_source

    def get_last_fetch_at(self) -> Optional[str]:
        """Return ISO timestamp for the latest successful historical fetch."""
        return self.last_fetch_at

    def get_last_fetch_error(self) -> Optional[str]:
        """Return the latest historical fetch error message, if any."""
        return self.last_fetch_error