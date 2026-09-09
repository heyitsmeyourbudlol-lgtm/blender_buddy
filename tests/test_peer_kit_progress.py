#!/usr/bin/env python3
"""Tests for peer_kit_progress — LOC + snapshot."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_kit_progress as kp  # noqa: E402


class TestPeerKitProgress(unittest.TestCase):
    def test_count_repo_loc_positive(self) -> None:
        buckets, total_code, _total_all = kp.count_repo_loc()
        self.assertGreater(total_code, 1000)
        names = {b.name for b in buckets}
        self.assertIn("scripts_py", names)
        self.assertIn("tests_py", names)

    def test_compute_kit_progress(self) -> None:
        kit = kp.compute_kit_progress()
        self.assertGreaterEqual(kit.factory_pct, 0)
        self.assertGreater(kit.loc_total, 0)
        self.assertGreater(kit.peer_commands, 50)

    def test_write_digest(self) -> None:
        kit = kp.compute_kit_progress()
        path = kp.write_kit_progress_digest(kit=kit)
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("Lines of code", text)
        self.assertIn("Factory readiness", text)


if __name__ == "__main__":
    unittest.main()
