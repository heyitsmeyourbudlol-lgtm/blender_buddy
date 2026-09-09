"""Tests for verify classification + retry-once self-heal gate."""

from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_peer_tasks as rpt  # noqa: E402


class ClassifyVerifyFailureTests(unittest.TestCase):
    def test_timeout(self) -> None:
        self.assertEqual(rpt.classify_verify_failure("anything", timed_out=True), "timeout")

    def test_self_check(self) -> None:
        self.assertEqual(
            rpt.classify_verify_failure("python3 scripts/peer_orchestrate.py --self-check"),
            "self-check",
        )

    def test_tests_unittest(self) -> None:
        self.assertEqual(
            rpt.classify_verify_failure("python3 -m unittest discover -s tests -q"),
            "tests",
        )

    def test_tests_pytest(self) -> None:
        self.assertEqual(rpt.classify_verify_failure("pytest -q"), "tests")

    def test_other(self) -> None:
        self.assertEqual(rpt.classify_verify_failure("python3 scripts/lint_all.py"), "other")


class RunVerifyGateTests(unittest.TestCase):
    def test_ok_no_retry(self) -> None:
        logs: list[str] = []
        with unittest.mock.patch.object(rpt, "run_verify_commands", return_value=(0, None)) as mock_run:
            failures, kind, retries = rpt.run_verify_gate(log_fn=logs.append)
        self.assertEqual((failures, kind, retries), (0, None, 0))
        mock_run.assert_called_once()
        self.assertFalse(any("retry once" in m for m in logs))

    def test_retry_once_then_ok(self) -> None:
        logs: list[str] = []
        with unittest.mock.patch.object(
            rpt,
            "run_verify_commands",
            side_effect=[(1, "tests"), (0, None)],
        ) as mock_run:
            failures, kind, retries = rpt.run_verify_gate(log_fn=logs.append)
        self.assertEqual((failures, kind, retries), (0, None, 1))
        self.assertEqual(mock_run.call_count, 2)
        self.assertTrue(any("retry once" in m for m in logs))

    def test_retry_once_still_fail(self) -> None:
        logs: list[str] = []
        with unittest.mock.patch.object(
            rpt,
            "run_verify_commands",
            side_effect=[(2, "self-check"), (1, "self-check")],
        ) as mock_run:
            failures, kind, retries = rpt.run_verify_gate(log_fn=logs.append)
        self.assertEqual((failures, kind, retries), (1, "self-check", 1))
        self.assertEqual(mock_run.call_count, 2)

    def test_retry_disabled(self) -> None:
        with unittest.mock.patch.object(
            rpt, "run_verify_commands", return_value=(1, "other")
        ) as mock_run:
            failures, kind, retries = rpt.run_verify_gate(log_fn=lambda _m: None, retry_once=False)
        self.assertEqual((failures, kind, retries), (1, "other", 0))
        mock_run.assert_called_once()


