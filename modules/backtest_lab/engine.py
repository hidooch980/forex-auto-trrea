"""Leakage-conscious EMA crossover backtest on caller-supplied historical OHLC bars.

This is a research simulator, not an execution adapter or performance guarantee.
Signals are formed at bar close and orders are modelled at the following bar open.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
import math
from typing import Iterable

@dataclass(frozen=True)
class BacktestCandle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float

@dataclass(frozen=True)
class Trade:
    side: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    gross_return_pct: float
    costs_pct: float
    net_return_pct: float
    exit_reason: str

@dataclass(frozen=True)
class BacktestResult:
    bars: int
    fast_period: int
    slow_period: int
    initial_equity: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    win_rate_pct: float
    profit_factor: float | None
    trades: tuple[Trade, ...]
    execution_allowed: bool = False
    def to_dict(self):
        result=asdict(self); result["trades"]=[asdict(t) for t in self.trades]
        return result

def _ema_series(values: list[float], period: int) -> list[float]:
    alpha=2.0/(period+1.0); out=[values[0]]
    for value in values[1:]: out.append(alpha*value+(1-alpha)*out[-1])
    return out

def run_ema_backtest(candles: Iterable[BacktestCandle], *, fast_period: int=9,
                     slow_period: int=21, initial_equity: float=10000.0,
                     cost_bps_per_side: float=1.0) -> BacktestResult:
    rows=list(candles)
    if not 2 <= fast_period < slow_period <= 200:
        raise ValueError("periods must satisfy 2 <= fast < slow <= 200")
    if not slow_period+2 <= len(rows) <= 10000:
        raise ValueError("historical bars must be between slow_period+2 and 10000")
    if not math.isfinite(initial_equity) or initial_equity <= 0:
        raise ValueError("initial equity must be finite and positive")
    if not math.isfinite(cost_bps_per_side) or not 0 <= cost_bps_per_side <= 1000:
        raise ValueError("cost per side must be between 0 and 1000 bps")
    prev=None
    for c in rows:
        if c.timestamp.tzinfo is None or c.timestamp.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        stamp=c.timestamp
        if prev is not None and stamp <= prev: raise ValueError("timestamps must be strictly increasing")
        prev=stamp
        vals=(c.open,c.high,c.low,c.close)
        if not all(math.isfinite(v) and v>0 for v in vals):
            raise ValueError("OHLC prices must be finite and positive")
        if c.high < max(c.open,c.close,c.low) or c.low > min(c.open,c.close,c.high):
            raise ValueError("invalid OHLC geometry")
    closes=[c.close for c in rows]
    fast=_ema_series(closes,fast_period); slow=_ema_series(closes,slow_period)
    side=0; entry_price=0.0; entry_idx=0; trades=[]
    equity=initial_equity; peak=initial_equity; max_dd=0.0
    cost_round_trip=2.0*cost_bps_per_side/10000.0
    for i in range(slow_period, len(rows)-1):
        desired=1 if fast[i]>slow[i] else -1 if fast[i]<slow[i] else 0
        if desired==side: continue
        execution=rows[i+1].open
        if side:
            gross=side*(execution/entry_price-1.0)
            net=gross-cost_round_trip
            equity*=max(0.0,1.0+net)
            trades.append(Trade("long" if side>0 else "short",
                rows[entry_idx].timestamp.isoformat(),rows[i+1].timestamp.isoformat(),
                entry_price,execution,gross*100.0,cost_round_trip*100.0,net*100.0,"opposite_signal"))
            peak=max(peak,equity); max_dd=max(max_dd,(peak-equity)/peak if peak else 0.0)
        side=desired
        if side:
            entry_price=execution; entry_idx=i+1
    if side:
        last=rows[-1]; execution=last.close
        gross=side*(execution/entry_price-1.0); net=gross-cost_round_trip
        equity*=max(0.0,1.0+net)
        trades.append(Trade("long" if side>0 else "short",
            rows[entry_idx].timestamp.isoformat(),last.timestamp.isoformat(),
            entry_price,execution,gross*100.0,cost_round_trip*100.0,net*100.0,"end_of_test_mark"))
        peak=max(peak,equity); max_dd=max(max_dd,(peak-equity)/peak if peak else 0.0)
    wins=sum(t.net_return_pct>0 for t in trades)
    gross_profit=sum(t.net_return_pct for t in trades if t.net_return_pct>0)
    gross_loss=-sum(t.net_return_pct for t in trades if t.net_return_pct<0)
    pf=(gross_profit/gross_loss) if gross_loss>0 else None
    return BacktestResult(len(rows),fast_period,slow_period,initial_equity,equity,
        (equity/initial_equity-1)*100.0,max_dd*100.0,len(trades),
        wins/len(trades)*100.0 if trades else 0.0,pf,tuple(trades),False)
