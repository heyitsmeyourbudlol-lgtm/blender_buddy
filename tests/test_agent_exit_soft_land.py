#!/usr/bin/env python3
"""OVERSEER_AGENT_EXIT_SOFT_VERIFY_OK_LAND_2026_09_04 tests."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_oversight_events as events  # noqa: E402


class TestAgentExitSoftLand(unittest.TestCase):
    def test_peer_loop_soft_keeps_verify_ok(self) -> None:
        src = (SCRIPTS / "peer_loop.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_AGENT_EXIT_SOFT_VERIFY_OK_LAND_2026_09_04", src)
        self.assertIn("verify_ok=bool(soft)", src)

    def test_skip_live_hit_soft_agent_exit(self) -> None:
        soft = (
            "2026-09-04 10:55:00 cursor-agent non-zero exit (soft Episodic) "
            "rc=1 failure_type=agent_exit_soft"
        )
        self.assertTrue(events._skip_live_hit_line(soft, "cursor-agent non-zero"))
        hard = "2026-09-04 10:55:00 cursor-agent non-zero exit rc=1"
        self.assertFalse(events._skip_live_hit_line(hard, "cursor-agent non-zero"))

    def test_soft_agent_exit_not_critical_stagnation(self) -> None:
        ctx = {
            "queue_count": 0,
            "phase": "WORKING",
            "noop_backoff_sec": 0,
            "last_cycle": {
                "noop": False,
                "verify_ok": True,
                "rc": 1,
                "failure_type": "agent_exit_soft",
                "note": "cursor-agent non-zero exit (soft Episodic)",
                "git_head": "abc",
            },
            "kit": {
                "factory_pct": 95,
                "asi_pct": 100,
                "tests_ok": True,
                "queue_drift": 0,
                "daemons": {"peer_loop": True, "improve_loop": True},
            },
            "bottlenecks": [],
            "daemon_running": True,
        }
        with mock.patch.object(
            events,
            "scan_live_error_hits",
            return_value=[
                "live log: cursor-agent non-zero — Fix verify gate — cursor-agent non-zero exit"
            ],
        ):
            rep = events.evaluate_stagnation(
                ctx, {"open": 0, "critical": 0, "high": 0}, state={}
            )
        self.assertFalse(rep.critical)
        self.assertFalse(any("verify gate FAIL" in r for r in rep.reasons))
        self.assertFalse(any("live log: cursor-agent" in r for r in rep.reasons))


if __name__ == "__main__":
    unittest.main()
