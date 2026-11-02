# Finalization and release gate

**Current classification: research-only development build. Not production-ready for live trading.**

## Implemented and covered by automated tests
- Persistent ERP risk ledger, pipeline, performance memory and specialist cells.
- Cognitive/behavioral risk checks in the research decision path; missing evidence fails closed.
- Authenticated Control Center with roles, CSRF protection, scrypt password hashes, login throttling and emergency-stop latch.
- Market Radar: validated OHLC input, EMA/RSI/ATR analysis, freshness checks, authenticated API and dashboard input/results page.
- Backtest Lab: EMA crossover simulation, signal-at-close/next-open fill model, per-side cost model, trade list and summary metrics; authenticated API and dashboard page.
- Python CI compiles modules and runs module/control-center tests, including Market Radar and Backtest Lab.
- All new research APIs return `execution_allowed: false`.

## Remaining mandatory release blockers
- [ ] Select and connect a licensed/reliable market-data provider; verify completed-bar semantics, symbol mapping, spread, bid/ask, outages and stale/future data.
- [ ] Select and connect a maintained economic-calendar/news provider; verify timestamps, revisions, impact classifications and outage handling.
- [ ] Reconcile closed trades, fees, swaps, partial closes and account currency from trusted broker/MT5 history before using them as learning truth.
- [ ] Implement a broker-specific demo adapter and execution-side risk gate; preview APIs are not execution controls.
- [ ] Make emergency stop durable/shared, audited, and acknowledged by downstream execution components.
- [ ] Validate realistic backtest costs, spread, slippage, swaps, gaps, rollovers, data quality and out-of-sample/walk-forward results.
- [ ] Add alert delivery (email/Telegram/etc.) only after provider selection, user consent and secret provisioning.
- [ ] Complete dependency/security review, CSP hardening, backups/restore, monitoring, load tests and incident procedures.
- [ ] Compile MQL5 in MetaEditor, run Strategy Tester, then extended demo forward testing.
- [ ] Build and verify signed Android release on supported devices.
- [ ] Require explicit operator approval before any live-execution flag can ever be enabled.

## Safety constraints
- No broker credentials, market-data secrets or API keys in the repository.
- No fabricated live prices, headlines, calendar events, trade history or performance figures.
- User-entered candles are caller-supplied data, not independently verified provider data.
- Backtest outputs are historical simulations, not forecasts or guarantees.
- Learning cells are bounded/shadow-only memory, not self-training neural networks.
- Emergency stop currently starts active but is process-local; it is not a broker-side kill switch.
- Keep `live_trading_enabled=False` and `execution_allowed=False`.
