# Service stability and integration status

Last audited: 2026-11-02.

## Verified in repository / CI
- Python compile and automated tests for the current repository modules.
- Authentication uses scrypt password hashes, opaque server-side sessions, HttpOnly/SameSite cookies, CSRF checks and persistent login throttling.
- Control Center exposes authenticated roles and a process-local emergency-stop latch.
- Market Radar API and dashboard page accept caller-supplied completed OHLCV bars and calculate EMA/RSI/ATR; stale/future/malformed input is rejected.
- Backtest Lab API and dashboard page run a deterministic EMA crossover simulation with close-to-next-open timing and configurable per-side transaction costs.
- Market Radar and Backtest Lab outputs are research-only and never authorize execution.

## Not verified / not connected
- Live price feed, broker account/positions, MT5 order adapter and execution reconciliation.
- Trusted economic calendar/news provider and push notification delivery.
- Broker-reconciled closed-trade history for learning.
- Persistent shared emergency-stop state and broker/EA acknowledgement.
- Production CSP hardening, independent penetration test, disaster recovery and load test.
- MQL5 MetaEditor compilation, extended demo forward testing and signed Android release.

## Deployment status
The existing VPS deployment is separate from this GitHub feature branch. Changes on the branch do not automatically update the running server. Deploy only after CI passes and an operator-approved maintenance window; retain backups and confirm health endpoints afterward.

## Safety
Keep all live trading and order execution disabled. Caller-supplied portfolio snapshots and historical candles are not trusted live account or market truth. Do not publish the system as production-ready until all missing integrations and release gates above are independently verified.
