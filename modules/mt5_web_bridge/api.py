"""Read-only MT5 snapshot bridge for the web Control Center."""
from __future__ import annotations
import hmac, json, os, sqlite3, time
from pathlib import Path
from typing import Callable
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

DB_PATH = Path(os.getenv("MT5_BRIDGE_DB", str(Path(__file__).resolve().parents[2] / "apps" / "control_center" / "data" / "mt5_bridge.sqlite3")))
MAX_AGE_SECONDS = int(os.getenv("MT5_BRIDGE_MAX_AGE_SECONDS", "120"))

class Candle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time: int = Field(gt=0)
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    tick_volume: int = Field(ge=0)
    @model_validator(mode="after")
    def check_range(self):
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close, self.high):
            raise ValueError("invalid candle OHLC range")
        return self

class BridgeSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timestamp: int = Field(gt=0)
    server_name: str = Field(min_length=1, max_length=160)
    account_mode: str = Field(pattern="^(demo|live|contest)$")
    currency: str = Field(min_length=3, max_length=8)
    balance: float = Field(ge=0, le=1e15)
    equity: float = Field(ge=0, le=1e15)
    symbol: str = Field(min_length=1, max_length=40, pattern="^[A-Za-z0-9._#-]+$")
    timeframe: str = Field(min_length=2, max_length=8)
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    spread_points: float = Field(ge=0)
    point: float = Field(gt=0)
    digits: int = Field(ge=0, le=12)
    tick_size: float = Field(gt=0)
    tick_value_loss: float = Field(gt=0)
    stops_level_points: int = Field(ge=0)
    freeze_level_points: int = Field(ge=0)
    volume_min: float = Field(gt=0)
    volume_max: float = Field(gt=0)
    volume_step: float = Field(gt=0)
    bars: list[Candle] = Field(min_length=20, max_length=300)
    @model_validator(mode="after")
    def check_market_data(self):
        if self.ask < self.bid:
            raise ValueError("ask must be >= bid")
        if self.volume_max < self.volume_min:
            raise ValueError("volume_max must be >= volume_min")
        if any(self.bars[i].time >= self.bars[i+1].time for i in range(len(self.bars)-1)):
            raise ValueError("bars must be ordered oldest to newest")
        return self

def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def _latest():
    with _connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS latest_snapshot (id INTEGER PRIMARY KEY CHECK(id=1), received_at INTEGER NOT NULL, payload_json TEXT NOT NULL)")
        row = db.execute("SELECT received_at,payload_json FROM latest_snapshot WHERE id=1").fetchone()
    return (int(row["received_at"]), json.loads(row["payload_json"])) if row else None

def build_mt5_bridge_router(require_role: Callable) -> APIRouter:
    router = APIRouter()
    @router.get("/api/mt5/bridge/status")
    def status(request: Request):
        require_role(request, "admin", "trader", "analyst", "viewer")
        latest = _latest()
        configured = len(os.getenv("MT5_BRIDGE_TOKEN", "")) >= 32
        if latest is None:
            return {"configured": configured, "connected": False, "last_received_at": None, "symbol": None, "account_mode": None, "execution_allowed": False}
        received, data = latest
        age = max(0, int(time.time()) - received)
        return {"configured": configured, "connected": configured and age <= MAX_AGE_SECONDS, "age_seconds": age, "last_received_at": received, "symbol": data["symbol"], "timeframe": data["timeframe"], "server_name": data["server_name"], "account_mode": data["account_mode"], "execution_allowed": False}
    @router.get("/api/mt5/bridge/snapshot")
    def snapshot(request: Request):
        require_role(request, "admin", "trader", "analyst", "viewer")
        latest = _latest()
        if latest is None:
            raise HTTPException(status_code=404, detail="No MT5 snapshot received yet.")
        received, data = latest
        age = max(0, int(time.time()) - received)
        return {"available": age <= MAX_AGE_SECONDS, "age_seconds": age, "received_at": received, "snapshot": data, "execution_allowed": False}
    @router.post("/api/mt5/bridge/ingest")
    def ingest(payload: BridgeSnapshot, authorization: str = Header(default="")):
        expected = os.getenv("MT5_BRIDGE_TOKEN", "")
        if len(expected) < 32:
            raise HTTPException(status_code=503, detail="MT5 bridge token is not configured.")
        supplied = authorization.removeprefix("Bearer ").strip()
        if not supplied or not hmac.compare_digest(supplied, expected):
            raise HTTPException(status_code=401, detail="Invalid bridge authorization.")
        now = int(time.time())
        if payload.timestamp > now + 30 or now - payload.timestamp > MAX_AGE_SECONDS:
            raise HTTPException(status_code=422, detail="Snapshot timestamp is stale or in the future.")
        encoded = json.dumps(payload.model_dump(), separators=(",", ":"), allow_nan=False)
        with _connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS latest_snapshot (id INTEGER PRIMARY KEY CHECK(id=1), received_at INTEGER NOT NULL, payload_json TEXT NOT NULL)")
            db.execute("INSERT INTO latest_snapshot(id,received_at,payload_json) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET received_at=excluded.received_at,payload_json=excluded.payload_json", (now, encoded))
        return {"ok": True, "received_at": now, "execution_allowed": False}
    return router
