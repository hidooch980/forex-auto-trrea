from datetime import datetime,timedelta,timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from modules.sltp_engine.api import build_sltp_router

def test_authenticated_sltp_endpoint_is_advisory_only():
    roles=[]
    def require_role(request,*allowed):
        roles.append(allowed)
        assert "analyst" in allowed
    app=FastAPI();app.include_router(build_sltp_router(require_role))
    start=datetime(2025,1,1,tzinfo=timezone.utc)
    bars=[]
    for i in range(60):
        p=1.1000+i*0.00005
        bars.append({"timestamp":(start+timedelta(minutes=15*i)).isoformat(),
          "open":p,"high":p+0.0005,"low":p-0.0005,"close":p+0.0001})
    payload={"side":"buy","entry":1.1035,"equity":10000,"risk_pct":0.25,
      "reward_risk":1.5,"candles":bars,"broker":{"point":0.00001,
      "tick_size":0.00001,"tick_value_loss":1.0,"digits":5,
      "stops_level_points":10,"freeze_level_points":5,"volume_min":0.01,
      "volume_max":100,"volume_step":0.01}}
    response=TestClient(app).post("/api/sltp/plan",json=payload)
    assert response.status_code==200
    assert response.json()["execution_allowed"] is False
    assert response.json()["plan"]["valid"] is True
    assert roles

def test_sltp_api_rejects_bad_payload():
    app=FastAPI();app.include_router(build_sltp_router(lambda *args:None))
    response=TestClient(app).post("/api/sltp/plan",json={"side":"buy"})
    assert response.status_code==422