class RunVerifyCommandsClassifyTests(unittest.TestCase):
    def _quiet_ready(self) -> tuple:
        return (
            unittest.mock.patch.object(rpt, "_prepare_verify_lane"),
            unittest.mock.patch.object(rpt, "_wait_verify_quiet", return_value=True),
        )

    def test_timeout_classifies(self) -> None:
        prep, quiet = self._quiet_ready()
        with unittest.mock.patch.object(rpt, "load_verify_commands", return_value=["slow cmd"]):
            with unittest.mock.patch.object(
                rpt, "_run_cmd_group", side_effect=rpt.subprocess.TimeoutExpired(cmd="slow", timeout=1)
            ), unittest.mock.patch.object(rpt, "_try_acquire_verify_lock", return_value=True), unittest.mock.patch.object(
                rpt, "_release_verify_lock"
            ), unittest.mock.patch.object(
                rpt, "_adapt_audit_blocks_verify", return_value=(False, None)
            ), prep, quiet:
                failures, kind = rpt.run_verify_commands(log_fn=lambda _m: None)
        self.assertEqual(failures, 1)
        self.assertEqual(kind, "timeout")

    def test_nonzero_classifies_self_check(self) -> None:
        proc = unittest.mock.Mock(returncode=1, stderr="boom", stdout="")
        cmd = "python3 scripts/peer_orchestrate.py --self-check"
        prep, quiet = self._quiet_ready()
        with unittest.mock.patch.object(rpt, "load_verify_commands", return_value=[cmd]):
            with unittest.mock.patch.object(rpt, "_run_cmd_group", return_value=proc), unittest.mock.patch.object(
                rpt, "_try_acquire_verify_lock", return_value=True
            ), unittest.mock.patch.object(rpt, "_release_verify_lock"), prep, quiet, unittest.mock.patch(
                "dgx_ram_budget.self_check_worker_count", return_value=0
            ), unittest.mock.patch.object(
                rpt, "_adapt_audit_blocks_verify", return_value=(False, None)
            ):
                failures, kind = rpt.run_verify_commands(log_fn=lambda _m: None)
        self.assertEqual(failures, 1)
        self.assertEqual(kind, "self-check")

    def test_skips_when_lock_held(self) -> None:
        logs: list[str] = []
        prep, quiet = self._quiet_ready()
        with unittest.mock.patch.object(rpt, "_try_acquire_verify_lock", return_value=False), prep, quiet:
            failures, kind = rpt.run_verify_commands(log_fn=logs.append)
        self.assertEqual((failures, kind), (-1, "deferred"))
        self.assertTrue(any("already running" in m for m in logs))

    def test_quiet_defer_skips_lock(self) -> None:
        """Swarm quiet-wait must not acquire the single-flight lock."""
        logs: list[str] = []
        acquire = unittest.mock.Mock(return_value=True)
        with unittest.mock.patch.object(rpt, "_prepare_verify_lane"), unittest.mock.patch.object(
            rpt, "_wait_verify_quiet", return_value=False
        ), unittest.mock.patch.object(rpt, "_try_acquire_verify_lock", acquire):
            failures, kind = rpt.run_verify_commands(log_fn=logs.append)
        self.assertEqual((failures, kind), (-1, "deferred"))
        acquire.assert_not_called()

    def test_filters_recursive_adapt_audit(self) -> None:
        self.assertTrue(rpt._is_recursive_adapt_command("python3 scripts/automation_adapt.py --audit"))
        self.assertFalse(rpt._is_recursive_adapt_command("python3 -m unittest discover -s tests -q"))


class AdaptAuditGateTests(unittest.TestCase):
    def test_blocks_stale_fingerprint(self) -> None:
        logs: list[str] = []
        finding = unittest.mock.Mock(level="warn", category="adapt_state", message="git fingerprint stale — re-run adapt --heal")
        report = unittest.mock.Mock(findings=[finding])
        with unittest.mock.patch("automation_adapt.run_audit", return_value=report):
            blocked, kind = rpt._adapt_audit_blocks_verify(log_fn=logs.append)
        self.assertTrue(blocked)
        self.assertEqual(kind, rpt.ADAPT_STALE_FAILURE)
        self.assertTrue(any("ADAPT_STALE" in m for m in logs))

    def test_blocks_null_fingerprint_warn_from_quick_audit(self) -> None:
        logs: list[str] = []
        finding = unittest.mock.Mock(
            level="warn",
            category="adapt_state",
            message="git fingerprint stale — re-run adapt --heal",
        )
        report = unittest.mock.Mock(findings=[finding])
        with unittest.mock.patch("automation_adapt.run_audit", return_value=report):
            blocked, kind = rpt._adapt_audit_blocks_verify(log_fn=logs.append)
        self.assertTrue(blocked)
        self.assertEqual(kind, rpt.ADAPT_STALE_FAILURE)

    def test_passes_clean_audit(self) -> None:
        finding = unittest.mock.Mock(level="pass", category="adapt_state", message="adapt-state consistent")
        report = unittest.mock.Mock(findings=[finding])
        with unittest.mock.patch("automation_adapt.run_audit", return_value=report):
            blocked, kind = rpt._adapt_audit_blocks_verify(log_fn=lambda _m: None)
        self.assertFalse(blocked)
        self.assertIsNone(kind)

    def test_does_not_block_on_queue_error(self) -> None:
        finding = unittest.mock.Mock(level="error", category="queue", message="WORK_QUEUE drift")
        report = unittest.mock.Mock(findings=[finding])
        with unittest.mock.patch("automation_adapt.run_audit", return_value=report):
            blocked, kind = rpt._adapt_audit_blocks_verify(log_fn=lambda _m: None)
        self.assertFalse(blocked)
        self.assertIsNone(kind)

    def test_blocks_on_adapt_state_error(self) -> None:
        finding = unittest.mock.Mock(level="error", category="adapt_state", message="adapt state inconsistent")
        report = unittest.mock.Mock(findings=[finding])
        with unittest.mock.patch("automation_adapt.run_audit", return_value=report):
            blocked, kind = rpt._adapt_audit_blocks_verify(log_fn=lambda _m: None)
        self.assertTrue(blocked)
        self.assertEqual(kind, rpt.ADAPT_STALE_FAILURE)


    def test_verify_commands_calls_audit_gate(self) -> None:
        with unittest.mock.patch.object(rpt, "_try_acquire_verify_lock", return_value=True), unittest.mock.patch.object(
            rpt, "_release_verify_lock"
        ), unittest.mock.patch.object(rpt, "_prepare_verify_lane"), unittest.mock.patch.object(
            rpt, "_wait_verify_quiet", return_value=True
        ), unittest.mock.patch.object(
            rpt, "_adapt_audit_blocks_verify", return_value=(True, rpt.ADAPT_STALE_FAILURE)
        ) as mock_audit, unittest.mock.patch.object(rpt, "load_verify_commands", return_value=["cmd"]), unittest.mock.patch(
            "automation_adapt.sync_git_fingerprint", return_value=True
        ):
            failures, kind = rpt.run_verify_commands(log_fn=lambda _m: None)
        self.assertEqual((failures, kind), (1, rpt.ADAPT_STALE_FAILURE))
        mock_audit.assert_called_once()


