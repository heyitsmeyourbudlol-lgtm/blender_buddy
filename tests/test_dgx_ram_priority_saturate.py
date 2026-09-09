#!/usr/bin/env python3
"""Saturate free-desktop floor — RAM priority must not SIGKILL under cap.

Needle: OVERSEER_SATURATE_KEEP_FLOOR_2026_09_07
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dgx_ram_priority as pri  # noqa: E402


def _fake_procs(n: int) -> list[SimpleNamespace]:
    return [SimpleNamespace(pid=1000 + i) for i in range(n)]


class SaturateKeepFloorTests(unittest.TestCase):
    def test_free_headroom_keeps_factory_floor(self) -> None:
        """8 under-cap agents must not be slaughtered for ballast headroom."""
        logs: list[str] = []
        procs = _fake_procs(8)
        with mock.patch.object(pri, "target_used_gb", return_value=100.0):
            with mock.patch.object(pri.budget, "footprint_gb", return_value=60.0):
                with mock.patch.object(pri, "hold_band_gb", return_value=2.0):
                    with mock.patch.object(
                        pri.budget,
                        "mem_stats",
                        return_value={"avail_gb": 3.0, "used_gb": 100.0},
                    ):
                        with mock.patch.object(
                            pri.budget, "ram_critical_avail_floor_gb", return_value=6.0
                        ):
                            with mock.patch.object(
                                pri.eff, "fill_headroom_gb", return_value=12.0
                            ):
                                with mock.patch.object(
                                    pri, "trim_worker_storms", return_value={}
                                ):
                                    with mock.patch(
                                        "peer_parallel_dispatch.find_agent_procs",
                                        return_value=procs,
                                    ):
                                        with mock.patch(
                                            "peer_parallel_dispatch.max_parallel_agent_procs",
                                            return_value=8,
                                        ):
                                            with mock.patch("os.kill") as kill:
                                                out = pri.free_headroom_for_fill(
                                                    log_fn=logs.append
                                                )
        self.assertEqual(out.get("agents_killed"), 0)
        kill.assert_not_called()

    def test_t3_skips_under_floor_kill(self) -> None:
        """Footprint over target must not SIGKILL agents within the factory floor."""
        logs: list[str] = []
        with mock.patch.object(pri.budget, "footprint_gb", return_value=105.0):
            with mock.patch.object(pri, "target_used_gb", return_value=100.0):
                with mock.patch(
                    "peer_parallel_dispatch.trim_agents_over_cap", return_value=0
                ) as trim:
                    with mock.patch("os.kill") as kill:
                        step = pri._evict_tier_3(log_fn=logs.append)
        self.assertEqual(step.freed_estimate, 0)
        trim.assert_called_once()
        kill.assert_not_called()
        self.assertTrue(any("skip under-floor" in m for m in logs))


if __name__ == "__main__":
    unittest.main()
