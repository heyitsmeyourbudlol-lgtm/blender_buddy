#!/usr/bin/env python3
"""Tests for agent board (birds-eye + per-niche)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_agent_board as board  # noqa: E402
import peer_orchestrate as po  # noqa: E402
import project_automation as auto  # noqa: E402


class TestPeerAgentBoard(unittest.TestCase):
    def test_build_board_has_floor_agents(self) -> None:
        floor = auto.parallel_peer_floor()
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp)
            with mock.patch.object(board, "ROSTER_PATH", cfg_dir / "roster.json"):
                with mock.patch.object(board, "STATUS_PATH", cfg_dir / "status.json"):
                    with mock.patch.object(board, "STATE_PATH", cfg_dir / "state.json"):
                        plan = po.build_plan(quick=True, loop=True)
                        board.record_dispatch(plan)
                        b = board.build_board(refresh_roster=False)
        self.assertEqual(len(b["agents"]), floor)
        self.assertEqual(len({a["role_id"] for a in b["agents"]}), floor)
        self.assertIn("orchestrator", b)
        self.assertIn("summary", b)

    def test_record_dispatch_persists(self) -> None:
        floor = auto.parallel_peer_floor()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roster.json"
            with mock.patch.object(board, "ROSTER_PATH", path):
                plan = po.build_plan(quick=True, loop=True)
                board.record_dispatch(plan)
                data = json.loads(path.read_text())
        self.assertEqual(len(data["agents"]), floor)
        self.assertTrue(data.get("dispatch_ts"))

    def test_update_agent_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "roster.json"
            with mock.patch.object(board, "ROSTER_PATH", path):
                plan = po.build_plan(quick=True, loop=True)
                board.record_dispatch(plan)
                ok = board.update_agent_note("verify_runner", "running", "Running unittest gate")
                self.assertTrue(ok)
                data = json.loads(path.read_text())
        vr = next(a for a in data["agents"] if a["role_id"] == "verify_runner")
        self.assertEqual(vr["status"], "running")
        self.assertIn("unittest", vr["detail"])


if __name__ == "__main__":
    unittest.main()
