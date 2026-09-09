#!/usr/bin/env python3
"""Tests for 8-worker parallel peer orchestration."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_orchestrate as po  # noqa: E402
import project_automation as auto  # noqa: E402


class TestParallelPeers(unittest.TestCase):
    def test_build_implementation_tasks_eight_unique_niches(self) -> None:
        cfg = auto.load_tasks_config()
        items = [f"**Factory task {i}** — improve `scripts/mod{i}.py`" for i in range(10)]
        with mock.patch.object(auto, "max_parallel_peers", return_value=8):
            with mock.patch.object(auto, "parallel_peer_floor", return_value=8):
                with mock.patch.object(auto, "merge_same_peer_tasks", return_value=False):
                    tasks, assigns = po._build_implementation_tasks(items, cfg)
        impl = [t for t in tasks if t.peer not in ("safety", "verify")]
        self.assertEqual(len(impl), 8)
        role_ids = [t.role_id for t in impl]
        self.assertEqual(len(set(role_ids)), 8)
        self.assertTrue(all(t.job_title for t in impl))

    def test_format_prompt_targets_eight_workers(self) -> None:
        cfg = auto.load_tasks_config()
        items = [f"**Item {i}** — scope `scripts/a{i}.py`" for i in range(3)]
        with mock.patch.object(auto, "max_parallel_peers", return_value=8):
            with mock.patch.object(auto, "parallel_peer_floor", return_value=8):
                with mock.patch.object(auto, "merge_same_peer_tasks", return_value=False):
                    tasks, assigns = po._build_implementation_tasks(items, cfg)
        plan = po.PeerPlan(
            orchestrator_brief="brief",
            tasks=tasks,
            live={},
            stop=False,
            stop_reason=None,
            role_assignments=assigns,
        )
        text = po.format_prompt(plan)
        self.assertIn("8", text)
        self.assertIn("one niche", text.lower())
        self.assertIn("Job title", text)
        self.assertEqual(len(assigns), 8)
        self.assertEqual(len({a.role.id for a in assigns}), 8)

    def test_merge_same_peer_tasks_collapses_when_enabled(self) -> None:
        raw = [
            po.PeerTask("implement", "generalPurpose", "green", "A", ["a.py"], "do A"),
            po.PeerTask("implement", "generalPurpose", "green", "B", ["b.py"], "do B"),
        ]
        merged = po._merge_implementation_tasks(raw)
        self.assertEqual(len(merged), 1)


if __name__ == "__main__":
    unittest.main()
