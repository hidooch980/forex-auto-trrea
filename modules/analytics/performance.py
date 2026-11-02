"""Auditable signal-performance and market-sentiment calculations.

Only completed, realized trades belong in signal-performance statistics.
No network/provider integration or synthetic sample data is included here.
"""
from __future__ import annotations

from collections import defaultdict
from math import isfinite
from typing import Iterable, Mapping

FEAR_GREED_WEIGHTS = {
    "momentum": 0.25,
    "market_breadth": 0.25,
    "volatility": 0.25,
    "safe_haven_demand": 0.25,
}


def _number(value, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def summarize_closed_trades(trades: Iterable[Mapping]) -> dict:
    """Aggregate realized net PnL; open/cancelled rows are never counted."""
    rows = []
    seen_ids = set()
    for trade in trades:
        if not isinstance(trade, Mapping):
            raise ValueError("each trade must be a mapping")
        if str(trade.get("status", "")).lower() not in {"closed", "completed"}:
            continue
        symbol = str(trade.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("closed trade requires a symbol")
        trade_id = trade.get("trade_id")
        if trade_id is not None:
            key = str(trade_id)
            if key in seen_ids:
                raise ValueError(f"duplicate closed trade id: {key}")
            seen_ids.add(key)
        pnl = _number(trade.get("net_profit"), "net_profit")
        rows.append((symbol, pnl))

    if not rows:
        return {
            "available": False, "total_closed": 0, "wins": 0, "losses": 0,
            "win_rate_pct": None, "average_profit": None, "net_profit": None,
            "profit_factor": None, "symbols": [], "heatmap": [],
        }

    wins = [pnl for _, pnl in rows if pnl > 0]
    losses = [pnl for _, pnl in rows if pnl < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    grouped = defaultdict(list)
    for symbol, pnl in rows:
        grouped[symbol].append(pnl)

    rankings = []
    for symbol, values in grouped.items():
        positive = sum(x for x in values if x > 0)
        negative = abs(sum(x for x in values if x < 0))
        rankings.append({
            "symbol": symbol,
            "closed_trades": len(values),
            "win_rate_pct": round(100 * sum(x > 0 for x in values) / len(values), 2),
            "average_profit": round(sum(values) / len(values), 8),
            "net_profit": round(sum(values), 8),
            "profit_factor": round(positive / negative, 4) if negative else (None if positive == 0 else "inf"),
        })
    rankings.sort(key=lambda row: (row["average_profit"], row["net_profit"], row["symbol"]), reverse=True)

    heatmap = [{
        "symbol": row["symbol"],
        "average_profit": row["average_profit"],
        "net_profit": row["net_profit"],
        "closed_trades": row["closed_trades"],
        "performance": "positive" if row["average_profit"] > 0 else ("negative" if row["average_profit"] < 0 else "neutral"),
    } for row in rankings]

    return {
        "available": True,
        "total_closed": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(rows), 2),
        "average_profit": round(sum(pnl for _, pnl in rows) / len(rows), 8),
        "net_profit": round(sum(pnl for _, pnl in rows), 8),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else (None if not gross_profit else "inf"),
        "symbols": rankings,
        "heatmap": heatmap,
    }


def calculate_fear_greed(components: Mapping[str, float]) -> dict:
    """Weighted 0-100 index; each component must be supplied by a live provider."""
    if set(components) != set(FEAR_GREED_WEIGHTS):
        missing = sorted(set(FEAR_GREED_WEIGHTS) - set(components))
        extra = sorted(set(components) - set(FEAR_GREED_WEIGHTS))
        raise ValueError(f"fear/greed components mismatch; missing={missing}, extra={extra}")
    normalized = {}
    for name in FEAR_GREED_WEIGHTS:
        value = _number(components[name], name)
        if not 0 <= value <= 100:
            raise ValueError(f"{name} must be between 0 and 100")
        normalized[name] = value
    score = round(sum(normalized[k] * FEAR_GREED_WEIGHTS[k] for k in FEAR_GREED_WEIGHTS), 2)
    if score < 20:
        label = "extreme_fear"
    elif score < 40:
        label = "fear"
    elif score < 60:
        label = "neutral"
    elif score < 80:
        label = "greed"
    else:
        label = "extreme_greed"
    return {"available": True, "score": score, "label": label,
            "components": normalized, "weights": dict(FEAR_GREED_WEIGHTS)}


def build_market_heatmap(snapshots: Iterable[Mapping]) -> list[dict]:
    """Normalize provider snapshots for a live market map; no price inference."""
    result = []
    seen = set()
    for item in snapshots:
        symbol = str(item.get("symbol", "")).strip().upper()
        if not symbol or symbol in seen:
            raise ValueError("market snapshots require unique non-empty symbols")
        seen.add(symbol)
        change = _number(item.get("change_pct"), "change_pct")
        result.append({"symbol": symbol, "change_pct": round(change, 6),
                       "direction": "up" if change > 0 else ("down" if change < 0 else "flat")})
    result.sort(key=lambda row: row["change_pct"], reverse=True)
    return result
