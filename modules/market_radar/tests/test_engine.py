from datetime import datetime,timedelta,timezone
import math
import pytest
from modules.market_radar.engine import Candle,analyze_market
NOW=datetime(2026,11,2,12,0,tzinfo=timezone.utc)
def make_candles(age=60):
    closes=[1.1+i*0.0001 for i in range(40)]; start=NOW-timedelta(minutes=len(closes),seconds=age)
    return [Candle(start+timedelta(minutes=i),p,p+0.0003,p-0.0003,p,100.0) for i,p in enumerate(closes)]
def test_valid_analysis_is_deterministic_and_never_executes():
    a=analyze_market("eurusd","M5",make_candles(),now=NOW); b=analyze_market("eurusd","M5",make_candles(),now=NOW)
    assert a==b and a.symbol=="EURUSD" and a.data_status=="valid"
    assert a.atr_14>0 and 0<=a.rsi_14<=100 and a.execution_allowed is False
    assert a.stance in {"BUY_BIAS","SELL_BIAS","HOLD"}
def test_rejects_too_few_bars():
    with pytest.raises(ValueError,match="30 and 1000"): analyze_market("EURUSD","M5",make_candles()[:29],now=NOW)
def test_rejects_stale_and_future_bars():
    with pytest.raises(ValueError,match="stale"): analyze_market("EURUSD","M5",make_candles(2000),now=NOW)
    with pytest.raises(ValueError,match="future"): analyze_market("EURUSD","M5",make_candles(-120),now=NOW)
def test_rejects_duplicate_timestamps():
    rows=make_candles(); c=rows[-1]; rows[-1]=Candle(rows[-2].timestamp,c.open,c.high,c.low,c.close,c.volume)
    with pytest.raises(ValueError,match="strictly increasing"): analyze_market("EURUSD","M5",rows,now=NOW)
def test_rejects_bad_ohlc_and_nonfinite_values():
    rows=make_candles(); c=rows[-1]; rows[-1]=Candle(c.timestamp,c.open,c.low-1,c.low,c.close,c.volume)
    with pytest.raises(ValueError,match="high is inconsistent"): analyze_market("EURUSD","M5",rows,now=NOW)
    rows=make_candles(); c=rows[-1]; rows[-1]=Candle(c.timestamp,c.open,math.nan,c.low,c.close,c.volume)
    with pytest.raises(ValueError,match="finite"): analyze_market("EURUSD","M5",rows,now=NOW)
def test_rejects_naive_timestamps():
    rows=make_candles(); c=rows[-1]; rows[-1]=Candle(c.timestamp.replace(tzinfo=None),c.open,c.high,c.low,c.close,c.volume)
    with pytest.raises(ValueError,match="timezone-aware"): analyze_market("EURUSD","M5",rows,now=NOW)
