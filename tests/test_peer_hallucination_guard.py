#!/usr/bin/env python3
"""Tests for hallucination guard layer."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_hallucination_guard as hg  # noqa: E402


class TestPeerHallucinationGuard(unittest.TestCase):
    def test_block_includes_awareness(self) -> None:
        block = hg.format_hallucination_block(role_id="factory_engineer")
        self.assertIn("hallucinat", block.lower())
        self.assertIn("Strategize", block)
        self.assertIn("strategy", block.lower())

    def test_strategy_checklist(self) -> None:
        text = hg.format_strategy_checklist()
        self.assertIn("Compare gate", text)
        self.assertIn("output-compare", text)

    def test_write_md(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            hg.HALLUCINATION_GUARD_MD = Path(tmp) / "HALLUCINATION_GUARD.md"
            path = hg.write_hallucination_guard_md()
            self.assertTrue(path.is_file())
            self.assertIn("Risk triggers", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
