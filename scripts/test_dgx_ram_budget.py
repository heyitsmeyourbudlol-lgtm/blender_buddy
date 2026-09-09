#!/usr/bin/env python3
"""Tests for DGX RAM budget."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dgx_ram_budget as budget  # noqa: E402


class TestDgxRamBudget(unittest.TestCase):
    def test_is_unittest_worker_cmdline_real_process(self) -> None:
        self.assertTrue(
            budget.is_unittest_worker_cmdline("python3 -m unittest discover -s tests -q")
        )
        self.assertTrue(
            budget.is_unittest_worker_cmdline("/bin/sh -c python3 -m unittest discover -s tests -q")
        )

    def test_is_unittest_worker_cmdline_excludes_cursor_agent(self) -> None:
        agent = (
            "cursor-agent -p --force # Niche agent\n"
            "Run verify: `python3 -m unittest discover -s tests -q`"
        )
        self.assertFalse(budget.is_unittest_worker_cmdline(agent))

    def test_effective_thresholds_with_cap(self) -> None:
        with mock.patch.object(budget, "ram_max_used_gb", return_value=100.0):
            min_avail, crit = budget.effective_ram_thresholds(121.0)
        self.assertEqual(min_avail, 21.0)
        self.assertGreaterEqual(crit, 6.0)
        self.assertLessEqual(crit, min_avail)

    def test_pressure_critical_when_over_cap(self) -> None:
        with mock.patch.object(budget, "ram_max_used_gb", return_value=100.0):
            level = budget.pressure_level(avail_gb=10.0, total_gb=121.0)
        self.assertEqual(level, "critical")

    def test_pressure_ok_with_headroom(self) -> None:
        with mock.patch.object(budget, "ram_max_used_gb", return_value=100.0):
            level = budget.pressure_level(avail_gb=30.0, total_gb=121.0)
        self.assertEqual(level, "ok")


    def test_guard_shell_vars_mins_nested_with_top_level(self) -> None:
        """Stale dgx_host.dgx_unittest_cap=96/20 must not beat top-level=2."""
        cfg = {
            "dgx_unittest_cap": 2,
            "max_parallel_peers": 8,
            "max_parallel_agent_procs": 8,
            "dgx_host": {
                "dgx_unittest_cap": 96,
                "dgx_max_cursor_agents": 48,
                "ram_max_used_gb": 100,
            },
        }
        with mock.patch.object(budget.auto, "CFG", cfg), mock.patch.object(
            budget.auto, "max_parallel_peers", return_value=8
        ), mock.patch.object(
            budget, "mem_stats", return_value={
                "total_gb": 121.0, "avail_gb": 30.0, "used_gb": 80.0,
                "footprint_gb": 80.0, "used_avail_gb": 91.0,
            }
        ), mock.patch.object(budget, "ram_max_used_gb", return_value=100.0):
            vars_ = budget.guard_shell_vars()
        self.assertEqual(vars_["unittest_cap"], 2)
        self.assertEqual(vars_["max_agents"], 8)

if __name__ == "__main__":
    unittest.main()
