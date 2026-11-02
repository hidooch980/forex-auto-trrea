"""Unified ERP API routes.

This facade joins existing modules through one authenticated contract. It is
not a broker adapter: all execution flags remain false until independently
verified venue adapters and execution-side controls exist.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from modules.risk_state_store import (
    PersistentRiskLedger, RiskLimitError, RiskStateError,
)

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
