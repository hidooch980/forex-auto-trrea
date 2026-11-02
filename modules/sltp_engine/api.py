"""Authenticated, advisory-only adaptive SL/TP endpoint."""
from datetime import datetime
from fastapi import APIRouter,HTTPException,Request
from pydantic import BaseModel,Field
from .engine import Candle,BrokerSpec,plan_sltp

class CandlePayload(BaseModel):
    timestamp: datetime
    open: float=Field(gt=0,le=1e12)
    high: float=Field(gt=0,le=1e12)
    low: float=Field(gt=0,le=1e12)
    close: float=Field(gt=0,le=1e12)

class BrokerSpecPayload(BaseModel):
    point: float=Field(gt=0)
    tick_size: float=Field(gt=0)
    tick_value_loss: float=Field(gt=0)
    digits: int=Field(ge=0,le=10)
    stops_level_points: int=Field(ge=0)
    freeze_level_points: int=Field(ge=0)
    volume_min: float=Field(gt=0)
    volume_max: float=Field(gt=0)
    volume_step: float=Field(gt=0)

class SLTPPayload(BaseModel):
    side: str=Field(pattern="^(buy|sell)$")
    entry: float=Field(gt=0,le=1e12)
    equity: float=Field(gt=0,le=1e12)
    risk_pct: float=Field(default=0.25,gt=0,le=0.25)
    reward_risk: float=Field(default=1.5,ge=1,le=5)
    atr_period: int=Field(default=14,ge=2,le=100)
    atr_multiple: float=Field(default=1.5,gt=0,le=10)
    swing_lookback: int=Field(default=20,ge=3,le=200)
    spread_points: float=Field(default=0,ge=0)
    max_atr_multiple: float=Field(default=4,gt=0,le=10)
    candles: list[CandlePayload]=Field(min_length=22,max_length=5000)
    broker: BrokerSpecPayload

def build_sltp_router(require_role):
    router=APIRouter(prefix="/api/sltp",tags=["adaptive-sltp"])
    @router.post("/plan")
    def create_plan(payload: SLTPPayload,request: Request):
        require_role(request,"admin","trader","analyst")
        try:
            plan=plan_sltp([Candle(**bar.model_dump()) for bar in payload.candles],
                side=payload.side,entry=payload.entry,spec=BrokerSpec(**payload.broker.model_dump()),
                equity=payload.equity,risk_pct=payload.risk_pct,reward_risk=payload.reward_risk,
                atr_period=payload.atr_period,atr_multiple=payload.atr_multiple,
                swing_lookback=payload.swing_lookback,spread_points=payload.spread_points,
                max_atr_multiple=payload.max_atr_multiple)
        except ValueError as exc:
            raise HTTPException(status_code=422,detail=str(exc)) from exc
        return {"ok":True,"plan":plan.to_dict(),"execution_allowed":False}
    return router
