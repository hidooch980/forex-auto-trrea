"""Read-only MT5 adapter. No order_send import or call exists in this module."""
def connect():
    try:
        import MetaTrader5 as mt5
    except ImportError as e:
        raise RuntimeError("Install MetaTrader5 on supported Windows environment") from e
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    return mt5

def snapshot(symbol="EURUSD", timeframe_name="TIMEFRAME_M1", bars=300):
    mt5=connect()
    try:
        tf=getattr(mt5,timeframe_name)
        rates=mt5.copy_rates_from_pos(symbol,tf,0,bars)
        if rates is None: raise RuntimeError(f"copy_rates failed: {mt5.last_error()}")
        info=mt5.symbol_info(symbol)
        tick=mt5.symbol_info_tick(symbol)
        return {"rates": rates, "point": info.point if info else None,
                "digits": info.digits if info else None,
                "bid": tick.bid if tick else None, "ask": tick.ask if tick else None}
    finally:
        mt5.shutdown()

def send_order(*args, **kwargs):
    raise RuntimeError("Trading disabled: this adapter is read-only; order execution is not implemented.")
