import os
import json
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from . import auth
from .config import AppConfig
from .engine import choose_regime, choose_strategy, authorize_trade
from .i18n import catalog_for_frontend, translate
from modules.ftmo_compliance import account_registry
from modules.broker_directory import directory as broker_directory

from modules.portfolio_risk_guard import (
    PortfolioSnapshot, Position as RiskPosition, TradeIntent as RiskTradeIntent,
    evaluate_portfolio,
)
from modules.erp_api.router import build_erp_router, default_ledger_path
from modules.risk_state_store import PersistentRiskLedger
from modules.market_radar.api import build_market_radar_router
from modules.backtest_lab.api import build_backtest_router
from modules.sltp_engine.api import build_sltp_router
from modules.mt5_web_bridge.api import build_mt5_bridge_router

app = FastAPI(title="Forex AI Hybrid Scalper", version="5.2.0")
cfg = AppConfig()
auth.init_auth()

@app.middleware("http")
async def apply_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if os.getenv("COOKIE_SECURE", "true").lower() == "true":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response



class LoginPayload(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)

class CreateUserPayload(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=14, max_length=256)
    role: str

class BrokerServerPayload(BaseModel):
    broker_name: str = Field(min_length=1, max_length=100)
    platform: str = Field(default="mt5", pattern="^(mt4|mt5)$")
    environment: str = Field(pattern="^(demo|live)$")
    server_name: str = Field(min_length=1, max_length=160)


class RiskPositionPayload(BaseModel):
    market: str = Field(min_length=1, max_length=40)
    instrument: str = Field(min_length=1, max_length=40)
    side: str = Field(pattern="^(long|short)$")
    notional_usd: float = Field(gt=0, le=1000000000000)
    stop_risk_usd: float = Field(ge=0, le=1000000000000)
    margin_usd: float = Field(ge=0, le=1000000000000)
    liquidity_usd_1pct: float = Field(gt=0, le=1000000000000)
    spread_bps: float = Field(ge=0, le=1000000)
    data_valid: bool = True


class RiskTradePayload(BaseModel):
    market: str = Field(min_length=1, max_length=40)
    instrument: str = Field(min_length=1, max_length=40)
    side: str = Field(pattern="^(long|short)$")
    notional_usd: float = Field(gt=0, le=1000000000000)
    stop_risk_usd: float = Field(ge=0, le=1000000000000)
    margin_usd: float = Field(ge=0, le=1000000000000)
    liquidity_usd_1pct: float = Field(gt=0, le=1000000000000)
    spread_bps: float = Field(ge=0, le=1000000)
    stop_loss_present: bool = True
    market_data_valid: bool = True


class PortfolioRiskPreviewPayload(BaseModel):
    equity_usd: float = Field(gt=0, le=1000000000000000)
    positions: list[RiskPositionPayload] = Field(default_factory=list, max_length=500)
    proposed_order: RiskTradePayload
    market_data_valid: bool = True

class FTMOAccountPayload(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    account_number: str | None = Field(default=None, max_length=80)
    product: str
    phase: str
    account_type: str
    platform: str = "mt5"
    initial_capital: float = Field(gt=0, le=100000000)
    currency: str = "USD"

def current_session(request: Request):
    session = auth.get_session(request.cookies.get("forex_session"))
    if not session:
        raise HTTPException(status_code=401, detail=translate("Authentication required.", request.headers.get("x-ui-language")))
    return session

def require_role(request: Request, *roles: str):
    user, csrf = current_session(request)
    if user["role"] not in roles:
        raise HTTPException(status_code=403, detail=translate("Insufficient role permissions.", request.headers.get("x-ui-language")))
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not secrets_compare(supplied, csrf):
            raise HTTPException(status_code=403, detail=translate("Invalid CSRF token.", request.headers.get("x-ui-language")))
    return user

def secrets_compare(left: str, right: str) -> bool:
    import hmac
    return hmac.compare_digest(left, right)

# Process-local latch. It starts active on every restart; execution remains disabled.
_emergency_stop_active = True

# Shared ERP risk ledger: all ERP risk APIs use this same durable store.
ERP_LEDGER = PersistentRiskLedger(default_ledger_path())
app.include_router(build_erp_router(require_role, ERP_LEDGER))
app.include_router(build_market_radar_router(require_role))
app.include_router(build_backtest_router(require_role))
app.include_router(build_sltp_router(require_role))
app.include_router(build_mt5_bridge_router(require_role))


@app.get("/api/health")
def health():
    return {"ok": True, "service": "control-center"}


@app.post("/api/auth/login")
def login(payload: LoginPayload, request: Request, response: Response):
    peer = request.client.host if request.client else "unknown"
    login_identity = f"{peer}|{payload.username.strip().casefold()}"
    blocked, retry_after = auth.login_is_blocked(login_identity)
    if blocked:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    user = auth.authenticate(payload.username, payload.password)
    if not user:
        auth.record_login_failure(login_identity)
        raise HTTPException(status_code=401, detail=translate("Invalid username or password.", request.headers.get("x-ui-language")))
    auth.clear_login_failures(login_identity)
    token, csrf, expires = auth.create_session(user["id"])
    response.set_cookie(
        "forex_session", token, httponly=True,
        secure=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        samesite="strict", max_age=auth.SESSION_TTL_SECONDS,
        path="/",
    )
    return {"ok": True, "user": user, "csrf_token": csrf, "expires_at": expires}

@app.get("/api/auth/me")
def auth_me(request: Request):
    user, csrf = current_session(request)
    return {"user": user, "csrf_token": csrf}

@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    require_role(request, "admin", "trader", "analyst", "viewer")
    auth.revoke_session(request.cookies.get("forex_session"))
    response.delete_cookie("forex_session", path="/", httponly=True, secure=os.getenv("COOKIE_SECURE", "true").lower() == "true", samesite="strict")
    return {"ok": True}

@app.get("/api/users")
def users(request: Request):
    require_role(request, "admin")
    return {"users": auth.list_users(), "roles": sorted(auth.ROLES)}

@app.post("/api/users")
def create_user(payload: CreateUserPayload, request: Request):
    require_role(request, "admin")
    try:
        user = auth.add_user(payload.username, payload.password, payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=translate(str(exc), request.headers.get("x-ui-language"))) from exc
    return {"ok": True, "user": user}

@app.patch("/api/users/{user_id}/active")
def change_user_active(user_id: int, active: bool, request: Request):
    actor = require_role(request, "admin")
    try:
        changed = auth.set_user_active(user_id, active, actor_user_id=actor["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=translate(str(exc), request.headers.get("x-ui-language"))) from exc
    if not changed:
        raise HTTPException(status_code=404, detail=translate("User not found.", request.headers.get("x-ui-language")))
    return {"ok": True, "user_id": user_id, "active": active}

@app.get("/api/bots/status")
def bots_status(request: Request):
    user, _ = current_session(request)
    is_admin = user["role"] == "admin"
    return {
        "execution_allowed": False,
        "bots": [
            {
                "id": "signals",
                "name": "Signal Bot",
                "state": "research_only",
                "engine_available": True,
                "market_data_connected": False,
                "endpoint": "/api/market-radar/analyze",
                "execution_allowed": False,
            },
            {
                "id": "manager",
                "name": "Risk Manager Bot",
                "state": "risk_preview_only",
                "engine_available": True,
                "live_positions_connected": False,
                "endpoint": "/api/risk/portfolio-preview",
                "emergency_stop": _emergency_stop_active,
                "execution_allowed": False,
            },
            {
                "id": "users",
                "name": "User Management Bot",
                "state": "admin_controlled" if is_admin else "admin_only",
                "available": is_admin,
                "user_count": len(auth.list_users()) if is_admin else None,
                "endpoint": "/api/users" if is_admin else None,
                "execution_allowed": False,
            },
        ],
    }


@app.get("/api/ftmo/products")
def ftmo_products(request: Request):
    require_role(request, "admin", "trader", "analyst", "viewer")
    return {"products": account_registry.PRODUCTS, "platforms": sorted(account_registry.PLATFORMS),
            "currencies": sorted(account_registry.CURRENCIES)}

@app.get("/api/brokers/search")
def search_brokers(request: Request, q: str = "", limit: int = 30):
    user, _ = current_session(request)
    return {"brokers": broker_directory.search_brokers(user["id"], q, limit)}


@app.get("/api/brokers/servers")
def broker_servers(request: Request, broker: str, platform: str = "mt5", environment: str | None = None):
    user, _ = current_session(request)
    try:
        return {"servers": broker_directory.list_servers(user["id"], broker, platform, environment)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/brokers/servers")
def add_broker_server(payload: BrokerServerPayload, request: Request):
    user = require_role(request, "admin", "trader")
    try:
        server = broker_directory.save_server(
            user["id"], payload.broker_name, payload.platform,
            payload.environment, payload.server_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "server": server}


@app.get("/api/ftmo/accounts")
def ftmo_accounts(request: Request):
    user, _ = current_session(request)
    return {"accounts": account_registry.list_accounts(user["id"])}

@app.post("/api/ftmo/accounts")
def add_ftmo_account(payload: FTMOAccountPayload, request: Request):
    user = require_role(request, "admin", "trader")
    try:
        account = account_registry.add_account(user["id"], payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="This account number is already registered.") from exc
        raise
    return {"ok": True, "account": account}

@app.put("/api/ftmo/accounts/{account_id}")
def update_ftmo_account(account_id: int, payload: FTMOAccountPayload, request: Request):
    user = require_role(request, "admin", "trader")
    try:
        account = account_registry.update_account(user["id"], account_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="This account number is already registered.") from exc
        raise
    if not account:
        raise HTTPException(status_code=404, detail="FTMO account not found.")
    return {"ok": True, "account": account}

@app.patch("/api/ftmo/accounts/{account_id}/active")
def set_ftmo_account_active(account_id: int, active: bool, request: Request):
    user = require_role(request, "admin", "trader")
    if not account_registry.set_account_active(user["id"], account_id, active):
        raise HTTPException(status_code=404, detail="FTMO account not found.")
    return {"ok": True, "account_id": account_id, "active": active}

@app.get("/api/status")
def status(request: Request): 
    require_role(request, "admin", "trader", "analyst", "viewer")
    return {
        "app": "Forex AI Hybrid Scalper",
        "version": "5.2.0",
        "mode": "DEMO / SAFE DEFAULTS",
        "live_trading_enabled": False,
        "emergency_stop": _emergency_stop_active,
        "news_filter_enabled": cfg.news_filter_enabled,
        "news_fail_closed": cfg.news_fail_closed,
        "symbols": cfg.symbols,
        "risk": {
            "assumed_balance_usd": cfg.account_balance_assumption,
            "fx_per_trade": cfg.fx_risk_fraction,
            "gold_per_trade": cfg.gold_risk_fraction,
            "daily_stop": cfg.daily_loss_limit,
        },
        "integrations": {
            "market_data": "not_connected",
            "news_calendar": "example_only",
            "mt5": "not_connected",
            "order_execution": "disabled",
        },
    }


@app.get("/api/news")
def news_feed(request: Request):
    require_role(request, "admin", "trader", "analyst", "viewer")
    # No provider is connected yet: never manufacture example headlines as live news.
    return {
        "available": False,
        "feed_status": "not_connected",
        "articles": [],
        "sentiment": {"positive": 0, "neutral": 0, "negative": 0, "score": None},
        "message": translate("هنوز منبع خبری متصل نشده است.", request.headers.get("x-ui-language")),
    }


@app.get("/api/analytics/overview")
def analytics_overview(request: Request):
    require_role(request, "admin", "trader", "analyst", "viewer")
    # No synthetic figures: real feeds and closed trade history are not connected.
    return {
        "available": False,
        "market_data_status": "not_connected",
        "trade_history_status": "not_connected",
        "fear_greed": {"available": False, "score": None, "label": "unavailable", "components": {}},
        "market_heatmap": [],
        "signal_performance": {
            "available": False, "total_closed": 0, "wins": 0, "losses": 0,
            "win_rate_pct": None, "average_profit": None, "net_profit": None,
            "profit_factor": None, "symbols": [], "heatmap": [],
        },
    }



@app.post("/api/risk/portfolio-preview")
def portfolio_risk_preview(payload: PortfolioRiskPreviewPayload, request: Request):
    require_role(request, "admin", "trader", "analyst")
    try:
        snapshot = PortfolioSnapshot(
            equity_usd=payload.equity_usd,
            positions=tuple(RiskPosition(**item.model_dump()) for item in payload.positions),
            emergency_stop=_emergency_stop_active,
            market_data_valid=payload.market_data_valid,
        )
        proposed = RiskTradeIntent(**payload.proposed_order.model_dump())
        decision = evaluate_portfolio(snapshot, proposed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "available": True,
        "risk_approved": decision.approved,
        "execution_allowed": False,
        "live_positions_connected": False,
        "live_market_data_connected": False,
        "emergency_stop": _emergency_stop_active,
        "reasons": list(decision.reasons),
        "metrics": {
            "total_open_risk_pct": decision.total_open_risk_pct,
            "market_open_risk_pct": decision.market_open_risk_pct,
            "gross_leverage": decision.gross_leverage,
            "margin_usage_pct": decision.margin_usage_pct,
            "instrument_concentration_pct": decision.instrument_concentration_pct,
            "order_liquidity_participation_pct": decision.order_liquidity_participation_pct,
        },
        "note": "Preview only. Inputs are caller-supplied, not verified live account or venue data.",
    }

@app.post("/api/emergency-stop")
def activate_emergency_stop(request: Request):
    require_role(request, "admin", "trader")
    global _emergency_stop_active
    _emergency_stop_active = True
    return {"ok": True, "emergency_stop": True, "message": "Emergency stop latched."}


@app.get("/api/decision-preview")
def decision_preview(request: Request, adx: float = 25, atr_ratio: float = 1.0, symbol: str = "XAUUSD"):
    require_role(request, "admin", "trader", "analyst")
    if symbol not in cfg.symbols:
        raise HTTPException(status_code=400, detail=translate("Symbol is not in the configured universe.", request.headers.get("x-ui-language")))
    regime = choose_regime(adx, atr_ratio, True)
    strategy = choose_strategy(regime)
    allowed, reason = authorize_trade(
        symbol=symbol,
        action="BUY",
        regime=regime,
        news_blocked=True,  # no verified live calendar is connected
        emergency_stop=_emergency_stop_active,
        live_enabled=False,
    )
    return {
        "symbol": symbol,
        "regime": regime,
        "strategy": strategy,
        "execution_allowed": allowed,
        "guard_reason": reason,
        "note": "Illustrative preview only; not a live market signal.",
    }


@app.get("/", response_class=HTMLResponse)
def public_site():
    return SITE_HTML


@app.get("/app", response_class=HTMLResponse)
def dashboard():
    return HTML


@app.get("/manifest.webmanifest")
def pwa_manifest():
    return Response(content=PWA_MANIFEST, media_type="application/manifest+json")


@app.get("/service-worker.js")
def service_worker():
    return Response(content=SERVICE_WORKER, media_type="application/javascript",
                    headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.get("/app-icon.svg")
def app_icon():
    return Response(content=APP_ICON, media_type="image/svg+xml")


@app.get("/offline", response_class=HTMLResponse)
def offline_page():
    return Response(content=OFFLINE_HTML, media_type="text/html")


PWA_MANIFEST = """{
  "id": "/app",
  "name": "Forex AI Hybrid Scalper",
  "short_name": "Forex AI",
  "description": "تحلیل بازار، مدیریت ریسک و مدیریت حساب‌های FTMO",
  "lang": "fa",
  "dir": "rtl",
  "start_url": "/app",
  "scope": "/",
  "display": "standalone",
  "orientation": "any",
  "background_color": "#090e1b",
  "theme_color": "#0b1020",
  "icons": [
    {"src": "/app-icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}
  ]
}"""

APP_ICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#39d6a2"/><stop offset="1" stop-color="#4d83e8"/></linearGradient></defs>
<rect width="512" height="512" rx="116" fill="#0b1020"/><rect x="42" y="42" width="428" height="428" rx="104" fill="url(#g)"/>
<path d="M145 358V154h125c66 0 102 34 102 91 0 42-21 70-59 83l67 30h-94l-54-26h-5v26zm82-96h42c23 0 35-7 35-19s-12-19-35-19h-42z" fill="#071522"/>
</svg>"""

SERVICE_WORKER = """const CACHE = "forex-ai-shell-v2";
const SHELL = ["/", "/app", "/manifest.webmanifest", "/app-icon.svg", "/offline"];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).then(response => {
      if (response.ok && (url.pathname === "/" || url.pathname === "/app")) {
        const copy = response.clone();
        caches.open(CACHE).then(cache => cache.put("/app", copy));
      }
      return response;
    }).catch(async () => (await caches.match(url.pathname)) || (await caches.match("/offline"))));
    return;
  }
  if (SHELL.includes(url.pathname)) {
    event.respondWith(caches.match(request).then(cached => cached || fetch(request)));
  }
});"""

OFFLINE_HTML = """<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#0b1020"><title>آفلاین | Forex AI</title><body style="margin:0;background:#090e1b;color:#edf2fb;font:16px Tahoma,system-ui;display:grid;min-height:100vh;place-items:center;text-align:center"><main><h1>اتصال اینترنت در دسترس نیست</h1><p>پوسته برنامه نصب‌شده در دسترس است؛ برای اطلاعات حساب و داده‌های زنده دوباره متصل شو.</p><a href="/app" style="color:#37d6a0">تلاش دوباره</a></main></body></html>"""

