# Market analytics module

This module contains pure, testable calculations used by the Forex AI dashboard.

## Signal performance

`summarize_closed_trades()` accepts records with `trade_id` (optional),
`symbol`, `status` (`closed` or `completed`) and realized `net_profit`.
It excludes open/cancelled trades, rejects duplicate closed trade IDs, and
calculates win rate, average net profit, total net profit, profit factor,
per-symbol rankings and heatmap classifications. Ranking is sorted by average
net profit, with net profit as a tie-breaker.

Only fully closed trade outcomes should be supplied. Partial MT5 exit deals must
not be treated as complete trades; the existing MT5 CSV journal records deal
rows and does not, by itself, prove that a partially exited position is fully
closed. A position-lifecycle reconciler is required before using that journal
as the dashboard's authoritative trade-history provider.

## Fear & Greed

`calculate_fear_greed()` requires four externally measured components:
momentum, market breadth, volatility and safe-haven demand. Each must be a
validated score in [0, 100]. Equal weights are currently transparent baseline
weights, not a calibrated predictive model. The dashboard does not show a
score until all components are supplied.

## Live market map

`build_market_heatmap()` normalizes provider-supplied symbol percentage
changes. It does not fetch prices or infer missing values.

## Current integration status

The dashboard page and authenticated API contract are present, but live market
prices, Fear & Greed component providers, and a reconciled closed-trade history
provider are not connected. Therefore the API returns explicit unavailable
states and empty collections rather than invented statistics. The calculations
are ready for provider integration and covered by unit tests.
