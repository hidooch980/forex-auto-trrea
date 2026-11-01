# Forex AI Hybrid Scalper — Unified v5 Architecture

A unified web + desktop control application for a Python research/decision engine and MetaTrader 5 execution bridge.

## Selected product requirements
- Web dashboard and Windows desktop shell (same UI/API).
- Fully automatic execution is the intended mode, but **live orders remain disabled by default**.
- Adaptive strategy selection: trend / range / breakout-wait / no-trade.
- High-impact USD/EUR/GBP/etc. news blackout with fail-closed behavior.
- FX majors and XAUUSD (gold).
- Risk defaults for a $500 test account: FX 0.25%, gold 0.10%, daily stop 1%.
- Emergency stop and audit log.

## Architecture
- `backend/`: FastAPI service, settings, risk guard, news guard, signal engine.
- `frontend/`: lightweight single-page dashboard served by FastAPI.
- `desktop/`: PyWebView wrapper to present the same local app as a desktop application.
- `mt5/`: MQL5 EA bridge scaffold. It is intentionally not an order-sending implementation yet.
- `tests/`: basic safety tests.

## Run the web dashboard
```bash
python -m pip install -r requirements.txt
uvicorn backend.app:app --host 127.0.0.1 --port 8000
```
Open `http://127.0.0.1:8000`.

## Run desktop wrapper (Windows)
```bash
pip install pywebview
python desktop/app.py
```
Start the backend first. Desktop wrapper points to localhost.

## MT5 integration status
The included EA is a **bridge scaffold only**. It reports terminal/account status and reads an allow/deny control file. It does not place trades. A broker-specific execution module still needs:
- exact symbol mapping (e.g. XAUUSD, GOLD, suffixes),
- tick-size/tick-value/contract-size and volume-step validation,
- stop-distance and freeze-level checks,
- order filling mode and deviation policy,
- idempotent order IDs and duplicate prevention,
- persistent daily loss lock across restart,
- heartbeat and stale-signal rejection,
- verified compile and Strategy Tester runs.

Do not set live trading on until those items are implemented and independently tested.

## Broker-selection checklist
Choose a broker only after verifying:
1. Legal entity and regulator for your country of residence (for Italy, verify the entity in CONSOB and the relevant EU regulator register).
2. Retail CFD leverage and negative-balance protection rules applicable to you.
3. MT5 availability for the exact legal entity/account.
4. XAUUSD contract size, tick size/value, minimum lot, volume step, margin, trading hours, swap/financing and stop/freeze levels.
5. Typical and stressed spreads, commissions, slippage and execution policy.
6. Deposit/withdrawal fees and complaint process.

Never choose based on a bonus, advertised maximum leverage, or a single headline spread. Confirm the exact entity and account terms in the legal documents before depositing.

## Important
This is a development starter, not investment advice or a promise of profitability. CFD/Forex trading can lose money rapidly. Start in Strategy Tester and demo. No broker credentials, passwords, API keys or investor passwords should be placed in source control.
