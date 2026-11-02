from pathlib import Path
from types import SimpleNamespace

import pytest

from modules.erp_api.router import build_erp_router
from modules.risk_state_store import PersistentRiskLedger, RiskLimits


def _router(tmp_path, monkeypatch=None):
    import os
    os.environ["ERP_PIPELINE_DB"] = str(tmp_path / "pipeline.sqlite3")
    os.environ["ERP_PERFORMANCE_DB"] = str(tmp_path / "performance.sqlite3")
    os.environ["ERP_CELLS_DB"] = str(tmp_path / "cells.sqlite3")
    ledger = PersistentRiskLedger(
        tmp_path / "erp.sqlite3",
        RiskLimits(max_total_risk_pct=0.10, max_engine_risk_pct=0.025),
    )
    calls = []
    def guard(request, *roles):
        calls.append(roles)
        return {"id": 1, "role": "admin"}
    router = build_erp_router(guard, ledger)
    return router, ledger, calls


def _endpoint(router, path, method="GET"):
    for route in router.routes:
        if route.path == path and method in route.methods:
            return route.endpoint
    raise AssertionError(f"route not found: {method} {path}")


def test_catalog_and_overview_expose_truthful_integration_states(tmp_path):
    router, ledger, _ = _router(tmp_path)
    request = SimpleNamespace()
    catalog = _endpoint(router, "/api/erp/catalog")(request)
    overview = _endpoint(router, "/api/erp/overview")(request)
    assert catalog["execution_allowed"] is False
    states = {item["id"]: item["state"] for item in catalog["modules"]}
    assert states["persistent_risk_ledger"] == "connected"
    assert states["mt5_execution"] == "disabled"
    assert overview["risk"]["active_reservations"] == 0
    assert overview["live_trading_enabled"] is False


def test_erp_risk_api_persists_equity_and_reservations(tmp_path):
    from modules.erp_api.router import EquityMarkPayload, ReservationPayload, ReservationTransitionPayload

    router, ledger, _ = _router(tmp_path)
    request = SimpleNamespace()
    equity = _endpoint(router, "/api/erp/risk/equity", "POST")(
        EquityMarkPayload(equity=10000, timestamp=1_800_000_000), request
    )
    assert equity["ok"] is True
    reserve = _endpoint(router, "/api/erp/risk/reservations", "POST")(
        ReservationPayload(reservation_id="order-1", engine="breakout",
                           risk_pct=0.02, timestamp=1_800_000_001), request
    )
    assert reserve["risk"]["active_risk_pct"] == pytest.approx(0.02)
    assert reserve["execution_allowed"] is False

    transition = _endpoint(router, "/api/erp/risk/reservations/{reservation_id}", "PATCH")(
        "order-1", ReservationTransitionPayload(status="OPEN", timestamp=1_800_000_002), request
    )
    assert transition["risk"]["active_reservations"] == 1
    assert ledger.snapshot(now=1_800_000_002).active_risk_pct == pytest.approx(0.02)


def test_erp_risk_api_rejects_over_budget_and_requires_admin_for_unlock(tmp_path):
    from fastapi import HTTPException
    from modules.erp_api.router import ReservationPayload, UnlockPayload

    router, _, calls = _router(tmp_path)
    request = SimpleNamespace()
    endpoint = _endpoint(router, "/api/erp/risk/reservations", "POST")
    endpoint(ReservationPayload(reservation_id="one", engine="breakout", risk_pct=0.02), request)
    with pytest.raises(HTTPException) as exc:
        endpoint(ReservationPayload(reservation_id="two", engine="breakout", risk_pct=0.02), request)
    assert exc.value.status_code == 409

    unlock = _endpoint(router, "/api/erp/risk/unlock", "POST")
    unlock(UnlockPayload(lock_name="daily", reason="reviewed by operator"), request)
    assert calls[-1] == ("admin",)


