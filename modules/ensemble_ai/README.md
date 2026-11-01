# Forex AI Hybrid Scalper — Ensemble Brain v1

Research/training scaffold for an MLP + LSTM + XGBoost ensemble with weekly retraining.
**Not a live trading system.** The MT5 adapter is read-only by default; order execution is deliberately not implemented.

## Design
- Three classifiers estimate `down / flat / up` probabilities.
- A validation-only soft-voting layer combines their probabilities.
- Walk-forward evaluation uses chronological splits; no random shuffling.
- Weekly retraining writes a candidate model. Promotion requires passing configured gates.
- Model artifacts are versioned and accompanied by metrics and feature schema.
- Risk checks are separate from model inference.
- MT5 integration is read-only and rejects trade requests.

## Install
Python 3.10+ recommended.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## Data contract
CSV columns: `time, open, high, low, close, tick_volume, spread, symbol`.
The training pipeline expects one row per completed bar and precomputed numeric features.
Do not mix symbols/timeframes without including symbol/timeframe identity features and validating each market separately.

## Run
```bash
python -m src.train --csv data/sample_features.csv --out artifacts
python -m src.evaluate --csv data/sample_features.csv --model-dir artifacts/candidate
python -m src.weekly_retrain --csv data/sample_features.csv --artifacts artifacts
```

The sample dataset is synthetic and only verifies the pipeline. It is not suitable for trading.
Use broker-quality historical bid/ask data, realistic commissions, swaps, spread and slippage.
Labels are generated from a future horizon in `src/data.py`; features must be strictly backward-looking.

## Weekly deployment protocol
1. Freeze a timestamped data snapshot.
2. Run training and walk-forward evaluation.
3. Compare candidate against active model on untouched recent holdout.
4. Reject if data checks, calibration, drawdown, turnover or performance gates fail.
5. Promote candidate atomically; retain previous version for rollback.
6. Run shadow/paper mode on MT5 demo before considering any execution integration.

## MT5
`src/mt5_readonly.py` only reads terminal/account/market data. It never calls `order_send`.
Live execution is out of scope for this scaffold and must be implemented separately with explicit safeguards, broker-specific symbol/volume checks, idempotency, stop-loss validation and demo sign-off.

## Important
ML probabilities are not calibrated guarantees. Avoid leakage, survivorship bias and overfitting.
Backtests should include realistic trading costs and use walk-forward/out-of-sample periods.
