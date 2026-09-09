#!/usr/bin/env python3
"""Tests for improve ↔ automation team integration."""

from __future__ import annotations

import os
import sys
import unittest
import unittest.mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import automation_improve as improve  # noqa: E402
import automation_team as team  # noqa: E402


class TestAutomationTeam(unittest.TestCase):
    def test_format_team_block_mentions_eight(self) -> None:
        text = team.format_team_block(quick=True)
        self.assertIn("Automation team", text)
        self.assertIn("8", text)
        self.assertIn("flaw", text.lower())

    def test_improve_plan_includes_team_block(self) -> None:
        signals = improve.ImproveSignals(
            live={"git": "clean", "tests": "ok", "queue_source": "empty", "open_items": []},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
            opportunities=[
                improve.Opportunity("speed", "Worktree pool", "ensure-pool", priority=20),
            ],
        )
        text = improve.build_plan_prompt(signals)
        self.assertIn("Automation team", text)
        self.assertIn("OPERATING_SYSTEM", text)

    def test_rank_team_opportunities_executable(self) -> None:
        opps = team.rank_team_opportunities(set())
        self.assertTrue(len(opps) >= 1)
        titles = " ".join(o.title.lower() for o in opps)
        self.assertTrue(
            "flaw" in titles or "debrief" in titles or "worktree" in titles or "roster" in titles
        )

    def test_team_status_uses_agents_board_slice_not_build_board(self) -> None:
        """TEAM_STATUS_SKIP_PORCELAIN — slice not build_board."""
        team.clear_team_status_cache()
        with unittest.mock.patch(
            "peer_agent_board.agents_board_slice",
            return_value={"summary": {"phase": "WAITING"}, "dispatch_iso": "iso-test"},
        ) as slice_fn:
            with unittest.mock.patch(
                "peer_agent_board.build_board",
                side_effect=AssertionError("build_board must not run"),
            ):
                st = team.team_status(quick=True)
        slice_fn.assert_called_once()
        self.assertEqual(st["agents_board"]["summary"]["phase"], "WAITING")
        self.assertEqual(st["agents_board"]["dispatch_iso"], "iso-test")

    def test_team_status_generation_cache_hit_and_remiss(self) -> None:
        """TEAM_STATUS_GENERATION_CACHE — same key HIT; ROUND mtime remisses."""
        import peer_flaw_scan as flaw

        team.clear_team_status_cache()
        first = team.team_status(quick=True)
        second = team.team_status(quick=True)
        self.assertIs(first, second)

        round_path = flaw.ROUND_PATH
        round_path.parent.mkdir(parents=True, exist_ok=True)
        if not round_path.is_file():
            round_path.write_text("{}", encoding="utf-8")
        ns = round_path.stat().st_mtime_ns + 1_000_000
        os.utime(round_path, ns=(ns // 1_000_000_000, ns % 1_000_000_000))
        third = team.team_status(quick=True)
        self.assertIsNot(first, third)
        self.assertEqual(third.get("operating_system"), first.get("operating_system"))

    def test_team_status_for_rank_generation_cache_hit_and_remiss(self) -> None:
        """RANK_TEAM_STATUS_CACHE — for_rank HIT; ROUND mtime remisses."""
        import peer_flaw_scan as flaw

        team.clear_team_status_cache()
        first = team.team_status_for_rank()
        second = team.team_status_for_rank()
        self.assertIs(first, second)

        round_path = flaw.ROUND_PATH
        round_path.parent.mkdir(parents=True, exist_ok=True)
        if not round_path.is_file():
            round_path.write_text("{}", encoding="utf-8")
        ns = round_path.stat().st_mtime_ns + 1_000_000
        os.utime(round_path, ns=(ns // 1_000_000_000, ns % 1_000_000_000))
        third = team.team_status_for_rank()
        self.assertIsNot(first, third)
        self.assertIn("entries", third.get("debrief") or {})

    def test_rank_team_uses_status_for_rank_not_full_debrief(self) -> None:
        """RANK_TEAM_STATUS_LITE — rank must not call debrief.status_dict / factory."""
        with unittest.mock.patch.object(
            team, "team_status_for_rank", wraps=team.team_status_for_rank
        ) as lite:
            with unittest.mock.patch(
                "peer_debrief.status_dict",
                side_effect=AssertionError("status_dict must not run on rank"),
            ):
                with unittest.mock.patch(
                    "factory_progress.compute_factory_progress",
                    side_effect=AssertionError("factory must not run on rank"),
                ):
                    opps = team.rank_team_opportunities(set())
        lite.assert_called_once()
        self.assertTrue(len(opps) >= 1)
        st = team.team_status_for_rank()
        self.assertIn("entries", st.get("debrief") or {})
        self.assertNotIn("recent", st.get("debrief") or {})

    def test_hand_out_worker_pool_assigns_all_roles(self) -> None:
        logs: list[str] = []
        signals = improve.ImproveSignals(
            live={"open_items": ["**Fix tests** — run unittest"]},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
            opportunities=[],
        )
        with unittest.mock.patch.object(team, "hand_out_worker_pool", wraps=team.hand_out_worker_pool):
            handed = team.hand_out_worker_pool(log_fn=logs.append, signals=signals)
        self.assertGreaterEqual(len(handed), 1)
        self.assertTrue(any("hand_out:" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
