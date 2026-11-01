"""Explainable news sentiment features; no network access or order execution."""
from datetime import datetime, timezone
import re

POSITIVE = {"beats", "beat", "growth", "surge", "rises", "rise", "strong", "hawkish", "upgrade", "optimistic", "recovery", "profit"}
NEGATIVE = {"misses", "miss", "decline", "falls", "fall", "weak", "dovish", "downgrade", "recession", "crisis", "inflation", "cuts", "cut", "risk", "loss"}
CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "XAU"}


def score_article(title, summary=""):
    """Transparent baseline score in [-1, 1], not a trained NLP model."""
    words = re.findall(r"[a-z']+", f"{title} {summary}".lower())
    pos = sum(word in POSITIVE for word in words)
    neg = sum(word in NEGATIVE for word in words)
    return 0.0 if pos + neg == 0 else (pos - neg) / (pos + neg)


def analyze_news(articles, now=None, max_age_hours=24):
    """Aggregate articles: title, summary, currencies, published_at, impact, source."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    totals, weights = {}, {}
    used = stale = 0
    for item in articles:
        published = item.get("published_at")
        if not isinstance(published, datetime):
            stale += 1
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        age = (now - published.astimezone(timezone.utc)).total_seconds() / 3600
        if age < -1 or age > max_age_hours:
            stale += 1
            continue
        currencies = {str(c).upper() for c in item.get("currencies", [])} & CURRENCIES
        if not currencies:
            continue
        impact = str(item.get("impact", "medium")).lower()
        impact_weight = {"high": 2.0, "medium": 1.0, "low": 0.5}.get(impact, 1.0)
        weight = impact_weight * max(0.1, 1.0 - max(0.0, age) / max_age_hours)
        score = score_article(item.get("title", ""), item.get("summary", ""))
        used += 1
        for currency in currencies:
            totals[currency] = totals.get(currency, 0.0) + score * weight
            weights[currency] = weights.get(currency, 0.0) + weight
    values = {c: round(totals[c] / weights[c], 4) for c in sorted(totals) if weights[c]}
    return {"sentiment_by_currency": values, "articles_used": used,
            "articles_stale_or_undated": stale, "available": bool(values),
            "as_of": now.isoformat(),
            "disclaimer": "Lexicon baseline only; validate sources and model quality."}


def pair_sentiment(result, symbol):
    """Return base-minus-quote sentiment; XAUUSD treats gold as base."""
    symbol = symbol.upper()
    if len(symbol) < 6:
        return 0.0
    base = "XAU" if symbol.startswith("XAU") else symbol[:3]
    quote = symbol[3:6]
    values = result.get("sentiment_by_currency", {})
    return round(float(values.get(base, 0.0)) - float(values.get(quote, 0.0)), 4)
