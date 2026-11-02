from backend.i18n import (
    SUPPORTED_LOCALES,
    catalog_for_frontend,
    is_rtl,
    normalize_locale,
    translate,
)


def test_supported_languages_and_direction():
    assert SUPPORTED_LOCALES == ("fa", "en", "ar", "tr")
    assert is_rtl("fa")
    assert is_rtl("ar")
    assert not is_rtl("en")
    assert not is_rtl("tr")


def test_locale_normalization_and_fallback():
    assert normalize_locale("tr-TR") == "tr"
    assert normalize_locale("ar_SA") == "ar"
    assert normalize_locale("xx") == "fa"


def test_dashboard_catalog_has_four_language_values():
    catalog = catalog_for_frontend()
    assert catalog["داشبورد معاملاتی"]["en"] == "Trading Dashboard"
    assert catalog["داشبورد معاملاتی"]["ar"]
    assert catalog["داشبورد معاملاتی"]["tr"]
    assert translate("Authentication required.", "tr") == "Kimlik doğrulaması gerekli."
