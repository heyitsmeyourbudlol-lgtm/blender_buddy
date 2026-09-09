#!/usr/bin/env python3
"""Tests for DGX resource poll."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dgx_resource_poll as poll  # noqa: E402


class TestDgxResourcePoll(unittest.TestCase):
    def test_snapshot_includes_priority_fields(self) -> None:
        with mock.patch.object(
            poll.rp,
            "snapshot",
            return_value={"beeping": False, "ram": {"mode": "hold"}, "gpu": {"mode": "hold"}},
        ):
            snap = poll.snapshot()
        self.assertIn("poll_enabled", snap)
        self.assertIn("interval_sec", snap)

    def test_poll_once_writes_latest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            latest = Path(tmp) / "latest.json"
            alert = Path(tmp) / "alert.json"
            signal = Path(tmp) / "peer-turn.signal"
            with (
                mock.patch.object(poll, "LATEST_PATH", latest),
                mock.patch.object(poll, "ALERT_PATH", alert),
                mock.patch.object(poll, "SIGNAL_PATH", signal),
                mock.patch.object(poll, "LOG_PATH", Path(tmp) / "poll.log"),
                mock.patch.object(
                    poll.rp,
                    "snapshot",
                    return_value={
                        "beeping": True,
                        "development_allowed": False,
                        "worst_mode": "trim",
                        "ram": {"mode": "trim", "footprint_gb": 105},
                        "gpu": {"mode": "hold", "gpu_util_pct": 85},
                    },
                ),
                mock.patch.object(
                    poll.rp,
                    "handle_beep",
                    return_value={
                        "beeping": True,
                        "development_allowed": False,
                        "worst_mode": "trim",
                        "transition": True,
                        "ram": {"mode": "trim"},
                        "gpu": {"mode": "hold"},
                    },
                ),
                mock.patch.object(poll, "write_latest", return_value=True),
                mock.patch.object(poll, "poke_peer_on_transition", return_value=True),
                mock.patch.object(poll, "poke_peer_on_beep", return_value=True),
            ):
                report = poll.poll_once(log_fn=lambda _m: None)
            self.assertTrue(latest.is_file())
            self.assertTrue(alert.is_file())
            self.assertTrue(report.get("alert_written"))
            payload = json.loads(latest.read_text())
            self.assertTrue(payload["beeping"])

    def test_poll_once_clears_alert_when_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            alert = Path(tmp) / "alert.json"
            alert.write_text(json.dumps({"beeping": True}), encoding="utf-8")
            with (
                mock.patch.object(poll, "LATEST_PATH", Path(tmp) / "latest.json"),
                mock.patch.object(poll, "ALERT_PATH", alert),
                mock.patch.object(poll, "SIGNAL_PATH", Path(tmp) / "signal"),
                mock.patch.object(poll, "LOG_PATH", Path(tmp) / "poll.log"),
                mock.patch.object(
                    poll.rp,
                    "snapshot",
                    return_value={"beeping": False, "ram": {"mode": "hold"}, "gpu": {"mode": "hold"}},
                ),
                mock.patch.object(
                    poll.rp,
                    "handle_beep",
                    return_value={
                        "beeping": False,
                        "development_allowed": True,
                        "transition": True,
                        "ram": {"mode": "hold"},
                        "gpu": {"mode": "hold"},
                    },
                ),
                mock.patch.object(poll, "write_latest", return_value=True),
                mock.patch.object(poll, "poke_peer_on_transition", return_value=False),
            ):
                poll.poll_once(log_fn=lambda _m: None)
            cleared = json.loads(alert.read_text())
            self.assertFalse(cleared["beeping"])
            self.assertEqual(cleared["reason"], "cleared")


if __name__ == "__main__":
    unittest.main()
