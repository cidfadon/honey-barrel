"""Watch list management."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config import WATCHLIST_DB


class WatchListManager:
    """Manage user watch lists."""

    def __init__(self):
        self.db_path = WATCHLIST_DB
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT UNIQUE NOT NULL,
                    name TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT
                )
                """
            )
            conn.commit()

    def add_stock(self, ticker: str, name: Optional[str] = None, notes: str = "") -> dict:
        """Add stock to watch list."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO watchlist (ticker, name, notes) VALUES (?, ?, ?)",
                    (ticker.upper(), name, notes),
                )
                conn.commit()
            return {"success": True, "ticker": ticker, "action": "added"}
        except sqlite3.IntegrityError:
            return {"success": False, "error": f"{ticker} already in watch list"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def remove_stock(self, ticker: str) -> dict:
        """Remove stock from watch list."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM watchlist WHERE ticker = ?", (ticker.upper(),)
                )
                conn.commit()
                if cursor.rowcount == 0:
                    return {"success": False, "error": f"{ticker} not in watch list"}
            return {"success": True, "ticker": ticker, "action": "removed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_watchlist(self) -> dict:
        """Get current watch list."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT ticker, name, notes, added_at FROM watchlist ORDER BY added_at DESC"
                )
                stocks = [
                    {
                        "ticker": row["ticker"],
                        "name": row["name"],
                        "notes": row["notes"],
                        "added_at": row["added_at"],
                    }
                    for row in cursor.fetchall()
                ]
            return {"success": True, "stocks": stocks, "count": len(stocks)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_tickers(self) -> List[str]:
        """Get list of tickers in watch list."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT ticker FROM watchlist ORDER BY added_at DESC")
                return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []

    def clear_watchlist(self) -> dict:
        """Clear all stocks from watch list."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM watchlist")
                conn.commit()
            return {"success": True, "action": "cleared"}
        except Exception as e:
            return {"success": False, "error": str(e)}
