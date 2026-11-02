# Finalization and release gate

**Current release classification: tested development scaffold; not production-ready.**

## Implemented and covered by repository tests
- Persistent ERP risk ledger and authenticated ERP API facade.
- Master Brain research decision chain with data/agent validation.
- Persistent data pipeline, idempotency, quarantine and bounded transient retry.
- Closed-trade outcome memory and chronological walk-forward reports.
- Isolated specialist learning cells with minimum sample threshold and shadow-only reliability.
- Observable market-stress scoring and objective trading-behavior proxies.
- Central risk reservation before any possible downstream execution.
- Execution flags remain false throughout the API.

## Mandatory blockers before production or live trading
- [ ] Connect and authenticate a market-data provider; validate symbols, timeframes, bid/ask and completed bars.
- [ ] Connect a maintained economic-calendar/news provider with outage and stale-data tests.
- [ ] Obtain closed trades from a trusted broker/MT5 source and reconcile positions, deals, partial closes, commissions, swaps and account currency before allowing them to update learning memory.
- [ ] Integrate the behavioral guard into a verified execution-side gate, not merely a preview API.
- [ ] Implement broker-specific MT5 order adapter, idempotent order IDs, fill/partial-fill handling, restart recovery and broker reconciliation.
- [ ] Add secrets management, TLS, production authentication/authorization review, audit retention, backups and operational alerting.
- [ ] Compile MQL5 in MetaEditor, run Strategy Tester, then extended demo forward testing.
- [ ] Run independent security review, chronological walk-forward, out-of-sample and failure-injection tests.
- [ ] Require explicit operator approval before enabling any live execution flag.

## Learning safety rules
- Cellular memory stores per-specialist directional outcomes. It is not a trained neural network.
- Reliability is neutral until the configured minimum sample count; shadow multipliers are bounded.
- No automatic live weight updates.
- Market-affect labels describe observable market/strategy stress, not a person's psychological state.
- Extreme market stress forces HOLD in the research decision pipeline.
- A forecast/outcome submitted through the API is not trusted broker truth until a reconciled source is connected.

## Operational environment variables
- `ERP_RISK_LEDGER_DB`
- `ERP_PIPELINE_DB`
- `ERP_PERFORMANCE_DB`
- `ERP_CELLS_DB`
- Or use `ERP_DATA_DIR` as the common data directory.

Do not store credentials or API keys in the repository. Keep live execution disabled until every mandatory blocker is independently verified.
