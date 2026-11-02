# News AI feature scaffold

This component converts timestamped, source-attributed news articles into transparent currency sentiment features for downstream ensemble models.

- Scores article title and summary with an explainable baseline lexicon.
- Weights fresh articles by impact and recency.
- Aggregates sentiment by currency and derives a base-minus-quote pair feature.
- Excludes undated and stale articles.

## Important boundaries

This is not a live news feed and not a trained financial-language model. A separately configured provider adapter, source validation, duplicate detection, language-aware NLP, and chronological model validation are required before production. Do not treat sentiment as a standalone trading signal. Existing economic-calendar blackout guards remain independent and take precedence around high-impact events.


## Four-language editorial news contract

`news_schema.py` defines a structured article with localized `title`,
`summary` and `analysis` fields for Persian (`fa`), English (`en`),
Arabic (`ar`) and Turkish (`tr`). Each article also carries source, source
URL, publication time, category, affected currencies, impact and sentiment.
If a requested translation is unavailable, the view explicitly reports the
fallback locale; financial news is never silently machine-translated.

The transparent sentiment lexicon now includes baseline terms in all four
languages. It is still a small explainable lexicon, not a trained multilingual
financial NLP model. Negation, context, sarcasm, source reliability and
cross-language calibration remain limitations.

No live news provider is configured by this change. The article contract and
dashboard news experience are foundations only; do not display sample records
as live market news.
