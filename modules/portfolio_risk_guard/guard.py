"""Cross-market portfolio risk gate for large, long/short books.

The evaluator is deterministic and fail-closed. It aggregates LONG and SHORT
risk as gross risk (never nets hedges), and does not execute orders.
All risk percentages are percentage points of current equity.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence


@dataclass(frozen=True)
class Position:
    market: str                 # forex, metals, crypto_spot, crypto_futures, indices, equities
    instrument: str
    side: str                   # long or short
    notional_usd: float
    stop_risk_usd: float
    margin_usd: float
    liquidity_usd_1pct: float   # estimated executable depth within 1% of mid
    spread_bps: float
    data_valid: bool = True


@dataclass(frozen=True)
class PortfolioSnapshot:
    equity_usd: float
    positions: Sequence[Position]
    emergency_stop: bool = False
    market_data_valid: bool = True


@dataclass(frozen=True)
class PortfolioLimits:
    max_total_open_risk_pct: float = 2.0
    max_market_open_risk_pct: float = 1.0
    max_gross_leverage: float = 3.0
    max_margin_usage_pct: float = 35.0
    max_instrument_concentration_pct: float = 25.0
    max_order_liquidity_participation_pct: float = 5.0
    max_spread_bps: float = 30.0


@dataclass(frozen=True)
class TradeIntent:
    market: str
    instrument: str
    side: str
    notional_usd: float
    stop_risk_usd: float
    margin_usd: float
    liquidity_usd_1pct: float
    spread_bps: float
    stop_loss_present: bool = True
    market_data_valid: bool = True


@dataclass(frozen=True)
class PortfolioDecision:
    approved: bool
    reasons: tuple[str, ...]
    total_open_risk_pct: float
    market_open_risk_pct: float
    gross_leverage: float
    margin_usage_pct: float
    instrument_concentration_pct: float
    order_liquidity_participation_pct: float


def _number(name: str, value: float, *, positive: bool = False) -> None:
    if not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise ValueError(f"{name} must be finite numeric")
    if value < 0 or (positive and value <= 0):
        raise ValueError(f"{name} is outside the allowed range")


def evaluate_portfolio(
    snapshot: PortfolioSnapshot,
    trade: TradeIntent,
    limits: PortfolioLimits = PortfolioLimits(),
) -> PortfolioDecision:
    """Evaluate a proposed order against the whole cross-market book."""
    _number("equity_usd", snapshot.equity_usd, positive=True)
    reasons: list[str] = []
    if snapshot.emergency_stop:
        reasons.append("portfolio_emergency_stop")
    if not snapshot.market_data_valid or not trade.market_data_valid:
        reasons.append("portfolio_or_order_market_data_invalid")
    if not trade.stop_loss_present:
        reasons.append("stop_loss_required")

    def validate_position(p: Position | TradeIntent, label: str) -> None:
        if not p.market or not p.instrument:
            raise ValueError(f"{label} market and instrument are required")
        if p.side not in {"long", "short"}:
            raise ValueError(f"{label} side must be long or short")
        for field in ("notional_usd", "stop_risk_usd", "margin_usd", "liquidity_usd_1pct", "spread_bps"):
            _number(f"{label}.{field}", getattr(p, field))
        if p.notional_usd <= 0 or p.liquidity_usd_1pct <= 0:
            raise ValueError(f"{label} notional and liquidity capacity must be positive")
        if not p.data_valid if isinstance(p, Position) else not p.market_data_valid:
            reasons.append(f"{label}_data_invalid")

    gross_notional = 0.0
    margin = 0.0
    total_risk = 0.0
    market_risk: dict[str, float] = {}
    instrument_notional: dict[str, float] = {}
    for index, position in enumerate(snapshot.positions):
        validate_position(position, f"position_{index}")
        gross_notional += position.notional_usd
        margin += position.margin_usd
        total_risk += position.stop_risk_usd
        market_risk[position.market] = market_risk.get(position.market, 0.0) + position.stop_risk_usd
        key = position.instrument.upper()
        instrument_notional[key] = instrument_notional.get(key, 0.0) + position.notional_usd

    validate_position(trade, "proposed_order")
    gross_notional += trade.notional_usd
    margin += trade.margin_usd
    total_risk += trade.stop_risk_usd
    market_risk[trade.market] = market_risk.get(trade.market, 0.0) + trade.stop_risk_usd
    instrument_key = trade.instrument.upper()
    instrument_notional[instrument_key] = instrument_notional.get(instrument_key, 0.0) + trade.notional_usd

    total_risk_pct = total_risk / snapshot.equity_usd * 100.0
    market_risk_pct = market_risk[trade.market] / snapshot.equity_usd * 100.0
    gross_leverage = gross_notional / snapshot.equity_usd
    margin_usage_pct = margin / snapshot.equity_usd * 100.0
    concentration_pct = instrument_notional[instrument_key] / snapshot.equity_usd * 100.0
    liquidity_participation_pct = trade.notional_usd / trade.liquidity_usd_1pct * 100.0

    if total_risk_pct > limits.max_total_open_risk_pct:
        reasons.append("total_portfolio_open_risk_limit")
    if market_risk_pct > limits.max_market_open_risk_pct:
        reasons.append("market_open_risk_limit")
    if gross_leverage > limits.max_gross_leverage:
        reasons.append("gross_leverage_limit")
    if margin_usage_pct > limits.max_margin_usage_pct:
        reasons.append("margin_usage_limit")
    if concentration_pct > limits.max_instrument_concentration_pct:
        reasons.append("instrument_concentration_limit")
    if liquidity_participation_pct > limits.max_order_liquidity_participation_pct:
        reasons.append("order_too_large_for_visible_liquidity")
    if trade.spread_bps > limits.max_spread_bps:
        reasons.append("spread_limit_exceeded")

    return PortfolioDecision(
        approved=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
        total_open_risk_pct=total_risk_pct,
        market_open_risk_pct=market_risk_pct,
        gross_leverage=gross_leverage,
        margin_usage_pct=margin_usage_pct,
        instrument_concentration_pct=concentration_pct,
        order_liquidity_participation_pct=liquidity_participation_pct,
    )
