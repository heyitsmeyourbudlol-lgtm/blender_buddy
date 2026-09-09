"""T2 SVD-TieStack — real truncated SVD; S≥100 at low rank.

OVERSEER_COMPRESSION_T2_SVD_2026_09_05
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import compression_t2_svd as t2  # noqa: E402


class CompressionT2SvdTests(unittest.TestCase):
    """OVERSEER_COMPRESSION_T2_SVD_2026_09_05"""

    def test_needle_present(self) -> None:
        src = (SCRIPTS / "compression_t2_svd.py").read_text(encoding="utf-8")
        self.assertIn(t2.NEEDLE, src)
        ready = (ROOT / "notes/COMPRESSION_TRAIN_READY.md").read_text(encoding="utf-8")
        self.assertIn(t2.NEEDLE, ready)

    def test_r_grid_includes_north_star(self) -> None:
        self.assertEqual(t2.R_GRID, (1, 2, 4, 8, 16, 32))
        self.assertIn(1, t2.R_GRID)

    def test_unique_up_pack_s100_clear(self) -> None:
        rows = t2.run_sweep()
        self.assertEqual([r.r for r in rows], list(t2.R_GRID))
        self.assertTrue(t2.monotonic_unique_up_with_rank(rows))
        prev_u = None
        for r in rows:
            with self.subTest(r=r.r):
                self.assertEqual(r.d, t2.D_DEFAULT)
                self.assertFalse(r.train_unlocked)
                self.assertTrue(r.detail["pass_pack"])
                self.assertEqual(r.arith_short_of_s100, r.cliff_before_s100)
                self.assertGreaterEqual(r.recon_mse, 0.0)
                if prev_u is not None:
                    self.assertGreater(r.u_unique, prev_u)
                prev_u = r.u_unique
        by_r = {r.r: r for r in rows}
        # r=1 → S≈128 clears arith; high r spends unique and goes short.
        self.assertFalse(by_r[1].arith_short_of_s100)
        self.assertGreaterEqual(by_r[1].s_arith, t2.NORTH_STAR_S)
        self.assertTrue(by_r[32].arith_short_of_s100)
        # Higher rank → lower recon residual (more singular mass kept).
        self.assertLess(by_r[32].recon_mse, by_r[1].recon_mse)

    def test_cli_json_exit_zero(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "compression_t2_svd.py"), "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr + proc.stdout[:500])
        data = json.loads(proc.stdout)
        self.assertEqual(data["needle"], t2.NEEDLE)
        self.assertTrue(data["monotonic_unique_up_with_rank"])
        self.assertTrue(data["all_pack_ok"])
        self.assertTrue(data["north_star_s_cleared"])
        self.assertFalse(data["train_unlocked"])
        self.assertEqual(len(data["results"]), len(t2.R_GRID))


if __name__ == "__main__":
    unittest.main()
