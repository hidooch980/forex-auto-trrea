# Read-only MetaTrader 5 discovery

This helper reads the exact server and symbol constraints from an MT5 terminal that is already running and logged in. It never logs in, switches accounts, reads passwords, or trades.

## Run on the Windows computer that has the MT5 terminal
1. Open MT5 and log into the intended account (demo is recommended).
2. In PowerShell, install the official Python package: `py -m pip install MetaTrader5`.
3. From the repository root, run:
   `py scripts/mt5_discover_server.py --symbol EURUSD --timeframe M15 --bars 100`
4. The JSON contains the exact `terminal.server_name`, demo/live classification, symbol tick size/value, point/digits, stop/freeze levels, volume min/max/step, bid/ask, spread and 100 most recent completed bars.
5. Keep the terminal open and connected. To inspect a different instrument, change `--symbol` to its exact MT5 Market Watch symbol (including broker suffix).

The script deliberately omits account login and passwords. Do not post account credentials. The returned `trade_allowed` fields are descriptive only; the tool remains read-only.

## Linux VPS limitation
The existing VPS is Ubuntu. The official MetaTrader5 Python package requires a supported Windows terminal host; it cannot discover a terminal running on a different computer. Run this script on the Windows host where MT5 is installed. It reports facts from that connected terminal, not from a broker-name catalogue.

## SL/TP
Use the `broker`, `spread_points` and `candles` values from the output in the Control Center's Adaptive SL/TP page. Enter the current equity and use ask for BUY entry / bid for SELL entry. The planner returns a proposal only; it never submits or modifies an order.
