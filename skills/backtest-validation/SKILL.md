---
name: backtest-validation
description: Use before trusting, ranking, promoting or reporting any trading strategy or model backtest.
---

# Backtest validation gate

1. Freeze strategy hypothesis, universe, parameters, timeframe and evaluation period before running.
2. Use chronological walk-forward folds; purge overlapping labels and embargo adjacent leakage.
3. Model bid/ask execution, variable spread, commissions, swaps, slippage, latency, rejected orders, partial fills and broker stop rules.
4. Compare against simple baselines and report all tried variants, not only the winner.
5. Report trade count, expectancy, profit factor, drawdown, exposure, turnover, average holding time, tail loss and per-symbol/per-regime breakdown.
6. Test parameter sensitivity, alternate periods, regime changes and cost stress (for example 1.5x and 2x estimated costs).
7. Keep a final holdout untouched until model selection is complete. Require shadow/paper operation before any live consideration.
8. A strategy author or LLM agent cannot approve its own result; an independent validator reviews it.

### WRONG
- Optimize on the test set and call it out-of-sample.
- Report gross profit without realistic costs.
- Treat one profitable run as proof of an edge.

### CORRECT
- Report uncertainty, failures, sample size and robustness alongside returns.
- Reject promotion when evidence is insufficient.

### Checklist
- [ ] Data passed quality and point-in-time checks
- [ ] Costs and execution constraints modeled
- [ ] Walk-forward and untouched holdout used
- [ ] Sensitivity and regime analysis completed
- [ ] Independent review and paper/shadow gate passed
