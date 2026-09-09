"""Ablation schedule — OA / successive-halving / Hyperband (S03/S16/S32).

OVERSEER_COMPRESSION_ABLATION_SCHEDULE_2026_09_06
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import compression_ablation_schedule as sched  # noqa: E402


class CompressionAblationScheduleTests(unittest.TestCase):
    """OVERSEER_COMPRESSION_ABLATION_SCHEDULE_2026_09_06"""

    def test_needle_present(self) -> None:
        src = (SCRIPTS / "compression_ablation_schedule.py").read_text(encoding="utf-8")
        self.assertIn(sched.NEEDLE, src)
        self.assertEqual(sched.NEEDLE, "OVERSEER_COMPRESSION_ABLATION_SCHEDULE_2026_09_06")
        research = (ROOT / "notes/RESEARCH_SPEED_TRAINING.md").read_text(encoding="utf-8")
        self.assertIn("compression_ablation_schedule.py", research)
        phases = (ROOT / "notes/COMPRESSION_RESEARCH_PHASES.md").read_text(encoding="utf-8")
        self.assertIn("compression_ablation_schedule.py", phases)

    def test_oa_l9_smaller_than_full_grid(self) -> None:
        oa = sched.orthogonal_array_screen()
        grid = sched.full_grid()
        self.assertEqual(len(oa), 9)
        self.assertEqual(len(grid), len(sched.K_LEVELS_DEFAULT) * len(sched.R_LEVELS_DEFAULT))
        self.assertLess(len(oa), len(grid))
        # Each factor level appears in the screen.
        ks = {p.k for p in oa}
        rs = {p.r for p in oa}
        es = {p.e for p in oa}
        self.assertEqual(len(ks), 3)
        self.assertEqual(len(rs), 3)
        self.assertEqual(len(es), 3)

    def test_successive_halving_culls_by_eta(self) -> None:
        configs = [
            sched.ConfigPoint(k=k, r=1, config_id=f"c{i}")
            for i, k in enumerate((2, 4, 8, 16, 50, 100, 125, 200, 256))
        ]
        bracket = sched.successive_halving_bracket(
            configs, max_resource=27, eta=3, bracket_id=0, s=2
        )
        self.assertGreaterEqual(len(bracket.rounds), 2)
        n_path = [r.n_configs for r in bracket.rounds]
        self.assertEqual(n_path[0], 9)
        # Each round keeps ~1/eta (floor), never grows.
        for a, b in zip(n_path, n_path[1:]):
            self.assertLessEqual(b, a)
            self.assertLessEqual(b, max(1, a // 3 + 1))
        self.assertFalse(sched.BLOCKS_RUNG0)
        self.assertFalse(sched.TRAIN_UNLOCKED)

    def test_hyperband_has_smax_plus_one_brackets(self) -> None:
        grid = sched.full_grid(
            k_levels=(2, 8, 50, 200),
            r_levels=(1, 4, 16),
        )
        max_r = 81
        eta = 3
        brackets = sched.hyperband_brackets(grid, max_resource=max_r, eta=eta)
        s_max = int(math.floor(math.log(max_r) / math.log(eta)))
        self.assertEqual(len(brackets), s_max + 1)
        self.assertEqual([b.s for b in brackets], list(range(s_max, -1, -1)))

    def test_oa_then_hb_payload_flags(self) -> None:
        payload = sched.build_schedule(mode="oa-then-hb", eta=3, max_resource=81)
        self.assertEqual(payload["needle"], sched.NEEDLE)
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["blocks_rung0"])
        self.assertFalse(payload["train_unlocked"])
        self.assertTrue(payload["recipe_locked"])
        self.assertEqual(payload["mode"], "oa-then-hb")
        self.assertEqual(payload["screen_n"], 9)
        self.assertGreater(payload["full_grid_n"], payload["screen_n"])
        self.assertGreater(len(payload["brackets"]), 0)
        self.assertIsNotNone(payload["approx_speedup_vs_full_grid"])
        self.assertGreater(payload["approx_speedup_vs_full_grid"], 1.0)

    def test_oa_then_hb_cheaper_than_full_hyperband_no_clone(self) -> None:
        """OVERSEER_COMPRESSION_HB_NO_CLONE_2026_09_08 — OA cull must shrink HB units."""
        oa_hb = sched.build_schedule(mode="oa-then-hb", eta=3, max_resource=81)
        full_hb = sched.build_schedule(mode="hyperband", eta=3, max_resource=81)
        self.assertLess(
            oa_hb["schedule_resource_units"],
            full_hb["schedule_resource_units"],
            msg=(
                "oa-then-hb must be cheaper than full-grid Hyperband; "
                "clone inflation made them equal (1902==1902) before fix"
            ),
        )
        # Measured peer-6 2026-09-08: BEFORE 1902 → AFTER 1134 (~1.68× vs prior schedule).
        self.assertEqual(oa_hb["schedule_resource_units"], 1134)
        self.assertEqual(full_hb["schedule_resource_units"], 1665)

    def test_cli_json_and_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ablation_schedule.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "compression_ablation_schedule.py"),
                    "--mode",
                    "oa-then-hb",
                    "--json",
                    "--out",
                    str(out),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            data = json.loads(proc.stdout)
            self.assertEqual(data["needle"], sched.NEEDLE)
            self.assertTrue(data["dry_run"])
            self.assertFalse(data["blocks_rung0"])
            self.assertTrue(out.is_file())
            disk = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(disk["needle"], sched.NEEDLE)
            self.assertEqual(disk["mode"], "oa-then-hb")
            self.assertEqual(disk["cache_needle"], sched.CACHE_NEEDLE)
            self.assertIn("fingerprint", disk)

    def test_ensure_default_schedule_probe_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            art = root / "notes/compression_artifacts/ablation_schedule.json"
            first = sched.ensure_default_schedule(root=root, path=art)
            self.assertTrue(first["ensured"])
            self.assertFalse(first["cache_hit"])
            self.assertTrue(first["cache_ok"])
            self.assertEqual(first["cache_needle"], sched.CACHE_NEEDLE)
            self.assertFalse(first["train_unlocked"])
            second = sched.ensure_default_schedule(root=root, path=art)
            self.assertFalse(second["ensured"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(second["fingerprint"], first["fingerprint"])
            check = sched.check_schedule_cache(art)
            self.assertTrue(check["cache_ok"])
            self.assertTrue(check["cache_hit"])

    def test_check_cache_cli_green_after_ensure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ablation_schedule.json"
            ensure = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "compression_ablation_schedule.py"),
                    "--ensure-default-schedule",
                    "--out",
                    str(out),
                    "--json",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(ensure.returncode, 0, msg=ensure.stderr)
            check = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "compression_ablation_schedule.py"),
                    "--check-cache",
                    "--out",
                    str(out),
                    "--json",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(check.returncode, 0, msg=check.stderr)
            data = json.loads(check.stdout)
            self.assertTrue(data["cache_ok"])
            self.assertEqual(data["cache_needle"], sched.CACHE_NEEDLE)


if __name__ == "__main__":
    unittest.main()
