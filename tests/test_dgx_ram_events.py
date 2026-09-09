#!/usr/bin/env python3
"""Tests for DGX RAM event triggers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dgx_ram_events as events  # noqa: E402


class TestDgxRamEvents(unittest.TestCase):
    def test_mode_hold_below_trim(self) -> None:
        with mock.patch.object(events, "trim_gb", return_value=100.0):
            with mock.patch.object(events, "pressure_gb", return_value=110.0):
                with mock.patch.object(events, "emergency_gb", return_value=120.0):
                    with mock.patch.object(events.budget, "footprint_gb", return_value=95.0):
                        self.assertEqual(events.ram_mode(), "hold")

    def test_mode_trim_at_100(self) -> None:
        with mock.patch.object(events, "trim_gb", return_value=100.0):
            with mock.patch.object(events, "pressure_gb", return_value=110.0):
                with mock.patch.object(events, "emergency_gb", return_value=120.0):
                    with mock.patch.object(events.budget, "footprint_gb", return_value=100.0):
                        self.assertEqual(events.ram_mode(), "trim")

    def test_mode_pressure_at_110(self) -> None:
        with mock.patch.object(events, "trim_gb", return_value=100.0):
            with mock.patch.object(events, "pressure_gb", return_value=110.0):
                with mock.patch.object(events, "emergency_gb", return_value=120.0):
                    with mock.patch.object(events.budget, "footprint_gb", return_value=112.0):
                        self.assertEqual(events.ram_mode(), "pressure")

    def test_mode_emergency_at_120(self) -> None:
        with mock.patch.object(events, "trim_gb", return_value=100.0):
            with mock.patch.object(events, "pressure_gb", return_value=110.0):
                with mock.patch.object(events, "emergency_gb", return_value=120.0):
                    with mock.patch.object(events.budget, "footprint_gb", return_value=121.0):
                        self.assertEqual(events.ram_mode(), "emergency")

    def test_agent_cap_scales_with_mode(self) -> None:
        with mock.patch.object(events, "agent_cap_for_mode", side_effect=lambda m: {"hold": 48, "trim": 36, "pressure": 12, "emergency": 4}[m]):
            with mock.patch.object(events, "ram_mode", return_value="pressure"):
                self.assertEqual(events.ram_agent_cap(), 12)

    def test_dispatch_blocked_in_emergency(self) -> None:
        stats = {"footprint_gb": 125.0, "avail_gb": 1.0, "total_gb": 121.7, "used_avail_gb": 120.0}
        with mock.patch.object(events, "ram_mode", return_value="emergency"):
            self.assertFalse(events.dispatch_allowed(stats=stats))

    def test_dispatch_allowed_in_hold_with_headroom(self) -> None:
        stats = {"footprint_gb": 90.0, "avail_gb": 30.0, "total_gb": 121.7, "used_avail_gb": 91.0}
        with mock.patch.object(events, "ram_mode", return_value="hold"):
            with mock.patch.object(events, "target_gb", return_value=100.0):
                self.assertTrue(events.dispatch_allowed(stats=stats))

    def test_agent_cap_hold_clamped_to_max_parallel_peers(self) -> None:
        """local.json may say agent_cap_hold=48 while pool is 8 — clamp wins."""
        with mock.patch.object(events, "_cfg", return_value={"agent_cap_hold": 48, "agent_cap_trim": 36}):
            with mock.patch.object(events.auto, "max_parallel_peers", return_value=8):
                self.assertEqual(events.agent_cap_for_mode("hold"), 8)
                self.assertEqual(events.agent_cap_for_mode("trim"), 8)

    def test_agent_cap_hold_respects_lower_config(self) -> None:
        with mock.patch.object(events, "_cfg", return_value={"agent_cap_hold": 4, "agent_cap_trim": 2}):
            with mock.patch.object(events.auto, "max_parallel_peers", return_value=8):
                self.assertEqual(events.agent_cap_for_mode("hold"), 4)
                self.assertEqual(events.agent_cap_for_mode("trim"), 2)


if __name__ == "__main__":
    unittest.main()
