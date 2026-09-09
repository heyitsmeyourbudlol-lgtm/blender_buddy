#!/usr/bin/env python3
"""Tests for executable agent gates."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_agent_gates as gates  # noqa: E402


class TestPeerAgentGates(unittest.TestCase):
    def test_plan_gate_covers_all_gaps(self) -> None:
        import peer_agent_human_gap as gap

        report = gates.run_plan_gate(role_id="factory_engineer", refresh=False, quick=True)
        gap_names = {r.gap for r in report.results}
        for human, *_ in gap.GAP_ROWS:
            self.assertIn(human, gap_names, msg=human)

    def test_done_gate_compare_pass(self) -> None:
        report = gates.run_done_gate(
            role_id="verify_runner",
            expected="ok",
            actual="ok",
            quick=True,
        )
        reality = [r for r in report.results if r.gap == "Reality check"][0]
        self.assertEqual(reality.status, "pass")

    def test_done_gate_compare_fail(self) -> None:
        report = gates.run_done_gate(
            role_id="verify_runner",
            expected="exit 0",
            actual="exit 1",
            quick=True,
        )
        reality = [r for r in report.results if r.gap == "Reality check"][0]
        self.assertEqual(reality.status, "fail")

    @patch.object(gates, "_queue_drift_ok", return_value=(False, "drift"))
    def test_plan_gate_blocks_on_drift(self, _mock: object) -> None:
        report = gates.run_plan_gate(role_id="orchestrator", refresh=False, quick=True)
        self.assertTrue(report.blocked)

    def test_plan_gate_softens_noop_always(self) -> None:
        """Noop alone must never hard-block plan-gate (autonomy deadlock)."""
        from unittest.mock import MagicMock

        soft = MagicMock()
        soft.severity = "critical"
        soft.title = "Noop cycle — queue fingerprint unchanged after ok verify"
        soft.evidence = "playbook:noop_cycle"
        with patch(
            "peer_self_diagnose.run_instant_diagnosis",
            return_value=[soft],
        ):
            report = gates.run_plan_gate(role_id="orchestrator", refresh=False, quick=True)
        sc = [r for r in report.results if r.gap == "Self-correction"][0]
        self.assertIn(sc.status, ("pass", "warn"))
        self.assertFalse(report.blocked)

    def test_worktree_pool_ok_uses_inprocess_list(self) -> None:
        """plan-gate must not shell ``python3 peer_worktree.py list`` (fork tax)."""
        import peer_worktree as wt

        fake = [
            wt.WorktreeEntry(path="/tmp/a", head="0" * 40, branch="peer/0"),
            wt.WorktreeEntry(path="/tmp/b", head="1" * 40, branch="peer/1"),
        ]
        with (
            patch.object(wt, "list_worktrees", return_value=fake) as list_mock,
            patch.object(gates.auto, "parallel_peer_floor", return_value=2),
            patch.object(gates.subprocess, "run") as run_mock,
        ):
            ok, detail = gates._worktree_pool_ok()
        self.assertTrue(ok)
        self.assertEqual(detail, "worktrees=2")
        list_mock.assert_called_once()
        run_mock.assert_not_called()

    def test_done_gate_creativity_gap_name(self) -> None:
        report = gates.run_done_gate(role_id="factory_engineer", quick=True)
        names = {r.gap for r in report.results}
        self.assertIn("Creativity", names)
        self.assertNotIn("Grounded ideas", names)


if __name__ == "__main__":
    unittest.main()
