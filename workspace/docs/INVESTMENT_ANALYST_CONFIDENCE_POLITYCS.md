# AMZN Investment Analyst Confidence Policy
## Parameters
buy_confidence_threshold = 0.60
base_notional_per_trade = 25
max_notional_per_symbol = 100
min_trade_qty = 0.01
qty_step = 0.01

## Sizing Formulas
1. target_notional = min(base_notional_per_trade + max(0, confidence - buy_confidence_threshold) * 100, max_notional_per_symbol).
2. final_qty = max(min_trade_qty, floor((target_notional / current_price) / qty_step) * qty_step).

## Calculation Assumptions for this Run
Confidence: 0.80 (Assumed high confidence, > 0.60 threshold)
Current Price Used: $250.78 (Ask price from quote)

Target Notional Calculation: min(25 + max(0, 0.8 - 0.6) * 100, 100) = 45.0
Final Qty Calculation: max(0.01, floor((45.0 / 250.78) / 0.01) * 0.01) ≈ 0.17