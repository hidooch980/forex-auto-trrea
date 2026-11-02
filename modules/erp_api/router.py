"""Unified ERP API routes.

This facade joins existing modules through one authenticated contract. It is
not a broker adapter: all execution flags remain false until independently
verified venue adapters and execution-side controls exist.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Any
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from modules.risk_state_store import (
    PersistentRiskLedger, RiskLimitError, RiskStateError,
)
from modules.data_pipeline import PersistentPipeline, PipelineError
from modules.agent_contracts import validate_agent_output
from modules.market_data_quality import validate_bars
from modules.master_brain.engine import AgentSignal, MarketContext, BrainConfig, evaluate_market

class AgentEvidencePayload(BaseModel):
    agent_id: str = Field(min_length=1, max_length=80)
    schema_version: str = Field(min_length=1, max_length=40)
    scope: str = Field(min_length=1, max_length=120)
    as_of: str
    source_ids: list[str] = Field(min_length=1, max_length=30)
    data_quality: str
    confidence: float = Field(ge=0, le=1)
    stance: str
    rationale: str = Field(min_length=1, max_length=1000)
    invalidations: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list)


class BrainPipelinePayload(BaseModel):
    symbol: str = Field(min_length=3, max_length=32)
    bars: list[dict[str, Any]] = Field(min_length=2, max_length=5000)
    expected_interval_seconds: int = Field(gt=0, le=86400)
    market_as_of: str
    agents: list[AgentEvidencePayload] = Field(min_length=1, max_length=20)
    calendar_valid: bool = False
    high_impact_blackout: bool = False
    emergency_stop: bool = True
    daily_loss_pct: float = Field(default=0, ge=0, le=100)
    drawdown_pct: float = Field(default=0, ge=0, le=100)
    spread_pips: float = Field(default=0, ge=0, le=100000)


class EquityMarkPayload(BaseModel):
    equity: float = Field(gt=0, le=1_000_000_000_000)
    timestamp: int | None = Field(default=None, ge=0)

class ReservationPayload(BaseModel):
    reservation_id: str = Field(min_length=1, max_length=128)
    engine: str = Field(min_length=1, max_length=80)
    risk_pct: float = Field(gt=0, le=100)
    status: str = Field(default="PENDING", pattern="^(PENDING|OPEN)$")
    timestamp: int | None = Field(default=None, ge=0)

class ReservationTransitionPayload(BaseModel):
    status: str = Field(pattern="^(OPEN|CLOSED|CANCELLED)$")
    timestamp: int | None = Field(default=None, ge=0)

class UnlockPayload(BaseModel):
    lock_name: str = Field(pattern="^(daily|drawdown)$")
    reason: str = Field(min_length=8, max_length=500)
    timestamp: int | None = Field(default=None, ge=0)


def _snapshot_dict(snapshot):
    return {
        "active_risk_pct": snapshot.active_risk_pct,
        "active_reservations": snapshot.active_reservations,
        "active_by_engine": snapshot.active_by_engine,
        "daily_loss_pct": snapshot.daily_loss_pct,
        "peak_drawdown_pct": snapshot.peak_drawdown_pct,
        "daily_lock": snapshot.daily_lock,
        "drawdown_lock": snapshot.drawdown_lock,
        "locked": snapshot.locked,
        "updated_at": snapshot.updated_at,
    }


def build_erp_router(require_role: Callable, ledger: PersistentRiskLedger) -> APIRouter:
    router = APIRouter(prefix="/api/erp", tags=["ERP Integration"])

    pipeline = PersistentPipeline(default_pipeline_path())

    def execute_brain_pipeline(run_id: str, raw: dict):
        try:
            pipeline.stage(run_id, "VALIDATE", "validation_started", "Checking market bars and agent evidence")
            now = datetime.now(timezone.utc)
            market_as_of = datetime.fromisoformat(raw["market_as_of"].replace("Z", "+00:00"))
            if market_as_of.tzinfo is None or market_as_of.utcoffset() is None:
                raise PipelineError("invalid_evidence", "Market timestamp must include a timezone")
            quality = validate_bars(
                raw["bars"], as_of=now, max_age_seconds=7200,
                expected_interval_seconds=raw["expected_interval_seconds"],
            )
            if not quality.valid:
                raise PipelineError("invalid_evidence", "Market data rejected: " + ",".join(quality.errors))
            signals = []
            for item in raw["agents"]:
                validated = validate_agent_output(item, now=now, max_age_seconds=900)
                if validated.scope.upper() != raw["symbol"].upper():
                    raise PipelineError("schema_violation", "Agent scope does not match requested symbol")
                score = {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0, "unavailable": 0.0}[validated.stance]
                signals.append(AgentSignal(
                    name=validated.agent_id, score=score,
                    confidence=validated.confidence, rationale=validated.rationale,
                    age_seconds=max(0.0, (now - validated.as_of).total_seconds()),
                    available=validated.stance != "unavailable",
                ))
            pipeline.stage(run_id, "FUSE", "evidence_validated", f"{len(signals)} agent outputs and {quality.rows} bars validated")
            context = MarketContext(
                symbol=raw["symbol"], market_data_valid=quality.valid,
                calendar_valid=raw["calendar_valid"],
                high_impact_blackout=raw["high_impact_blackout"],
                emergency_stop=raw["emergency_stop"],
                daily_loss_pct=raw["daily_loss_pct"],
                drawdown_pct=raw["drawdown_pct"], spread_pips=raw["spread_pips"],
                requested_risk_pct=0.025,
            )
            decision = evaluate_market(context, signals, BrainConfig())
            pipeline.stage(run_id, "RISK_GATE", "brain_decision_created", "Deterministic committee decision evaluated")
            output = {
                "decision": decision.to_dict(),
                "market_quality": quality.to_dict(),
                "execution_allowed": False,
                "live_trading_enabled": False,
                "risk_reservation": None,
            }
            if decision.approved:
                try:
                    reserved = ledger.reserve(run_id, "master_brain", decision.risk_pct, status="PENDING")
                    output["risk_reservation"] = _snapshot_dict(reserved)
                except (RiskLimitError, RiskStateError) as exc:
                    output["decision"]["approved"] = False
                    output["decision"]["action"] = "HOLD"
                    output["decision"]["risk_pct"] = 0.0
                    output["decision"]["reasons"] = list(output["decision"]["reasons"]) + ["central_risk_ledger_blocked"]
                    output["risk_block_reason"] = str(exc)
            pipeline.finish(run_id, output)
            return pipeline.get(run_id)
        except PipelineError as exc:
            pipeline.fail(run_id, exc.code, str(exc), retryable=exc.retryable)
            return pipeline.get(run_id)
        except (ValueError, TypeError, KeyError) as exc:
            pipeline.fail(run_id, "invalid_evidence", str(exc))
            return pipeline.get(run_id)
        except Exception as exc:
            pipeline.fail(run_id, "internal_pipeline_error", type(exc).__name__)
            return pipeline.get(run_id)

    @router.post("/brain/pipeline")
    def run_brain_pipeline(payload: BrainPipelinePayload, request: Request):
        require_role(request, "admin", "trader", "analyst")
        try:
            run_id, created = pipeline.create(payload.model_dump(), request.headers.get("idempotency-key"))
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = execute_brain_pipeline(run_id, payload.model_dump()) if created else pipeline.get(run_id)
        return {"created": created, "run": result, "execution_allowed": False}

    @router.get("/brain/pipeline/health")
    def brain_pipeline_health(request: Request):
        require_role(request, "admin", "trader", "analyst", "viewer")
        return pipeline.health()

    @router.get("/brain/pipeline/{run_id}")
    def brain_pipeline_run(run_id: str, request: Request):
        require_role(request, "admin", "trader", "analyst", "viewer")
        result = pipeline.get(run_id)
        if not result:
            raise HTTPException(status_code=404, detail="Pipeline run not found")
        return result

    @router.post("/brain/pipeline/{run_id}/retry")
    def retry_brain_pipeline(run_id: str, request: Request):
        require_role(request, "admin", "trader")
        try:
            raw, _ = pipeline.retry(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Pipeline run not found") from exc
        except PipelineError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"run": execute_brain_pipeline(run_id, raw), "execution_allowed": False}

    @router.get("/catalog")
    def catalog(request: Request):
        require_role(request, "admin", "trader", "analyst", "viewer")
        return {
            "contract_version": "1.0",
            "modules": [
                {"id": "control_center", "state": "connected", "api": "/api/status"},
                {"id": "master_brain", "state": "research_only", "api": "/api/decision-preview"},
                {"id": "xauusd_phantom", "state": "risk_planner_only", "api": "/api/erp/risk/reservations"},
                {"id": "persistent_risk_ledger", "state": "connected", "api": "/api/erp/risk/snapshot"},
                {"id": "portfolio_risk_guard", "state": "preview_only", "api": "/api/risk/portfolio-preview"},
                {"id": "broker_directory", "state": "connected", "api": "/api/brokers"},
                {"id": "ftmo_registry", "state": "connected", "api": "/api/ftmo/accounts"},
                {"id": "news_provider", "state": "not_connected", "api": "/api/news"},
                {"id": "market_data", "state": "not_connected", "api": None},
                {"id": "analytics", "state": "no_live_trade_history", "api": "/api/analytics/overview"},
                {"id": "mt5_execution", "state": "disabled", "api": None},
            ],
            "live_trading_enabled": False,
            "execution_allowed": False,
        }

    @router.get("/overview")
    def overview(request: Request):
        require_role(request, "admin", "trader", "analyst", "viewer")
        snap = ledger.snapshot()
        return {
            "service": "forex-ai-erp",
            "contract_version": "1.0",
            "health": "degraded" if snap.locked else "safe_scaffold",
            "risk": _snapshot_dict(snap),
            "live_trading_enabled": False,
            "execution_allowed": False,
            "external_sources_verified": False,
        }

    @router.get("/risk/snapshot")
    def risk_snapshot(request: Request):
        require_role(request, "admin", "trader", "analyst", "viewer")
        return {"risk": _snapshot_dict(ledger.snapshot()), "execution_allowed": False}

    @router.post("/risk/equity")
    def record_equity(payload: EquityMarkPayload, request: Request):
        require_role(request, "admin", "trader")
        try:
            snap = ledger.record_equity(payload.equity, now=payload.timestamp)
        except (ValueError, RiskStateError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "risk": _snapshot_dict(snap), "execution_allowed": False}

    @router.post("/risk/reservations", status_code=201)
    def reserve_risk(payload: ReservationPayload, request: Request):
        require_role(request, "admin", "trader")
        try:
            snap = ledger.reserve(
                payload.reservation_id, payload.engine, payload.risk_pct,
                status=payload.status, now=payload.timestamp,
            )
        except RiskLimitError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RiskStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "risk": _snapshot_dict(snap), "execution_allowed": False,
                "message": "Risk reserved in the persistent ledger; no broker order was sent."}

    @router.patch("/risk/reservations/{reservation_id}")
    def transition_reservation(reservation_id: str, payload: ReservationTransitionPayload, request: Request):
        require_role(request, "admin", "trader")
        try:
            snap = ledger.transition(reservation_id, payload.status, now=payload.timestamp)
        except RiskStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "risk": _snapshot_dict(snap), "execution_allowed": False}

    @router.post("/risk/unlock")
    def unlock_risk(payload: UnlockPayload, request: Request):
        require_role(request, "admin")
        try:
            snap = ledger.unlock(payload.lock_name, payload.reason, now=payload.timestamp)
        except (ValueError, RiskStateError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "risk": _snapshot_dict(snap), "execution_allowed": False}

    return router


def default_ledger_path() -> Path:
    configured = os.getenv("ERP_RISK_LEDGER_DB")
    if configured:
        return Path(configured)
    return Path(os.getenv("ERP_DATA_DIR", "data")) / "erp_risk_ledger.sqlite3"


def default_pipeline_path() -> Path:
    configured = os.getenv("ERP_PIPELINE_DB")
    if configured:
        return Path(configured)
    return Path(os.getenv("ERP_DATA_DIR", "data")) / "erp_pipeline.sqlite3"
