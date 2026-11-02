"""Read identity and symbol constraints from an already connected MT5 terminal.

Requires the official MetaTrader5 Python package and a logged-in terminal on
supported Windows. Never logs in, changes accounts, reads passwords or trades.
"""
from __future__ import annotations

def discover_connected_terminal(mt5=None):
    if mt5 is None:
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError("MetaTrader5 Python package is unavailable; run on the Windows host with MT5 installed") from exc
    terminal=mt5.terminal_info()
    account=mt5.account_info()
    if terminal is None or account is None:
        raise RuntimeError(f"No connected/logged-in MT5 terminal: {mt5.last_error()}")
    server=str(getattr(account,"server","") or "").strip()
    company=str(getattr(terminal,"company","") or "").strip()
    name=str(getattr(terminal,"name","") or "").strip()
    if not server:
        raise RuntimeError("Connected MT5 terminal did not report an account server")
    mode=getattr(account,"trade_mode",None)
    real=getattr(mt5,"ACCOUNT_TRADE_MODE_REAL",2)
    demo=getattr(mt5,"ACCOUNT_TRADE_MODE_DEMO",0)
    environment="live" if mode==real else "demo" if mode==demo else "unknown"
    return {
        "platform":"mt5",
        "server_name":server,
        "company":company,
        "terminal_name":name,
        "environment":environment,
        "connected":bool(getattr(terminal,"connected",False)),
        "trade_allowed":bool(getattr(terminal,"trade_allowed",False)),
        "account_trade_allowed":bool(getattr(account,"trade_allowed",False)),
        "currency":str(getattr(account,"currency","") or ""),
        "leverage":int(getattr(account,"leverage",0) or 0),
        "source":"connected_mt5_terminal",
        "read_only":True,
    }

def discover_symbol_spec(symbol: str, mt5=None):
    if mt5 is None:
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError("MetaTrader5 package is required on the connected Windows terminal host") from exc
    name=str(symbol or "").strip()
    if not name or len(name)>64:
        raise ValueError("symbol is required")
    info=mt5.symbol_info(name)
    if info is None:
        raise RuntimeError(f"Symbol unavailable in connected MT5 terminal: {name}")
    return {
        "symbol":name,"point":float(info.point),"tick_size":float(info.trade_tick_size),
        "tick_value_loss":float(getattr(info,"trade_tick_value_loss",0.0) or 0.0),
        "digits":int(info.digits),"stops_level_points":int(info.trade_stops_level),
        "freeze_level_points":int(info.trade_freeze_level),
        "volume_min":float(info.volume_min),"volume_max":float(info.volume_max),
        "volume_step":float(info.volume_step),
    }
