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


## Broker and MT4/MT5 server directory

`modules/broker_directory` provides broker-name autocomplete for a curated discovery list (including common global providers) and a per-user directory of exact MT4/MT5 server names. The control center exposes authenticated broker search plus Demo/Live server suggestions and lets admins/traders save a newly confirmed server so it appears in later searches.

The catalog deliberately does not invent exact Demo/Live server labels: these can differ by broker entity, region, platform and account group, and may change. A broker name appearing in autocomplete does not mean its server endpoints have been verified or that a terminal connection is available. Users should copy the exact server label shown by their broker or MT4/MT5 login screen. The directory stores names only; it never stores account passwords or investor passwords. Saved server suggestions are isolated per user.

The current directory is a starter catalog, not an exhaustive registry of every broker worldwide. MT5 terminal-side broker discovery and automatic synchronization with all brokers are not yet integrated.

## Cross-market portfolio risk for large and two-sided trading

`modules/portfolio_risk_guard` adds a deterministic portfolio-level pre-trade evaluator for combined Forex, metals, crypto spot/futures and other configured markets. It aggregates stop-risk across the entire book, applies separate per-market risk caps, and measures gross leverage, margin usage, per-instrument concentration, visible-liquidity participation and spread.

Long and short positions are deliberately aggregated as **gross risk**; opposite directions are not assumed to cancel because basis, funding, margin, execution and liquidation risks remain. Missing/invalid market data, missing stop-loss, and an active portfolio emergency stop fail closed. Default limits are conservative starting values and must be calibrated to verified account equity, contract specifications and venue liquidity.

This is a tested policy component only. It is **not yet connected to live account/position feeds, the Master Brain, broker/exchange order routing or liquidation controls**. It does not place, amend or close orders, and live trading remains disabled. Liquidity-depth inputs must come from a fresh, venue-specific order book; estimates or stale depth must not be treated as executable capacity.

The control center also exposes an authenticated `POST /api/risk/portfolio-preview` endpoint for submitting a caller-provided equity snapshot, current positions and proposed order. It returns the risk decision, limit metrics and block reasons. This endpoint is a preview only: caller-supplied values are not treated as verified live data, the global emergency-stop latch is included, and `execution_allowed` is always false. It does not replace a live broker/exchange adapter or the final execution-side risk gate.


## XAUUSD Phantom-inspired four-engine research framework

`modules/xauusd_phantom` adds a deterministic, broker-agnostic research planner inspired by the public ANAKO GOLD PHANTOM feature description. It defines four independent strategy lanes (breakout, pullback, momentum and mean reversion), but applies one shared XAUUSD risk budget before any candidate is accepted. The initial research defaults cap each engine at 0.025% equity risk and all four engines together at 0.10% open stop-risk; these are conservative engineering test defaults, not optimized parameters or a profitability claim.

The planner includes fail-closed checks for stale/future signals, invalid stop/target geometry, reward/risk, spread, market closure, news blackout and emergency stop. It also provides execution-neutral helpers for one-cancels-other pending-order cleanup, ATR trailing-stop tightening and a realized-profit vault split. It does not place orders, fetch news, manage broker tickets, move money, or connect to the MT5 EA. Every decision returns `execution_allowed: false`.

The four strategy names are independent proposal slots, not four completed profitable trading algorithms. Signal generation, broker-specific pending-order lifecycle, persistent vault accounting, economic-calendar integration, MT5 compilation, Strategy Tester validation and demo forward-testing remain separate release gates. Run its tests with:

```bash
PYTHONPATH=modules python -m pytest -q modules/xauusd_phantom/tests
```


## Persistent risk ledger and circuit breakers

`modules/risk_state_store` adds a restart-safe SQLite ledger for risk reservations. Pending orders and open positions both reserve risk; the reservation is released only after a confirmed `CLOSED` or `CANCELLED` state transition. Reservation IDs are unique, state transitions are validated, and reservation checks use SQLite write transactions so concurrent callers cannot both spend the same risk budget.

The ledger persists active risk by strategy engine, total reserved risk, daily starting equity, account high-water equity, daily-loss and peak-drawdown circuit breakers, and an append-only audit trail. The daily lock resets automatically on the next UTC day; the peak-drawdown lock requires an explicit, reasoned operator unlock. The default limits mirror the XAUUSD Phantom research budget (0.10% total, 0.025% per engine), with 1% daily loss and 5% peak drawdown thresholds.

This is a storage and policy primitive, not yet an account-history reconciler or a live execution integration. A trusted adapter must reconcile broker order/position IDs and actual stop-loss cash risk after every fill, partial fill, cancellation, close, reconnect and restart. Until that adapter is connected and verified, the ledger must not be treated as a live account's source of truth, and order execution remains disabled. Run its tests with:

```bash
python -m pytest -q modules/risk_state_store/tests
```


## Unified ERP API integration layer

The control center now mounts a shared authenticated ERP API facade under `/api/erp`. The module catalog reports which subsystems are connected, preview-only, research-only or still unavailable; the overview combines that registry with the persistent risk snapshot.