class RunLocalCycleDeferredTests(unittest.TestCase):
    def test_deferred_is_not_gate_failure(self) -> None:
        """heal-all verify-gate must not [FAIL] when swarm defers verify."""
        plan = unittest.mock.Mock(stop=False, stop_reason=None, tasks=["t1"])
        live = unittest.mock.Mock(git_clean=False, tests_ok=True)
        with unittest.mock.patch.object(rpt.po, "build_plan", return_value=plan), unittest.mock.patch.object(
            rpt.auto, "measure_live_state", return_value=live
        ), unittest.mock.patch.object(
            rpt, "run_verify_commands", return_value=(-1, "deferred")
        ), unittest.mock.patch.object(rpt.auto, "success_metrics_ok", return_value=True):
            logs: list[str] = []
            rc, ready = rpt.run_local_cycle(quick=True, log_fn=logs.append)
        self.assertEqual((rc, ready), (0, False))
        self.assertTrue(any("deferred" in m for m in logs))
        self.assertFalse(any("failure(s)" in m for m in logs))


    def test_idle_stop_never_ready_without_verify(self) -> None:
        """plan.stop + green metrics must not auto_commit via ready=True."""
        plan = unittest.mock.Mock(stop=True, stop_reason="queue empty", tasks=[])
        live = unittest.mock.Mock(git_clean=True, tests_ok=True)
        with unittest.mock.patch.object(rpt.po, "build_plan", return_value=plan), unittest.mock.patch.object(
            rpt.auto, "measure_live_state", return_value=live
        ), unittest.mock.patch.object(
            rpt, "run_verify_commands", side_effect=AssertionError("verify must not run on idle")
        ), unittest.mock.patch.object(rpt.auto, "success_metrics_ok", return_value=True):
            logs: list[str] = []
            rc, ready = rpt.run_local_cycle(quick=True, log_fn=logs.append)
        self.assertEqual((rc, ready), (0, False))
        self.assertTrue(any("idle" in m for m in logs))


