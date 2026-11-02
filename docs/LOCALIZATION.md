# Localization and multilingual content standard

## Supported locales

| Code | Language | Native name | Direction |
|---|---|---|---|
| `fa` | Persian | فارسی | RTL |
| `en` | English | English | LTR |
| `ar` | Arabic | العربية | RTL |
| `tr` | Turkish | Türkçe | LTR |

Persian is the default locale. The control center stores the user's selection in
browser-local preferences and sets the document `lang` and `dir` attributes.
All layout changes must work in both directions; use CSS logical properties
(`margin-inline`, `padding-inline`, `border-inline-start/end`) rather than
hard-coded left/right offsets.

## Rules for every new feature

1. Add all user-visible labels, empty states, validation messages, tooltips,
   button labels and accessibility text to `apps/control_center/backend/i18n.py`.
2. Never put a new user-visible string directly into JavaScript or HTML when
   it should be translated. Use the shared catalog and `t()` in the browser,
   or `translate()` for API responses.
3. Keep API identifiers, enum values, symbols, broker codes, file formats and
   log keys stable and language-neutral. Translate only their presentation.
4. Format dates, times, numbers and currencies with the selected locale, while
   keeping machine-readable API values in ISO 8601 / numeric form.
5. Check Persian and Arabic at narrow mobile widths, then English and Turkish
   at the same widths. Verify keyboard focus, screen-reader labels and mixed
   RTL/LTR text such as XAUUSD, prices and timestamps.
6. Do not silently fall back to another language. For content that lacks a
   reviewed translation, expose the actual content locale and mark the
   fallback explicitly.
7. Financial/legal copy and trading news must be translated or reviewed by a
   qualified editor. Do not invent translations of market facts or use an
   unverified machine translation as a source.

## News article contract

The news module uses `modules/news_ai/news_schema.py`. Each article has a
stable ID, source, source URL, publication timestamp, category, impact,
sentiment and affected instruments/currencies. The editorial fields
`title`, `summary` and `analysis` are maps keyed by locale code. A localized
view includes `requested_locale`, `content_locale` and
`translation_fallback`.

The news-center UI is organized around a market sentiment pulse, impact and
category filters, searchable headlines, and article cards containing source,
publication time, summary, analysis and source link. It is a presentation and
data-contract foundation only: no live news provider is currently connected.

## Current implementation scope

- Shared four-language catalog and locale normalization.
- Persistent dashboard language selector, including the login screen.
- RTL/LTR switching for Persian/Arabic and English/Turkish.
- Localized common authentication and account-management API errors.
- News article localization contract and explicit fallback metadata.
- Baseline news sentiment vocabulary for all four languages.

Still required for a complete production rollout: translation coverage for
every remaining module and desktop string, reviewed terminology glossary,
provider-specific news translation feeds, source allowlists, deduplication,
multilingual financial NLP validation, and browser-based visual/accessibility
testing for all four locales.
