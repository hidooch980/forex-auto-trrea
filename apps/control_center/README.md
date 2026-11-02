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

Open `http://127.0.0.1:8000` for the public product website, then choose **ورود به پنل** or open `http://127.0.0.1:8000/app` directly for the authenticated trading workspace.\n\n## Installable mobile app (PWA)\n\nThe website includes a Progressive Web App manifest, app icon, service worker, offline shell, and an install prompt. Serve it over HTTPS (or localhost during development), open the site in Chrome/Edge on Android or desktop, then choose **Install app / Add to Home Screen**. Authenticated API responses are deliberately never cached; offline mode only provides the application shell, not live prices or account data.

## User security and roles

Accounts are stored in SQLite at `data/auth.sqlite3`; password hashes use scrypt with per-user random salts. Session IDs are random opaque tokens stored server-side as SHA-256 hashes. Cookies are HttpOnly and SameSite=Strict; the Secure flag defaults on (set `COOKIE_SECURE=false` only for local plain-HTTP development); state-changing authenticated API calls require a per-session CSRF token. Login attempts are throttled persistently per IP/username identity (8 failures in a 5-minute window triggers a 15-minute lockout). API responses are marked no-store and baseline browser security headers are applied.

Roles:
- `admin`: list/create/deactivate users and access all dashboard controls.
- `trader`: view status and decision previews; activate emergency stop.
- `analyst`: view status and decision previews; no write controls.
- `viewer`: view status only.

Only an explicitly provisioned administrator can create accounts. Set these environment variables before the first startup:

```bash
export ADMIN_USERNAME="your-admin-name"
export ADMIN_PASSWORD="use-a-unique-password-at-least-14-characters"
```

No default account or password is created. Keep the admin password in your hosting provider's secret manager; never commit it to GitHub. If an administrator already exists, changing these variables will not overwrite that account.

For HTTPS deployment, keep `COOKIE_SECURE=true` (the default). Set it false only for local HTTP development. Set `AUTH_DB_PATH` to a persistent, writable location and back it up securely. Set `SESSION_TTL_SECONDS` to adjust the session lifetime (default 8 hours). Disable a user from the admin panel to revoke all of that user's sessions.

API:
- `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`
- `GET /api/users`, `POST /api/users`, `PATCH /api/users/{id}/active` (admin only)
- `GET /api/status` (authenticated)
- `GET /api/decision-preview` (admin, trader, analyst)
- `POST /api/emergency-stop` (admin, trader; CSRF token required)

## Desktop app

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r desktop/requirements.txt
python desktop/app.py
```

The desktop launcher starts the local API on `127.0.0.1:8000` and opens it in a native window.

## Safety and deployment limitations

- No live market prices, broker connection, MT5 order placement or production news-calendar provider.
- Live order execution remains disabled.
- The emergency-stop latch is process-local; it is not a broker-side kill switch.
- Use HTTPS, a reverse proxy, firewall restrictions, persistent encrypted backups and host-level monitoring before remote deployment. Add edge/WAF rate limits, account recovery controls, CSP hardening, audit logging and independent security review before exposing login to the public internet.
- Do not expose the development server directly to the public internet.
