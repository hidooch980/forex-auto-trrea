from datetime import datetime,timedelta,timezone
import pytest
from modules.backtest_lab.engine import BacktestCandle,run_ema_backtest

def series(values):
    start=datetime(2025,1,1,tzinfo=timezone.utc)
    return [BacktestCandle(start+timedelta(hours=i),v,v*1.002,v*.998,v) for i,v in enumerate(values)]

def test_deterministic_and_never_allows_execution():
    values=[100+i*.2 for i in range(80)]
    a=run_ema_backtest(series(values)); b=run_ema_backtest(series(values))
    assert a==b and a.execution_allowed is False
    assert a.bars==80 and a.final_equity>0

def test_costs_reduce_or_preserve_result():
    values=[100+i*.2 for i in range(80)]
    free=run_ema_backtest(series(values),cost_bps_per_side=0)
    costly=run_ema_backtest(series(values),cost_bps_per_side=5)
    assert costly.final_equity<=free.final_equity

def test_rejects_bad_periods_and_short_history():
    with pytest.raises(ValueError,match="periods"):
        run_ema_backtest(series([100+i for i in range(40)]),fast_period=21,slow_period=9)
    with pytest.raises(ValueError,match="historical bars"):
        run_ema_backtest(series([100+i for i in range(20)]))

def test_rejects_bad_timestamps_and_ohlc():
    rows=series([100+i for i in range(40)])
    c=rows[-1]; rows[-1]=BacktestCandle(c.timestamp.replace(tzinfo=None),c.open,c.high,c.low,c.close)
    with pytest.raises(ValueError,match="timezone-aware"): run_ema_backtest(rows)
    rows=series([100+i for i in range(40)]); c=rows[-1]
    rows[-1]=BacktestCandle(c.timestamp,c.open,c.low-1,c.low,c.close)
    with pytest.raises(ValueError,match="geometry"): run_ema_backtest(rows)
