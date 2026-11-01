# Integration status and known limitations

| Area | Current state | Not yet verified |
|---|---|---|
| FastAPI dashboard | Scaffold exists | Authentication, persistent state, secure remote deployment |
| Adaptive regime/strategy selector | Basic deterministic logic | Market-data integration and strategy validation |
| News guard | Fail-closed helper/scaffold | Live calendar provider, freshness and outage tests |
| Risk controls | Basic guards/config defaults | Persistent daily lock, broker equity reconciliation |
| MLP/LSTM/XGBoost | Model-building and evaluation scaffolds | Full leakage-safe pipeline, robust feature set, resource profiling |
| Weekly retraining | Script scaffold | Real scheduler, data pipeline, promotion/rollback automation |
| Smart SL/TP | Pure calculation functions with unit tests | Broker tick/volume/stops constraints and execution confirmation |
| MT5 | Read-only/scaffold boundary | Working Linux terminal bridge and order execution |
| Emergency stop | UI placeholder / config flag | Authenticated backend control, persistent enforcement and EA acknowledgement |
| Live trading | Disabled | Must remain disabled until all safety gates pass |

## Known architectural risks

- The current ensemble code imports TensorFlow, scikit-learn and XGBoost directly; the AI dependencies are not part of the lightweight dashboard requirements.
- Model features and labels need symbol/timeframe-aware definitions and strict chronological data partitioning before any performance claim.
- Ensemble candidate promotion must be based only on validation data; the final holdout must remain untouched until final evaluation.
- Smart-exit output is a proposal only. The caller must validate broker constraints and persist partial-close state only after broker confirmation.
- The current dashboard emergency-stop button is a placeholder and must not be represented as an operational kill switch.
