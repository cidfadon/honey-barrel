from typing import Literal, Optional

from pydantic import BaseModel, Field


class MarketOrderIn(BaseModel):
    ticker: str = Field(..., examples=["AAPL_US_EQ"])
    quantity: float = Field(..., gt=0)
    side: Literal["BUY", "SELL"]
    extended_hours: bool = False


class LimitOrderIn(MarketOrderIn):
    limit_price: float
    time_validity: Literal["DAY", "GTC"] = "DAY"


class LLMDecision(BaseModel):
    """Strict schema the LLM must obey when proposing a trade."""
    action: Literal["BUY", "SELL", "HOLD"]
    ticker: Optional[str] = None
    quantity: Optional[float] = None
    rationale: str
    confidence: float = Field(..., ge=0, le=1)


class AnalyzeOut(BaseModel):
    snapshot_id: int
    analysis_id: int
    completion: str
    decision: LLMDecision


class AutoTradeOut(AnalyzeOut):
    executed: bool
    order_id: Optional[int] = None
    reason_if_skipped: Optional[str] = None
