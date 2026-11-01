from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from .config import AppConfig
from .engine import choose_regime, choose_strategy, authorize_trade

app = FastAPI(title="Forex AI Hybrid Scalper", version="5.1.0")
cfg = AppConfig()
# Process-local latch. It starts active on every restart; execution remains disabled.
_emergency_stop_active = True


@app.get("/api/health")
def health():
    return {"ok": True, "service": "control-center"}


@app.get("/api/status")
def status():
    return {
        "app": "Forex AI Hybrid Scalper",
        "version": "5.1.0",
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
def activate_emergency_stop():
    global _emergency_stop_active
    _emergency_stop_active = True
    return {"ok": True, "emergency_stop": True, "message": "Emergency stop latched."}


@app.get("/api/decision-preview")
def decision_preview(adx: float = 25, atr_ratio: float = 1.0, symbol: str = "XAUUSD"):
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
<header class="top"><div><h1>Forex AI Hybrid Scalper</h1><div class="sub">پنل یکپارچه وب و دسکتاپ · نسخه ۵.۱</div></div><span class="pill">حالت امن · فقط آزمایشی</span></header>
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
</main>
<script>
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
 try{const r=await fetch('/api/emergency-stop',{method:'POST'});if(!r.ok)throw new Error('HTTP '+r.status);t.textContent='قفل توقف اضطراری فعال شد.';await refreshStatus();}
 catch(e){t.textContent='خطا در فعال‌سازی توقف: '+e.message;}
 finally{b.disabled=false;}
}
async function preview(){
 const s=document.getElementById('symbol').value,el=document.getElementById('preview');
 try{const r=await fetch('/api/decision-preview?symbol='+encodeURIComponent(s));const d=await r.json();if(!r.ok)throw new Error(d.detail||'request failed');
 el.textContent=s+' · رژیم: '+d.regime+' · استراتژی: '+d.strategy+' · مجوز اجرا: خیر ('+d.guard_reason+')';
 }catch(e){el.textContent='پیش‌نمایش در دسترس نیست: '+e.message;}
}
refreshStatus();
</script></body></html>
"""
