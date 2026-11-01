# Smart TP/SL module — Forex AI Hybrid Scalper

Adaptive initial stop/target planning plus partial take-profit, break-even and ATR trailing logic.
This is a broker-neutral risk-management module. It does **not** connect to MT5 or send/modify orders.

## Included
- Adaptive initial SL using ATR and recent swing structure.
- Adaptive TP based on market regime, bounded by configured R-multiples.
- Partial close request at +1R (default 50%).
- Break-even stop after +1R, including configurable cost buffer.
- ATR trailing after +1.2R; stop can tighten only, never widen.
- Tests for long/short symmetry and stop monotonicity.

## Example
```python
from src.smart_tpsl import ExitConfig, plan_trade, manage_open_trade

cfg = ExitConfig()
plan = plan_trade(
    symbol="EURUSD", side="BUY", entry=1.0850, atr=0.0008,
    swing_low=1.0837, swing_high=1.0870, regime="TREND",
    spread=0.0001, config=cfg
)
print(plan)

state = {"partial_done": False, "initial_risk": plan["risk_distance"]}
action = manage_open_trade(
    side="BUY", entry=1.0850, current_price=1.0858,
    current_atr=0.0007, current_sl=plan["sl"], state=state,
    config=cfg, cost_buffer=0.0001
)
print(action)
```

## Rules
- `BUY` uses bid-side executable price for exit checks; `SELL` uses ask-side executable price. The caller must pass the correct side-aware price.
- `swing_low` / `swing_high` must be calculated from completed bars only.
- `spread` and `cost_buffer` must be in the same price units as the symbol.
- Lot sizing is intentionally separate: calculate volume from account equity, risk fraction, tick value/size and stop distance using broker symbol metadata.
- Partial close volume must be rounded to broker volume step and checked against min volume by the MT5 execution adapter.
- Do not widen SL. Do not remove server-side SL.
- If market data is stale, spread/news guard fails, or broker stop constraints fail, block the trade.
- Test on historical bid/ask data, then demo. No profitability claim is made.

## Initial defaults (research starting points, not optimized)
- FX: ATR stop multiplier 1.5; gold: 2.0.
- Trend TP: 2.2R; range TP: 1.3R; high volatility TP: 1.5R.
- Partial: 50% at +1R.
- Break-even: after +1R plus cost buffer.
- ATR trailing: starts at +1.2R; distance 1.2 ATR.
