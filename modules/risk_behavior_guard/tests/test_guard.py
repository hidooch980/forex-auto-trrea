from dataclasses import replace

import pytest

from modules.risk_behavior_guard import AccountRisk, BehaviorMetrics, TradeProposal, evaluate_trade


ACCOUNT = AccountRisk(0.2, 0.5, 1.0, 2, 0)
PROPOSAL = TradeProposal(0.2, 2.0, True, True, True, True)
BEHAVIOR = BehaviorMetrics(1, 120, 1.0, 1.0, 30)


def test_normal_trade_passes():
    assert evaluate_trade(ACCOUNT, PROPOSAL, BEHAVIOR).approved


def test_daily_loss_limit_blocks():
    result = evaluate_trade(replace(ACCOUNT, daily_loss_pct=1.0), PROPOSAL, BEHAVIOR)
    assert not result.approved
    assert "daily_loss_limit_reached" in result.reasons


def test_missing_stop_or_calendar_blocks():
    result = evaluate_trade(ACCOUNT, replace(PROPOSAL, has_stop_loss=False, calendar_clear=False), BEHAVIOR)
    assert not result.approved
    assert "stop_loss_required" in result.reasons
    assert "calendar_block_or_unavailable" in result.reasons


def test_revenge_pattern_blocks_and_sets_zero_risk_cap():
    behavior = replace(BEHAVIOR, minutes_since_last_loss=5, risk_vs_recent_average=1.5)
    result = evaluate_trade(ACCOUNT, PROPOSAL, behavior)
    assert not result.approved
    assert "possible_revenge_trading" in result.behavior_flags
    assert result.risk_cap_pct == 0


def test_fomo_late_entry_blocks():
    result = evaluate_trade(ACCOUNT, PROPOSAL, replace(BEHAVIOR, signal_age_seconds=180))
    assert not result.approved
    assert "possible_fomo_or_late_entry" in result.behavior_flags


def test_overtrading_and_consecutive_losses_block():
    result = evaluate_trade(replace(ACCOUNT, consecutive_losses=3), PROPOSAL, replace(BEHAVIOR, trades_last_hour=4))
    assert not result.approved
    assert "consecutive_loss_lock" in result.reasons
    assert "hourly_overtrading_lock" in result.reasons


def test_unknown_loss_timing_fails_closed():
    result = evaluate_trade(ACCOUNT, PROPOSAL, replace(BEHAVIOR, minutes_since_last_loss=None))
    assert not result.approved
    assert "last_loss_timing_unknown" in result.reasons


def test_non_finite_metrics_rejected():
    with pytest.raises(ValueError, match="finite"):
        evaluate_trade(ACCOUNT, replace(PROPOSAL, risk_pct=float("nan")), BEHAVIOR)
