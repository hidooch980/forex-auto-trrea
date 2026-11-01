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

- Maximum proposed risk: 0.25% per FX trade; XAUUSD has an enforced 0.10% instrument cap. Lower upstream/broker limits still take precedence.
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
