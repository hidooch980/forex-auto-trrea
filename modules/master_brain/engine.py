"""Deterministic, auditable orchestration for specialist trading signals.

This module does not connect to a broker, fetch market data, or place orders.
All scores are research inputs supplied by upstream components.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from math import isfinite
from typing import Mapping


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class AgentSignal:
    """A specialist's normalized view. score must be in [-1, 1]."""
    name: str
    score: float
    confidence: float
    rationale: str = ""
    age_seconds: float = 0.0
    available: bool = True


@dataclass(frozen=True)
class RiskProfile:
    """Balanced defaults aligned with the repository's conservative test settings."""
    max_risk_per_trade_pct: float = 0.25
    max_daily_loss_pct: float = 1.0
    max_drawdown_pct: float = 5.0
    min_confidence: float = 0.60
    min_edge: float = 0.18
    max_signal_age_seconds: float = 900.0
    max_spread_pips: float = 2.5
    # Instrument-level hard caps; XAUUSD is intentionally lower than FX.
    instrument_risk_caps_pct: Mapping[str, float] = field(default_factory=lambda: {
        "XAUUSD": 0.10,
    })


@dataclass(frozen=True)
class BrainConfig:
    architecture: str = "hybrid"
    profile: RiskProfile = field(default_factory=RiskProfile)
    # Weights sum to 1.0. They are priors, not learned performance claims.
    weights: Mapping[str, float] = field(default_factory=lambda: {
        "technical": 0.22,
        "institutional": 0.20,
        "news": 0.12,
        "macro": 0.16,
        "smart_money": 0.18,
        "strategy": 0.12,
    })
    min_active_agents: int = 2


@dataclass(frozen=True)
class MarketContext:
    symbol: str
    market_data_valid: bool = True
    calendar_valid: bool = True
    high_impact_blackout: bool = False
    emergency_stop: bool = False
    daily_loss_pct: float = 0.0
    drawdown_pct: float = 0.0
    spread_pips: float = 0.0
    requested_risk_pct: float | None = None
    # Optional historical reliability multipliers; bounded to avoid one agent
    # dominating the committee. Keep at 1.0 until walk-forward evidence exists.
    reliability: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class BrainDecision:
    symbol: str
    action: Action
    score: float
    confidence: float
    risk_pct: float
    approved: bool
    reasons: tuple[str, ...]
    agent_scores: Mapping[str, float]
    effective_weights: Mapping[str, float]

    def to_dict(self) -> dict:
        result = asdict(self)
        result["action"] = self.action.value
        return result


def _finite_range(value: float, low: float, high: float, label: str) -> None:
    if not isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be between {low} and {high}")


def _validate_config(config: BrainConfig) -> None:
    if config.architecture != "hybrid":
        raise ValueError("Only the hybrid architecture is currently implemented")
    if not config.weights or any(not isfinite(v) or v < 0 for v in config.weights.values()):
        raise ValueError("Agent weights must be finite, non-negative values")
    if sum(config.weights.values()) <= 0:
        raise ValueError("At least one agent weight must be positive")
    if config.min_active_agents < 1:
        raise ValueError("min_active_agents must be at least 1")
    p = config.profile
    for value, label in (
        (p.max_risk_per_trade_pct, "max_risk_per_trade_pct"),
        (p.max_daily_loss_pct, "max_daily_loss_pct"),
        (p.max_drawdown_pct, "max_drawdown_pct"),
        (p.max_signal_age_seconds, "max_signal_age_seconds"),
        (p.max_spread_pips, "max_spread_pips"),
    ):
        if not isfinite(value) or value <= 0:
            raise ValueError(f"{label} must be positive and finite")
    _finite_range(p.min_confidence, 0.0, 1.0, "min_confidence")
    _finite_range(p.min_edge, 0.0, 1.0, "min_edge")
    for symbol, cap in p.instrument_risk_caps_pct.items():
        if not symbol.strip() or not isfinite(cap) or cap <= 0:
            raise ValueError("instrument risk caps must have non-empty symbols and positive finite values")


def _instrument_risk_cap(profile: RiskProfile, symbol: str) -> float:
    """Resolve caps for broker suffixes (for example XAUUSD.a or XAUUSDm)."""
    normalized = symbol.strip().upper()
    caps = profile.instrument_risk_caps_pct
    matching = [
        (key.strip().upper(), cap)
        for key, cap in caps.items()
        if normalized == key.strip().upper()
        or normalized.startswith(key.strip().upper())
    ]
    if matching:
        longest = max(len(key) for key, _ in matching)
        matched_cap = min(cap for key, cap in matching if len(key) == longest)
        return min(matched_cap, 0.10) if normalized.startswith("XAU") else matched_cap
    if normalized.startswith("XAU"):
        return min(caps.get("XAUUSD", 0.10), 0.10)
    return profile.max_risk_per_trade_pct


