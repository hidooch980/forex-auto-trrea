"""Strict output contract for research-only market agents.

Agent output is untrusted input. Validation checks structure, provenance and
freshness; it does not treat an LLM confidence score as calibrated probability.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Mapping


ALLOWED_STANCES = {"bullish", "bearish", "neutral", "unavailable"}


@dataclass(frozen=True)
class AgentOutput:
    agent_id: str
    schema_version: str
    scope: str
    as_of: datetime
    source_ids: tuple[str, ...]
    data_quality: str
    confidence: float
    stance: str
    rationale: str
    invalidations: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["as_of"] = self.as_of.astimezone(timezone.utc).isoformat()
        return value


def validate_agent_output(
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
    max_age_seconds: float = 900.0,
    max_future_skew_seconds: float = 30.0,
    require_sources: bool = True,
) -> AgentOutput:
    """Validate one agent result; malformed or stale evidence is rejected."""
    if not isinstance(payload, Mapping):
        raise ValueError("agent output must be an object")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    current = current.astimezone(timezone.utc)
    if max_age_seconds <= 0 or not isfinite(max_age_seconds):
        raise ValueError("max_age_seconds must be positive and finite")

    required = {
        "agent_id", "schema_version", "scope", "as_of", "source_ids",
        "data_quality", "confidence", "stance", "rationale",
    }
    missing = required - set(payload)
    if missing:
        raise ValueError(f"missing agent output fields: {','.join(sorted(missing))}")

    def text_field(name: str) -> str:
        value = payload[name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be non-empty text")
        return value.strip()

    agent_id = text_field("agent_id")
    schema_version = text_field("schema_version")
    scope = text_field("scope")
    data_quality = text_field("data_quality").lower()
    rationale = text_field("rationale")
    if data_quality not in {"valid", "degraded", "invalid", "unknown"}:
        raise ValueError("data_quality must be valid, degraded, invalid or unknown")
    if data_quality != "valid":
        raise ValueError("agent output data quality is not valid")

    as_of = payload["as_of"]
    if isinstance(as_of, str):
        try:
            as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("as_of must be an ISO-8601 timestamp") from exc
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    as_of = as_of.astimezone(timezone.utc)
    age = (current - as_of).total_seconds()
    if age > max_age_seconds:
        raise ValueError("agent output is stale")
    if age < -max_future_skew_seconds:
        raise ValueError("agent output timestamp is in the future")

    sources = payload["source_ids"]
    if not isinstance(sources, (list, tuple, set)):
        raise ValueError("source_ids must be a list of source identifiers")
    source_ids = tuple(sorted({str(item).strip() for item in sources if str(item).strip()}))
    if require_sources and not source_ids:
        raise ValueError("at least one source_id is required")
    if len(source_ids) != len([item for item in sources if str(item).strip()]):
        raise ValueError("source_ids must be unique")

    try:
        confidence = float(payload["confidence"])
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be numeric") from exc
    if not isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be finite and between 0 and 1")

    stance = text_field("stance").lower()
    if stance not in ALLOWED_STANCES:
        raise ValueError(f"stance must be one of {sorted(ALLOWED_STANCES)}")
    if stance == "unavailable" and confidence != 0:
        raise ValueError("unavailable stance must have zero confidence")

    def text_tuple(name: str) -> tuple[str, ...]:
        values = payload.get(name, ())
        if not isinstance(values, (list, tuple, set)):
            raise ValueError(f"{name} must be a list of text values")
        normalized = tuple(str(item).strip() for item in values if str(item).strip())
        if len(normalized) != len(values):
            raise ValueError(f"{name} cannot contain empty values")
        return normalized

    return AgentOutput(
        agent_id=agent_id, schema_version=schema_version, scope=scope,
        as_of=as_of, source_ids=source_ids, data_quality=data_quality,
        confidence=confidence, stance=stance, rationale=rationale,
        invalidations=text_tuple("invalidations"),
        limitations=text_tuple("limitations"),
    )