class AfterVerifyOkGateTests(unittest.TestCase):
    def test_transcript_turn_skips_after_verify_ok(self) -> None:
        import peer_loop
        import peer_transcript as pt

        meta = unittest.mock.Mock()
        state: dict = {"x": 1}
        after_calls: list[str] = []
        live = unittest.mock.Mock(git_clean=True, tests_ok=True)
        with unittest.mock.patch.object(pt, "output_generated", return_value=True), unittest.mock.patch.object(
            pt, "build_next_input", return_value="prompt"
        ), unittest.mock.patch.object(
            peer_loop, "dispatch_prompt_text", return_value=(0, False)
        ), unittest.mock.patch.object(pt, "mark_processed", side_effect=lambda _m, s: s), unittest.mock.patch.object(
            peer_loop.auto, "measure_live_state", return_value=live
        ), unittest.mock.patch.object(
            peer_loop,
            "_after_verify_ok",
            side_effect=lambda **kw: after_calls.append(kw.get("note", "")),
        ):
            out, auth = peer_loop._maybe_dispatch_on_turn(
                quick=True,
                mode="clipboard",
                clipboard_only=True,
                press_enter=False,
                log_fn=lambda _m: None,
                state=state,
                paid_api=False,
                use_agent=True,
                meta=meta,
                path=None,
                live=live,
                watcher=None,
                fallback_poll_sec=0.1,
                done_timeout_sec=1.0,
            )
        self.assertIs(out, state)
        self.assertFalse(auth)
        self.assertEqual(after_calls, [])

    def test_deferred_verify_stamps_verify_ok_false(self) -> None:
        import peer_loop
        import peer_transcript as pt
        import run_peer_tasks as rpt_mod

        state: dict = {"last_cycle": {"verify_ok": True, "noop": False}}
        recorded: list[dict] = []

        def _rec(st, **kw):
            recorded.append(kw)
            st["last_cycle"] = {
                "verify_ok": kw.get("verify_ok"),
                "note": kw.get("note"),
                "noop": False,
            }

        live = unittest.mock.Mock(git_clean=True, tests_ok=True)
        with unittest.mock.patch.object(peer_loop.auto, "has_loop_work", return_value=True), unittest.mock.patch.object(
            peer_loop, "_mechanical_pre_dispatch", return_value=True
        ), unittest.mock.patch.object(pt, "current_queue_fingerprint", return_value=("fp", [])), unittest.mock.patch.object(
            peer_loop, "_noop_remaining_or_clear", return_value=0.0
        ), unittest.mock.patch.object(
            peer_loop, "_resolve_coding_cwd", return_value=("/tmp", False)
        ), unittest.mock.patch.object(
            peer_loop.peer_worktree, "continue_on_dirty_enabled", return_value=True
        ), unittest.mock.patch.object(
            peer_loop, "_dispatch_agent_cycle", return_value=(0, False)
        ), unittest.mock.patch.object(
            peer_loop.auto, "measure_live_state", return_value=live
        ), unittest.mock.patch.object(
            peer_loop, "wait_for_git_clean", return_value=unittest.mock.Mock(git_clean=True)
        ), unittest.mock.patch.object(
            rpt_mod, "run_verify_gate", return_value=(-1, "deferred", 0)
        ), unittest.mock.patch.object(pt, "record_cycle_outcome", side_effect=_rec), unittest.mock.patch.object(
            pt, "save_state"
        ):
            auth = peer_loop._run_terminal_cycle(
                quick=True,
                log_fn=lambda _m: None,
                state=state,
                fallback_poll_sec=0.1,
                done_timeout_sec=1.0,
                paid_api=False,
                watcher=None,
                live=live,
            )
        self.assertFalse(auth)
        self.assertTrue(recorded)
        self.assertFalse(recorded[0].get("verify_ok"))
        self.assertEqual(state["last_cycle"].get("failure_type"), "deferred")


class QuietLimitsTests(unittest.TestCase):
    def test_agent_cap_from_verify_quiet_max_agents(self) -> None:
        with unittest.mock.patch.dict(
            rpt.auto.CFG,
            {"verify_quiet_max_agents": 2, "max_parallel_agent_procs": 8, "verify_quiet_max_unittest": 1},
            clear=False,
        ):
            agent_cap, max_tests = rpt._verify_quiet_limits()
        self.assertEqual(agent_cap, 2)
        self.assertEqual(max_tests, 1)
        self.assertNotEqual(agent_cap, 8)

    def test_agent_cap_clamped_to_0_2(self) -> None:
        with unittest.mock.patch.dict(
            rpt.auto.CFG,
            {"verify_quiet_max_agents": 99, "max_parallel_agent_procs": 8},
            clear=False,
        ):
            agent_cap, _ = rpt._verify_quiet_limits()
        self.assertEqual(agent_cap, 2)

    def test_agent_cap_allows_zero(self) -> None:
        with unittest.mock.patch.dict(
            rpt.auto.CFG,
            {"verify_quiet_max_agents": 0, "max_parallel_agent_procs": 8},
            clear=False,
        ):
            agent_cap, _ = rpt._verify_quiet_limits()
        self.assertEqual(agent_cap, 0)

    def test_free_desktop_saturate_ignores_agent_swarm(self) -> None:
        """trim_agents_over_cap=false must not forever-defer on agents>2 (T10-04)."""
        logs: list[str] = []
        with unittest.mock.patch.dict(
            rpt.auto.CFG,
            {
                "trim_agents_over_cap": False,
                "verify_quiet_timeout_sec": 5,
                "verify_quiet_max_agents": 2,
                "verify_quiet_max_unittest": 2,
                "verify_quiet_max_self_check": 2,
            },
            clear=False,
        ), unittest.mock.patch(
            "peer_parallel_dispatch.find_agent_procs", return_value=[1, 2, 3, 4, 5, 6, 7]
        ), unittest.mock.patch(
            "dgx_ram_budget.unittest_worker_count", return_value=0
        ), unittest.mock.patch(
            "dgx_ram_budget.self_check_worker_count", return_value=0
        ), unittest.mock.patch(
            "dgx_ram_budget.trim_unittest_storm", return_value=0
        ), unittest.mock.patch(
            "dgx_ram_budget.trim_self_check_storm", return_value=0
        ):
            ok = rpt._wait_verify_quiet(log_fn=logs.append, timeout_sec=5.0)
        self.assertTrue(ok)
        self.assertTrue(any("free-desktop saturate" in m for m in logs))