def test_brain_pipeline_validates_evidence_fuses_and_reserves_central_risk(tmp_path, monkeypatch):
    from datetime import datetime, timezone, timedelta
    from modules.erp_api.router import BrainPipelinePayload, AgentEvidencePayload

    router, ledger, _ = _router(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    bars = [
        {"time": int((now - timedelta(minutes=1)).timestamp()), "open": 2000, "high": 2002, "low": 1999, "close": 2001},
        {"time": int((now - timedelta(seconds=30)).timestamp()), "open": 2001, "high": 2003, "low": 2000, "close": 2002},
    ]
    def agent(name):
        return AgentEvidencePayload(
            agent_id=name, schema_version="1.0", scope="XAUUSD",
            as_of=now.isoformat(), source_ids=[f"feed:{name}"],
            data_quality="valid", confidence=0.95, stance="bullish",
            rationale="test evidence",
        )
    payload = BrainPipelinePayload(
        symbol="XAUUSD", bars=bars, expected_interval_seconds=30,
        market_as_of=now.isoformat(), agents=[agent("technical"), agent("news")],
        calendar_valid=True, emergency_stop=False, spread_pips=1,
    )
    endpoint = _endpoint(router, "/api/erp/brain/pipeline", "POST")
    result = endpoint(payload, SimpleNamespace(headers={"idempotency-key": "brain-test"}))
    run = result["run"]
    assert run["status"] == "COMPLETE"
    assert run["output"]["decision"]["action"] == "BUY"
    assert run["output"]["execution_allowed"] is False
    assert run["output"]["risk_reservation"]["active_reservations"] == 1
    assert ledger.snapshot().active_risk_pct == pytest.approx(0.025)


def test_brain_pipeline_quarantines_stale_or_bad_market_data(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from modules.erp_api.router import BrainPipelinePayload, AgentEvidencePayload

    router, _, _ = _router(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    agent = AgentEvidencePayload(
        agent_id="technical", schema_version="1.0", scope="XAUUSD",
        as_of=now.isoformat(), source_ids=["feed:technical"],
        data_quality="valid", confidence=0.9, stance="bullish", rationale="test",
    )
    payload = BrainPipelinePayload(
        symbol="XAUUSD",
        bars=[
            {"time": 1, "open": 2000, "high": 2002, "low": 1999, "close": 2001},
            {"time": 2, "open": 2001, "high": 2003, "low": 2000, "close": 2002},
        ],
        expected_interval_seconds=1, market_as_of=now.isoformat(), agents=[agent],
        calendar_valid=True, emergency_stop=False,
    )
    result = _endpoint(router, "/api/erp/brain/pipeline", "POST")(
        payload, SimpleNamespace(headers={})
    )["run"]
    assert result["status"] == "QUARANTINED"
    assert result["error"]["code"] == "invalid_evidence"


def test_performance_api_records_outcomes_and_reports_walk_forward(tmp_path, monkeypatch):
    from modules.erp_api.router import ClosedTradeOutcomePayload, AgentForecastPayload

    router, _, _ = _router(tmp_path, monkeypatch)
    endpoint = _endpoint(router, "/api/erp/performance/closed-trade", "POST")
    payload = ClosedTradeOutcomePayload(
        trade_id="closed-001", symbol="XAUUSD", closed_at=100,
        realized_return_pct=0.4,
        forecasts=[AgentForecastPayload(
            agent_id="technical", stance="bullish", confidence=0.8, as_of=90,
        )],
    )
    saved = endpoint(payload, SimpleNamespace(headers={}))
    assert saved["recorded"] is True
    report = _endpoint(router, "/api/erp/performance/walk-forward", "GET")(
        SimpleNamespace(headers={})
    )
    assert report["agents"]["technical"]["total_samples"] == 1
    assert report["live_weights_modified"] is False


def test_closed_trade_updates_shadow_cells_and_cognition_routes(tmp_path, monkeypatch):
    from modules.erp_api.router import ClosedTradeOutcomePayload, AgentForecastPayload, MarketAffectPayload

    router, _, _ = _router(tmp_path, monkeypatch)
    saved = _endpoint(router, "/api/erp/performance/closed-trade", "POST")(
        ClosedTradeOutcomePayload(
            trade_id="cell-trade-1", symbol="XAUUSD", closed_at=100,
            realized_return_pct=0.5,
            forecasts=[AgentForecastPayload(
                agent_id="technical", stance="bullish", confidence=0.9, as_of=90,
            )],
        ), SimpleNamespace(headers={})
    )
    assert saved["cell_learning"] == "updated_in_shadow_mode"
    cells = _endpoint(router, "/api/erp/cognition/cells", "GET")(SimpleNamespace(headers={}))
    assert cells["cells"]["technical"]["wins"] == 1
    assert cells["live_weight_change_authorized"] is False

    affect = _endpoint(router, "/api/erp/cognition/market-affect", "POST")(
        MarketAffectPayload(
            volatility_pct=4, spread_ratio=3, drawdown_pct=6,
            consecutive_losses=4, agent_disagreement=0.9, data_quality_score=0.5,
        ), SimpleNamespace(headers={})
    )
    assert affect["state"] == "extreme"
    assert affect["human_emotion_inference"] is False
    assert affect["trading_effect"] == "HOLD_REVIEW_REQUIRED"
