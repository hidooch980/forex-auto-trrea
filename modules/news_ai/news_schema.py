"""Localized market-news article contract.

Content must be translated/reviewed by an editor or trusted provider. This
module deliberately does not machine-translate financial claims.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

SUPPORTED_LOCALES = ("fa", "en", "ar", "tr")
REQUIRED_LOCALIZED_FIELDS = ("title", "summary", "analysis")


def _localized(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a locale-to-text object")
    result: dict[str, str] = {}
    for locale, text in value.items():
        if locale not in SUPPORTED_LOCALES:
            raise ValueError(f"unsupported locale in {field}: {locale}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{field}.{locale} must be non-empty text")
        result[locale] = text.strip()
    if "fa" not in result and "en" not in result:
        raise ValueError(f"{field} must include Persian or English source text")
    return result


def validate_news_article(article: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one provider/editor-supplied article."""
    if not isinstance(article, dict):
        raise ValueError("article must be an object")
    article_id = str(article.get("id", "")).strip()
    source = str(article.get("source", "")).strip()
    url = str(article.get("url", "")).strip()
    if not article_id or not source or not url.startswith(("https://", "http://")):
        raise ValueError("article requires id, source and an http(s) url")
    published_at = article.get("published_at")
    if not isinstance(published_at, datetime):
        raise ValueError("published_at must be a datetime")
    impact = str(article.get("impact", "medium")).lower()
    if impact not in {"high", "medium", "low"}:
        raise ValueError("impact must be high, medium or low")
    category = str(article.get("category", "markets")).strip().lower()
    sentiment = str(article.get("sentiment", "neutral")).lower()
    if sentiment not in {"positive", "neutral", "negative"}:
        raise ValueError("sentiment must be positive, neutral or negative")
    localized = {
        field: _localized(article.get(field), field)
        for field in REQUIRED_LOCALIZED_FIELDS
    }
    available = sorted(set.intersection(*(set(v) for v in localized.values())))
    return {
        "id": article_id,
        "source": source,
        "url": url,
        "published_at": published_at,
        "category": category,
        "impact": impact,
        "sentiment": sentiment,
        "currencies": sorted({str(x).upper() for x in article.get("currencies", [])}),
        "localized": localized,
        "available_locales": available,
    }


def article_for_locale(article: dict[str, Any], locale: str) -> dict[str, Any]:
    """Return one locale view, with explicit fallback metadata (never auto-translate)."""
    locale = locale if locale in SUPPORTED_LOCALES else "fa"
    normalized = validate_news_article(article) if "localized" not in article else article
    content = normalized["localized"]
    selected = locale
    if not all(locale in content[field] for field in REQUIRED_LOCALIZED_FIELDS):
        selected = "fa" if all("fa" in content[field] for field in REQUIRED_LOCALIZED_FIELDS) else "en"
    return {
        **{key: value for key, value in normalized.items() if key != "localized"},
        **{field: content[field][selected] for field in REQUIRED_LOCALIZED_FIELDS},
        "requested_locale": locale,
        "content_locale": selected,
        "translation_fallback": selected != locale,
    }
