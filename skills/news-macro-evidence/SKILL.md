---
name: news-macro-evidence
description: Use when gathering, scoring or connecting news, central-bank statements, economic releases, calendars or cross-asset context to forex and gold.
---

# News and macro evidence workflow

1. Record publisher, canonical URL, article/release ID, publication time, update time, ingestion time and language.
2. Deduplicate syndicated copies and revisions; preserve original and corrected versions.
3. Extract named entities, affected currencies, instrument scope, event category and impact with explicit confidence.
4. Separate reported fact, source interpretation and agent inference. Quote no unsupported numbers.
5. For economic releases, retain actual, consensus, prior and revised prior values with units and release timestamp.
6. Compare surprise to consensus only when units and release vintages match. Do not infer direction from a headline alone.
7. Aggregate sentiment by currency and time decay, but show source quality and conflicting evidence.
8. Calendar outages, stale timestamps and ambiguous event windows block the relevant risk-sensitive decision.

### WRONG
- Treat a lexicon score as trained financial NLP.
- Map every negative headline to a sell signal.
- Confuse the event period with publication time.

### CORRECT
- Keep source evidence and uncertainty attached to every macro/news view.
- Explain why a release affects the base currency, quote currency or gold.

### Checklist
- [ ] Primary source or trusted publisher identified
- [ ] Publication and ingestion timestamps available
- [ ] Duplicates/revisions resolved
- [ ] Actual/consensus/prior units aligned
- [ ] Currency mapping and uncertainty recorded
