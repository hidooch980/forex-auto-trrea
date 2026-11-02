import pytest

from modules.portfolio_risk_guard import (
    PortfolioSnapshot, Position, TradeIntent, evaluate_portfolio,
)


def intent(**changes):
    values = dict(market="crypto_futures", instrument="BTCUSDT", side="long",
                  notional_usd=1000, stop_risk_usd=50, margin_usd=250,
                  liquidity_usd_1pct=50000, spread_bps=5)
    values.update(changes)
    return TradeIntent(**values)


def test_small_order_within_all_portfolio_limits():
    result = evaluate_portfolio(PortfolioSnapshot(10000, ()), intent())
    assert result.approved
    assert result.total_open_risk_pct == 0.5


def test_long_and_short_risks_are_added_not_netted():
    book = (
        Position("crypto_futures", "BTCUSDT", "long", 1000, 60, 250, 50000, 5),
        Position("crypto_futures", "BTCUSDT", "short", 1000, 60, 250, 50000, 5),
    )
    result = evaluate_portfolio(PortfolioSnapshot(10000, book), intent())
    assert not result.approved
    assert result.total_open_risk_pct == pytest.approx(1.7)
    assert "instrument_concentration_limit" in result.reasons


def test_cross_market_aggregate_risk_blocks():
    book = (Position("forex", "EURUSD", "short", 1000, 100, 100, 50000, 2),)
    result = evaluate_portfolio(PortfolioSnapshot(10000, book), intent(stop_risk_usd=120))
    assert not result.approved
    assert "total_portfolio_open_risk_limit" in result.reasons


def test_large_order_vs_liquidity_blocks():
    result = evaluate_portfolio(
        PortfolioSnapshot(100000, ()),
        intent(notional_usd=10000, stop_risk_usd=100, margin_usd=1000,
               liquidity_usd_1pct=100000, spread_bps=5),
    )
    assert not result.approved
    assert "order_too_large_for_visible_liquidity" in result.reasons


def test_missing_stop_and_emergency_stop_fail_closed():
    result = evaluate_portfolio(
        PortfolioSnapshot(10000, (), emergency_stop=True),
        intent(stop_loss_present=False),
    )
    assert not result.approved
    assert "portfolio_emergency_stop" in result.reasons
    assert "stop_loss_required" in result.reasons


def test_bad_position_data_rejected():
    with pytest.raises(ValueError, match="finite"):
        evaluate_portfolio(PortfolioSnapshot(10000, ()), intent(notional_usd=float("nan")))


def test_invalid_existing_position_data_blocks():
    book = (Position("forex", "GBPUSD", "long", 100, 10, 20, 10000, 2, False),)
    result = evaluate_portfolio(PortfolioSnapshot(10000, book), intent())
    assert not result.approved
    assert "position_0_data_invalid" in result.reasons
