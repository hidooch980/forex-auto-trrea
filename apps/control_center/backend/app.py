from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from .config import AppConfig
from .engine import choose_regime, choose_strategy, authorize_trade
from .guards import daily_loss_locked, news_guard

app = FastAPI(title="Forex AI Hybrid Scalper", version="5.0.0")
cfg = AppConfig()

@app.get("/api/status")
def status():
    return {
        "app": "Forex AI Hybrid Scalper",
        "version": "5.0.0",
        "mode": "DEMO / SAFE DEFAULTS",
        "live_trading_enabled": cfg.live_trading_enabled,
        "emergency_stop": cfg.emergency_stop,
        "news_filter_enabled": cfg.news_filter_enabled,
        "symbols": cfg.symbols,
        "risk": {"fx": cfg.fx_risk_fraction, "gold": cfg.gold_risk_fraction,
                 "daily_stop": cfg.daily_loss_limit}
    }

@app.get("/api/health")
def health():
    return {"ok": True}

@app.get("/api/decision-preview")
def decision_preview(adx: float = 25, atr_ratio: float = 1.0, symbol: str = "XAUUSD"):
    regime = choose_regime(adx, atr_ratio, True)
    strategy = choose_strategy(regime)
    return {"symbol": symbol, "regime": regime, "strategy": strategy,
            "note": "Illustrative preview only; not a live market signal."}

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTML
HTML = r"""
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Forex AI Hybrid Scalper</title>
<style>
body{margin:0;background:#0b1220;color:#e8eef8;font:15px system-ui}
main{max-width:1100px;margin:auto;padding:28px}
header{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
h1{margin:0;font-size:26px}.muted{color:#9aa9bd}.pill{background:#173c30;color:#8ce0b6;padding:7px 12px;border-radius:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-top:22px}
.card{background:#121d30;border:1px solid #26354d;border-radius:14px;padding:18px}
.big{font-size:27px;font-weight:700}.warn{color:#ffcf80}.green{color:#8ce0b6}
button{background:#a93232;color:white;border:0;border-radius:10px;padding:12px 16px;font-weight:700;cursor:pointer}
small{color:#9aa9bd} .modules{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.module{background:#17243a;padding:13px;border-radius:10px}
</style></head><body><main>
<header><div><h1>FOREX AI HYBRID SCALPER</h1><div class="muted">Unified Web + Desktop Control Center</div></div><span class="pill">SAFE MODE · DEMO FIRST</span></header>
<section class="grid">
<div class="card"><small>Assumed test capital</small><div class="big">$500</div><small>Configure actual account after broker validation</small></div>
<div class="card"><small>FX risk / trade</small><div class="big">0.25%</div><small>Gold risk / trade: 0.10%</small></div>
<div class="card"><small>Daily loss guard</small><div class="big">1.00%</div><small>Fail-closed risk policy</small></div>
<div class="card"><small>Live execution</small><div class="big warn">DISABLED</div><small>EA order execution is not yet implemented</small></div>
</section>
<section class="card" style="margin-top:16px"><h2>Market universe</h2><p>EURUSD · GBPUSD · USDJPY · AUDUSD · USDCAD · USDCHF · EURJPY · <b class="green">XAUUSD Gold</b></p></section>
<section class="card" style="margin-top:16px"><h2>Unified skill modules</h2><div class="modules">
<div class="module">Scanner</div><div class="module">News Guard</div><div class="module">Analyst</div><div class="module">Adaptive Entry</div><div class="module">Smart Exit</div><div class="module">Time Machine</div><div class="module">Risk Manager</div><div class="module">Capital Manager</div><div class="module">Broker Manager</div><div class="module">Alerts</div><div class="module">Performance</div></div></section>
<section class="card" style="margin-top:16px"><h2>Safety controls</h2><p class="warn">Emergency stop is ON. Live trading is OFF. News filter is ON and blocks trades if calendar data is missing or stale.</p><button onclick="alert('Emergency stop is already active in this starter. Backend control endpoint will be added after authentication and MT5 bridge validation.')">Emergency stop status</button></section>
<p class="muted"><small>Development scaffold only. No live quotes, broker connection, economic calendar provider or order placement are bundled.</small></p>
</main></body></html>
"""
