import numpy as np
import pandas as pd

META = {"time", "symbol", "open", "high", "low", "close", "tick_volume", "spread"}

def load_frame(path):
    df = pd.read_csv(path, parse_dates=["time"])
    required = {"time", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    df = df.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    if df["time"].isna().any() or df["close"].isna().any():
        raise ValueError("Null time/close values are not allowed")
    return df

def make_features(df):
    """Backward-looking features only. Fit no scaler on future rows."""
    x = pd.DataFrame(index=df.index)
    close = df["close"].astype(float)
    ret = close.pct_change()
    for lag in (1, 2, 3, 5, 8, 13, 21):
        x[f"ret_{lag}"] = close.pct_change(lag)
    for w in (5, 10, 20, 50):
        x[f"vol_{w}"] = ret.rolling(w).std()
        x[f"mom_{w}"] = close / close.shift(w) - 1
        x[f"dist_sma_{w}"] = close / close.rolling(w).mean() - 1
    high_low = (df["high"] - df["low"]).astype(float)
    x["range_pct"] = high_low / close.replace(0, np.nan)
    x["body_pct"] = (df["close"] - df["open"]) / close.replace(0, np.nan)
    if "spread" in df:
        x["spread"] = df["spread"].astype(float)
    if "tick_volume" in df:
        x["log_tick_volume"] = np.log1p(df["tick_volume"].clip(lower=0))
    # cyclical time features, based on bar timestamp
    hour = df["time"].dt.hour
    dow = df["time"].dt.dayofweek
    x["hour_sin"] = np.sin(2*np.pi*hour/24)
    x["hour_cos"] = np.cos(2*np.pi*hour/24)
    x["dow_sin"] = np.sin(2*np.pi*dow/7)
    x["dow_cos"] = np.cos(2*np.pi*dow/7)
    return x.replace([np.inf, -np.inf], np.nan)

def make_labels(df, horizon=5, flat_threshold=0.001):
    future_return = df["close"].shift(-horizon) / df["close"] - 1
    # 0=down, 1=flat, 2=up
    y = np.where(future_return < -flat_threshold, 0,
        np.where(future_return > flat_threshold, 2, 1))
    y = pd.Series(y, index=df.index, dtype="int64")
    y.iloc[-horizon:] = np.nan
    return y