SITE_HTML = r"""<!doctype html>
<html lang="fa" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#090e1b"><meta name="description" content="Forex AI Hybrid Scalper؛ مرکز تحلیل بازار، مدیریت ریسک و حساب‌های FTMO.">
<link rel="manifest" href="/manifest.webmanifest"><link rel="icon" href="/app-icon.svg" type="image/svg+xml">
<title>Forex AI | پلتفرم هوشمند معامله‌گری</title>
<style>
:root{color-scheme:dark;--bg:#090e1b;--panel:#111a2b;--line:#243149;--text:#edf2fb;--muted:#9aa9bf;--green:#37d6a0;--blue:#7c9cff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 75% 5%,#203653 0,transparent 38%),var(--bg);color:var(--text);font:15px/1.8 Tahoma,system-ui,sans-serif}a{color:inherit;text-decoration:none}.wrap{width:min(1160px,calc(100% - 36px));margin:auto}.nav{height:78px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #ffffff16}.brand{display:flex;align-items:center;gap:12px;font-weight:900;letter-spacing:.5px}.logo{width:42px;height:42px;border-radius:14px;background:linear-gradient(135deg,#39d6a2,#4d83e8);display:grid;place-items:center;color:#071522;font-size:22px}.navlinks{display:flex;gap:22px;color:var(--muted);font-size:13px}.actions{display:flex;gap:10px;align-items:center}.btn{display:inline-flex;align-items:center;justify-content:center;border:1px solid #ffffff25;border-radius:12px;padding:10px 17px;font-weight:700}.btn.primary{background:linear-gradient(120deg,#37d6a0,#69a5ff);border:0;color:#071522}.hero{padding:92px 0 72px;display:grid;grid-template-columns:1.05fr .95fr;gap:55px;align-items:center}.tag{display:inline-flex;border:1px solid #37d6a055;background:#37d6a012;color:#70e8be;border-radius:30px;padding:5px 12px;font-size:12px}.hero h1{font-size:clamp(34px,5vw,58px);line-height:1.3;margin:20px 0}.hero p{color:var(--muted);max-width:620px;font-size:17px}.hero-actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:27px}.visual{border:1px solid #ffffff20;border-radius:24px;padding:18px;background:linear-gradient(150deg,#15263b,#111a2b);box-shadow:0 28px 80px #0006}.visual-top{display:flex;justify-content:space-between;color:var(--muted);font-size:12px}.chart{height:230px;width:100%;margin-top:15px}.chart svg{width:100%;height:100%}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:15px}.stat{background:#ffffff08;border:1px solid #ffffff12;border-radius:12px;padding:12px}.stat small{color:var(--muted);display:block}.stat b{font-size:18px}.section{padding:60px 0}.section h2{font-size:30px;margin:0 0 8px}.lead{color:var(--muted);margin:0 0 25px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.feature{background:var(--panel);border:1px solid var(--line);border-radius:17px;padding:22px}.feature .ico{font-size:23px;color:var(--green)}.feature h3{margin:8px 0}.feature p{color:var(--muted);font-size:13px;margin:0}.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.step{padding:20px;border-inline-start:2px solid var(--green);background:#ffffff08;border-radius:12px}.step b{display:block;font-size:17px}.step span{color:var(--muted);font-size:13px}.notice{margin:35px 0;background:#d7a94c12;border:1px solid #d7a94c44;border-radius:14px;padding:17px;color:#e9d5a6;font-size:13px}.footer{border-top:1px solid #ffffff18;padding:25px 0;color:var(--muted);font-size:12px;display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap}
@media(max-width:800px){.navlinks{display:none}.hero{grid-template-columns:1fr;padding:55px 0 35px;gap:30px}.grid{grid-template-columns:1fr 1fr}.steps{grid-template-columns:1fr}.hero h1{font-size:38px}}@media(max-width:520px){.grid{grid-template-columns:1fr}.nav{height:68px}.nav .btn{padding:8px 11px;font-size:12px}.stats{grid-template-columns:1fr 1fr 1fr}.stat b{font-size:15px}}

.bot-grid{grid-template-columns:repeat(auto-fit,minmax(245px,1fr));margin-top:14px}.bot-card{display:flex;flex-direction:column;gap:12px;min-height:265px}.bot-card h3{margin:0;font-size:17px}.bot-card p{color:var(--muted);font-size:12px;line-height:1.9;margin:0;min-height:64px}.bot-card-head{display:flex;align-items:center;justify-content:space-between}.bot-facts{display:grid;gap:7px;padding:12px;border:1px solid #ffffff12;border-radius:12px;background:#07132255;font-size:11px;color:var(--muted);margin-top:auto}.bot-facts b{color:var(--text)}.bot-card button{margin-top:3px}.bot-restricted{opacity:.72}
/* Secure control-center visual system refresh */
:root{--bg:#080f1d;--panel:#101b2d;--panel2:#15243a;--line:#263a54;--text:#eff5ff;--muted:#9aabc2;--green:#36d9a4;--blue:#79a7ff;--red:#ff6f7d;--shadow:0 18px 55px #02081766}
body{background:radial-gradient(ellipse at 78% -8%,#1d4260 0,transparent 36%),radial-gradient(ellipse at 5% 35%,#17334a55 0,transparent 32%),var(--bg)}
.card{border:1px solid color-mix(in srgb,var(--line) 86%,transparent);border-radius:19px;box-shadow:0 10px 30px #02081722;transition:border-color .2s,transform .2s,box-shadow .2s}
.card:hover{border-color:#3b5878;box-shadow:var(--shadow)}
.sidebar{background:linear-gradient(180deg,#0d192a,#0a1423);border-inline-end:1px solid #ffffff12}
.brand .logo{box-shadow:0 7px 24px #39d6a233}
.nav button{border:1px solid transparent;border-radius:12px;transition:background .18s,border-color .18s,color .18s}
.nav button:hover{background:#1a2b42;border-color:#ffffff12}.nav button.active{background:linear-gradient(100deg,#1d594e66,#274a7555);border-color:#3bd8a355;color:#eafff7;box-shadow:inset 3px 0 0 var(--green)}
.topbar{backdrop-filter:blur(16px);background:#0a1424d9;border-bottom:1px solid #ffffff12}
.hero{border:1px solid #3bd8a333;background:radial-gradient(circle at 85% 15%,#36d9a41c,transparent 35%),linear-gradient(120deg,#142b3c,#17243c 65%,#1c2d48);border-radius:22px;box-shadow:var(--shadow)}
.metric-value{letter-spacing:-.04em;font-variant-numeric:tabular-nums}.metric-icon{border:1px solid #ffffff14;border-radius:12px;background:#ffffff08}
.field{border:1px solid #334963;background:#0b1728;color:var(--text);border-radius:12px;min-height:44px;transition:border-color .2s,box-shadow .2s}.field:focus{outline:none;border-color:var(--green);box-shadow:0 0 0 3px #36d9a422}
button.primary{border:1px solid #54e0b5;background:linear-gradient(110deg,#1aa982,#168b91);border-radius:12px;box-shadow:0 8px 22px #159d7a33;font-weight:800}button.primary:hover{filter:brightness(1.08);transform:translateY(-1px)}button:disabled{opacity:.58;cursor:wait;transform:none!important}
.pill{border:1px solid #ffffff16;background:#ffffff08;border-radius:999px;padding:5px 10px}.pill.ok{border-color:#36d9a455;background:#36d9a414;color:#7ce8c2}
.login-wrap{width:min(480px,calc(100% - 32px));max-width:none;margin:7vh auto 4vh;position:relative}
.login-wrap:before{content:"";position:absolute;inset:-55px -70px;z-index:-1;background:radial-gradient(ellipse,#1b536044,transparent 68%);filter:blur(18px);pointer-events:none}
.login-brand{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:22px}.login-secure{font-size:11px;color:var(--muted);display:flex;align-items:center;gap:7px}.login-secure i{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 12px #36d9a4}
.login-card{padding:clamp(22px,5vw,34px);border-radius:23px;background:linear-gradient(150deg,#15243a,#0f1a2c 65%);box-shadow:0 28px 80px #02081788;border-color:#40577788}
.login-topline{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:22px}.login-topline .field{width:auto;min-width:110px;padding:7px 10px}.login-card h2{font-size:25px;letter-spacing:-.5px;margin:0 0 7px}.login-card>p{color:var(--muted);font-size:13px;margin:0 0 24px}.login-label{display:block;color:#c5d2e5;font-size:12px;font-weight:700;margin:14px 0 7px}.login-card .field{width:100%;padding:12px 14px}.login-submit{width:100%;display:flex;align-items:center;justify-content:space-between;padding:13px 16px;margin-top:20px}.login-message{min-height:26px;margin-top:12px;color:var(--muted)}.login-message:not(:empty){font-size:12px}.login-foot{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;border-top:1px solid #ffffff14;margin-top:20px;padding-top:15px;color:var(--muted);font-size:10px}.login-foot span:first-child{color:#7ce8c2}.login-caption{text-align:center;color:#8294ad;font-size:11px;margin:17px 0}
@media(max-width:760px){.shell{display:block}.sidebar{position:relative;width:100%;height:auto}.nav{display:flex;overflow-x:auto;gap:7px;padding-bottom:9px}.nav button{white-space:nowrap;min-width:max-content}.side-bottom{display:none}main{padding:12px}.topbar{position:relative;gap:12px;flex-wrap:wrap}.top-actions{width:100%;flex-wrap:wrap}.login-wrap{margin:5vh auto 3vh}.hero{padding:20px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
</style></head><body>
<header class="wrap nav"><a class="brand" href="/"><span class="logo">F</span><span>FOREX AI<small style="display:block;color:#9aa9bf;font-size:9px;letter-spacing:2px">HYBRID SCALPER</small></span></a>
<nav class="navlinks"><a href="#features">امکانات</a><a href="#ftmo">مدیریت FTMO</a><a href="#how">نحوه استفاده</a></nav>
<div class="actions"><button class="btn" id="install" hidden>نصب اپلیکیشن</button><a class="btn primary" href="/app" aria-label="ورود کاربران">ورود کاربران</a></div></header>
<main class="wrap"><section class="hero"><div><span class="tag">● پلتفرم تحلیل و مدیریت ریسک</span><h1>معامله‌گری هوشمند،<br><span style="color:#6fe5b8">با کنترل ریسک در اولویت</span></h1><p>یک فضای کاری یکپارچه برای تحلیل بازار، بررسی سیگنال‌ها، مدیریت حساب‌های FTMO و پایش عملکرد؛ با نمایش شفاف وضعیت اتصال داده‌ها و کنترل‌های ایمنی.</p><div class="hero-actions"><a class="btn primary" href="/app">ورود به داشبورد</a><a class="btn" href="#features">مشاهده امکانات</a></div></div>
<div class="visual"><div class="visual-top"><span>FOREX AI · MARKET WORKSPACE</span><span style="color:#e9bd68">SAFE MODE</span></div><div class="chart"><svg viewBox="0 0 600 250" preserveAspectRatio="none" aria-label="نمودار تزئینی"><defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#37d6a0" stop-opacity=".35"/><stop offset="1" stop-color="#37d6a0" stop-opacity="0"/></linearGradient></defs><path d="M0 190 L45 172 85 180 130 130 170 150 215 105 255 126 300 80 345 105 390 70 430 95 475 45 520 65 560 25 600 40 L600 250 L0 250Z" fill="url(#fill)"/><path d="M0 190 L45 172 85 180 130 130 170 150 215 105 255 126 300 80 345 105 390 70 430 95 475 45 520 65 560 25 600 40" fill="none" stroke="#37d6a0" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg></div><div class="stats"><div class="stat"><small>حساب‌های FTMO</small><b>چندگانه</b></div><div class="stat"><small>مدیریت ریسک</small><b>قانون‌محور</b></div><div class="stat"><small>اجرای زنده</small><b style="color:#e9bd68">خاموش</b></div></div></div></section>
<section class="section" id="features"><h2>ابزارهای یکپارچه</h2><p class="lead">همه‌چیز در یک پنل، با وضعیت واقعی و بدون اعداد ساختگی.</p><div class="grid">
<article class="feature"><div class="ico">⌁</div><h3>تحلیل بازار</h3><p>آماده برای اتصال فید قیمت، ساختار بازار و تحلیل چندلایه؛ تا زمان اتصال، داده زنده جعل نمی‌شود.</p></article>
<article class="feature"><div class="ico">◎</div><h3>مدیریت حساب FTMO</h3><p>ثبت چند حساب، محصول، مرحله، نوع حساب، سرمایه و پلتفرم با جداسازی اطلاعات هر کاربر.</p></article>
<article class="feature"><div class="ico">◇</div><h3>هوش مصنوعی ترکیبی</h3><p>ترکیب ماژول‌های تحلیل، فیلترهای ریسک و پیش‌نمایش تصمیم؛ بدون ارسال خودکار سفارش.</p></article>
<article class="feature"><div class="ico">▤</div><h3>اخبار و رویدادها</h3><p>جایگاه آماده برای خبر و تقویم اقتصادی؛ اتصال منبع معتبر پیش از نمایش رویدادهای زنده ضروری است.</p></article>
<article class="feature"><div class="ico">▦</div><h3>عملکرد و آمار</h3><p>نرخ برد، سود میانگین، رتبه نمادها و نقشه حرارتی پس از اتصال تاریخچه معاملات بسته‌شده.</p></article>
<article class="feature"><div class="ico">▣</div><h3>اپلیکیشن قابل نصب</h3><p>نسخه PWA برای افزودن به صفحه اصلی اندروید و دسکتاپ؛ پوسته در حالت آفلاین نیز در دسترس می‌ماند.</p></article>
</div></section>
<section class="section" id="ftmo"><h2>حساب‌های FTMO خودت را مدیریت کن</h2><p class="lead">هر حساب تنظیمات و مرحله مخصوص خود را دارد.</p><div class="steps"><div class="step"><b>۱. افزودن حساب</b><span>نام، شناسه اختیاری، سرمایه و ارز را وارد کن.</span></div><div class="step"><b>۲. انتخاب محصول و مرحله</b><span>1-Step، 2-Step، Instant، Futures یا Free Trial بر اساس گزینه‌های پشتیبانی‌شده.</span></div><div class="step"><b>۳. انتخاب نوع حساب</b><span>Standard، Swing یا نوع متناسب با محصول.</span></div></div></section>
<div class="notice">این پلتفرم ابزار تحلیل و مدیریت است، نه تضمین سود. حساب‌های FTMO از محیط شبیه‌سازی استفاده می‌کنند. اتصال داده زنده، اعتبارسنجی قوانین جاری و آزمون روی حساب آزمایشی باید پیش از هرگونه اجرای واقعی تکمیل شود. در نسخه فعلی ارسال سفارش واقعی غیرفعال است.</div></main>
<footer class="wrap footer"><span>© Forex AI Hybrid Scalper</span><span>محیط امن · تحلیل و مدیریت ریسک · بدون تضمین سود</span><a href="/app">ورود به پنل</a></footer>
<script>
let installPrompt;const installButton=document.getElementById("install");
window.addEventListener("beforeinstallprompt",event=>{event.preventDefault();installPrompt=event;installButton.hidden=false;});
installButton.addEventListener("click",async()=>{if(!installPrompt)return;installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;installButton.hidden=true;});
if("serviceWorker" in navigator){window.addEventListener("load",()=>navigator.serviceWorker.register("/service-worker.js").catch(()=>{}));}
</script></body></html>""";


