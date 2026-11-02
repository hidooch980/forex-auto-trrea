from types import SimpleNamespace
import pytest
from modules.mt5_discovery.discovery import discover_connected_terminal,discover_symbol_spec,discover_market_snapshot

class FakeMT5:
    ACCOUNT_TRADE_MODE_REAL=2
    ACCOUNT_TRADE_MODE_DEMO=0
    def __init__(self,mode=0,connected=True):
        self.mode=mode; self.connected=connected
    def terminal_info(self):
        return SimpleNamespace(company="Broker Company",name="MetaTrader 5",connected=self.connected,trade_allowed=True)
    def account_info(self):
        return SimpleNamespace(server="ExactBroker-Demo",trade_mode=self.mode,trade_allowed=True,currency="USD",leverage=100)
    def symbol_info(self,name):
        return SimpleNamespace(point=0.00001,trade_tick_size=0.00001,trade_tick_value_loss=1.0,
            digits=5,trade_stops_level=10,trade_freeze_level=5,volume_min=.01,volume_max=100,volume_step=.01)

def test_reads_exact_demo_server_from_connected_terminal():
    result=discover_connected_terminal(FakeMT5())
    assert result["server_name"]=="ExactBroker-Demo"
    assert result["environment"]=="demo" and result["read_only"] is True

def test_identifies_real_account_mode_without_logging_in():
    result=discover_connected_terminal(FakeMT5(mode=2))
    assert result["environment"]=="live"

def test_discovery_requires_terminal_and_account():
    class Disconnected(FakeMT5):
        def account_info(self): return None
        def last_error(self): return (-10004,"no connection")
    with pytest.raises(RuntimeError,match="No connected"):
        discover_connected_terminal(Disconnected())

def test_reads_actual_symbol_constraints():
    result=discover_symbol_spec("EURUSD",FakeMT5())
    assert result["stops_level_points"]==10
    assert result["tick_value_loss"]==1.0

def test_reads_exact_connected_market_snapshot_and_closed_bars():
    import datetime
    class MarketMT5(FakeMT5):
        TIMEFRAME_M15=15
        def symbol_select(self,name,enabled): return True
        def symbol_info_tick(self,name): return SimpleNamespace(bid=1.1,ask=1.1001)
        def copy_rates_from_pos(self,name,tf,start,count):
            base=1735689600
            return [{"time":base+i*900,"open":1.1,"high":1.101,"low":1.099,
                     "close":1.1005,"tick_volume":100} for i in range(30)]
    result=discover_market_snapshot("EURUSD",timeframe="M15",bars=30,mt5=MarketMT5())
    assert result["terminal"]["server_name"]=="ExactBroker-Demo"
    assert result["bars_are_closed"] is True and result["read_only"] is True
    assert len(result["candles"])==30 and result["spread_points"]==pytest.approx(10)
    assert result["broker"]["stops_level_points"]==10

def test_snapshot_rejects_unsupported_timeframe_and_short_history():
    with pytest.raises(ValueError,match="unsupported timeframe"):
        discover_market_snapshot("EURUSD",timeframe="M2",mt5=FakeMT5())
