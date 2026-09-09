#!/usr/bin/env python3
"""Prove peer_loop pre-dispatch wires compact → check → ensure-pool before spawn."""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_commands as pc  # noqa: E402
import peer_loop  # noqa: E402


class TestPreDispatchCompoundRecipe(unittest.TestCase):
    def test_cli_compound_order(self) -> None:
        steps = pc.COMPOUND_STEPS["pre-dispatch"]
        self.assertEqual(steps[0], "compact-queue")
        self.assertIn("check", steps)
        self.assertIn("ensure-pool", steps)
        self.assertLess(steps.index("check"), steps.index("ensure-pool"))


class TestMechanicalPreDispatchWire(unittest.TestCase):
    def test_source_calls_check_and_ensure_pool(self) -> None:
        src = inspect.getsource(peer_loop._mechanical_pre_dispatch)
        self.assertIn("run_self_check", src)
        self.assertIn("_emit_worktree_inventory", src)
        self.assertIn("OVERSEER_PRE_DISPATCH_CHECK_POOL_2026_09_07", src)

    def test_terminal_cycle_invokes_mechanical_pre_dispatch(self) -> None:
        src = inspect.getsource(peer_loop._run_terminal_cycle)
        self.assertIn("_mechanical_pre_dispatch", src)

    def test_mechanical_runs_check_then_ensure(self) -> None:
        peer_loop.clear_pre_dispatch_check_cache()
        peer_loop.clear_emit_ensure_cache()
        logs: list[str] = []
        order: list[str] = []

        def _check(*, quick: bool = False) -> int:
            order.append("check")
            return 0

        def _emit(log_fn) -> None:  # noqa: ANN001
            order.append("ensure-pool")
            log_fn("worktree pool: test ensure")

        with (
            mock.patch.object(
                peer_loop.auto, "compact_executable_queue", return_value=(0, [])
            ),
            mock.patch.dict("sys.modules", {"peer_self_heal": mock.MagicMock()}),
            mock.patch(
                "peer_transcript.current_queue_fingerprint",
                return_value=("fp", []),
            ),
            mock.patch("automation_adapt.heal_queue_drift", return_value=([], [])),
            mock.patch("peer_team_context.write_team_context"),
            mock.patch(
                "factory_niche_runtime.assist_pre_dispatch", return_value={}
            ),
            mock.patch("peer_agent_gates.run_plan_gate") as gate,
            mock.patch("peer_orchestrate.run_self_check", side_effect=_check),
            mock.patch.object(peer_loop, "_emit_worktree_inventory", side_effect=_emit),
        ):
            report = mock.Mock(blocked=False, warn_count=0)
            gate.return_value = report
            # Avoid self-heal import path noise — patch module attr if loaded
            ok = peer_loop._mechanical_pre_dispatch(
                log_fn=logs.append, role_id="orchestrator"
            )
        self.assertTrue(ok)
        self.assertEqual(order, ["check", "ensure-pool"])
        self.assertTrue(any("check ok" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
