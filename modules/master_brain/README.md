# Hybrid Master Brain

The Master Brain is the central, deterministic decision orchestrator for the Forex AI Hybrid Scalper. It combines six specialist signal channels:

| Agent | Intended responsibility |
|---|---|
| Technical | Trend, momentum, volatility and price structure |
| Institutional | Public positioning/volume/open-interest proxies |
| News | Timestamped headline sentiment and event context |
| Macro | Rates, central-bank policy and economic regime |
| Smart Money | Liquidity sweeps, structure shifts, order blocks and FVG hypotheses |
| Strategy | Testable rule sets inspired by systematic discretionary and trend traders |

The implementation in `engine.py` accepts normalized inputs and produces an auditable BUY/SELL/HOLD decision. It is intentionally deterministic and does not call an LLM, fetch live data, train a model, or connect to a broker.

## Balanced defaults

- Maximum proposed risk: 0.25% per FX trade; XAU-prefixed symbols, including broker suffix variants such as XAUUSD.a, have a hard 0.10% cap. A configured gold cap cannot raise this ceiling. Lower upstream/broker limits still take precedence.
- Daily loss stop: 1%.
- Drawdown stop: 5%.
- Minimum committee confidence: 0.60.
- Minimum directional edge: 0.18.
- At least two fresh specialist signals.
- Signals older than 15 minutes are excluded by default.
- Spread above 2.5 pips blocks a decision.
- Missing/invalid calendar, missing/invalid market data, event blackout, and emergency stop all fail closed.
- Risk multipliers based on past reliability are bounded to 0.5–1.5 and default to 1.0. Do not enable adaptive learning until chronological walk-forward evidence supports it.

These are research guardrails, not personalized financial advice or a promise of safety/profitability. Instrument-specific caps are enforced by the brain itself (XAUUSD: 0.10%); broker/account limits may reduce them further.

## Example

```python
from modules.master_brain import AgentSignal, MarketContext, evaluate_market

decision = evaluate_market(
    MarketContext(symbol="EURUSD", calendar_valid=True),
    [
        AgentSignal("technical", 0.7, 0.8, "trend aligned"),
        AgentSignal("institutional", 0.4, 0.7, "public futures proxy"),
        AgentSignal("news", 0.2, 0.6, "headline baseline"),
    ],
)
print(decision.to_dict())
```

## MT5 signal publisher

`signal_bridge.py` publishes an already-created `BrainDecision` to the
MetaTrader 5 shared Common\\Files directory. It uses atomic replacement,
HMAC-SHA256 authentication, a random nonce, a UTC timestamp and an explicit
HOLD message to clear an older directional signal.

The publisher does **not** generate agent signals, fetch live prices or compute
a stop distance. The caller must provide a validated positive `sl_points` for
BUY/SELL decisions and use the same 32+ byte secret configured in the EA's
`InpBridgeSecret` input. Keep that secret out of source control.

See [the MT5 bridge setup](../../mt5/README.md#authenticated-python-to-mt5-bridge)
for the local folder setup and limitations. This is a local same-computer
transport, not a cloud connection.

## Test

From repository root:

```bash
python -m unittest discover -s modules/master_brain/tests -v
```

## Important data limitations

- Internal bank order flow and proprietary institutional positions are not public. COT, futures volume/open interest, visible order-book depth, regulatory filings and central-bank communications are imperfect, delayed or partial proxies.
- News sentiment must not override the independent economic-calendar blackout.
- Agent scores are hypotheses, not calibrated probabilities.
- Strategy principles associated with well-known traders must be encoded as explicit, testable rules; this package does not copy private trades or claim to reproduce any trader.
- No live execution is enabled. Every decision requires upstream data validation, realistic costs, chronological walk-forward testing and demo forward-testing before any later execution integration.
