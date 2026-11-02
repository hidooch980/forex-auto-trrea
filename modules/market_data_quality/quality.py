"""Fail-closed OHLCV quality checks.

Input timestamps are interpreted as UTC when numeric (Unix seconds) or when
timezone-aware datetimes are supplied. Naive datetimes are rejected. The
validator never silently sorts, deduplicates, fills, or repairs source data.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class QualityReport:
    valid: bool
    rows: int
    duplicate_timestamps: int
    out_of_order_rows: int
    invalid_ohlc_rows: int
    non_finite_rows: int
    negative_volume_rows: int
    negative_spread_rows: int
    stale: bool
    future_timestamps: int
    gap_count: int
    latest_bar_utc: str | None
    age_seconds: float | None
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _records(rows: Iterable[Any]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        if isinstance(row, Mapping):
            result.append(dict(row))
            continue
        names = getattr(getattr(row, "dtype", None), "names", None)
        if names:
            result.append({name: row[name].item() if hasattr(row[name], "item") else row[name] for name in names})
            continue
        raise ValueError("each bar must be a mapping or a structured MT5 rate row")
    return result


def _timestamp(value: Any) -> datetime:
    if isinstance(value, bool):
        raise ValueError("boolean timestamp is invalid")
    if isinstance(value, (int, float)):
        if not isfinite(float(value)):
            raise ValueError("timestamp must be finite")
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("bar timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)
    raise ValueError("timestamp must be Unix seconds or timezone-aware datetime")


def validate_bars(
    rows: Iterable[Any],
    *,
    as_of: datetime | None = None,
    max_age_seconds: float = 180.0,
    expected_interval_seconds: int | None = None,
    gap_tolerance: float = 1.5,
    require_volume: bool = False,
) -> QualityReport:
    """Validate completed bars. Empty, stale, malformed or unordered data fails."""
    records = _records(rows)
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    now = now.astimezone(timezone.utc)
    if max_age_seconds <= 0 or not isfinite(max_age_seconds):
        raise ValueError("max_age_seconds must be positive and finite")
    if expected_interval_seconds is not None and expected_interval_seconds <= 0:
        raise ValueError("expected_interval_seconds must be positive")
    if gap_tolerance < 1 or not isfinite(gap_tolerance):
        raise ValueError("gap_tolerance must be finite and >= 1")

    errors: list[str] = []
    times: list[datetime] = []
    duplicate_count = 0
    out_of_order = 0
    invalid_ohlc = 0
    non_finite = 0
    negative_volume = 0
    negative_spread = 0
    future = 0

    if not records:
        errors.append("no_bars_received")

    required = {"time", "open", "high", "low", "close"}
    for index, row in enumerate(records):
        missing = required - set(row)
        if missing:
            errors.append(f"row_{index}_missing_fields:{','.join(sorted(missing))}")
            continue
        try:
            ts = _timestamp(row["time"])
            times.append(ts)
            if ts > now:
                future += 1
        except (ValueError, OverflowError, OSError):
            errors.append(f"row_{index}_invalid_timestamp")
            continue

        values = []
        try:
            for field in ("open", "high", "low", "close"):
                value = float(row[field])
                if not isfinite(value):
                    raise ValueError
                values.append(value)
            o, h, low, c = values
            if min(values) <= 0 or h < max(o, c, low) or low > min(o, c, h):
                invalid_ohlc += 1
        except (TypeError, ValueError, OverflowError):
            non_finite += 1

        if "tick_volume" in row:
            try:
                if float(row["tick_volume"]) < 0:
                    negative_volume += 1
            except (TypeError, ValueError):
                negative_volume += 1
        elif require_volume:
            errors.append(f"row_{index}_missing_tick_volume")

        if "spread" in row:
            try:
                if float(row["spread"]) < 0:
                    negative_spread += 1
            except (TypeError, ValueError):
                negative_spread += 1

    if len(times) == len(records):
        seen = set()
        for ts in times:
            if ts in seen:
                duplicate_count += 1
            seen.add(ts)
        out_of_order = sum(times[i] < times[i - 1] for i in range(1, len(times)))
    else:
        errors.append("one_or_more_timestamps_unreadable")

    gap_count = 0
    if expected_interval_seconds and len(times) > 1:
        chronological = sorted(set(times))
        gap_count = sum(
            (chronological[i] - chronological[i - 1]).total_seconds()
            > expected_interval_seconds * gap_tolerance
            for i in range(1, len(chronological))
        )

    latest = max(times) if times else None
    age = (now - latest).total_seconds() if latest else None
    stale = age is None or age > max_age_seconds
    if stale:
        errors.append("latest_bar_stale_or_missing")
    if future:
        errors.append("future_timestamps_present")
    if duplicate_count:
        errors.append("duplicate_timestamps_present")
    if out_of_order:
        errors.append("bars_not_chronological")
    if invalid_ohlc:
        errors.append("invalid_ohlc_relationship")
    if non_finite:
        errors.append("non_finite_ohlc_values")
    if negative_volume:
        errors.append("negative_or_invalid_tick_volume")
    if negative_spread:
        errors.append("negative_or_invalid_spread")
    if gap_count:
        errors.append("bar_gaps_detected")

    valid = not errors
    return QualityReport(
        valid=valid, rows=len(records), duplicate_timestamps=duplicate_count,
        out_of_order_rows=out_of_order, invalid_ohlc_rows=invalid_ohlc,
        non_finite_rows=non_finite, negative_volume_rows=negative_volume,
        negative_spread_rows=negative_spread, stale=stale,
        future_timestamps=future, gap_count=gap_count,
        latest_bar_utc=latest.isoformat() if latest else None,
        age_seconds=round(age, 3) if age is not None else None,
        errors=tuple(errors),
    )
