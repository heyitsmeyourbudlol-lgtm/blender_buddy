"""T3 BitDistill — teacher logit bank → SVD student + durable cache.

OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05
OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import compression_t3_bitdistill as t3  # noqa: E402


class CompressionT3BitdistillTests(unittest.TestCase):
    """OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05 + LOGIT_CACHE."""

    def test_needle_present(self) -> None:
        src = (SCRIPTS / "compression_t3_bitdistill.py").read_text(encoding="utf-8")
        self.assertIn(t3.NEEDLE, src)
        self.assertIn(t3.CACHE_NEEDLE, src)
        novel = (ROOT / "notes/COMPRESSION_NOVEL.md").read_text(encoding="utf-8")
        self.assertIn(t3.NEEDLE, novel)
        self.assertIn(t3.CACHE_NEEDLE, novel)
        recipe = (ROOT / "notes/COMPRESSION_TRAIN_RECIPE.md").read_text(encoding="utf-8")
        self.assertIn(t3.CACHE_NEEDLE, recipe)
        ready = (ROOT / "notes/COMPRESSION_TRAIN_READY.md").read_text(encoding="utf-8")
        self.assertIn(t3.CACHE_NEEDLE, ready)

    def test_compare_gates(self) -> None:
        rows = t3.run_compare()
        self.assertEqual(len(rows), 2)
        student = rows[0]
        prune = rows[1]
        self.assertEqual(student.detail.get("role"), "bitdistill_student")
        self.assertEqual(prune.detail.get("role"), "prune_control")
        self.assertTrue(student.pass_pack)
        self.assertTrue(student.pass_u_budget)
        self.assertTrue(student.pass_kd)
        self.assertFalse(student.data_prune)
        self.assertTrue(student.passed)
        self.assertTrue(prune.data_prune)
        self.assertFalse(prune.passed)
        self.assertEqual(student.quality, "proxy")
        self.assertLessEqual(student.u_unique, student.detail["u_budget"])

    def test_summary(self) -> None:
        payload = t3.summary_dict(t3.run_compare())
        self.assertTrue(payload["all_passed"])
        self.assertTrue(payload["pass_kd"])
        self.assertTrue(payload["u_within_budget"])
        self.assertFalse(payload["train_unlocked"])
        self.assertFalse(payload["data_prune"])
        self.assertFalse(payload["prune_control_passed"])
        self.assertEqual(payload["quality"], "proxy")
        self.assertEqual(payload["needle"], t3.NEEDLE)
        self.assertEqual(payload["cache_needle"], t3.CACHE_NEEDLE)

    def test_logit_bank_cache_roundtrip(self) -> None:
        self.assertTrue(t3.bank_cache_roundtrip_ok())

    def test_check_bank_at_path(self) -> None:
        """OVERSEER_COMPRESSION_T3_LOGIT_CACHE — durable PATH verify (T0 parity)."""
        with tempfile.TemporaryDirectory(prefix="t3_check_path_") as td:
            path = Path(td) / "bank.json"
            teachers, xs, bank = t3.synth_teacher_and_bank()
            t3.dump_logit_bank(path, teachers, xs, bank)
            self.assertTrue(t3.check_bank_at_path(path))

    def test_load_refuses_prune_and_missing_cache_needle(self) -> None:
        teachers, xs, bank = t3.synth_teacher_and_bank()
        with tempfile.TemporaryDirectory(prefix="t3_bank_bad_") as td:
            good = Path(td) / "good.json"
            t3.dump_logit_bank(good, teachers, xs, bank)
            t3.load_logit_bank(good)  # must succeed

            pruned = Path(td) / "pruned.json"
            raw = json.loads(good.read_text(encoding="utf-8"))
            raw["data_prune"] = True
            pruned.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                t3.load_logit_bank(pruned)

            unlocked = Path(td) / "unlocked.json"
            raw2 = json.loads(good.read_text(encoding="utf-8"))
            raw2["train_unlocked"] = True
            unlocked.write_text(json.dumps(raw2), encoding="utf-8")
            with self.assertRaises(ValueError):
                t3.load_logit_bank(unlocked)

            no_cache = Path(td) / "no_cache.json"
            raw3 = json.loads(good.read_text(encoding="utf-8"))
            del raw3["cache_needle"]
            no_cache.write_text(json.dumps(raw3), encoding="utf-8")
            with self.assertRaises(ValueError):
                t3.load_logit_bank(no_cache)

    def test_cli_json_exit_zero(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "compression_t3_bitdistill.py"), "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["needle"], t3.NEEDLE)
        self.assertEqual(data["cache_needle"], t3.CACHE_NEEDLE)
        self.assertTrue(data["all_passed"])
        self.assertFalse(data["train_unlocked"])

    def test_cli_write_read_bank(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t3_cli_bank_") as td:
            bank_path = Path(td) / "bank.json"
            write = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "compression_t3_bitdistill.py"),
                    "--write-bank",
                    str(bank_path),
                    "--json",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(write.returncode, 0, msg=write.stderr)
            self.assertTrue(bank_path.is_file())
            dumped = json.loads(bank_path.read_text(encoding="utf-8"))
            self.assertEqual(dumped["cache_needle"], t3.CACHE_NEEDLE)
            self.assertFalse(dumped["data_prune"])
            self.assertFalse(dumped["train_unlocked"])

            read = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "compression_t3_bitdistill.py"),
                    "--read-bank",
                    str(bank_path),
                    "--json",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(read.returncode, 0, msg=read.stderr)
            data = json.loads(read.stdout)
            self.assertEqual(data["bank_source"], "cache")
            self.assertTrue(data["all_passed"])

            check = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "compression_t3_bitdistill.py"),
                    "--check-cache",
                    "--json",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(check.returncode, 0, msg=check.stderr)
            cdata = json.loads(check.stdout)
            self.assertTrue(cdata["bank_cache_ok"])
            self.assertTrue(cdata["all_passed"])
            # Bare --check-cache → DEFAULT_BANK_PATH (T0 pack parity; not synth)
            self.assertEqual(cdata["bank_source"], "cache")
            self.assertIn("bank_path", cdata)
            self.assertTrue(
                cdata["bank_path"].endswith("t3_teacher_logit_bank.json"),
                msg=cdata["bank_path"],
            )
            self.assertFalse(cdata["train_unlocked"])
            self.assertFalse(cdata["data_prune"])

            # PATH form (parity with T0 --check-cache PATH) — durable bank verify
            check_path = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "compression_t3_bitdistill.py"),
                    "--check-cache",
                    str(bank_path),
                    "--json",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(check_path.returncode, 0, msg=check_path.stderr)
            pdata = json.loads(check_path.stdout)
            self.assertTrue(pdata["bank_cache_ok"])
            self.assertEqual(pdata["bank_source"], "cache")
            self.assertEqual(pdata["bank_path"], str(bank_path))
            self.assertFalse(pdata["data_prune"])
            self.assertFalse(pdata["train_unlocked"])
            self.assertTrue(pdata["all_passed"])

    def test_ensure_default_bank(self) -> None:
        """Canonical Lane-U path: dump→load KD-stable; TRAIN locked."""
        with tempfile.TemporaryDirectory(prefix="t3_default_bank_") as td:
            path = Path(td) / "t3_teacher_logit_bank.json"
            out, ok = t3.ensure_default_bank(path)
            self.assertEqual(out, path)
            self.assertTrue(ok)
            self.assertTrue(path.is_file())
            meta = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(meta["cache_needle"], t3.CACHE_NEEDLE)
            self.assertFalse(meta["data_prune"])
            self.assertFalse(meta["train_unlocked"])
            # CLI against temp path via --write-bank + --read-bank already covered;
            # ensure DEFAULT_BANK_PATH constant points under notes/compression_artifacts/
            self.assertEqual(
                t3.DEFAULT_BANK_PATH.name, "t3_teacher_logit_bank.json"
            )
            self.assertIn("compression_artifacts", str(t3.DEFAULT_BANK_PATH))

    def test_ensure_default_bank_cli(self) -> None:
        """CLI --ensure-default-bank emits bank_path (T0 pack_path parity); TRAIN locked."""
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "compression_t3_bitdistill.py"),
                "--ensure-default-bank",
                "--json",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["bank_cache_ok"])
        self.assertTrue(data["all_passed"])
        self.assertEqual(data["bank_source"], "default_bank")
        self.assertFalse(data["train_unlocked"])
        self.assertFalse(data["data_prune"])
        self.assertIn("bank_path", data)
        self.assertTrue(data["bank_path"].endswith("t3_teacher_logit_bank.json"))
        self.assertTrue(t3.DEFAULT_BANK_PATH.is_file())
        loaded = t3.load_logit_bank(t3.DEFAULT_BANK_PATH)
        self.assertEqual(len(loaded[0]), t3.LAYERS)
        self.assertEqual(len(loaded[1]), t3.N_EXAMPLES)


if __name__ == "__main__":
    unittest.main()
