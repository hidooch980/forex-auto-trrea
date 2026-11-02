from datetime import datetime,timedelta,timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from modules.backtest_lab.api import build_backtest_router

def test_authenticated_backtest_api_returns_research_only_result():
    calls=[]
    def require_role(request,*roles):
        calls.append(roles)
        assert "analyst" in roles
    app=FastAPI(); app.include_router(build_backtest_router(require_role))
    start=datetime(2025,1,1,tzinfo=timezone.utc)
    bars=[]
    for i in range(60):
        p=100+i*0.1
        bars.append({"timestamp":(start+timedelta(hours=i)).isoformat(),"open":p,"high":p+0.2,"low":p-0.2,"close":p})
    response=TestClient(app).post("/api/backtest/run",json={"candles":bars})
    assert response.status_code==200
    body=response.json()
    assert body["ok"] is True and body["execution_allowed"] is False
    assert body["result"]["bars"]==60
    assert calls

def test_backtest_api_rejects_invalid_history():
    app=FastAPI(); app.include_router(build_backtest_router(lambda *args: None))
    response=TestClient(app).post("/api/backtest/run",json={"candles":[]})
    assert response.status_code==422
