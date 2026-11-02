"""Fail-closed risk and behavioral guard; no broker execution is performed.

Behavior flags are objective trading-pattern proxies, not diagnoses of emotion.
All percentages are expressed in percentage points (0.25 means 0.25%).
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class RiskLimits:
    max_trade_risk_pct: float = 0.25
    max_daily_loss_pct: float = 1.0
    max_weekly_loss_pct: float = 2.0
    max_peak_drawdown_pct: float = 5.0
    max_trades_per_day: int = 8
    max_consecutive_losses: int = 3
    max_trades_per_hour: int = 4
    min_reward_risk: float = 1.5
    cooldown_after_loss_minutes: int = 15
    revenge_risk_multiplier: float = 1.25
    fomo_risk_multiplier: float = 1.25


@dataclass(frozen=True)
class AccountRisk:
    daily_loss_pct: float
    weekly_loss_pct: float
    peak_drawdown_pct: float
    trades_today: int
    consecutive_losses: int
    emergency_stop: bool = False


@dataclass(frozen=True)
class TradeProposal:
    risk_pct: float
    reward_risk: float
    has_stop_loss: bool
    market_data_valid: bool
    calendar_clear: bool
    spread_acceptable: bool


@dataclass(frozen=True)
class BehaviorMetrics:
    trades_last_hour: int
    minutes_since_last_loss: float | None
    risk_vs_recent_average: float
    volume_multiplier_after_loss: float
    signal_age_seconds: float
    normal_signal_age_seconds: float = 60.0


@dataclass(frozen=True)
class GuardDecision:
    approved: bool
    reasons: tuple[str, ...]
    risk_cap_pct: float
    cooldown_required_minutes: int
    behavior_flags: tuple[str, ...]


def _finite(name: str, value: float) -> None:
    if not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise ValueError(f"{name} must be finite numeric")


def evaluate_trade(
    account: AccountRisk,
    proposal: TradeProposal,
    behavior: BehaviorMetrics,
    limits: RiskLimits = RiskLimits(),
) -> GuardDecision:
    """Return a deterministic verdict. Missing/invalid evidence rejects the trade."""
    numeric = {
        "daily_loss_pct": account.daily_loss_pct,
        "weekly_loss_pct": account.weekly_loss_pct,
        "peak_drawdown_pct": account.peak_drawdown_pct,
        "risk_pct": proposal.risk_pct,
        "reward_risk": proposal.reward_risk,
        "risk_vs_recent_average": behavior.risk_vs_recent_average,
        "volume_multiplier_after_loss": behavior.volume_multiplier_after_loss,
        "signal_age_seconds": behavior.signal_age_seconds,
        "normal_signal_age_seconds": behavior.normal_signal_age_seconds,
    }
    if behavior.minutes_since_last_loss is not None:
        numeric["minutes_since_last_loss"] = behavior.minutes_since_last_loss
    for name, value in numeric.items():
        _finite(name, value)
    if min(account.daily_loss_pct, account.weekly_loss_pct, account.peak_drawdown_pct,
           proposal.risk_pct, behavior.risk_vs_recent_average,
           behavior.volume_multiplier_after_loss, behavior.signal_age_seconds) < 0:
        raise ValueError("loss, risk and behavior metrics cannot be negative")
    if account.trades_today < 0 or account.consecutive_losses < 0 or behavior.trades_last_hour < 0:
        raise ValueError("trade counters cannot be negative")
    if proposal.reward_risk < 0 or behavior.normal_signal_age_seconds <= 0:
        raise ValueError("reward_risk must be non-negative and normal signal age positive")

    reasons: list[str] = []
    flags: list[str] = []
    cooldown = 0
    if account.emergency_stop:
        reasons.append("emergency_stop_active")
    if account.daily_loss_pct >= limits.max_daily_loss_pct:
        reasons.append("daily_loss_limit_reached")
    if account.weekly_loss_pct >= limits.max_weekly_loss_pct:
        reasons.append("weekly_loss_limit_reached")
    if account.peak_drawdown_pct >= limits.max_peak_drawdown_pct:
        reasons.append("peak_drawdown_limit_reached")
    if account.trades_today >= limits.max_trades_per_day:
        reasons.append("daily_trade_count_limit_reached")
    if account.consecutive_losses >= limits.max_consecutive_losses:
        reasons.append("consecutive_loss_lock")
    if behavior.trades_last_hour >= limits.max_trades_per_hour:
        reasons.append("hourly_overtrading_lock")
    if not proposal.has_stop_loss:
        reasons.append("stop_loss_required")
    if not proposal.market_data_valid:
        reasons.append("market_data_invalid_or_missing")
    if not proposal.calendar_clear:
        reasons.append("calendar_block_or_unavailable")
    if not proposal.spread_acceptable:
        reasons.append("spread_limit_exceeded")
    if proposal.reward_risk < limits.min_reward_risk:
        reasons.append("reward_risk_below_minimum")

    if behavior.minutes_since_last_loss is None:
        reasons.append("last_loss_timing_unknown")
    elif behavior.minutes_since_last_loss < limits.cooldown_after_loss_minutes:
        flags.append("post_loss_cooldown")
        cooldown = max(cooldown, limits.cooldown_after_loss_minutes - int(behavior.minutes_since_last_loss))
        reasons.append("cooldown_after_loss")

    if behavior.minutes_since_last_loss is not None and behavior.minutes_since_last_loss < 60:
        if behavior.risk_vs_recent_average >= limits.revenge_risk_multiplier or behavior.volume_multiplier_after_loss >= limits.revenge_risk_multiplier:
            flags.append("possible_revenge_trading")
            reasons.append("risk_or_volume_increased_after_loss")
    if behavior.signal_age_seconds > behavior.normal_signal_age_seconds * 2:
        flags.append("possible_fomo_or_late_entry")
        reasons.append("signal_too_old_for_entry")

    risk_cap = limits.max_trade_risk_pct
    if flags:
        risk_cap = 0.0
    elif proposal.risk_pct > risk_cap:
        reasons.append("per_trade_risk_limit_exceeded")
    if proposal.risk_pct <= 0:
        reasons.append("proposed_risk_must_be_positive")

    return GuardDecision(
        approved=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
        risk_cap_pct=risk_cap,
        cooldown_required_minutes=cooldown,
        behavior_flags=tuple(dict.fromkeys(flags)),
    )
