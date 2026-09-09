#!/usr/bin/env python3
"""Tests for command_ecosystem coverage + raw-script tips."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import command_ecosystem as ceco  # noqa: E402


class TestCommandEcosystem(unittest.TestCase):
    def test_raw_script_tip_warns(self) -> None:
        tip = ceco.raw_script_tip("run python3 scripts/foo_bar.py --x")
        self.assertIsNotNone(tip)
        self.assertIn("foo_bar", tip or "")

    def test_raw_script_tip_ok_with_peer(self) -> None:
        tip = ceco.raw_script_tip(
            "./scripts/peer check then python3 scripts/foo_bar.py"
        )
        self.assertIsNone(tip)

    def test_niche_prefix_idempotent(self) -> None:
        a = ceco.ensure_niche_task_prefix("**X** — do stuff")
        self.assertIn("commands-list", a)
        b = ceco.ensure_niche_task_prefix(a)
        self.assertEqual(a, b)

    def test_build_coverage_shape(self) -> None:
        cov = ceco.build_coverage()
        self.assertIn("n_gaps", cov)
        self.assertIn("gaps", cov)
        self.assertIn("layers", cov)
        self.assertEqual(cov.get("needle"), ceco.NEEDLE)

    def test_dispatch_audit_shape(self) -> None:
        audit = ceco.dispatch_compliance_audit()
        self.assertIn("status", audit)
        self.assertIn("peer_vs_raw_ratio", audit)

    def test_orchestrator_block(self) -> None:
        block = ceco.orchestrator_command_block()
        self.assertIn("pre-dispatch", block)
        self.assertIn("commands-cycle", block)


if __name__ == "__main__":
    unittest.main()
