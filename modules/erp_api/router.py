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
from modules.performance_memory import PerformanceMemory
from modules.cognitive_cells import CellularLearning, analyze_market_affect
from modules.risk_behavior_guard import AccountRisk, BehaviorMetrics, TradeProposal, RiskLimits, evaluate_trade

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
    # Required at decision time for any directional candidate; absent evidence fails closed.
    behavior: dict[str, Any] | None = None


class AgentForecastPayload(BaseModel):
    agent_id: str = Field(min_length=1, max_length=80)
    stance: str = Field(pattern="^(bullish|bearish|neutral)$")
    confidence: float = Field(ge=0, le=1)
    as_of: int = Field(ge=0)


class ClosedTradeOutcomePayload(BaseModel):
    trade_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=3, max_length=32)
    closed_at: int = Field(ge=0)
    realized_return_pct: float
    forecasts: list[AgentForecastPayload] = Field(min_length=1, max_length=30)


class TradingBehaviorPayload(BaseModel):
    daily_loss_pct: float = Field(ge=0, le=100)
    weekly_loss_pct: float = Field(ge=0, le=100)
    peak_drawdown_pct: float = Field(ge=0, le=100)
    trades_today: int = Field(ge=0, le=10000)
    consecutive_losses: int = Field(ge=0, le=1000)
    emergency_stop: bool = True
    trades_last_hour: int = Field(ge=0, le=1000)
    minutes_since_last_loss: float | None = Field(default=None, ge=0)
    risk_vs_recent_average: float = Field(ge=0, le=100)
    volume_multiplier_after_loss: float = Field(ge=0, le=100)
    signal_age_seconds: float = Field(ge=0, le=1e9)
    normal_signal_age_seconds: float = Field(default=60, gt=0, le=1e9)
    proposed_risk_pct: float = Field(gt=0, le=100)
    reward_risk: float = Field(ge=0, le=100)
    has_stop_loss: bool
    market_data_valid: bool
    calendar_clear: bool
    spread_acceptable: bool


class MarketAffectPayload(BaseModel):
    volatility_pct: float = Field(ge=0, le=1000)
    spread_ratio: float = Field(ge=0, le=1000)
    drawdown_pct: float = Field(ge=0, le=100)
    consecutive_losses: int = Field(ge=0, le=1000)
    agent_disagreement: float = Field(ge=0, le=1)
    data_quality_score: float = Field(ge=0, le=1)


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
    lock_name: str = Field(pattern="^(daily|drawdown|emergency_stop)$")
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
        "emergency_stop": snapshot.emergency_stop,
        "locked": snapshot.locked,
        "updated_at": snapshot.updated_at,
    }


