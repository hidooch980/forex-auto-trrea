import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from modules.master_brain.signal_bridge import publish_decision, verify_signal_line


SECRET = "test-bridge-secret-with-at-least-32-bytes-long"


@dataclass
class Decision:
    symbol: str = "EURUSD"
    action: str = "BUY"
    confidence: float = 0.82
    approved: bool = True


class SignalBridgeTests(unittest.TestCase):
    def test_publish_and_verify_signed_directional_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = publish_decision(
                Decision(), common_files_dir=directory, secret=SECRET,
                sl_points=150, now=1_800_000_000,
            )
            self.assertEqual(path, Path(directory) / "ForexAI_Bridge" / "EURUSD.signal")
            parsed = verify_signal_line(
                path.read_text(encoding="ascii"), SECRET,
                now=1_800_000_010, max_age_seconds=30,
            )
            self.assertEqual(parsed["action"], "BUY")
            self.assertTrue(parsed["approved"])
            self.assertEqual(parsed["sl_points"], 150)

    def test_signature_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = publish_decision(
                Decision(), common_files_dir=directory, secret=SECRET,
                sl_points=150, now=1_800_000_000,
            )
            line = path.read_text(encoding="ascii").replace("|BUY|", "|SELL|")
            with self.assertRaisesRegex(ValueError, "signature"):
                verify_signal_line(line, SECRET, now=1_800_000_010)

    def test_stale_and_future_messages_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = publish_decision(
                Decision(), common_files_dir=directory, secret=SECRET,
                sl_points=150, now=1_800_000_000,
            )
            line = path.read_text(encoding="ascii")
            with self.assertRaisesRegex(ValueError, "stale or future"):
                verify_signal_line(line, SECRET, now=1_800_000_040)
            with self.assertRaisesRegex(ValueError, "stale or future"):
                verify_signal_line(line, SECRET, now=1_799_999_999)

    def test_hold_overwrites_previous_directional_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = publish_decision(
                Decision(), common_files_dir=directory, secret=SECRET,
                sl_points=150, now=1_800_000_000,
            )
            hold = Decision(action="HOLD", confidence=0.0, approved=False)
            publish_decision(
                hold, common_files_dir=directory, secret=SECRET,
                now=1_800_000_001,
            )
            parsed = verify_signal_line(
                path.read_text(encoding="ascii"), SECRET,
                now=1_800_000_002,
            )
            self.assertEqual(parsed["action"], "HOLD")
            self.assertFalse(parsed["approved"])
            self.assertEqual(parsed["sl_points"], 0)

    def test_directional_signal_requires_stop_and_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "positive sl_points"):
                publish_decision(
                    Decision(), common_files_dir=directory, secret=SECRET,
                    sl_points=0, now=1_800_000_000,
                )


if __name__ == "__main__":
    unittest.main()
