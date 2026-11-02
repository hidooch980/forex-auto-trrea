# MT5 Expert Advisor — Forex AI Hybrid Scalper

## Status

The first MT5 execution shell is implemented in `Experts/ForexAIHybridScalper.mq5`.
It is deliberately **disabled by default**. It is not yet connected directly to the
Python Master Brain and must not be treated as a production-ready trading system.

## Safety defaults

- `InpEnableLiveTrading = false`: no order is sent unless the operator explicitly enables it.
- Hard maximum risk is 0.25% of equity per FX trade, regardless of a larger input value.
- XAU symbols (symbol name contains `XAU`) are capped at 0.10%.
- Daily equity loss ceiling is hard-capped at 1.00%.
- One open position per symbol and magic number.
- A fresh, approved brain signal, confidence threshold, stop distance, spread check,
  terminal permission, free-margin check and valid broker stop distances are required.
- Position size is calculated with `OrderCalcProfit`; volume is rounded down.
  If the broker minimum lot would exceed the risk budget, the trade is skipped.
- Emergency stop: terminal Global Variable `FAI.GLOBAL.EMERGENCY_STOP = 1`.

These are software guardrails, not a guarantee against slippage, gaps, rejected orders,
broker execution differences, or losses.

## Signal bridge contract

A trusted bridge must publish the following **terminal Global Variables** for the chart symbol.
The EA only reads these values; it does not fabricate an AI signal.

| Variable | Value |
|---|---|
| `FAI.<SYMBOL>.ACTION` | `1` = BUY, `-1` = SELL, `0` = no signal |
| `FAI.<SYMBOL>.CONFIDENCE` | number from 0.0 to 1.0 |
| `FAI.<SYMBOL>.SL_POINTS` | positive stop-loss distance in symbol points |
| `FAI.<SYMBOL>.TIMESTAMP` | signal Unix timestamp in broker/server time basis |
| `FAI.<SYMBOL>.APPROVED` | `1` only after Master Brain and risk gate approval |
| `FAI.GLOBAL.EMERGENCY_STOP` | `1` blocks new entries; `0` or absent does not block |

Example for EURUSD:
- `FAI.EURUSD.ACTION = 1`
- `FAI.EURUSD.CONFIDENCE = 0.78`
- `FAI.EURUSD.SL_POINTS = 180`
- `FAI.EURUSD.TIMESTAMP = <current server Unix timestamp>`
- `FAI.EURUSD.APPROVED = 1`

**Important:** these values are an interface contract only. A Python-to-terminal publisher,
signal authentication, stale/replay protection across restarts, and end-to-end integration
tests still need to be implemented. Do not manually publish test signals on a live account.

## Trade journal (CSV)

The EA records deal events belonging to its configured magic number through
`OnTradeTransaction`. Both opening and closing deal records are written to
`MQL5/Files/ForexAI_TradeJournal.csv` (or the filename set in
`InpJournalFile`). The journal includes server time, deal and position IDs,
symbol, deal type/entry type, volume, price, profit, commission, swap, fee,
net result, account balance/equity, magic number and broker comment.

- The file is append-only from the EA; it is not uploaded or sent anywhere.
- Open it from MT5: File → Open Data Folder → MQL5 → Files.
- Net result per deal is profit + commission + swap + fee. A round trip can
  contain separate entry and exit rows; analyze by position ID for trade-level totals.
- Broker accounting conventions can vary. Verify commissions and fees against the account history.
- This is an execution journal, not a complete strategy-decision journal: signal rationale,
  agent votes, news context and screenshots are not yet included.
- Keep a backup before editing or clearing the CSV.

## Install in MetaTrader 5

1. Open MetaTrader 5 → File → Open Data Folder.
2. Copy `ForexAIHybridScalper.mq5` into `MQL5/Experts/`.
3. Open it in MetaEditor and compile.
4. Attach it to a demo chart and keep `InpEnableLiveTrading=false`.
5. Validate the signal bridge and risk sizing on a demo account before considering any live use.

Compilation and broker-specific demo validation have not been run from this repository workflow.
