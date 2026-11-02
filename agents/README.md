# Forex AI specialist agents

This registry defines roles and contracts, not autonomous permission to trade. Agents produce evidence-backed analysis; the deterministic Master Brain and independent risk gates remain authoritative.

## Specialist roles

- **Market Data Sentinel** — validates provider identity, timestamps, quote freshness, OHLC integrity, spread, symbol mapping and feed continuity.
- **Technical Structure Analyst** — multi-timeframe trend, volatility, momentum, support/resistance and setup invalidation.
- **Macro & Calendar Analyst** — central-bank policy, rates, inflation, employment and event windows; every claim must cite a timestamped source.
- **News & Sentiment Analyst** — source credibility, duplicate-story clustering, currency mapping, event novelty and sentiment uncertainty. The lexicon baseline is not an NLP model.
- **Regime & Cross-Asset Analyst** — trend/range/volatility regime and FX/gold/intermarket context; never infer unprovided data.
- **Strategy Research Analyst** — hypothesis generation, feature review, leakage checks and walk-forward research; cannot approve its own backtest.
- **Execution & Broker Observer** — read-only MT5 terminal, symbol specifications, bid/ask, spread, market state and order constraints. No order-send permission.
- **Risk & FTMO Controller** — independent deterministic policy checks. Missing, stale or contradictory evidence means reject.
- **Independent Critic** — challenges assumptions, data lineage, conflicts and overconfidence; cannot override hard risk gates.
- **Master Brain** — fuses fresh specialist outputs, records weights/reasons and emits BUY/SELL/HOLD research decisions. It does not directly execute orders.

## Agent output contract

Every agent result must carry: `agent_id`, `schema_version`, `symbol` or explicit market scope, `as_of` UTC timestamp, `source_ids`, `data_quality`, `confidence` in [0,1], `stance`, `rationale`, `invalidations`, and `limitations`. Unsupported claims are omitted, not guessed.

## Permission model

1. Research agents: read-only market/news/calendar inputs.
2. Critic: read-only access to other agent outputs and source evidence.
3. Risk controller: deterministic code, not an LLM judgment.
4. Execution observer: read-only MT5 adapter.
5. Order execution: separate future component, disabled by default, requires explicit operator enablement and demo certification. No agent gets broker credentials or unrestricted order tools.

See `registry.yaml` for machine-readable role definitions.
