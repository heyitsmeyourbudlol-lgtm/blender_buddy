#!/usr/bin/env python3
"""Tests for honest factory progress meter."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import factory_progress as fp  # noqa: E402
import project_automation as auto  # noqa: E402


class TestFactoryProgress(unittest.TestCase):
    def test_to_dict_has_role_and_vs_asi(self) -> None:
        prog = fp.FactoryProgress(
            pct=42,
            raw=0.42,
            label="test",
            north_star="ns",
            dimensions=[],
            blockers=["b"],
            highlights=["h"],
            as_of=1.0,
        )
        d = prog.to_dict()
        self.assertEqual(d["pct"], 42)
        self.assertEqual(d["role"], "primary_outcome_meter")
        self.assertIn("ASI", d["vs_asi"])
        self.assertEqual(d["blockers"], ["b"])

    def test_blocked_dirty_tree_lowers_dispatch(self) -> None:
        live = {"git_clean": False, "git": "dirty (40 paths)"}
        state = {
            "last_cycle": {
                "ts": 1.0,
                "verify_ok": True,
                "noop": True,
                "note": "waiting for clean tree",
            }
        }
        theater = ["crown-era time bomb philosophy"]
        with mock.patch.object(fp, "_launchctl_running", return_value=False):
            with mock.patch.object(
                fp,
                "_open_and_done_items",
                return_value=(theater, []),
            ):
                with mock.patch.object(fp, "_active_open_items", return_value=theater):
                    with mock.patch.object(
                        fp,
                        "_registry_stats",
                        return_value={
                            "total": 0,
                            "ready": 0,
                            "gaps": 0,
                            "names_ready": [],
                            "names_gap": [],
                        },
                    ):
                        with mock.patch.object(
                            fp.peer_worktree,
                            "continue_on_dirty_enabled",
                            return_value=False,
                        ):
                            prog = fp.compute_factory_progress(live=live, state=state)
        self.assertLessEqual(prog.pct, 55)
        self.assertTrue(any("dirty" in b.lower() for b in prog.blockers))
        dispatch = next(d for d in prog.dimensions if d.id == "dispatch_clear")
        self.assertLess(dispatch.score, 0.5)

    def test_backlog_deferred_does_not_count_as_active_theater(self) -> None:
        """self_sufficient deferred markers in Backlog must not tank executable_queue."""
        active = ["**Daily flaw scan** — run flaw-scan-preview"]
        all_open = active + [
            "**Irreversible artifact gate — peer success = merged diff or PR note**"
        ]
        with mock.patch.object(fp.auto, "factory_meter_mode", return_value="self_sufficient"):
            with mock.patch.object(fp, "_active_open_items", return_value=active):
                with mock.patch.object(
                    fp, "_open_and_done_items", return_value=(all_open, [])
                ):
                    self.assertTrue(fp._is_deferred(all_open[1]))
                    self.assertFalse(fp._is_deferred(active[0]))
                    theater = sum(
                        1 for t in fp._active_open_items() if fp._is_theater(t) or fp._is_deferred(t)
                    )
                    self.assertEqual(theater, 0)

    def test_deferred_markers_match_creative_newdrop_and_registry(self) -> None:
        """OVERSEER_DEFERRED_CREATIVE_MARKERS — Creative wording must count deferred."""
        with mock.patch.object(fp.auto, "factory_meter_mode", return_value="self_sufficient"):
            self.assertTrue(
                fp._is_deferred(
                    "**Newdrop native verify + worktree/PR** — resume when "
                    "factory_meter_mode=external_proof"
                )
            )
            self.assertTrue(
                fp._is_deferred(
                    "**Remaining registry native verify** — do not re-open Active "
                    "while factory_meter_mode=self_sufficient"
                )
            )
            self.assertIn(
                "OVERSEER_DEFERRED_CREATIVE_MARKERS_2026_09_04",
                Path(fp.__file__).read_text(encoding="utf-8"),
            )

    def test_empty_active_does_not_fallback_to_backlog_opens(self) -> None:
        """OVERSEER_EMPTY_ACTIVE_2026_09_03 — empty Active ≠ Backlog as Active opens."""
        backlog_only = [
            "**[efficiency-research] TTL-skip write_team_context on pre-dispatch** — demoted",
            "**[product-forge] Active — External proof on Newdrop** — Autonomous product mode",
        ]
        live = {"git_clean": True, "git": "clean"}
        state = {
            "last_cycle": {
                "ts": 1.0,
                "verify_ok": True,
                "noop": False,
                "note": "landed factory work",
            }
        }
        with mock.patch.object(fp.auto, "factory_meter_mode", return_value="self_sufficient"):
            with mock.patch.object(fp, "_active_open_items", return_value=[]):
                with mock.patch.object(
                    fp, "_open_and_done_items", return_value=(backlog_only, [])
                ):
                    with mock.patch.object(fp, "_launchctl_running", return_value=True):
                        with mock.patch.object(
                            fp,
                            "_registry_stats",
                            return_value={
                                "total": 0,
                                "ready": 0,
                                "gaps": 0,
                                "names_ready": [],
                                "names_gap": [],
                            },
                        ):
                            with mock.patch.object(
                                fp.peer_worktree,
                                "continue_on_dirty_enabled",
                                return_value=True,
                            ):
                                prog = fp.compute_factory_progress(live=live, state=state)
        eq = next(d for d in prog.dimensions if d.id == "executable_queue")
        # OVERSEER_EMPTY_ACTIVE_CLEARED_2026_09_04
        self.assertEqual(eq.evidence, "Active queue cleared (healthy idle)")
        self.assertAlmostEqual(eq.score, 1.0)

    def test_continue_on_dirty_raises_dispatch(self) -> None:
        live = {"git_clean": False, "git": "dirty (40 paths)"}
        with mock.patch.object(fp, "_launchctl_running", return_value=False):
            with mock.patch.object(fp, "_open_and_done_items", return_value=([], [])):
                with mock.patch.object(
                    fp,
                    "_registry_stats",
                    return_value={
                        "total": 0,
                        "ready": 0,
                        "gaps": 0,
                        "names_ready": [],
                        "names_gap": [],
                    },
                ):
                    with mock.patch.object(
                        fp.peer_worktree, "continue_on_dirty_enabled", return_value=True
                    ):
                        prog = fp.compute_factory_progress(live=live, state={})
        dispatch = next(d for d in prog.dimensions if d.id == "dispatch_clear")
        self.assertGreaterEqual(dispatch.score, 0.7)
        self.assertFalse(any("Dirty tree blocking" in b for b in prog.blockers))

    def test_healthy_signals_raise_pct(self) -> None:
        live = {"git_clean": True, "git": "clean"}
        state = {
            "last_cycle": {
                "ts": 1.0,
                "verify_ok": True,
                "noop": False,
                "note": "landed factory work",
            },
            "last_queue_advance_ts": 1.0,
        }

        def _lc(label: str) -> bool:
            if "ram-peer" in label:
                return False
            return bool(label)

        with mock.patch.object(fp.self_heal, "_peer_daemon_running", return_value=True):
            with mock.patch.object(fp.self_heal, "_improve_daemon_running", return_value=True):
                with mock.patch.object(fp, "_launchctl_running", side_effect=_lc):
                    with mock.patch.object(
                        fp,
                        "_open_and_done_items",
                        return_value=(
                            ["[factory:ram] External proof on RAM"],
                            [
                                "External proof on CaaS",
                                "External proof on CPT",
                                "Unblock dirty tree",
                                "native verify gate",
                            ],
                        ),
                    ):
                        with mock.patch.object(
                            fp,
                            "_registry_stats",
                            return_value={
                                "total": 3,
                                "ready": 2,
                                "gaps": 1,
                                "names_ready": ["RAM", "CaaS"],
                                "names_gap": ["CPT"],
                            },
                        ):
                            prog = fp.compute_factory_progress(live=live, state=state)
        self.assertGreaterEqual(prog.pct, 55)
        ids = {d.id for d in prog.dimensions}
        self.assertIn("dispatch_clear", ids)
        self.assertTrue(
            "self_sufficiency" in ids or "external_proof" in ids,
            ids,
        )
        dispatch = next(d for d in prog.dimensions if d.id == "dispatch_clear")
        self.assertEqual(dispatch.score, 1.0)

    def test_systemd_peer_daemon_raises_single_brain(self) -> None:
        live = {"git_clean": True, "git": "clean"}
        state = {
            "last_cycle": {"ts": 1.0, "verify_ok": True, "noop": False, "note": "ok"},
        }
        with mock.patch.object(fp.self_heal, "_peer_daemon_running", return_value=True):
            with mock.patch.object(fp.self_heal, "_improve_daemon_running", return_value=True):
                with mock.patch.object(
                    fp.self_heal,
                    "dual_namespace_collision",
                    return_value={"peer": [], "improve": []},
                ):
                    with mock.patch.object(fp, "_open_and_done_items", return_value=([], [])):
                        with mock.patch.object(
                            fp,
                            "_registry_stats",
                            return_value={
                                "total": 0,
                                "ready": 0,
                                "gaps": 0,
                                "names_ready": [],
                                "names_gap": [],
                            },
                        ):
                            prog = fp.compute_factory_progress(live=live, state=state)
        brain = next(d for d in prog.dimensions if d.id == "single_brain")
        self.assertEqual(brain.score, 1.0)
        self.assertNotIn("Hub peer daemon down", prog.blockers)

    def test_launchctl_plist_style_pid(self) -> None:
        plist_out = '{\n\t"PID" = 12345;\n\t"Label" = "com.togi.x";\n};\n'
        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout=plist_out, stderr="")
            self.assertTrue(fp._launchctl_running("com.togi.x"))
        no_pid = '{\n\t"LastExitStatus" = 0;\n\t"Label" = "com.togi.x";\n};\n'
        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout=no_pid, stderr="")
            self.assertFalse(fp._launchctl_running("com.togi.x"))

    def test_recent_delivery_not_regressed_on_soft_tick(self) -> None:
        live = {"git_clean": True, "git": "clean"}
        now = time.time()
        state = {
            "last_cycle": {
                "ts": now,
                "verify_ok": True,
                "noop": True,
                "note": "agent noop",
            },
            "last_delivery_ok_ts": now - 600,
            "factory_progress_peak": {"pct": 71, "raw": 0.71},
        }
        with mock.patch.object(fp, "time") as t:
            t.time.return_value = now
            with mock.patch.object(fp.self_heal, "_peer_daemon_running", return_value=True):
                with mock.patch.object(fp.self_heal, "_improve_daemon_running", return_value=True):
                    with mock.patch.object(fp, "_open_and_done_items", return_value=([], [])):
                        with mock.patch.object(
                            fp,
                            "_registry_stats",
                            return_value={
                                "total": 0,
                                "ready": 0,
                                "gaps": 0,
                                "names_ready": [],
                                "names_gap": [],
                            },
                        ):
                            prog = fp.compute_factory_progress(live=live, state=state)
        delivery = next(d for d in prog.dimensions if d.id == "delivery")
        self.assertGreaterEqual(delivery.score, 0.85)
        self.assertGreaterEqual(prog.pct, 71)

    def test_self_sufficient_mode_uses_self_sufficiency_dimension(self) -> None:
        with mock.patch.object(auto, "factory_meter_mode", return_value="self_sufficient"):
            with mock.patch.object(fp.self_heal, "_peer_daemon_running", return_value=True):
                with mock.patch.object(fp.self_heal, "_improve_daemon_running", return_value=True):
                    with mock.patch.object(fp, "_open_and_done_items", return_value=([], [])):
                        with mock.patch.object(
                            fp,
                            "_registry_stats",
                            return_value={
                                "total": 0,
                                "ready": 0,
                                "gaps": 0,
                                "names_ready": [],
                                "names_gap": [],
                            },
                        ):
                            with mock.patch.object(
                                fp.asi_rubric,
                                "_log_has_recent_any",
                                return_value=(True, "wake ok"),
                            ):
                                with mock.patch.object(
                                    fp.self_heal,
                                    "scan_bottlenecks",
                                    return_value=[],
                                ):
                                    live = {"git_clean": True, "git": "clean"}
                                    state = {
                                        "last_cycle": {
                                            "ts": time.time(),
                                            "verify_ok": True,
                                            "noop": False,
                                        }
                                    }
                                    prog = fp.compute_factory_progress(live=live, state=state)
        ids = {d.id for d in prog.dimensions}
        self.assertIn("self_sufficiency", ids)
        self.assertNotIn("external_proof", ids)
        self.assertFalse(
            any("external proof" in b.lower() for b in prog.blockers),
            prog.blockers,
        )

    def test_healthy_idle_wake_credit_when_log_stale(self) -> None:
        """OVERSEER_HEALTHY_IDLE_WAKE_CREDIT_2026_09_04 — empty Active + improve up."""
        with mock.patch.object(auto, "factory_meter_mode", return_value="self_sufficient"):
            with mock.patch.object(fp.self_heal, "_peer_daemon_running", return_value=True):
                with mock.patch.object(fp.self_heal, "_improve_daemon_running", return_value=True):
                    with mock.patch.object(fp, "_open_and_done_items", return_value=([], [])):
                        with mock.patch.object(fp, "_active_open_items", return_value=[]):
                            with mock.patch.object(
                                fp,
                                "_registry_stats",
                                return_value={
                                    "total": 0,
                                    "ready": 0,
                                    "gaps": 0,
                                    "names_ready": [],
                                    "names_gap": [],
                                },
                            ):
                                with mock.patch.object(
                                    fp.asi_rubric,
                                    "_log_has_recent_any",
                                    return_value=(False, "improve-loop.log stale (2000s)"),
                                ):
                                    with mock.patch.object(
                                        fp.self_heal,
                                        "scan_bottlenecks",
                                        return_value=[],
                                    ):
                                        live = {"git_clean": True, "git": "clean"}
                                        state = {
                                            "last_cycle": {
                                                "ts": time.time(),
                                                "verify_ok": True,
                                                "noop": False,
                                            }
                                        }
                                        prog = fp.compute_factory_progress(
                                            live=live, state=state
                                        )
        ss = next(d for d in prog.dimensions if d.id == "self_sufficiency")
        self.assertGreaterEqual(ss.score, 0.95)
        self.assertIn("healthy idle", ss.evidence.lower())
        self.assertFalse(
            any("not waking peer" in b.lower() for b in prog.blockers),
            prog.blockers,
        )

    def test_format_progress_text_mentions_asi_distinction(self) -> None:
        prog = fp.FactoryProgress(
            pct=10,
            raw=0.1,
            label="low",
            north_star="ns",
            dimensions=[],
            blockers=["x"],
            highlights=[],
            as_of=0,
        )
        text = fp.format_progress_text(prog)
        self.assertIn("Factory progress", text)
        self.assertIn("ASI", text)

    def test_improve_log_path_prefers_freshest_peer_ns(self) -> None:
        """OVERSEER_IMPROVE_LOG_PEER_NS_2026_09_04 — peer-* wake must count."""
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cfg = home / ".config"
            hub = cfg / "automation-hub"
            peer = cfg / "peer-6"
            hub.mkdir(parents=True)
            peer.mkdir(parents=True)
            hub_log = hub / "improve-loop.log"
            peer_log = peer / "improve-loop.log"
            hub_log.write_text("old\n")
            peer_log.write_text("wake peer: fresh\n")
            older = time.time() - 3600
            newer = time.time()
            os.utime(hub_log, (older, older))
            os.utime(peer_log, (newer, newer))
            with mock.patch.object(fp.Path, "home", return_value=home):
                with mock.patch.object(fp, "IMPROVE_LOG", hub_log):
                    chosen = fp._improve_log_path()
            self.assertEqual(chosen.resolve(), peer_log.resolve())


if __name__ == "__main__":
    unittest.main()
