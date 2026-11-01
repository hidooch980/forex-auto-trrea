import pytest
from src.smart_tpsl import ExitConfig, plan_trade, manage_open_trade

def test_buy_plan():
    p=plan_trade("EURUSD","BUY",1.1000,0.0010,1.0990,1.1020,"TREND")
    assert p["sl"] < p["entry"] < p["tp"]
    assert p["tp_r_multiple"] == ExitConfig().trend_tp_r

def test_sell_plan():
    p=plan_trade("XAUUSD","SELL",2300,5,2290,2310,"RANGE")
    assert p["tp"] < p["entry"] < p["sl"]

def test_partial_be_trailing_long():
    c=ExitConfig()
    p=manage_open_trade("BUY",1.1,1.102,0.0005,1.099,
       {"initial_risk":0.001,"partial_done":False},c,cost_buffer=0.00005)
    assert p["close_fraction"] == 0.5
    assert p["new_sl"] >= 1.10005
    assert p["modify_sl"]

def test_stop_never_widens():
    p=manage_open_trade("SELL",1.1,1.101,0.001,1.102,
       {"initial_risk":0.001},ExitConfig())
    assert p["new_sl"] <= 1.102

def test_bad_side_rejected():
    with pytest.raises(ValueError):
        plan_trade("EURUSD","HOLD",1.1,0.001)
