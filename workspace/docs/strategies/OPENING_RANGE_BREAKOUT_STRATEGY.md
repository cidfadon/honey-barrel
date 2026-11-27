1. Purpose
Define a repeatable, rule‑based intraday scalping strategy that combines:

Opening Range Breakout (ORB)

Micro‑Scalping Spread Capture

VWAP Momentum Confirmation

The goal is to maximize high‑probability entries, increase average spread, and avoid low‑liquidity traps, enabling a realistic path toward ≈10% daily account growth under optimal market conditions.

2. Source of Truth
This strategy integrates:

ORB breakout logic

VWAP bounce confirmation

Micro‑trend tape‑speed analysis

Liquidity + spread filters

Your MCP investment‑analyst / broker / analysis‑cycle stack

If conflicts arise, follow MCP‑only rules.

3. Strategy Definition (Upgraded)
What is ORB + Scalping Hybrid?
A combined strategy that:

Uses ORB to identify high‑volatility breakout windows

Uses scalping logic to capture micro‑spreads inside those windows

Uses VWAP + tape speed to confirm momentum strength

Uses strict risk controls to maintain high win‑rate

This hybrid approach increases average trade quality and reduces noise.

4. Roles & Boundaries (Unchanged but Optimized)
4.1 investment‑analyst
Responsibilities:

Detect ORB breakout

Detect micro‑trend direction

Measure tape speed

Confirm spread ≥ $0.05 minimum

Produce BUY/SELL/HOLD signals with confidence scoring

Primary MCP tools:

analyze_stock

analyze_watchlist

data_fetch

4.2 investment‑broker
Responsibilities:

Execute trades only when spread + momentum align

Enforce upgraded risk rules

Apply micro‑stop‑loss

Apply time‑based exits

Log all executions

Primary MCP tools:

order_place_market

order_place_limit

position_close

4.3 investment‑analysis‑cycle
Responsibilities:

Orchestrate detection → execution → reporting

Enforce upgraded success criteria

Maintain daily performance logs

5. Inputs (Upgraded)
Required:

watchlist symbols

opening_range_window: 5 | 15 | 30 minutes

New required inputs:

minimum_spread: $0.05

tape_speed_threshold: medium or high

liquidity_threshold: average or above

Optional:

risk_mode: paper | live

breakout_confirmation: 1–3 candles

stop_loss_method: ATR | fixed ticks | time‑stop

max_hold_time: 10–20 seconds

6. Output Contract
Same as your original, but now includes:

spread_quality_score

tape_speed_score

liquidity_score

micro‑trend direction

scalping‑cycle count

average spread captured

7. Orchestration Flow (Upgraded)
Phase A: Intake & Validation
Validate watchlist

Normalize symbols

Compute opening range

Fetch volume, ATR, VWAP

Compute spread + tape speed + liquidity

Phase B: Analyst Phase
Detect ORB breakout

Confirm with:

volume spike ≥ 150%

spread ≥ $0.05

tape speed increasing

micro‑trend alignment

VWAP confirmation

Produce BUY/SELL/HOLD with confidence

Reject low‑quality setups

Phase C: Broker Phase
Check market state

For BUY (long ORB):

place market order

fallback to limit

For SELL (short ORB):

verify borrow availability

execute short

Apply upgraded exits:

take‑profit at 1.5×–3× risk

micro‑stop‑loss (1–2 ticks)

time‑stop (10–20 seconds)

Log all attempts

Phase D: Report & Verification
Same as original, but now includes:

spread analysis

tape speed analysis

micro‑trend direction

scalping cycle performance

8. ORB Entry Rules (Upgraded)
Breakout above Opening Range High → BUY

Breakout below Opening Range Low → SELL

Volume ≥ 150% of average

Spread ≥ $0.05

Tape speed increasing

1–3 candle confirmation

Liquidity ≥ average

Reject entries during dead zones

9. ORB Exit Rules (Upgraded)
Stop‑loss:
1–2 ticks

spread flip

time‑stop 20 seconds

midpoint of opening range

Take‑profit:
1.5×–3× risk

optional VWAP trailing stop

10. Risk Controls (Upgraded)
Max 1–2% account risk per trade

Max 2 ORB attempts per day

Max 20–40 scalping cycles per ORB window

Avoid correlated tickers

Avoid low‑liquidity periods

Avoid spreads < $0.05

11. Daily Performance Target
To target ≈10% per day, the strategy relies on:

high‑quality ORB windows

strict spread filtering

tape‑speed confirmation

micro‑trend alignment

disciplined exits

avoiding low‑probability trades

This is not a guarantee, only a structural optimization.

12. Failure Semantics
Same as original.

13. Prompt Template (Upgraded)
Run ORB + Scalping Hybrid Strategy for watchlist: AAPL, TSLA, NVDA.
Use MCP‑only execution path.
Detect breakout above/below opening range.
Require spread ≥ $0.05 and tape speed ≥ threshold.
Require at least one Alpaca write success.
Persist final report and verify readability.
Return status=failed if any hard condition is unmet.

14. Minimal Smoke Checklist (Upgraded)
Compute opening range

Detect breakout

Confirm with volume

Confirm spread ≥ $0.05

Confirm tape speed

Confirm liquidity

Execute scalping cycles

Apply micro‑stop‑loss

Apply time‑stop

Produce final report