#!/usr/bin/env python3
"""Tests for DGX resource priority."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dgx_resource_priority as rp  # noqa: E402


class TestDgxResourcePriority(unittest.TestCase):
    def test_beeping_when_ram_or_gpu_not_hold(self) -> None:
        with mock.patch.object(rp, "_read_poll_latest", return_value=None):
            with mock.patch.object(rp, "_ram_snapshot", return_value={"mode": "trim", "enabled": True}):
                with mock.patch.object(rp, "_gpu_snapshot", return_value={"mode": "hold", "enabled": True}):
                    self.assertTrue(rp.beeping())

    def test_not_beeping_when_both_hold(self) -> None:
        with mock.patch.object(rp, "_read_poll_latest", return_value=None):
            with mock.patch.object(rp, "_ram_snapshot", return_value={"mode": "hold", "enabled": True}):
                with mock.patch.object(rp, "_gpu_snapshot", return_value={"mode": "hold", "enabled": True}):
                    self.assertFalse(rp.beeping())

    def test_beeping_prefers_fresh_poll_latest(self) -> None:
        """Compression: guard hot path must not call live GPU/RAM when poll-latest is fresh."""
        with mock.patch.object(
            rp,
            "_read_poll_latest",
            return_value={"beeping": True, "worst_mode": "trim"},
        ):
            with mock.patch.object(rp, "_ram_snapshot") as ram:
                with mock.patch.object(rp, "_gpu_snapshot") as gpu:
                    self.assertTrue(rp.beeping())
                    ram.assert_not_called()
                    gpu.assert_not_called()

    def test_snapshot_force_live_bypasses_poll_latest(self) -> None:
        with mock.patch.object(
            rp,
            "_read_poll_latest",
            return_value={"beeping": True, "ram": {"mode": "trim"}, "gpu": {"mode": "hold"}},
        ):
            with mock.patch.object(rp, "_ram_snapshot", return_value={"mode": "hold", "enabled": True}):
                with mock.patch.object(rp, "_gpu_snapshot", return_value={"mode": "hold", "enabled": True}):
                    snap = rp.snapshot(force_live=True)
        self.assertFalse(snap["beeping"])
        self.assertEqual(snap["ram"]["mode"], "hold")

    def test_snapshot_reuses_fresh_poll_latest(self) -> None:
        cached = {
            "beeping": False,
            "development_allowed": True,
            "worst_mode": "hold",
            "ram": {"mode": "hold"},
            "gpu": {"mode": "hold"},
        }
        with mock.patch.object(rp, "_read_poll_latest", return_value=cached):
            with mock.patch.object(rp, "_gpu_snapshot") as gpu:
                snap = rp.snapshot()
                gpu.assert_not_called()
        self.assertEqual(snap["beeping"], False)
        self.assertEqual(snap["worst_mode"], "hold")

    def test_read_poll_latest_respects_ttl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resource-poll-latest.json"
            path.write_text(
                json.dumps({"beeping": False, "worst_mode": "hold"}),
                encoding="utf-8",
            )
            # Age the file past TTL
            old = time.time() - 120.0
            import os

            os.utime(path, (old, old))
            with mock.patch.object(rp, "_poll_latest_paths", return_value=[path]):
                with mock.patch.object(rp, "poll_latest_ttl_sec", return_value=45.0):
                    self.assertIsNone(rp._read_poll_latest())
            # Fresh file hits
            path.write_text(
                json.dumps({"beeping": True, "worst_mode": "pressure"}),
                encoding="utf-8",
            )
            with mock.patch.object(rp, "_poll_latest_paths", return_value=[path]):
                with mock.patch.object(rp, "poll_latest_ttl_sec", return_value=45.0):
                    hit = rp._read_poll_latest()
            self.assertIsNotNone(hit)
            self.assertTrue(hit["beeping"])

    def test_read_poll_latest_falls_through_stale_to_fresh_hub(self) -> None:
        """Compression: stale CONFIG_DIR file must not block hub poll hit."""
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "stale.json"
            fresh = Path(tmp) / "fresh.json"
            stale.write_text(json.dumps({"beeping": False}), encoding="utf-8")
            fresh.write_text(json.dumps({"beeping": True}), encoding="utf-8")
            import os

            os.utime(stale, (time.time() - 120.0, time.time() - 120.0))
            with mock.patch.object(rp, "_poll_latest_paths", return_value=[stale, fresh]):
                with mock.patch.object(rp, "poll_latest_ttl_sec", return_value=45.0):
                    hit = rp._read_poll_latest()
            self.assertIsNotNone(hit)
            self.assertTrue(hit["beeping"])

    def test_development_blocked_when_beeping(self) -> None:
        with mock.patch.object(rp, "beeping", return_value=True):
            with mock.patch.object(rp, "pause_development_when_beeping", return_value=True):
                self.assertFalse(rp.development_allowed())

    def test_worst_mode_picks_higher_severity(self) -> None:
        mode = rp.worst_mode(
            ram={"mode": "trim"},
            gpu={"mode": "emergency"},
        )
        self.assertEqual(mode, "emergency")

    def test_mechanical_fixes_pass_poll_gpu_snap(self) -> None:
        """COMPRESSION_POLL_GUARD_SKIP_NVML_2026_09_05 — poll gpu snap skips NVML CDLL."""
        poll_gpu = {"mode": "boost", "gpu_util_pct": 0.0, "effective_util_pct": 55.0}
        snap = {
            "beeping": True,
            "development_allowed": False,
            "worst_mode": "boost",
            "ram": {"mode": "hold"},
            "gpu": poll_gpu,
        }
        with mock.patch.dict("sys.modules", {"dgx_ram_events": mock.MagicMock(enabled=lambda: False)}):
            gev = mock.MagicMock()
            gev.enabled.return_value = True
            gev.handle_events.return_value = {"mode": "boost"}
            with mock.patch.dict("sys.modules", {"dgx_gpu_events": gev}):
                # Force re-import path inside _run_mechanical_fixes via patched modules
                report = rp._run_mechanical_fixes(log_fn=lambda _m: None, snap=snap)
        gev.handle_events.assert_called_once()
        kwargs = gev.handle_events.call_args.kwargs
        self.assertIs(kwargs.get("snap"), poll_gpu)
        self.assertEqual(report.get("gpu", {}).get("mode"), "boost")

    def test_handle_beep_passes_snap_to_mechanical(self) -> None:
        """Guard/beep path must forward poll-backed snap into mechanical fixes."""
        cached = {
            "beeping": True,
            "development_allowed": False,
            "worst_mode": "boost",
            "ram": {"mode": "hold", "footprint_gb": 22.0},
            "gpu": {"mode": "boost", "gpu_util_pct": 0.0, "effective_util_pct": 55.0},
        }
        with mock.patch.object(rp, "snapshot", return_value=dict(cached)):
            with mock.patch.object(rp, "_load_state", return_value={"beeping": True}):
                with mock.patch.object(rp, "_save_state"):
                    with mock.patch.object(rp, "_run_mechanical_fixes", return_value={}) as mech:
                        with mock.patch.object(rp, "kill_dev_agents_on_beep", return_value=False):
                            rp.handle_beep(log_fn=lambda _m: None)
        mech.assert_called_once()
        self.assertEqual(mech.call_args.kwargs.get("snap"), cached)

    def test_gpu_handle_events_reuses_snap_no_nvml(self) -> None:
        """Poll gpu snap must not call gpu_snapshot inside sustain override path."""
        import dgx_gpu_events as gev

        poll_gpu = {
            "mode": "boost",
            "gpu_util_pct": 0.0,
            "effective_util_pct": 55.0,
            "gpu_temp_c": 59.0,
            "gpu_unavailable": False,
        }
        with mock.patch.object(gev, "gpu_snapshot") as snap_fn:
            with mock.patch.object(gev, "_save_state"):
                with mock.patch.object(gev, "_load_state", return_value={"mode": "boost"}):
                    with mock.patch.object(gev, "OVERRIDE_PATH", Path(tempfile.mkdtemp()) / "ovr.json"):
                        report = gev.handle_events(
                            log_fn=lambda _m: None,
                            skip_cursor_agent=True,
                            snap=poll_gpu,
                        )
        snap_fn.assert_not_called()
        self.assertIn("write_sustain_override", report.get("actions") or [])


if __name__ == "__main__":
    unittest.main()
