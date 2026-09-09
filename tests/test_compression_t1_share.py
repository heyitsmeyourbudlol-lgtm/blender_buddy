"""T1 share-factor ablation — unique↓ + pack + recon; S≥100 at high k.

OVERSEER_COMPRESSION_T1_SHARE_2026_09_05
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

import compression_t1_share as t1  # noqa: E402


class CompressionT1ShareTests(unittest.TestCase):
    """OVERSEER_COMPRESSION_T1_SHARE_2026_09_05"""

    def test_needle_present(self) -> None:
        src = (SCRIPTS / "compression_t1_share.py").read_text(encoding="utf-8")
        self.assertIn(t1.NEEDLE, src)
        novel = (ROOT / "notes/COMPRESSION_NOVEL.md").read_text(encoding="utf-8")
        self.assertIn(t1.NEEDLE, novel)

    def test_k_grid_includes_north_star(self) -> None:
        self.assertEqual(t1.K_GRID, (2, 4, 8, 16, 50, 100, 125, 200))
        self.assertIn(200, t1.K_GRID)

    def test_monotonic_unique_pack_and_s100_clear(self) -> None:
        rows = t1.run_sweep()
        self.assertEqual([r.k for r in rows], list(t1.K_GRID))
        self.assertTrue(t1.monotonic_unique_down(rows))
        prev_u = None
        for r in rows:
            with self.subTest(k=r.k):
                self.assertEqual(r.n_logic, t1.N_L_DEFAULT)
                self.assertFalse(r.train_unlocked)
                self.assertTrue(r.detail["pass_pack"])
                self.assertTrue(r.quality_proxy_ok)
                self.assertEqual(r.arith_short_of_s100, r.cliff_before_s100)
                self.assertLessEqual(
                    abs(r.packed_bytes - r.u_unique / 8.0), t1.META_BOUND_BYTES
                )
                self.assertGreaterEqual(r.recon_mse, 0.0)
                if prev_u is not None:
                    self.assertLess(r.u_unique, prev_u)
                prev_u = r.u_unique
        # Weak k still short; high k clears arith north-star (not a quality cliff).
        by_k = {r.k: r for r in rows}
        self.assertTrue(by_k[16].arith_short_of_s100)
        self.assertFalse(by_k[200].arith_short_of_s100)
        self.assertGreaterEqual(by_k[200].s_arith, t1.NORTH_STAR_S)

    def test_cli_json_exit_zero(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "compression_t1_share.py"), "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["needle"], t1.NEEDLE)
        self.assertTrue(data["monotonic_unique_down"])
        self.assertTrue(data["all_pack_ok"])
        self.assertTrue(data["north_star_s_cleared"])
        self.assertFalse(data["train_unlocked"])
        self.assertEqual(len(data["results"]), len(t1.K_GRID))


if __name__ == "__main__":
    unittest.main()
