"""TTL-skip gather in peer_loop._prepare_continuous_prompts when prompts age-fresh."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import automation_improve as improve  # noqa: E402
import peer_loop  # noqa: E402


class WritePromptsAgeFreshTests(unittest.TestCase):
    def test_age_fresh_true_when_stamp_within_ttl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            plan = config_dir / "plan.md"
            exe = config_dir / "exec.md"
            combined = config_dir / "combined.md"
            fp_path = config_dir / "improve-prompts.fp"
            for p in (plan, exe, combined):
                p.write_text("x\n", encoding="utf-8")
            fp_path.write_text(
                json.dumps({"fp": "abc", "ts": time.time()}) + "\n", encoding="utf-8"
            )
            with mock.patch.object(improve, "PLAN_PATH", plan), mock.patch.object(
                improve, "EXECUTE_PATH", exe
            ), mock.patch.object(improve, "COMBINED_PATH", combined), mock.patch.object(
                improve, "WRITE_PROMPTS_FP_PATH", fp_path
            ), mock.patch.object(improve, "write_prompts_ttl_sec", return_value=120.0):
                self.assertTrue(improve.write_prompts_age_fresh())
                age = improve.write_prompts_fp_age_sec()
                self.assertIsNotNone(age)
                assert age is not None
                self.assertLess(age, 5.0)

    def test_age_fresh_false_when_stamp_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            plan = config_dir / "plan.md"
            exe = config_dir / "exec.md"
            combined = config_dir / "combined.md"
            fp_path = config_dir / "improve-prompts.fp"
            for p in (plan, exe, combined):
                p.write_text("x\n", encoding="utf-8")
            fp_path.write_text(
                json.dumps({"fp": "abc", "ts": time.time() - 999.0}) + "\n",
                encoding="utf-8",
            )
            with mock.patch.object(improve, "PLAN_PATH", plan), mock.patch.object(
                improve, "EXECUTE_PATH", exe
            ), mock.patch.object(improve, "COMBINED_PATH", combined), mock.patch.object(
                improve, "WRITE_PROMPTS_FP_PATH", fp_path
            ), mock.patch.object(improve, "write_prompts_ttl_sec", return_value=120.0):
                self.assertFalse(improve.write_prompts_age_fresh())


class PrepareContinuousPromptsTtlTests(unittest.TestCase):
    def test_prepare_skips_gather_when_age_fresh(self) -> None:
        logs: list[str] = []
        with mock.patch.object(peer_loop.auto, "improve_drives_automation", return_value=True), mock.patch.object(
            improve, "write_prompts_age_fresh", return_value=True
        ), mock.patch.object(
            improve, "write_prompts_fp_age_sec", return_value=1.5
        ), mock.patch.object(
            improve, "write_prompts_ttl_sec", return_value=120.0
        ), mock.patch.object(improve, "gather_signals") as gather, mock.patch.object(
            improve, "write_prompts"
        ) as write:
            with mock.patch.dict("sys.modules", {"automation_improve": improve}):
                peer_loop._prepare_continuous_prompts(quick=True, log_fn=logs.append)
            gather.assert_not_called()
            write.assert_not_called()
            self.assertTrue(any("gather deferred" in line for line in logs))

    def test_prepare_gathers_when_age_stale(self) -> None:
        logs: list[str] = []
        fake_signals = object()
        with mock.patch.object(peer_loop.auto, "improve_drives_automation", return_value=True), mock.patch.object(
            improve, "write_prompts_age_fresh", return_value=False
        ), mock.patch.object(
            improve, "gather_signals", return_value=fake_signals
        ) as gather, mock.patch.object(
            improve, "write_prompts", return_value=["a", "b", "c"]
        ) as write:
            with mock.patch.dict("sys.modules", {"automation_improve": improve}):
                peer_loop._prepare_continuous_prompts(quick=True, log_fn=logs.append)
            gather.assert_called_once()
            write.assert_called_once()
            self.assertTrue(any("3 file(s)" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
