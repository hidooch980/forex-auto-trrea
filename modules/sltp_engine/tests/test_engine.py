from datetime import datetime,timedelta,timezone
import pytest
from modules.sltp_engine.engine import Candle,BrokerSpec,plan_sltp

def history(n=60):
    start=datetime(2025,1,1,tzinfo=timezone.utc)
    out=[]
    for i in range(n):
        p=1.1000+i*0.00005
        out.append(Candle(start+timedelta(minutes=15*i),p,p+0.0005,p-0.0005,p+0.0001))
    return out

def spec(**kw):
    d=dict(point=0.00001,tick_size=0.00001,tick_value_loss=1.0,digits=5,
        stops_level_points=10,freeze_level_points=5,volume_min=0.01,
        volume_max=100,volume_step=0.01)
    d.update(kw); return BrokerSpec(**d)

def test_buy_plan_respects_structure_rr_and_risk_budget():
    rows=history()
    result=plan_sltp(rows,side="buy",entry=1.1035,spec=spec(),equity=10000,
                     risk_pct=0.25,reward_risk=2.0)
    assert result.valid and result.execution_allowed is False
    assert result.stop_loss<result.entry<result.take_profit
    assert result.reward_distance/result.risk_distance>=1.99
    assert result.estimated_risk_money<=result.risk_budget

def test_sell_plan_is_mirrored():
    rows=history()
    result=plan_sltp(rows,side="sell",entry=1.1035,spec=spec(),equity=10000)
    assert result.valid
    assert result.take_profit<result.entry<result.stop_loss
    assert result.estimated_risk_money<=result.risk_budget

def test_minimum_stop_distance_fail_closed():
    result=plan_sltp(history(),side="buy",entry=1.1035,
        spec=spec(stops_level_points=10000),equity=10000)
    assert not result.valid and "broker_minimum_stop_distance" in result.reasons
    assert result.stop_loss is None and result.volume==0

def test_too_far_structure_is_rejected():
    result=plan_sltp(history(),side="buy",entry=1.1001,spec=spec(),
        equity=10000,max_atr_multiple=1.1)
    assert not result.valid and "structure_too_far_from_entry" in result.reasons

def test_minimum_lot_never_forces_risk_overshoot():
    result=plan_sltp(history(),side="buy",entry=1.1035,spec=spec(volume_min=1.0),
        equity=100, risk_pct=0.01)
    assert not result.valid
    assert "risk_budget_below_broker_minimum_volume" in result.reasons
    assert result.volume==0

def test_rejects_naive_time_bad_ohlc_and_bad_rr():
    rows=history(); c=rows[-1]
    rows[-1]=Candle(c.timestamp.replace(tzinfo=None),c.open,c.high,c.low,c.close)
    with pytest.raises(ValueError,match="timezone-aware"):
        plan_sltp(rows,side="buy",entry=1.1035,spec=spec(),equity=10000)
    rows=history(); c=rows[-1]
    rows[-1]=Candle(c.timestamp,c.open,c.low,c.low,c.close)
    with pytest.raises(ValueError,match="geometry"):
        plan_sltp(rows,side="buy",entry=1.1035,spec=spec(),equity=10000)
    with pytest.raises(ValueError,match="reward_risk"):
        plan_sltp(history(),side="buy",entry=1.1035,spec=spec(),equity=10000,reward_risk=0.5)

def test_risk_caps_reject_more_than_quarter_percent():
    with pytest.raises(ValueError,match="risk_pct"):
        plan_sltp(history(),side="buy",entry=1.1035,spec=spec(),equity=10000,risk_pct=0.5)
