#!/usr/bin/env python3
"""OVERSEER_FANOUT_PENDING_STAMP + TRIM_SIGKILL + HEALTHY_IDLE soft/safety (2026-09-04)."""
from __future__ import annotations
import sys, tempfile, time, unittest
from pathlib import Path
from unittest import mock
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import peer_oversight as po
import peer_oversight_events as events

class TestFanoutPendingStamp(unittest.TestCase):
    def test_needles_present(self) -> None:
        src = (SCRIPTS / "peer_oversight.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_FANOUT_PENDING_STAMP_2026_09_04", src)
        self.assertIn("OVERSEER_FANOUT_TRIM_SIGKILL_2026_09_04", src)
        self.assertIn("_mark_fanout_pending", src)
        self.assertIn("sigkill=", src)
    def test_pending_blocks_fanout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pending = Path(td) / "overseer-fanout-pending"
            pending.write_text(f"{time.time():.6f}\n", encoding="utf-8")
            with mock.patch.object(po, "OVERSEER_FANOUT_PENDING", pending):
                with mock.patch.object(po, "_overseer_running_count", return_value=0):
                    self.assertTrue(po._overseer_fanout_blocked())
    def test_no_pending_allows_when_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pending = Path(td) / "overseer-fanout-pending"
            with mock.patch.object(po, "OVERSEER_FANOUT_PENDING", pending):
                with mock.patch.object(po, "_overseer_running_count", return_value=0):
                    self.assertFalse(po._overseer_fanout_blocked())

class TestHealthyIdleSoftVerify(unittest.TestCase):
    def test_soft_verify_needle(self) -> None:
        src = (SCRIPTS / "peer_oversight_events.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_HEALTHY_IDLE_SOFT_VERIFY_2026_09_04", src)
        self.assertIn("OVERSEER_HEALTHY_IDLE_NO_SAFETY_NET_2026_09_04", src)
        self.assertIn("OVERSEER_HEALTHY_IDLE_LOCAL_ONLY_DEMOTE_2026_09_04", src)
        self.assertIn("def _last_verify_ok_for_idle", src)
    def test_soft_failure_counts_as_idle_ok(self) -> None:
        last = {"verify_ok": False, "failure_type": "agent_exit_soft",
                "note": "cursor-agent non-zero exit (soft Episodic)"}
        self.assertTrue(events._last_verify_ok_for_idle(last))
        self.assertFalse(events._last_verify_ok_for_idle({"verify_ok": False, "failure_type": "hard"}))
    def test_local_only_demoted_when_idle_green(self) -> None:
        ctx = {"queue_count": 0, "phase": "WORKING", "noop_backoff_sec": 0,
               "kit": {"factory_pct": 100, "asi_pct": 100, "tests_ok": True},
               "last_cycle": {"verify_ok": True, "noop": False, "local_only": True,
                              "note": "prompt refresh", "git_head": "deadbeef"}}
        with mock.patch.object(events, "_active_queue_metrics", return_value=("", 0)):
            with mock.patch.object(events, "_live_factory_pct", return_value=100.0):
                with mock.patch.object(events, "scan_live_error_hits", return_value=[]):
                    with mock.patch.object(events, "_dual_brain_mismatch", return_value=False):
                        with mock.patch.object(events, "_queue_drift_count", return_value=0):
                            with mock.patch.object(events, "_log_has_patterns", return_value=False):
                                rep = events.evaluate_stagnation(ctx, {"open": 0}, state={})
        self.assertFalse(any("local-only" in r for r in rep.reasons))
        self.assertFalse(rep.should_dispatch)

if __name__ == "__main__":
    unittest.main()
