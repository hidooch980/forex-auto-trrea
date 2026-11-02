import pytest
from modules.performance_memory import PerformanceMemory


def test_closed_trade_memory_and_chronological_walk_forward(tmp_path):
    memory = PerformanceMemory(tmp_path / "performance.sqlite3")
    for i in range(40):
        memory.record_closed_trade(
            f"trade-{i}", "XAUUSD", 1000 + i * 10,
            0.5 if i % 2 == 0 else -0.3,
            [{"agent_id": "technical", "stance": "bullish" if i % 2 == 0 else "bearish",
              "confidence": 0.8, "as_of": 990 + i * 10}],
            recorded_at=2000 + i,
        )
    report = memory.report(min_train=20, min_test=10)
    agent = report["agents"]["technical"]
    assert agent["train"]["samples"] == 28
    assert agent["out_of_sample"]["samples"] == 12
    assert agent["walk_forward_eligible"] is True
    assert report["live_weights_modified"] is False


def test_future_forecast_and_duplicate_trade_are_rejected(tmp_path):
    memory = PerformanceMemory(tmp_path / "performance.sqlite3")
    with pytest.raises(ValueError, match="precede trade close"):
        memory.record_closed_trade(
            "t1", "EURUSD", 100, 0.2,
            [{"agent_id": "news", "stance": "bullish", "confidence": 0.7, "as_of": 101}],
            recorded_at=200,
        )
    forecast = [{"agent_id": "news", "stance": "bullish", "confidence": 0.7, "as_of": 90}]
    memory.record_closed_trade("t1", "EURUSD", 100, 0.2, forecast, recorded_at=200)
    with pytest.raises(Exception):
        memory.record_closed_trade("t1", "EURUSD", 100, 0.2, forecast, recorded_at=200)


def test_insufficient_samples_never_qualify_for_walk_forward(tmp_path):
    memory = PerformanceMemory(tmp_path / "performance.sqlite3")
    for i in range(5):
        memory.record_closed_trade(
            f"t{i}", "GBPUSD", 100+i, 1,
            [{"agent_id": "macro", "stance": "bullish", "confidence": 0.5, "as_of": 90+i}],
            recorded_at=200,
        )
    report = memory.report()
    assert report["agents"]["macro"]["walk_forward_eligible"] is False
