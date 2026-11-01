def choose_regime(adx_value: float, atr_ratio: float, history_ready: bool):
    if not history_ready:
        return "unknown"
    if atr_ratio >= 1.8:
        return "high_volatility"
    if adx_value >= 22:
        return "trend"
    return "range"

def choose_strategy(regime: str):
    return {
        "trend": "trend_following",
        "range": "range_reversion",
        "high_volatility": "breakout_wait",
        "unknown": "no_trade"
    }.get(regime, "no_trade")

def authorize_trade(symbol: str, action: str, regime: str, news_blocked: bool,
                    emergency_stop: bool, live_enabled: bool):
    if emergency_stop:
        return False, "emergency stop active"
    if not live_enabled:
        return False, "live trading disabled"
    if news_blocked:
        return False, "news blackout"
    if action not in ("BUY", "SELL"):
        return False, "no valid signal"
    if regime in ("unknown", "high_volatility"):
        return False, "market regime not approved"
    return True, "authorized by guards"
