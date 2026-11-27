# Investment Analysis Cycle

Use this skill to run a full investment cycle that orchestrates both:
- `investment-analyst` (market analysis and watchlist scoring)
- `investment-broker` (BUY/SELL/HOLD decision + execution path)

This skill is the top-level coordinator and must never report success without at least one real Alpaca order execution.

## Inputs
- Watchlist symbols, for example: `AAPL, GOOGL, AMZN, NVDA, MRVL, SPCX`
- Risk mode: `paper` (default) or `live`
- Optional confidence threshold for BUY decisions
- Optional `base_notional_per_trade` and `max_notional_per_symbol` for confidence-based sizing

## Core Flow
1. Run analyst phase:
   - collect watchlist and analysis data
   - produce per-symbol signal (BUY/SELL/HOLD) and confidence
2. Run broker phase:
   - validate account and market state
   - apply broker rules, guardrails, and retry policy from `investment-broker`
   - choose final action per symbol
3. Build cycle report with:
   - analyst outputs
   - broker decisions
   - confidence-based sizing rationale and final qty per executed symbol
   - execution status and verified Alpaca order metadata

## Blueprint Contract
Use these blueprint references as the source of truth for decisions and report layout:
- `/workspace/investment-analyst-api/INVESTMENT_ANALYST_BLUEPRINT.md`
- `/workspace/docs/INVESTMENT_ANALYST_CONFIDENCE_POLITYCS.md`
- `/workspace/docs/DEFINITIVE_SKILLS_MANIFEST.md`

## Real-Execution Requirement
If MCP tools or execution endpoints are unavailable, the cycle must fail:
1. Keep analyst outputs if available.
2. Exhaust broker retry policy first (do not fail on first transient error).
3. If broker execution is still unavailable, return `status=failed`.
4. Never emit `execution_mode=simulation` as a successful cycle outcome.
5. Never claim real order execution unless confirmed by Alpaca order state.

### Allowed execution path
The only allowed execution path for order placement is via `alpaca-mcp` write tools invoked from `investment-broker`.

Forbidden substitutes:
- `alpaca-cli`
- `curl` or direct raw HTTP examples to Alpaca
- ad hoc Python or shell snippets for order placement
- narrative-only or hypothetical descriptions of a trade

If the agent cannot access the required MCP write tools, it must return `status=failed` instead of proposing an alternative execution method.

## Report Output
Write the cycle result to `/workspace/reports` as JSON or Markdown.
Recommended filename pattern:
- `investment_analysis_cycle_YYYYMMDD_HHMMSS.json`
- `investment_analysis_cycle_YYYYMMDD_HHMMSS.md`

### Report persistence verification (required)
After write attempts, verify both files exist and are readable.
Minimum checks:
1. list `/workspace/reports` and confirm both filenames
2. read first lines/bytes from each file
3. include `report_write_verified=true|false` in final output

If verification fails:
1. retry write up to 3 times with backoff (1s, 2s)
2. try both absolute and relative paths
3. return `report_write_verified=false` and do not claim successful persistence

### Real order verification (required)
Before final success, include all of the following from Alpaca:
1. `order_id`
2. `order_status`
3. `symbol`
4. `submitted_at`
5. `final_qty`

Before final success, also include:
1. `confidence`
2. `target_notional`
3. `sizing_rationale`

If any field is missing, return `status=failed`.

## Minimal Run Checklist
1. Read watchlist.
2. Run analyst step for all symbols.
3. Run broker decision step with retry policy.
4. Require at least one real Alpaca write tool success (`order_place_market` or `order_place_limit`).
5. Require confidence-based sizing for executed BUY/SELL actions.
6. Save report to `/workspace/reports`.
7. Verify report files exist and are readable before final success.
8. Verify Alpaca order metadata exists (`order_id`, `order_status`, `symbol`, `submitted_at`, `final_qty`) before final success.