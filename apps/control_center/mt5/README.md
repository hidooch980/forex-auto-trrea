# MT5 bridge status

The final broker-specific EA is not implemented in this starter. This directory reserves the integration boundary.

Required production work:
- MQL5 EA with authenticated local bridge or signed signal file.
- Validate signal age, symbol allowlist, spread, margin, stops/freeze levels and volume steps.
- Calculate lots using broker tick value/tick size and account currency.
- Persist daily equity anchor and emergency-stop state across terminal restarts.
- Prevent duplicate orders and log every request/result/retcode.
- Implement SL/TP server-side and verify accepted protection after fill.
- Compile and run MetaTrader Strategy Tester plus broker demo forward test.

No credentials belong in this repository.
