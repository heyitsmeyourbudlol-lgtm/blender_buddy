"""T6 toy quality falsifier — ALBERT-BitMoE vs LoRA-Hive heldout ε.

OVERSEER_COMPRESSION_T6_QUALITY_2026_09_06
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

import compression_t6_quality as t6  # noqa: E402


class CompressionT6QualityTests(unittest.TestCase):
    """OVERSEER_COMPRESSION_T6_QUALITY_2026_09_06"""

    def test_needle_present(self) -> None:
        src = (SCRIPTS / "compression_t6_quality.py").read_text(encoding="utf-8")
        self.assertIn(t6.NEEDLE, src)
        novel = (ROOT / "notes/COMPRESSION_NOVEL.md").read_text(encoding="utf-8")
        self.assertIn(t6.NEEDLE, novel)
        phases = (ROOT / "notes/COMPRESSION_RESEARCH_PHASES.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(t6.NEEDLE, phases)

    def test_compare_gates(self) -> None:
        rows = t6.run_compare()
        self.assertEqual(len(rows), 3)
        albert, hive, prune = rows
        self.assertEqual(albert.stack, "ALBERT-BitMoE")
        self.assertEqual(albert.role, "primary")
        self.assertEqual(hive.stack, "LoRA-Hive")
        self.assertEqual(hive.role, "control")
        self.assertEqual(prune.role, "prune_control")
        self.assertTrue(albert.pass_pack)
        self.assertTrue(albert.pass_u_budget)
        self.assertTrue(albert.pass_kd)
        self.assertFalse(albert.data_prune)
        self.assertTrue(albert.passed)
        self.assertTrue(hive.pass_kd)
        self.assertFalse(hive.data_prune)
        self.assertTrue(hive.passed)
        self.assertTrue(prune.data_prune)
        self.assertFalse(prune.passed)
        self.assertEqual(albert.quality, "proxy")
        self.assertEqual(hive.quality, "proxy")
        self.assertLessEqual(albert.heldout_kd_mse, t6.KD_EPS)
        self.assertLessEqual(hive.heldout_kd_mse, t6.KD_EPS)

    def test_summary(self) -> None:
        payload = t6.summary_dict(t6.run_compare())
        self.assertTrue(payload["all_passed"])
        self.assertTrue(payload["pass_kd_albert"])
        self.assertTrue(payload["pass_kd_hive"])
        self.assertFalse(payload["train_unlocked"])
        self.assertFalse(payload["data_prune"])
        self.assertFalse(payload["prune_control_passed"])
        self.assertEqual(payload["quality"], "proxy")
        self.assertEqual(payload["needle"], t6.NEEDLE)
        self.assertTrue(payload["recipe_stack_unchanged"])

    def test_no_data_prune_on_primary_path(self) -> None:
        rows = t6.run_compare()
        self.assertFalse(rows[0].data_prune)
        self.assertFalse(rows[1].data_prune)
        self.assertEqual(rows[0].detail["n_examples_used"], t6.N_EXAMPLES)
        self.assertEqual(rows[1].detail["n_examples_used"], t6.N_EXAMPLES)

    def test_cli_json_exit_zero(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "compression_t6_quality.py"), "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["needle"], t6.NEEDLE)
        self.assertTrue(data["all_passed"])
        self.assertFalse(data["train_unlocked"])
        self.assertFalse(data["data_prune"])
        self.assertEqual(len(data["results"]), 3)


if __name__ == "__main__":
    unittest.main()
