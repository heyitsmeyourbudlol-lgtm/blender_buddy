"""OVERSEER_SELF_CHECK_TIP_CONTINUE_ON_DIRTY_WHEN_DIRTY_2026_09_04."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_orchestrate as po  # noqa: E402
import project_automation as auto  # noqa: E402


class SelfCheckContinueOnDirtyTipTests(unittest.TestCase):
    """self-check tip must name continue_on_dirty when dirty."""

    def test_tip_names_continue_on_dirty_when_dirty(self) -> None:
        tip = po._continue_on_dirty_tip_when_dirty(
            SimpleNamespace(
                git_clean=False,
                git_detail="git: 3 changed path(s) (2 modified, 1 untracked)",
            )
        )
        self.assertIsNotNone(tip)
        assert tip is not None
        self.assertIn("continue_on_dirty", tip)
        self.assertIn("changed path", tip)

    def test_tip_absent_when_clean(self) -> None:
        self.assertIsNone(
            po._continue_on_dirty_tip_when_dirty(
                SimpleNamespace(git_clean=True, git_detail="git: clean working tree")
            )
        )

    def test_needle_and_wire_in_self_check_body(self) -> None:
        import inspect

        src = Path(po.__file__).read_text(encoding="utf-8")
        self.assertIn(
            "OVERSEER_SELF_CHECK_TIP_CONTINUE_ON_DIRTY_WHEN_DIRTY_2026_09_04", src
        )
        body = inspect.getsource(po._run_self_check_body)
        self.assertIn("_continue_on_dirty_tip_when_dirty", body)
        self.assertIn(
            "OVERSEER_SELF_CHECK_TIP_CONTINUE_ON_DIRTY_WHEN_DIRTY_2026_09_04", body
        )

    def test_land_proof_closes_kit_item(self) -> None:
        item = (
            "**[kit] peer_orchestrate: self-check tip must name continue_on_dirty "
            "when dirty** — file `scripts/peer_orchestrate.py`; unittest; "
            "`./scripts/peer test-quick`"
        )
        self.assertTrue(auto._land_proof_present(item))
        wq = f"## Active\n\n- [ ] {item}\n\n## Done\n\n"
        new_wq, closed = auto.close_landed_done_orphans(wq)
        self.assertEqual(closed, 1)
        self.assertIn("- [x]", new_wq)

    def test_self_check_stdout_names_continue_on_dirty_when_dirty(self) -> None:
        dirty = SimpleNamespace(
            git_clean=False,
            git_detail="git: 1 changed path(s) (1 modified, 0 untracked)",
            tests_ok=True,
            tests_detail="ok",
            import_rss_mb=None,
            footprint_detail="",
            open_items=[],
        )
        role = mock.Mock()
        role.job_title = "Factory Engineer"
        with (
            mock.patch.object(po.auto, "measure_live_state", return_value=dirty),
            mock.patch.object(po, "build_plan") as bp,
            mock.patch.object(po, "format_prompt", return_value="plan"),
            mock.patch.object(po.auto, "loop_work_items") as lq,
            mock.patch.object(po.roles, "load_roles", return_value=[role] * 8),
            mock.patch.object(po.roles, "worker_pool_size", return_value=8),
            mock.patch.object(
                po.roles, "hub_pool_assignments", return_value=[role] * 8
            ),
            mock.patch.object(po.auto, "parallel_peer_floor", return_value=8),
            mock.patch.object(po.auto, "launch_track_active", return_value=False),
            mock.patch.object(po.auto, "validate_tasks_config", return_value=[]),
            mock.patch.object(po, "_check_fact_checker_niche", return_value=[]),
            mock.patch.object(po, "_check_niche_composer_niche", return_value=[]),
            mock.patch.object(po, "_check_t0_executable_lane", return_value=[]),
            mock.patch.object(po.auto, "sync_queue_drift", return_value=[]),
            mock.patch.object(po.auto, "load_tasks_config", return_value={}),
            mock.patch.object(po.auto, "load_context_md", return_value=""),
            mock.patch.object(po.auto, "load_work_queue_md", return_value="## Active\n"),
            mock.patch("builtins.print") as printed,
        ):
            plan = mock.Mock()
            plan.stop = False
            plan.tasks = [mock.Mock(peer="impl")]
            plan.role_assignments = [
                mock.Mock(role=role) for _ in range(8)
            ]
            plan.live = {"open_items": ["x"]}
            bp.return_value = plan
            lq.return_value = SimpleNamespace(open_items=["x"], source="launch")
            rc = po._run_self_check_body(quick=True)
        out = "\n".join(
            str(c.args[0]) if c.args else "" for c in printed.call_args_list
        )
        self.assertIn("continue_on_dirty", out)
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
