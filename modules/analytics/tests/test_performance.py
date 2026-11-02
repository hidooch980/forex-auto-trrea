import pytest

from performance import (
    build_market_heatmap,
    calculate_fear_greed,
    summarize_closed_trades,
)


def test_signal_performance_uses_only_closed_net_results_and_ranks_by_average():
    result = summarize_closed_trades([
        {"trade_id": "1", "symbol": "EURUSD", "status": "closed", "net_profit": 20},
        {"trade_id": "2", "symbol": "EURUSD", "status": "closed", "net_profit": -10},
        {"trade_id": "3", "symbol": "XAUUSD", "status": "completed", "net_profit": 15},
        {"trade_id": "4", "symbol": "GBPUSD", "status": "open", "net_profit": 999},
    ])
    assert result["total_closed"] == 3
    assert result["wins"] == 2
    assert result["losses"] == 1
    assert result["win_rate_pct"] == pytest.approx(66.67)
    assert result["net_profit"] == 25
    assert result["symbols"][0]["symbol"] == "XAUUSD"
    assert result["symbols"][1]["symbol"] == "EURUSD"
    assert result["heatmap"][1]["performance"] == "positive"


def test_empty_performance_is_unavailable_not_zero_profit():
    result = summarize_closed_trades([])
    assert result["available"] is False
    assert result["average_profit"] is None
    assert result["profit_factor"] is None


def test_duplicate_closed_trade_ids_are_rejected():
    rows = [
        {"trade_id": "same", "symbol": "EURUSD", "status": "closed", "net_profit": 1},
        {"trade_id": "same", "symbol": "EURUSD", "status": "closed", "net_profit": 2},
    ]
    with pytest.raises(ValueError, match="duplicate"):
        summarize_closed_trades(rows)


def test_fear_greed_requires_all_real_components_and_bounded_values():
    components = {
        "momentum": 80, "market_breadth": 60,
        "volatility": 40, "safe_haven_demand": 20,
    }
    result = calculate_fear_greed(components)
    assert result["score"] == 50
    assert result["label"] == "neutral"
    with pytest.raises(ValueError):
        calculate_fear_greed({"momentum": 90})
    components["volatility"] = 101
    with pytest.raises(ValueError):
        calculate_fear_greed(components)


def test_live_market_heatmap_sorts_provider_snapshots():
    result = build_market_heatmap([
        {"symbol": "EURUSD", "change_pct": -0.4},
        {"symbol": "XAUUSD", "change_pct": 0.8},
        {"symbol": "GBPUSD", "change_pct": 0},
    ])
    assert [x["symbol"] for x in result] == ["XAUUSD", "GBPUSD", "EURUSD"]
