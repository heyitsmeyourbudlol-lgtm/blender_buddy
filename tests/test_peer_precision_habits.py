#!/usr/bin/env python3
"""Tests for precision habits layer."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_precision_habits as ph  # noqa: E402


class TestPeerPrecisionHabits(unittest.TestCase):
    def test_block_includes_needle_method(self) -> None:
        block = ph.format_precision_block(role_id="verify_runner", model="inherit")
        self.assertIn("needle", block.lower())
        self.assertIn("Locate", block)
        self.assertIn("failing test", block.lower())

    def test_model_tiers(self) -> None:
        fast = ph.format_model_precision(model="composer-2.5-fast", subagent_type="shell")
        self.assertIn("Speed", fast)
        self.assertIn("exit code", fast.lower())
        self.assertEqual(ph.normalize_model("composer-2.5-fast"), "composer-2.5-fast")

    def test_write_md(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ph.PRECISION_HABITS_MD = Path(tmp) / "PRECISION_HABITS.md"
            path = ph.write_precision_habits_md()
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn("Haystack questions", text)
            self.assertIn("Factory Engineer", text)


if __name__ == "__main__":
    unittest.main()
