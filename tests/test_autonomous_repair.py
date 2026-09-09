#!/usr/bin/env python3
"""Tests for autonomous_repair."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import autonomous_repair as ar  # noqa: E402
import project_automation as auto  # noqa: E402


class TestAutonomousRepair(unittest.TestCase):
    def test_enabled_default_true(self) -> None:
        with mock.patch.object(ar, "_cfg", return_value={}):
            self.assertTrue(ar.enabled())

    def test_dedupe_queue(self) -> None:
        with mock.patch.object(auto, "dedupe_work_queue_files", return_value=3):
            self.assertIn("removed 3", ar.dedupe_queue())

    def test_repair_verify_failure_dispatches_on_still_failing(self) -> None:
        lines: list[str] = []

        def log_fn(msg: str) -> None:
            lines.append(msg)

        with mock.patch.object(ar, "enabled", return_value=True):
            with mock.patch.object(ar, "_on_cooldown", return_value=False):
                with mock.patch.object(ar, "run_mechanical_repairs", return_value=[]):
                    with mock.patch(
                        "run_peer_tasks.run_verify_gate",
                        return_value=(1, "tests", 1),
                    ):
                        with mock.patch.object(
                            ar,
                            "dispatch_role",
                            return_value="dispatch_role: launched verify_runner",
                        ) as dispatch:
                            ok = ar.repair_verify_failure(log_fn=log_fn, paid_api=True)
        self.assertTrue(ok)
        dispatch.assert_called_once()
        self.assertTrue(any("self-fixing" in ln for ln in lines))


if __name__ == "__main__":
    unittest.main()
