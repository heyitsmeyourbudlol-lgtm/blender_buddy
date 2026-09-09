#!/usr/bin/env python3
"""Tests for cumulative project learning."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_project_learning as pl  # noqa: E402


class TestPeerProjectLearning(unittest.TestCase):
    def test_inside_out_map_nonempty(self) -> None:
        self.assertGreater(len(pl.INSIDE_OUT_MAP), 8)

    def test_format_learning_block(self) -> None:
        block = pl.format_learning_block(role_id="factory_engineer")
        self.assertIn("Project learning", block)
        self.assertIn("Master", block)
        self.assertIn("peer_loop", block)

    def test_record_and_recent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pl.SHARED_LEARNINGS_JSONL = Path(tmp) / "learnings.jsonl"
            pl.PROJECT_LEARNING_MD = Path(tmp) / "PROJECT_LEARNING.md"
            pl.LEARNING_STATE_JSON = Path(tmp) / "state.json"
            entry = pl.record_learning(
                "factory_engineer",
                "peer_loop calls build_plan before dispatch",
                also_agent_note=False,
            )
            self.assertTrue(entry.text)
            recent = pl.recent_learnings(role_id="factory_engineer", limit=5)
            self.assertEqual(len(recent), 1)


if __name__ == "__main__":
    unittest.main()
