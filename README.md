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
