"""FTMO rule-aware pre-trade compliance checks.

This module evaluates supplied account snapshots; it does not log in to FTMO,
fetch market data, or place orders. Snapshot fields must come from the connected
MT5 terminal/account and be timestamped in the broker's CE(S)T trading day.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping

PROFILES = {
    "1_step": {
        "daily_loss_pct": 3.0, "max_loss_pct": 10.0,
        "daily_basis": "day_start_balance",
        "max_loss_basis": "highest_eod_balance",
        "consistency_pct": 50.0, "profit_targets": {"challenge": 10.0},
        "minimum_trading_days": 0,
    },
    "2_step": {
        "daily_loss_pct": 5.0, "max_loss_pct": 10.0,
        "daily_basis": "day_start_balance",
        "max_loss_basis": "initial_capital",
        "consistency_pct": None,
        "profit_targets": {"challenge": 10.0, "verification": 5.0},
        "minimum_trading_days": 4,
    },
    "instant": {
        "daily_loss_pct": 3.0, "max_loss_pct": 10.0,
        "daily_basis": "day_start_balance",
        "max_loss_basis": "highest_closed_balance",
        "consistency_pct": 30.0, "profit_targets": {},
        "minimum_trading_days": 0,
    },
}


def _finite_positive(snapshot: Mapping, key: str) -> float:
    try:
        value = float(snapshot[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"missing or invalid account field: {key}") from exc
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{key} must be a finite positive number")
    return value


def evaluate_account(profile: str, phase: str, snapshot: Mapping) -> dict:
    """Evaluate equity drawdown against the selected FTMO product rules.

    Required: initial_capital, equity, day_start_balance.
    1-Step additionally requires highest_eod_balance.
    Instant additionally requires highest_closed_balance.
    2-Step uses the initial capital for the static maximum-loss floor.
    """
    if profile not in PROFILES:
        raise ValueError("profile must be 1_step, 2_step, or instant")
    if phase not in {"challenge", "verification", "funded"}:
        raise ValueError("phase must be challenge, verification, or funded")
    rules = PROFILES[profile]
    initial = _finite_positive(snapshot, "initial_capital")
    equity = _finite_positive(snapshot, "equity")
    day_start = _finite_positive(snapshot, "day_start_balance")
    daily_floor = day_start - initial * rules["daily_loss_pct"] / 100.0

    if profile == "1_step":
        high = _finite_positive(snapshot, "highest_eod_balance")
        max_floor = max(initial, high) - initial * rules["max_loss_pct"] / 100.0
    elif profile == "instant":
        high = _finite_positive(snapshot, "highest_closed_balance")
        max_floor = max(initial, high) - initial * rules["max_loss_pct"] / 100.0
    else:
        max_floor = initial * (1.0 - rules["max_loss_pct"] / 100.0)

    violations = []
    if equity <= daily_floor:
        violations.append("MAX_DAILY_LOSS")
    if equity <= max_floor:
        violations.append("MAX_LOSS")

    consistency = None
    limit = rules["consistency_pct"]
    if limit is not None:
        rule_kind = snapshot.get("consistency_rule", "consistency")
        if profile == "1_step" and rule_kind not in {"consistency", "best_day"}:
            raise ValueError("1-Step consistency_rule must be consistency or best_day")
        if profile == "instant" and rule_kind != "consistency":
            raise ValueError("Instant account uses the Consistency rule")
        best_day = float(snapshot.get("best_day_profit", 0.0))
        total_profit = float(snapshot.get("total_closed_profit", 0.0))
        denominator = total_profit
        if profile == "1_step" and rule_kind == "best_day":
            denominator = float(snapshot.get("positive_days_profit", 0.0))
        if not all(isfinite(v) for v in (best_day, total_profit, denominator)):
            raise ValueError("consistency values must be finite")
        if denominator > 0 and best_day > denominator * limit / 100.0:
            consistency = {
                "satisfied": False, "rule": rule_kind, "best_day_profit": best_day,
                "comparison_profit": denominator, "maximum_share_pct": limit,
            }
        else:
            consistency = {
                "satisfied": True, "rule": rule_kind, "best_day_profit": best_day,
                "comparison_profit": denominator, "maximum_share_pct": limit,
            }

    min_days = rules["minimum_trading_days"] if profile == "2_step" and phase in {"challenge", "verification"} else 0
    trading_days = int(snapshot.get("trading_days", 0))
    if trading_days < 0:
        raise ValueError("trading_days cannot be negative")
    target = rules["profit_targets"].get(phase)
    return {
        "profile": profile, "phase": phase,
        "can_open_new_trade": not violations,
        "breached": bool(violations), "violations": violations,
        "equity": equity, "daily_loss_floor": round(daily_floor, 2),
        "maximum_loss_floor": round(max_floor, 2),
        "daily_loss_pct": rules["daily_loss_pct"],
        "max_loss_pct": rules["max_loss_pct"],
        "consistency": consistency,
        "minimum_trading_days": min_days,
        "trading_days": trading_days,
        "minimum_days_satisfied": trading_days >= min_days,
        "profit_target_pct": target,
        "disclaimer": "Compliance estimate from supplied snapshot; verify current FTMO terms and account metrics.",
    }


def news_execution_allowed(*, phase: str, account_type: str,
                           event_is_ftmo_restricted: bool,
                           minutes_to_event: float) -> bool:
    """Apply FTMO's selected-news window only to funded Standard accounts."""
    if phase not in {"challenge", "verification", "funded"}:
        raise ValueError("invalid phase")
    if account_type not in {"standard", "swing"}:
        raise ValueError("account_type must be standard or swing")
    if not isfinite(float(minutes_to_event)):
        raise ValueError("minutes_to_event must be finite")
    if phase != "funded" or account_type == "swing" or not event_is_ftmo_restricted:
        return True
    return abs(float(minutes_to_event)) > 2.0