class IdleReadyFalseTests(unittest.TestCase):
    def test_idle_never_ready_without_verify(self) -> None:
        plan = unittest.mock.Mock(stop=True, stop_reason="empty queue", tasks=[])
        live = unittest.mock.Mock(git_clean=True, tests_ok=True)
        with unittest.mock.patch.object(rpt.po, "build_plan", return_value=plan), unittest.mock.patch.object(
            rpt.auto, "measure_live_state", return_value=live
        ), unittest.mock.patch.object(
            rpt.auto, "success_metrics_ok", return_value=True
        ), unittest.mock.patch.object(rpt, "run_verify_commands") as ver:
            rc, ready = rpt.run_local_cycle(quick=True, log_fn=lambda _m: None)
        self.assertEqual((rc, ready), (0, False))
        ver.assert_not_called()


class QuietWaitRetrimTests(unittest.TestCase):
    def test_retrim_during_wait(self) -> None:
        logs: list[str] = []
        counts = {"n": 0}

        def _count() -> int:
            counts["n"] += 1
            return 5 if counts["n"] < 2 else 0

        with unittest.mock.patch.dict(
            rpt.auto.CFG,
            {"verify_quiet_timeout_sec": 20, "verify_trim_unittest_cap": 0, "verify_quiet_max_unittest": 0},
            clear=False,
        ), unittest.mock.patch(
            "peer_parallel_dispatch.find_agent_procs", return_value=[]
        ), unittest.mock.patch(
            "dgx_ram_budget.unittest_worker_count", side_effect=_count
        ), unittest.mock.patch(
            "dgx_ram_budget.self_check_worker_count", return_value=0
        ), unittest.mock.patch(
            "dgx_ram_budget.trim_unittest_storm", return_value=3
        ) as trim, unittest.mock.patch(
            "dgx_ram_budget.trim_self_check_storm", return_value=0
        ), unittest.mock.patch.object(rpt.time, "sleep"):
            ok = rpt._wait_verify_quiet(log_fn=logs.append, timeout_sec=20.0)
        self.assertTrue(ok)
        self.assertGreaterEqual(trim.call_count, 1)
        self.assertTrue(any("re-trimmed" in m for m in logs))

    def test_prepare_trims_self_check(self) -> None:
        logs: list[str] = []
        with unittest.mock.patch.dict(
            rpt.auto.CFG,
            {"verify_trim_unittest_cap": 2, "dgx_self_check_cap": 2},
            clear=False,
        ), unittest.mock.patch(
            "dgx_ram_budget.trim_unittest_storm", return_value=1
        ) as ut, unittest.mock.patch(
            "dgx_ram_budget.trim_self_check_storm", return_value=4
        ) as sc:
            rpt._prepare_verify_lane(log_fn=logs.append)
        ut.assert_called_once_with(cap=2)
        sc.assert_called_once_with(cap=2)
        self.assertTrue(any("self-check" in m for m in logs))


