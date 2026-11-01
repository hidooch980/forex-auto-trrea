from dataclasses import dataclass
from typing import Optional, Dict, Any
import math

@dataclass(frozen=True)
class ExitConfig:
    fx_atr_sl: float = 1.5
    gold_atr_sl: float = 2.0
    swing_buffer_atr: float = 0.10
    min_sl_atr: float = 0.80
    max_sl_atr: float = 3.00
    trend_tp_r: float = 2.2
    range_tp_r: float = 1.3
    high_vol_tp_r: float = 1.5
    default_tp_r: float = 1.8
    partial_trigger_r: float = 1.0
    partial_fraction: float = 0.50
    breakeven_trigger_r: float = 1.0
    trailing_start_r: float = 1.2
    trailing_atr_multiple: float = 1.2
    min_trailing_atr: float = 0.8

def _positive(name, value):
    if value is None or not math.isfinite(float(value)) or float(value) <= 0:
        raise ValueError(f"{name} must be a finite positive number")

def plan_trade(symbol: str, side: str, entry: float, atr: float,
               swing_low: Optional[float] = None,
               swing_high: Optional[float] = None,
               regime: str = "UNKNOWN", spread: float = 0.0,
               config: ExitConfig = ExitConfig()) -> Dict[str, Any]:
    """Create initial SL/TP. Swing levels must come from completed candles."""
    side = side.upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    _positive("entry", entry); _positive("atr", atr)
    if spread < 0 or not math.isfinite(float(spread)):
        raise ValueError("spread must be finite and non-negative")
    is_gold = "XAU" in symbol.upper() or "GOLD" in symbol.upper()
    sl_mult = config.gold_atr_sl if is_gold else config.fx_atr_sl
    buffer = max(spread, atr * config.swing_buffer_atr)
    if side == "BUY":
        candidates = [entry - atr * sl_mult]
        if swing_low is not None:
            candidates.append(float(swing_low) - buffer)
        raw_sl = min(candidates)
        risk = entry - raw_sl
        if risk <= 0: raise ValueError("Invalid BUY stop")
        risk = min(max(risk, atr*config.min_sl_atr), atr*config.max_sl_atr)
        sl = entry - risk
    else:
        candidates = [entry + atr * sl_mult]
        if swing_high is not None:
            candidates.append(float(swing_high) + buffer)
        raw_sl = max(candidates)
        risk = raw_sl - entry
        if risk <= 0: raise ValueError("Invalid SELL stop")
        risk = min(max(risk, atr*config.min_sl_atr), atr*config.max_sl_atr)
        sl = entry + risk

    regime = regime.upper().replace(" ", "_")
    tp_r = {
        "TREND": config.trend_tp_r,
        "RANGE": config.range_tp_r,
        "HIGH_VOLATILITY": config.high_vol_tp_r,
        "HIGH_VOL": config.high_vol_tp_r,
    }.get(regime, config.default_tp_r)
    tp = entry + risk*tp_r if side == "BUY" else entry - risk*tp_r
    return {
        "symbol": symbol, "side": side, "entry": float(entry),
        "sl": float(sl), "tp": float(tp), "risk_distance": float(risk),
        "tp_r_multiple": float(tp_r), "partial_trigger": float(
            entry + risk*config.partial_trigger_r if side == "BUY"
            else entry - risk*config.partial_trigger_r),
        "breakeven_trigger": float(
            entry + risk*config.breakeven_trigger_r if side == "BUY"
            else entry - risk*config.breakeven_trigger_r),
        "trailing_start": float(
            entry + risk*config.trailing_start_r if side == "BUY"
            else entry - risk*config.trailing_start_r),
    }

def _tighten_only(side: str, old_sl: float, proposed_sl: float) -> float:
    # Long SL may only rise; short SL may only fall.
    return max(old_sl, proposed_sl) if side == "BUY" else min(old_sl, proposed_sl)

def manage_open_trade(side: str, entry: float, current_price: float,
                      current_atr: float, current_sl: float,
                      state: Dict[str, Any],
                      config: ExitConfig = ExitConfig(),
                      cost_buffer: float = 0.0) -> Dict[str, Any]:
    """Return management instructions; caller executes them after broker checks."""
    side = side.upper()
    if side not in ("BUY", "SELL"): raise ValueError("side must be BUY or SELL")
    for n,v in (("entry",entry),("current_price",current_price),
                ("current_atr",current_atr),("current_sl",current_sl)):
        _positive(n,v)
    if cost_buffer < 0: raise ValueError("cost_buffer must be non-negative")
    initial_risk = float(state.get("initial_risk", 0))
    _positive("state.initial_risk", initial_risk)
    move = current_price-entry if side=="BUY" else entry-current_price
    r_now = move/initial_risk
    partial_done = bool(state.get("partial_done", False))
    close_fraction = 0.0
    if not partial_done and r_now >= config.partial_trigger_r:
        close_fraction = config.partial_fraction
    new_sl = current_sl
    reasons = []
    if r_now >= config.breakeven_trigger_r:
        be = entry + cost_buffer if side=="BUY" else entry-cost_buffer
        new_sl = _tighten_only(side, new_sl, be)
        reasons.append("break_even")
    if r_now >= config.trailing_start_r:
        distance = max(current_atr*config.trailing_atr_multiple,
                       current_atr*config.min_trailing_atr)
        candidate = current_price-distance if side=="BUY" else current_price+distance
        tightened = _tighten_only(side, new_sl, candidate)
        if tightened != new_sl:
            new_sl = tightened
            reasons.append("atr_trailing")
    return {
        "r_multiple": float(r_now),
        "close_fraction": float(close_fraction),
        "mark_partial_done_after_confirmed_close": bool(close_fraction > 0),
        "new_sl": float(new_sl),
        "modify_sl": bool(new_sl != current_sl),
        "reasons": reasons,
    }
