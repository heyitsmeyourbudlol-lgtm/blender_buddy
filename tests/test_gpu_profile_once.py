"""Tests for GPU profile-once (DGX util + CLEAN FP4 meters; skip without code change).

OVERSEER_GPU_PROFILE_ONCE_2026_09_05
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import gpu_profile_once as gpo  # noqa: E402


class GpuProfileOnceTests(unittest.TestCase):
    """OVERSEER_GPU_PROFILE_ONCE_2026_09_05"""

    def test_needle_present(self) -> None:
        src = (SCRIPTS / "gpu_profile_once.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_GPU_PROFILE_ONCE_2026_09_05", src)
        self.assertIn("without a code change", src)
        self.assertIn("scope_fingerprint", src)
        self.assertIn("append_meter", src)

    def test_scope_fingerprint_stable(self) -> None:
        a = gpo.scope_fingerprint(root=ROOT)
        b = gpo.scope_fingerprint(root=ROOT)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 16)

    def test_skip_when_fingerprint_unchanged(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gpu_prof_") as td:
            cfg = Path(td)
            with mock.patch.object(gpo.auto, "CONFIG_DIR", cfg):
                fp = gpo.scope_fingerprint(root=ROOT)
                gpo.save_state({"scope_fp": fp, "ts": "t0"})
                skip, got = gpo.should_skip(force=False, root=ROOT)
                self.assertTrue(skip)
                self.assertEqual(got, fp)
                skip_f, _ = gpo.should_skip(force=True, root=ROOT)
                self.assertFalse(skip_f)

    def test_run_profile_appends_meters(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gpu_prof_run_") as td:
            cfg = Path(td)
            with mock.patch.object(gpo.auto, "CONFIG_DIR", cfg):
                with mock.patch.object(
                    gpo,
                    "_gpu_snap",
                    return_value={"gpu_util_pct": 0.0, "gpu_temp_c": 40.0},
                ):
                    with mock.patch.object(
                        gpo, "_probe_te_fp4", return_value=(False, "ModuleNotFoundError: x")
                    ):
                        row = gpo.run_profile(force=True, root=ROOT)
                self.assertFalse(row.skipped)
                self.assertIsNotNone(row.prompt_tok_s)
                self.assertIsNotNone(row.accepted_writing_tok_s)
                self.assertFalse(row.te_fp4_available)
                self.assertIn("transformer_engine_unavailable_use_clean_fp4_mmap", row.bottlenecks)
                meters = cfg / gpo.METERS_NAME
                self.assertTrue(meters.is_file())
                lines = [ln for ln in meters.read_text(encoding="utf-8").splitlines() if ln.strip()]
                self.assertEqual(len(lines), 1)
                blob = json.loads(lines[0])
                self.assertIn("prompt_tok_s", blob)
                self.assertIn("gpu_util_pct", blob)
                # Second call without force must skip (same scope fp).
                row2 = gpo.run_profile(force=False, root=ROOT)
                self.assertTrue(row2.skipped)
                lines2 = [ln for ln in meters.read_text(encoding="utf-8").splitlines() if ln.strip()]
                self.assertEqual(len(lines2), 1)  # no append on skip

    def test_cli_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gpu_prof_cli_") as td:
            cfg = Path(td)
            with mock.patch.object(gpo.auto, "CONFIG_DIR", cfg):
                with mock.patch.object(gpo, "_gpu_snap", return_value={"gpu_util_pct": 1.0}):
                    with mock.patch("sys.stdout", new_callable=lambda: __import__("io").StringIO()):
                        rc = gpo.main(["--json", "--force"])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
