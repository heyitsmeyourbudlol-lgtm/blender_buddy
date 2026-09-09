#!/usr/bin/env python3
"""Tests for honest factory progress meter."""

from __future__ import annotations

import json
import os
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

    def test_kit_run_registry_target_not_deferred_theater(self) -> None:
        """OVERSEER_KIT_RUN_NOT_DEFERRED_2026_09_07 — Active kit-run ≠ theater."""
        with mock.patch.object(fp.auto, "factory_meter_mode", return_value="self_sufficient"):
            kit = (
                "**[factory] Kit-run third registry target** — pick next "
                "repos/registry.json target with .git on CLEAN; `./scripts/peer kit-run`"
            )
            self.assertFalse(fp._is_deferred(kit))
            self.assertNotIn("registry target", fp._DEFERRED_MARKERS)
            self.assertIn(
                "OVERSEER_KIT_RUN_NOT_DEFERRED_2026_09_07",
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

    def test_t10_08_dirty_hub_coding_wt_dispatch_ge_95(self) -> None:
        """OVERSEER_T10_08_CODING_WT_DISPATCH_2026_09_07 — Active open + coding wt ≥95%."""
        live = {"git_clean": False, "git": "dirty (242 paths)"}
        active = ["**[top10] TOP10_NEXT T10-04 non-noop ≥8/day** — keep shipping"]
        with mock.patch.object(fp, "_launchctl_running", return_value=True):
            with mock.patch.object(fp, "_active_open_items", return_value=active):
                with mock.patch.object(
                    fp, "_open_and_done_items", return_value=(active, [])
                ):
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
                            with mock.patch.object(
                                fp.peer_worktree,
                                "coding_worktree_config",
                                return_value=("coding-wt", "coding"),
                            ):
                                with mock.patch.object(fp, "ROOT", Path("/tmp")):
                                    (Path("/tmp") / "coding-wt").mkdir(
                                        parents=True, exist_ok=True
                                    )
                                    prog = fp.compute_factory_progress(
                                        live=live, state={}
                                    )
        dispatch = next(d for d in prog.dimensions if d.id == "dispatch_clear")
        self.assertGreaterEqual(dispatch.score, 0.95)
        self.assertIn("coding worktree present", dispatch.evidence)
        self.assertNotIn("healthy idle", dispatch.evidence)
        self.assertIn(
            "OVERSEER_T10_08_CODING_WT_DISPATCH_2026_09_07",
            Path(fp.__file__).read_text(encoding="utf-8"),
        )

    def test_healthy_idle_cod_is_full_dispatch_clear(self) -> None:
        """OVERSEER_HEALTHY_IDLE_DISPATCH_FULL_2026_09_07 — no 0.95 ceiling."""
        live = {"git_clean": False, "git": "dirty (37 paths)"}
        coding = Path("/tmp/factory-progress-coding-wt")
        coding.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(fp, "_launchctl_running", return_value=True):
            with mock.patch.object(fp, "_active_open_items", return_value=[]):
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
                            fp.peer_worktree,
                            "continue_on_dirty_enabled",
                            return_value=True,
                        ):
                            with mock.patch.object(
                                fp.peer_worktree,
                                "coding_worktree_config",
                                return_value=("coding-wt", "coding"),
                            ):
                                with mock.patch.object(fp, "ROOT", Path("/tmp")):
                                    # Resolve coding_wt = ROOT/rel → /tmp/coding-wt
                                    (Path("/tmp") / "coding-wt").mkdir(
                                        parents=True, exist_ok=True
                                    )
                                    prog = fp.compute_factory_progress(
                                        live=live, state={}
                                    )
        dispatch = next(d for d in prog.dimensions if d.id == "dispatch_clear")
        self.assertAlmostEqual(dispatch.score, 1.0)
        self.assertIn("healthy idle", dispatch.evidence)

    def test_soft_deferred_recent_delivery_full_credit(self) -> None:
        """OVERSEER_DELIVERY_RECENT_SOFT_DEFERRED_2026_09_07 — ~61m still 1.0."""
        import time

        live = {"git_clean": True, "git": "clean"}
        now = time.time()
        state = {
            "last_cycle": {
                "ts": now,
                "verify_ok": False,
                "noop": False,
                "failure_type": "deferred",
                "note": "verify deferred (swarm/lock)",
            },
            "last_delivery_ok_ts": now - 3700.0,  # ~1.03h — display rounds to 1.0h
        }
        with mock.patch.object(fp.self_heal, "_peer_daemon_running", return_value=True):
            with mock.patch.object(
                fp.self_heal, "_improve_daemon_running", return_value=True
            ):
                with mock.patch.object(fp, "_launchctl_running", return_value=True):
                    with mock.patch.object(
                        fp, "_open_and_done_items", return_value=([], [])
                    ):
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
        self.assertAlmostEqual(delivery.score, 1.0)
        self.assertIn("soft deferred", delivery.evidence)

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
        """Darwin plist PID parser — force darwin path (Linux shares ASI TTL)."""
        plist_out = '{\n\t"PID" = 12345;\n\t"Label" = "com.togi.x";\n};\n'
        with mock.patch.object(fp.sys, "platform", "darwin"), mock.patch(
            "subprocess.run"
        ) as run:
            run.return_value = mock.Mock(returncode=0, stdout=plist_out, stderr="")
            self.assertTrue(fp._launchctl_running("com.togi.x"))
        no_pid = '{\n\t"LastExitStatus" = 0;\n\t"Label" = "com.togi.x";\n};\n'
        with mock.patch.object(fp.sys, "platform", "darwin"), mock.patch(
            "subprocess.run"
        ) as run:
            run.return_value = mock.Mock(returncode=0, stdout=no_pid, stderr="")
            self.assertFalse(fp._launchctl_running("com.togi.x"))

    def test_linux_launchctl_shares_asi_daemon_ttl(self) -> None:
        """FACTORY_DAEMON_PROBE_SHARE_ASI_TTL — Linux delegates to asi TTL cache."""
        if not hasattr(fp.asi_rubric, "clear_daemon_probe_cache"):
            self.skipTest("asi daemon TTL missing")
        fp.asi_rubric.clear_daemon_probe_cache()
        label = "com.togi.automation-hub-oversight-loop"
        calls = {"n": 0}

        def fake_asi(lab: str, *, now: float | None = None) -> bool:
            calls["n"] += 1
            return True

        with mock.patch.object(fp.sys, "platform", "linux"), mock.patch.object(
            fp.asi_rubric, "_launchctl_running", side_effect=fake_asi
        ):
            self.assertTrue(fp._launchctl_running(label))
            self.assertEqual(calls["n"], 1)
            self.assertTrue(fp._launchctl_running(label))
            self.assertEqual(calls["n"], 2)  # delegate each call; ASI owns TTL
        self.assertIn(
            "FACTORY_DAEMON_PROBE_SHARE_ASI_TTL_2026_09_08",
            (fp.SCRIPTS / "factory_progress.py").read_text(encoding="utf-8"),
        )
        fp.asi_rubric.clear_daemon_probe_cache()

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
        with mock.patch.object(fp.time, "time", return_value=now):
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

        fp.clear_improve_log_path_cache()
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
        self.assertIn(
            "IMPROVE_LOG_PATH_TARGETED_SCANDIR_2026_09_08",
            (ROOT / "scripts" / "factory_progress.py").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "IMPROVE_LOG_PATH_CANDIDATE_STRSET_2026_09_08",
            (ROOT / "scripts" / "factory_progress.py").read_text(encoding="utf-8"),
        )
        fp.clear_improve_log_path_cache()

    def test_improve_log_path_ttl_hit_skips_scandir(self) -> None:
        """IMPROVE_LOG_PATH_BOUNDED_PEERS — cold miss skips ~/.config scandir; TTL HIT free."""
        fp.clear_improve_log_path_cache()
        calls = {"n": 0}
        real_scandir = os.scandir

        def counting_scandir(path):
            calls["n"] += 1
            return real_scandir(path)

        with mock.patch.object(fp.os, "scandir", side_effect=counting_scandir):
            a = fp._improve_log_path()
            self.assertEqual(calls["n"], 0)  # BOUNDED_PEERS — no full scandir
            b = fp._improve_log_path()
            self.assertEqual(calls["n"], 0)
            self.assertEqual(a, b)
            fp._IMPROVE_LOG_PATH_CACHE["at"] = time.monotonic() - (
                fp._IMPROVE_LOG_PATH_TTL_SEC + 1.0
            )
            fp._improve_log_path()
            self.assertEqual(calls["n"], 0)
        self.assertIn(
            "IMPROVE_LOG_PATH_BOUNDED_PEERS_2026_09_08",
            (ROOT / "scripts" / "factory_progress.py").read_text(encoding="utf-8"),
        )
        fp.clear_improve_log_path_cache()

    def test_improve_log_path_bounded_peers_no_scandir(self) -> None:
        """IMPROVE_LOG_PATH_BOUNDED_PEERS_2026_09_08 — miss uses peer-0..N only."""
        fp.clear_improve_log_path_cache()
        with mock.patch.object(
            fp.os, "scandir", side_effect=AssertionError("scandir forbidden")
        ):
            chosen = fp._improve_log_path()
        self.assertTrue(chosen.name == "improve-loop.log" or chosen == fp.IMPROVE_LOG)
        self.assertGreaterEqual(fp._improve_log_peer_slot_cap(), 8)
        self.assertIn(
            "IMPROVE_LOG_PATH_BOUNDED_PEERS_2026_09_08",
            (ROOT / "scripts" / "factory_progress.py").read_text(encoding="utf-8"),
        )
        fp.clear_improve_log_path_cache()

    def test_improve_log_path_candidate_strset_and_clear_keeps_ttl(self) -> None:
        """IMPROVE_LOG_PATH_CANDIDATE_STRSET + FACTORY_CLEAR_KEEP_IMPROVE_LOG_TTL."""
        src = (ROOT / "scripts" / "factory_progress.py").read_text(encoding="utf-8")
        self.assertIn("IMPROVE_LOG_PATH_CANDIDATE_STRSET_2026_09_08", src)
        self.assertIn("FACTORY_CLEAR_KEEP_IMPROVE_LOG_TTL_2026_09_08", src)
        self.assertIn("statmod.S_ISREG", src)
        fp.clear_improve_log_path_cache()
        chosen = fp._improve_log_path()
        at = fp._IMPROVE_LOG_PATH_CACHE.get("at")
        fp.clear_factory_progress_cache()
        self.assertIs(fp._IMPROVE_LOG_PATH_CACHE.get("path"), chosen)
        self.assertEqual(fp._IMPROVE_LOG_PATH_CACHE.get("at"), at)
        # TTL HIT must not re-scandir after generation clear.
        with mock.patch.object(
            fp.os, "scandir", side_effect=AssertionError("scandir after clear_factory")
        ):
            again = fp._improve_log_path()
        self.assertEqual(again, chosen)
        fp.clear_improve_log_path_cache()

    def test_throughput_non_noop_rate_and_cph(self) -> None:
        """OVERSEER_FACTORY_THROUGHPUT_2026_09_07 — live mass×speed fields."""
        now = time.time()
        state = {
            "last_cycle": {
                "ts": now - 60,
                "verify_ok": True,
                "noop": False,
                "note": "landed",
            },
            "cycle_history": [
                {"ts": now - 3000, "noop": True, "verify_ok": True},
                {"ts": now - 1800, "noop": False, "verify_ok": True},
                {"ts": now - 900, "noop": False, "verify_ok": True},
                {"ts": now - 60, "noop": False, "verify_ok": True},
            ],
        }
        board = {
            "worker_target": 8,
            "summary": {"active_agents": 3, "total_agents": 8, "phase": "WORKING"},
        }
        with mock.patch.object(fp, "_active_open_items", return_value=["a", "b"]):
            with mock.patch.object(fp, "_mac_offloaded", return_value=False):
                tp = fp.compute_throughput(
                    state=state, agents_board=board, now=now, window_sec=3600.0
                )
        self.assertEqual(tp["window_cycles"], 4)
        self.assertAlmostEqual(tp["non_noop_rate"], 0.75, places=2)
        self.assertEqual(tp["open_active"], 2)
        self.assertEqual(tp["parallel_busy"], 3)
        self.assertEqual(tp["parallel_target"], 8)
        self.assertIsNotNone(tp["last_cycle_age_sec"])
        self.assertLess(tp["last_cycle_age_sec"], 120)
        self.assertIsNotNone(tp["median_cycle_latency_sec"])
        self.assertIn("cycles_per_hour", tp)
        self.assertIn("mass_speed", tp)
        # 3 non-noop in 1h → 3.0 ≥ bar 2.0 and rate 0.75 ≥ 0.5
        self.assertTrue(tp["efficient"], tp["efficiency_label"])

    def test_throughput_brain_clean_when_mac_offloaded(self) -> None:
        now = time.time()
        state = {
            "last_cycle": {"ts": now - 30, "verify_ok": True, "noop": False},
            "cycle_history": [],
        }
        with mock.patch.object(fp, "_active_open_items", return_value=[]):
            with mock.patch.object(fp, "_mac_offloaded", return_value=True):
                tp = fp.compute_throughput(state=state, now=now)
        self.assertEqual(tp["brain"], "CLEAN")
        self.assertTrue(tp["mac_offloaded"])
        self.assertIn("false-negative", tp["brain_note"])
        self.assertTrue(tp["efficient"], tp["efficiency_label"])

    def test_mac_offloaded_credits_clean_peer_improve(self) -> None:
        """Local LaunchAgent down must not tank factory when CLEAN owns the loops."""
        live = {"git_clean": True, "git": "clean"}
        now = time.time()
        state = {
            "last_cycle": {
                "ts": now,
                "verify_ok": True,
                "noop": False,
                "note": "ok",
            },
            "last_delivery_ok_ts": now,
            "cycle_history": [{"ts": now, "noop": False, "verify_ok": True}],
        }
        with mock.patch.object(fp, "_mac_offloaded", return_value=True):
            with mock.patch.object(
                fp,
                "_clean_peer_improve_active",
                return_value=(True, True, "CLEAN peer-loop=active improve-loop=active"),
            ):
                with mock.patch.object(fp, "_launchctl_running", return_value=False):
                    with mock.patch.object(
                        fp.self_heal, "_peer_daemon_running", return_value=False
                    ):
                        with mock.patch.object(
                            fp.self_heal, "_improve_daemon_running", return_value=False
                        ):
                            with mock.patch.object(
                                fp, "_open_and_done_items", return_value=([], [])
                            ):
                                with mock.patch.object(
                                    fp, "_active_open_items", return_value=[]
                                ):
                                    with mock.patch.object(
                                        fp,
                                        "_registry_stats",
                                        return_value={
                                            "total": 1,
                                            "ready": 1,
                                            "gaps": 0,
                                            "names_ready": ["x"],
                                            "names_gap": [],
                                        },
                                    ):
                                        with mock.patch.object(
                                            fp.self_heal,
                                            "scan_bottlenecks",
                                            return_value=[],
                                        ):
                                            with mock.patch.object(
                                                fp.self_heal,
                                                "dual_namespace_collision",
                                                return_value={},
                                            ):
                                                prog = fp.compute_factory_progress(
                                                    live=live, state=state
                                                )
        brain = next(d for d in prog.dimensions if d.id == "single_brain")
        self.assertEqual(brain.score, 1.0)
        self.assertTrue(
            any("CLEAN" in h for h in prog.highlights),
            prog.highlights,
        )
        self.assertFalse(
            any("daemons down" in b.lower() for b in prog.blockers),
            prog.blockers,
        )

    def test_factory_to_dict_includes_throughput(self) -> None:
        live = {"git_clean": True, "git": "clean"}
        now = time.time()
        state = {
            "last_cycle": {
                "ts": now,
                "verify_ok": True,
                "noop": False,
                "note": "ok",
            },
            "cycle_history": [
                {"ts": now - 100, "noop": False, "verify_ok": True},
                {"ts": now, "noop": False, "verify_ok": True},
            ],
            "last_delivery_ok_ts": now,
        }
        with mock.patch.object(fp, "_launchctl_running", return_value=False):
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
                            fp.self_heal,
                            "_peer_daemon_running",
                            return_value=True,
                        ):
                            with mock.patch.object(
                                fp.self_heal,
                                "_improve_daemon_running",
                                return_value=True,
                            ):
                                with mock.patch.object(
                                    fp.self_heal,
                                    "dual_namespace_collision",
                                    return_value={"peer": False, "improve": False},
                                ):
                                    with mock.patch.object(
                                        fp.self_heal,
                                        "scan_bottlenecks",
                                        return_value=[],
                                    ):
                                        with mock.patch.object(
                                            fp,
                                            "_mac_offloaded",
                                            return_value=False,
                                        ):
                                            prog = fp.compute_factory_progress(
                                                live=live,
                                                state=state,
                                                daemons={
                                                    "peer_loop": True,
                                                    "improve_loop": True,
                                                },
                                            )
        d = prog.to_dict()
        self.assertIn("throughput", d)
        self.assertIn("non_noop_rate", d["throughput"])
        self.assertIn("brain", d["throughput"])

    def test_factory_progress_generation_cache_hit(self) -> None:
        """FACTORY_PROGRESS_GENERATION_2026_09_05 hub port — default-path memo."""
        fp.clear_factory_progress_cache()
        first = fp.compute_factory_progress()
        second = fp.compute_factory_progress()
        self.assertIs(first, second)
        fp.clear_factory_progress_cache()
        third = fp.compute_factory_progress()
        self.assertIsNot(third, first)
        # Explicit state bypasses memo (tests / peak persist).
        bypass = fp.compute_factory_progress(state={"last_cycle": {}})
        self.assertIsNot(bypass, third)

    def test_active_open_items_generation_hit(self) -> None:
        """ACTIVE_OPEN_WQ_MTIME_GENERATION_2026_09_08 — close_landed once per WQ mtime."""
        fp.clear_active_open_items_cache()
        calls = {"n": 0}
        orig = auto.close_landed_done_orphans

        def _wrap(md: str):
            calls["n"] += 1
            return orig(md)

        with mock.patch.object(auto, "close_landed_done_orphans", side_effect=_wrap):
            a = fp._active_open_items()
            b = fp._active_open_items()
            self.assertEqual(calls["n"], 1)
            self.assertEqual(a, b)
            fp.clear_active_open_items_cache()
            c = fp._active_open_items()
            self.assertEqual(calls["n"], 2)
            self.assertEqual(c, a)
        self.assertIn(
            "ACTIVE_OPEN_WQ_MTIME_GENERATION_2026_09_08",
            (ROOT / "scripts" / "factory_progress.py").read_text(encoding="utf-8"),
        )

    def test_open_and_done_index_share_mtime_hit(self) -> None:
        """OPEN_AND_DONE_QUEUE_MD_INDEX_SHARE_2026_09_08 — index + mtime memo."""
        fp.clear_open_and_done_items_cache()
        auto.clear_queue_md_index_cache()
        md = (
            "## Active\n"
            "- [ ] **alpha task** — file-scoped `scripts/factory_progress.py`\n"
            "## Backlog\n"
            "- [ ] **beta backlog** — deferred\n"
            "## Done\n"
            "- [x] **gamma done** — landed\n"
        )
        ctx = "## Remaining work (priority order)\n- [ ] **delta remaining**\n"
        calls = {"n": 0}
        orig = auto._queue_md_index

        def _wrap(blob: str):
            calls["n"] += 1
            return orig(blob)

        with mock.patch.object(auto, "load_work_queue_md", return_value=md):
            with mock.patch.object(auto, "load_context_md", return_value=ctx):
                with mock.patch.object(auto, "_queue_md_index", side_effect=_wrap):
                    o1, d1 = fp._open_and_done_items()
                    o2, d2 = fp._open_and_done_items()
                    self.assertEqual(calls["n"], 1)
                    self.assertEqual(o1, o2)
                    self.assertEqual(d1, d2)
                    fp.clear_open_and_done_items_cache()
                    o3, d3 = fp._open_and_done_items()
                    self.assertEqual(calls["n"], 2)
                    self.assertEqual(o3, o1)
                    self.assertEqual(d3, d1)
        self.assertTrue(any("alpha" in x for x in o1))
        self.assertTrue(any("beta" in x for x in o1))
        self.assertTrue(any("delta" in x for x in o1))
        self.assertTrue(any("gamma" in x for x in d1))
        self.assertIn(
            "OPEN_AND_DONE_QUEUE_MD_INDEX_SHARE_2026_09_08",
            (ROOT / "scripts" / "factory_progress.py").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "OPEN_AND_DONE_QUEUE_MD_INDEX_SHARE_2026_09_08",
            (ROOT / "scripts" / "project_automation.py").read_text(encoding="utf-8"),
        )

    def test_mac_offloaded_ttl_hit(self) -> None:
        """MAC_OFFLOADED_TTL_2026_09_08 — TTL HIT skips marker remiss."""
        fp.clear_mac_offloaded_cache()
        fp._MAC_OFFLOADED_CACHE["at"] = time.monotonic()
        fp._MAC_OFFLOADED_CACHE["val"] = False
        with mock.patch.object(Path, "is_file", side_effect=AssertionError("no remiss")):
            self.assertFalse(fp._mac_offloaded())
        fp.clear_mac_offloaded_cache()
        fp._MAC_OFFLOADED_CACHE["at"] = time.monotonic()
        fp._MAC_OFFLOADED_CACHE["val"] = True
        with mock.patch.object(Path, "is_file", side_effect=AssertionError("no remiss")):
            self.assertTrue(fp._mac_offloaded())
        fp.clear_mac_offloaded_cache()
        self.assertIn(
            "MAC_OFFLOADED_TTL_2026_09_08",
            (ROOT / "scripts" / "factory_progress.py").read_text(encoding="utf-8"),
        )

    def test_improve_log_path_candidate_strset_no_path_eq(self) -> None:
        """IMPROVE_LOG_PATH_CANDIDATE_STRSET — cold miss must not Path.__eq__-storm."""
        fp.clear_improve_log_path_cache()
        eq = {"n": 0}
        orig = Path.__eq__

        def counting_eq(self, other):  # noqa: ANN001
            eq["n"] += 1
            return orig(self, other)

        Path.__eq__ = counting_eq  # type: ignore[method-assign]
        try:
            chosen = fp._improve_log_path()
        finally:
            Path.__eq__ = orig  # type: ignore[method-assign]
        self.assertIsInstance(chosen, Path)
        self.assertEqual(eq["n"], 0)
        self.assertIn(
            "IMPROVE_LOG_PATH_CANDIDATE_STRSET_2026_09_08",
            (ROOT / "scripts" / "factory_progress.py").read_text(encoding="utf-8"),
        )
        fp.clear_improve_log_path_cache()

    def test_registry_stats_mtime_memo_hit(self) -> None:
        """REGISTRY_STATS_MTIME_MEMO_2026_09_08 — WQ remiss skips registry JSON parse."""
        fp.clear_registry_stats_cache()
        calls = {"n": 0}
        real_loads = json.loads

        def counting_loads(s, *a, **k):
            calls["n"] += 1
            return real_loads(s, *a, **k)

        with mock.patch.object(fp.json, "loads", side_effect=counting_loads):
            a = fp._registry_stats()
            b = fp._registry_stats()
            self.assertEqual(calls["n"], 1)
            self.assertEqual(a, b)
            fp.clear_registry_stats_cache()
            c = fp._registry_stats()
            self.assertEqual(calls["n"], 2)
            self.assertEqual(c.get("total"), a.get("total"))
        self.assertIn(
            "REGISTRY_STATS_MTIME_MEMO_2026_09_08",
            (ROOT / "scripts" / "factory_progress.py").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "FACTORY_CLEAR_KEEP_IMPROVE_LOG_TTL_2026_09_08",
            (ROOT / "scripts" / "factory_progress.py").read_text(encoding="utf-8"),
        )

    def test_factory_state_scrub_poison_light_no_transcript(self) -> None:
        """FACTORY_STATE_SCRUB_POISON_LIGHT — meter load skips peer_transcript import."""
        src = (ROOT / "scripts" / "factory_progress.py").read_text(encoding="utf-8")
        self.assertIn("FACTORY_STATE_SCRUB_POISON_LIGHT_2026_09_08", src)
        self.assertIn("FACTORY_MAC_OFFLOAD_LINUX_NO_DGX_IMPORT_2026_09_08", src)
        self.assertIn("peer_last_cycle_poison", src)
        # _scrub_state_dict / _load_state_with_source must not import peer_transcript
        scrub_src = fp._scrub_state_dict.__doc__ or ""
        self.assertIn("peer_transcript", scrub_src)
        poisoned = {
            "last_cycle": {
                "verify_ok": True,
                "failure_type": "deferred",
                "ts": 100.0,
                "note": "soft",
            }
        }
        scrubbed = fp._scrub_state_dict(poisoned)
        lc = scrubbed.get("last_cycle") or {}
        self.assertIs(lc.get("verify_ok"), False)
        self.assertEqual(str(lc.get("failure_type") or ""), "deferred")
        # Linux: absent marker → False without dgx_watch
        fp.clear_mac_offloaded_cache()
        with mock.patch.object(fp.sys, "platform", "linux"):
            with mock.patch.dict(sys.modules, {"dgx_watch": None}):
                # Ensure import would fail if attempted
                real_import = __import__

                def block_dgx(name, *a, **k):
                    if name == "dgx_watch":
                        raise AssertionError("dgx_watch import forbidden on Linux")
                    return real_import(name, *a, **k)

                with mock.patch("builtins.__import__", side_effect=block_dgx):
                    self.assertFalse(fp._mac_offloaded())
        fp.clear_mac_offloaded_cache()

    def test_factory_progress_accepts_quick_kw(self) -> None:
        """FACTORY_PROGRESS_QUICK_KW_2026_09_05 — team_status/debrief pass quick=."""
        fp.clear_factory_progress_cache()
        with_quick = fp.compute_factory_progress(quick=True)
        again = fp.compute_factory_progress(quick=True)
        self.assertIs(with_quick, again)
        self.assertIsInstance(with_quick.pct, int)


if __name__ == "__main__":
    unittest.main()
