---
name: risk-ftmo-gates
description: Use before approving a proposed trade, changing account settings, evaluating FTMO rules or reviewing drawdown and news restrictions.
---

# Independent risk and FTMO policy gate

1. Resolve account product, phase, account type, platform, currency and broker-server day from the registered account profile.
2. Load the matching rule set from the versioned policy registry. Never infer a rule from a product nickname.
3. Validate equity/balance snapshots, daily reset boundary, closed and floating PnL, fees, swaps, open risk and exposure.
4. Validate current spread, stop distance, volume step, margin and market availability.
5. Validate high-impact calendar data and product-specific news/overnight/weekend restrictions. Missing or stale calendar evidence is a block where the policy requires it.
6. Apply all independent hard caps after agent scoring. An agent cannot vote away a risk violation.
7. Persist rule version, input snapshot, calculation, verdict and human-readable reasons.
8. Default to reject on unknown account metadata, missing data or conflicting sources.

### WRONG
- Use one generic FTMO rule for all products and phases.
- Treat a funded simulated account as a live brokerage account.
- Let model confidence increase a hard risk limit.

### CORRECT
- Resolve account-specific rules and evaluate them deterministically.
- Reconcile partial deals to complete positions before computing performance.

### Checklist
- [ ] Product/phase/account type resolved
- [ ] Correct server-day and equity/balance basis used
- [ ] Calendar and execution data fresh
- [ ] Risk caps and FTMO rules independently passed
- [ ] Full audit trail stored