class QuietLimitsAndNotesSyncTests(unittest.TestCase):
    def test_verify_quiet_limits_uses_quiet_max_not_dispatch_cap(self) -> None:
        with unittest.mock.patch.dict(
            rpt.auto.CFG,
            {"verify_quiet_max_agents": 2, "max_parallel_agent_procs": 48, "verify_quiet_max_unittest": 1},
            clear=False,
        ):
            agent_cap, max_tests = rpt._verify_quiet_limits()
        self.assertEqual(agent_cap, 2)
        self.assertEqual(max_tests, 1)
        with unittest.mock.patch.dict(
            rpt.auto.CFG,
            {"max_parallel_agent_procs": 48, "verify_quiet_max_agents": 0},
            clear=False,
        ):
            self.assertEqual(rpt._verify_quiet_limits()[0], 0)

    def test_run_verify_syncs_notes_only_fingerprint(self) -> None:
        logs: list[str] = []
        with unittest.mock.patch.object(rpt, "_prepare_verify_lane"), unittest.mock.patch.object(
            rpt, "_wait_verify_quiet", return_value=True
        ), unittest.mock.patch.object(
            rpt, "_try_acquire_verify_lock", return_value=True
        ), unittest.mock.patch.object(rpt, "_release_verify_lock"), unittest.mock.patch.object(
            rpt, "load_verify_commands", return_value=[]
        ), unittest.mock.patch.object(
            rpt, "_adapt_audit_blocks_verify", return_value=(False, None)
        ), unittest.mock.patch(
            "automation_adapt.sync_notes_only_fingerprint", return_value=True
        ) as sync:
            failures, kind = rpt.run_verify_commands(log_fn=logs.append)
        self.assertEqual(failures, 0)
        self.assertIsNone(kind)
        sync.assert_called_once()
        self.assertTrue(any("notes-only" in m for m in logs))


class ClearDeferredStampAfterReadyTests(unittest.TestCase):
    """OVERSEER_VERIFY_CLEAR_DEFERRED_2026_09_07 — ready clears soft deferred."""

    def test_ready_clears_deferred_last_cycle_stamp(self) -> None:
        import peer_transcript as pt

        state = {
            "last_cycle": {
                "verify_ok": False,
                "failure_type": "deferred",
                "note": "verify deferred (swarm/lock)",
                "noop": False,
                "rc": 0,
                "local_only": False,
            }
        }
        logs: list[str] = []
        with unittest.mock.patch.object(pt, "load_state", return_value=state), unittest.mock.patch.object(
            pt, "save_state"
        ) as save, unittest.mock.patch.object(
            pt, "record_cycle_outcome"
        ) as record, unittest.mock.patch.object(pt, "scrub_last_cycle_poison", side_effect=lambda s: s):
            cleared = rpt._clear_deferred_stamp_after_ready(log_fn=logs.append)
        self.assertTrue(cleared)
        lc = state.get("last_cycle") or {}
        self.assertTrue(lc.get("verify_ok"))
        self.assertNotEqual(str(lc.get("failure_type") or ""), "deferred")
        self.assertIn("cleared deferred", str(lc.get("note") or "").lower())
        # In-place clear — must not invent a local_only cycle (T10-04 meter).
        self.assertFalse(lc.get("local_only"))
        self.assertFalse(record.called)
        self.assertTrue(any("cleared deferred" in m for m in logs))
        self.assertTrue(save.called)

    def test_ready_skips_when_not_deferred(self) -> None:
        import peer_transcript as pt

        state = {"last_cycle": {"verify_ok": True, "note": "ok", "noop": False}}
        with unittest.mock.patch.object(pt, "load_state", return_value=state), unittest.mock.patch.object(
            pt, "save_state"
        ) as save:
            cleared = rpt._clear_deferred_stamp_after_ready(log_fn=lambda _m: None)
        self.assertFalse(cleared)
        self.assertFalse(save.called)

    def test_local_cycle_ready_clears_deferred(self) -> None:
        import peer_transcript as pt

        plan = unittest.mock.Mock(stop=False, tasks=[object()], stop_reason="")
        live = unittest.mock.Mock(git_clean=True, tests_ok=True)
        state = {
            "last_cycle": {
                "verify_ok": False,
                "failure_type": "deferred",
                "note": "verify deferred (swarm/lock)",
            }
        }
        logs: list[str] = []
        with unittest.mock.patch.object(rpt.po, "build_plan", return_value=plan), unittest.mock.patch.object(
            rpt.auto, "measure_live_state", return_value=live
        ), unittest.mock.patch.object(rpt, "run_verify_commands", return_value=(0, None)), unittest.mock.patch.object(
            pt, "load_state", return_value=state
        ), unittest.mock.patch.object(pt, "current_queue_fingerprint", return_value=("fp", [])), unittest.mock.patch.object(
            pt, "save_state"
        ), unittest.mock.patch.object(pt, "git_head_oneline", return_value="deadbeef"), unittest.mock.patch.object(
            pt, "scrub_last_cycle_poison", side_effect=lambda s: s
        ):
            rc, ready = rpt.run_local_cycle(quick=True, log_fn=logs.append)
        self.assertEqual(rc, 0)
        self.assertTrue(ready)
        self.assertTrue((state.get("last_cycle") or {}).get("verify_ok"))
        self.assertTrue(any("cleared deferred" in m for m in logs))


if __name__ == "__main__":
    unittest.main()
