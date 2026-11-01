from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

def daily_loss_locked(start_equity: float, current_equity: float, limit: float) -> bool:
    if start_equity <= 0:
        return True
    return current_equity <= start_equity * (1.0 - limit)

def news_guard(csv_path: str, symbol: str, now=None, enabled=True, fail_closed=True,
               before_minutes=45, after_minutes=30, max_age_hours=24):
    if not enabled:
        return False, "news filter disabled"
    p = Path(csv_path)
    if not p.exists():
        return fail_closed, "calendar unavailable"
    try:
        df = pd.read_csv(p)
        required = {"time", "currency", "impact", "title"}
        if not required.issubset(df.columns) or df.empty:
            raise ValueError("invalid or empty calendar")
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        if df["time"].isna().any():
            raise ValueError("invalid calendar timestamps")
        now = pd.Timestamp(now or datetime.now(timezone.utc))
        now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
        if (now - df["time"].max()).total_seconds() > max_age_hours * 3600:
            return fail_closed, "calendar stale"
        currencies = {symbol[:3], symbol[3:6]} if symbol != "XAUUSD" else {"USD"}
        high = df[(df["impact"].str.lower() == "high") &
                  (df["currency"].str.upper().isin(currencies))]
        for _, event in high.iterrows():
            minutes = (event["time"] - now).total_seconds() / 60
            if -after_minutes <= minutes <= before_minutes:
                return True, f'{event["currency"]}: {event["title"]}'
        return False, "no high-impact event in blackout window"
    except Exception as exc:
        return fail_closed, f"calendar error: {exc}"
