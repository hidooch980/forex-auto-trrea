---
name: point-in-time-research
description: Use for market datasets, macro/news joins, feature engineering, ML labels, training or any historical performance claim.
---

# Point-in-time research discipline

1. Define decision timestamp, prediction horizon, universe and target before querying data.
2. Each observation needs both event/effective time and availability/ingestion time. A value is usable only if it was public and received before the decision timestamp.
3. Keep original releases and revisions separately. Never replace historical values with today's revised macro data.
4. Build features using backward-looking windows only. Shift labels forward; exclude rows whose full label horizon is not observable.
5. Split chronologically. Fit imputers, scalers, feature selection and calibration only on each training fold.
6. Purge overlapping label horizons and apply embargo where observations share information.
7. Record dataset hash, provider, retrieval time, transformations, feature schema and code revision.

### WRONG
- Random train/test split for time series.
- Join macro releases by period label rather than publication time.
- Normalize the entire dataset before splitting.

### CORRECT
- Use point-in-time joins and fold-local preprocessing.
- Report a separate untouched final holdout.

### Checklist
- [ ] Event time and availability time retained
- [ ] Revisions and survivorship handled
- [ ] No future-looking features or labels in inputs
- [ ] Chronological splits and fold-local transforms
- [ ] Dataset and code provenance recorded
