import pytest
from modules.cognitive_cells import CellularLearning, analyze_market_affect


def test_cells_are_isolated_and_weights_wait_for_minimum_samples(tmp_path):
    memory = CellularLearning(tmp_path / "cells.sqlite3", min_samples=3)
    assert memory.cell("technical")["shadow_reliability_multiplier"] == 1.0
    for i in range(3):
        memory.observe("technical", "win", closed_at=100+i)
    technical = memory.cell("technical")
    assert technical["eligible_for_shadow_weighting"] is True
    assert technical["shadow_reliability_multiplier"] == 1.25
    assert memory.cell("news")["directional_samples"] == 0
    assert technical["live_weight_change_authorized"] is False


def test_market_affect_uses_observable_proxies_not_human_diagnosis():
    result = analyze_market_affect(
        volatility_pct=4, spread_ratio=3, drawdown_pct=6,
        consecutive_losses=4, agent_disagreement=0.9, data_quality_score=0.5,
    )
    assert result.state == "extreme"
    assert result.human_emotion_inference is False
    assert "volatility" in result.flags


def test_invalid_affect_inputs_fail_closed():
    with pytest.raises(ValueError):
        analyze_market_affect(volatility_pct=-1, spread_ratio=1, drawdown_pct=0,
                              consecutive_losses=0, agent_disagreement=0.2, data_quality_score=1)