Core contracts:
- `GET /api/erp/catalog` — module/API registry and truthful connection states.
- `GET /api/erp/overview` — unified ERP health and risk overview.
- `GET /api/erp/risk/snapshot` — persistent risk reservations and circuit-breaker state.
- `POST /api/erp/risk/equity` — record a trusted equity mark.
- `POST /api/erp/risk/reservations` — atomically reserve risk before an external order adapter may proceed.
- `PATCH /api/erp/risk/reservations/{reservation_id}` — reconcile reservation lifecycle (PENDING → OPEN/CLOSED/CANCELLED, OPEN → CLOSED).
- `POST /api/erp/risk/unlock` — admin-only, reason-audited risk-lock override.

The ERP facade reuses the same SQLite risk ledger for every caller. Set `ERP_RISK_LEDGER_DB` to select its durable database file, or `ERP_DATA_DIR` to select its parent directory. Keep this path on persistent storage and include it in encrypted backups. All state-changing routes use the existing session, role and CSRF controls.

**Important boundary:** this is the first shared API/integration layer, not completion of every external connector. Broker/MT5 execution, live market data, news/calendar providers and reconciled account history remain disconnected. The API deliberately returns `execution_allowed: false`; reserving risk is not an order submission. A trusted broker adapter must reconcile actual tickets, fills, partial fills, cancellations, closes and restart recovery before any execution path can be enabled.


## AI brain, chained data pipeline and error center

The ERP exposes a persistent, auditable decision chain:
`INGEST → VALIDATE → FUSE → RISK_GATE → COMPLETE`.
Raw market bars pass the existing OHLC/timestamp/freshness validator; each specialist output must pass the provenance, schema, scope and freshness contract; the hybrid Master Brain then fuses normalized specialist stances. The central persistent risk ledger is the final deterministic gate and reserves the approved risk budget before any downstream execution adapter could be considered.

New API contracts:
- `POST /api/erp/brain/pipeline` — submit bars plus provenance-carrying agent evidence; supports the `Idempotency-Key` header.
- `GET /api/erp/brain/pipeline/health` — run counts, retryable failures and quarantined inputs.
- `GET /api/erp/brain/pipeline/{run_id}` — full run state and ordered event trail.
- `POST /api/erp/brain/pipeline/{run_id}/retry` — admin/trader retry for transient upstream failures only, maximum three attempts.

The pipeline database is durable SQLite (WAL + FULL synchronous). Configure `ERP_PIPELINE_DB`, or use `ERP_DATA_DIR/erp_pipeline.sqlite3`. Invalid or stale evidence is quarantined and never auto-corrected. Retry is not permitted for schema, timestamp, provenance or data-quality failures. Internal exceptions are logged by type, without echoing sensitive payloads into the error message.

Safety boundary: the API accepts caller-supplied bars and agent evidence; it does not itself connect to a verified market-data vendor, news calendar or MT5. The economic calendar defaults invalid and the emergency stop defaults active. Every response retains `execution_allowed: false`; a risk reservation is not an order. The current stance-to-score mapping (bullish=+1, bearish=-1, neutral=0) is a deterministic bridge, not a trained or calibrated AI model.


## Closed-trade memory and agent evaluation

The ERP now accepts verified-by-operator closed-trade outcomes and the forecasts that existed before each trade closed:
- `POST /api/erp/performance/closed-trade` stores the trade outcome plus per-agent stance, confidence and pre-close timestamp.
- `GET /api/erp/performance/walk-forward` reports chronological train and out-of-sample hit rate, Brier score, sample count and confidence per agent.
- Storage: `ERP_PERFORMANCE_DB`, or `ERP_DATA_DIR/erp_performance_memory.sqlite3`.

Forecast timestamps later than the trade close are rejected. Duplicate trade IDs are rejected. The report uses chronological ordering, a 70/30 train/holdout split, and minimum sample thresholds (20 train / 10 holdout by default). This is evaluation memory, not online model training: it does not modify Master Brain weights or claim that an agent is profitable. Outcomes must be supplied by a trusted, reconciled closed-trade source; that broker reconciliation connector is not yet implemented.


## Cellular specialist learning and market-stress analysis

`modules/cognitive_cells` stores isolated outcome memory for technical, institutional, news, macro, smart-money and strategy specialist cells. A closed-trade outcome updates each matching cell using forecast direction versus realized trade direction. A Beta(1,1) posterior is reported for directional evidence. Shadow reliability multipliers remain neutral until at least 30 directional observations, are bounded to 0.75–1.25, and are never authorized to change live weights. The Master Brain may consume eligible multipliers in research-only evaluation; this is not online neural-network training.

The ERP exposes:
- `GET /api/erp/cognition/cells` — per-cell samples, posterior and shadow reliability.
- `POST /api/erp/cognition/market-affect` — observable market stress classification.
- `POST /api/erp/cognition/trading-behavior` — objective proxies for revenge trading, post-loss cooldown, overtrading and stale/FOMO-style entry.
- `POST /api/erp/performance/closed-trade` — also updates matching cell outcome memory.

Market-affect features include realized bar-range proxy, spread ratio, drawdown, loss streak, specialist disagreement and data-quality score. Labels (calm/uncertain/stressed/extreme) describe market/strategy conditions, not a trader's actual mental or emotional state. Extreme stress forces HOLD in the research decision chain. No psychological diagnosis is made.

## Release and finalization gate

See [`docs/FINALIZATION_CHECKLIST.md`](docs/FINALIZATION_CHECKLIST.md) for verified implementation scope and mandatory blockers before production/live use. The project remains a tested development scaffold; live execution is disabled.
