#!/usr/bin/env python3
"""Unittests for compression_t4_scale."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compression_t4_scale as t4  # noqa: E402


class CompressionT4ScaleTests(unittest.TestCase):
    def test_needle_present(self) -> None:
        self.assertIn("OVERSEER_COMPRESSION_T4_SCALE", t4.NEEDLE)

    def test_n_grid_includes_scale(self) -> None:
        self.assertGreaterEqual(min(t4.N_GRID), 10_000_000)
        self.assertGreaterEqual(max(t4.N_GRID), 100_000_000)

    def test_ratio_stable_and_s100(self) -> None:
        rows = t4.run_grid()
        payload = t4.report_dict(rows)
        self.assertTrue(payload["ratio_stable_pm20"])
        self.assertTrue(payload["all_above_floor_s50"])
        self.assertTrue(payload["north_star_s_cleared"])
        self.assertFalse(payload["train_unlocked"])
        self.assertFalse(payload["data_prune"])

    def test_cli_json_exit_zero(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "compression_t4_scale.py"), "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["needle"], t4.NEEDLE)
        self.assertTrue(data["north_star_s_cleared"])


if __name__ == "__main__":
    unittest.main()
