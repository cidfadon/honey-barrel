## 1. Purpose

Define a **unified trading strategy framework** that allows the investment stack to run **multiple intraday strategies** in a single orchestrated cycle:

- **Opening Range Breakout**
    
- **VWAP Bounce**
    
- **Scalping**
    
- **Momentum Breakout**
    

This blueprint enables dynamic strategy selection, parallel signal generation, and consolidated broker execution.

## 2. Source Of Truth

Use this blueprint together with:

- /workspace/docs/DEFINITIVE_SKILLS_MANIFEST.md
    
- Individual strategy blueprints (ORB, VWAP, Scalping, Momentum)
    
- MCP‑only execution rules
    

If conflicts arise, MCP rules override.

## 3. Strategy Definitions

### 3.1 ORB (Opening Range Breakout)

Captures volatility when price breaks above/below the opening range.

### 3.2 VWAP Bounce

Mean‑reversion or trend‑continuation trades around VWAP.

### 3.3 Scalping

High‑frequency micro‑trend trades targeting small moves.

### 3.4 Momentum Breakout

Continuation trades when price accelerates with volume and trend alignment.

## 4. Roles And Boundaries

### 4.1 investment-analyst

Responsibility:

- run **all strategies** in parallel
    
- generate per‑strategy signals
    
- merge signals into a unified recommendation
    

Primary MCP tools:

- **analyze_watchlist**
    
- **analyze_stock**
    
- **data_fetch**
    

### 4.2 investment-broker

Responsibility:

- map merged signals to BUY/SELL/HOLD
    
- execute trades using Alpaca MCP tools
    
- enforce risk rules per strategy
    

Primary MCP tools:

- **order_place_market**
    
- **order_place_limit**
    
- **position_close**
    

### 4.3 investment-analysis-cycle

Responsibility:

- orchestrate multi‑strategy analysis → merge → execution → reporting
    
- enforce hard success criteria
    

## 5. Inputs

Required:

- watchlist symbols
    
- enabled_strategies: array of strategy names
    

Optional:

- per‑strategy configuration
    
- risk_mode
    
- confidence_threshold
    
- max_symbols_per_run
    

## 6. Output Contract

Returns:

- status
    
- run_id
    
- timestamps
    
- enabled_strategies_used
    
- analyst_summary (merged)
    
- broker_summary
    
- orders_executed
    
- report_write_verified
    
- failure_reasons
    

## 7. Orchestration Flow (Multi‑Strategy)

### Phase A: Intake & Validation

1. Validate watchlist
    
2. Normalize symbols
    
3. Load enabled strategies
    
4. Fetch required data per strategy
    

### Phase B: Analyst Phase

For each symbol:

1. Run ORB detection
    
2. Run VWAP bounce/rejection detection
    
3. Run scalping micro‑trend detection
    
4. Run momentum breakout detection
    
5. Merge signals using:
    
    - confidence weighting
        
    - strategy priority
        
    - risk mode
        
6. Produce unified BUY/SELL/HOLD
    

### Phase C: Broker Phase

1. Check market state
    
2. For BUY:
    
    - execute market order
        
    - fallback to limit order
        
3. For SELL:
    
    - close/reduce position
        
4. Apply per‑strategy risk rules
    
5. Log all attempts
    

### Phase D: Report & Verification

1. Build JSON/Markdown report
    
2. Save to /workspace/reports
    
3. Verify readability
    
4. Return final status
    

## 8. Strategy Merge Logic

### Priority (default):

1. Momentum Breakout
    
2. ORB
    
3. VWAP Bounce
    
4. Scalping
    

### Merge Rules

- If ≥2 strategies agree → use majority action
    
- If conflict:
    
    - use highest‑priority strategy
        
- Confidence = weighted average
    
- HOLD overrides BUY/SELL only if confidence < threshold
    

## 9. Risk Controls

- Max 1% account risk per trade
    
- Max 5 trades per cycle
    
- Strategy‑specific risk rules still apply
    
- Avoid correlated tickers
    
- No trades during major news releases
    

## 10. Example Multi‑Strategy Report

json

```
{
  "status": "success",
  "run_id": "multi_20260809_111501",
  "started_at": "2026-08-09T11:15:01Z",
  "completed_at": "2026-08-09T11:17:40Z",
  "enabled_strategies_used": ["ORB", "VWAP", "Scalping", "Momentum"],
  "watchlist_used": ["AAPL", "TSLA", "NVDA"],
  "analyst_summary": {
    "signals": [
      {
        "symbol": "AAPL",
        "merged_action": "BUY",
        "confidence": 0.86,
        "strategy_breakdown": {
          "ORB": "BUY",
          "VWAP": "BUY",
          "Scalping": "HOLD",
          "Momentum": "BUY"
        }
      }
    ]
  },
  "broker_summary": {
    "executed": 1,
    "attempt_logs": [
      {
        "tool_name": "order_place_market",
        "attempt": 1,
        "max_attempts": 3,
        "error_class": "retryable",
        "result": "success",
        "timestamp": "2026-08-09T11:16:01Z"
      }
    ]
  },
  "orders_executed": [
    {
      "symbol": "AAPL",
      "order_id": "multi111",
      "order_status": "accepted",
      "submitted_at": "2026-08-09T11:16:01Z"
    }
  ],
  "report_write_verified": true,
  "failure_reasons": []
}
```

## 11. Failure Semantics

Same as main blueprint:

- no successful write order
    
- missing metadata
    
- report unreadable
    
- MCP substitution violations
    

## 12. Prompt Template

Run multi‑strategy cycle for watchlist: AAPL, TSLA, NVDA. Enable ORB, VWAP, Scalping, Momentum. Use MCP-only execution path. Merge strategy signals. Require at least one Alpaca write success. Persist final report and verify readability. Return status=failed if any hard condition is unmet.

## 13. Minimal Smoke Checklist

1. Run all strategies
    
2. Merge signals
    
3. Execute broker decision
    
4. Verify order metadata
    
5. Write & verify report
    
