"""OVERSEER_SELF_CHECK_DEDUP_2026_09_04 — no orphan measure before build_plan."""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import peer_orchestrate as po  # noqa: E402
import project_automation as auto  # noqa: E402


class SelfCheckDedupMeasureTests(unittest.TestCase):
    def test_source_skips_orphan_measure(self) -> None:
        src = inspect.getsource(po._run_self_check_body)
        self.assertNotIn("live = auto.measure_live_state", src)
        self.assertIn("OVERSEER_SELF_CHECK_REUSE_PLAN_LIVE_2026_09_04", src)
        self.assertIn("OVERSEER_LAND_2026_09_04", src)
        self.assertEqual(src.count("build_plan(quick=quick)"), 1)

    def test_body_uses_plan_live_not_second_measure(self) -> None:
        plan = po.PeerPlan(
            orchestrator_brief="b",
            tasks=[],
            live={
                "git_clean": True,
                "git": "clean",
                "tests_ok": True,
                "tests": "tests: ok",
                "import_rss_mb": 10.0,
                "footprint": "rss",
                "open_items": [],
                "queue_source": "empty",
            },
            stop=True,
            stop_reason="done",
        )
        with mock.patch.object(po, "_try_acquire_self_check_lock", return_value=True), mock.patch.object(
            po, "_release_self_check_lock"
        ), mock.patch.object(po, "build_plan", return_value=plan) as bp, mock.patch.object(
            auto, "measure_live_state"
        ) as measure, mock.patch.object(
            auto,
            "load_tasks_config",
            return_value={
                "peers": {},
                "task_templates": {},
                "verify_commands": [],
                "match_rules": [],
                "agent_roles": [],
            },
        ), mock.patch.object(auto, "load_context_md", return_value="## Remaining work\n"), mock.patch.object(
            auto, "load_work_queue_md", return_value="## Active\n"
        ), mock.patch.object(auto, "validate_tasks_config", return_value=[]), mock.patch.object(
            auto, "sync_queue_drift", return_value=[]
        ), mock.patch.object(auto, "launch_track_active", return_value=False), mock.patch.object(
            auto, "loop_work_items", return_value=auto.QueueState(open_items=[], source="empty")
        ), mock.patch.object(po.roles, "load_roles", return_value=[]), mock.patch.object(
            po.roles, "worker_pool_size", return_value=8
        ), mock.patch.object(auto, "parallel_peer_floor", return_value=8), mock.patch.object(
            po, "format_prompt", return_value="preview"
        ):
            rc = po.run_self_check(quick=True)
        # Role/adapt issues may still flag rc=1 under thin mocks — measure must not run.
        bp.assert_called_once()
        measure.assert_not_called()
        self.assertIn(rc, (0, 1))


if __name__ == "__main__":
    unittest.main()
