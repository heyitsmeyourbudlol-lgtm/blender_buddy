#!/usr/bin/env python3
"""Tests for expected vs actual output compare."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_output_compare as oc  # noqa: E402


class TestPeerOutputCompare(unittest.TestCase):
    def test_match(self) -> None:
        result = oc.compare_outputs("ok\n", "ok\n")
        self.assertTrue(result.match)

    def test_discrepancy_diff(self) -> None:
        result = oc.compare_outputs("expected line", "actual line")
        self.assertFalse(result.match)
        self.assertTrue(result.diff_lines)

    def test_exit_compare(self) -> None:
        result = oc.compare_exit_and_output(
            expected_exit=0,
            actual_exit=1,
            expected_output="ok",
            actual_output="fail",
        )
        self.assertFalse(result.match)

    def test_block_includes_workflow(self) -> None:
        block = oc.format_output_compare_block(role_id="verify_runner")
        self.assertIn("Expected vs actual", block)
        self.assertIn("verify", block.lower())


if __name__ == "__main__":
    unittest.main()
