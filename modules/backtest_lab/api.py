"""Authenticated, research-only backtest endpoint."""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from .engine import BacktestCandle, run_ema_backtest

class BacktestBarPayload(BaseModel):
    timestamp: datetime
    open: float = Field(gt=0, le=1e12)
    high: float = Field(gt=0, le=1e12)
    low: float = Field(gt=0, le=1e12)
    close: float = Field(gt=0, le=1e12)

class BacktestPayload(BaseModel):
    candles: list[BacktestBarPayload] = Field(min_length=24, max_length=10000)
    fast_period: int = Field(default=9, ge=2, le=199)
    slow_period: int = Field(default=21, ge=3, le=200)
    initial_equity: float = Field(default=10000, gt=0, le=1e12)
    cost_bps_per_side: float = Field(default=1, ge=0, le=1000)

def build_backtest_router(require_role):
    router=APIRouter(prefix="/api/backtest",tags=["backtest-lab"])
    @router.post("/run")
    def run(payload: BacktestPayload, request: Request):
        require_role(request,"admin","trader","analyst")
        try:
            result=run_ema_backtest(
                [BacktestCandle(**bar.model_dump()) for bar in payload.candles],
                fast_period=payload.fast_period,slow_period=payload.slow_period,
                initial_equity=payload.initial_equity,cost_bps_per_side=payload.cost_bps_per_side)
        except ValueError as exc:
            raise HTTPException(status_code=422,detail=str(exc)) from exc
        return {"ok":True,"result":result.to_dict(),"execution_allowed":False}
    return router
