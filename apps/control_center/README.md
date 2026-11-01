# Control Center — Web + Desktop

The Control Center is a FastAPI dashboard with a PyWebView desktop shell.

## Web dashboard

From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. The API also exposes:

- `GET /api/health` — service health
- `GET /api/status` — safe-mode configuration and integration status
- `GET /api/decision-preview?symbol=XAUUSD` — illustrative, non-live decision preview
- `POST /api/emergency-stop` — latches the emergency stop in the running process

The emergency-stop latch is process-local and resets to active on restart. It does not send a cancel/close request to MT5 because no broker execution adapter is connected. Live order execution is hard-disabled.

## Desktop app

From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r desktop/requirements.txt
python desktop/app.py
```

The desktop launcher starts the local API on `127.0.0.1:8000` and opens it in a native window. Close the desktop window to exit.

## Safety / limitations

- No live market prices or broker connection.
- No MT5 order placement or position modification.
- No production news-calendar provider; the news guard must remain fail-closed until a verified feed is integrated.
- The dashboard's capital and risk values are configuration assumptions, not connected account data.
- The emergency-stop button latches the dashboard's internal state only. It is not a broker-side kill switch.
- Do not expose the development server to the public internet. Add authentication, HTTPS, firewall restrictions and persistent state before remote deployment.
