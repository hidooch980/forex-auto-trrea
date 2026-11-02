from datetime import datetime, timedelta, timezone

import pytest

from modules.agent_contracts import validate_agent_output


NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def payload(**updates):
    value = {
        "agent_id": "technical_structure",
        "schema_version": "1.0",
        "scope": "EURUSD:M15",
        "as_of": NOW.isoformat(),
        "source_ids": ["mt5:EURUSD:M15:2026-11-02T11:45:00Z"],
        "data_quality": "valid",
        "confidence": 0.72,
        "stance": "bullish",
        "rationale": "Higher highs and positive momentum in validated bars.",
        "invalidations": ["Break below prior swing low"],
        "limitations": ["No order-flow feed"],
    }
    value.update(updates)
    return value


def test_valid_output_normalizes_and_passes():
    result = validate_agent_output(payload(), now=NOW)
    assert result.agent_id == "technical_structure"
    assert result.source_ids[0].startswith("mt5:")
    assert result.to_dict()["as_of"].endswith("+00:00")


def test_missing_sources_rejected():
    with pytest.raises(ValueError, match="source_id"):
        validate_agent_output(payload(source_ids=[]), now=NOW)


def test_stale_output_rejected():
    old = (NOW - timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError, match="stale"):
        validate_agent_output(payload(as_of=old), now=NOW)


def test_future_output_rejected():
    future = (NOW + timedelta(minutes=2)).isoformat()
    with pytest.raises(ValueError, match="future"):
        validate_agent_output(payload(as_of=future), now=NOW)


def test_invalid_data_quality_rejected():
    with pytest.raises(ValueError, match="data quality"):
        validate_agent_output(payload(data_quality="degraded"), now=NOW)


def test_confidence_bounds_enforced():
    with pytest.raises(ValueError, match="confidence"):
        validate_agent_output(payload(confidence=1.1), now=NOW)


def test_unavailable_must_have_zero_confidence():
    with pytest.raises(ValueError, match="zero confidence"):
        validate_agent_output(payload(stance="unavailable"), now=NOW)


def test_duplicate_sources_rejected():
    with pytest.raises(ValueError, match="unique"):
        validate_agent_output(payload(source_ids=["x", "x"]), now=NOW)
