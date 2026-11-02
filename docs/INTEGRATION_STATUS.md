# Service stability and integration status

Last repository audit: 2026-11-02. This file separates code-level checks from deployment and live-trading verification.

## Verified in repository

| Area | Implemented / checked | Remaining limitation |
|---|---|---|
| Python CI | Compile step and module/control-center tests | Only validates the tested Python code and dependencies |
| Authentication | SQLite users/sessions, scrypt password hashes, HttpOnly/SameSite cookies, CSRF on state-changing authenticated routes | Production reverse-proxy, TLS, backup/restore and penetration tests not verified |
| Login abuse control | Persistent per-IP-and-username attempt throttling (8 failures / 5 minutes; 15-minute lockout) | Not a substitute for edge/WAF rate limits, bot defense or distributed abuse monitoring |
| HTTP headers | no-sniff, frame denial, referrer/permissions policies, API no-store, HSTS when secure-cookie mode is enabled | CSP needs a nonce/hash migration because the dashboard contains inline scripts/styles |
| Roles | Admin/trader/analyst/viewer authorization and tests | Full authorization matrix and independent security review remain outstanding |
| Portfolio risk | Deterministic cross-market preview; gross long+short risk, leverage, margin, concentration, liquidity and spread checks | Caller-supplied snapshots only; no live account/position reconciliation and no execution-side enforcement |
| Emergency stop | Authenticated stop endpoint; starts active; live execution disabled | Process-local only, no durable shared state, no broker/EA acknowledgement, no audited reset workflow |
| Broker directory | Search catalog and user-scoped saved MT4/MT5 Demo/Live server names | Starter catalog only; no automatic MetaTrader discovery or server verification |
| News and analytics | APIs explicitly report unavailable rather than inventing data | No live calendar/news/market data or trade-history provider |
| Android | HTTPS-only server URL; WebView mixed-content block, safe browsing and stricter navigation; release signing workflow | Build must pass after latest Android changes; no deployed HTTPS endpoint or published signed APK verified |
| MT5 / exchanges | Read-only/scaffold boundaries and signal bridge documentation | No verified live adapter, account feed, order routing, reconciliation or exchange connectivity |
| AI models | Research/training/evaluation scaffolds and agent contracts | No validated live inference pipeline, leakage-safe final holdout report or automated model promotion |

## Safety posture

- Live order execution remains disabled.
- The portfolio risk preview always returns `execution_allowed: false`.
- Emergency stop starts active. It must not be treated as a broker-side kill switch.
- Never use caller-supplied equity, open positions, spread or liquidity as verified live data.
- Do not connect production API keys with withdrawal permissions. Exchange keys, if later added, must be trade-only, IP-restricted and stored outside the repository.
- Do not claim the service is production-ready until deployment, TLS, persistent storage, backup restore, monitoring, real-feed freshness, broker/exchange sandbox order lifecycle, reconciliation and independent security checks pass.

## Release gates still open

1. Run and pass current Python CI and Android debug APK workflow on the latest commit.
2. Configure a real HTTPS deployment, secure secrets, persistent database volumes and tested backups.
3. Add a shared persistent emergency-stop state with explicit admin reset, audit trail and downstream broker/EA acknowledgement.
4. Implement provider adapters with timestamps, health checks, stale-data rejection and reconnect handling.
5. Reconcile positions, equity, margin, fees, funding and realized/unrealized PnL across all connected venues.
6. Put deterministic risk checks directly in the final order execution path; no preview-only bypass.
7. Validate demo/testnet order submit, amend, cancel, partial fill, reject, timeout, duplicate request and restart recovery.
8. Complete MQL5 compilation and Strategy Tester validation on supported terminals.
9. Perform dependency/security scanning, rate limiting at the edge, CSP hardening, audit logging, load testing and backup-restore drills.
10. Publish a signed Android release only after signing secrets and the release workflow are verified.

## Local development cookie setting

The secure cookie flag defaults to enabled. For local plain-HTTP development only, set `COOKIE_SECURE=false`. For every remotely accessible deployment, terminate TLS and keep `COOKIE_SECURE=true`.
