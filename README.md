# Forex AI Hybrid Scalper

Unified development repository for a Forex and XAUUSD research/scanning dashboard, AI model experiments, risk/news guards, and smart exit planning.

> **Status: development scaffold — not production-ready and not approved for live trading.** The repository does not currently contain a verified end-to-end MT5 order execution bridge, a live market-data feed, or a production economic-calendar integration. Live order placement is intentionally disabled. Use demo accounts and independent validation only.

## Repository layout

```text
apps/control_center/       FastAPI dashboard and desktop wrapper scaffold
modules/ensemble_ai/       MLP + LSTM + XGBoost training/evaluation scaffold
modules/smart_exit/        ATR/swing-based SL/TP and position-management planner
modules/news_ai/           Explainable news sentiment features by currency/pair
modules/master_brain/      Hybrid specialist-signal orchestration and balanced risk gate
 docs/                     Integration and deployment notes
.github/workflows/         Basic Python test workflow
```

## Agreed default research configuration

- Instruments: selected FX pairs and XAUUSD (broker symbol suffixes must be mapped explicitly).
- Test-account assumption: USD 500; this is a placeholder, not an account connection.
- Per-trade risk defaults: FX 0.25%, XAUUSD 0.10%.
- Daily loss guard: 1%.
- News filter: fail-closed when valid calendar data is missing or stale.
- No martingale or grid logic.
- Live trading: disabled.

These are configuration starting points, not evidence of profitability or safe execution.

## Quick start — dashboard scaffold

