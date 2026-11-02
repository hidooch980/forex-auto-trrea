"""Deterministic OHLC market analysis. No broker or order-routing functionality."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import math
from typing import Iterable

@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

@dataclass(frozen=True)
class RadarResult:
    symbol: str; timeframe: str; bars: int; latest_close: float
    ema_fast: float; ema_slow: float; rsi_14: float; atr_14: float; atr_pct: float
    trend: str; momentum: str; volatility: str; stance: str; confidence: float
    data_status: str; reasons: tuple[str, ...]; execution_allowed: bool = False
    def to_dict(self):
        result = asdict(self); result["reasons"] = list(self.reasons); return result

def _ema(values: list[float], period: int) -> float:
    alpha = 2.0 / (period + 1.0); value = values[0]
    for item in values[1:]: value = alpha * item + (1.0 - alpha) * value
    return value

def _rsi(values: list[float], period: int = 14) -> float:
    changes = [values[i] - values[i-1] for i in range(1, len(values))]
    gains = [max(x, 0.0) for x in changes]; losses = [max(-x, 0.0) for x in changes]
    avg_gain = sum(gains[:period]) / period; avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = ((period-1)*avg_gain + gain) / period
        avg_loss = ((period-1)*avg_loss + loss) / period
    if avg_loss == 0: return 100.0 if avg_gain > 0 else 50.0
    if avg_gain == 0: return 0.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

def _atr(candles: list[Candle], period: int = 14) -> float:
    ranges = []
    for i, c in enumerate(candles):
        if i == 0: ranges.append(c.high-c.low)
        else:
            prev = candles[i-1].close
            ranges.append(max(c.high-c.low, abs(c.high-prev), abs(c.low-prev)))
    value = sum(ranges[:period]) / period
    for current in ranges[period:]: value = ((period-1)*value + current) / period
    return value

def analyze_market(symbol: str, timeframe: str, candles: Iterable[Candle], *,
                   now: datetime | None = None, max_age_seconds: int = 900,
                   max_future_seconds: int = 30) -> RadarResult:
    """Analyze completed OHLC bars; reject malformed, stale or future data.

    Caller must ensure the final bar is closed. This engine cannot infer provider
    finality, broker session state, spread, liquidity or executable prices.
    """
    if not symbol or len(symbol)>32 or not timeframe or len(timeframe)>16:
        raise ValueError("symbol and timeframe are required and must be short identifiers")
    if max_age_seconds < 1 or max_future_seconds < 0: raise ValueError("invalid freshness limits")
    rows = list(candles)
    if not 30 <= len(rows) <= 1000: raise ValueError("between 30 and 1000 candles are required")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None: raise ValueError("now must be timezone-aware")
    current = current.astimezone(timezone.utc); previous = None
    for c in rows:
        if c.timestamp.tzinfo is None or c.timestamp.utcoffset() is None:
            raise ValueError("all candle timestamps must be timezone-aware")
        stamp = c.timestamp.astimezone(timezone.utc)
        if previous is not None and stamp <= previous: raise ValueError("candle timestamps must be strictly increasing")
        previous = stamp
        values = (c.open,c.high,c.low,c.close,c.volume)
        if not all(math.isfinite(v) for v in values): raise ValueError("OHLCV values must be finite")
        if min(c.open,c.high,c.low,c.close) <= 0 or c.volume < 0: raise ValueError("prices must be positive and volume cannot be negative")
        if c.high < max(c.open,c.close,c.low): raise ValueError("candle high is inconsistent")
        if c.low > min(c.open,c.close,c.high): raise ValueError("candle low is inconsistent")
    age = (current - rows[-1].timestamp.astimezone(timezone.utc)).total_seconds()
    if age > max_age_seconds: raise ValueError("latest candle is stale")
    if age < -max_future_seconds: raise ValueError("latest candle timestamp is in the future")
    closes = [c.close for c in rows]
    fast = _ema(closes[-min(len(closes),50):],9); slow = _ema(closes[-min(len(closes),100):],21)
    rsi = _rsi(closes[-15:]); atr = _atr(rows[-15:]); atr_pct = atr/closes[-1]*100.0
    trend = "bullish" if fast>slow else "bearish" if fast<slow else "sideways"
    momentum = "overbought" if rsi>=70 else "oversold" if rsi<=30 else "neutral"
    volatility = "high" if atr_pct>=1.0 else "normal"
    reasons = [f"EMA9 {trend} relative to EMA21",f"RSI14={rsi:.2f}",f"ATR14={atr:.6g} ({atr_pct:.3f}%)"]
    stance="HOLD"; confidence=0.0
    if trend=="bullish" and 50<rsi<70: stance="BUY_BIAS"; confidence=min(0.75,0.50+(rsi-50)/100.0)
    elif trend=="bearish" and 30<rsi<50: stance="SELL_BIAS"; confidence=min(0.75,0.50+(50-rsi)/100.0)
    else: reasons.append("trend/momentum confirmation is insufficient; remain on HOLD")
    if volatility=="high":
        stance="HOLD"; confidence=0.0; reasons.append("high ATR percentage suppresses directional bias")
    return RadarResult(symbol.upper(),timeframe,len(rows),closes[-1],fast,slow,rsi,atr,atr_pct,
        trend,momentum,volatility,stance,round(confidence,4),"valid",tuple(reasons),False)
