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



def test_multilingual_sentiment_baseline():
    assert score_article("رشد و افزایش تقویت بازار") > 0
    assert score_article("کاهش و ضعف و بحران") < 0
    assert score_article("ارتفاع ونمو إيجابي") > 0
    assert score_article("تراجع وضعف وأزمة") < 0
    assert score_article("güçlü büyüme ve yükseliş") > 0
    assert score_article("düşüş ve enflasyon riski") < 0


def test_localized_news_article_contract_and_explicit_fallback():
    from news_schema import article_for_locale, validate_news_article

    article = {
        "id": "sample-1",
        "source": "Verified News Desk",
        "url": "https://example.com/story",
        "published_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "category": "macro",
        "impact": "high",
        "sentiment": "negative",
        "currencies": ["USD", "XAU"],
        "title": {"fa": "عنوان فارسی", "en": "English headline"},
        "summary": {"fa": "خلاصه فارسی", "en": "English summary"},
        "analysis": {"fa": "تحلیل فارسی", "en": "English analysis"},
    }
    normalized = validate_news_article(article)
    view = article_for_locale(normalized, "tr")
    assert view["title"] == "English headline"
    assert view["content_locale"] == "en"
    assert view["translation_fallback"] is True


def test_news_contract_rejects_missing_locale_content():
    from news_schema import validate_news_article

    article = {
        "id": "sample-2", "source": "Desk", "url": "https://example.com/story",
        "published_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "title": {"fa": "عنوان"}, "summary": {"fa": "خلاصه"},
        "analysis": {},
    }
    try:
        validate_news_article(article)
        assert False, "missing localized analysis must be rejected"
    except ValueError:
        pass



def test_news_contract_rejects_naive_timestamps_and_unknown_categories():
    from news_schema import validate_news_article

    article = {
        "id": "sample-3", "source": "Desk", "url": "https://example.com/story",
        "published_at": datetime(2026, 1, 1),
        "category": "rumor",
        "title": {"fa": "عنوان"}, "summary": {"fa": "خلاصه"},
        "analysis": {"fa": "تحلیل"},
    }
    try:
        validate_news_article(article)
        assert False, "naive timestamp must be rejected"
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
