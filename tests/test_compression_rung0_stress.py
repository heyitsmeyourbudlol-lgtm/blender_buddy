#!/usr/bin/env python3
"""Unittests for rung0 train helpers + stress suite honesty gate."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compression_stress_suite as stress  # noqa: E402
import compression_train_rung0 as rung0  # noqa: E402


class Rung0Helpers(unittest.TestCase):
    def test_s_ge_100_at_t4_n1e7_defaults(self) -> None:
        u = rung0.unique_params(10_000_000, 200, 1, 2, 256, 256, 16)
        s = 10_000_000 / u
        self.assertEqual(u, 74576)
        self.assertGreaterEqual(s, 100.0)

    def test_nvfp4_pack_half_bytes(self) -> None:
        self.assertEqual(rung0.nvfp4_bytes(100), 50.0)


class StressHonesty(unittest.TestCase):
    def test_waiting_without_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            art = Path(td)
            with mock.patch.object(stress, "ART", art), mock.patch.object(
                stress, "STRESS_PATH", art / "stress_bars.json"
            ), mock.patch.object(stress, "STATUS_PATH", art / "rung0_train_status.json"), mock.patch.object(
                stress, "SKELETON_PATH", art / "rung0_model_skeleton.json"
            ), mock.patch.object(
                stress, "CKPT_LATEST", art / "rung0_checkpoints" / "rung0_latest.pt"
            ):
                payload = stress.evaluate()
        self.assertEqual(payload["status"], "WAITING_FOR_FULL_TRAIN")
        self.assertFalse(payload["integrate_allowed"])
        self.assertTrue(all(v is None for v in payload["bars"].values()))

    def test_integrate_false_when_bar_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            art = Path(td)
            ckpt = art / "rung0_checkpoints"
            ckpt.mkdir(parents=True)
            (ckpt / "rung0_latest.pt").write_bytes(b"fake")
            status = {
                "train_complete": True,
                "step": 100,
                "S_arith": 3.0,  # fail S bar
                "unique_U_arith": 25076,
                "n_logic": 100000,
                "nvfp4_pack_bytes": 12538.0,
                "heldout_kd_mse": 0.01,
                "data_prune": False,
                "north_star_1b_complete": False,
            }
            (art / "rung0_train_status.json").write_text(json.dumps(status), encoding="utf-8")
            (art / "rung0_model_skeleton.json").write_text(json.dumps(status), encoding="utf-8")
            with mock.patch.object(stress, "ART", art), mock.patch.object(
                stress, "STATUS_PATH", art / "rung0_train_status.json"
            ), mock.patch.object(stress, "SKELETON_PATH", art / "rung0_model_skeleton.json"), mock.patch.object(
                stress, "CKPT_LATEST", ckpt / "rung0_latest.pt"
            ), mock.patch.object(
                stress.subprocess,
                "check_output",
                return_value=json.dumps({"needle": "OVERSEER_COMPRESSION_T5_SERVE_2026_09_06", "rows": [1]}),
            ):
                payload = stress.evaluate()
        self.assertEqual(payload["status"], "FAIL")
        self.assertFalse(payload["integrate_allowed"])
        self.assertEqual(payload["bars"]["S_ge_100_or_recipe_floor"]["result"], "FAIL")


if __name__ == "__main__":
    unittest.main()
