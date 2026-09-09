#!/usr/bin/env python3
"""Tests for grounded idea synthesis."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_idea_synthesis as idea  # noqa: E402


class TestPeerIdeaSynthesis(unittest.TestCase):
    def test_articulate_template_requires_anchors(self) -> None:
        block = idea.format_idea_synthesis_block(role_id="factory_engineer")
        self.assertIn("Anchors", block)
        self.assertIn("≥2", block)

    def test_invalid_anchors_rejected(self) -> None:
        ok, msg = idea._validate_anchors("only one anchor")
        self.assertFalse(ok)
        self.assertIn("≥2", msg)

    def test_record_idea_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            idea.IDEAS_JSONL = Path(tmp) / "ideas.jsonl"
            idea.CREATIVE_BACKLOG_PATH = Path(tmp) / "CREATIVE_BACKLOG.md"
            path = idea.record_idea(
                role_id="factory_engineer",
                title="Test lever",
                anchors="scripts/peer_loop.py:820 wake path",
                hypothesis="Reduce noop hold when queue_fp unchanged",
                experiment="unittest peer_loop noop",
            )
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "Test lever")
            self.assertIn("Test lever", idea.CREATIVE_BACKLOG_PATH.read_text(encoding="utf-8"))

    def test_niche_lenses(self) -> None:
        text = idea.format_niche_ideas("orchestrator")
        self.assertIn("queue", text.lower())


if __name__ == "__main__":
    unittest.main()
