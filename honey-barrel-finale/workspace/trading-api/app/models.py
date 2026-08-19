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
