from pydantic import BaseModel
from typing import List

class AppConfig(BaseModel):
    account_balance_assumption: float = 500.0
    fx_risk_fraction: float = 0.0025
    gold_risk_fraction: float = 0.001
    daily_loss_limit: float = 0.01
    max_positions_total: int = 2
    max_gold_positions: int = 1
    news_filter_enabled: bool = True
    news_fail_closed: bool = True
    live_trading_enabled: bool = False
    symbols: List[str] = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "EURJPY", "XAUUSD"]
    emergency_stop: bool = True
