"""Regression: run_local_cycle ready follows verify gate, not git_clean."""

from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402
import run_peer_tasks  # noqa: E402


class LocalCycleReadyTests(unittest.TestCase):
    def test_ready_ignores_git_dirty(self) -> None:
        plan = unittest.mock.Mock(stop=False, tasks=["item"])
        dirty = auto.LiveState(False, "notes dirty", True, "ok", 13.0, "ok")
        with unittest.mock.patch.object(
            run_peer_tasks.po, "build_plan", return_value=plan
        ), unittest.mock.patch.object(
            run_peer_tasks.auto, "measure_live_state", return_value=dirty
        ), unittest.mock.patch.object(
            run_peer_tasks, "run_verify_commands", return_value=(0, None)
        ):
            rc, ready = run_peer_tasks.run_local_cycle(quick=True, log_fn=lambda *_a, **_k: None)
        self.assertEqual(rc, 0)
        self.assertTrue(ready)

    def test_failures_not_ready(self) -> None:
        plan = unittest.mock.Mock(stop=False, tasks=["item"])
        clean = auto.LiveState(True, "clean", False, "fail", 13.0, "ok")
        with unittest.mock.patch.object(
            run_peer_tasks.po, "build_plan", return_value=plan
        ), unittest.mock.patch.object(
            run_peer_tasks.auto, "measure_live_state", return_value=clean
        ), unittest.mock.patch.object(
            run_peer_tasks, "run_verify_commands", return_value=(1, "tests")
        ):
            rc, ready = run_peer_tasks.run_local_cycle(quick=True, log_fn=lambda *_a, **_k: None)
        self.assertEqual(rc, 1)
        self.assertFalse(ready)


if __name__ == "__main__":
    unittest.main()
