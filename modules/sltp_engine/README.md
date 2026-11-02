# Adaptive SL/TP Engine

Research-only stop-loss/take-profit planner:
- Wilder ATR from completed OHLC bars.
- Structural swing low/high with spread/point buffer.
- Selects the farther of the ATR stop and structure stop, then checks maximum ATR distance.
- Applies broker point, tick-size, digits, stops-level, freeze-level, volume min/max/step.
- Calculates size from equity risk budget and broker loss tick value; rounds volume down and rejects if broker minimum would breach budget.
- Computes TP from configurable reward/risk ratio.
- Returns a fail-closed invalid plan if broker distance, structure or minimum lot constraints fail.
- API is authenticated and returns `execution_allowed: false`. It never places or modifies orders.

Limitations: caller must supply current executable bid/ask, completed bars and exact broker symbol metadata. Tick value may vary by price/account currency and must be refreshed from the connected terminal. Slippage, gaps, commissions, swap and liquidity are not guaranteed by this estimate. Not production-ready for live execution.
