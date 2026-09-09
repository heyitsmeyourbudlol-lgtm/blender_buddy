#!/usr/bin/env python3
"""Tests for agent vs human gap matrix."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_agent_human_gap as gap  # noqa: E402


class TestPeerAgentHumanGap(unittest.TestCase):
    def test_matrix_has_creativity_row(self) -> None:
        self.assertTrue(any(row[0] == "Creativity" for row in gap.GAP_ROWS))

    def test_block_mentions_countermeasure(self) -> None:
        block = gap.format_human_gap_block(compact=True)
        self.assertIn("Agent vs human", block)
        self.assertIn("hallucination", block.lower())

    def test_write_md(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            gap.AGENT_VS_HUMAN_MD = Path(tmp) / "AGENT_VS_HUMAN.md"
            path = gap.write_agent_vs_human_md()
            text = path.read_text(encoding="utf-8")
            self.assertIn("Full gap matrix", text)
            self.assertGreaterEqual(text.count("|"), 20)


if __name__ == "__main__":
    unittest.main()
