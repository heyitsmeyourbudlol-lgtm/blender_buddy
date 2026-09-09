#!/usr/bin/env python3
"""Unittests for compression_t5_serve (T5 residency smoke).

OVERSEER_COMPRESSION_T5_SERVE_2026_09_06
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compression_t5_serve as t5  # noqa: E402


class CompressionT5ServeTests(unittest.TestCase):
    def test_needle_present(self) -> None:
        self.assertIn("OVERSEER_COMPRESSION_T5_SERVE", t5.NEEDLE)

    def test_north_star_raw_5mb_fits_l2(self) -> None:
        rows = t5.build_rows(None)
        north = next(r for r in rows if r.label == "north_star_10M_unique")
        self.assertEqual(north.unique_u, 10_000_000)
        self.assertAlmostEqual(north.raw_nvfp4_bytes, 5_000_000.0)
        self.assertAlmostEqual(north.raw_nvfp4_mb, 5.0)
        self.assertAlmostEqual(north.packed_sketch_mb, 5.625)
        self.assertTrue(north.fit_l2_24mb)
        self.assertTrue(north.fit_l3_24mb)

    def test_logical_1b_does_not_fit(self) -> None:
        rows = t5.build_rows(None)
        one_b = next(r for r in rows if r.label == "logical_1B_all_unique")
        self.assertAlmostEqual(one_b.raw_nvfp4_mb, 500.0)
        self.assertFalse(one_b.fit_l2_24mb)

    def test_skeleton_when_present(self) -> None:
        sk = t5.load_skeleton()
        self.assertIsNotNone(sk)
        assert sk is not None
        rows = t5.build_rows(sk)
        payload = t5.report_dict(rows, sk)
        self.assertTrue(payload["arith_not_quality"])
        self.assertTrue(payload["north_star_fits_l2"])
        self.assertTrue(any(r.label == "rung0_skeleton" for r in rows))
        skel = next(r for r in rows if r.label == "rung0_skeleton")
        self.assertEqual(skel.unique_u, int(sk["unique_U"]))

    def test_cli_json_exit_zero(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "compression_t5_serve.py"), "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["needle"], t5.NEEDLE)
        self.assertTrue(data["arith_not_quality"])
        self.assertTrue(data["north_star_fits_l2"])
        self.assertAlmostEqual(data["north_star_raw_mb"], 5.0)


if __name__ == "__main__":
    unittest.main()
