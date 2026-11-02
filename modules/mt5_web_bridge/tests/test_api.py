import time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from modules.mt5_web_bridge.api import build_mt5_bridge_router

def sample():
    now=int(time.time())
    bars=[]
    for i in range(20):
        p=1.1+i*0.0001
        bars.append({"time":now-(20-i)*900,"open":p,"high":p+0.0002,"low":p-0.0002,"close":p+0.0001,"tick_volume":100+i})
    return {"timestamp":now,"server_name":"Demo-Server","account_mode":"demo","currency":"USD","balance":10000,"equity":10000,"symbol":"EURUSD","timeframe":"M15","bid":1.1,"ask":1.1001,"spread_points":10,"point":0.00001,"digits":5,"tick_size":0.00001,"tick_value_loss":1.0,"stops_level_points":10,"freeze_level_points":0,"volume_min":0.01,"volume_max":100,"volume_step":0.01,"bars":bars}

@pytest.fixture
def client(tmp_path, monkeypatch):
    from modules.mt5_web_bridge import api
    monkeypatch.setattr(api,"DB_PATH",tmp_path/"bridge.sqlite3")
    monkeypatch.setenv("MT5_BRIDGE_TOKEN","t"*48)
    app=FastAPI()
    app.include_router(build_mt5_bridge_router(lambda request,*roles: {"role":"admin"}))
    return TestClient(app)

def test_initial_status_disconnected(client):
    d=client.get("/api/mt5/bridge/status").json()
    assert d["connected"] is False and d["execution_allowed"] is False

def test_ingest_requires_token(client):
    assert client.post("/api/mt5/bridge/ingest",json=sample()).status_code==401

def test_ingest_and_snapshot(client):
    r=client.post("/api/mt5/bridge/ingest",headers={"Authorization":"Bearer "+"t"*48},json=sample())
    assert r.status_code==200 and r.json()["execution_allowed"] is False
    d=client.get("/api/mt5/bridge/status").json()
    assert d["connected"] is True and d["symbol"]=="EURUSD"
    snap=client.get("/api/mt5/bridge/snapshot").json()
    assert len(snap["snapshot"]["bars"])==20

def test_stale_snapshot_rejected(client):
    p=sample();p["timestamp"]-=1000
    r=client.post("/api/mt5/bridge/ingest",headers={"Authorization":"Bearer "+"t"*48},json=p)
    assert r.status_code==422

def test_extra_credentials_rejected(client):
    p=sample();p["password"]="never-accept"
    r=client.post("/api/mt5/bridge/ingest",headers={"Authorization":"Bearer "+"t"*48},json=p)
    assert r.status_code==422


def test_future_snapshot_rejected(client):
    p=sample();p["timestamp"]+=120
    r=client.post("/api/mt5/bridge/ingest",headers={"Authorization":"Bearer "+"t"*48},json=p)
    assert r.status_code==422
