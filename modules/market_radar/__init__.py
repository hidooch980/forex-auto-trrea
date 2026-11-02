"""Fail-closed, execution-neutral market radar."""
from .engine import Candle, RadarResult, analyze_market
__all__ = ["Candle", "RadarResult", "analyze_market"]
