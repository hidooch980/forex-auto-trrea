# MT5 Expert Advisor — Forex AI Hybrid Scalper

## Status

The first MT5 execution shell is implemented in `Experts/ForexAIHybridScalper.mq5`.
It is deliberately **disabled by default**. It is not yet connected directly to the
Python Master Brain and must not be treated as a production-ready trading system.

## Safety defaults

- `InpEnableLiveTrading = false`: no order is sent unless the operator explicitly enables it.
- Hard maximum risk is 0.25% of equity per FX trade, regardless of a larger input value.
- XAU symbols (symbol name contains `XAU`) are hard-capped at 0.10%, even if
  `InpXauRiskCapPct` is configured higher.
- Daily equity loss ceiling is hard-capped at 1.00%. The starting equity baseline
  is shared by all EA charts for the same account and broker-server date, rather
  than being reset separately for each symbol.
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

## Authenticated Python-to-MT5 bridge

The EA now reads a signed, atomically replaced signal file from MT5's shared
**Common\\Files** directory. It no longer consumes directional signals from
terminal Global Variables. The emergency-stop latch remains a terminal Global
Variable: `FAI.GLOBAL.EMERGENCY_STOP = 1`.

1. Generate a random secret of at least 32 UTF-8 bytes and keep it private.
   Set the same value in the EA input `InpBridgeSecret` and the Python
   publisher's secret source. Do not commit the secret to GitHub.
2. Set `common_files_dir` to the absolute MT5 Common\\Files directory
   (usually under the user's MetaQuotes roaming data directory).
3. After upstream data and specialist agents have produced a decision, pass
   that exact `BrainDecision` to `publish_decision()`. The bridge publisher
   does not invent signals or fetch prices.

Example:

```python
import os
from modules.master_brain.signal_bridge import publish_decision

# decision = evaluate_market(validated_market_context, specialist_signals)
publish_decision(
    decision,
    common_files_dir=r"C:\\Users\\<USER>\\AppData\\Roaming\\MetaQuotes\\Terminal\\Common\\Files",
    secret=os.environ["FOREXAI_BRIDGE_SECRET"],
    sl_points=validated_stop_distance_points,
)
```

The publisher writes `ForexAI_Bridge/<SYMBOL>.signal` using a temporary file
and atomic replacement. Each message carries a SHA-256 HMAC, UTC Unix timestamp,
random nonce, approval flag and stop distance. The EA verifies the HMAC, symbol,
approval, freshness and stop distance before considering a directional signal.
A HOLD decision is also published and overwrites the prior signal. Python and
MT5 must run on the same computer and use the same Common\\Files directory.

**Security boundary:** protect the Common\\Files directory and the EA inputs.
Anyone who can read the EA's configured secret and write the shared bridge
folder can impersonate the publisher. Use a unique secret per terminal/account
and rotate it if exposed. This local file bridge is not a remote/cloud transport.

This transport only carries decisions that an upstream caller already created.
It does not provide live price feeds, economic-calendar validation, agent
generation, automatic stop-distance calculation, or order execution validation.
Live trading remains disabled by default. Verify the publisher and EA together
on a demo terminal before enabling anything.

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

## ثبت دلیل خروج و ضرر

در هر ردیف ژورنال، ستون‌های `deal_reason` و `loss_reason` اضافه شده‌اند.
برای خروج زیان‌ده، دسته‌بندی ماشینی شامل این موارد است:

- `STOP_LOSS_TRIGGERED`: خروج با فعال‌شدن حدضرر
- `MARGIN_STOP_OUT`: بسته‌شدن اجباری به علت سطح مارجین
- `MANUAL_CLOSE_AT_LOSS`: بستن دستی از ترمینال، موبایل یا وب با زیان
- `EA_CLOSED_AT_LOSS`: بسته‌شدن زیان‌ده توسط اکسپرت
- `LOSS_OTHER_OR_UNATTRIBUTED`: زیان با علت اجرایی نامشخص یا سایر علت‌ها

همچنین زمینه ورود شامل confidence، جهت سیگنال، فاصله حدضرر و اسپرد لحظه ورود
با شناسه موقعیت نگهداری می‌شود و هنگام ثبت خروج به ژورنال افزوده می‌شود.
اگر این داده‌ها از قبل در ترمینال موجود نباشند مقدار `-1` یا `NA` ثبت می‌شود.

**محدودیت مهم:** این ستون‌ها علت اجرایی خروج را مشخص می‌کنند، نه علت بنیادی اشتباه بودن تحلیل.
برای تشخیص مواردی مانند ورود دیرهنگام، خبر ناگهانی، ضعف روند، واگرایی یا خطای عامل AI،
باید snapshot تحلیل و اخبار در لحظه ورود نیز از پل Python به MT5 ارسال و ذخیره شود.
در خروج‌های جزئی نیز هر ردیف یک deal جداگانه است؛ برای نتیجه کل موقعیت از `position_id`
و جمع خالص همه ردیف‌های آن استفاده کنید.

## Install in MetaTrader 5

1. Open MetaTrader 5 → File → Open Data Folder.
2. Copy `ForexAIHybridScalper.mq5` into `MQL5/Experts/`.
3. Open it in MetaEditor and compile.
4. Attach it to a demo chart and keep `InpEnableLiveTrading=false`.
5. Validate the signal bridge and risk sizing on a demo account before considering any live use.

Compilation and broker-specific demo validation have not been run from this repository workflow.
