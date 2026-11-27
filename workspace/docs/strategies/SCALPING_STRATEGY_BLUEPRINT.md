
## 1. Purpose

Define a **high‑frequency intraday scalping strategy** designed to capture **small, repeatable price movements** using strict risk controls, fast execution, and MCP‑only tooling. This blueprint mirrors your analyst/broker/orchestration architecture.

## 2. Source Of Truth

Use this blueprint together with:

- **Scalping basics**
    
- **Order flow**
    
- **Tape reading**
    
- /workspace/docs/DEFINITIVE_SKILLS_MANIFEST.md
    

If conflicts arise, MCP‑only rules override.

## 3. Strategy Definition

Scalping is a **rapid‑execution strategy** where trades last **seconds to minutes**, targeting **0.05%–0.30%** price moves. Key characteristics:

- high liquidity
    
- tight spreads
    
- fast confirmation signals
    
- strict stop-loss discipline
    

Common tools: Level 2, order flow, micro‑trend detection, VWAP micro‑bounces.

## 4. Roles And Boundaries

### 4.1 investment-analyst

Responsibility:

- detect micro‑trend setups
    
- identify scalping windows (high liquidity periods)
    
- produce BUY/SELL/HOLD signals with confidence
    

Primary MCP tools:

- **data_fetch**
    
- **analyze_stock**
    
- **analyze_watchlist**
    

### 4.2 investment-broker

Responsibility:

- execute rapid BUY/SELL orders
    
- enforce micro‑risk rules
    
- verify order state
    

Primary MCP tools:

- **order_place_market**
    
- **order_place_limit**
    
- **position_close**
    

### 4.3 investment-analysis-cycle

Responsibility:

- orchestrate scalping detection → execution → reporting
    
- enforce hard success criteria identical to main blueprint
    

## 5. Inputs

Required:

- watchlist symbols
    
- scalping_window: e.g., 09:30–11:00 EST
    

Optional:

- max_trade_duration_seconds
    
- max_spread_allowed
    
- min_liquidity_threshold
    
- stop_loss_method: fixed ticks | ATR micro | spread‑based
    

## 6. Output Contract

Returns:

- status
    
- run_id
    
- timestamps
    
- scalping_window_used
    
- analyst_summary
    
- broker_summary
    
- orders_executed
    
- report_write_verified
    
- failure_reasons
    

## 7. Orchestration Flow (Scalping Version)

### Phase A: Intake & Validation

1. Validate watchlist
    
2. Normalize symbols
    
3. Confirm scalping window
    
4. Fetch micro‑data (1s–30s intervals)
    

### Phase B: Analyst Phase

1. Detect micro‑trend direction
    
2. Confirm with:
    
    - liquidity ≥ threshold
        
    - spread ≤ max_spread_allowed
        
    - tape speed increasing
        
3. Produce BUY/SELL/HOLD with confidence
    

### Phase C: Broker Phase

1. Check market state
    
2. For BUY:
    
    - place market order (fastest fill)
        
    - fallback to limit order if spread widens
        
3. For SELL:
    
    - close position quickly
        
4. Apply micro stop-loss
    
5. Log all attempts
    

### Phase D: Report & Verification

1. Build JSON/Markdown report
    
2. Save to /workspace/reports
    
3. Verify readability
    
4. Return final status
    

## 8. Scalping Entry Rules

- Micro‑trend up → BUY
    
- Micro‑trend down → SELL
    
- Spread must be ≤ 0.05%
    
- Liquidity must be above threshold
    
- Tape speed must be increasing
    

## 9. Scalping Exit Rules

- Stop-loss:
    
    - fixed ticks (1–3 ticks)
        
    - or ATR micro (0.1–0.3 ATR)
        
- Take-profit:
    
    - 1–3 ticks
        
    - or fixed % (0.05%–0.30%)
        
- Hard exit if trade exceeds max_trade_duration_seconds
    

## 10. Risk Controls

- Max 0.5% account risk per trade
    
- Max 10 scalps per session
    
- Avoid low‑liquidity periods
    
- Avoid correlated tickers
    
- No overnight holds
    

## 11. Example Scalping Strategy Report

json

```
{
  "status": "success",
  "run_id": "scalp_20260809_094501",
  "started_at": "2026-08-09T09:45:01Z",
  "completed_at": "2026-08-09T09:46:12Z",
  "scalping_window_used": "09:30-11:00",
  "watchlist_used": ["AAPL", "TSLA", "NVDA"],
  "analyst_summary": {
    "signals": [
      {"symbol": "AAPL", "action": "BUY", "confidence": 0.81},
      {"symbol": "TSLA", "action": "SELL", "confidence": 0.72}
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
        "timestamp": "2026-08-09T09:45:31Z"
      }
    ]
  },
  "orders_executed": [
    {
      "symbol": "AAPL",
      "order_id": "xyz111",
      "order_status": "accepted",
      "submitted_at": "2026-08-09T09:45:31Z"
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

Run scalping strategy for watchlist: AAPL, TSLA, NVDA. Use MCP-only execution path. Detect micro‑trend scalping signals. Require at least one Alpaca write success. Persist final report and verify readability. Return status=failed if any hard condition is unmet.

## 14. Minimal Smoke Checklist

1. Fetch micro‑data
    
2. Detect micro‑trend
    
3. Confirm liquidity + spread
    
4. Execute broker decision
    
5. Verify order metadata
    
6. Write & verify report
