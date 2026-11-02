"""Authenticated file bridge publisher for the MT5 terminal.

The publisher accepts an already-evaluated Master Brain decision. It does not
create market data, specialist signals, or trading decisions.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Mapping

_SYMBOL_RE = re.compile(r"^[A-Z0-9._-]{3,32}$")
_VERSION = "FAI1"


def _secret_bytes(secret: str | bytes) -> bytes:
    value = secret.encode("utf-8") if isinstance(secret, str) else secret
    if not isinstance(value, bytes) or len(value) < 32:
        raise ValueError("bridge secret must contain at least 32 bytes")
    return value


def _canonical(fields: list[str]) -> bytes:
    return "|".join(fields).encode("utf-8")


def sign_fields(fields: list[str], secret: str | bytes) -> str:
    """Return a SHA-256 HMAC hex digest for the exact pipe-delimited fields."""
    return hmac.new(_secret_bytes(secret), _canonical(fields), hashlib.sha256).hexdigest()


def verify_signal_line(line: str, secret: str | bytes, *, now: int | None = None,
                       max_age_seconds: int = 30) -> dict:
    """Validate syntax, HMAC, freshness and field ranges; useful for bridge tests."""
    parts = line.strip().split("|")
    if len(parts) != 9 or parts[0] != _VERSION:
        raise ValueError("invalid bridge message format")
    version, symbol, action, confidence, sl_points, timestamp, approved, nonce, signature = parts
    if not _SYMBOL_RE.fullmatch(symbol):
        raise ValueError("invalid symbol")
    if action not in {"BUY", "SELL", "HOLD"}:
        raise ValueError("invalid action")
    if approved not in {"0", "1"}:
        raise ValueError("invalid approval flag")
    if not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise ValueError("invalid nonce")
    expected = sign_fields(parts[:-1], secret)
    if not hmac.compare_digest(signature, expected):
        raise ValueError("invalid bridge signature")
    try:
        confidence_value = float(confidence)
        stop_value = float(sl_points)
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise ValueError("invalid numeric bridge field") from exc
    if not 0.0 <= confidence_value <= 1.0:
        raise ValueError("confidence outside [0, 1]")
    if action in {"BUY", "SELL"} and (approved != "1" or stop_value <= 0):
        raise ValueError("directional signal must be approved and have a stop")
    if action == "HOLD" and approved != "0":
        raise ValueError("HOLD cannot be approved")
    current = int(time.time()) if now is None else int(now)
    if timestamp_value > current or current - timestamp_value > max_age_seconds:
        raise ValueError("stale or future bridge message")
    return {
        "symbol": symbol, "action": action, "confidence": confidence_value,
        "sl_points": stop_value, "timestamp": timestamp_value,
        "approved": approved == "1", "nonce": nonce,
    }


def publish_decision(decision, *, common_files_dir: str | Path,
                     secret: str | bytes, sl_points: float = 0,
                     now: int | None = None) -> Path:
    """Atomically publish one signed decision under MT5's Common\Files folder.

    HOLD decisions are published too, so an earlier directional signal is
    overwritten instead of remaining actionable until its TTL expires.
    """
    key = _secret_bytes(secret)
    symbol = str(decision.symbol).strip().upper()
    if not _SYMBOL_RE.fullmatch(symbol):
        raise ValueError("invalid symbol")
    action = str(getattr(decision.action, "value", decision.action)).upper()
    if action not in {"BUY", "SELL", "HOLD"}:
        raise ValueError("invalid decision action")
    approved = bool(decision.approved) and action in {"BUY", "SELL"}
    if action == "HOLD":
        approved = False
    confidence = float(decision.confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("decision confidence outside [0, 1]")
    stop = float(sl_points)
    if action in {"BUY", "SELL"} and (not approved or stop <= 0):
        raise ValueError("approved directional decision requires positive sl_points")
    if action == "HOLD":
        stop = 0.0

    timestamp = int(time.time()) if now is None else int(now)
    fields = [
        _VERSION, symbol, action, format(confidence, ".8f"),
        format(stop, ".4f"), str(timestamp), "1" if approved else "0",
        uuid.uuid4().hex,
    ]
    signature = hmac.new(key, _canonical(fields), hashlib.sha256).hexdigest()
    line = "|".join(fields + [signature]) + "\n"

    target_dir = Path(common_files_dir) / "ForexAI_Bridge"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{symbol}.signal"
    fd, temporary = tempfile.mkstemp(prefix=f".{symbol}.", suffix=".tmp", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        # MT5 opens the file briefly on each tick. Retry transient Windows
        # sharing violations while keeping the previous complete file intact.
        for attempt in range(10):
            try:
                os.replace(temporary, target)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.05)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return target
