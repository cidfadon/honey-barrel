## 1. Purpose

Define a **mean‑reversion intraday strategy** that exploits price reactions around the **Volume‑Weighted Average Price (VWAP)**. VWAP Bounce is one of the most widely used institutional day‑trading strategies because VWAP represents **fair value**, **institutional order flow**, and **intraday equilibrium**.

## 2. Source Of Truth

Use this blueprint together with:

- **VWAP basics**
    
- **VWAP Bounce**
    
- **Mean reversion**
    
- /workspace/docs/DEFINITIVE_SKILLS_MANIFEST.md
    

If conflicts arise, MCP‑only rules override.

## 3. Strategy Definition

VWAP Bounce is a **reaction strategy**:

- When price pulls back to VWAP during a trend, traders expect a **bounce** (continuation).
    
- When price rejects VWAP from below, traders expect a **fade** (mean reversion).
    

Key characteristics:

- Works best in **trending markets**
    
- Uses VWAP as dynamic support/resistance
    
- Requires volume confirmation
    
- Uses tight risk controls
    

## 4. Roles And Boundaries

### 4.1 investment-analyst

Responsibility:

- detect VWAP bounce or VWAP rejection setups
    
- compute trend direction
    
- produce BUY/SELL/HOLD signals with confidence
    

Primary MCP tools:

- **data_fetch**
    
- **analyze_stock**
    
- **analyze_watchlist**
    

### 4.2 investment-broker

Responsibility:

- execute bounce/fade trades
    
- enforce risk rules
    
- verify order state
    

Primary MCP tools:

- **order_place_market**
    
- **order_place_limit**
    
- **position_close**
    

### 4.3 investment-analysis-cycle

Responsibility:

- orchestrate VWAP detection → execution → reporting
    
- enforce hard success criteria identical to main blueprint
    

## 5. Inputs

Required:

- watchlist symbols
    
- vwap_window: intraday VWAP (default)
    

Optional:

- trend_detection_window
    
- min_volume_confirmation
    
- bounce_confirmation_candles
    
- stop_loss_method: VWAP breach | ATR | fixed %
    

## 6. Output Contract

Returns:

- status
    
- run_id
    
- timestamps
    
- vwap_window_used
    
- analyst_summary
    
- broker_summary
    
- orders_executed
    
- report_write_verified
    
- failure_reasons
    

## 7. Orchestration Flow (VWAP Version)

### Phase A: Intake & Validation

1. Validate watchlist
    
2. Normalize symbols
    
3. Compute VWAP
    
4. Fetch trend + volume data
    

### Phase B: Analyst Phase

1. Detect trend direction
    
2. Detect VWAP bounce or VWAP rejection
    
3. Confirm with:
    
    - volume ≥ min_volume_confirmation
        
    - trend alignment
        
    - candle confirmation
        
4. Produce BUY/SELL/HOLD with confidence
    

### Phase C: Broker Phase

1. Check market state
    
2. For BUY (VWAP bounce in uptrend):
    
    - place market order
        
    - fallback to limit order if spread widens
        
3. For SELL (VWAP rejection in downtrend):
    
    - execute short order
        
4. Apply stop-loss rules
    
5. Log all attempts
    

### Phase D: Report & Verification

1. Build JSON/Markdown report
    
2. Save to /workspace/reports
    
3. Verify readability
    
4. Return final status
    

## 8. VWAP Entry Rules

### Long (BUY)

- Price above VWAP
    
- Pullback touches VWAP
    
- Bounce candle closes above VWAP
    
- Volume spike confirms continuation
    

### Short (SELL)

- Price below VWAP
    
- Pullback touches VWAP
    
- Rejection candle closes below VWAP
    
- Volume spike confirms continuation
    

## 9. VWAP Exit Rules

- Stop-loss:
    
    - VWAP breach (most common)
        
    - or ATR (0.3–0.6 ATR)
        
- Take-profit:
    
    - 1.5×–2.5× risk
        
- Optional trailing stop using VWAP band
    

## 10. Risk Controls

- Max 1% account risk per trade
    
- Max 3 VWAP trades per session
    
- Avoid low‑volume periods
    
- Avoid correlated tickers
    
- No trades during major news releases
    

## 11. Example VWAP Strategy Report

json

```
{
  "status": "success",
  "run_id": "vwap_20260809_101501",
  "started_at": "2026-08-09T10:15:01Z",
  "completed_at": "2026-08-09T10:17:22Z",
  "vwap_window_used": "intraday",
  "watchlist_used": ["AAPL", "TSLA", "NVDA"],
  "analyst_summary": {
    "signals": [
      {"symbol": "AAPL", "action": "BUY", "confidence": 0.83},
      {"symbol": "TSLA", "action": "SELL", "confidence": 0.71}
    ]
  },
  "broker_summary": {
    "executed": 2,
    "attempt_logs": [
      {
        "tool_name": "order_place_market",
        "attempt": 1,
        "max_attempts": 3,
        "error_class": "retryable",
        "result": "success",
        "timestamp": "2026-08-09T10:16:01Z"
      }
    ]
  },
  "orders_executed": [
    {
      "symbol": "AAPL",
      "order_id": "vwap111",
      "order_status": "accepted",
      "submitted_at": "2026-08-09T10:16:01Z"
    }
  ],
  "report_write_verified": true,
  "failure_reasons": []
}
```

## 12. Failure Semantics

Same as main blueprint:

- no successful write order
    
- missing metadata
    
- report unreadable
    
- MCP substitution violations
    

## 13. Prompt Template

Run VWAP Bounce strategy for watchlist: AAPL, TSLA, NVDA. Use MCP-only execution path. Detect VWAP bounce/rejection signals. Require at least one Alpaca write success. Persist final report and verify readability. Return status=failed if any hard condition is unmet.

## 14. Minimal Smoke Checklist

1. Compute VWAP
    
2. Detect bounce/rejection
    
3. Confirm trend + volume
    
4. Execute broker decision
    
5. Verify order metadata
    
6. Write & verify report
    

If you want, I can now generate a **VWAP Bounce + ORB + Scalping unified multi‑strategy blueprint**, or produce **a full MCP server implementation** for VWAP Bounce.

Choose:

- **Multi‑Strategy Blueprint**
    
- **VWAP MCP Server**