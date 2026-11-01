from datetime import datetime, timedelta, timezone
from news_analyzer import analyze_news, pair_sentiment, score_article


def test_article_sentiment_direction():
    assert score_article("Strong growth beats forecast") > 0
    assert score_article("Weak decline and recession risk") < 0


def test_currency_and_pair_sentiment():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = analyze_news([
        {"title": "Strong growth beats forecast", "currencies": ["USD"],
         "published_at": now, "impact": "high"},
        {"title": "Weak decline", "currencies": ["EUR"],
         "published_at": now, "impact": "medium"},
    ], now=now)
    assert result["available"]
    assert pair_sentiment(result, "EURUSD") < 0


def test_stale_and_undated_articles_are_excluded():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = analyze_news([
        {"title": "Strong growth", "currencies": ["USD"],
         "published_at": now - timedelta(days=3)},
        {"title": "Strong growth", "currencies": ["USD"]},
    ], now=now)
    assert not result["available"]
    assert result["articles_stale_or_undated"] == 2


def test_unknown_currency_is_ignored():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = analyze_news([{"title": "Strong growth", "currencies": ["ABC"],
                            "published_at": now}], now=now)
    assert not result["available"]