From `apps/control_center`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` on the same machine. Do not expose the development server directly to the public internet. Add authentication, TLS termination, firewall rules, and a reviewed deployment configuration before remote access.

## Tests

The component tests are currently separate. See each component README and run the commands from that component directory. The CI workflow runs the lightweight guard and smart-exit unit tests; it does not validate model quality, broker integration, or trading performance.

## AI model component

`modules/ensemble_ai/` contains MLP, LSTM and XGBoost model-building code, ensemble weighting, metrics, registry and retraining scaffolding. TensorFlow and XGBoost are heavyweight optional dependencies and should be installed only in a suitable training environment. The weekly retraining script is an orchestration scaffold, not a configured production scheduler. Before relying on evaluation results, enforce strict chronological train/validation/holdout separation and symbol/timeframe-aware features.

## News analysis component

`modules/news_ai/` provides a transparent baseline for scoring timestamped news headlines/summaries, weighting by recency and impact, and aggregating sentiment by currency and FX pair. It is a feature scaffold only: no live news provider is connected and the lexicon is not a trained financial NLP model. Keep the existing economic-calendar blackout guard independent; stale or missing calendar data must not be bypassed by sentiment scores.

## Hybrid Master Brain

`modules/master_brain/` is the deterministic central committee for technical, institutional-proxy, news, macro, smart-money and strategy signals. It produces auditable BUY/SELL/HOLD research decisions, applies freshness/confidence/disagreement checks, and fails closed on missing market/calendar data, event blackouts, emergency stop, daily loss, drawdown or excessive spread. The balanced profile caps proposed risk at 0.25% per trade; existing instrument-specific limits (including the lower XAUUSD default) must take precedence when integrating it. Reliability multipliers are bounded and remain neutral by default. This is an orchestration baseline, not a human-like autonomous intelligence, calibrated probability model, live data feed, or broker execution engine. See [Master Brain documentation](modules/master_brain/README.md).

## Smart exit component

`modules/smart_exit/` calculates proposed initial SL/TP and returns position-management instructions. It does not send modifications or partial-close orders to a broker. Before integration, add and test broker-specific tick-size, tick-value, volume-step, minimum-volume, stop-distance, freeze-level, bid/ask and partial-close confirmation handling.

## MetaTrader 5 status

The MT5 material is a scaffold/read-only boundary. Native Python `MetaTrader5` integration is Windows-oriented; this repository does not claim that MT5 runs natively on Ubuntu. A Linux deployment needs a separately validated MT5 terminal/bridge strategy (for example, a carefully tested Wine setup or a separate Windows execution host). No broker credentials belong in Git.

## Required work before any live use

1. Select a regulated broker entity appropriate to the user's jurisdiction and verify its MT5/XAUUSD contract specifications.
2. Implement authenticated, encrypted, monitored market-data and news-calendar adapters.
3. Implement an authenticated emergency-stop endpoint and persistent risk locks.
4. Complete broker-specific order execution, idempotency, reconciliation and restart recovery.
5. Compile and test the EA in MetaEditor/Strategy Tester where applicable.
6. Run chronological walk-forward and out-of-sample tests, then extended demo forward-testing.
7. Review logs, failure modes, security, and operational recovery independently.

Never commit passwords, investor passwords, API keys, account numbers, private keys, or `.env` files.

## Run component unit tests locally

Run each component's tests from its own directory so its local `src` / `backend` package is importable:

```bash
cd modules/smart_exit && PYTHONPATH=. python -m pytest -q
cd ../../modules/ensemble_ai && PYTHONPATH=. python -m pytest -q
cd ../../modules/news_ai && PYTHONPATH=. python -m pytest -q
cd ../../apps/control_center && PYTHONPATH=. python -m pytest -q tests
```


## Four-language platform foundation

The control center supports Persian (`fa`), English (`en`), Arabic (`ar`)
and Turkish (`tr`) through a shared localization catalog. The selected locale
is persisted in the browser, the document language and writing direction are
updated (Persian/Arabic RTL; English/Turkish LTR), and common API authorization
errors use the selected locale.

News content follows an editorial localization contract: headline, summary
and analysis are stored per language, with explicit fallback metadata rather
than silent machine translation. The news sentiment baseline includes
multilingual vocabulary, but it is not a trained financial NLP model.

This is the foundation for a complete localization rollout, not a claim that
every component document, external provider message, MT5 terminal message or
all dynamic server-generated content has already been translated. Live news
and market-data providers remain unconnected.


## Market pulse and signal performance

The four-language control center now includes a market analytics workspace:
- Signal performance cards: win rate, average net profit, net profit and profit factor.
- Fear & Greed index interface, requiring measured momentum, breadth, volatility and safe-haven-demand components.
- Live market map driven only by provider-supplied price changes.
- Signal-performance heatmap and symbol ranking sorted by average net profit.
- Authenticated `/api/analytics/overview` endpoint.

The analytics calculations live in `modules/analytics` and have independent unit
tests. They accept only completed realized trade outcomes; open trades and
partial exits must not be counted as completed results. The current MT5 journal
is deal-oriented, so a position-lifecycle reconciliation layer is required
before it can be treated as a complete closed-trade source.

**Integration status:** the dashboard and calculation layer are implemented,
but live price data, Fear & Greed source components and reconciled closed-trade
history are not connected. The API therefore reports unavailable states and
does not fabricate performance values. See `modules/analytics/README.md`.


## Specialist agents, reusable skills and market-data quality

The project now defines bounded specialist-agent roles in `agents/registry.yaml` and portable workflows under `skills/*/SKILL.md`. The skill set covers MT5 read-only integration, market-data validation, point-in-time research, backtest validation, FTMO/risk checks, news/macro evidence and agent review.

A deterministic validator in `modules/market_data_quality` checks OHLC integrity, timestamps, duplicates, ordering, freshness, future bars, volume/spread anomalies and optional interval gaps. It does not repair source data. Its unit tests run in CI.

These additions adapt research practices from public quant-finance skill catalogs; they do not copy third-party skill text or code. External skill instructions never grant tool permissions. LLM agents remain research-only; data validation and risk policy are deterministic.

### Reference projects and APIs

- [ML4T Agent Skills](https://github.com/ml4t/skills) — point-in-time data, leakage, walk-forward validation, cost models and research workflow discipline.
- [Artheras Quant Skills](https://github.com/artheras/skills) — executable verification gates, strategy specification and risk review.
- [LLMQuant Skills](https://github.com/LLMQuant/skills) — evidence-grounded finance workflows and specialist skill routing.
- [MQL5 Python integration](https://www.mql5.com/en/docs/python_metatrader5) — terminal status, symbols, ticks, bars, market depth and account/order inspection APIs.
- [MT5 copy_rates_from_pos](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py) — bar retrieval semantics; position zero is the current/forming bar, so completed-bar research must handle it separately.

**Integration status:** these are architecture, workflow and quality-gate foundations. They do not mean live market/news/calendar providers are connected, specialist LLM agents are running autonomously, or MT5 live execution is enabled. The MT5 Python adapter remains read-only and live trading remains disabled.


Agent outputs are validated by `modules/agent_contracts`: every specialist result must include a UTC timestamp, source identifiers, valid data-quality state, bounded confidence, stance and rationale. Stale, future-dated, source-free or degraded outputs are rejected before orchestration.


## Deterministic risk and behavioral discipline

`modules/risk_behavior_guard` provides a fail-closed pre-trade policy evaluator. It checks daily/weekly loss, peak drawdown, trade count, loss streak, hourly overtrading, required stop-loss, minimum reward/risk, market-data validity, calendar availability and spread acceptance. It also flags objective proxies for revenge trading (risk/volume escalation after a loss), post-loss cooldown and stale-signal/FOMO-style late entries.

The module does not infer a person's actual emotional state and does not place, modify or close orders. Missing last-loss timing blocks approval until a reliable trade-history adapter supplies it. Its current default limits are conservative research defaults (0.25% per trade, 1% daily loss, 2% weekly loss, 5% peak drawdown); account-specific FTMO/broker rules must override them where stricter. The guard is unit-tested in CI but is not yet wired into the live Master Brain or MT5 execution path, and live execution remains disabled.
