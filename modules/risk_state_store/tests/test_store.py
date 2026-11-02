import pytest

from modules.risk_state_store import (
    PersistentRiskLedger, RiskLimitError, RiskStateError, RiskLimits,
)


def test_reservations_survive_restart_and_release_only_on_terminal_state(tmp_path):
    db = tmp_path / "risk.sqlite3"
    ledger = PersistentRiskLedger(db)
    ledger.reserve("order-1", "breakout", .025, now=100)
    restarted = PersistentRiskLedger(db)
    snap = restarted.snapshot(now=101)
    assert snap.active_risk_pct == pytest.approx(.025)
    assert snap.active_by_engine == {"breakout": 1}
    restarted.transition("order-1", "OPEN", now=102)
    restarted.transition("order-1", "CLOSED", now=103)
    assert PersistentRiskLedger(db).snapshot(now=104).active_risk_pct == 0


def test_total_and_per_engine_limits_are_atomic(tmp_path):
    ledger = PersistentRiskLedger(tmp_path / "risk.db",
        RiskLimits(max_total_risk_pct=.04, max_engine_risk_pct=.025,
                   max_active_per_engine=1))
    ledger.reserve("a", "breakout", .025, now=1)
    with pytest.raises(RiskLimitError, match="engine_position_limit"):
        ledger.reserve("b", "breakout", .01, now=2)
    with pytest.raises(RiskLimitError, match="total_risk_limit"):
        ledger.reserve("c", "pullback", .02, now=2)


def test_duplicate_ids_and_invalid_transitions_fail(tmp_path):
    ledger = PersistentRiskLedger(tmp_path / "risk.db")
    ledger.reserve("a", "breakout", .02, now=1)
    with pytest.raises(RiskStateError, match="duplicate_reservation_id"):
        ledger.reserve("a", "pullback", .01, now=2)
    with pytest.raises(RiskStateError, match="invalid_transition"):
        ledger.transition("a", "OPEN", now=2)
    ledger.transition("a", "CANCELLED", now=3)
    with pytest.raises(RiskStateError, match="invalid_transition"):
        ledger.transition("a", "OPEN", now=4)


def test_daily_loss_and_peak_drawdown_locks_persist(tmp_path):
    ledger = PersistentRiskLedger(tmp_path / "risk.db",
        RiskLimits(max_total_risk_pct=.1, max_engine_risk_pct=.05,
                   max_daily_loss_pct=1, max_peak_drawdown_pct=5))
    ledger.record_equity(1000, now=1_800_000_000)
    snap = ledger.record_equity(985, now=1_800_000_060)
    assert snap.daily_lock
    with pytest.raises(RiskLimitError, match="persistent_risk_lock"):
        ledger.reserve("blocked", "breakout", .01, now=1_800_000_061)
    ledger.unlock("daily", "operator reviewed broker statement", now=1_800_000_062)
    assert not ledger.snapshot(now=1_800_000_063).daily_lock

    ledger.record_equity(1000, now=1_800_000_100)
    snap = ledger.record_equity(940, now=1_800_000_160)
    assert snap.drawdown_lock
    with pytest.raises(RiskLimitError, match="persistent_risk_lock"):
        ledger.reserve("blocked-2", "breakout", .01, now=1_800_000_161)


def test_invalid_equity_and_timestamp_regression_fail_closed(tmp_path):
    ledger = PersistentRiskLedger(tmp_path / "risk.db")
    with pytest.raises(ValueError):
        ledger.record_equity(float("nan"), now=10)
    ledger.record_equity(1000, now=100)
    with pytest.raises(RiskStateError, match="timestamp_regression"):
        ledger.record_equity(999, now=99)


def test_oco_reservation_is_a_single_max_loss_budget(tmp_path):
    ledger = PersistentRiskLedger(tmp_path / "risk.db",
        RiskLimits(max_total_risk_pct=.1, max_engine_risk_pct=.1))
    # The execution adapter reserves the worst-case loss once for the OCO group.
    ledger.reserve("oco-group-1", "breakout", .08, status="PENDING", now=1)
    assert ledger.snapshot(now=2).active_risk_pct == pytest.approx(.08)


def test_daily_lock_resets_on_next_utc_day_but_drawdown_lock_does_not(tmp_path):
    from datetime import datetime, timezone, timedelta
    ledger = PersistentRiskLedger(tmp_path / "risk.db",
        RiskLimits(max_total_risk_pct=.1, max_engine_risk_pct=.05,
                   max_daily_loss_pct=1, max_peak_drawdown_pct=20))
    day_one = int(datetime(2026, 11, 1, 23, 59, tzinfo=timezone.utc).timestamp())
    day_two = int((datetime(2026, 11, 1, 23, 59, tzinfo=timezone.utc)
                   + timedelta(minutes=2)).timestamp())
    ledger.record_equity(1000, now=day_one)
    assert ledger.record_equity(985, now=day_one+30).daily_lock
    next_day = ledger.record_equity(985, now=day_two)
    assert not next_day.daily_lock
    assert next_day.daily_loss_pct == 0


def test_in_memory_database_is_rejected_as_not_persistent():
    with pytest.raises(ValueError, match="persistent SQLite file"):
        PersistentRiskLedger(":memory:")
