# Forex AI Agent Skills

Portable, reviewable workflows inspired by public quant-finance skill repositories. These are project-specific adaptations, not copied third-party skill files. Skills provide repeatable procedures; executable Python tests enforce critical rules.

## Skill index

- `market-data-quality`: timestamp, OHLC, spread, duplicates, gaps and freshness.
- `mt5-read-only`: terminal lifecycle, symbol discovery, ticks/bars and broker specifications without order placement.
- `point-in-time-research`: prevent look-ahead, leakage and revised-data contamination.
- `backtest-validation`: walk-forward, purging/embargo, costs, robustness and honest reporting.
- `risk-ftmo-gates`: independent, fail-closed account and trading-rule validation.
- `news-macro-evidence`: provenance, event time, deduplication, currency mapping and uncertainty.
- `agent-review`: evidence contract, independent critic, permissions and auditability.

## Activation principle

A skill can guide an agent but cannot grant permissions. LLM outputs are untrusted research inputs. Only deterministic validators may approve data quality and risk policy. Unknown, stale or conflicting evidence blocks downstream signal approval.
