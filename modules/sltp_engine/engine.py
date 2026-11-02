"""Adaptive SL/TP planner using ATR, recent swing structure and broker metadata.

No broker connection and no order execution. All input candles must be completed bars.
Risk sizing uses broker tick size/value and rounds volume DOWN to the broker step.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
from math import floor, isfinite
from typing import Sequence

@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float

@dataclass(frozen=True)
class BrokerSpec:
    point: float
    tick_size: float
    tick_value_loss: float
    digits: int
    stops_level_points: int
    freeze_level_points: int
    volume_min: float
    volume_max: float
    volume_step: float

@dataclass(frozen=True)
class SLTPPlan:
    valid: bool
    reasons: tuple[str, ...]
    side: str
    entry: float
    stop_loss: float | None
    take_profit: float | None
    atr: float
    atr_points: float
    risk_distance: float
    reward_distance: float
    reward_risk: float
    risk_budget: float
    volume: float
    estimated_risk_money: float
    execution_allowed: bool = False
    def to_dict(self):
        return asdict(self)

def _finite_positive(name: str, value: float) -> None:
    if not isinstance(value,(int,float)) or not isfinite(float(value)) or value<=0:
        raise ValueError(f"{name} must be finite and positive")

def _atr(rows: Sequence[Candle], period: int) -> float:
    trs=[]
    for i,row in enumerate(rows):
        prev=rows[i-1].close if i else row.close
        trs.append(max(row.high-row.low,abs(row.high-prev),abs(row.low-prev)))
    if len(trs)<period: raise ValueError("not enough bars for ATR")
    value=sum(trs[:period])/period
    for tr in trs[period:]:
        value=(value*(period-1)+tr)/period
    return value

def _floor_tick(price: float, tick: float) -> float:
    return floor(price/tick+1e-10)*tick

def _ceil_tick(price: float, tick: float) -> float:
    return -floor(-price/tick+1e-10)*tick

def _floor_volume(volume: float, step: float) -> float:
    return floor(volume/step+1e-10)*step

def plan_sltp(candles: Sequence[Candle], *, side: str, entry: float,
              spec: BrokerSpec, equity: float, risk_pct: float=0.25,
              reward_risk: float=1.5, atr_period: int=14,
              atr_multiple: float=1.5, swing_lookback: int=20,
              spread_points: float=0.0, max_atr_multiple: float=4.0) -> SLTPPlan:
    if side not in {"buy","sell"}: raise ValueError("side must be buy or sell")
    _finite_positive("entry",entry); _finite_positive("equity",equity)
    for name,value in (("point",spec.point),("tick_size",spec.tick_size),
        ("tick_value_loss",spec.tick_value_loss),("volume_min",spec.volume_min),
        ("volume_max",spec.volume_max),("volume_step",spec.volume_step),
        ("risk_pct",risk_pct),("reward_risk",reward_risk),
        ("atr_multiple",atr_multiple),("max_atr_multiple",max_atr_multiple)):
        _finite_positive(name,value)
    if spec.digits<0 or spec.digits>10 or spec.stops_level_points<0 or spec.freeze_level_points<0:
        raise ValueError("invalid broker price constraints")
    if spec.volume_max<spec.volume_min: raise ValueError("invalid broker volume range")
    if not 0<risk_pct<=0.25: raise ValueError("risk_pct must be within (0, 0.25]")
    if reward_risk<1.0 or reward_risk>5.0: raise ValueError("reward_risk must be between 1 and 5")
    if not 2<=atr_period<=100 or not atr_period+2<=len(candles)<=5000:
        raise ValueError("invalid candle count for ATR")
    if not 3<=swing_lookback<=200 or len(candles)<swing_lookback:
        raise ValueError("invalid swing lookback")
    if not isfinite(spread_points) or spread_points<0: raise ValueError("spread_points must be finite and non-negative")
    previous=None
    for c in candles:
        if c.timestamp.tzinfo is None or c.timestamp.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        if previous is not None and c.timestamp<=previous: raise ValueError("timestamps must be strictly increasing")
        previous=c.timestamp
        for name,value in (("open",c.open),("high",c.high),("low",c.low),("close",c.close)):
            _finite_positive(name,value)
        if c.high<max(c.open,c.close,c.low) or c.low>min(c.open,c.close,c.high):
            raise ValueError("invalid OHLC geometry")
    atr=_atr(candles,atr_period)
    recent=candles[-swing_lookback:]
    spread=spread_points*spec.point
    buffer=max(spread, spec.point)
    if side=="buy":
        structural=min(c.low for c in recent)-buffer
        volatility=entry-atr*atr_multiple
        raw_stop=min(structural,volatility)
        stop=_floor_tick(raw_stop,spec.tick_size)
        distance=entry-stop
        target=_ceil_tick(entry+distance*reward_risk,spec.tick_size)
    else:
        structural=max(c.high for c in recent)+buffer
        volatility=entry+atr*atr_multiple
        raw_stop=max(structural,volatility)
        stop=_ceil_tick(raw_stop,spec.tick_size)
        distance=stop-entry
        target=_floor_tick(entry-distance*reward_risk,spec.tick_size)
    target=round(target,spec.digits); stop=round(stop,spec.digits)
    reasons=[]
    min_distance=max(spec.stops_level_points,spec.freeze_level_points)*spec.point+spread
    if distance<=0: reasons.append("non_positive_stop_distance")
    if distance<min_distance: reasons.append("broker_minimum_stop_distance")
    if distance>atr*max_atr_multiple: reasons.append("structure_too_far_from_entry")
    if side=="buy" and not (stop<entry<target): reasons.append("invalid_buy_price_geometry")
    if side=="sell" and not (target<entry<stop): reasons.append("invalid_sell_price_geometry")
    budget=equity*risk_pct/100.0
    loss_per_lot=(distance/spec.tick_size)*spec.tick_value_loss
    raw_volume=budget/loss_per_lot if loss_per_lot>0 else 0.0
    volume=min(spec.volume_max,_floor_volume(raw_volume,spec.volume_step))
    if volume<spec.volume_min: reasons.append("risk_budget_below_broker_minimum_volume")
    estimated=loss_per_lot*volume
    if estimated>budget+max(1e-8,budget*1e-8): reasons.append("rounded_volume_exceeds_risk_budget")
    return SLTPPlan(not reasons,tuple(reasons),side,entry,stop if not reasons else None,
        target if not reasons else None,atr,atr/spec.point,distance if not reasons else 0.0,
        abs(target-entry) if not reasons else 0.0,reward_risk,budget,volume if not reasons else 0.0,
        estimated if not reasons else 0.0,False)
