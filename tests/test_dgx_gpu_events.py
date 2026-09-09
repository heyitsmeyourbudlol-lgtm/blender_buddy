#!/usr/bin/env python3
"""Tests for DGX GPU event triggers + thermal scaling."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dgx_gpu_events as events  # noqa: E402


class TestDgxGpuEvents(unittest.TestCase):
    def test_mode_hold_when_hot(self) -> None:
        snap = {"gpu_util_pct": 50.0, "gpu_temp_c": 91.0}
        with mock.patch.object(events, "thermal_enabled", return_value=True):
            with mock.patch.object(events, "temp_critical_c", return_value=90.0):
                self.assertEqual(events.gpu_mode(snap=snap), "hold")
                self.assertTrue(events.over_max(snap=snap))

    def test_mode_boost_when_cool_and_underutilized(self) -> None:
        snap = {"gpu_util_pct": 65.0, "gpu_temp_c": 50.0}
        with mock.patch.object(events, "thermal_enabled", return_value=True):
            with mock.patch.object(events, "temp_cool_c", return_value=55.0):
                with mock.patch.object(events, "temp_hot_c", return_value=82.0):
                    with mock.patch.object(events, "temp_critical_c", return_value=90.0):
                        with mock.patch.object(events, "boost_util_pct", return_value=80.0):
                            with mock.patch.object(events, "pressure_util_pct", return_value=55.0):
                                with mock.patch.object(events, "emergency_util_pct", return_value=35.0):
                                    self.assertEqual(events.gpu_mode(snap=snap), "boost")

    def test_mode_pressure_below_55(self) -> None:
        snap = {"gpu_util_pct": 40.0, "gpu_temp_c": 50.0}
        with mock.patch.object(events, "thermal_enabled", return_value=True):
            with mock.patch.object(events, "temp_cool_c", return_value=55.0):
                with mock.patch.object(events, "temp_hot_c", return_value=82.0):
                    with mock.patch.object(events, "temp_critical_c", return_value=90.0):
                        with mock.patch.object(events, "boost_util_pct", return_value=80.0):
                            with mock.patch.object(events, "pressure_util_pct", return_value=55.0):
                                with mock.patch.object(events, "emergency_util_pct", return_value=35.0):
                                    self.assertEqual(events.gpu_mode(snap=snap), "pressure")

    def test_mode_emergency_below_35(self) -> None:
        snap = {"gpu_util_pct": 20.0, "gpu_temp_c": 48.0}
        with mock.patch.object(events, "thermal_enabled", return_value=True):
            with mock.patch.object(events, "temp_cool_c", return_value=55.0):
                with mock.patch.object(events, "temp_hot_c", return_value=82.0):
                    with mock.patch.object(events, "temp_critical_c", return_value=90.0):
                        with mock.patch.object(events, "boost_util_pct", return_value=80.0):
                            with mock.patch.object(events, "pressure_util_pct", return_value=55.0):
                                with mock.patch.object(events, "emergency_util_pct", return_value=35.0):
                                    self.assertEqual(events.gpu_mode(snap=snap), "emergency")

    def test_thermal_scale_cool_full(self) -> None:
        with mock.patch.object(events, "thermal_enabled", return_value=True):
            with mock.patch.object(events, "temp_cool_c", return_value=55.0):
                with mock.patch.object(events, "temp_hot_c", return_value=82.0):
                    with mock.patch.object(events, "temp_critical_c", return_value=90.0):
                        self.assertEqual(events.thermal_scale(temp_c=50.0), 1.0)

    def test_thermal_scale_decreases_with_heat(self) -> None:
        with mock.patch.object(events, "thermal_enabled", return_value=True):
            with mock.patch.object(events, "temp_cool_c", return_value=55.0):
                with mock.patch.object(events, "temp_hot_c", return_value=82.0):
                    with mock.patch.object(events, "temp_critical_c", return_value=90.0):
                        with mock.patch.object(events, "thermal_gamma", return_value=1.0):
                            with mock.patch.object(events, "thermal_min_scale", return_value=0.15):
                                cool = events.thermal_scale(temp_c=55.0)
                                mid = events.thermal_scale(temp_c=68.5)
                                hot = events.thermal_scale(temp_c=82.0)
                                crit = events.thermal_scale(temp_c=90.0)
                                self.assertEqual(cool, 1.0)
                                self.assertLess(mid, cool)
                                self.assertLessEqual(hot, mid + 0.01)
                                self.assertEqual(crit, 0.0)

    def test_effective_max_util_scales(self) -> None:
        with mock.patch.object(events, "thermal_enabled", return_value=True):
            with mock.patch.object(events, "max_util_pct", return_value=95.0):
                with mock.patch.object(events, "_cfg", return_value={"thermal_min_util_pct": 25}):
                    with mock.patch.object(events, "thermal_scale", return_value=1.0):
                        self.assertAlmostEqual(events.effective_max_util_pct(), 95.0)
                    with mock.patch.object(events, "thermal_scale", return_value=0.0):
                        self.assertAlmostEqual(events.effective_max_util_pct(), 25.0)
                    with mock.patch.object(events, "thermal_scale", return_value=0.5):
                        self.assertAlmostEqual(events.effective_max_util_pct(), 60.0)

    def test_at_target_with_slack(self) -> None:
        with mock.patch.object(events, "target_util_pct", return_value=80.0):
            self.assertTrue(events.at_target(snap={"gpu_util_pct": 76.0}))

    def test_sustain_params_scale_with_mode(self) -> None:
        snap = {"gpu_util_pct": 10.0, "gpu_temp_c": 50.0}
        with mock.patch.object(events, "thermal_enabled", return_value=True):
            hold = events.sustain_params("hold", snap=snap)
            emergency = events.sustain_params("emergency", snap=snap)
            self.assertLess(hold["sustain_sec"], emergency["sustain_sec"])
            self.assertLess(hold["embed_batch"], emergency["embed_batch"])
            self.assertAlmostEqual(hold["thermal_scale"], 1.0)

    def test_sustain_thermal_stop_at_critical(self) -> None:
        snap = {"gpu_util_pct": 40.0, "gpu_temp_c": 92.0}
        with mock.patch.object(events, "thermal_enabled", return_value=True):
            with mock.patch.object(events, "temp_critical_c", return_value=90.0):
                params = events.sustain_params("boost", snap=snap)
                self.assertTrue(params.get("thermal_stop") or params.get("throttled"))
                self.assertEqual(params.get("sustain_passes"), 0)


if __name__ == "__main__":
    unittest.main()
