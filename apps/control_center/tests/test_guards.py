from backend.guards import daily_loss_locked
from backend.engine import choose_regime, choose_strategy, authorize_trade

def test_daily_stop():
    assert daily_loss_locked(500, 494, .01)

def test_adaptive():
    assert choose_strategy(choose_regime(28, 1.0, True)) == "trend_following"
    assert choose_strategy(choose_regime(10, 1.0, True)) == "range_reversion"
    assert choose_strategy(choose_regime(10, 2.0, True)) == "breakout_wait"

def test_live_disabled():
    ok, reason = authorize_trade("XAUUSD", "BUY", "trend", False, True, False)
    assert not ok
