from datetime import datetime

from sqlalchemy import (
    JSON, BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, String, Text,
)

# Use Integer in SQLite (so auto-increment works) and BigInteger in Postgres.
PK = BigInteger().with_variant(Integer(), "sqlite")
FK = BigInteger().with_variant(Integer(), "sqlite")

from .db import Base


class T212Call(Base):
    __tablename__ = "t212_calls"
    id = Column(PK, primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    endpoint = Column(Text, nullable=False)
    method = Column(Text, nullable=False)
    payload = Column(JSON)
    response = Column(JSON)
    http_status = Column(Integer)
    latency_ms = Column(Integer)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    id = Column(PK, primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    cash = Column(JSON, nullable=False)
    positions = Column(JSON, nullable=False)


class Order(Base):
    __tablename__ = "orders"
    id = Column(PK, primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    t212_order_id = Column(Text, unique=True)
    ticker = Column(Text, nullable=False)
    side = Column(String(4), nullable=False)            # BUY | SELL
    qty = Column(Numeric(18, 6), nullable=False)
    order_type = Column(Text, nullable=False)           # MARKET | LIMIT | STOP
    limit_price = Column(Numeric(18, 6))
    status = Column(Text, nullable=False)
    raw = Column(JSON)


class LLMAnalysis(Base):
    __tablename__ = "llm_analyses"
    id = Column(PK, primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    snapshot_id = Column(FK, ForeignKey("portfolio_snapshots.id"))
    model = Column(Text, nullable=False)
    prompt = Column(Text, nullable=False)
    completion = Column(Text, nullable=False)
    decision = Column(JSON)
    triggered_order_id = Column(FK, ForeignKey("orders.id"))


class DailyTradingLog(Base):
    """One record per trading day.  Written (or upserted) when a day's
    end-of-day snapshot is finalised via POST /api/daily-log.

    Columns
    -------
    trade_date  – the calendar date this row describes  (unique)
    strategy    – Ollama model name / strategy label used that day
    snapshot    – full PortfolioSnapshot payload (cash + positions) as JSON
    orders      – list of all Order rows placed that day as JSON
    analyses    – list of all LLMAnalysis rows that day as JSON
    profit      – net profit/loss for the day (computed by the caller or from
                  the difference in total portfolio value between BOD and EOD)
    notes       – free-form text (e.g. market conditions, guardrail hits)
    log_file    – relative path inside reports/ where the raw CSV log was saved
    """
    __tablename__ = "daily_trading_logs"

    id = Column(PK, primary_key=True, autoincrement=True)
    trade_date = Column(Text, unique=True, nullable=False)   # "YYYY-MM-DD"
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow,
                        onupdate=datetime.utcnow, nullable=False)
    strategy = Column(Text, nullable=False, default="")
    snapshot = Column(JSON, nullable=False, default=dict)
    orders = Column(JSON, nullable=False, default=list)
    analyses = Column(JSON, nullable=False, default=list)
    profit = Column(Numeric(18, 6), nullable=True)
    notes = Column(Text, nullable=True)
    log_file = Column(Text, nullable=True)
