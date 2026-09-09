#!/usr/bin/env python3
"""Tests for peer_factory_a_plus."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_factory_a_plus as fap  # noqa: E402


class TestFactoryAPlus(unittest.TestCase):
    def test_is_theater_detects_crown_markers(self) -> None:
        self.assertTrue(fap._is_theater("TIME BOMB crown-era strategy essay"))
        self.assertFalse(fap._is_theater("**[factory-a-plus:phase0] Dual-daemon proof**"))

    def test_demote_theater_moves_active_open(self) -> None:
        work = (
            "## Active\n\n"
            "- [ ] **TIME BOMB** crown-era meta-exit essay\n"
            "- [ ] **[factory-a-plus:phase0] Dual-daemon proof** — bootstrap\n\n"
            "## Backlog\n\n"
            "- [ ] old backlog item\n"
        )
        import project_automation as auto

        with mock.patch.object(auto, "load_work_queue_md", return_value=work):
            n, demoted = fap.demote_theater(write=False)
        self.assertEqual(n, 1)
        self.assertTrue(any("TIME BOMB" in d for d in demoted))

    def test_evaluate_phases_returns_six(self) -> None:
        phases = fap.evaluate_phases()
        self.assertEqual(len(phases), 6)
        self.assertEqual(phases[0].phase, "0")


if __name__ == "__main__":
    unittest.main()
