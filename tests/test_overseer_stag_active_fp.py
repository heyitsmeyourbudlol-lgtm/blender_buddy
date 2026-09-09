"""OVERSEER_STATE_SAVE_PRESERVE + OVERSEER_ACTIVE_ONLY_QUEUE_FP + HEALTHY_IDLE (2026-09-04)."""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_oversight_events as events  # noqa: E402
import peer_transcript as pt  # noqa: E402


class OverseerStagActiveFpTests(unittest.TestCase):
    def test_preserve_rich_fields_on_thin_save(self) -> None:
        src = (SCRIPTS / "peer_transcript.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_STATE_SAVE_PRESERVE_LAST_CYCLE_2026_09_04", src)
        rich = {
            "last_cycle": {
                "ts": 1_700_000_000.0,
                "verify_ok": True,
                "noop": False,
                "rc": 0,
                "queue_fp": "abc",
                "git_head": "deadbeef",
                "note": "prior ok",
            },
            "last_delivery_ok_ts": 1_700_000_000.0,
            "cycle_history": [{"ts": 1_700_000_000.0, "verify_ok": True}],
        }
        thin = {"stall_reason": "noop_backoff", "stall_since_ts": 99.0}
        with mock.patch.object(pt, "_unlocked_read_state", return_value=rich):
            reason = pt._preserve_rich_fields_from_disk(thin)
        self.assertIsNotNone(reason)
        self.assertEqual(thin["last_cycle"]["note"], "prior ok")
        self.assertIn("cycle_history", thin)

    def test_metric_snapshot_active_only_skips_creative_fp(self) -> None:
        src = (SCRIPTS / "peer_oversight_events.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_ACTIVE_ONLY_QUEUE_FP_2026_09_04", src)
        self.assertIn("OVERSEER_METRIC_SNAP_LIVE_GIT_HEAD_2026_09_08", src)
        ctx = {
            "queue_count": 3,
            "queue_source": "creative",
            "phase": "WORKING",
            "last_cycle": {"noop": False, "verify_ok": True, "git_head": "abc"},
            "kit": {"factory_pct": 94, "asi_pct": 100},
        }
        with mock.patch.object(events, "_active_queue_metrics", return_value=("", 0)):
            with mock.patch("peer_transcript.load_state", return_value={}):
                snap = events.metric_snapshot(ctx, {"open": 0})
        self.assertEqual(snap["queue_count"], 0)
        self.assertEqual(snap["queue_fp"], "")
        with mock.patch.object(
            events,
            "metric_snapshot",
            return_value={
                "queue_fp": "",
                "queue_count": 0,
                "factory_pct": 95,
                "asi_pct": 100,
                "git_head": "abc",
                "verify_ok": True,
                "noop": False,
                "phase": "WORKING",
                "open_flaws": 0,
                "dispatch_allowed": True,
                "last_queue_advance_ts": 0,
                "ts": time.time(),
            },
        ):
            with mock.patch.object(events, "stagnation_cycles_threshold", return_value=2):
                with mock.patch.object(events, "scan_live_error_hits", return_value=[]):
                    rep = events.evaluate_stagnation(
                        {
                            "queue_count": 3,
                            "queue_source": "creative",
                            "phase": "WORKING",
                            "noop_backoff_sec": 0,
                            "last_cycle": {
                                "noop": False,
                                "verify_ok": True,
                                "git_head": "abc",
                                "rc": 0,
                            },
                            "kit": {
                                "factory_pct": 95,
                                "asi_pct": 100,
                                "queue_drift": 0,
                                "daemons": {"peer_loop": True, "improve_loop": True},
                                "tests_ok": True,
                                "audit_ok": True,
                            },
                            "bottlenecks": [],
                            "daemon_running": True,
                            "auth_ready": True,
                            "git_clean": False,
                            "ram": {"dispatch_allowed": True},
                        },
                        {"open": 0, "critical": 0, "high": 0},
                        state={
                            "snapshots": [
                                {"queue_fp": "creafp", "factory_pct": 94, "git_head": "abc"},
                                {"queue_fp": "creafp", "factory_pct": 94, "git_head": "abc"},
                                {"queue_fp": "creafp", "factory_pct": 94, "git_head": "abc"},
                            ]
                        },
                    )
        self.assertFalse(any("fingerprint unchanged" in r for r in rep.reasons))

    def test_metric_snapshot_live_git_head_when_last_cycle_blank(self) -> None:
        """OVERSEER_METRIC_SNAP_LIVE_GIT_HEAD_2026_09_08 — thin last_cycle fills live SHA."""
        src = (SCRIPTS / "peer_oversight_events.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_METRIC_SNAP_LIVE_GIT_HEAD_2026_09_08", src)
        ctx = {
            "queue_count": 0,
            "queue_source": "empty",
            "phase": "WORKING",
            "last_cycle": {"noop": False, "verify_ok": True, "git_head": ""},
            "kit": {"factory_pct": 100, "asi_pct": 100},
        }
        with mock.patch.object(events, "_active_queue_metrics", return_value=("", 0)):
            with mock.patch("peer_transcript.load_state", return_value={}):
                with mock.patch(
                    "peer_transcript.git_head_oneline",
                    return_value="67489f1 peer cycle: verify ok",
                ):
                    snap = events.metric_snapshot(ctx, {"open": 0})
        self.assertTrue(snap["git_head"].startswith("67489f1"))
        self.assertEqual(events._comparable_git_head(snap["git_head"]), "67489f1")

    def test_healthy_idle_skips_flat_and_head_theater(self) -> None:
        src = (SCRIPTS / "peer_oversight_events.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_HEALTHY_IDLE_NO_FLAT_STAG_2026_09_04", src)
        self.assertIn("OVERSEER_HEALTHY_IDLE_GATE_QUEUE_FP_2026_09_04", src)
        self.assertIn("OVERSEER_HEALTHY_IDLE_SNAP_FACTORY_2026_09_04", src)
        self.assertIn("def _healthy_idle_factory", src)
        self.assertIn("OVERSEER_GIT_HEAD_SENTINEL_STAG_2026_09_04", src)
        self.assertEqual(events._comparable_git_head("continue_on_dirty"), "")
        self.assertEqual(events._comparable_git_head("overseer-working"), "")
        self.assertEqual(events._comparable_git_head("06ce5c1 peer cycle"), "06ce5c1")
        ctx = {
            "queue_count": 0,
            "queue_source": "empty",
            "phase": "WORKING",
            "noop_backoff_sec": 0,
            "last_cycle": {
                "noop": False,
                "verify_ok": True,
                "git_head": "06ce5c1 peer cycle",
                "rc": 0,
            },
            "kit": {
                "factory_pct": 94,
                "asi_pct": 100,
                "queue_drift": 0,
                "daemons": {"peer_loop": True, "improve_loop": True},
                "tests_ok": True,
                "audit_ok": True,
            },
            "bottlenecks": [],
            "daemon_running": True,
            "auth_ready": True,
            "git_clean": False,
            "ram": {"dispatch_allowed": True},
        }
        state = {
            "snapshots": [
                {
                    "queue_fp": "",
                    "queue_count": 0,
                    "factory_pct": 94,
                    "asi_pct": 100,
                    "git_head": "06ce5c1 peer cycle",
                }
            ]
            * 6,
            "stagnation_cycles": 122,
        }
        with mock.patch.object(events, "stagnation_cycles_threshold", return_value=2):
            with mock.patch.object(events, "scan_live_error_hits", return_value=[]):
                with mock.patch.object(events, "_dual_brain_mismatch", return_value=False):
                    with mock.patch.object(events, "_queue_drift_count", return_value=0):
                        with mock.patch.object(
                            events, "_active_queue_metrics", return_value=("", 0)
                        ):
                            rep = events.evaluate_stagnation(
                                ctx, {"open": 0, "critical": 0, "high": 0}, state=state
                            )
        self.assertFalse(rep.stagnant)
        self.assertEqual(rep.score, 0)
        self.assertEqual(state["stagnation_cycles"], 0)
        self.assertFalse(any("flat at" in r for r in rep.reasons))
        self.assertFalse(any("HEAD unchanged" in r for r in rep.reasons))

    def test_healthy_idle_soft_deferred_no_flat_dispatch(self) -> None:
        """OVERSEER_HEALTHY_IDLE_SOFT_DEFERRED_2026_09_07 — deferred ≠ red idle veto."""
        src = (SCRIPTS / "peer_oversight_events.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_HEALTHY_IDLE_SOFT_DEFERRED_2026_09_07", src)
        self.assertIn("def _verify_ok_for_idle", src)
        # Poison pair must not count idle-green.
        self.assertFalse(
            events._verify_ok_for_idle({"verify_ok": True, "failure_type": "deferred"})
        )
        self.assertTrue(
            events._verify_ok_for_idle(
                {
                    "verify_ok": False,
                    "failure_type": "deferred",
                    "note": "verify deferred (swarm/lock)",
                    "noop": False,
                    "rc": 0,
                }
            )
        )
        ctx = {
            "queue_count": 0,
            "queue_source": "empty",
            "phase": "WAITING",
            "noop_backoff_sec": 0,
            "last_cycle": {
                "noop": False,
                "verify_ok": False,
                "failure_type": "deferred",
                "note": "verify deferred (swarm/lock)",
                "git_head": "7b6f9ae peer cycle",
                "rc": 0,
            },
            "kit": {
                "factory_pct": 100,
                "asi_pct": 100,
                "queue_drift": 0,
                "daemons": {"peer_loop": True, "improve_loop": True},
                "tests_ok": True,
                "audit_ok": True,
            },
            "bottlenecks": [],
            "daemon_running": True,
            "auth_ready": True,
            "git_clean": False,
            "ram": {"dispatch_allowed": True},
        }
        state = {
            "snapshots": [
                {
                    "queue_fp": "",
                    "queue_count": 0,
                    "factory_pct": 100,
                    "asi_pct": 100,
                    "git_head": "7b6f9ae peer cycle",
                }
            ]
            * 6,
            "stagnation_cycles": 84,
        }
        with mock.patch.object(events, "stagnation_cycles_threshold", return_value=2):
            with mock.patch.object(events, "scan_live_error_hits", return_value=[]):
                with mock.patch.object(events, "_dual_brain_mismatch", return_value=False):
                    with mock.patch.object(events, "_queue_drift_count", return_value=0):
                        with mock.patch.object(
                            events, "_active_queue_metrics", return_value=("", 0)
                        ):
                            rep = events.evaluate_stagnation(
                                ctx, {"open": 0, "critical": 0, "high": 0}, state=state
                            )
        self.assertFalse(rep.critical)
        self.assertFalse(rep.should_dispatch)
        self.assertEqual(state["stagnation_cycles"], 0)
        self.assertFalse(any("flat at" in r for r in rep.reasons))
        self.assertFalse(any("cycles without improvement" in r for r in rep.reasons))
        self.assertTrue(any("demote (healthy idle)" in r for r in rep.reasons))

    def test_healthy_idle_live_factory_and_no_noncritical_dispatch(self) -> None:
        """OVERSEER_HEALTHY_IDLE_LIVE_FACTORY + NO_DISPATCH — thin kit + hub-protect HIGH."""
        src = (SCRIPTS / "peer_oversight_events.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_HEALTHY_IDLE_LIVE_FACTORY_2026_09_04", src)
        self.assertIn("OVERSEER_HEALTHY_IDLE_NO_DISPATCH_2026_09_04", src)
        self.assertIn("_HUB_PROTECT_STAG_SKIP", src)
        ctx = {
            "queue_count": 3,
            "queue_source": "creative",
            "phase": "WORKING",
            "noop_backoff_sec": 0,
            "last_cycle": {
                "noop": False,
                "verify_ok": True,
                "git_head": "06ce5c1",
                "rc": 0,
            },
            # Thin kit — factory_pct missing (Mac clobber / mid-measure).
            "kit": {
                "asi_pct": 100,
                "queue_drift": 0,
                "daemons": {"peer_loop": True, "improve_loop": True},
                "tests_ok": True,
                "audit_ok": True,
            },
            "bottlenecks": [
                {
                    "id": "hub_protect_timer_stopped",
                    "severity": "high",
                    "title": "hub-protect timer",
                },
                {
                    "id": "adapt_stale",
                    "severity": "medium",
                    "title": "adapt fp",
                },
            ],
            "daemon_running": True,
            "auth_ready": True,
            "git_clean": False,
            "ram": {"dispatch_allowed": True},
        }
        state = {
            "snapshots": [
                {
                    "queue_fp": "",
                    "queue_count": 0,
                    "factory_pct": 96,
                    "asi_pct": 100,
                    "git_head": "06ce5c1",
                }
            ]
            * 6,
            "stagnation_cycles": 6,
        }

        class _Prog:
            pct = 96

        with mock.patch.object(events, "stagnation_cycles_threshold", return_value=2):
            with mock.patch.object(events, "scan_live_error_hits", return_value=[]):
                with mock.patch.object(events, "_dual_brain_mismatch", return_value=False):
                    with mock.patch.object(events, "_queue_drift_count", return_value=0):
                        with mock.patch.object(
                            events, "_active_queue_metrics", return_value=("", 0)
                        ):
                            with mock.patch.object(events, "high_expectations_enabled", return_value=True):
                                with mock.patch(
                                    "factory_progress.compute_report", return_value=_Prog()
                                ):
                                    rep = events.evaluate_stagnation(
                                        ctx,
                                        {"open": 0, "critical": 0, "high": 0},
                                        state=state,
                                    )
        self.assertFalse(rep.critical)
        self.assertFalse(rep.should_dispatch)
        self.assertFalse(any("high-severity bottleneck" in r for r in rep.reasons))
        self.assertFalse(any("flat at" in r for r in rep.reasons))
        self.assertEqual(state["stagnation_cycles"], 0)

    def test_stale_noop_stall_demoted_on_healthy_idle(self) -> None:
        """OVERSEER_STALE_NOOP_STALL_DEMOTE_2026_09_04 — expired backoff ≠ critical."""
        src = (SCRIPTS / "peer_oversight_events.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_STALE_NOOP_STALL_DEMOTE_2026_09_04", src)
        ctx = {
            "queue_count": 0,
            "queue_source": "empty",
            "phase": "WORKING",
            "noop_backoff_sec": 0,
            "stall_reason": "noop_backoff",
            "last_cycle": {
                "noop": False,
                "verify_ok": True,
                "git_head": "06ce5c1",
                "rc": 0,
            },
            "kit": {
                "factory_pct": 99,
                "asi_pct": 100,
                "queue_drift": 0,
                "daemons": {"peer_loop": True, "improve_loop": True},
                "tests_ok": True,
                "audit_ok": True,
            },
            "bottlenecks": [],
            "daemon_running": True,
            "auth_ready": True,
            "git_clean": False,
            "ram": {"dispatch_allowed": True},
        }
        with mock.patch.object(events, "stagnation_cycles_threshold", return_value=2):
            with mock.patch.object(events, "scan_live_error_hits", return_value=[]):
                with mock.patch.object(events, "_dual_brain_mismatch", return_value=False):
                    with mock.patch.object(events, "_queue_drift_count", return_value=0):
                        with mock.patch.object(
                            events, "_active_queue_metrics", return_value=("", 0)
                        ):
                            rep = events.evaluate_stagnation(
                                ctx,
                                {"open": 0, "critical": 0, "high": 0},
                                state={"snapshots": [], "stagnation_cycles": 0},
                            )
        self.assertFalse(rep.critical)
        self.assertTrue(any("stale stall" in r and "demote" in r for r in rep.reasons))
        self.assertFalse(any(r.startswith("stall reason:") for r in rep.reasons))

    def test_research_stale_demoted_on_healthy_idle(self) -> None:
        """OVERSEER_HEALTHY_IDLE_DEMOTE_RESEARCH_STALE_2026_09_04"""
        src = (SCRIPTS / "peer_oversight_events.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_HEALTHY_IDLE_DEMOTE_RESEARCH_STALE_2026_09_04", src)
        ctx = {
            "queue_count": 0,
            "queue_source": "empty",
            "phase": "WORKING",
            "noop_backoff_sec": 0,
            "last_cycle": {
                "noop": False,
                "verify_ok": True,
                "git_head": "06ce5c1",
                "rc": 0,
            },
            "kit": {
                "factory_pct": 99,
                "asi_pct": 100,
                "queue_drift": 0,
                "daemons": {"peer_loop": True, "improve_loop": True},
                "tests_ok": True,
                "audit_ok": True,
            },
            "bottlenecks": [],
            "daemon_running": True,
            "auth_ready": True,
            "git_clean": False,
            "ram": {"dispatch_allowed": True},
        }
        with mock.patch.object(events, "stagnation_cycles_threshold", return_value=2):
            with mock.patch.object(events, "scan_live_error_hits", return_value=[]):
                with mock.patch.object(events, "_dual_brain_mismatch", return_value=False):
                    with mock.patch.object(events, "_queue_drift_count", return_value=0):
                        with mock.patch.object(
                            events, "_active_queue_metrics", return_value=("", 0)
                        ):
                            rep = events.evaluate_stagnation(
                                ctx,
                                {"open": 0, "critical": 0, "high": 0},
                                state={"snapshots": [], "stagnation_cycles": 5},
                                extras={"repo_research_stale_sec": 2400.0},
                            )
        self.assertFalse(rep.critical)
        self.assertFalse(rep.should_dispatch)
        self.assertTrue(any("demote (healthy idle)" in r for r in rep.reasons))
        self.assertFalse(any("repo flaw research stale" in r for r in rep.reasons))

    def test_cleared_active_demotes_theater_below_factory_90(self) -> None:
        """OVERSEER_CLEARED_ACTIVE_NO_FACTORY_GATE_2026_09_04 — 88% ≠ soft storm."""
        src = (SCRIPTS / "peer_oversight_events.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_CLEARED_ACTIVE_NO_FACTORY_GATE_2026_09_04", src)
        ctx = {
            "queue_count": 3,
            "queue_source": "creative",
            "phase": "WORKING",
            "noop_backoff_sec": 0,
            "last_cycle": {
                "noop": False,
                "verify_ok": True,
                "git_head": "06ce5c1",
                "rc": 0,
            },
            "kit": {
                "factory_pct": 88,
                "asi_pct": 83,
                "queue_drift": 0,
                "daemons": {"peer_loop": True, "improve_loop": True},
                "tests_ok": True,
                "audit_ok": True,
            },
            "bottlenecks": [],
            "daemon_running": True,
            "auth_ready": True,
            "git_clean": False,
            "ram": {"dispatch_allowed": True},
        }
        state = {
            "snapshots": [
                {
                    "queue_fp": "",
                    "queue_count": 0,
                    "factory_pct": 88,
                    "asi_pct": 83,
                    "git_head": "06ce5c1",
                }
            ]
            * 6,
            "stagnation_cycles": 14,
        }
        with mock.patch.object(events, "stagnation_cycles_threshold", return_value=2):
            with mock.patch.object(events, "scan_live_error_hits", return_value=[]):
                with mock.patch.object(events, "_dual_brain_mismatch", return_value=False):
                    with mock.patch.object(events, "_queue_drift_count", return_value=0):
                        with mock.patch.object(
                            events, "_active_queue_metrics", return_value=("", 0)
                        ):
                            with mock.patch.object(
                                events, "high_expectations_enabled", return_value=True
                            ):
                                rep = events.evaluate_stagnation(
                                    ctx,
                                    {"open": 0, "critical": 0, "high": 0},
                                    state=state,
                                    extras={"repo_research_stale_sec": 3060.0},
                                )
        self.assertFalse(rep.critical)
        self.assertFalse(rep.should_dispatch)
        self.assertEqual(state["stagnation_cycles"], 0)
        self.assertFalse(any("repo flaw research stale" in r for r in rep.reasons))
        self.assertFalse(any("flat at" in r for r in rep.reasons))
        self.assertFalse(any("HEAD unchanged" in r for r in rep.reasons))
        self.assertFalse(any("fingerprint unchanged" in r for r in rep.reasons))
        self.assertTrue(any("demote (healthy idle)" in r for r in rep.reasons))

    def test_research_stale_prefers_freshest_namespace(self) -> None:
        """OVERSEER_RESEARCH_STALE_FRESHEST_NS_2026_09_04 — twin ns ≠ 57m theater."""
        src = (SCRIPTS / "peer_oversight_events.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_RESEARCH_STALE_FRESHEST_NS_2026_09_04", src)
        self.assertIn("automation-hub", src)

    def test_oversight_reloads_events_and_rebinds_hub_ns(self) -> None:
        """OVERSEER_RELOAD_EVENTS_HUB_NS_2026_09_04 — forever twin-ns soft storm."""
        src = (SCRIPTS / "peer_oversight.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_RELOAD_EVENTS_HUB_NS_2026_09_04", src)
        self.assertIn("def _refresh_oversight_runtime", src)
        self.assertIn("importlib.reload", src)


if __name__ == "__main__":
    unittest.main()
