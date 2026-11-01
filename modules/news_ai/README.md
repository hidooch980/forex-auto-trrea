# News AI feature scaffold

This component converts timestamped, source-attributed news articles into transparent currency sentiment features for downstream ensemble models.

- Scores article title and summary with an explainable baseline lexicon.
- Weights fresh articles by impact and recency.
- Aggregates sentiment by currency and derives a base-minus-quote pair feature.
- Excludes undated and stale articles.

## Important boundaries

This is not a live news feed and not a trained financial-language model. A separately configured provider adapter, source validation, duplicate detection, language-aware NLP, and chronological model validation are required before production. Do not treat sentiment as a standalone trading signal. Existing economic-calendar blackout guards remain independent and take precedence around high-impact events.
