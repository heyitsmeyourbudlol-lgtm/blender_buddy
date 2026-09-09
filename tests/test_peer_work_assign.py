#!/usr/bin/env python3
"""Tests for peer work assignment + ETA scheduling."""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_work_assign as wa  # noqa: E402


class TestPeerWorkAssign(unittest.TestCase):
    def test_estimate_grows_with_scope(self) -> None:
        small = wa.estimate_eta_sec("fix one line in scripts/foo.py", role_id="verify_runner")
        large = wa.estimate_eta_sec(
            "refactor scripts/foo.py scripts/bar.py and all repos",
            role_id="factory_engineer",
        )
        self.assertLess(small, large)

    def test_scheduling_now_vs_miss(self) -> None:
        now = time.time()
        soon = wa.scheduling_decision(eta_sec=300, deadline_ts=now + 3600, now=now)
        self.assertEqual(soon.when, wa.WHEN_NOW)
        impossible = wa.scheduling_decision(
            eta_sec=int(wa.cursor_agent_timeout_sec()) + 600,
            now=now,
        )
        self.assertEqual(impossible.when, wa.WHEN_MISS)

    def test_explicit_deadline_miss_is_miss_not_later(self) -> None:
        """Explicit deadline passed but task fits cursor session → WHEN_MISS, not WHEN_LATER."""
        now = time.time()
        # Deadline already passed (30s ago), ETA=120s fits well within cursor session.
        # Before fix: elif finish_ts <= cursor_limit_ts - 60 would fire → WHEN_LATER (wrong).
        # After fix: explicit deadline_ts provided + slack<0 → WHEN_MISS.
        result = wa.scheduling_decision(
            eta_sec=120,
            deadline_ts=now - 30,
            now=now,
        )
        self.assertEqual(result.when, wa.WHEN_MISS)

    def test_assign_blocked_on_miss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wa.REGISTRY_PATH = root / "work-assignments.json"
            try:
                import peer_agent_comms as comms

                comms.COMMS_DIR = root / "comms"
                comms.BUS_PATH = comms.COMMS_DIR / "bus.jsonl"
                comms.AGENTS_DIR = comms.COMMS_DIR / "agents"
                huge_eta = int(wa.cursor_agent_timeout_sec()) + 3600
                with mock.patch.object(wa, "estimate_eta_sec", return_value=huge_eta):
                    result = wa.assign_work(
                        "orchestrator",
                        "verify_runner",
                        "impossible before session ends",
                    )
            except RuntimeError:
                self.skipTest("comms disabled")
            self.assertFalse(result.get("ok"))
            self.assertEqual(result.get("when"), wa.WHEN_MISS)

    def test_block_documents_eta(self) -> None:
        block = wa.format_work_assign_block(role_id="orchestrator")
        self.assertIn("cursor-agent", block.lower())
        self.assertIn("eta", block.lower())


if __name__ == "__main__":
    unittest.main()
