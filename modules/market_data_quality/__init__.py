"""Deterministic market-data quality gates for MT5 and external feeds."""
from .quality import QualityReport, validate_bars

__all__ = ["QualityReport", "validate_bars"]
