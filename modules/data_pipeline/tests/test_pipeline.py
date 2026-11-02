import pytest

from modules.data_pipeline import PersistentPipeline, PipelineError


def test_run_state_events_and_restart_persistence(tmp_path):
    path = tmp_path / "pipeline.sqlite3"
    pipeline = PersistentPipeline(path)
    run_id, created = pipeline.create({"symbol": "XAUUSD"}, "request-1", now=100)
    assert created
    assert PersistentPipeline(path).get(run_id)["status"] == "RUNNING"
    pipeline.stage(run_id, "VALIDATE", "bars_validated", "12 bars checked", now=101)
    pipeline.finish(run_id, {"action": "HOLD"}, now=102)
    state = PersistentPipeline(path).get(run_id)
    assert state["status"] == "COMPLETE"
    assert state["output"]["action"] == "HOLD"
    assert [e["stage"] for e in state["events"]] == ["INGEST", "VALIDATE", "COMPLETE"]


def test_idempotency_key_returns_existing_run(tmp_path):
    pipeline = PersistentPipeline(tmp_path / "pipeline.sqlite3")
    first, created = pipeline.create({"symbol": "EURUSD"}, "same-key", now=1)
    second, created_again = pipeline.create({"symbol": "GBPUSD"}, "same-key", now=2)
    assert created and not created_again
    assert first == second


def test_quarantine_invalid_data_and_only_retry_transient(tmp_path):
    pipeline = PersistentPipeline(tmp_path / "pipeline.sqlite3")
    run_id, _ = pipeline.create({"symbol": "XAUUSD"}, now=1)
    pipeline.fail(run_id, "invalid_evidence", "bad timestamp", now=2)
    assert pipeline.get(run_id)["status"] == "QUARANTINED"
    with pytest.raises(PipelineError, match="Only transient"):
        pipeline.retry(run_id, now=3)


def test_transient_retry_is_bounded(tmp_path):
    pipeline = PersistentPipeline(tmp_path / "pipeline.sqlite3")
    run_id, _ = pipeline.create({"symbol": "XAUUSD"}, now=1)
    for attempt in (2, 3):
        pipeline.fail(run_id, "upstream_timeout", "provider timed out", retryable=True, now=attempt)
        payload, count = pipeline.retry(run_id, now=attempt+1)
        assert payload["symbol"] == "XAUUSD"
        assert count == attempt
    pipeline.fail(run_id, "upstream_timeout", "provider timed out", retryable=True, now=5)
    with pytest.raises(PipelineError, match="Maximum retry"):
        pipeline.retry(run_id, now=6)


def test_rejects_memory_database(tmp_path):
    with pytest.raises(ValueError, match="persistent SQLite"):
        PersistentPipeline(":memory:")


def test_stage_regression_is_rejected(tmp_path):
    pipeline = PersistentPipeline(tmp_path / "pipeline.sqlite3")
    run_id, _ = pipeline.create({"symbol": "EURUSD"}, now=1)
    pipeline.stage(run_id, "VALIDATE", "validated", "Evidence validated", now=2)
    with pytest.raises(PipelineError, match="cannot move backwards"):
        pipeline.stage(run_id, "INGEST", "bad_transition", "Attempted regression", now=3)
