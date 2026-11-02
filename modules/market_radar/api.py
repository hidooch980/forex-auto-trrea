"""Authenticated preview-only API for deterministic market radar."""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from .engine import Candle, analyze_market

class CandlePayload(BaseModel):
    timestamp: datetime
    open: float = Field(gt=0, le=1e12)
    high: float = Field(gt=0, le=1e12)
    low: float = Field(gt=0, le=1e12)
    close: float = Field(gt=0, le=1e12)
    volume: float = Field(default=0, ge=0, le=1e18)

class RadarPayload(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    timeframe: str = Field(min_length=1, max_length=16)
    candles: list[CandlePayload] = Field(min_length=30, max_length=1000)
    max_age_seconds: int = Field(default=900, ge=1, le=86400)

def build_market_radar_router(require_role):
    router=APIRouter(prefix="/api/market-radar",tags=["market-radar"])
    @router.post("/analyze")
    def analyze(payload: RadarPayload, request: Request):
        require_role(request,"admin","trader","analyst","viewer")
        try:
            result=analyze_market(payload.symbol,payload.timeframe,
                [Candle(**row.model_dump()) for row in payload.candles],
                max_age_seconds=payload.max_age_seconds)
        except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc
        return {"ok":True,"analysis":result.to_dict(),"execution_allowed":False}
    return router
