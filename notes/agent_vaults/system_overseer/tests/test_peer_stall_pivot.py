#!/usr/bin/env python3
"""Tests for stall pivot (what else can I do while blocked)."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_stall_pivot as stall  # noqa: E402


class TestStallPivot(unittest.TestCase):
    def test_ready_after_threshold(self) -> None:
        state = stall.note_stall({}, "noop_backoff")
        state["stall_since_ts"] = time.time() - 5
        self.assertTrue(stall.ready_to_pivot(state))

    def test_not_ready_before_threshold(self) -> None:
        state = stall.note_stall({}, "noop_backoff")
        state["stall_since_ts"] = time.time() - 1
        self.assertFalse(stall.ready_to_pivot(state))

    def test_clear_stall_resets(self) -> None:
        state = stall.note_stall({"stall_pivot_active": True}, "noop_backoff")
        stall.clear_stall(state)
        self.assertNotIn("stall_reason", state)
        self.assertFalse(stall.ready_to_pivot(state))

    def test_alternate_items_skips_dirty_when_git_wait(self) -> None:
        items = [
            "Unblock dirty tree for peer_loop",
            "External proof: adapt + native verify on RAM",
            "Shorten hot paths — cache metrics",
        ]
        with mock.patch.object(stall.auto, "open_work_items") as ow:
            ow.return_value = stall.auto.QueueState(open_items=items, source="context")
            with mock.patch.object(stall.auto, "creative_backlog_items", return_value=[]):
                alts = stall.alternate_items("git_clean_wait", limit=3)
        self.assertTrue(all("dirty" not in a.lower() for a in alts))
        self.assertTrue(any("external proof" in a.lower() or "shorten" in a.lower() for a in alts))

    def test_pivot_prompt_asks_what_else(self) -> None:
        prefix = stall.pivot_prompt_prefix(
            "noop_backoff",
            ["Shorten hot paths"],
            4.0,
        )
        self.assertIn("what else can", prefix.lower())
        self.assertIn("Shorten hot paths", prefix)

    def test_maybe_pivot_runs_local_work(self) -> None:
        state = stall.note_stall({}, "noop_backoff")
        state["stall_since_ts"] = time.time() - 10
        logs: list[str] = []

        with mock.patch.object(stall, "run_local_pivot_work", return_value=True) as local:
            did = stall.maybe_pivot(
                state=state,
                reason="noop_backoff",
                quick=True,
                log_fn=logs.append,
                use_agent=False,
            )
        self.assertTrue(did)
        local.assert_called_once()
        self.assertTrue(any("stall pivot" in x for x in logs))

    def test_maybe_stall_adapt_audit_ttl_skips_subprocess(self) -> None:
        logs: list[str] = []
        fake_adapt = mock.MagicMock()
        fake_adapt.should_re_adapt.return_value = False
        with mock.patch.dict(sys.modules, {"automation_adapt": fake_adapt}):
            with mock.patch.object(stall, "_adapt_audit_age_sec", return_value=12.0):
                with mock.patch("subprocess.run") as run:
                    stall._maybe_stall_adapt_audit(log_fn=logs.append)
        run.assert_not_called()
        fake_adapt.detect_signals.assert_called_once()
        self.assertTrue(any("TTL-skip" in x for x in logs))

    def test_maybe_stall_adapt_audit_stale_shells(self) -> None:
        logs: list[str] = []
        fake_adapt = mock.MagicMock()
        fake_adapt.should_re_adapt.return_value = False
        proc = mock.MagicMock(returncode=0)
        with mock.patch.dict(sys.modules, {"automation_adapt": fake_adapt}):
            with mock.patch.object(stall, "_adapt_audit_age_sec", return_value=120.0):
                with mock.patch("subprocess.run", return_value=proc) as run:
                    stall._maybe_stall_adapt_audit(log_fn=logs.append)
        run.assert_called_once()
        self.assertTrue(any("adapt audit ok" in x for x in logs))

    def test_continuum_kit_fresh_after_mark(self) -> None:
        stall.mark_continuum_kit_refresh()
        self.assertTrue(stall.continuum_kit_fresh(ttl_sec=60.0))
        self.assertFalse(stall.continuum_kit_fresh(ttl_sec=0.0))

    def test_continuum_kit_fresh_accepts_slightly_future_stamp(self) -> None:
        """Legacy .3f round / clock skew → negative age must still count fresh."""
        stall.CONTINUUM_KIT_TS.parent.mkdir(parents=True, exist_ok=True)
        stall.CONTINUUM_KIT_TS.write_text(f"{time.time() + 0.05:.6f}\n", encoding="utf-8")
        self.assertTrue(stall.continuum_kit_fresh(ttl_sec=60.0))

    def test_run_local_pivot_skips_kit_when_continuum_fresh(self) -> None:
        logs: list[str] = []
        stall.mark_continuum_kit_refresh()
        fake_pl = mock.MagicMock()
        with mock.patch.dict(sys.modules, {"peer_loop": fake_pl}):
            with mock.patch.object(stall, "_maybe_stall_adapt_audit"):
                stall.run_local_pivot_work(quick=True, log_fn=logs.append)
        fake_pl._emit_worktree_inventory.assert_not_called()
        fake_pl._close_completed_asi_phase_plans.assert_not_called()
        fake_pl._prepare_continuous_prompts.assert_not_called()
        fake_pl._maybe_adapt.assert_called_once()
        self.assertTrue(any("continuum kit fresh" in x for x in logs))

    def test_run_local_pivot_runs_kit_when_stale(self) -> None:
        logs: list[str] = []
        if stall.CONTINUUM_KIT_TS.is_file():
            stall.CONTINUUM_KIT_TS.unlink()
        fake_pl = mock.MagicMock()
        with mock.patch.dict(sys.modules, {"peer_loop": fake_pl}):
            with mock.patch.object(stall, "_maybe_stall_adapt_audit"):
                stall.run_local_pivot_work(quick=True, log_fn=logs.append)
        fake_pl._emit_worktree_inventory.assert_called_once()
        fake_pl._close_completed_asi_phase_plans.assert_called_once()
        fake_pl._prepare_continuous_prompts.assert_called_once()
        self.assertTrue(stall.continuum_kit_fresh())


if __name__ == "__main__":
    unittest.main()
