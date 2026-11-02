# Market Radar (research-only)

Deterministic, execution-neutral OHLC analysis: EMA(9), EMA(21), Wilder RSI(14), ATR(14), ATR percentage, trend/momentum labels and a conservative research bias. This is a transparent technical baseline, not a predictive model or proven strategy.

## API

Authenticated `POST /api/market-radar/analyze` (admin, trader, analyst, viewer). Caller supplies 30–1000 timezone-aware OHLCV bars in strictly increasing timestamp order. Prices must be finite and positive, OHLC geometry valid, and volume nonnegative. Latest bar defaults to a maximum age of 15 minutes and may not be materially future-dated. Invalid or stale input returns HTTP 422.

Response includes indicator values, reasons and `execution_allowed: false`. No data provider is connected; caller-supplied candles are not verified market truth. Caller must supply completed bars only. This endpoint never places, modifies or closes orders.

## Limits

EMA/RSI/ATR describe past price/volatility, not future outcomes. ATR is not a stop-loss recommendation. Bias is suppressed when confirmation is weak or ATR percentage is high. This module does not validate spread, slippage, liquidity, session, news, contract specifications or executable prices. Existing independent risk gates remain mandatory. Backtests must include realistic costs and chronological out-of-sample evaluation.

Run from repository root: `PYTHONPATH=. python -m pytest -q modules/market_radar/tests`.
Live trading and order execution remain disabled.
