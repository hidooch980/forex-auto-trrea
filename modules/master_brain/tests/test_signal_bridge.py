from dataclasses import dataclass
from pathlib import Path

import pytest

from modules.master_brain.signal_bridge import publish_decision, verify_signal_line


SECRET = "test-bridge-secret-with-at-least-32-bytes-long"


@dataclass
class Decision:
    symbol: str = "EURUSD"
    action: str = "BUY"
    confidence: float = 0.82
    approved: bool = True


def test_publish_and_verify_signed_directional_signal(tmp_path):
    path = publish_decision(
        Decision(), common_files_dir=tmp_path, secret=SECRET,
        sl_points=150, now=1_800_000_000,
    )
    assert path == tmp_path / "ForexAI_Bridge" / "EURUSD.signal"
    parsed = verify_signal_line(
        path.read_text(encoding="ascii"), SECRET,
        now=1_800_000_010, max_age_seconds=30,
    )
    assert parsed["action"] == "BUY"
    assert parsed["approved"] is True
    assert parsed["sl_points"] == 150


def test_signature_tampering_is_rejected(tmp_path):
    path = publish_decision(
        Decision(), common_files_dir=tmp_path, secret=SECRET,
        sl_points=150, now=1_800_000_000,
    )
    line = path.read_text(encoding="ascii").replace("|BUY|", "|SELL|")
    with pytest.raises(ValueError, match="signature"):
        verify_signal_line(line, SECRET, now=1_800_000_010)


def test_stale_and_future_messages_are_rejected(tmp_path):
    path = publish_decision(
        Decision(), common_files_dir=tmp_path, secret=SECRET,
        sl_points=150, now=1_800_000_000,
    )
    line = path.read_text(encoding="ascii")
    with pytest.raises(ValueError, match="stale or future"):
        verify_signal_line(line, SECRET, now=1_800_000_040)
    with pytest.raises(ValueError, match="stale or future"):
        verify_signal_line(line, SECRET, now=1_799_999_999)


def test_hold_overwrites_previous_directional_signal(tmp_path):
    path = publish_decision(
        Decision(), common_files_dir=tmp_path, secret=SECRET,
        sl_points=150, now=1_800_000_000,
    )
    hold = Decision(action="HOLD", confidence=0.0, approved=False)
    publish_decision(
        hold, common_files_dir=tmp_path, secret=SECRET,
        now=1_800_000_001,
    )
    parsed = verify_signal_line(
        path.read_text(encoding="ascii"), SECRET,
        now=1_800_000_002,
    )
    assert parsed["action"] == "HOLD"
    assert parsed["approved"] is False
    assert parsed["sl_points"] == 0


def test_directional_signal_requires_stop_and_approval(tmp_path):
    with pytest.raises(ValueError, match="positive sl_points"):
        publish_decision(
            Decision(), common_files_dir=tmp_path, secret=SECRET,
            sl_points=0, now=1_800_000_000,
        )
