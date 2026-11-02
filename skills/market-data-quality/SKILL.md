---
name: market-data-quality
description: Use before feature engineering, market analysis, signal generation or backtesting when validating MT5 or external OHLC/tick data.
---

# Market data quality gate

1. Identify provider, broker server, account environment, symbol, timeframe, retrieval time and timezone.
2. Preserve the raw response. Never silently sort, deduplicate, forward-fill, interpolate or rewrite provider bars.
3. Validate required OHLC fields, finite positive prices, OHLC relationships, timestamp timezone, chronological order, duplicate timestamps, missing intervals, non-negative spread and volume.
4. Measure freshness against UTC retrieval time and timeframe-specific policy. Distinguish a forming candle from a completed candle.
5. Compare bid/ask with last tick and symbol point/digits. A zero or missing quote is unavailable, not a valid price.
6. Report gaps separately from session closures; use a market calendar before classifying weekend/holiday gaps as feed outages.
7. Emit a structured quality report with errors, warnings, latest timestamp, age, provider and raw snapshot identifier.
8. If a critical check fails, mark the snapshot invalid and stop downstream agents.

### WRONG
- Assume the latest returned bar is closed.
- Fill a missing candle and train on the fabricated value.
- Treat a stale tick as live because the terminal is connected.

### CORRECT
- Fetch completed bars separately from the forming bar.
- Keep raw and normalized data side by side with provenance.
- Fail closed when freshness or timestamp semantics are unknown.

### Checklist
- [ ] UTC and source timestamps recorded
- [ ] Symbol mapping verified against broker metadata
- [ ] No duplicates, malformed OHLC or out-of-order bars
- [ ] Freshness and session-aware gap checks passed
- [ ] Spread and tick quality checked
- [ ] Invalid snapshots cannot reach Master Brain
