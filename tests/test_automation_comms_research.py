"""Tests for automation_comms_research."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import automation_comms_research as cr  # noqa: E402


class TestCommsResearch(unittest.TestCase):
    def test_curated_trends_non_empty(self) -> None:
        self.assertGreaterEqual(len(cr.CURATED_COMMS_TRENDS), 5)

    def test_build_report_shape(self) -> None:
        report = cr.build_comms_report(refresh=False)
        self.assertIn("trends", report)
        self.assertIn("gap_count", report)
        self.assertGreater(report["curated_count"], 0)


if __name__ == "__main__":
    unittest.main()
