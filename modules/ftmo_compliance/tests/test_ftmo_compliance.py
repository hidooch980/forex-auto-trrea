import pytest

from ftmo_compliance import evaluate_account, news_execution_allowed


def base(**extra):
    result = {"initial_capital": 100000, "equity": 100000,
              "day_start_balance": 100000, "highest_eod_balance": 100000,
              "highest_closed_balance": 100000, "trading_days": 4,
              "best_day_profit": 100, "total_closed_profit": 1000}
    result.update(extra)
    return result


def test_two_step_uses_five_percent_daily_and_static_ten_percent_max_loss():
    result = evaluate_account("2_step", "challenge", base(equity=94999))
    assert result["breached"]
    assert result["violations"] == ["MAX_DAILY_LOSS"]
    assert result["daily_loss_floor"] == 95000
    assert result["maximum_loss_floor"] == 90000
    assert result["minimum_days_satisfied"]


def test_one_step_uses_three_percent_daily_and_eod_trailing_max_loss():
    result = evaluate_account("1_step", "challenge",
        base(equity=97000, highest_eod_balance=110000))
    assert result["violations"] == ["MAX_DAILY_LOSS"]
    assert result["maximum_loss_floor"] == 100000


def test_instant_uses_three_percent_daily_and_closed_balance_trailing_floor():
    result = evaluate_account("instant", "funded",
        base(equity=99000, highest_closed_balance=110000))
    assert result["violations"] == ["MAX_LOSS"]
    assert result["maximum_loss_floor"] == 100000
    assert result["consistency"]["maximum_share_pct"] == 30


def test_one_step_consistency_is_fifty_percent_and_not_a_breach():
    result = evaluate_account("1_step", "funded",
        base(best_day_profit=600, total_closed_profit=1000))
    assert result["consistency"]["satisfied"] is False
    assert result["can_open_new_trade"] is True


def test_legacy_one_step_best_day_rule_uses_positive_days_profit():
    result = evaluate_account("1_step", "funded",
        base(best_day_profit=600, total_closed_profit=1000,
             positive_days_profit=1200, consistency_rule="best_day"))
    assert result["consistency"]["rule"] == "best_day"
    assert result["consistency"]["satisfied"] is False


def test_two_step_has_four_minimum_days_only_in_evaluation():
    assert not evaluate_account("2_step", "verification", base(trading_days=3))["minimum_days_satisfied"]
    assert evaluate_account("2_step", "funded", base(trading_days=0))["minimum_days_satisfied"]


@pytest.mark.parametrize("phase,kind,event,minutes,expected", [
    ("challenge", "standard", True, 0, True),
    ("verification", "standard", True, 1, True),
    ("funded", "swing", True, 0, True),
    ("funded", "standard", False, 0, True),
    ("funded", "standard", True, 3, True),
    ("funded", "standard", True, 2, False),
    ("funded", "standard", True, -1, False),
])
def test_news_window(phase, kind, event, minutes, expected):
    assert news_execution_allowed(phase=phase, account_type=kind,
        event_is_ftmo_restricted=event, minutes_to_event=minutes) is expected


def test_unknown_profile_and_invalid_snapshot_fail_closed():
    with pytest.raises(ValueError):
        evaluate_account("unknown", "challenge", base())
    with pytest.raises(ValueError):
        evaluate_account("2_step", "challenge", {"initial_capital": 100000})