HTML = r"""
<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b1020">
<meta name="description" content="Forex AI Hybrid Scalper — داشبورد تحلیل بازار، مدیریت ریسک و حساب‌های FTMO.">
<link rel="manifest" href="/manifest.webmanifest"><link rel="icon" href="/app-icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/app-icon.svg">
<title>Forex AI | مرکز هوشمند معاملات</title>
<style>
:root{color-scheme:dark;--bg:#090e1b;--panel:#111a2b;--panel2:#151f33;--line:#243149;--text:#edf2fb;--muted:#91a0b8;--green:#37d6a0;--red:#ff6d7a;--gold:#e9bd68;--blue:#7c9cff;--shadow:0 18px 50px #0003}
:root.light{color-scheme:light;--bg:#f3f6fb;--panel:#fff;--panel2:#f7f9fd;--line:#e3e9f2;--text:#172238;--muted:#687790;--green:#079b70;--red:#dc4658;--gold:#a87820;--blue:#496bd4;--shadow:0 14px 40px #25385812}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.7 Vazirmatn,Tahoma,system-ui,sans-serif;transition:background .2s,color .2s}
button,input,select{font:inherit}button{cursor:pointer}.shell{min-height:100vh;display:grid;grid-template-columns:250px minmax(0,1fr)}
.sidebar{background:var(--panel);border-inline-end:1px solid var(--line);padding:24px 16px;display:flex;flex-direction:column;gap:24px;position:sticky;top:0;height:100vh}
.brand{display:flex;align-items:center;gap:11px;padding:0 8px}.logo{width:39px;height:39px;border-radius:13px;background:linear-gradient(135deg,#39d6a2,#4d83e8);display:grid;place-items:center;color:#071522;font-weight:1000;font-size:19px}.brand strong{font-size:16px;letter-spacing:.2px}.brand small{display:block;color:var(--muted);font-size:10px;direction:ltr;text-align:right}
.nav-title{font-size:10px;color:var(--muted);padding:0 12px;margin-bottom:-14px}.nav{display:grid;gap:5px}.nav button{display:flex;align-items:center;gap:12px;text-align:start;color:var(--muted);background:transparent;border:1px solid transparent;padding:11px 13px;border-radius:11px}.nav button.active,.nav button:hover{background:var(--panel2);border-color:var(--line);color:var(--text)}.nav .ico{width:21px;text-align:center;font-size:16px}
.side-bottom{margin-top:auto}.safe{padding:13px;border:1px solid #269b7950;background:#159b7010;border-radius:13px;color:var(--green);font-size:12px}.safe b{display:block;font-size:13px;margin-bottom:3px}
main{min-width:0;padding:25px clamp(14px,3vw,38px) 42px;max-width:1600px;width:100%;margin:auto}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:23px}.eyebrow{color:var(--muted);font-size:12px}.heading{font-size:24px;font-weight:850;margin:2px 0}.top-actions{display:flex;align-items:center;gap:9px}.icon-btn,.ghost{border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:11px;padding:9px 12px}.user-chip{display:flex;align-items:center;gap:9px;border:1px solid var(--line);background:var(--panel);padding:6px 11px;border-radius:12px}.avatar{width:30px;height:30px;border-radius:10px;background:#243d5a;color:#a9c7ff;display:grid;place-items:center;font-weight:800}
.market-strip{display:flex;gap:10px;overflow:auto;margin-bottom:17px;padding-bottom:3px}.ticker{min-width:150px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 13px}.ticker small{color:var(--muted);display:block}.ticker b{direction:ltr;display:block;text-align:right;font-size:14px}.ticker em{font-style:normal;font-size:11px;color:var(--muted)}
.hero{background:linear-gradient(112deg,#172d3a,#17233c 58%,#28284a);border:1px solid #354866;border-radius:18px;padding:22px 24px;display:flex;justify-content:space-between;align-items:center;gap:18px;overflow:hidden;position:relative}.hero:after{content:"";position:absolute;width:260px;height:260px;border:1px solid #ffffff12;border-radius:50%;left:10%;top:-170px;box-shadow:0 0 0 35px #ffffff08,0 0 0 70px #ffffff05}.hero h2{font-size:19px;margin:0 0 5px}.hero p{margin:0;color:#b9c8dc;font-size:12px}.hero .hero-tag{position:relative;z-index:1;border:1px solid #56d6ad66;background:#2cba8b20;color:#8df0ce;padding:8px 13px;border-radius:30px;white-space:nowrap;font-size:12px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin-top:16px}.card{background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:17px;box-shadow:var(--shadow);min-width:0}.metric-top{display:flex;align-items:center;justify-content:space-between;color:var(--muted);font-size:12px}.metric-icon{width:32px;height:32px;border-radius:10px;background:var(--panel2);display:grid;place-items:center;font-size:15px}.metric-value{font-size:25px;font-weight:850;direction:ltr;text-align:right;margin:8px 0 1px;line-height:1.4}.metric-foot{font-size:11px;color:var(--muted)}.green{color:var(--green)}.red{color:var(--red)}.gold{color:var(--gold)}
.content-grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(270px,.85fr);gap:14px;margin-top:14px}.section-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}.section-head h3{margin:0;font-size:15px}.section-head small{color:var(--muted)}
.chart-wrap{height:210px;position:relative;border-radius:10px;background:linear-gradient(180deg,#30bd9510,transparent)}.chart-wrap svg{width:100%;height:100%;overflow:visible}.chart-labels{display:flex;justify-content:space-between;color:var(--muted);font-size:10px;margin-top:4px;direction:ltr}
.signal{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 0;border-bottom:1px solid var(--line)}.signal:last-child{border:0}.pair{display:flex;align-items:center;gap:9px}.coin{width:34px;height:34px;border-radius:11px;background:var(--panel2);display:grid;place-items:center;font-weight:800;color:var(--gold)}.pair b{display:block;font-size:13px}.pair small{color:var(--muted);font-size:10px}.signal-side{text-align:left;direction:ltr}.signal-side b{display:block}.signal-side small{font-size:10px;color:var(--muted)}
.pill{font-size:10px;padding:4px 8px;border-radius:20px;background:#e7b74a18;color:var(--gold);border:1px solid #e7b74a35}.pill.ok{background:#25bd8b16;color:var(--green);border-color:#25bd8b35}
.modules{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:14px}.module{padding:13px;border:1px solid var(--line);background:var(--panel);border-radius:13px}.module b{display:block;font-size:12px}.module small{color:var(--muted);font-size:10px}
.actions{display:flex;gap:9px;flex-wrap:wrap;align-items:center}.primary{background:linear-gradient(135deg,#21bd8d,#178b77);border:0;color:#041b19;padding:10px 16px;border-radius:10px;font-weight:800}.danger{background:#a83243;color:#fff;border:0;padding:10px 15px;border-radius:10px;font-weight:800}.field{background:var(--panel2);border:1px solid var(--line);border-radius:10px;color:var(--text);padding:10px 12px;min-width:0}
.notice{background:#e9b74b12;border:1px solid #e9b74b35;color:var(--gold);padding:12px 14px;border-radius:12px;font-size:11px;margin-top:14px}
.page{display:none}.page.active{display:block}.login-wrap{max-width:420px;margin:8vh auto}.login-card{padding:26px}.login-card h2{margin:0 0 6px}.login-card p{color:var(--muted);font-size:12px;margin:0 0 20px}.login-card input{width:100%;margin:6px 0}.login-card button{width:100%;margin-top:10px}.status{margin-top:10px;color:var(--muted);font-size:12px;min-height:20px}
.user-row{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:11px 0;border-bottom:1px solid var(--line)}.user-row:last-child{border:0}
footer{color:var(--muted);font-size:10px;margin-top:18px;line-height:1.9}
@media(max-width:1050px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.content-grid{grid-template-columns:1fr}}
@media(max-width:700px){.shell{display:block}.sidebar{position:static;height:auto;padding:13px;border-left:0;border-bottom:1px solid var(--line);gap:12px}.brand{padding:0 5px}.nav-title,.side-bottom{display:none}.nav{display:flex;overflow:auto}.nav button{white-space:nowrap;padding:8px 10px}.nav .ico{display:none}main{padding:17px 12px 30px}.heading{font-size:20px}.hero{padding:17px;align-items:flex-start;flex-direction:column}.hero .hero-tag{white-space:normal}.grid{gap:9px}.card{padding:13px}.metric-value{font-size:21px}.modules{grid-template-columns:repeat(2,minmax(0,1fr))}.topbar{margin-bottom:15px}}

/* Lively visual refresh: aurora accents, richer surfaces and gentle motion */
:root{
 --bg:#080d1c;--panel:#101a30;--panel2:#172541;--line:#2b3b5e;
 --text:#f2f6ff;--muted:#9cacc8;--green:#42efbd;--red:#ff718c;
 --gold:#ffd27a;--blue:#8ba7ff;--shadow:0 18px 48px #02081780;
}
:root.light{
 --bg:#f0f4fc;--panel:#ffffff;--panel2:#f0f4ff;--line:#dce5f5;
 --text:#17223c;--muted:#687a9a;--green:#079d7b;--red:#db4968;
 --gold:#a97517;--blue:#4e6ed5;--shadow:0 14px 38px #38558a18;
}
body{
 background:
  radial-gradient(ellipse at 12% 8%,#6945c51c,transparent 34%),
  radial-gradient(ellipse at 88% 22%,#13c9a51a,transparent 30%),
  radial-gradient(ellipse at 65% 95%,#4774e818,transparent 32%),var(--bg);
}
.sidebar{background:linear-gradient(180deg,var(--panel),color-mix(in srgb,var(--panel) 88%,#5b4baf 12%));}
.logo{background:linear-gradient(135deg,#48f0c1 0%,#55a6ff 52%,#a77bff 100%);box-shadow:0 0 25px #4bdcbe55,0 0 42px #8871ff22;}
.brand strong{background:linear-gradient(90deg,#59e8c4,#9aabff);-webkit-background-clip:text;background-clip:text;color:transparent;}
.nav button{transition:background .2s,border-color .2s,transform .2s,color .2s}
html[dir=rtl] .nav button:hover{transform:translateX(-3px)}html[dir=ltr] .nav button:hover{transform:translateX(3px)}
.nav button.active{background:linear-gradient(100deg,#36dcb21d,#7b75ef20);border-color:#50d8c35c;box-shadow:inset -3px 0 #54e2c0;color:var(--text)}
.hero{
 background:linear-gradient(112deg,#102c3b 0%,#19264a 48%,#39265a 100%);
 border:1px solid #5c78a8a6;box-shadow:0 18px 55px #101c3d70;
}
.hero:before{content:"";position:absolute;inset:-80% -30%;background:linear-gradient(110deg,transparent 40%,#ffffff0c 50%,transparent 60%);transform:translateX(-55%);animation:auroraSweep 9s ease-in-out infinite}
.hero:after{border-color:#83ffe51a;box-shadow:0 0 0 35px #8d86ff0b,0 0 0 70px #56e9c007}
.hero h2{background:linear-gradient(90deg,#fff,#a9f5e5 55%,#c7c2ff);-webkit-background-clip:text;background-clip:text;color:transparent}
.hero .hero-tag{box-shadow:0 0 24px #43e9bb22}
.card,.ticker,.module{transition:transform .22s ease,border-color .22s ease,box-shadow .22s ease}
.card:hover,.ticker:hover,.module:hover{transform:translateY(-3px);border-color:#6684bd88;box-shadow:0 18px 42px #02081755}
.metric-icon{background:linear-gradient(135deg,#32dcb31c,#8c7bff25);border:1px solid #7a8de52c;color:#8debd8}
.metric-value{background:linear-gradient(100deg,var(--text),#82dcca);-webkit-background-clip:text;background-clip:text;color:transparent}
.metric-value.red{background:linear-gradient(90deg,#ff8395,#ffb0c0);-webkit-background-clip:text;background-clip:text}
.ticker{background:linear-gradient(145deg,var(--panel),color-mix(in srgb,var(--panel) 85%,#5368b7 15%))}
.ticker b{color:var(--green)}
.pill.ok{box-shadow:0 0 15px #37d6a022}
.primary{background:linear-gradient(110deg,#38e2b4,#39b9d6 55%,#7f83f5);box-shadow:0 7px 22px #36cdb34a;transition:transform .2s,filter .2s}
.primary:hover{transform:translateY(-2px);filter:brightness(1.08)}
.danger{box-shadow:0 7px 22px #d83e5940}
.chart-wrap{background:radial-gradient(ellipse at 50% 100%,#36d6a018,transparent 70%),linear-gradient(180deg,#30bd9510,transparent)}
.module{background:linear-gradient(145deg,var(--panel),color-mix(in srgb,var(--panel) 90%,#7569d8 10%))}
.module b{color:var(--blue)}
.safe{box-shadow:inset 0 0 25px #159b7010}
@keyframes auroraSweep{0%,100%{transform:translateX(-55%) rotate(0deg)}50%{transform:translateX(55%) rotate(0deg)}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
@media(max-width:700px){.nav button.active{box-shadow:inset 0 -3px #54e2c0}.nav button:hover{transform:none}.card:hover,.ticker:hover,.module:hover{transform:none}}

.table-wrap{width:100%;overflow-x:auto;margin-top:12px}.data-table{width:100%;border-collapse:collapse;min-width:620px;text-align:start}.data-table th,.data-table td{padding:11px 13px;border-bottom:1px solid var(--line);white-space:nowrap}.data-table th{color:var(--muted);font-size:11px;font-weight:700}.data-table td{font-size:12px}.data-table tbody tr:hover{background:var(--panel2)}
</style>
</head>
<body>
<section id="login-screen" class="login-wrap">
 <div class="login-brand"><div class="brand"><div class="logo">F</div><div><strong>FOREX AI</strong><small>HYBRID SCALPER</small></div></div><span class="login-secure"><i></i> اتصال رمزگذاری‌شده</span></div>
 <form id="login-form" class="card login-card" onsubmit="login(event)" autocomplete="on">
  <div class="login-topline"><span class="eyebrow">SECURE WORKSPACE</span><select id="login-language" class="field" aria-label="Language" onchange="setLanguage(this.value)"><option value="fa">فارسی</option><option value="en">English</option><option value="ar">العربية</option><option value="tr">Türkçe</option></select></div>
  <h2>به فضای کاری امن خوش آمدید</h2><p>برای ادامه، مشخصات حساب خود را وارد کنید.</p>
  <label class="login-label" for="login-user">نام کاربری</label><input class="field" id="login-user" name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required minlength="3" maxlength="64" placeholder="نام کاربری">
  <label class="login-label" for="login-pass">رمز عبور</label><input class="field" id="login-pass" name="password" type="password" autocomplete="current-password" required maxlength="256" placeholder="رمز عبور">
  <button class="primary login-submit" id="login-submit" type="submit"><span>ورود امن به پنل</span><span aria-hidden="true">↗</span></button>
  <div id="login-message" class="status login-message" role="status" aria-live="polite">حساب کاربری خود را وارد کنید.</div>
  <div class="login-foot"><span>● معاملات واقعی غیرفعال</span><span>محافظت نشست و محدودیت تلاش ورود</span></div>
 </form>
 <p class="login-caption">دسترسی فقط برای کاربران مجاز · هرگز رمز حساب بروکر را اینجا وارد نکنید.</p>
</section>
<div id="app-shell" class="shell" hidden>
<aside class="sidebar">
 <div class="brand"><div class="logo">F</div><div><strong>FOREX AI</strong><small>HYBRID SCALPER</small></div></div>
 <div class="nav-title">فضای کاری</div>
 <nav class="nav">
  <button class="active" data-page="overview" onclick="goPage('overview',this)"><span class="ico">▦</span>نمای کلی</button>
  <button data-page="signals" onclick="goPage('signals',this)"><span class="ico">⌁</span>سیگنال‌ها</button>
  <button data-page="market-radar" onclick="goPage('market-radar',this)"><span class="ico">⌖</span>رادار بازار</button>
  <button data-page="backtest" onclick="goPage('backtest',this)"><span class="ico">▧</span>آزمایشگاه بک‌تست</button>
  <button data-page="sltp" onclick="goPage('sltp',this)"><span class="ico">⇅</span>مدیریت هوشمند SL/TP</button>
  <button data-page="mt5" onclick="goPage('mt5',this)"><span class="ico">◉</span>اتصال زنده MT5</button>
  <button data-page="news" onclick="goPage(&quot;news&quot;,this)"><span class="ico">▤</span>خبرها</button>
  <button data-page="performance" onclick="goPage(&quot;performance&quot;,this)"><span class="ico">▥</span>عملکرد و نبض بازار</button>
  <button data-page="analysis" onclick="goPage('analysis',this)"><span class="ico">◫</span>تحلیل بازار</button>
  <button data-page="simulator" onclick="goPage('simulator',this)"><span class="ico">◉</span>شبیه‌ساز</button>
  <button data-page="modules" onclick="goPage('modules',this)"><span class="ico">◇</span>مرکز ربات‌ها</button>
  <button data-page="ftmo" onclick="goPage('ftmo',this)"><span class="ico">◎</span>حساب‌های FTMO</button>
  <button id="users-nav" data-page="users" onclick="goPage('users',this)" hidden><span class="ico">♙</span>مدیریت کاربران</button>
 </nav>
 <div class="side-bottom"><div class="safe"><b>● حالت امن فعال</b>معاملات واقعی غیرفعال هستند.</div></div>
</aside>
<main>
 <header class="topbar"><div><div class="eyebrow">مرکز کنترل / <span id="crumb">نمای کلی</span></div><div class="heading" id="page-title">داشبورد معاملاتی</div></div>
 <div class="top-actions"><button class="ghost" id="install-app" hidden onclick="installPwa()">نصب اپلیکیشن</button><select id="language-select" class="field" aria-label="Language" onchange="setLanguage(this.value)"><option value="fa">فارسی</option><option value="en">English</option><option value="ar">العربية</option><option value="tr">Türkçe</option></select><button class="icon-btn" onclick="toggleTheme()" title="تغییر پوسته">◐</button><div class="user-chip"><div class="avatar" id="avatar">U</div><div><b id="account-label">کاربر</b><div class="eyebrow" id="role-label">عضو</div></div></div><button class="ghost" onclick="logout()">خروج</button></div></header>
 <div class="market-strip"><div class="ticker"><small>EUR / USD</small><b>—</b><em>داده زنده متصل نیست</em></div><div class="ticker"><small>GBP / USD</small><b>—</b><em>داده زنده متصل نیست</em></div><div class="ticker"><small>USD / JPY</small><b>—</b><em>داده زنده متصل نیست</em></div><div class="ticker"><small>GOLD / XAU</small><b>—</b><em>داده زنده متصل نیست</em></div></div>
 <section id="page-overview" class="page active">
  <div class="hero"><div><h2>تصمیم‌گیری هوشمند، با کنترل کامل ریسک</h2><p>تحلیل چندلایه بازار و مدیریت سرمایه در یک فضای کاری یکپارچه</p></div><span class="hero-tag">● محیط آزمایشی · بدون اجرای سفارش</span></div>
  <div class="grid">
   <article class="card"><div class="metric-top"><span>سرمایه فرضی</span><span class="metric-icon">◈</span></div><div class="metric-value">$500</div><div class="metric-foot">برای محاسبات آزمایشی</div></article>
   <article class="card"><div class="metric-top"><span>ریسک هر معامله FX</span><span class="metric-icon">⌁</span></div><div class="metric-value">0.25%</div><div class="metric-foot">طلا: 0.10%</div></article>
   <article class="card"><div class="metric-top"><span>حد توقف زیان روزانه</span><span class="metric-icon">◇</span></div><div class="metric-value">1.00%</div><div class="metric-foot">محدودیت پیکربندی‌شده</div></article>
   <article class="card"><div class="metric-top"><span>اجرای معاملات</span><span class="metric-icon">◉</span></div><div class="metric-value red">خاموش</div><div class="metric-foot">اتصال بروکر برقرار نیست</div></article>
  </div>
  <div class="content-grid">
   <article class="card"><div class="section-head"><h3>نمای تحلیلی بازار</h3><span class="pill">نمونه نمایشی</span></div>
    <div class="chart-wrap"><svg viewBox="0 0 700 210" preserveAspectRatio="none" aria-label="نمودار تزئینی نمونه"><defs><linearGradient id="area" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#37d6a0" stop-opacity=".25"/><stop offset="1" stop-color="#37d6a0" stop-opacity="0"/></linearGradient></defs><g stroke="currentColor" opacity=".09"><path d="M0 35H700M0 85H700M0 135H700M0 185H700"/></g><path d="M0 155 C35 150 45 115 80 125 S125 160 160 130 S205 105 240 118 S285 70 320 92 S360 130 400 98 S450 115 480 72 S530 85 560 55 S610 95 640 45 S675 50 700 25 L700 210 L0 210Z" fill="url(#area)"/><path d="M0 155 C35 150 45 115 80 125 S125 160 160 130 S205 105 240 118 S285 70 320 92 S360 130 400 98 S450 115 480 72 S530 85 560 55 S610 95 640 45 S675 50 700 25" fill="none" stroke="#37d6a0" stroke-width="3" vector-effect="non-scaling-stroke"/></svg></div><div class="chart-labels"><span>09:00</span><span>11:00</span><span>13:00</span><span>15:00</span><span>17:00</span></div><div class="notice">این نمودار صرفاً نمونه رابط کاربری است و از قیمت یا داده بازار دریافت نشده است.</div>
   </article>
   <article class="card"><div class="section-head"><h3>وضعیت سیستم</h3><span class="pill ok">محیط امن</span></div><div class="signal"><div class="pair"><div class="coin">AI</div><div><b>موتور تحلیل</b><small>قابل استفاده در حالت آزمایشی</small></div></div><span class="pill ok">آماده</span></div><div class="signal"><div class="pair"><div class="coin">N</div><div><b>فیلتر اخبار</b><small>منبع زنده متصل نیست</small></div></div><span class="pill">محدود</span></div><div class="signal"><div class="pair"><div class="coin">MT</div><div><b>اتصال MT5</b><small>اتصال برقرار نشده</small></div></div><span class="pill">قطع</span></div><div class="signal"><div class="pair"><div class="coin">EX</div><div><b>اجرای سفارش</b><small>در این نسخه خاموش است</small></div></div><span class="pill">غیرفعال</span></div><div id="status" class="status">در حال دریافت وضعیت...</div></article>
  </div>
  <div class="card" style="margin-top:14px"><div class="section-head"><h3>کنترل اضطراری</h3><small>دسترسی محدود به مدیر و معامله‌گر</small></div><div class="actions"><button id="stop" class="danger" onclick="activateStop()">فعال‌سازی توقف اضطراری</button><button class="ghost" onclick="refreshStatus()">به‌روزرسانی وضعیت</button></div><div id="toast" class="status"></div></div>
 </section>
 <section id="page-market-radar" class="page">
  <div class="card">
   <div class="section-head"><h3>رادار بازار · تحلیل کندل‌های واردشده</h3><span class="pill">تحقیقاتی · بدون اجرای سفارش</span></div>
   <p class="eyebrow">۳۰ تا ۱۰۰۰ کندل تکمیل‌شده را از منبع معتبر خود وارد کن. این بخش خودش قیمت زنده دریافت نمی‌کند و کامل‌بودن کندل‌ها را باید منبع داده تضمین کند.</p>
   <div class="actions">
    <input id="radar-symbol" class="field" value="EURUSD" maxlength="32" aria-label="نماد" placeholder="نماد مانند EURUSD">
    <input id="radar-timeframe" class="field" value="M15" maxlength="16" aria-label="تایم‌فریم" placeholder="تایم‌فریم مانند M15">
   </div>
   <label for="radar-candles" class="eyebrow">دادهٔ کندل‌ها در قالب JSON (هر کندل: timestamp, open, high, low, close, volume)</label>
   <textarea id="radar-candles" class="field" rows="9" style="width:100%;font-family:monospace;direction:ltr;text-align:left" spellcheck="false" placeholder='[{"timestamp":"2026-11-02T10:00:00Z","open":1.1,"high":1.101,"low":1.099,"close":1.1005,"volume":120}]'></textarea>
   <div class="actions" style="margin-top:12px"><button class="primary" id="radar-run" onclick="runMarketRadar()">تحلیل کندل‌ها</button><button class="ghost" onclick="document.getElementById('radar-candles').value=''">پاک‌کردن داده</button></div>
   <div id="radar-message" class="status" aria-live="polite">برای تحلیل، دادهٔ واقعی و تکمیل‌شده وارد کن.</div>
   <div id="radar-result" class="grid" style="margin-top:14px" hidden>
    <article class="card"><div class="metric-foot">روند</div><div class="metric-value" id="radar-trend">—</div></article>
    <article class="card"><div class="metric-foot">مومنتوم RSI 14</div><div class="metric-value" id="radar-rsi">—</div></article>
    <article class="card"><div class="metric-foot">نوسان ATR ٪</div><div class="metric-value" id="radar-atr">—</div></article>
    <article class="card"><div class="metric-foot">جهت‌گیری پژوهشی</div><div class="metric-value" id="radar-stance">—</div></article>
   </div>
   <div class="notice">خروجی صرفاً تحلیل تکنیکی است، نه توصیه سرمایه‌گذاری یا سیگنال اجرایی. تا زمان اتصال فید معتبر، اعداد را دستی/از منبع خودت وارد کن. اجرای زنده همچنان غیرفعال است.</div>
  </div>
 </section>
 <section id="page-sltp" class="page">
  <div class="card">
   <div class="section-head"><h3>محاسبه‌گر هوشمند حدضرر و حدسود</h3><span class="pill">فقط محاسبه · بدون سفارش</span></div>
   <p class="eyebrow">دادهٔ کندل‌های بسته‌شده و مشخصات واقعی نماد را از MT5 بگیر و در قالب JSON وارد کن. موتور ATR، سقف/کف ساختاری، اسپرد، محدودیت توقف بروکر و حجم مجاز را بررسی می‌کند.</p>
   <label for="sltp-payload" class="eyebrow">ورودی کامل JSON مطابق نمونهٔ راهنما</label>
   <textarea id="sltp-payload" class="field" rows="14" style="width:100%;font-family:monospace;direction:ltr;text-align:left" spellcheck="false" placeholder='{"side":"buy","entry":1.1,"equity":10000,"risk_pct":0.25,"reward_risk":1.5,"spread_points":12,"candles":[...],"broker":{"point":0.00001,"tick_size":0.00001,"tick_value_loss":1,"digits":5,"stops_level_points":10,"freeze_level_points":0,"volume_min":0.01,"volume_max":100,"volume_step":0.01}}'></textarea>
   <div class="actions" style="margin-top:12px"><button class="primary" id="sltp-run" onclick="runSLTP()">محاسبهٔ SL/TP</button><button class="ghost" onclick="document.getElementById('sltp-payload').value=''">پاک‌کردن داده</button></div>
   <div id="sltp-message" class="status" aria-live="polite">تا زمانی که مشخصات واقعی نماد و دادهٔ معتبر وارد نشود، خروجی تأیید نمی‌شود.</div>
   <div id="sltp-result" class="grid" style="margin-top:14px" hidden>
    <article class="card"><div class="metric-foot">Stop Loss</div><div class="metric-value" id="sltp-stop">—</div></article>
    <article class="card"><div class="metric-foot">Take Profit</div><div class="metric-value" id="sltp-target">—</div></article>
    <article class="card"><div class="metric-foot">حجم محاسبه‌شده</div><div class="metric-value" id="sltp-volume">—</div></article>
    <article class="card"><div class="metric-foot">ریسک تخمینی</div><div class="metric-value" id="sltp-risk">—</div></article>
   </div>
   <div class="notice">این خروجی پیشنهاد محاسباتی است، نه سفارش و نه تضمین قیمت اجرا. tick value، tick size، اسپرد و قوانین نماد باید از ترمینال متصل و برای همان حساب/نماد تازه گرفته شوند. اجرای زنده خاموش است.</div>
  </div>
 </section>
 <section id="page-mt5" class="page">
  <div class="grid">
   <article class="card"><div class="metric-top"><span>وضعیت پل MT5</span><span class="metric-icon">◉</span></div><div class="metric-value" id="mt5-connection-state">قطع</div><div class="metric-foot" id="mt5-connection-detail">هنوز داده‌ای دریافت نشده است.</div></article>
   <article class="card"><div class="metric-top"><span>نماد و تایم‌فریم</span></div><div class="metric-value" id="mt5-symbol">—</div><div class="metric-foot" id="mt5-timeframe">—</div></article>
   <article class="card"><div class="metric-top"><span>Bid / Ask</span></div><div class="metric-value" id="mt5-quote">—</div><div class="metric-foot" id="mt5-spread">اسپرد: —</div></article>
   <article class="card"><div class="metric-top"><span>Equity</span></div><div class="metric-value" id="mt5-equity">—</div><div class="metric-foot" id="mt5-account-mode">حساب: —</div></article>
  </div>
  <div class="card" style="margin-top:14px">
   <div class="section-head"><h3>اتصال خواندنی MetaTrader 5</h3><span class="pill">بدون اجرای سفارش</span></div>
   <p class="eyebrow">این صفحه فقط snapshot واقعی ترمینال را نمایش می‌دهد: قیمت، کندل‌های بسته‌شده، مشخصات نماد و وضعیت حساب. هیچ رمز حساب یا شماره حسابی دریافت یا ذخیره نمی‌شود.</p>
   <div class="actions"><button class="primary" onclick="loadMT5Bridge()">بروزرسانی وضعیت</button><span class="status" id="mt5-updated">در انتظار اتصال</span></div>
   <div class="notice" id="mt5-setup-notice">برای اتصال، سرویس MT5 باید روی همین Ubuntu اجرا شود و Expert Advisor فقط‌خواندنی ForexAutoWebBridge به این API داده ارسال کند. کلید پل باید در تنظیمات امن سرویس و EA تنظیم شود؛ آن را در پیام یا مخزن عمومی قرار نده.</div>
   <div style="overflow:auto;margin-top:14px"><table class="data-table" style="width:100%"><thead><tr><th>ساعت بروکر (بدون منطقه زمانی)</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Tick volume</th></tr></thead><tbody id="mt5-bars"><tr><td colspan="6">هنوز داده‌ای دریافت نشده است.</td></tr></tbody></table></div>
   <div class="notice">وضعیت اتصال پس از ۱۲۰ ثانیه بدون داده تازه، قطع نمایش داده می‌شود. داده حساب فقط برای نمایش است. اجرای زنده و ارسال سفارش از این پل پشتیبانی نمی‌شود.</div>
  </div>
 </section>
 <section id="page-backtest" class="page">
  <div class="card">
   <div class="section-head"><h3>آزمایشگاه بک‌تست EMA</h3><span class="pill">شبیه‌سازی تاریخی · بدون سفارش</span></div>
   <p class="eyebrow">کندل‌های تاریخی OHLC را وارد کن. سیگنال در بسته‌شدن کندل محاسبه و ورود/خروج در بازشدن کندل بعدی شبیه‌سازی می‌شود؛ هزینهٔ معامله هم لحاظ می‌شود.</p>
   <div class="actions">
    <input id="bt-fast" class="field" type="number" min="2" max="199" value="9" aria-label="EMA سریع" placeholder="EMA سریع">
    <input id="bt-slow" class="field" type="number" min="3" max="200" value="21" aria-label="EMA کند" placeholder="EMA کند">
    <input id="bt-cost" class="field" type="number" min="0" max="1000" step="0.1" value="1" aria-label="هزینه هر سمت بر حسب bps" placeholder="هزینه هر سمت bps">
    <input id="bt-equity" class="field" type="number" min="1" value="10000" aria-label="سرمایه اولیه" placeholder="سرمایه اولیه">
   </div>
   <label for="bt-candles" class="eyebrow">JSON کندل‌ها (timestamp, open, high, low, close)</label>
   <textarea id="bt-candles" class="field" rows="9" style="width:100%;font-family:monospace;direction:ltr;text-align:left" spellcheck="false" placeholder='[{"timestamp":"2025-01-01T00:00:00Z","open":1.1,"high":1.102,"low":1.099,"close":1.101}]'></textarea>
   <div class="actions" style="margin-top:12px"><button class="primary" id="bt-run" onclick="runBacktest()">اجرای بک‌تست</button><button class="ghost" onclick="document.getElementById('bt-candles').value=''">پاک‌کردن داده</button></div>
   <div id="bt-message" class="status" aria-live="polite">بک‌تست فقط روی دادهٔ تاریخی واردشده اجرا می‌شود.</div>
   <div id="bt-result" class="grid" style="margin-top:14px" hidden>
    <article class="card"><div class="metric-foot">بازده کل</div><div class="metric-value" id="bt-return">—</div></article>
    <article class="card"><div class="metric-foot">حداکثر افت سرمایه</div><div class="metric-value" id="bt-dd">—</div></article>
    <article class="card"><div class="metric-foot">نرخ برد</div><div class="metric-value" id="bt-win">—</div></article>
    <article class="card"><div class="metric-foot">تعداد معاملات</div><div class="metric-value" id="bt-count">—</div></article>
   </div>
   <div class="notice">نتیجه به کیفیت داده، اسپرد، لغزش، سوآپ، کمیسیون، ساعات بازار و شکاف قیمت حساس است. این مدل ساده است و جایگزین آزمون خارج از نمونه، تست دمو یا تأیید مستقل نیست. اجرای زنده غیرفعال می‌ماند.</div>
  </div>
 </section>
 <section id="page-signals" class="page"><div class="card"><div class="section-head"><h3>سیگنال‌های معاملاتی</h3><span class="pill">اتصال زنده موجود نیست</span></div><p class="eyebrow">پس از اتصال منبع داده و موتور تولید سیگنال، نقاط ورود، حد ضرر، اهداف سود و نسبت ریسک به بازده در این بخش نمایش داده می‌شوند.</p><div class="signal"><div class="pair"><div class="coin">Au</div><div><b>XAUUSD · طلا</b><small>نمونه نمایشی، نه سیگنال واقعی</small></div></div><span class="pill">بدون سیگنال زنده</span></div><div class="signal"><div class="pair"><div class="coin">€</div><div><b>EURUSD</b><small>منتظر اتصال بازار</small></div></div><span class="pill">بدون سیگنال زنده</span></div></div></section>
 <section id="page-news" class="page">
  <div class="card">
   <div class="section-head"><h3>نبض خبری بازار</h3><span class="pill" id="news-feed-status">فید خبری · متصل نیست</span></div>
   <div class="grid" style="margin-top:0">
    <article class="card"><div class="metric-top"><span>مثبت</span><span class="metric-icon">↗</span></div><div class="metric-value green" id="news-positive">0</div><div class="metric-foot">احساسات بازار</div></article>
    <article class="card"><div class="metric-top"><span>خنثی</span><span class="metric-icon">→</span></div><div class="metric-value" id="news-neutral">0</div><div class="metric-foot">احساسات بازار</div></article>
    <article class="card"><div class="metric-top"><span>منفی</span><span class="metric-icon">↘</span></div><div class="metric-value red" id="news-negative">0</div><div class="metric-foot">احساسات بازار</div></article>
    <article class="card"><div class="metric-top"><span>تعداد خبرهای در دسترس</span><span class="metric-icon">▤</span></div><div class="metric-value" id="news-count">0</div><div class="metric-foot">خبرهای تأییدشده</div></article>
   </div>
   <div class="actions" style="margin-top:16px"><input id="news-search" class="field" placeholder="جستجو در خبرها" oninput="renderNews()"><select id="news-category" class="field" onchange="renderNews()"><option value="all">همه دسته‌ها</option><option value="forex">فارکس</option><option value="gold">طلا</option><option value="macro">اقتصاد کلان</option><option value="central_banks">بانک‌های مرکزی</option><option value="economic_calendar">تقویم اقتصادی</option><option value="inflation">تورم و CPI</option><option value="employment">اشتغال و NFP</option><option value="analysis">تحلیل بازار</option></select><select id="news-impact" class="field" onchange="renderNews()"><option value="all">همه اهمیت‌ها</option><option value="high">زیاد</option><option value="medium">متوسط</option><option value="low">کم</option></select></div>
   <div id="news-list" style="margin-top:14px"><div class="notice">هنوز منبع خبری متصل نشده است.</div></div>
   <div class="notice">پس از اتصال منبع معتبر، خبرها همراه با تیتر، خلاصه، تحلیل، زمان انتشار، منبع و احساسات بازار نمایش داده می‌شوند.</div>
  </div>
 </section>
 <section id="page-performance" class="page">
  <div class="card">
   <div class="section-head"><h3>عملکرد سیگنال‌ها</h3><span class="pill" id="performance-status">تاریخچه معاملات متصل نیست</span></div>
   <div class="grid" style="margin-top:0">
    <article class="card"><div class="metric-top"><span>نرخ برد</span><span class="metric-icon">％</span></div><div class="metric-value" id="perf-win-rate">—</div><div class="metric-foot">فقط معاملات بسته‌شده</div></article>
    <article class="card"><div class="metric-top"><span>میانگین سود</span><span class="metric-icon">↗</span></div><div class="metric-value" id="perf-average">—</div><div class="metric-foot">سود خالص هر معامله</div></article>
    <article class="card"><div class="metric-top"><span>سود خالص</span><span class="metric-icon">◈</span></div><div class="metric-value" id="perf-net">—</div><div class="metric-foot">پس از هزینه‌ها</div></article>
    <article class="card"><div class="metric-top"><span>Profit Factor</span><span class="metric-icon">◇</span></div><div class="metric-value" id="perf-factor">—</div><div class="metric-foot">سود ناخالص تقسیم بر زیان ناخالص</div></article>
   </div>
   <div class="notice" id="performance-empty">برای محاسبه عملکرد، تاریخچه معاملات بسته‌شده و نتیجه خالص هر معامله باید متصل شود.</div>
  </div>
  <div class="content-grid">
   <article class="card"><div class="section-head"><h3>شاخص ترس و طمع</h3><span class="pill" id="fear-greed-status">داده کافی نیست</span></div>
    <div style="display:flex;align-items:center;justify-content:center;gap:22px;padding:24px 8px;flex-wrap:wrap">
     <div id="fear-greed-gauge" style="width:150px;height:150px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--line) 0deg 360deg)"><div style="width:116px;height:116px;border-radius:50%;background:var(--panel);display:grid;place-items:center;text-align:center"><b id="fear-greed-score" style="font-size:30px">—</b><small>0–100</small></div></div>
     <div><h3 id="fear-greed-label">در انتظار داده بازار</h3><p class="eyebrow">مومنتوم، پهنای بازار، نوسان و تقاضای دارایی امن</p></div>
    </div><div class="notice">شاخص فقط پس از دریافت مؤلفه‌های معتبر بازار محاسبه می‌شود؛ مقدار نمایشی یا حدسی نداریم.</div>
   </article>
   <article class="card"><div class="section-head"><h3>نقشه زنده بازار</h3><span class="pill" id="market-map-status">فید قیمت متصل نیست</span></div><div id="live-market-map" class="notice">با اتصال قیمت لحظه‌ای نمادها، نقشه تغییرات بازار اینجا نمایش داده می‌شود.</div></article>
  </div>
  <article class="card"><div class="section-head"><h3>نقشه حرارتی عملکرد سیگنال‌ها</h3><span class="pill">بر اساس سود خالص میانگین</span></div><div id="signal-heatmap" class="notice">پس از ثبت معاملات بسته‌شده، عملکرد مثبت و منفی هر نماد در این نقشه نمایش داده می‌شود.</div></article>
  <article class="card"><div class="section-head"><h3>جدول رتبه‌بندی نمادها</h3><span class="eyebrow">مرتب‌شده بر اساس میانگین سود</span></div>
   <div class="table-wrap"><table class="data-table"><thead><tr><th>رتبه</th><th>نماد</th><th>تعداد معاملات</th><th>نرخ برد</th><th>میانگین سود</th><th>سود خالص</th></tr></thead><tbody id="symbol-ranking"><tr><td colspan="6">هنوز تاریخچه معاملات متصل نشده است.</td></tr></tbody></table></div>
  </article>
 </section>

 <section id="page-analysis" class="page"><div class="card"><div class="section-head"><h3>تحلیل چندتایم‌فریمی</h3><span class="pill">در انتظار داده بازار</span></div><div class="modules"><div class="module"><b>ساختار قیمت</b><small>Market Structure</small></div><div class="module"><b>SMC / ICT</b><small>مفاهیم نقدینگی و نواحی</small></div><div class="module"><b>رژیم بازار</b><small>تشخیص روند و نوسان</small></div></div><div class="notice">تا زمان اتصال فید معتبر قیمت، هیچ تحلیل یا جهت بازار به‌عنوان نتیجه زنده ارائه نمی‌شود.</div></div></section>
 <section id="page-simulator" class="page"><div class="card"><div class="section-head"><h3>شبیه‌ساز تصمیم</h3><span class="pill">آزمایشی</span></div><p class="eyebrow">این ابزار صرفاً منطق محافظتی را در شرایط نمونه نشان می‌دهد.</p><div class="actions"><select class="field" id="symbol"><option>XAUUSD</option><option>EURUSD</option><option>GBPUSD</option><option>USDJPY</option></select><button class="primary" onclick="preview()">اجرای پیش‌نمایش</button></div><div id="preview" class="status">برای شروع، نماد را انتخاب کنید.</div></div></section>
 <section id="page-modules" class="page">
  <div class="hero"><div><h2>مرکز فرماندهی ربات‌ها</h2><p>وضعیت واقعی ماژول‌ها، سطح دسترسی و محدودیت‌های اجرایی را یکجا ببین.</p></div><span class="hero-tag">● اجرای سفارش خاموش است</span></div>
  <div class="grid bot-grid">
   <article class="card bot-card"><div class="bot-card-head"><span class="metric-icon">⌁</span><span class="pill" id="bot-signals-state">در حال بررسی</span></div><h3>ربات سیگنال‌دهی</h3><p>تحلیل کندل، روند، مومنتوم و نوسان؛ نمایش جهت‌گیری پژوهشی فقط پس از دریافت داده معتبر.</p><div class="bot-facts"><span>موتور تحلیل: <b id="bot-signals-engine">—</b></span><span>فید بازار: <b id="bot-signals-feed">—</b></span></div><button class="primary" onclick="goPage('market-radar',document.querySelector('[data-page=market-radar]'))">بازکردن تحلیل سیگنال</button></article>
   <article class="card bot-card"><div class="bot-card-head"><span class="metric-icon">◇</span><span class="pill" id="bot-manager-state">در حال بررسی</span></div><h3>ربات مدیریت و کنترل ریسک</h3><p>پیش‌نمایش ریسک پرتفوی، کنترل توقف اضطراری و بررسی محدودیت‌ها؛ بدون ارسال یا مدیریت سفارش.</p><div class="bot-facts"><span>موتور ریسک: <b id="bot-manager-engine">—</b></span><span>توقف اضطراری: <b id="bot-manager-stop">—</b></span></div><button class="primary" onclick="goPage('simulator',document.querySelector('[data-page=simulator]'))">بازکردن کنترل ریسک</button></article>
   <article class="card bot-card" id="bot-users-card"><div class="bot-card-head"><span class="metric-icon">♙</span><span class="pill" id="bot-users-state">در حال بررسی</span></div><h3>ربات مدیریت کاربران</h3><p>مدیریت حساب‌ها، نقش‌ها و فعال‌سازی کاربران با محدودیت دسترسی مدیر و ثبت وضعیت دسترسی.</p><div class="bot-facts"><span>کاربران ثبت‌شده: <b id="bot-users-count">—</b></span><span>سطح دسترسی: <b id="bot-users-access">—</b></span></div><button class="primary" id="bot-users-open" onclick="goPage('users',document.querySelector('[data-page=users]'))">مدیریت کاربران</button></article>
  </div>
  <div class="card" style="margin-top:14px"><div class="section-head"><h3>قواعد ایمنی مشترک</h3><span class="pill ok">فعال</span></div><div class="modules"><div class="module"><b>بدون اجرای سفارش</b><small>execution_allowed همیشه false</small></div><div class="module"><b>داده واقعی الزامی</b><small>داده نمونه به‌عنوان بازار زنده نمایش داده نمی‌شود</small></div><div class="module"><b>دسترسی مبتنی بر نقش</b><small>عملیات کاربران فقط برای مدیر سیستم</small></div></div><div id="bots-status-message" class="status" aria-live="polite">برای دریافت وضعیت، صفحه را تازه‌سازی کن.</div></div>
 </section>
 <section id="page-ftmo" class="page">
  <div class="card"><div class="section-head"><h3>مدیریت حساب‌های FTMO</h3><span class="pill">ثبت چند حساب</span></div>
   <p class="eyebrow">برای هر حساب، محصول، مرحله و نوع حساب را جداگانه ثبت کن. رمز ورود MT5 یا رمز FTMO را وارد نکن.</p>
   <form id="ftmo-account-form" onsubmit="saveFtmoAccount(event)" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px">
    <input class="field" id="ftmo-label" placeholder="نام دلخواه حساب" required maxlength="80"><input class="field" id="ftmo-number" placeholder="شماره حساب (اختیاری)" maxlength="80">
    <select class="field" id="ftmo-product" required onchange="refreshFtmoOptions()"><option value="">انتخاب محصول</option></select>
    <select class="field" id="ftmo-phase" required><option value="">انتخاب مرحله</option></select><select class="field" id="ftmo-type" required><option value="">نوع حساب معاملاتی</option></select>
    <select class="field" id="ftmo-platform"><option value="mt5">MetaTrader 5</option><option value="mt4">MetaTrader 4</option><option value="ctrader">cTrader</option><option value="tradingview">TradingView</option><option value="other">سایر</option></select>
    <input class="field" id="ftmo-capital" type="number" min="1" max="100000000" step="any" placeholder="سرمایه اولیه" required>
    <select class="field" id="ftmo-currency"><option>USD</option><option>EUR</option><option>GBP</option><option>CHF</option><option>CZK</option><option>CAD</option><option>AUD</option></select><button class="primary" type="submit">＋ افزودن حساب</button>
   </form><div id="ftmo-message" class="status" aria-live="polite"></div>
  </div>
  <div class="card" style="margin-top:14px"><div class="section-head"><h3>حساب‌های ثبت‌شده</h3><button class="ghost" onclick="loadFtmoAccounts()">بروزرسانی</button></div><div id="ftmo-account-list" class="status">در حال دریافت...</div></div>
  <div class="card" style="margin-top:14px">
   <div class="section-head"><h3>جست‌وجوی بروکر و سرورهای MT4 / MT5</h3><span class="pill">Demo / Live</span></div>
   <p class="eyebrow">نام بروکر را جست‌وجو کن؛ سرور دقیق Demo یا Live را انتخاب یا ثبت کن. پیشنهادهای ثبت‌شده فقط برای حساب کاربری خودت ذخیره می‌شوند.</p>
   <form id="broker-server-form" onsubmit="saveBrokerServer(event)" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px">
    <input class="field" id="broker-search" list="broker-suggestions" placeholder="جست‌وجوی نام بروکر..." autocomplete="off" required maxlength="100" oninput="searchBrokerNames()" onchange="loadBrokerServers()">
    <datalist id="broker-suggestions"></datalist>
    <select class="field" id="broker-platform" onchange="loadBrokerServers()"><option value="mt5">MetaTrader 5</option><option value="mt4">MetaTrader 4</option></select>
    <select class="field" id="broker-environment" onchange="loadBrokerServers()"><option value="demo">Demo (آزمایشی)</option><option value="live">Live (واقعی)</option></select>
    <input class="field" id="broker-server-search" list="broker-server-suggestions" placeholder="نام دقیق سرور بروکر..." autocomplete="off" required maxlength="160">
    <datalist id="broker-server-suggestions"></datalist>
    <button class="primary" type="submit">＋ ذخیره سرور</button>
   </form>
   <div id="broker-directory-message" class="status" aria-live="polite"></div>
   <div id="broker-server-list" class="status">برای دیدن پیشنهادهای سرور، بروکر را جست‌وجو کن.</div>
  </div>
  <div class="notice">این بخش فعلاً مشخصات حساب را ذخیره می‌کند؛ اتصال زنده MT5 و ارسال سفارش هنوز فعال نیست.</div>
 </section>
 <section id="page-users" class="page"><div class="card"><div class="section-head"><h3>مدیریت کاربران</h3><span class="pill">مدیر سیستم</span></div><div class="actions"><input class="field" id="new-username" placeholder="نام کاربری"><input class="field" id="new-password" type="password" autocomplete="new-password" placeholder="رمز حداقل ۱۴ نویسه"><select class="field" id="new-role"><option value="trader">معامله‌گر</option><option value="analyst">تحلیل‌گر</option><option value="viewer">فقط مشاهده</option></select><button class="primary" onclick="createUser()">ایجاد کاربر</button></div><div id="users-list" class="status"></div></div></section>
 <footer>Forex AI Hybrid Scalper · ابزار تحلیلی و آموزشی. داده زنده، تقویم اقتصادی معتبر، اتصال بروکر و ارسال سفارش در این نسخه فعال نیست. نمودارها و مقادیر نمونه صرفاً برای نمایش رابط کاربری هستند. معامله‌گری ریسک بالایی دارد.</footer>
</main></div>
<script>
const I18N = __I18N_CATALOG__;
let activeLocale = "fa";
function t(source){return (I18N[source]&&I18N[source][activeLocale])||source;}
const originalTextNodes=new WeakMap();
function applyLanguage(locale){activeLocale=["fa","en","ar","tr"].includes(locale)?locale:"fa";const rtl=["fa","ar"].includes(activeLocale);document.documentElement.lang=activeLocale;document.documentElement.dir=rtl?"rtl":"ltr";["language-select","login-language"].forEach(id=>{const select=document.getElementById(id);if(select)select.value=activeLocale;});const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let node;while(node=walker.nextNode()){if(!node.parentElement||["SCRIPT","STYLE"].includes(node.parentElement.tagName))continue;if(!originalTextNodes.has(node))originalTextNodes.set(node,node.nodeValue);const original=originalTextNodes.get(node);const trimmed=original.trim();if(!trimmed)continue;const translated=t(trimmed);node.nodeValue=original.replace(trimmed,translated);}
 document.querySelectorAll("[placeholder],[title],[aria-label]").forEach(el=>{for(const attr of ["placeholder","title","aria-label"]){if(!el.hasAttribute(attr))continue;const key="i18n"+attr[0].toUpperCase()+attr.slice(1);if(!el.dataset[key])el.dataset[key]=el.getAttribute(attr);el.setAttribute(attr,t(el.dataset[key]));}});
 const title=document.getElementById("page-title");if(title&&currentPage)title.textContent=t(pageTitles[currentPage]);const crumb=document.getElementById("crumb");if(crumb&&currentPage)crumb.textContent=t(pageTitles[currentPage]);try{localStorage.setItem("forexai-locale",activeLocale);}catch(e){} }
function setLanguage(locale){applyLanguage(locale);if(currentUser){document.getElementById("role-label").textContent=t("نقش: ")+t(currentUser.role);refreshStatus();if(currentPage==="news")loadNews();if(currentPage==="performance")loadPerformance();if(currentPage==="users")loadUsers();}}
let currentPage="overview";\nlet mt5BridgeRefreshTimer=null;
const pageTitles={performance:"عملکرد و نبض بازار",news:"اخبار بازار",overview:"داشبورد معاملاتی",signals:"سیگنال‌های معاملاتی","market-radar":"رادار بازار",backtest:"آزمایشگاه بک‌تست",sltp:"مدیریت هوشمند SL/TP",mt5:"اتصال زنده MT5",analysis:"تحلیل بازار",simulator:"شبیه‌ساز تصمیم",modules:"مرکز ربات‌ها",ftmo:"حساب‌های FTMO",users:"مدیریت کاربران"};
let csrfToken='',currentUser=null;
async function api(path,options={}){const headers=Object.assign({"X-UI-Language":activeLocale},options.headers||{});if(options.method&&options.method!=='GET')headers['X-CSRF-Token']=csrfToken;return fetch(path,Object.assign({credentials:'same-origin'},options,{headers}));}
async function login(event){if(event)event.preventDefault();const msg=document.getElementById('login-message'),button=document.getElementById('login-submit'),username=document.getElementById('login-user'),password=document.getElementById('login-pass');if(!username.value.trim()||!password.value){msg.textContent='نام کاربری و رمز عبور را وارد کنید.';return;}button.disabled=true;button.querySelector('span').textContent='در حال بررسی اطلاعات...';msg.textContent='در حال اتصال امن به سرور...';try{const r=await fetch('/api/auth/login',{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-UI-Language':activeLocale},body:JSON.stringify({username:username.value.trim(),password:password.value})});let d={};try{d=await r.json();}catch(parseError){throw Error('پاسخ سرور قابل خواندن نیست. صفحه را تازه‌سازی کنید.');}if(!r.ok)throw Error((d.detail||'ورود ناموفق بود')+(r.status===429?' · چند دقیقه بعد دوباره تلاش کنید.':''));if(!d.csrf_token||!d.user)throw Error('پاسخ ورود ناقص است؛ با پشتیبانی تماس بگیرید.');csrfToken=d.csrf_token;password.value='';msg.textContent='ورود موفق؛ در حال بازکردن پنل...';showApp(d.user);}catch(e){msg.textContent=e instanceof TypeError?'ارتباط با سرور برقرار نشد؛ اتصال اینترنت را بررسی و دوباره تلاش کنید.':e.message;}finally{button.disabled=false;button.querySelector('span').textContent='ورود امن به پنل';}}
function showApp(user){currentUser=user;document.getElementById('login-screen').hidden=true;document.getElementById('app-shell').hidden=false;document.getElementById('account-label').textContent=user.username;document.getElementById('role-label').textContent=t('نقش: ')+t(user.role);document.getElementById('avatar').textContent=(user.username||'U').slice(0,1).toUpperCase();document.getElementById('users-nav').hidden=user.role!=='admin';refreshStatus();loadFtmoProducts();loadFtmoAccounts();if(user.role==='admin')loadUsers();}
async function restoreSession(){try{const r=await fetch('/api/auth/me',{credentials:'same-origin'});if(!r.ok)return;const d=await r.json();csrfToken=d.csrf_token;showApp(d.user);}catch(e){}}
function goPage(name,button){if(name==='users'&&(!currentUser||currentUser.role!=='admin'))return;currentPage=name;if(mt5BridgeRefreshTimer!==null){clearInterval(mt5BridgeRefreshTimer);mt5BridgeRefreshTimer=null;}document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));document.getElementById('page-'+name).classList.add('active');document.querySelectorAll('.nav button').forEach(b=>b.classList.remove('active'));if(button)button.classList.add('active');if(name==='news')loadNews();if(name==='modules')loadBotStatus();if(name==='mt5'){loadMT5Bridge();mt5BridgeRefreshTimer=window.setInterval(()=>{if(currentPage==='mt5')loadMT5Bridge();},15000);}if(name==='performance')loadPerformance();if(name==='ftmo'){loadFtmoProducts();loadFtmoAccounts();}document.getElementById('page-title').textContent=t(pageTitles[name]);document.getElementById('crumb').textContent=t(pageTitles[name]);}
async function runSLTP(){
 const msg=document.getElementById('sltp-message'),button=document.getElementById('sltp-run'),out=document.getElementById('sltp-result');
 out.hidden=true;button.disabled=true;msg.textContent='در حال اعتبارسنجی مشخصات بروکر و محاسبه...';
 try{
  const payload=JSON.parse(document.getElementById('sltp-payload').value);
  const response=await api('/api/sltp/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const data=await response.json();if(!response.ok)throw Error(data.detail||'محاسبه انجام نشد.');
  const p=data.plan;
  if(!p.valid){msg.textContent='طرح رد شد: '+p.reasons.join('، ');return;}
  document.getElementById('sltp-stop').textContent=String(p.stop_loss);
  document.getElementById('sltp-target').textContent=String(p.take_profit);
  document.getElementById('sltp-volume').textContent=Number(p.volume).toFixed(3);
  document.getElementById('sltp-risk').textContent=Number(p.estimated_risk_money).toFixed(2);
  out.hidden=false;msg.textContent='محاسبه معتبر است · ATR '+Number(p.atr).toPrecision(5)+' · R/R '+Number(p.reward_risk).toFixed(2)+' · اجازه اجرا: خیر';
 }catch(e){msg.textContent='خطا: '+e.message;}
 finally{button.disabled=false;}
}
async function runBacktest(){
 const msg=document.getElementById('bt-message'),button=document.getElementById('bt-run'),out=document.getElementById('bt-result');
 out.hidden=true;button.disabled=true;msg.textContent='در حال اجرای شبیه‌سازی...';
 try{
  const candles=JSON.parse(document.getElementById('bt-candles').value);
  if(!Array.isArray(candles))throw Error('ورودی باید آرایه‌ای از کندل‌ها باشد.');
  const payload={candles,fast_period:Number(document.getElementById('bt-fast').value),slow_period:Number(document.getElementById('bt-slow').value),cost_bps_per_side:Number(document.getElementById('bt-cost').value),initial_equity:Number(document.getElementById('bt-equity').value)};
  const response=await api('/api/backtest/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const data=await response.json();if(!response.ok)throw Error(data.detail||'بک‌تست ناموفق بود.');
  const r=data.result;
  document.getElementById('bt-return').textContent=Number(r.total_return_pct).toFixed(2)+'%';
  document.getElementById('bt-dd').textContent=Number(r.max_drawdown_pct).toFixed(2)+'%';
  document.getElementById('bt-win').textContent=Number(r.win_rate_pct).toFixed(1)+'%';
  document.getElementById('bt-count').textContent=String(r.trade_count);
  out.hidden=false;msg.textContent='بک‌تست تمام شد · '+r.bars+' کندل · سرمایه نهایی '+Number(r.final_equity).toFixed(2)+' · اجازه اجرا: خیر';
 }catch(e){msg.textContent='خطا: '+e.message;}
 finally{button.disabled=false;}
}
async function runMarketRadar(){
 const msg=document.getElementById('radar-message'),button=document.getElementById('radar-run'),out=document.getElementById('radar-result');
 out.hidden=true;button.disabled=true;msg.textContent='در حال اعتبارسنجی و تحلیل داده‌ها...';
 try{
  const raw=JSON.parse(document.getElementById('radar-candles').value);
  if(!Array.isArray(raw))throw Error('ورودی باید آرایه‌ای از کندل‌ها باشد.');
  const payload={symbol:document.getElementById('radar-symbol').value.trim(),timeframe:document.getElementById('radar-timeframe').value.trim(),candles:raw};
  const response=await api('/api/market-radar/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const data=await response.json();if(!response.ok)throw Error(data.detail||'تحلیل انجام نشد.');
  const a=data.analysis;
  document.getElementById('radar-trend').textContent=t(a.trend);
  document.getElementById('radar-rsi').textContent=Number(a.rsi_14).toFixed(2)+' · '+t(a.momentum);
  document.getElementById('radar-atr').textContent=Number(a.atr_pct).toFixed(3)+'% · '+t(a.volatility);
  document.getElementById('radar-stance').textContent=t(a.stance);
  out.hidden=false;msg.textContent='تحلیل انجام شد · '+a.bars+' کندل · آخرین قیمت '+a.latest_close+' · اجازه اجرای سفارش: خیر';
 }catch(e){msg.textContent='خطا: '+e.message;}
 finally{button.disabled=false;}
}
function toggleTheme(){document.documentElement.classList.toggle('light');}
async function logout(){try{await api('/api/auth/logout',{method:'POST'});}finally{csrfToken='';location.reload();}}
let brokerSearchTimer=null;
async function searchBrokerNames(){
 const input=document.getElementById('broker-search');const q=input.value.trim();
 clearTimeout(brokerSearchTimer);
 brokerSearchTimer=setTimeout(async()=>{try{
  const r=await fetch('/api/brokers/search?q='+encodeURIComponent(q),{headers:{'X-UI-Language':activeLocale}});
  const d=await r.json();if(!r.ok)throw Error(d.detail||'خطا');
  const list=document.getElementById('broker-suggestions');list.replaceChildren();
  (d.brokers||[]).forEach(b=>{const o=document.createElement('option');o.value=b.name;list.appendChild(o);});
 }catch(e){document.getElementById('broker-directory-message').textContent=e.message;}},120);
}
async function loadBrokerServers(){
 const broker=document.getElementById('broker-search').value.trim();const platform=document.getElementById('broker-platform').value;const environment=document.getElementById('broker-environment').value;
 const list=document.getElementById('broker-server-suggestions');const view=document.getElementById('broker-server-list');
 list.replaceChildren();if(!broker){view.textContent='ابتدا نام بروکر را جست‌وجو کن.';return;}
 try{
  const url='/api/brokers/servers?broker='+encodeURIComponent(broker)+'&platform='+platform+'&environment='+environment;
  const r=await fetch(url,{headers:{'X-UI-Language':activeLocale}});const d=await r.json();if(!r.ok)throw Error(d.detail||'خطا');
  (d.servers||[]).forEach(server=>{const o=document.createElement('option');o.value=server.server_name;list.appendChild(o);});
  view.textContent=d.servers&&d.servers.length?'سرورهای ذخیره‌شده '+(environment==='demo'?'آزمایشی':'واقعی')+': '+d.servers.map(x=>x.server_name).join(' · '):'هنوز سروری برای این بروکر و نوع حساب ذخیره نشده؛ نام دقیق را از پنل بروکر وارد و ذخیره کن.';
 }catch(e){view.textContent=e.message;}
}
async function saveBrokerServer(e){
 e.preventDefault();const msg=document.getElementById('broker-directory-message');
 const payload={broker_name:document.getElementById('broker-search').value.trim(),platform:document.getElementById('broker-platform').value,environment:document.getElementById('broker-environment').value,server_name:document.getElementById('broker-server-search').value.trim()};
 try{
  const r=await api('/api/brokers/servers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const d=await r.json();if(!r.ok)throw Error(d.detail||'ذخیره سرور ناموفق بود');
  msg.textContent='سرور ذخیره شد و از این پس در پیشنهادهای همین بروکر نمایش داده می‌شود.';
  document.getElementById('broker-server-search').value='';await searchBrokerNames();await loadBrokerServers();
 }catch(err){msg.textContent='خطا: '+err.message;}
}
let ftmoProducts={};
const ftmoLabels={cfd_1_step:"FTMO Challenge 1-Step",cfd_2_step:"FTMO Challenge 2-Step",cfd_instant:"FTMO Instant",futures:"FTMO Futures",free_trial:"Free Trial"};
const ftmoPhaseLabels={challenge:"Challenge",verification:"Verification",funded:"FTMO Account / Funded",instant:"Instant Account",evaluation:"Evaluation",sim_funded:"Sim-Funded",trial:"Free Trial"};
const ftmoTypeLabels={standard:"Standard",swing:"Swing",growth:"Growth",classic:"Classic"};
async function loadFtmoProducts(){try{const r=await fetch('/api/ftmo/products',{headers:{'X-UI-Language':activeLocale}});const d=await r.json();if(!r.ok)throw Error(d.detail||'خطا');ftmoProducts=d.products||{};const s=document.getElementById('ftmo-product');if(s.options.length<=1)Object.entries(ftmoProducts).forEach(([k,p])=>{const o=document.createElement('option');o.value=k;o.textContent=ftmoLabels[k]||p.label;s.appendChild(o);});refreshFtmoOptions();}catch(e){document.getElementById('ftmo-message').textContent=e.message;}}
function refreshFtmoOptions(){const spec=ftmoProducts[document.getElementById('ftmo-product').value]||{phases:[],account_types:[]};const p=document.getElementById('ftmo-phase'),t=document.getElementById('ftmo-type');p.replaceChildren();t.replaceChildren();const p0=document.createElement('option');p0.value='';p0.textContent='انتخاب مرحله';p.appendChild(p0);spec.phases.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=ftmoPhaseLabels[v]||v;p.appendChild(o);});const t0=document.createElement('option');t0.value='';t0.textContent='نوع حساب معاملاتی';t.appendChild(t0);spec.account_types.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=ftmoTypeLabels[v]||v;t.appendChild(o);});}
async function saveFtmoAccount(e){e.preventDefault();const msg=document.getElementById('ftmo-message');const payload={label:document.getElementById('ftmo-label').value,account_number:document.getElementById('ftmo-number').value||null,product:document.getElementById('ftmo-product').value,phase:document.getElementById('ftmo-phase').value,account_type:document.getElementById('ftmo-type').value,platform:document.getElementById('ftmo-platform').value,initial_capital:Number(document.getElementById('ftmo-capital').value),currency:document.getElementById('ftmo-currency').value};try{const r=await api('/api/ftmo/accounts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw Error(d.detail||'ثبت حساب ناموفق بود');msg.textContent='حساب با موفقیت ثبت شد.';document.getElementById('ftmo-account-form').reset();refreshFtmoOptions();await loadFtmoAccounts();}catch(e){msg.textContent='خطا: '+e.message;}}
async function loadFtmoAccounts(){const el=document.getElementById('ftmo-account-list');if(!el)return;try{const r=await fetch('/api/ftmo/accounts',{headers:{'X-UI-Language':activeLocale}});const d=await r.json();if(!r.ok)throw Error(d.detail||'خطا');el.replaceChildren();if(!d.accounts.length){el.textContent='هنوز حسابی ثبت نشده است.';return;}d.accounts.forEach(a=>{const row=document.createElement('div');row.className='user-row';const info=document.createElement('span');info.textContent=a.label+' · '+(ftmoLabels[a.product]||a.product)+' · '+(ftmoPhaseLabels[a.phase]||a.phase)+' · '+(ftmoTypeLabels[a.account_type]||a.account_type)+' · '+Number(a.initial_capital).toLocaleString(activeLocale)+' '+a.currency+(a.account_number?' · #'+a.account_number:'')+' · '+a.platform;const badge=document.createElement('span');badge.className='pill'+(a.active?' ok':'');badge.textContent=a.active?'فعال':'غیرفعال';row.append(info,badge);el.appendChild(row);});}catch(e){el.textContent=e.message;}}
async function loadBotStatus(){
 const msg=document.getElementById('bots-status-message');
 try{
  const r=await api('/api/bots/status');const d=await r.json();if(!r.ok)throw Error(d.detail||'دریافت وضعیت ربات‌ها ناموفق بود');
  const bots=Object.fromEntries((d.bots||[]).map(bot=>[bot.id,bot]));
  const signal=bots.signals||{},manager=bots.manager||{},users=bots.users||{};
  document.getElementById('bot-signals-state').textContent=signal.market_data_connected?'داده متصل':'فقط پژوهشی';
  document.getElementById('bot-signals-engine').textContent=signal.engine_available?'آماده':'در دسترس نیست';
  document.getElementById('bot-signals-feed').textContent=signal.market_data_connected?'متصل':'متصل نیست';
  document.getElementById('bot-manager-state').textContent=manager.state==='risk_preview_only'?'پیش‌نمایش ریسک':'محدود';
  document.getElementById('bot-manager-engine').textContent=manager.engine_available?'آماده':'در دسترس نیست';
  document.getElementById('bot-manager-stop').textContent=manager.emergency_stop?'فعال':'غیرفعال';
  document.getElementById('bot-users-state').textContent=users.available?'مدیریت مدیر':'دسترسی محدود';
  document.getElementById('bot-users-count').textContent=users.available?String(users.user_count):'محرمانه';
  document.getElementById('bot-users-access').textContent=users.available?'مدیر سیستم':'فقط مدیر';
  document.getElementById('bot-users-open').disabled=!users.available;
  document.getElementById('bot-users-card').classList.toggle('bot-restricted',!users.available);
  msg.textContent='وضعیت از سرور دریافت شد · اجرای سفارش برای همه ربات‌ها غیرفعال است.';
 }catch(e){msg.textContent='خطا در دریافت وضعیت ربات‌ها: '+e.message;}
}
async function loadUsers(){const el=document.getElementById('users-list');try{const r=await fetch('/api/users',{headers:{'X-UI-Language':activeLocale}});const d=await r.json();if(!r.ok)throw Error(d.detail||'خطا');el.replaceChildren();d.users.forEach(u=>{const row=document.createElement('div');row.className='user-row';const label=document.createElement('span');label.textContent=u.username+' · '+t(u.role)+' · '+(u.active?t('فعال'):t('غیرفعال'));row.appendChild(label);if(u.role!=='admin'){const b=document.createElement('button');b.className='ghost';b.textContent=u.active?t('غیرفعال‌کردن'):t('فعال‌کردن');b.onclick=()=>setUserActive(u.id,!u.active);row.appendChild(b);}el.appendChild(row);});}catch(e){el.textContent=e.message;}}
async function createUser(){try{const r=await api('/api/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:document.getElementById('new-username').value,password:document.getElementById('new-password').value,role:document.getElementById('new-role').value})});const d=await r.json();if(!r.ok)throw Error(d.detail||'خطا');document.getElementById('new-password').value='';await loadUsers();}catch(e){document.getElementById('users-list').textContent=e.message;}}
async function setUserActive(id,active){try{const r=await api('/api/users/'+id+'/active?active='+active,{method:'PATCH'});const d=await r.json();if(!r.ok)throw Error(d.detail||'خطا');await loadUsers();}catch(e){document.getElementById('users-list').textContent=e.message;}}
async function refreshStatus(){const el=document.getElementById('status');try{const r=await fetch('/api/status',{headers:{'X-UI-Language':activeLocale}});if(!r.ok)throw Error('HTTP '+r.status);const d=await r.json();el.textContent=t('توقف اضطراری: ')+(d.emergency_stop?t('فعال'):t('غیرفعال'))+' · '+t('فیلتر خبر: ')+(d.news_filter_enabled?t('روشن'):t('خاموش'))+' · MT5: '+t('متصل نیست')+' · '+t('اجرای واقعی: غیرفعال');}catch(e){el.textContent=t('وضعیت سرویس دریافت نشد: ')+e.message;}}
async function activateStop(){const b=document.getElementById('stop'),toastEl=document.getElementById('toast');b.disabled=true;try{const r=await api('/api/emergency-stop',{method:'POST'});if(!r.ok)throw Error('HTTP '+r.status);toastEl.textContent=t('قفل توقف اضطراری فعال شد.');await refreshStatus();}catch(e){toastEl.textContent=t('خطا: ')+e.message;}finally{b.disabled=false;}}
async function preview(){const s=document.getElementById('symbol').value,el=document.getElementById('preview');try{const r=await fetch('/api/decision-preview?symbol='+encodeURIComponent(s),{headers:{'X-UI-Language':activeLocale}});const d=await r.json();if(!r.ok)throw Error(d.detail||'خطا');el.textContent=s+' · '+t('رژیم: ')+d.regime+' · '+t('استراتژی: ')+d.strategy+' · '+t('مجوز اجرا: خیر')+' · '+d.guard_reason+' · '+t('پیش‌نمایش غیرزنده');}catch(e){el.textContent=t('پیش‌نمایش در دسترس نیست: ')+e.message;}}
async function loadPerformance(){
 try{
  const r=await fetch("/api/analytics/overview",{headers:{"X-UI-Language":activeLocale}});
  const d=await r.json();if(!r.ok)throw Error(d.detail||"");
  const p=d.signal_performance||{},available=!!p.available;
  document.getElementById("performance-status").textContent=t(available?"آمار آماده است":"تاریخچه معاملات متصل نیست");
  document.getElementById("perf-win-rate").textContent=available?p.win_rate_pct+"%":"—";
  document.getElementById("perf-average").textContent=available?formatMetric(p.average_profit):"—";
  document.getElementById("perf-net").textContent=available?formatMetric(p.net_profit):"—";
  document.getElementById("perf-factor").textContent=available?(p.profit_factor==="inf"?"∞":p.profit_factor):"—";
  document.getElementById("performance-empty").hidden=available;
  const fg=d.fear_greed||{};
  document.getElementById("fear-greed-status").textContent=t(fg.available?"شاخص محاسبه شد":"داده کافی نیست");
  document.getElementById("fear-greed-score").textContent=fg.available?fg.score:"—";
  document.getElementById("fear-greed-label").textContent=fg.available?t(fg.label):t("در انتظار داده بازار");
  if(fg.available)document.getElementById("fear-greed-gauge").style.background="conic-gradient(var(--green) "+(fg.score*3.6)+"deg,var(--line) 0deg)";
  document.getElementById("market-map-status").textContent=t(d.market_data_status==="not_connected"?"فید قیمت متصل نیست":"بازار زنده");
  renderMarketMap(d.market_heatmap||[]);renderSignalHeatmap(p.heatmap||[]);renderSymbolRanking(p.symbols||[]);
 }catch(e){document.getElementById("performance-empty").textContent=t("خطا: ")+e.message;}
}
function formatMetric(v){if(v===null||v===undefined)return "—";return new Intl.NumberFormat(activeLocale,{maximumFractionDigits:4}).format(v);}
function renderMarketMap(rows){
 const el=document.getElementById("live-market-map");el.replaceChildren();
 if(!rows.length){el.textContent=t("با اتصال قیمت لحظه‌ای نمادها، نقشه تغییرات بازار اینجا نمایش داده می‌شود.");return;}
 rows.forEach(row=>{const item=document.createElement("span");item.className="module";item.style.display="inline-flex";item.style.flexDirection="column";item.style.margin="4px";item.style.minWidth="112px";item.style.padding="16px";item.style.background=row.direction==="up"?"#16a34a22":row.direction==="down"?"#ef444422":"var(--panel2)";item.style.borderColor=row.direction==="up"?"var(--green)":row.direction==="down"?"var(--red)":"var(--line)";const symbol=document.createElement("b");symbol.textContent=row.symbol;const change=document.createElement("small");change.textContent=formatMetric(row.change_pct)+"%";item.append(symbol,change);el.appendChild(item);});
}
function renderSignalHeatmap(rows){
 const el=document.getElementById("signal-heatmap");el.replaceChildren();
 if(!rows.length){el.textContent=t("پس از ثبت معاملات بسته‌شده، عملکرد مثبت و منفی هر نماد در این نقشه نمایش داده می‌شود.");return;}
 rows.forEach(row=>{const item=document.createElement("div");item.className="module";item.style.display="inline-flex";item.style.margin="4px";item.style.borderColor=row.performance==="positive"?"var(--green)":row.performance==="negative"?"var(--red)":"var(--line)";item.style.background=row.performance==="positive"?"#16a34a22":row.performance==="negative"?"#ef444422":"var(--panel2)";const title=document.createElement("b");title.textContent=row.symbol;const detail=document.createElement("small");detail.textContent=formatMetric(row.average_profit);item.append(title,detail);el.appendChild(item);});
}
function renderSymbolRanking(rows){
 const body=document.getElementById("symbol-ranking");body.replaceChildren();
 if(!rows.length){const tr=document.createElement("tr"),td=document.createElement("td");td.colSpan=6;td.textContent=t("هنوز تاریخچه معاملات متصل نشده است.");tr.appendChild(td);body.appendChild(tr);return;}
 rows.forEach((row,index)=>{const tr=document.createElement("tr");[index+1,row.symbol,row.closed_trades,formatMetric(row.win_rate_pct)+"%",formatMetric(row.average_profit),formatMetric(row.net_profit)].forEach(value=>{const td=document.createElement("td");td.textContent=String(value);tr.appendChild(td);});body.appendChild(tr);});
}
let newsArticles=[];
async function loadNews(){const list=document.getElementById("news-list");try{const r=await fetch("/api/news",{headers:{"X-UI-Language":activeLocale}});const d=await r.json();if(!r.ok)throw Error(d.detail||"");newsArticles=d.articles||[];document.getElementById("news-feed-status").textContent=t("فید خبری")+" · "+t(d.feed_status==="not_connected"?"متصل نیست":"آماده");document.getElementById("news-positive").textContent=d.sentiment?.positive??0;document.getElementById("news-neutral").textContent=d.sentiment?.neutral??0;document.getElementById("news-negative").textContent=d.sentiment?.negative??0;document.getElementById("news-count").textContent=newsArticles.length;renderNews();}catch(e){list.textContent=t("خطا: ")+e.message;}}
function renderNews(){const list=document.getElementById("news-list");if(!list)return;list.replaceChildren();const q=(document.getElementById("news-search")?.value||"").toLowerCase();const impact=document.getElementById("news-impact")?.value||"all";const category=document.getElementById("news-category")?.value||"all";const rows=newsArticles.filter(a=>(impact==="all"||a.impact===impact)&&(category==="all"||a.category===category)&&[a.title,a.summary,a.analysis,a.source,a.category].join(" ").toLowerCase().includes(q));if(!rows.length){const empty=document.createElement("div");empty.className="notice";empty.textContent=t("هنوز منبع خبری متصل نشده است.");list.appendChild(empty);return;}rows.forEach(a=>{const card=document.createElement("article");card.className="card";card.style.marginBottom="12px";const head=document.createElement("div");head.className="section-head";const title=document.createElement("h3");title.textContent=a.title;const badge=document.createElement("span");badge.className="pill";badge.textContent=t(a.impact||"متوسط");head.append(title,badge);const meta=document.createElement("div");meta.className="eyebrow";meta.textContent=[a.source,a.category,new Date(a.published_at).toLocaleString(activeLocale),t(a.sentiment||"خنثی")].filter(Boolean).join(" · ");const summary=document.createElement("p");summary.textContent=a.summary||"";if(a.translation_fallback){const fallback=document.createElement("small");fallback.className="eyebrow";fallback.textContent=t("محتوا به زبان دیگری نمایش داده می‌شود.")+" ("+(a.content_locale||"")+")";card.append(fallback);}const analysis=document.createElement("p");analysis.textContent=a.analysis||"";const link=document.createElement("a");link.href=a.url;link.target="_blank";link.rel="noopener noreferrer";link.textContent=t("مشاهده منبع");card.append(head,meta,summary,analysis,link);list.appendChild(card);});}
let deferredInstallPrompt=null;
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();deferredInstallPrompt=event;const b=document.getElementById('install-app');if(b)b.hidden=false;});
async function installPwa(){if(!deferredInstallPrompt)return;deferredInstallPrompt.prompt();await deferredInstallPrompt.userChoice;deferredInstallPrompt=null;const b=document.getElementById('install-app');if(b)b.hidden=true;}
if('serviceWorker' in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('/service-worker.js').catch(()=>{}));}
try{applyLanguage(localStorage.getItem('forexai-locale')||'fa');}catch(e){applyLanguage('fa');}
restoreSession();

async function loadMT5Bridge(){
 const state=document.getElementById('mt5-connection-state');
 const detail=document.getElementById('mt5-connection-detail');
 try{
  const sr=await api('/api/mt5/bridge/status');
  const st=await sr.json();
  if(!sr.ok)throw Error(st.detail||'خطا در دریافت وضعیت پل');
  state.textContent=st.connected?'متصل':'قطع';
  detail.textContent=st.connected?'داده تازه · '+st.age_seconds+' ثانیه قبل':'هنوز snapshot تازه دریافت نشده است';
  document.getElementById('mt5-symbol').textContent=st.symbol||'—';
  document.getElementById('mt5-timeframe').textContent=st.timeframe||'—';
  document.getElementById('mt5-account-mode').textContent='حساب: '+(st.account_mode||'—')+' · '+(st.server_name||'');
  document.getElementById('mt5-setup-notice').textContent=st.configured
   ?'کلید پل روی سرور تنظیم شده است. برای نمایش داده زنده، EA فقط‌خواندنی باید در ترمینال MT5 اجرا و به این endpoint متصل باشد.'
   :'کلید پل هنوز تنظیم نشده است. ابتدا کلید امن MT5_BRIDGE_TOKEN را در محیط سرویس تعریف کن؛ سپس همان کلید را فقط در تنظیمات EA قرار بده.';
  const r=await api('/api/mt5/bridge/snapshot');
  if(!r.ok){document.getElementById('mt5-bars').innerHTML='<tr><td colspan="6">در انتظار اولین snapshot از MT5</td></tr>';return;}
  const d=await r.json(),p=d.snapshot;
  document.getElementById('mt5-quote').textContent=Number(p.bid).toFixed(p.digits)+' / '+Number(p.ask).toFixed(p.digits);
  document.getElementById('mt5-spread').textContent='اسپرد: '+Number(p.spread_points).toFixed(1)+' points';
  document.getElementById('mt5-equity').textContent=Number(p.equity).toFixed(2)+' '+p.currency;
  document.getElementById('mt5-updated').textContent='آخرین دریافت: '+new Date(d.received_at*1000).toLocaleString();
  document.getElementById('mt5-bars').innerHTML=(p.bars||[]).slice(-30).reverse().map(c=>'<tr><td>'+new Date(c.time*1000).toISOString().slice(0,16).replace('T',' ')+'</td><td>'+c.open+'</td><td>'+c.high+'</td><td>'+c.low+'</td><td>'+c.close+'</td><td>'+c.tick_volume+'</td></tr>').join('');
 }catch(e){state.textContent='خطا';detail.textContent=e.message;}
}
</script>
</body></html>
"""

HTML = HTML.replace("__I18N_CATALOG__", json.dumps(catalog_for_frontend(), ensure_ascii=False))
