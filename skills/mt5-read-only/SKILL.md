---
name: mt5-read-only
description: Use when integrating MetaTrader 5 terminal data, symbols, ticks, bars, account state or broker execution constraints.
---

# MetaTrader 5 read-only workflow

1. Confirm terminal path, terminal build, connection state, broker server, account currency and demo/live environment without exposing credentials.
2. Discover instruments with `symbols_get`; never assume EURUSD/XAUUSD names or suffixes. Verify `symbol_info`, trade mode, digits, point, tick size/value, contract size, volume min/max/step and stops/freeze levels.
3. Retrieve bid/ask ticks and timestamp. Reject missing, crossed, zero or stale quotes.
4. Retrieve bars with `copy_rates_from_pos`. MT5 position zero is the current bar; use position one for completed-bar research and fetch the forming bar separately.
5. Convert MT5 epoch timestamps to timezone-aware UTC and retain broker/server context.
6. Apply `market-data-quality` before features or agent analysis.
7. Record `last_error()` for failed API calls and distinguish empty history from terminal disconnection.
8. Use `order_calc_margin`, `order_calc_profit` and `order_check` only in a separately authorized pre-trade simulation. Do not call `order_send` from research agents.

### WRONG
- Guess symbol suffixes, pip value or volume precision.
- Treat terminal initialization as proof that prices are fresh.
- Place orders from an analysis agent.

### CORRECT
- Discover broker-specific contract metadata and validate each instrument.
- Keep the adapter read-only and isolate future execution behind independent policy gates.

### Checklist
- [ ] Terminal connection and server recorded
- [ ] Symbol metadata and quote timestamp validated
- [ ] Closed bars separated from live candle
- [ ] Read-only adapter tested with a demo terminal
- [ ] No credentials or unrestricted execution tools exposed
