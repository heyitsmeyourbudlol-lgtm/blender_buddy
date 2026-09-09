#!/usr/bin/env python3
"""OVERSEER_FANOUT_CAP_2026_09_03 — hard cap concurrent System Overseers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_oversight as po  # noqa: E402


class TestOverseerFanoutCap(unittest.TestCase):
    def test_cmdline_matches_role_and_h1(self) -> None:
        pathish = (
            "/home/x/.cursor-server/.../cursor-agent-worker/.../cursor-agent "
            "-p # System overseer — event-triggered stagnation dispatch "
            "You are the **System Overseer** for Automation"
        )
        self.assertTrue(po._cmdline_is_overseer(pathish))

    def test_cmdline_rejects_worker_server_token(self) -> None:
        cmd = "cursor-agent worker-server --port 1 System Overseer"
        self.assertFalse(po._cmdline_is_overseer(cmd))

    def test_fanout_blocked_when_count_at_max(self) -> None:
        with mock.patch.object(po, "_overseer_running_count", return_value=1):
            with mock.patch.object(po, "OVERSEER_FANOUT_MAX", 1):
                self.assertTrue(po._overseer_fanout_blocked())

    def test_fanout_allows_when_zero(self) -> None:
        with mock.patch.object(po, "_overseer_running_count", return_value=0):
            self.assertFalse(po._overseer_fanout_blocked())


if __name__ == "__main__":
    unittest.main()
