"""Deterministic, broker-agnostic ANAKO-inspired XAUUSD planning layer.

This module never sends orders. It validates four independent engine proposals,
applies one shared portfolio risk gate, and emits execution-neutral plans.
All risk percentages are percentages of current equity, not fractions.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Iterable, Sequence

ENGINE_NAMES = ("breakout", "pullback", "momentum", "mean_reversion")


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class EngineSignal:
    engine: str
    side: Side
    confidence: float
    entry: float
    stop_loss: float
    take_profit: float
    risk_pct: float
    timestamp: int
    order_type: str = "MARKET"  # MARKET, BUY_STOP, SELL_STOP


@dataclass(frozen=True)
class OpenRisk:
    engine: str
    risk_pct: float


@dataclass(frozen=True)
class PendingOrder:
    order_id: str
    engine: str
    oco_group: str
    status: str = "PENDING"


@dataclass(frozen=True)
class PhantomConfig:
    min_confidence: float = 0.60
    min_reward_risk: float = 1.50
    max_engine_risk_pct: float = 0.025
    max_total_open_risk_pct: float = 0.10
    max_open_positions_per_engine: int = 1
    max_spread_points: float = 35.0
    max_signal_age_seconds: int = 60
    trailing_atr_multiple: float = 1.5
    profit_vault_share: float = 0.25


@dataclass(frozen=True)
class PhantomDecision:
    approved: tuple[EngineSignal, ...]
    blocked: tuple[tuple[str, str], ...]
    projected_total_risk_pct: float
    execution_allowed: bool = False


def _valid_number(value: float) -> bool:
    return isfinite(value)


def _rr(signal: EngineSignal) -> float:
    risk = abs(signal.entry - signal.stop_loss)
    reward = abs(signal.take_profit - signal.entry)
    return reward / risk if risk > 0 else 0.0


def _geometry_valid(signal: EngineSignal) -> bool:
    values = (signal.confidence, signal.entry, signal.stop_loss,
              signal.take_profit, signal.risk_pct)
    if not all(_valid_number(float(v)) for v in values):
        return False
    if signal.entry <= 0 or signal.stop_loss <= 0 or signal.take_profit <= 0:
        return False
    if signal.risk_pct <= 0:
        return False
    if signal.side == Side.BUY:
        return signal.stop_loss < signal.entry < signal.take_profit
    if signal.side == Side.SELL:
        return signal.take_profit < signal.entry < signal.stop_loss
    return False


def _config_valid(config: PhantomConfig) -> bool:
    numeric_limits = (
        config.min_confidence, config.min_reward_risk,
        config.max_engine_risk_pct, config.max_total_open_risk_pct,
        config.max_spread_points, config.trailing_atr_multiple,
        config.profit_vault_share,
    )
    try:
        if not all(_valid_number(float(value)) for value in numeric_limits):
            return False
    except (TypeError, ValueError, OverflowError):
        return False
    return (
        0 <= config.min_confidence <= 1
        and config.min_reward_risk > 0
        and config.max_engine_risk_pct > 0
        and config.max_total_open_risk_pct > 0
        and isinstance(config.max_open_positions_per_engine, int)
        and not isinstance(config.max_open_positions_per_engine, bool)
        and config.max_open_positions_per_engine >= 1
        and config.max_spread_points > 0
        and isinstance(config.max_signal_age_seconds, int)
        and not isinstance(config.max_signal_age_seconds, bool)
        and config.max_signal_age_seconds >= 0
        and config.trailing_atr_multiple > 0
        and 0 <= config.profit_vault_share <= 1
    )


def evaluate_cycle(
    signals: Sequence[EngineSignal],
    open_risks: Sequence[OpenRisk],
    *,
    now: int,
    spread_points: float,
    equity_usd: float,
    market_open: bool = True,
    news_blocked: bool = False,
    emergency_stop: bool = False,
    config: PhantomConfig = PhantomConfig(),
) -> PhantomDecision:
    """Approve proposals under one shared fail-closed XAU risk budget.

    open_risks must include exposure from both filled positions and pending
    orders. OCO siblings should be represented once at their maximum possible
    loss, not summed as if both could fill simultaneously.
    """
    blocked: list[tuple[str, str]] = []
    approved: list[EngineSignal] = []
    if not _config_valid(config):
        return PhantomDecision((), tuple((s.engine, "invalid_config") for s in signals),
                               float("inf"))
    if not isinstance(now, int) or isinstance(now, bool):
        return PhantomDecision((), tuple((s.engine, "invalid_cycle_time") for s in signals),
                               float("inf"))
    if emergency_stop:
        return PhantomDecision((), tuple((s.engine, "emergency_stop") for s in signals),
                               sum(p.risk_pct for p in open_risks))
    if not market_open:
        return PhantomDecision((), tuple((s.engine, "market_closed") for s in signals),
                               sum(p.risk_pct for p in open_risks))
    if news_blocked:
        return PhantomDecision((), tuple((s.engine, "news_blackout") for s in signals),
                               sum(p.risk_pct for p in open_risks))
    if not _valid_number(spread_points) or spread_points < 0 or spread_points > config.max_spread_points:
        return PhantomDecision((), tuple((s.engine, "spread_gate") for s in signals),
                               sum(p.risk_pct for p in open_risks))
    if not _valid_number(equity_usd) or equity_usd <= 0:
        return PhantomDecision((), tuple((s.engine, "invalid_equity") for s in signals),
                               sum(p.risk_pct for p in open_risks))

    current_risk = 0.0
    engine_counts = {name: 0 for name in ENGINE_NAMES}
    for position in open_risks:
        if position.engine not in engine_counts or not _valid_number(position.risk_pct) or position.risk_pct < 0:
            return PhantomDecision((), tuple((s.engine, "invalid_open_risk_snapshot") for s in signals),
                                   float("inf"))
        current_risk += position.risk_pct
        engine_counts[position.engine] += 1

    seen: set[str] = set()
    for signal in signals:
        reason = ""
        if signal.engine not in ENGINE_NAMES:
            reason = "unknown_engine"
        elif signal.engine in seen:
            reason = "duplicate_engine_signal"
        else:
            seen.add(signal.engine)
            if not isinstance(signal.timestamp, int) or isinstance(signal.timestamp, bool):
                reason = "invalid_signal_timestamp"
            elif not _geometry_valid(signal):
                reason = "invalid_signal_geometry"
            elif signal.confidence < config.min_confidence or signal.confidence > 1:
                reason = "confidence_gate"
            elif signal.timestamp > now or now - signal.timestamp > config.max_signal_age_seconds:
                reason = "stale_or_future_signal"
            elif signal.order_type not in ("MARKET", "BUY_STOP", "SELL_STOP"):
                reason = "unsupported_order_type"
            elif signal.order_type == "BUY_STOP" and signal.side != Side.BUY:
                reason = "pending_order_side_mismatch"
            elif signal.order_type == "SELL_STOP" and signal.side != Side.SELL:
                reason = "pending_order_side_mismatch"
            elif _rr(signal) < config.min_reward_risk:
                reason = "reward_risk_below_minimum"
            elif signal.risk_pct > config.max_engine_risk_pct:
                reason = "engine_risk_limit"
            elif engine_counts[signal.engine] >= config.max_open_positions_per_engine:
                reason = "engine_position_limit"
            elif current_risk + signal.risk_pct > config.max_total_open_risk_pct + 1e-12:
                reason = "portfolio_risk_limit"
        if reason:
            blocked.append((signal.engine, reason))
        else:
            approved.append(signal)
            current_risk += signal.risk_pct
            engine_counts[signal.engine] += 1

    return PhantomDecision(tuple(approved), tuple(blocked), current_risk)


def plan_oco_cancellations(filled_order_id: str, pending: Iterable[PendingOrder]) -> tuple[str, ...]:
    """Return sibling pending IDs to cancel after one order in an OCO group fills."""
    filled = next((p for p in pending if p.order_id == filled_order_id), None)
    if filled is None or not filled.oco_group:
        return ()
    return tuple(p.order_id for p in pending
                 if p.oco_group == filled.oco_group
                 and p.order_id != filled_order_id
                 and p.status == "PENDING")


def plan_trailing_stop(
    *, side: Side, current_stop: float, market_price: float,
    atr: float, atr_multiple: float = 1.5,
) -> float | None:
    """Return a tighter ATR trailing stop; never loosen an existing stop."""
    if not all(_valid_number(v) for v in (current_stop, market_price, atr, atr_multiple)):
        return None
    if min(current_stop, market_price, atr, atr_multiple) <= 0:
        return None
    candidate = market_price - atr * atr_multiple if side == Side.BUY else market_price + atr * atr_multiple
    if side == Side.BUY and candidate > current_stop and candidate < market_price:
        return candidate
    if side == Side.SELL and candidate < current_stop and candidate > market_price:
        return candidate
    return None


def plan_profit_vault(realized_profit_usd: float, share: float = 0.25) -> tuple[float, float]:
    """Split positive realized profit into protected reserve and reusable profit."""
    if not _valid_number(realized_profit_usd) or not _valid_number(share):
        raise ValueError("profit and share must be finite numbers")
    if realized_profit_usd < 0 or not 0 <= share <= 1:
        raise ValueError("profit must be non-negative and share must be between 0 and 1")
    vault = realized_profit_usd * share
    return round(vault, 2), round(realized_profit_usd - vault, 2)
