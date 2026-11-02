import os
import json
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from . import auth
from .config import AppConfig
from .engine import choose_regime, choose_strategy, authorize_trade
from .i18n import catalog_for_frontend, translate
from modules.ftmo_compliance import account_registry

app = FastAPI(title="Forex AI Hybrid Scalper", version="5.2.0")
cfg = AppConfig()
auth.init_auth()

class LoginPayload(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)

class CreateUserPayload(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=14, max_length=256)
    role: str

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


@app.get("/api/health")
def health():
    return {"ok": True, "service": "control-center"}


@app.post("/api/auth/login")
def login(payload: LoginPayload, request: Request, response: Response):
    user = auth.authenticate(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail=translate("Invalid username or password.", request.headers.get("x-ui-language")))
    token, csrf, expires = auth.create_session(user["id"])
    response.set_cookie(
        "forex_session", token, httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
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
    response.delete_cookie("forex_session", path="/", httponly=True, samesite="strict")
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

@app.get("/api/ftmo/products")
def ftmo_products(request: Request):
    require_role(request, "admin", "trader", "analyst", "viewer")
    return {"products": account_registry.PRODUCTS, "platforms": sorted(account_registry.PLATFORMS),
            "currencies": sorted(account_registry.CURRENCIES)}

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
def dashboard():
    return HTML


HTML = r"""
<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b1020">
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
 <div class="brand" style="margin-bottom:18px"><div class="logo">F</div><div><strong>FOREX AI</strong><small>HYBRID SCALPER</small></div></div>
 <div class="card login-card"><div style="display:flex;justify-content:flex-end;margin-bottom:12px"><select id="login-language" class="field" aria-label="Language" onchange="setLanguage(this.value)"><option value="fa">فارسی</option><option value="en">English</option><option value="ar">العربية</option><option value="tr">Türkçe</option></select></div><h2>به مرکز معاملات خوش آمدید</h2><p>برای ورود به فضای کاری امن، اطلاعات حساب خود را وارد کنید.</p>
 <input class="field" id="login-user" autocomplete="username" placeholder="نام کاربری">
 <input class="field" id="login-pass" type="password" autocomplete="current-password" placeholder="رمز عبور">
 <button class="primary" onclick="login()">ورود به پنل</button><div id="login-message" class="status">حساب کاربری خود را وارد کنید.</div></div>
</section>
<div id="app-shell" class="shell" hidden>
<aside class="sidebar">
 <div class="brand"><div class="logo">F</div><div><strong>FOREX AI</strong><small>HYBRID SCALPER</small></div></div>
 <div class="nav-title">فضای کاری</div>
 <nav class="nav">
  <button class="active" data-page="overview" onclick="goPage('overview',this)"><span class="ico">▦</span>نمای کلی</button>
  <button data-page="signals" onclick="goPage('signals',this)"><span class="ico">⌁</span>سیگنال‌ها</button>
  <button data-page="news" onclick="goPage(&quot;news&quot;,this)"><span class="ico">▤</span>خبرها</button>
  <button data-page="performance" onclick="goPage(&quot;performance&quot;,this)"><span class="ico">▥</span>عملکرد و نبض بازار</button>
  <button data-page="analysis" onclick="goPage('analysis',this)"><span class="ico">◫</span>تحلیل بازار</button>
  <button data-page="simulator" onclick="goPage('simulator',this)"><span class="ico">◉</span>شبیه‌ساز</button>
  <button data-page="modules" onclick="goPage('modules',this)"><span class="ico">◇</span>ماژول‌های AI</button>
  <button id="users-nav" data-page="users" onclick="goPage('users',this)" hidden><span class="ico">♙</span>مدیریت کاربران</button>
 </nav>
 <div class="side-bottom"><div class="safe"><b>● حالت امن فعال</b>معاملات واقعی غیرفعال هستند.</div></div>
</aside>
<main>
 <header class="topbar"><div><div class="eyebrow">مرکز کنترل / <span id="crumb">نمای کلی</span></div><div class="heading" id="page-title">داشبورد معاملاتی</div></div>
 <div class="top-actions"><select id="language-select" class="field" aria-label="Language" onchange="setLanguage(this.value)"><option value="fa">فارسی</option><option value="en">English</option><option value="ar">العربية</option><option value="tr">Türkçe</option></select><button class="icon-btn" onclick="toggleTheme()" title="تغییر پوسته">◐</button><div class="user-chip"><div class="avatar" id="avatar">U</div><div><b id="account-label">کاربر</b><div class="eyebrow" id="role-label">عضو</div></div></div><button class="ghost" onclick="logout()">خروج</button></div></header>
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
 <section id="page-modules" class="page"><div class="card"><div class="section-head"><h3>ماژول‌های هوش مصنوعی</h3><span class="pill">نمای معماری</span></div><div class="modules"><div class="module"><b>Market Scanner</b><small>اسکن نمادها و شرایط بازار</small></div><div class="module"><b>News Guard</b><small>فیلتر رویدادهای خبری</small></div><div class="module"><b>Adaptive AI</b><small>انتخاب رژیم و استراتژی</small></div><div class="module"><b>Ensemble AI</b><small>ترکیب مدل‌های تحلیلی</small></div><div class="module"><b>Smart Exit</b><small>مدیریت خروج و اهداف</small></div><div class="module"><b>Risk Manager</b><small>کنترل سرمایه و محدودیت‌ها</small></div></div></div></section>
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
let currentPage="overview";
const pageTitles={performance:"عملکرد و نبض بازار",news:"اخبار بازار",overview:"داشبورد معاملاتی",signals:"سیگنال‌های معاملاتی",analysis:"تحلیل بازار",simulator:"شبیه‌ساز تصمیم",modules:"ماژول‌های هوش مصنوعی",users:"مدیریت کاربران"};
let csrfToken='',currentUser=null;
async function api(path,options={}){const headers=Object.assign({"X-UI-Language":activeLocale},options.headers||{});if(options.method&&options.method!=='GET')headers['X-CSRF-Token']=csrfToken;return fetch(path,Object.assign({credentials:'same-origin'},options,{headers}));}
async function login(){const msg=document.getElementById('login-message');try{const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json','X-UI-Language':activeLocale},body:JSON.stringify({username:document.getElementById('login-user').value,password:document.getElementById('login-pass').value})});const d=await r.json();if(!r.ok)throw Error(t('ورود ناموفق بود')+(d.detail?' · '+d.detail:''));csrfToken=d.csrf_token;document.getElementById('login-pass').value='';showApp(d.user);}catch(e){msg.textContent=e.message;}}
function showApp(user){currentUser=user;document.getElementById('login-screen').hidden=true;document.getElementById('app-shell').hidden=false;document.getElementById('account-label').textContent=user.username;document.getElementById('role-label').textContent=t('نقش: ')+t(user.role);document.getElementById('avatar').textContent=(user.username||'U').slice(0,1).toUpperCase();document.getElementById('users-nav').hidden=user.role!=='admin';refreshStatus();if(user.role==='admin')loadUsers();}
async function restoreSession(){try{const r=await fetch('/api/auth/me',{credentials:'same-origin'});if(!r.ok)return;const d=await r.json();csrfToken=d.csrf_token;showApp(d.user);}catch(e){}}
function goPage(name,button){currentPage=name;if(name==='users'&&(!currentUser||currentUser.role!=='admin'))return;document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));document.getElementById('page-'+name).classList.add('active');document.querySelectorAll('.nav button').forEach(b=>b.classList.remove('active'));if(button)button.classList.add('active');if(name==='news')loadNews();if(name==='performance')loadPerformance();document.getElementById('page-title').textContent=t(pageTitles[name]);document.getElementById('crumb').textContent=t(pageTitles[name]);}
function toggleTheme(){document.documentElement.classList.toggle('light');}
async function logout(){try{await api('/api/auth/logout',{method:'POST'});}finally{csrfToken='';location.reload();}}
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
try{applyLanguage(localStorage.getItem('forexai-locale')||'fa');}catch(e){applyLanguage('fa');}
restoreSession();
</script>
</body></html>
"""

HTML = HTML.replace("__I18N_CATALOG__", json.dumps(catalog_for_frontend(), ensure_ascii=False))
