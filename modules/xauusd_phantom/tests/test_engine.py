import pytest

from xauusd_phantom import (
    EngineSignal, OpenRisk, PendingOrder, PhantomConfig, Side,
    evaluate_cycle, plan_oco_cancellations, plan_profit_vault,
    plan_trailing_stop,
)


def signal(engine, side=Side.BUY, risk=0.025, timestamp=100):
    if side == Side.BUY:
        return EngineSignal(engine, side, 0.8, 2000, 1990, 2020, risk, timestamp)
    return EngineSignal(engine, side, 0.8, 2000, 2010, 1980, risk, timestamp)


def test_four_independent_engines_share_one_portfolio_cap():
    signals = [signal(name) for name in ("breakout", "pullback", "momentum", "mean_reversion")]
    result = evaluate_cycle(signals, [], now=100, spread_points=10, equity_usd=1000)
    assert len(result.approved) == 4
    assert result.projected_total_risk_pct == pytest.approx(0.10)
    assert result.execution_allowed is False


def test_existing_risk_blocks_new_trade_over_shared_cap():
    result = evaluate_cycle([signal("breakout")],
                            [OpenRisk("pullback", 0.09)],
                            now=100, spread_points=10, equity_usd=1000)
    assert not result.approved
    assert result.blocked == (("breakout", "portfolio_risk_limit"),)


@pytest.mark.parametrize("kwargs,reason", [
    ({"news_blocked": True}, "news_blackout"),
    ({"market_open": False}, "market_closed"),
    ({"emergency_stop": True}, "emergency_stop"),
    ({"spread_points": 50}, "spread_gate"),
])
def test_global_gates_fail_closed(kwargs, reason):
    base = dict(now=100, spread_points=10, equity_usd=1000)
    base.update(kwargs)
    result = evaluate_cycle([signal("breakout")], [], **base)
    assert not result.approved
    assert result.blocked[0][1] == reason


def test_stale_future_and_bad_geometry_are_rejected():
    stale = signal("breakout", timestamp=1)
    bad = EngineSignal("pullback", Side.BUY, .9, 2000, 2010, 2020, .02, 100)
    result = evaluate_cycle([stale, bad], [], now=100, spread_points=5, equity_usd=1000)
    assert {reason for _, reason in result.blocked} == {
        "stale_or_future_signal", "invalid_signal_geometry"
    }


def test_oco_cancels_only_pending_siblings():
    orders = [
        PendingOrder("buy", "breakout", "gold-1"),
        PendingOrder("sell", "breakout", "gold-1"),
        PendingOrder("other", "momentum", "gold-2"),
        PendingOrder("done", "breakout", "gold-1", "FILLED"),
    ]
    assert plan_oco_cancellations("buy", orders) == ("sell",)


def test_trailing_stop_only_tightens():
    assert plan_trailing_stop(side=Side.BUY, current_stop=1990,
                              market_price=2010, atr=5) == 2002.5
    assert plan_trailing_stop(side=Side.BUY, current_stop=2005,
                              market_price=2010, atr=5) is None
    assert plan_trailing_stop(side=Side.SELL, current_stop=2010,
                              market_price=1990, atr=5) == 1997.5


def test_profit_vault_splits_only_realized_profit():
    assert plan_profit_vault(100, .25) == (25, 75)
    with pytest.raises(ValueError):
        plan_profit_vault(-10, .25)



def test_unknown_side_and_invalid_config_fail_closed():
    invalid_side = EngineSignal("breakout", "HOLD", .9, 2000, 1990, 2020, .02, 100)
    result = evaluate_cycle([invalid_side], [], now=100, spread_points=5, equity_usd=1000)
    assert not result.approved
    assert result.blocked[0][1] == "invalid_signal_geometry"

    bad_config = PhantomConfig(max_total_open_risk_pct=float("nan"))
    result = evaluate_cycle([signal("breakout")], [], now=100,
                            spread_points=5, equity_usd=1000, config=bad_config)
    assert not result.approved
    assert result.blocked[0][1] == "invalid_config"


def test_invalid_timestamp_and_cycle_time_fail_closed():
    bad_signal = signal("breakout", timestamp=100.5)
    result = evaluate_cycle([bad_signal], [], now=100, spread_points=5, equity_usd=1000)
    assert not result.approved
    assert result.blocked[0][1] == "invalid_signal_timestamp"

    result = evaluate_cycle([signal("breakout")], [], now=float("nan"),
                            spread_points=5, equity_usd=1000)
    assert not result.approved
    assert result.blocked[0][1] == "invalid_cycle_time"


def test_pending_exposure_must_be_reserved_in_shared_risk_snapshot():
    result = evaluate_cycle([signal("breakout")], [OpenRisk("pullback", .09)],
                            now=100, spread_points=5, equity_usd=1000)
    assert not result.approved
    assert result.blocked[0][1] == "portfolio_risk_limit"
