import os
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from . import auth
from .config import AppConfig
from .engine import choose_regime, choose_strategy, authorize_trade

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

def current_session(request: Request):
    session = auth.get_session(request.cookies.get("forex_session"))
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return session

def require_role(request: Request, *roles: str):
    user, csrf = current_session(request)
    if user["role"] not in roles:
        raise HTTPException(status_code=403, detail="Insufficient role permissions.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not secrets_compare(supplied, csrf):
            raise HTTPException(status_code=403, detail="Invalid CSRF token.")
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
def login(payload: LoginPayload, response: Response):
    user = auth.authenticate(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "user": user}

@app.patch("/api/users/{user_id}/active")
def change_user_active(user_id: int, active: bool, request: Request):
    require_role(request, "admin")
    if not auth.set_user_active(user_id, active):
        raise HTTPException(status_code=404, detail="User not found.")
    return {"ok": True, "user_id": user_id, "active": active}

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
        raise HTTPException(status_code=400, detail="Symbol is not in the configured universe.")
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
<meta name="theme-color" content="#0b1220">
<title>Forex AI Hybrid Scalper</title>
<style>
:root{color-scheme:dark;--bg:#0b1220;--panel:#121d30;--line:#26354d;--muted:#9aa9bd;--text:#e8eef8;--green:#7fe0b3;--amber:#ffd18a;--red:#ff7777}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 85% 0,#182944 0,transparent 32%),var(--bg);color:var(--text);font:15px system-ui,-apple-system,sans-serif}
main{max-width:1180px;margin:auto;padding:26px 18px 50px}.top{display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap}
h1{font-size:clamp(22px,4vw,30px);margin:0}.sub,.muted,small{color:var(--muted)}.sub{margin-top:6px}
.pill{border:1px solid #28624d;background:#12372d;color:var(--green);border-radius:30px;padding:8px 13px;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin-top:20px}
.card{background:linear-gradient(150deg,#15233a,#111b2c);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 12px 30px #0002}
.label{color:var(--muted);font-size:13px}.value{font-size:27px;font-weight:800;margin:8px 0 2px;direction:ltr;text-align:right}
.green{color:var(--green)}.amber{color:var(--amber)}.red{color:var(--red)}
section{margin-top:16px}h2{font-size:18px;margin:0 0 14px}
.symbols,.modules{display:flex;gap:9px;flex-wrap:wrap}.tag,.module{background:#1a2a42;border:1px solid #2b405d;border-radius:10px;padding:10px 12px}
.module{flex:1 1 130px}.module b{display:block;margin-bottom:3px}
.actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
button,select{border:1px solid #40516b;border-radius:10px;padding:11px 14px;background:#1a2a42;color:var(--text);font:inherit}
button{cursor:pointer;font-weight:700}button.danger{background:#762d35;border-color:#a84c54}button:disabled{opacity:.55;cursor:wait}
.status{padding:12px;border-radius:12px;background:#1b2b42;color:var(--amber);margin-top:10px}
#toast{min-height:22px;color:var(--green);margin-top:10px}
footer{margin-top:18px;color:var(--muted);font-size:12px;line-height:1.8}
@media(max-width:560px){main{padding:18px 12px 36px}.card{padding:15px}.value{font-size:24px}}
</style>
</head>
<body><main>
<header class="top"><div><h1>Forex AI Hybrid Scalper</h1><div class="sub">پنل یکپارچه وب و دسکتاپ · نسخه ۵.۲</div></div><span class="pill">حالت امن · فقط آزمایشی</span></header>
<section class="card" id="login-card"><h2>ورود کاربران</h2><div class="actions"><input id="login-user" autocomplete="username" placeholder="نام کاربری"><input id="login-pass" type="password" autocomplete="current-password" placeholder="رمز عبور"><button onclick="login()">ورود</button></div><div id="login-message" class="status">برای مشاهده پنل وارد حساب کاربری شوید.</div></section>
<section class="card" id="account-card" hidden><div class="actions"><b id="account-label"></b><span id="role-label" class="pill"></span><button onclick="logout()">خروج امن</button></div></section>
<section class="card" id="users-card" hidden><h2>مدیریت کاربران (فقط مدیر)</h2><div class="actions"><input id="new-username" placeholder="نام کاربری جدید"><input id="new-password" type="password" autocomplete="new-password" placeholder="رمز عبور حداقل ۱۴ نویسه"><select id="new-role"><option value="trader">معامله‌گر</option><option value="analyst">تحلیل‌گر</option><option value="viewer">فقط مشاهده</option></select><button onclick="createUser()">ساخت کاربر</button></div><div id="users-list" class="status"></div></section>
<div id="app-content" hidden>
<div class="grid">
 <article class="card"><div class="label">سرمایه فرضی آزمایش</div><div class="value">$500</div><small>سرمایه واقعی متصل نیست</small></article>
 <article class="card"><div class="label">ریسک هر معامله FX</div><div class="value">0.25%</div><small>طلا: 0.10%</small></article>
 <article class="card"><div class="label">حد توقف زیان روزانه</div><div class="value">1.00%</div><small>قفل ریسک مستقل</small></article>
 <article class="card"><div class="label">اجرای سفارش واقعی</div><div class="value red">غیرفعال</div><small>اتصال بروکر و MT5 برقرار نیست</small></article>
</div>
<section class="card"><h2>وضعیت سرویس</h2><div id="status" class="status">در حال دریافت وضعیت…</div><div id="toast"></div></section>
<section class="card"><h2>نمادهای پیکربندی‌شده</h2><div class="symbols"><span class="tag">EURUSD</span><span class="tag">GBPUSD</span><span class="tag">USDJPY</span><span class="tag">AUDUSD</span><span class="tag">USDCAD</span><span class="tag">USDCHF</span><span class="tag">EURJPY</span><span class="tag">XAUUSD · Gold</span></div></section>
<section class="card"><h2>ماژول‌های پروژه</h2><div class="modules">
<div class="module"><b>Scanner</b><small>اسکن بازار - آماده اتصال</small></div><div class="module"><b>News Guard</b><small>فیلتر خبر fail-closed</small></div><div class="module"><b>Adaptive AI</b><small>انتخاب رژیم و استراتژی</small></div><div class="module"><b>Ensemble</b><small>MLP · LSTM · XGBoost</small></div><div class="module"><b>Smart Exit</b><small>برنامه‌ریز SL/TP</small></div><div class="module"><b>Risk Manager</b><small>کنترل ریسک پایه</small></div><div class="module"><b>MT5 Bridge</b><small>هنوز متصل نشده</small></div></div></section>
<section class="card"><h2>کنترل اضطراری</h2><p class="muted">این دکمه قفل اضطراری پنل را فعال می‌کند. اجرای سفارش در این نسخه از ابتدا غیرفعال است.</p><div class="actions"><button id="stop" class="danger" onclick="activateStop()">فعال‌کردن توقف اضطراری</button><button onclick="refreshStatus()">به‌روزرسانی وضعیت</button></div></section>
<section class="card"><h2>پیش‌نمایش تصمیم (غیرواقعی)</h2><div class="actions"><select id="symbol"><option>XAUUSD</option><option>EURUSD</option><option>GBPUSD</option><option>USDJPY</option></select><button onclick="preview()">نمایش پیش‌نمایش</button></div><div id="preview" class="status">این بخش سیگنال زنده تولید نمی‌کند.</div></section>
<footer>این برنامه در وضعیت توسعه است؛ قیمت زنده، تقویم اقتصادی معتبر، اتصال بروکر و ارسال سفارش ندارد. اطلاعات ورود و کلیدهای API را در GitHub قرار ندهید. پیش از استفاده از راه دور، احراز هویت، HTTPS و محدودسازی شبکه لازم است.</footer>
</div>
</main>
<script>
let csrfToken = '';
async function api(path, options={}) {
 const headers = Object.assign({}, options.headers || {});
 if (options.method && options.method !== 'GET') headers['X-CSRF-Token'] = csrfToken;
 return fetch(path, Object.assign({credentials:'same-origin'}, options, {headers}));
}
async function login(){
 const message=document.getElementById('login-message');
 try{
  const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:document.getElementById('login-user').value,password:document.getElementById('login-pass').value})});
  const d=await r.json(); if(!r.ok) throw new Error(d.detail||'ورود ناموفق بود');
  csrfToken=d.csrf_token; showAccount(d.user); document.getElementById('login-pass').value=''; message.textContent='ورود موفق بود.';
 }catch(e){message.textContent=e.message;}
}
function showAccount(user){
 document.getElementById('login-card').hidden=true;
 document.getElementById('account-card').hidden=false;
 document.getElementById('account-label').textContent='کاربر: '+user.username;
 document.getElementById('role-label').textContent='نقش: '+user.role;
 document.getElementById('app-content').hidden=false;
 document.getElementById('users-card').hidden=user.role!=='admin';
 if(user.role==='admin') loadUsers();
 refreshStatus();
}
async function restoreSession(){
 try{
  const r=await fetch('/api/auth/me',{credentials:'same-origin'}); if(!r.ok)return;
  const d=await r.json(); csrfToken=d.csrf_token; showAccount(d.user);
 }catch(e){}
}
async function logout(){
 try{await api('/api/auth/logout',{method:'POST'});}finally{csrfToken='';location.reload();}
}
async function loadUsers(){
 const el=document.getElementById('users-list');
 try{
  const r=await fetch('/api/users');const d=await r.json();if(!r.ok)throw new Error(d.detail||'خطا');
  el.replaceChildren();
  d.users.forEach(u=>{const row=document.createElement('div');row.className='actions';const label=document.createElement('span');label.textContent=u.username+' · '+u.role+' · '+(u.active?'فعال':'غیرفعال');row.appendChild(label);
   if(u.role!=='admin'){const b=document.createElement('button');b.textContent=u.active?'غیرفعال‌کردن':'فعال‌کردن';b.onclick=()=>setUserActive(u.id,!u.active);row.appendChild(b);}el.appendChild(row);});
 }catch(e){el.textContent=e.message;}
}
async function createUser(){
 try{const r=await api('/api/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:document.getElementById('new-username').value,password:document.getElementById('new-password').value,role:document.getElementById('new-role').value})});const d=await r.json();if(!r.ok)throw new Error(d.detail||'خطا');document.getElementById('new-password').value='';await loadUsers();}
 catch(e){document.getElementById('users-list').textContent=e.message;}
}
async function setUserActive(id,active){
 try{const r=await api('/api/users/'+id+'/active?active='+active,{method:'PATCH'});const d=await r.json();if(!r.ok)throw new Error(d.detail||'خطا');await loadUsers();}
 catch(e){document.getElementById('users-list').textContent=e.message;}
}
async function refreshStatus(){
 const el=document.getElementById('status');
 try{
  const r=await fetch('/api/status'); if(!r.ok) throw new Error('HTTP '+r.status);
  const d=await r.json();
  el.innerHTML='توقف اضطراری: <b class="'+(d.emergency_stop?'red':'green')+'">'+(d.emergency_stop?'فعال':'غیرفعال')+'</b> · فیلتر خبر: <b>'+(d.news_filter_enabled?'روشن':'خاموش')+'</b> · اتصال MT5: <b>ندارد</b> · معامله واقعی: <b class="red">غیرفعال</b>';
 }catch(e){el.textContent='ارتباط با بک‌اند برقرار نشد: '+e.message}
}
async function activateStop(){
 const b=document.getElementById('stop'),t=document.getElementById('toast');b.disabled=true;
 try{const r=await api('/api/emergency-stop',{method:'POST'});if(!r.ok)throw new Error('HTTP '+r.status);t.textContent='قفل توقف اضطراری فعال شد.';await refreshStatus();}
 catch(e){t.textContent='خطا در فعال‌سازی توقف: '+e.message;}
 finally{b.disabled=false;}
}
async function preview(){
 const s=document.getElementById('symbol').value,el=document.getElementById('preview');
 try{const r=await fetch('/api/decision-preview?symbol='+encodeURIComponent(s));const d=await r.json();if(!r.ok)throw new Error(d.detail||'request failed');
 el.textContent=s+' · رژیم: '+d.regime+' · استراتژی: '+d.strategy+' · مجوز اجرا: خیر ('+d.guard_reason+')';
 }catch(e){el.textContent='پیش‌نمایش در دسترس نیست: '+e.message;}
}
restoreSession();
</script></body></html>
"""
