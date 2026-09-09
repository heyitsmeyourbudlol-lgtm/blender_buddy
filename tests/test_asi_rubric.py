#!/usr/bin/env python3
"""Tests for phased ASI rubric."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import asi_rubric  # noqa: E402
import automation_improve as improve  # noqa: E402


class TestAsiRubric(unittest.TestCase):
    def test_phases_defined(self) -> None:
        self.assertGreaterEqual(len(asi_rubric.ASI_PHASES), 4)
        completable = [p for p in asi_rubric.ASI_PHASES if p.completable]
        self.assertEqual(len(completable), 4)

    def test_empty_signals_low_pct(self) -> None:
        signals = improve.ImproveSignals(
            live={},
            audit_ok=False,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
        )
        result = asi_rubric.compute_asi_rubric(signals)
        self.assertLess(result.pct, 50)
        self.assertGreaterEqual(result.pct, 0)
        self.assertTrue(result.phases)
        self.assertTrue(result.current_phase_id)
        self.assertIsNotNone(result.next_plan)

    def test_last_cycle_improves_phase1_partial(self) -> None:
        signals = improve.ImproveSignals(
            live={},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={
                "last_cycle": {
                    "ts": 1.0,
                    "verify_ok": True,
                    "noop": False,
                }
            },
        )
        with mock.patch.object(asi_rubric, "_launchctl_running", return_value=True):
            with mock.patch.object(
                asi_rubric,
                "_log_has_recent",
                return_value=(True, "log ok"),
            ):
                result = asi_rubric.compute_asi_rubric(signals)
        phase1 = next(p for p in result.phases if p["id"] == "grounded_loop")
        self.assertGreater(phase1["score"], 0.5)

    def test_peer_log_recent_uses_last_cycle_not_log_tail(self) -> None:
        signals = improve.ImproveSignals(
            live={},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={
                "last_cycle": {
                    "ts": __import__("time").time() - 30,
                    "verify_ok": True,
                    "noop": False,
                }
            },
        )
        ctx = asi_rubric._probe_ctx(signals)
        score, evidence = asi_rubric._p1_peer_log_recent(ctx)
        self.assertEqual(score, 1.0)
        self.assertIn("last_cycle", evidence)

    def test_compute_asi_progress_delegates(self) -> None:
        signals = improve.ImproveSignals(
            live={},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
        )
        asi = improve.compute_asi_progress(signals)
        self.assertTrue(asi.phases)
        self.assertIn("phase", asi.label.lower() + (asi.next_plan or "").lower())
        self.assertEqual(asi.pct, max(0, min(100, int(round(asi.raw * 100)))))

    def test_horizon_includes_phases(self) -> None:
        signals = improve.ImproveSignals(
            live={"tests": "ok"},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
            opportunities=[],
        )
        text = improve.build_horizon_markdown(signals, cycle=1)
        self.assertIn("Phased rubric", text)
        self.assertIn("Phase 1", text)
        payload = improve.horizon_payload(signals, cycle=1)
        self.assertIn("phases", payload["asi"])
        self.assertIn("current_phase_id", payload["asi"])

    def test_format_phase_advance_plan_mentions_met_and_next(self) -> None:
        text = asi_rubric.format_phase_advance_plan(
            "grounded_loop", "verify_memory"
        )
        self.assertIn("MET", text)
        self.assertIn("Verify", text)
        self.assertIn("work kit", text.lower())
        self.assertIn("automation_improve", text)

    def test_work_kit_plan_forbids_self_improve(self) -> None:
        plan = asi_rubric.work_kit_plan_for_phase("parallel_orchestration")
        lowered = plan.lower()
        self.assertIn("do not edit automation_improve", lowered)
        self.assertTrue("worktree" in lowered or "peer" in lowered)

    def test_peer_probe_ignores_sibling_project_label(self) -> None:
        """Phase 1 must not credit ram-peer-loop when Automation peer is down."""
        signals = improve.ImproveSignals(
            live={},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
        )
        ctx = asi_rubric._probe_ctx(signals)
        self.assertNotIn("com.togi.ram-peer-loop", ctx["peer_labels"])
        project_label = str(ctx["peer_labels"][0] or "")
        self.assertTrue(project_label)
        # Hub may be automation-* or worktree namespace (peer-1 / peer-N).
        self.assertTrue(
            "automation" in project_label.lower() or "peer" in project_label.lower(),
            project_label,
        )

        def fake_running(label: str) -> bool:
            return label == "com.togi.ram-peer-loop"

        with mock.patch.object(asi_rubric, "_launchctl_running", side_effect=fake_running):
            score, evidence = asi_rubric._p1_peer_daemon(ctx)
        self.assertEqual(score, 0.0)
        self.assertIn("not running", evidence)


    def test_launchctl_running_falls_back_to_systemd(self) -> None:
        asi_rubric.clear_daemon_probe_cache()
        with mock.patch.object(asi_rubric, "_IS_DARWIN", True), mock.patch.object(
            asi_rubric.subprocess, "run", side_effect=FileNotFoundError("launchctl")
        ):
            with mock.patch.object(asi_rubric, "_systemd_user_active", return_value=True) as sysd:
                self.assertTrue(asi_rubric._launchctl_running("com.togi.automation-hub-peer-loop"))
                sysd.assert_called_with("peer-loop.service")
        asi_rubric.clear_daemon_probe_cache()

    def test_daemon_probe_ttl_hit_skips_systemd(self) -> None:
        """Needle ASI_DAEMON_PROBE_TTL_2026_09_05 — HIT must not re-shell."""
        asi_rubric.clear_daemon_probe_cache()
        label = "com.togi.automation-hub-peer-loop"
        calls = {"n": 0}

        def fake_systemd(unit: str) -> bool:
            calls["n"] += 1
            return True

        with mock.patch.object(asi_rubric, "_IS_DARWIN", False), mock.patch.object(
            asi_rubric, "_systemd_user_active", side_effect=fake_systemd
        ):
            self.assertTrue(asi_rubric._launchctl_running(label, now=100.0))
            self.assertEqual(calls["n"], 1)
            self.assertTrue(asi_rubric._launchctl_running(label, now=110.0))
            self.assertEqual(calls["n"], 1)  # TTL HIT
            past = 100.0 + asi_rubric.daemon_probe_effective_ttl_sec() + 1.0
            self.assertTrue(asi_rubric._launchctl_running(label, now=past))
            self.assertEqual(calls["n"], 2)  # past effective TTL
        asi_rubric.clear_daemon_probe_cache()

    def test_daemon_probe_ttl_wake_floor_hits_at_wake_boundary(self) -> None:
        """ASI_DAEMON_PROBE_TTL_WAKE_FLOOR — wake==bare TTL must still HIT."""
        src = (SCRIPTS / "asi_rubric.py").read_text(encoding="utf-8")
        self.assertIn("ASI_DAEMON_PROBE_TTL_WAKE_FLOOR_2026_09_08", src)
        self.assertIn("daemon_probe_effective_ttl_sec", src)
        asi_rubric.clear_daemon_probe_cache()
        label = "com.togi.automation-hub-peer-loop"
        calls = {"n": 0}

        def fake_systemd(unit: str) -> bool:
            calls["n"] += 1
            return True

        with mock.patch.object(asi_rubric, "_IS_DARWIN", False), mock.patch.object(
            asi_rubric, "_systemd_user_active", side_effect=fake_systemd
        ), mock.patch.object(
            asi_rubric, "daemon_probe_effective_ttl_sec", return_value=35.0
        ):
            self.assertTrue(asi_rubric._launchctl_running(label, now=100.0))
            self.assertEqual(calls["n"], 1)
            # Age just past bare 30s — floor must HIT.
            self.assertTrue(asi_rubric._launchctl_running(label, now=130.5))
            self.assertEqual(calls["n"], 1)
            self.assertTrue(asi_rubric._launchctl_running(label, now=136.0))
            self.assertEqual(calls["n"], 2)
        asi_rubric.clear_daemon_probe_cache()

    def test_daemon_probe_clear_forces_remiss(self) -> None:
        asi_rubric.clear_daemon_probe_cache()
        label = "com.togi.automation-hub-improve-loop"
        with mock.patch.object(asi_rubric, "_IS_DARWIN", False), mock.patch.object(
            asi_rubric, "_systemd_user_active", return_value=True
        ) as sd:
            self.assertTrue(asi_rubric._launchctl_running(label, now=1.0))
            asi_rubric.clear_daemon_probe_cache()
            self.assertTrue(asi_rubric._launchctl_running(label, now=2.0))
            self.assertEqual(sd.call_count, 2)
        asi_rubric.clear_daemon_probe_cache()

    def test_systemd_user_active_shares_heal_batch(self) -> None:
        """ASI_SHARE_SYSTEMD_IS_ACTIVE_BATCH — prefer heal batch; 0 local is-active."""
        self.assertIn(
            "ASI_SHARE_SYSTEMD_IS_ACTIVE_BATCH_2026_09_08",
            (SCRIPTS / "asi_rubric.py").read_text(encoding="utf-8"),
        )
        if asi_rubric._IS_DARWIN:
            self.skipTest("Linux/DGX batch share")
        import peer_self_heal as heal

        asi_rubric.clear_daemon_probe_cache()
        heal.clear_systemd_active_cache()
        heal._probe_cache.clear()
        units = list(heal._SYSTEMD_ACTIVE_BATCH_UNITS)
        sample = "\n".join(["active"] * len(units)) + "\n"
        calls: list[list[str]] = []
        real_run = heal.subprocess.run

        def fake_run(cmd, *args, **kwargs):
            if (
                isinstance(cmd, (list, tuple))
                and len(cmd) >= 3
                and cmd[0] == "systemctl"
                and "is-active" in cmd
            ):
                calls.append(list(cmd))
                return mock.Mock(returncode=0, stdout=sample, stderr="")
            return real_run(cmd, *args, **kwargs)

        with mock.patch.object(heal.subprocess, "run", side_effect=fake_run):
            with mock.patch.object(asi_rubric.subprocess, "run", side_effect=fake_run):
                self.assertTrue(asi_rubric._systemd_user_active("peer-loop.service"))
                self.assertTrue(asi_rubric._systemd_user_active("improve-loop.service"))
                # Label TTL path also reuses heal (clear ASI label cache).
                asi_rubric.clear_daemon_probe_cache()
                self.assertTrue(
                    asi_rubric._launchctl_running("com.togi.automation-hub-peer-loop")
                )
                self.assertTrue(
                    asi_rubric._launchctl_running("com.togi.automation-hub-improve-loop")
                )
        self.assertEqual(len(calls), 1, "peer+improve must share one batch is-active")
        self.assertEqual(calls[0][3:], units)
        asi_rubric.clear_daemon_probe_cache()
        heal.clear_systemd_active_cache()


class TestEnqueuePhasePlan(unittest.TestCase):
    def _signals(self) -> improve.ImproveSignals:
        return improve.ImproveSignals(
            live={},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
        )

    def test_active_phase_enqueues_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            work = tmp_path / "WORK_QUEUE.md"
            ctx = tmp_path / "self_improve_context.md"
            work.write_text("# Q\n\n## Active\n\n")
            ctx.write_text("# C\n\n## Remaining work\n\n")
            logs: list[str] = []
            with mock.patch.object(
                improve, "_queue_paths_for_enqueue", return_value=(ctx, work)
            ):
                with mock.patch.object(
                    improve,
                    "compute_asi_progress",
                    return_value=improve.AsiProgress(
                        pct=10,
                        label="active phase",
                        scale=100,
                        raw=0.1,
                        dimensions=[],
                        phases=[],
                        current_phase_id="grounded_loop",
                        next_plan="Stabilize peer daemons",
                    ),
                ):
                    out = improve.enqueue_phase_plan(
                        self._signals(), log_fn=logs.append, previous_phase_id=None
                    )
            self.assertIsNotNone(out)
            self.assertIn("Harden active capability", out or "")
            self.assertIn("factory:grounded_loop", out or "")
            body = work.read_text()
            self.assertIn("grounded_loop", body)
            self.assertIn("Stabilize peer daemons", body)

    def test_phase_advance_enqueues_complete_to_plan_next(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            work = tmp_path / "WORK_QUEUE.md"
            ctx = tmp_path / "self_improve_context.md"
            work.write_text("# Q\n\n## Active\n\n")
            ctx.write_text("# C\n\n## Remaining work\n\n")
            logs: list[str] = []
            with mock.patch.object(
                improve, "_queue_paths_for_enqueue", return_value=(ctx, work)
            ):
                with mock.patch.object(
                    improve,
                    "compute_asi_progress",
                    return_value=improve.AsiProgress(
                        pct=30,
                        label="advanced",
                        scale=100,
                        raw=0.3,
                        dimensions=[],
                        phases=[],
                        current_phase_id="verify_memory",
                        next_plan="Fix verify",
                    ),
                ):
                    out = improve.enqueue_phase_plan(
                        self._signals(),
                        log_fn=logs.append,
                        previous_phase_id="grounded_loop",
                    )
            self.assertIsNotNone(out)
            self.assertIn("complete → next", out or "")
            self.assertIn("factory:verify_memory", out or "")
            body = work.read_text()
            self.assertIn("MET", body)
            self.assertIn("verify_memory", body)
            with mock.patch.object(
                improve, "_queue_paths_for_enqueue", return_value=(ctx, work)
            ):
                with mock.patch.object(
                    improve,
                    "compute_asi_progress",
                    return_value=improve.AsiProgress(
                        pct=30,
                        label="advanced",
                        scale=100,
                        raw=0.3,
                        dimensions=[],
                        phases=[],
                        current_phase_id="verify_memory",
                        next_plan="Fix verify",
                    ),
                ):
                    again = improve.enqueue_phase_plan(
                        self._signals(),
                        log_fn=logs.append,
                        previous_phase_id="grounded_loop",
                    )
            self.assertIsNone(again)

    def test_load_previous_asi_phase_id_from_horizon_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "improve-horizon.json"
            path.write_text(
                json.dumps({"asi": {"current_phase_id": "verify_memory"}}) + "\n"
            )
            with mock.patch.object(improve, "HORIZON_JSON_PATH", path):
                self.assertEqual(
                    improve._load_previous_asi_phase_id(), "verify_memory"
                )


class TestLogTailSeek(unittest.TestCase):
    """LOG_TAIL_SEEK_2026_09_05 — seek last N bytes; do not full-read huge logs."""

    def test_read_log_tail_seeks_not_full_decode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.log"
            # ~2MB prefix + distinctive tail (mirrors multi-MB improve-loop.log).
            path.write_bytes(b"X" * (2 * 1024 * 1024) + b"wake peer\nhand_out:1\n")
            with mock.patch.object(Path, "read_text", autospec=True) as rt:
                tail = asi_rubric._read_log_tail(path, tail_bytes=64)
                rt.assert_not_called()
            self.assertIn("wake peer", tail)
            self.assertIn("hand_out:1", tail)
            self.assertLessEqual(len(tail.encode("utf-8")), 64)

    def test_log_has_recent_any_matches_tail_needle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "improve-loop.log"
            path.write_bytes(b"noise\n" * 5000 + b"drive work kit ok\n")
            asi_rubric.clear_log_has_recent_any_cache()
            ok, ev = asi_rubric._log_has_recent_any(
                path,
                ("wake peer", "hand_out:", "drive work kit"),
                max_age_sec=3600.0,
                tail_bytes=256,
            )
            self.assertTrue(ok)
            self.assertIn("drive work kit", ev)

    def test_log_has_recent_any_mtime_memo_skips_reread(self) -> None:
        """LOG_HAS_RECENT_ANY_MTIME_MEMO — remiss skips tail seek when mtime stable."""
        self.assertIn(
            "LOG_HAS_RECENT_ANY_MTIME_MEMO_2026_09_08",
            (SCRIPTS / "asi_rubric.py").read_text(encoding="utf-8"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "improve-loop.log"
            path.write_bytes(b"noise\n" * 2000 + b"wake peer\n")
            asi_rubric.clear_log_has_recent_any_cache()
            needles = ("wake peer", "hand_out:", "drive work kit")
            calls = {"n": 0}
            real_tail = asi_rubric._read_log_tail

            def counting_tail(p, tail_bytes=32000):
                calls["n"] += 1
                return real_tail(p, tail_bytes)

            with mock.patch.object(asi_rubric, "_read_log_tail", side_effect=counting_tail):
                a_ok, a_ev = asi_rubric._log_has_recent_any(
                    path, needles, max_age_sec=3600.0, tail_bytes=128
                )
                b_ok, b_ev = asi_rubric._log_has_recent_any(
                    path, needles, max_age_sec=3600.0, tail_bytes=128
                )
                self.assertTrue(a_ok and b_ok)
                self.assertEqual(calls["n"], 1, "mtime HIT must skip second tail read")
                self.assertIn("wake peer", a_ev)
                self.assertIn("wake peer", b_ev)
                asi_rubric.clear_log_has_recent_any_cache()
                asi_rubric._log_has_recent_any(
                    path, needles, max_age_sec=3600.0, tail_bytes=128
                )
                self.assertEqual(calls["n"], 2)
        asi_rubric.clear_log_has_recent_any_cache()

    def test_label_to_systemd_maps_oversight_loop(self) -> None:
        """OVERSEER_ASI_OVERSIGHT_SYSTEMD_MAP — oversight must map (factory 99% pin)."""
        self.assertEqual(
            asi_rubric._label_to_systemd_unit("com.togi.automation-hub-oversight-loop"),
            "oversight-loop.service",
        )
        self.assertEqual(
            asi_rubric._label_to_systemd_unit("com.togi.automation-oversight-loop"),
            "oversight-loop.service",
        )
        self.assertEqual(
            asi_rubric._label_to_systemd_unit("com.togi.automation-hub-peer-loop"),
            "peer-loop.service",
        )
        self.assertIn(
            "OVERSEER_ASI_OVERSIGHT_SYSTEMD_MAP_2026_09_08",
            (SCRIPTS / "asi_rubric.py").read_text(encoding="utf-8"),
        )
        asi_rubric.clear_daemon_probe_cache()
        with mock.patch.object(asi_rubric, "_systemd_user_active", return_value=True) as act:
            with mock.patch.object(asi_rubric, "_IS_DARWIN", False):
                self.assertTrue(
                    asi_rubric._launchctl_running("com.togi.automation-hub-oversight-loop")
                )
            act.assert_called_with("oversight-loop.service")
        asi_rubric.clear_daemon_probe_cache()

    def test_probe_ctx_no_import_automation_improve(self) -> None:
        """ASI_PROBE_CTX_NO_IMPROVE_IMPORT — label+SCRIPTS without cold import."""
        self.assertIn(
            "ASI_PROBE_CTX_NO_IMPROVE_IMPORT_2026_09_08",
            (SCRIPTS / "asi_rubric.py").read_text(encoding="utf-8"),
        )
        for k in list(sys.modules):
            if k == "automation_improve" or k.startswith("automation_improve."):
                del sys.modules[k]
        signals = mock.Mock(loop_state={}, live={})
        ctx = asi_rubric._probe_ctx(signals)
        self.assertNotIn(
            "automation_improve",
            sys.modules,
            "_probe_ctx must not cold-import automation_improve",
        )
        import automation_improve as improve

        self.assertEqual(ctx["improve_label"], improve.IMPROVE_LABEL)
        self.assertEqual(ctx["worktree_path"], asi_rubric.SCRIPTS / "peer_worktree.py")


if __name__ == "__main__":
    unittest.main()
