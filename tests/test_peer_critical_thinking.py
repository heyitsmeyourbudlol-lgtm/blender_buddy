#!/usr/bin/env python3
"""Tests for critical thinking layer."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_critical_thinking as ct  # noqa: E402


class TestPeerCriticalThinking(unittest.TestCase):
    def test_block_includes_gates(self) -> None:
        block = ct.format_critical_thinking_block(role_id="verify_runner")
        self.assertIn("Evidence", block)
        self.assertIn("Plan gate", block)
        self.assertIn("flake", block.lower())

    def test_self_check_questions(self) -> None:
        block = ct.format_self_check_questions(role_id="queue_steward")
        self.assertIn("Before Plan", block)
        self.assertIn("identical", block.lower())
        self.assertIn("BLOCK", block)

    def test_write_md(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ct.CRITICAL_THINKING_MD = Path(tmp) / "CRITICAL_THINKING.md"
            path = ct.write_critical_thinking_md()
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn("Pre-mortem", text)


if __name__ == "__main__":
    unittest.main()
