# MT5 Web Bridge (read-only)

This receiver accepts market/account snapshots pushed by the MQL5 publisher. It has no
order placement, position modification, account login, or credential-storage endpoint.

## Security
- Ingest requires a bearer token from MT5_BRIDGE_TOKEN (at least 32 characters).
- Never commit the token. Configure it only in the service environment and MT5 EA inputs.
- Browser reads use existing authenticated session and CSRF protections.
- Account number and broker password are not collected.
- Snapshots older than 120 seconds are marked disconnected.
- Only the latest snapshot is retained. execution_allowed is always false.

## Publisher
Source: mt5/Experts/ForexAutoWebBridge.mq5. Compile in MetaEditor, attach to an MT5 chart,
set the bridge token, and allow the HTTPS host under MT5 Expert Advisors WebRequest URLs.
The EA publishes completed bars only (CopyRates starts at shift 1) and never sends orders.

## Ubuntu
The FastAPI receiver runs in the existing Control Center; no additional public port is used.
MT5 terminal still needs a compatible Wine installation and the publisher EA loaded.
The official MetaTrader5 Python package is Windows-only; this bridge uses MQL5 WebRequest
instead. Repository changes do not imply Wine/MT5 has already been installed on the VPS.
