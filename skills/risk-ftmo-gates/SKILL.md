---
name: risk-ftmo-gates
description: Use before approving a proposed trade, changing account settings, evaluating FTMO rules or reviewing drawdown and news restrictions.
---

# Independent risk, behavior and FTMO policy gate

1. Resolve account product, phase, account type, platform, currency and broker-server day from the registered account profile.
2. Load the matching rule set from the versioned policy registry. Never infer a rule from a product nickname.
3. Validate equity/balance snapshots, daily reset boundary, closed and floating PnL, fees, swaps, open risk and exposure.
4. Validate current spread, stop distance, volume step, margin and market availability.
5. Validate high-impact calendar data and product-specific news/overnight/weekend restrictions. Missing or stale calendar evidence is a block where the policy requires it.
6. Apply all independent hard caps after agent scoring. An agent cannot vote away a risk violation.
7. Monitor objective behavior proxies: trade frequency, consecutive losses, time since last loss, risk/volume increase after a loss, and stale/late signals. Do not claim to read a trader's actual emotions.
8. Enforce cooldown after losses and block revenge-pattern, overtrading and late-entry flags. Never increase size to recover a loss.
9. Persist rule version, input snapshot, calculation, verdict and human-readable reasons.
10. Default to reject on unknown account metadata, missing data or conflicting sources.

### WRONG
- Use one generic FTMO rule for all products and phases.
- Treat a funded simulated account as a live brokerage account.
- Let model confidence increase a hard risk limit.
- Diagnose fear, greed or anger from price data alone.
- Use martingale, loss-chasing or automatic size escalation.

### CORRECT
- Resolve account-specific rules and evaluate them deterministically.
- Reconcile partial deals to complete positions before computing performance.
- Treat revenge trading, FOMO and overtrading as cautious pattern labels, not psychological diagnoses.
- Require a human-reviewed unlock after a hard daily/weekly loss lock.

### Checklist
- [ ] Product/phase/account type resolved
- [ ] Correct server-day and equity/balance basis used
- [ ] Calendar and execution data fresh
- [ ] Risk caps and FTMO rules independently passed
- [ ] Behavioral metrics available and cooldown clear
- [ ] Full audit trail stored