def build_erp_router(require_role: Callable, ledger: PersistentRiskLedger) -> APIRouter:
    router = APIRouter(prefix="/api/erp", tags=["ERP Integration"])

    pipeline = PersistentPipeline(default_pipeline_path())
    performance = PerformanceMemory(default_performance_path())
    cells = CellularLearning(default_cells_path())

    def execute_brain_pipeline(run_id: str, raw: dict):
        try:
            pipeline.stage(run_id, "VALIDATE", "validation_started", "Checking market bars and agent evidence")
            now = datetime.now(timezone.utc)
            market_as_of = datetime.fromisoformat(raw["market_as_of"].replace("Z", "+00:00"))
            if market_as_of.tzinfo is None or market_as_of.utcoffset() is None:
                raise PipelineError("invalid_evidence", "Market timestamp must include a timezone")
            market_age = (now - market_as_of.astimezone(timezone.utc)).total_seconds()
            if market_age < -30 or market_age > 7200:
                raise PipelineError("invalid_evidence", "Market snapshot timestamp is future-dated or stale")
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
            average_range_pct = sum(
                (float(bar["high"]) - float(bar["low"])) / max(float(bar["close"]), 1e-12) * 100
                for bar in raw["bars"]
            ) / len(raw["bars"])
            raw_scores = [signal.score for signal in signals if signal.available]
            disagreement = min(1.0, max(0.0, 1.0 - abs(sum(raw_scores) / len(raw_scores)))) if raw_scores else 1.0
            affect = analyze_market_affect(
                volatility_pct=average_range_pct,
                spread_ratio=raw["spread_pips"] / 2.5,
                drawdown_pct=raw["drawdown_pct"],
                consecutive_losses=0,
                agent_disagreement=disagreement,
                data_quality_score=1.0 if quality.valid else 0.0,
            )
            shadow_cells = cells.snapshot()["cells"]
            reliability = {
                name: cell["shadow_reliability_multiplier"]
                for name, cell in shadow_cells.items()
                if cell["eligible_for_shadow_weighting"]
            }
            context = MarketContext(
                symbol=raw["symbol"], market_data_valid=quality.valid,
                calendar_valid=raw["calendar_valid"],
                high_impact_blackout=raw["high_impact_blackout"],
                emergency_stop=raw["emergency_stop"] or ledger.snapshot().locked or affect.state == "extreme",
                daily_loss_pct=raw["daily_loss_pct"],
                drawdown_pct=raw["drawdown_pct"], spread_pips=raw["spread_pips"],
                requested_risk_pct=0.025, reliability=reliability,
            )
            decision = evaluate_market(context, signals, BrainConfig())
            decision_data = decision.to_dict()
            behavioral_guard = {
                "evaluated": False, "approved": False,
                "reasons": ["not_required_for_non_directional_decision"],
                "behavior_flags": [], "risk_cap_pct": 0.0,
            }
            if decision.approved:
                behavior_raw = raw.get("behavior")
                if not isinstance(behavior_raw, dict):
                    behavioral_guard = {
                        "evaluated": True, "approved": False,
                        "reasons": ["behavioral_evidence_missing"],
                        "behavior_flags": [], "risk_cap_pct": 0.0,
                    }
                else:
                    behavior_input = TradingBehaviorPayload.model_validate(behavior_raw)
                    account = AccountRisk(
                        daily_loss_pct=behavior_input.daily_loss_pct,
                        weekly_loss_pct=behavior_input.weekly_loss_pct,
                        peak_drawdown_pct=behavior_input.peak_drawdown_pct,
                        trades_today=behavior_input.trades_today,
                        consecutive_losses=behavior_input.consecutive_losses,
                        emergency_stop=behavior_input.emergency_stop or ledger.snapshot().locked,
                    )
                    behavior_metrics = BehaviorMetrics(
                        trades_last_hour=behavior_input.trades_last_hour,
                        minutes_since_last_loss=behavior_input.minutes_since_last_loss,
                        risk_vs_recent_average=behavior_input.risk_vs_recent_average,
                        volume_multiplier_after_loss=behavior_input.volume_multiplier_after_loss,
                        signal_age_seconds=behavior_input.signal_age_seconds,
                        normal_signal_age_seconds=behavior_input.normal_signal_age_seconds,
                    )
                    proposal = TradeProposal(
                        risk_pct=behavior_input.proposed_risk_pct,
                        reward_risk=behavior_input.reward_risk,
                        has_stop_loss=behavior_input.has_stop_loss,
                        market_data_valid=behavior_input.market_data_valid,
                        calendar_clear=behavior_input.calendar_clear,
                        spread_acceptable=behavior_input.spread_acceptable,
                    )
                    guard_result = evaluate_trade(account, proposal, behavior_metrics, RiskLimits())
                    behavioral_guard = {
                        "evaluated": True, "approved": guard_result.approved,
                        "reasons": list(guard_result.reasons),
                        "behavior_flags": list(guard_result.behavior_flags),
                        "risk_cap_pct": guard_result.risk_cap_pct,
                        "cooldown_required_minutes": guard_result.cooldown_required_minutes,
                        "interpretation": "objective_behavioral_proxies_only",
                    }
                if not behavioral_guard["approved"]:
                    decision_data["approved"] = False
                    decision_data["action"] = "HOLD"
                    decision_data["risk_pct"] = 0.0
                    decision_data["reasons"] = list(decision_data["reasons"]) + ["behavioral_guard_blocked"]
                else:
                    decision_data["risk_pct"] = min(
                        decision_data["risk_pct"],
                        behavior_input.proposed_risk_pct,
                        behavioral_guard["risk_cap_pct"],
                    )

            pipeline.stage(run_id, "RISK_GATE", "brain_decision_created", "Master Brain and behavioral risk gates evaluated")
            output = {
                "decision": decision_data,
                "behavioral_guard": behavioral_guard,
                "market_quality": quality.to_dict(),
                "market_affect": {
                    "state": affect.state, "stress_score": affect.stress_score,
                    "flags": list(affect.flags), "human_emotion_inference": False,
                },
                "cell_learning_mode": "shadow_only",
                "execution_allowed": False,
                "live_trading_enabled": False,
                "risk_reservation": None,
            }
            if decision_data["approved"]:
                try:
                    reserved = ledger.reserve(run_id, "master_brain", decision_data["risk_pct"], status="PENDING")
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

    @router.post("/performance/closed-trade")
    def record_closed_trade(payload: ClosedTradeOutcomePayload, request: Request):
        require_role(request, "admin", "trader", "analyst")
        try:
            result = performance.record_closed_trade(
                payload.trade_id, payload.symbol, payload.closed_at,
                payload.realized_return_pct, [item.model_dump() for item in payload.forecasts],
            )
            outcome = "win" if payload.realized_return_pct > 0 else "loss" if payload.realized_return_pct < 0 else "neutral"
            for forecast in payload.forecasts:
                stance = forecast.stance
                correct = (stance == "bullish" and outcome == "win") or (stance == "bearish" and outcome == "loss")
                cell_outcome = "neutral" if stance == "neutral" or outcome == "neutral" else "win" if correct else "loss"
                if forecast.agent_id.strip().lower() in {"technical", "institutional", "news", "macro", "smart_money", "strategy"}:
                    cells.observe(forecast.agent_id, cell_outcome, closed_at=payload.closed_at)
            return {**result, "cell_learning": "updated_in_shadow_mode"}
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise HTTPException(status_code=409, detail="Trade outcome already recorded") from exc
            raise

    @router.get("/performance/walk-forward")
    def performance_walk_forward(request: Request):
        require_role(request, "admin", "trader", "analyst", "viewer")
        return performance.report()

    @router.get("/cognition/cells")
    def cognition_cells(request: Request):
        require_role(request, "admin", "trader", "analyst", "viewer")
        return cells.snapshot()

    @router.post("/cognition/market-affect")
    def cognition_market_affect(payload: MarketAffectPayload, request: Request):
        require_role(request, "admin", "trader", "analyst", "viewer")
        affect = analyze_market_affect(**payload.model_dump())
        return {
            "state": affect.state,
            "stress_score": affect.stress_score,
            "flags": list(affect.flags),
            "human_emotion_inference": False,
            "trading_effect": "HOLD_REVIEW_REQUIRED" if affect.state == "extreme" else "RESEARCH_CONTEXT_ONLY",
        }

    @router.post("/cognition/trading-behavior")
    def cognition_trading_behavior(payload: TradingBehaviorPayload, request: Request):
        require_role(request, "admin", "trader", "analyst", "viewer")
        account = AccountRisk(
            daily_loss_pct=payload.daily_loss_pct,
            weekly_loss_pct=payload.weekly_loss_pct,
            peak_drawdown_pct=payload.peak_drawdown_pct,
            trades_today=payload.trades_today,
            consecutive_losses=payload.consecutive_losses,
            emergency_stop=payload.emergency_stop,
        )
        behavior = BehaviorMetrics(
            trades_last_hour=payload.trades_last_hour,
            minutes_since_last_loss=payload.minutes_since_last_loss,
            risk_vs_recent_average=payload.risk_vs_recent_average,
            volume_multiplier_after_loss=payload.volume_multiplier_after_loss,
            signal_age_seconds=payload.signal_age_seconds,
            normal_signal_age_seconds=payload.normal_signal_age_seconds,
        )
        proposal = TradeProposal(
            risk_pct=payload.proposed_risk_pct, reward_risk=payload.reward_risk,
            has_stop_loss=payload.has_stop_loss, market_data_valid=payload.market_data_valid,
            calendar_clear=payload.calendar_clear, spread_acceptable=payload.spread_acceptable,
        )
        result = evaluate_trade(account, proposal, behavior, RiskLimits())
        return {
            "approved": result.approved, "reasons": list(result.reasons),
            "behavior_flags": list(result.behavior_flags),
            "risk_cap_pct": result.risk_cap_pct,
            "cooldown_required_minutes": result.cooldown_required_minutes,
            "emotion_diagnosis": False,
            "interpretation": "objective_behavioral_proxies_only",
            "execution_allowed": False,
        }

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
                {"id": "data_pipeline_error_center", "state": "connected", "api": "/api/erp/brain/pipeline/health"},
                {"id": "agent_performance_memory", "state": "connected", "api": "/api/erp/performance/walk-forward"},
                {"id": "cognitive_cells", "state": "shadow_learning", "api": "/api/erp/cognition/cells"},
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

    @router.post("/risk/emergency-stop")
    def activate_emergency_stop(payload: UnlockPayload, request: Request):
        require_role(request, "admin")
        if payload.lock_name != "emergency_stop":
            raise HTTPException(status_code=400, detail="lock_name must be emergency_stop")
        try:
            snap = ledger.set_emergency_stop(True, payload.reason, now=payload.timestamp)
        except (ValueError, RiskStateError) as exc:
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


def default_performance_path() -> Path:
    configured = os.getenv("ERP_PERFORMANCE_DB")
    if configured:
        return Path(configured)
    return Path(os.getenv("ERP_DATA_DIR", "data")) / "erp_performance_memory.sqlite3"


def default_cells_path() -> Path:
    configured = os.getenv("ERP_CELLS_DB")
    if configured:
        return Path(configured)
    return Path(os.getenv("ERP_DATA_DIR", "data")) / "erp_cognitive_cells.sqlite3"