def evaluate_market(
    context: MarketContext,
    signals: list[AgentSignal] | tuple[AgentSignal, ...],
    config: BrainConfig | None = None,
) -> BrainDecision:
    """Fuse available fresh agents, then apply independent fail-closed risk gates."""
    config = config or BrainConfig()
    _validate_config(config)
    if not context.symbol.strip():
        raise ValueError("symbol is required")
    if not isfinite(context.daily_loss_pct) or context.daily_loss_pct < 0:
        raise ValueError("daily_loss_pct must be finite and non-negative")
    if not isfinite(context.drawdown_pct) or context.drawdown_pct < 0:
        raise ValueError("drawdown_pct must be finite and non-negative")
    if not isfinite(context.spread_pips) or context.spread_pips < 0:
        raise ValueError("spread_pips must be finite and non-negative")

    profile = config.profile
    reasons: list[str] = []
    if context.emergency_stop:
        reasons.append("emergency_stop_active")
    if not context.market_data_valid:
        reasons.append("market_data_missing_or_invalid")
    if not context.calendar_valid:
        reasons.append("economic_calendar_missing_or_invalid")
    if context.high_impact_blackout:
        reasons.append("high_impact_event_blackout")
    if context.daily_loss_pct >= profile.max_daily_loss_pct:
        reasons.append("daily_loss_limit_reached")
    if context.drawdown_pct >= profile.max_drawdown_pct:
        reasons.append("drawdown_limit_reached")
    if context.spread_pips > profile.max_spread_pips:
        reasons.append("spread_above_limit")

    seen: set[str] = set()
    usable: dict[str, AgentSignal] = {}
    for signal in signals:
        name = signal.name.strip().lower()
        if name not in config.weights:
            continue
        if name in seen:
            raise ValueError(f"duplicate agent signal: {name}")
        seen.add(name)
        _finite_range(signal.score, -1.0, 1.0, f"{name}.score")
        _finite_range(signal.confidence, 0.0, 1.0, f"{name}.confidence")
        if not isfinite(signal.age_seconds) or signal.age_seconds < 0:
            raise ValueError(f"{name}.age_seconds must be finite and non-negative")
        if signal.available and signal.age_seconds <= profile.max_signal_age_seconds:
            usable[name] = signal

    if len(usable) < config.min_active_agents:
        reasons.append("insufficient_fresh_agent_evidence")

    raw_weights: dict[str, float] = {}
    for name, signal in usable.items():
        reliability = float(context.reliability.get(name, 1.0))
        if not isfinite(reliability):
            raise ValueError(f"{name}.reliability must be finite")
        reliability = min(1.5, max(0.5, reliability))
        raw_weights[name] = config.weights[name] * reliability * signal.confidence

    denominator = sum(raw_weights.values())
    if denominator <= 0:
        score = confidence = 0.0
        effective_weights: dict[str, float] = {}
    else:
        effective_weights = {name: weight / denominator for name, weight in raw_weights.items()}
        score = sum(effective_weights[name] * usable[name].score for name in usable)
        configured_active_weight = sum(config.weights[name] for name in usable)
        confidence = (
            sum(config.weights[name] * usable[name].confidence for name in usable)
            / configured_active_weight
            if configured_active_weight else 0.0
        )

    if confidence < profile.min_confidence:
        reasons.append("confidence_below_threshold")
    if abs(score) < profile.min_edge:
        reasons.append("edge_below_threshold")

    action = Action.HOLD
    if not reasons:
        action = Action.BUY if score > 0 else Action.SELL

    instrument_cap = min(
        profile.max_risk_per_trade_pct,
        _instrument_risk_cap(profile, context.symbol),
    )
    requested = instrument_cap if context.requested_risk_pct is None else context.requested_risk_pct
    if not isfinite(requested) or requested < 0:
        raise ValueError("requested_risk_pct must be finite and non-negative")
    risk_pct = min(requested, instrument_cap) if action != Action.HOLD else 0.0

    return BrainDecision(
        symbol=context.symbol.upper(),
        action=action,
        score=round(score, 6),
        confidence=round(confidence, 6),
        risk_pct=round(risk_pct, 6),
        approved=action != Action.HOLD,
        reasons=tuple(reasons) if reasons else ("committee_consensus_passed",),
        agent_scores={name: signal.score for name, signal in usable.items()},
        effective_weights={name: round(weight, 6) for name, weight in effective_weights.items()},
    )
