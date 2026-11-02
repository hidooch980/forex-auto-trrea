# Backtest Lab

Deterministic EMA crossover research simulator for caller-supplied historical OHLC bars.

- Signals are computed on bar close and simulated at the next bar open.
- Round-trip costs are applied as basis points per side.
- Final open exposure is marked to the final close and labelled `end_of_test_mark`.
- Reports trade count, win rate, profit factor, return and trade-level maximum drawdown.
- No live market data, broker connection, funding/borrow model, intrabar stop model or execution guarantee.
- Caller is responsible for data provenance, timezone, corporate actions/rollovers and avoiding survivorship bias.
- `execution_allowed` is always false. This is not a trading signal.

Run tests: `PYTHONPATH=. python -m pytest -q modules/backtest_lab/tests`.
