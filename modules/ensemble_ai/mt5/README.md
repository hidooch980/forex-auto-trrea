# MT5 integration boundary

The Python adapter in `src/mt5_readonly.py` is read-only. It can initialize MT5 and retrieve rates/ticks.
It deliberately refuses order placement. Before any execution module is written, require:
- demo account only and explicit account/symbol allowlist
- fresh bid/ask tick and max spread check
- broker symbol metadata: volume min/max/step, stops level, filling mode
- server-side SL mandatory; validate stop distance and lot rounding
- risk sizing from equity and tick value, including contract-size differences for XAUUSD
- daily loss lock, max open positions, duplicate-signal/idempotency key
- news calendar fail-closed and emergency stop persisted outside process memory
- audit log for every signal, rejection and order response
- integration tests against broker demo and manual approval before enabling live mode
