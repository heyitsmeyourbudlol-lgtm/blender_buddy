"""Tests for automation_improve — work-kit driver (not self-improving)."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import automation_improve as improve  # noqa: E402


class ImproveRankTests(unittest.TestCase):
    def test_rank_includes_test_failure(self) -> None:
        signals = improve.ImproveSignals(
            live={"tests_ok": False, "tests": "FAIL"},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
        )
        with mock.patch.object(improve, "queue_known_keys", return_value=set()):
            opps = improve.rank_opportunities(signals)
        self.assertTrue(any("test" in o.title.lower() for o in opps))

    def test_rank_default_opportunities_when_green(self) -> None:
        signals = improve.ImproveSignals(
            live={"tests_ok": True, "git_clean": True, "tests": "ok", "git": "clean"},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
        )
        with mock.patch.object(improve, "queue_known_keys", return_value=set()), mock.patch.object(
            improve, "_script_inventory", return_value={"scripts": 4, "test_modules": 8}
        ):
            opps = improve.rank_opportunities(signals)
        self.assertGreaterEqual(len(opps), 3)
        categories = {o.category for o in opps}
        self.assertTrue(categories & {"speed", "monster", "smooth", "efficiency"})
        # No meta "Sharpen CLI" polish of improve itself
        self.assertFalse(any("sharpen cli" in o.title.lower() for o in opps))
        self.assertTrue(any(improve.is_work_kit_target(o) for o in opps))

    def test_dirty_git_is_now_factory_work(self) -> None:
        signals = improve.ImproveSignals(
            live={"tests_ok": True, "git_clean": False, "git": "dirty"},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
        )
        with mock.patch.object(improve, "queue_known_keys", return_value=set()), mock.patch.object(
            improve, "_registry_factory_gaps", return_value=[]
        ):
            opps = improve.rank_opportunities(signals)
        stab = next(o for o in opps if "Unblock dirty tree" in o.title)
        self.assertEqual(stab.priority, improve.GIT_UNBLOCK_PRIORITY)
        self.assertLessEqual(stab.priority, 20)
        self.assertFalse(improve.is_self_target(stab))
        self.assertTrue(improve.is_work_kit_target(stab))


class ImproveFilterTests(unittest.TestCase):
    def test_denylist_drops_improve_horizon_asi(self) -> None:
        bad = [
            improve.Opportunity("ease", "Rewrite automation_improve prompts", "meta", 10),
            improve.Opportunity("ease", "Horizon board cosmetics", "polish", 20),
            improve.Opportunity("asi", "[ASI 100%] True artificial superintelligence", "never", 99),
        ]
        for o in bad:
            self.assertTrue(improve.is_self_target(o), o.title)
            self.assertFalse(improve.is_work_kit_target(o), o.title)

    def test_allowlist_keeps_peer_loop_work(self) -> None:
        good = [
            improve.Opportunity(
                "smooth",
                "Harden loop gates",
                "noop backoff in peer_loop",
                20,
            ),
            improve.Opportunity(
                "efficiency",
                "[trend] Parallel agents via git worktrees",
                "peer_worktree spawn helper",
                22,
            ),
            improve.Opportunity(
                "ease",
                "Smarter peer matching",
                "Tighten peer_tasks match_rules",
                55,
            ),
        ]
        for o in good:
            self.assertTrue(improve.is_work_kit_target(o), o.title)
            self.assertFalse(improve.is_self_target(o), o.title)

    def test_denylist_drops_strategy_essays(self) -> None:
        bad = [
            improve.Opportunity("ease", "Crown-era time bomb banking", "read loop_strategy", 10),
            improve.Opportunity("ease", "Competition ladder distribution", "philosophy", 20),
        ]
        for o in bad:
            self.assertTrue(improve.is_self_target(o), o.title)

    def test_dirty_tree_unblock_is_work_kit(self) -> None:
        opp = improve.Opportunity(
            "smooth",
            "Unblock dirty tree for peer_loop dispatch",
            "peer_worktree isolate dirty tree",
            8,
        )
        self.assertTrue(improve.is_work_kit_target(opp))

    def test_maximize_parallel_task_peers_is_work_kit_target(self) -> None:
        opp = improve.Opportunity(
            "speed",
            "Maximize parallel Task peers",
            "Launch the full peer set in ONE message; utilize as many subagents as scopes allow.",
            28,
        )
        self.assertTrue(improve.is_work_kit_target(opp))
        self.assertFalse(improve.is_self_target(opp))


class ImproveEnqueueTests(unittest.TestCase):
    def test_enqueue_dedupes_and_skips_self(self) -> None:
        signals = improve.ImproveSignals(
            live={},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
            opportunities=[
                improve.Opportunity(
                    "efficiency",
                    "[trend] Parallel agents via git worktrees",
                    "Add peer_worktree helper",
                    priority=22,
                ),
                improve.Opportunity(
                    "asi",
                    "[ASI 100%] True artificial superintelligence",
                    "never",
                    priority=99,
                ),
                improve.Opportunity(
                    "smooth",
                    "Stabilize git before loop churn",
                    "dirty",
                    priority=42,
                ),
            ],
        )
        logs: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wq = root / "notes" / "WORK_QUEUE.md"
            ctx = root / "scripts" / "self_improve_context.md"
            wq.parent.mkdir(parents=True)
            ctx.parent.mkdir(parents=True)
            wq.write_text("# Q\n\n## Active items\n\n- [ ] **Existing** — keep\n\n## Done\n\n")
            ctx.write_text(
                "# C\n\n## Remaining work (priority order)\n\n- [ ] **Existing** — keep\n\n## Done\n\n"
            )
            with mock.patch.object(improve.adapt, "_queue_paths", return_value=(ctx, wq)):
                with mock.patch.object(
                    improve,
                    "queue_known_keys",
                    return_value={improve.auto._normalize_queue_key("Existing — keep")},
                ):
                    inserted = improve.enqueue_work_opportunities(
                        signals, log_fn=logs.append, cap=2
                    )
            self.assertEqual(len(inserted), 1)
            self.assertIn("Parallel agents", inserted[0])
            body = wq.read_text()
            self.assertIn("Parallel agents", body)
            self.assertNotIn("ASI 100%", body)
            self.assertNotIn("Stabilize git", body)
            signals2 = improve.ImproveSignals(
                live={},
                audit_ok=True,
                audit_warnings=[],
                audit_errors=[],
                queue_drift=[],
                loop_state={},
                opportunities=signals.opportunities,
            )
            with mock.patch.object(improve.adapt, "_queue_paths", return_value=(ctx, wq)):
                inserted2 = improve.enqueue_work_opportunities(
                    signals2, log_fn=logs.append, cap=2
                )
            self.assertEqual(inserted2, [])


class ImproveMechanicalTests(unittest.TestCase):
    def test_apply_mechanical_calls_heals(self) -> None:
        signals = improve.ImproveSignals(
            live={"git_clean": False},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=["only in notes/WORK_QUEUE.md: foo"],
            loop_state={},
        )
        logs: list[str] = []
        proc = mock.Mock()
        proc.communicate.return_value = ("ok\n", "")
        proc.returncode = 0
        with mock.patch.object(
            improve.adapt, "heal_queue_drift", return_value=(["synced"], [])
        ) as heal_q, mock.patch.object(
            improve.adapt, "should_re_adapt", return_value=False
        ), mock.patch("peer_self_heal.self_heal_enabled", return_value=False), mock.patch(
            "peer_parallel_dispatch.find_agent_procs", return_value=[]
        ), mock.patch.object(
            improve.subprocess, "Popen", return_value=proc
        ) as popen:
            actions = improve.apply_mechanical(signals, log_fn=logs.append)
        heal_q.assert_called_once()
        local_calls = [
            c for c in popen.call_args_list if "run_local_cycle" in str(c)
        ]
        self.assertEqual(len(local_calls), 1)
        self.assertTrue(local_calls[0].kwargs.get("start_new_session"))
        self.assertTrue(any("queue-drift" in a for a in actions))
        self.assertTrue(any("local-cycle: ok" in a or "local-cycle: rc=" in a for a in actions))

    def test_apply_mechanical_skips_local_cycle_when_swarm_noisy(self) -> None:
        """OVERSEER_IMPROVE_SKIP_LOCAL_CYCLE_SWARM_2026_09_04"""
        signals = improve.ImproveSignals(
            live={},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
        )
        logs: list[str] = []
        with mock.patch.object(improve.adapt, "should_re_adapt", return_value=False), mock.patch(
            "peer_self_heal.self_heal_enabled", return_value=False
        ), mock.patch(
            "run_peer_tasks._verify_quiet_limits", return_value=(2, 2)
        ), mock.patch(
            "peer_parallel_dispatch.find_agent_procs", return_value=[1, 2, 3, 4, 5]
        ), mock.patch.object(improve.subprocess, "Popen") as popen:
            actions = improve.apply_mechanical(signals, log_fn=logs.append)
        local_calls = [
            c for c in popen.call_args_list if "run_local_cycle" in str(c)
        ]
        self.assertEqual(local_calls, [])
        self.assertTrue(any("swarm agents=" in a for a in actions))
        self.assertTrue(any("swarm agents=" in m for m in logs))

    def test_apply_mechanical_skips_verify_on_cooldown(self) -> None:
        signals = improve.ImproveSignals(
            live={},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
        )
        logs: list[str] = []
        with mock.patch.object(improve.adapt, "should_re_adapt", return_value=False), mock.patch(
            "peer_self_heal.self_heal_enabled", return_value=False
        ), mock.patch.object(improve.subprocess, "Popen") as popen:
            actions = improve.apply_mechanical(signals, log_fn=logs.append, run_verify=False)
        local_calls = [
            c for c in popen.call_args_list if "run_local_cycle" in str(c)
        ]
        self.assertEqual(local_calls, [])
        self.assertTrue(any("skipped" in a for a in actions))
        self.assertTrue(any("verify cooldown" in m for m in logs))


class ImprovePromptTests(unittest.TestCase):
    def test_horizon_tiers_and_board(self) -> None:
        signals = improve.ImproveSignals(
            live={"git": "clean", "tests": "ok", "queue_source": "empty", "open_items": []},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
            trend_report={"curated_count": 2, "gap_count": 1, "partial_count": 1},
            opportunities=[
                improve.Opportunity("smooth", "Fix now", "blocker", priority=8),
                improve.Opportunity("ease", "Next week", "upgrade", priority=30),
                improve.Opportunity("efficiency", "Later", "bet", priority=50),
            ],
        )
        text = improve.build_horizon_markdown(signals, cycle=3)
        self.assertIn("NOW — unblock factory", text)
        self.assertIn("OVER THE HORIZON", text)
        self.assertIn("Fix now", text)
        self.assertIn("Later", text)
        self.assertEqual(improve._horizon_tier(8), "NOW")
        self.assertEqual(improve._horizon_tier(30), "NEXT")
        self.assertEqual(improve._horizon_tier(50), "HORIZON")
        self.assertEqual(improve._horizon_tier(99), "ASI")
        self.assertIn("OSS monster factory", text)
        self.assertIn("Investment north star", text)
        self.assertIn("Artificial Super Intelligence", text)
        self.assertIn("Phased rubric", text)
        asi = improve.compute_asi_progress(signals)
        self.assertIsInstance(asi, improve.AsiProgress)
        self.assertEqual(asi.scale, improve.ASI_SCALE_PCT)
        self.assertEqual(asi.ceiling, improve.ASI_SCALE_PCT)
        self.assertGreaterEqual(asi.pct, 0)
        self.assertLessEqual(asi.pct, 100)
        self.assertEqual(asi.pct, max(0, min(100, int(round(asi.raw * 100)))))
        self.assertIn(f"{asi.pct}%", text)
        self.assertIn("toward ASI", asi.label)
        self.assertTrue(asi.phases)
        self.assertTrue(asi.current_phase_id)
        for phase in asi.phases:
            if phase.get("status") == "active":
                self.assertIn(phase.get("title", ""), text)
        payload = improve.horizon_payload(signals, cycle=3)
        self.assertFalse(payload["asi"]["achievable_today"])
        self.assertEqual(payload["asi"]["progress_pct"], asi.pct)
        self.assertEqual(payload["investment_north_star"], improve.INVESTMENT_NORTH_STAR)
        self.assertEqual(payload["asi"]["scale"], improve.ASI_SCALE_PCT)
        self.assertEqual(payload["asi"]["ceiling"], improve.ASI_SCALE_PCT)
        self.assertGreaterEqual(payload["asi"]["progress_pct"], 0)
        self.assertLessEqual(payload["asi"]["progress_pct"], 100)
        self.assertTrue(payload["asi"]["dimensions"])
        self.assertTrue(payload["asi"]["phases"])
        with mock.patch.object(improve, "queue_known_keys", return_value=set()):
            asi_opps = [o for o in improve.rank_opportunities(signals) if o.category == "asi"]
        self.assertTrue(asi_opps)
        self.assertEqual(asi_opps[0].priority, 99)
        self.assertIn("monster", improve.GOALS)

    def test_compute_asi_progress_phased_rubric(self) -> None:
        signals = improve.ImproveSignals(
            live={"tests_ok": True},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={
                "last_cycle": {
                    "ts": 1.0,
                    "rc": 0,
                    "verify_ok": True,
                    "queue_fp": "a",
                    "queue_fp_before": "a",
                    "noop": False,
                    "git_head": "abc",
                    "note": "",
                }
            },
            trend_report={"curated_count": 10, "gap_count": 2, "partial_count": 3, "have_count": 5},
        )
        asi = improve.compute_asi_progress(signals)
        self.assertEqual(asi.scale, improve.ASI_SCALE_PCT)
        self.assertEqual(asi.ceiling, improve.ASI_SCALE_PCT)
        self.assertEqual(asi.pct, max(0, min(100, int(round(asi.raw * 100)))))
        self.assertGreaterEqual(asi.pct, 0)
        self.assertLessEqual(asi.pct, 100)
        self.assertTrue(
            "toward ASI" in asi.label or "phased rubric complete" in asi.label,
            msg=asi.label,
        )
        self.assertIn("ASI", asi.label)
        self.assertTrue(asi.phases)
        self.assertFalse(
            improve.horizon_payload(signals)["asi"]["achievable_today"]
        )
        by_id = {d["id"]: d for d in asi.dimensions if d.get("id")}
        self.assertIn("verify_ok", by_id)
        self.assertEqual(by_id["verify_ok"]["score"], 1.0)
        bar = improve._asi_progress_bar(asi.pct)
        self.assertEqual(len(bar), 20)

    def test_last_cycle_raises_phased_score(self) -> None:
        """Runtime evidence (last_cycle + verify_ok) must not lower phased pct."""
        low = improve.ImproveSignals(
            live={"tests_ok": True},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
            trend_report={"curated_count": 10, "have_count": 1, "gap_count": 5, "partial_count": 4},
        )
        high = improve.ImproveSignals(
            live={"tests_ok": True},
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
            trend_report={"curated_count": 10, "have_count": 9, "gap_count": 0, "partial_count": 1},
        )
        low_p = improve.compute_asi_progress(low)
        high_p = improve.compute_asi_progress(high)
        self.assertGreaterEqual(high_p.pct, low_p.pct)
        self.assertGreater(high_p.pct, low_p.pct)
        self.assertGreaterEqual(high_p.pct, 0)
        self.assertLessEqual(high_p.pct, 100)
        self.assertEqual(high_p.pct, max(0, min(100, int(round(high_p.raw * 100)))))
        self.assertFalse(
            improve.horizon_payload(high)["asi"]["achievable_today"]
        )

    def test_maximize_parallel_and_improve_drives_work_on_real_repo(self) -> None:
        """Kit code probes: parallel orchestration + improve→work criteria exist."""
        signals = improve.ImproveSignals(
            live={},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
        )
        progress = improve.compute_asi_progress(signals)
        by_id = {d["id"]: d for d in progress.dimensions if d.get("id")}
        self.assertEqual(by_id["maximize_parallel"]["score"], 1.0)
        self.assertEqual(by_id["improve_drives_work"]["score"], 1.0)

    def test_plan_includes_industry_when_trends_present(self) -> None:
        signals = improve.ImproveSignals(
            live={"git": "clean", "tests": "ok", "queue_source": "empty", "open_items": []},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
            trend_report={"curated_count": 8, "gap_count": 1, "partial_count": 3},
            opportunities=[],
        )
        text = improve.build_plan_prompt(signals)
        self.assertIn("Industry trends", text)
        self.assertIn("AUTOMATION_TRENDS.md", text)
        self.assertIn("OSS monster factory", text)
        self.assertIn("Investment north star", text)

    def test_plan_prompt_says_plan_first(self) -> None:
        signals = improve.ImproveSignals(
            live={"git": "clean", "tests": "ok", "queue_source": "empty", "open_items": []},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
            opportunities=[
                improve.Opportunity("speed", "Faster self-check", "use --quick", priority=10),
            ],
        )
        text = improve.build_plan_prompt(signals)
        self.assertIn("PLAN FIRST", text)
        self.assertIn("Do **not** write code", text)
        self.assertIn("Faster self-check", text)
        self._assert_maximize_parallel_peers_wording(text)

    def test_execute_prompt_says_implement(self) -> None:
        signals = improve.ImproveSignals(
            live={},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
            opportunities=[improve.Opportunity("ease", "CLI", "peer help", priority=10)],
        )
        text = improve.build_execute_prompt(signals)
        self.assertIn("EXECUTE", text)
        self.assertIn("Orchestrate peers now", text)
        self.assertIn("self-check", text)
        self._assert_maximize_parallel_peers_wording(text)

    def _assert_maximize_parallel_peers_wording(self, text: str) -> None:
        """Prompts must push maximizing parallel Task peers/subagents, not only a ≥2 floor."""
        lowered = text.lower()
        self.assertTrue(
            "maximize parallel task" in lowered,
            "expected maximize-parallel Task peers/subagents wording",
        )
        self.assertTrue(
            "subagent" in lowered or "peer" in lowered,
            "expected subagents or peers in maximize-parallel guidance",
        )


class ImproveWriteTests(unittest.TestCase):
    def _empty_signals(self) -> improve.ImproveSignals:
        return improve.ImproveSignals(
            live={"git": "clean", "tests": "ok", "queue_source": "empty", "open_items": []},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
            opportunities=[],
        )

    def test_write_prompts_creates_files(self) -> None:
        signals = self._empty_signals()
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            with mock.patch.object(improve, "CONFIG_DIR", config_dir), mock.patch.object(
                improve, "PLAN_PATH", config_dir / "automation-improve-plan.md"
            ), mock.patch.object(
                improve, "EXECUTE_PATH", config_dir / "automation-improve-execute.md"
            ), mock.patch.object(
                improve, "COMBINED_PATH", config_dir / "automation-improve.md"
            ):
                paths = improve.write_prompts(signals, plan=True, execute=True, combined=True)
                self.assertEqual(len(paths), 3)
                self.assertTrue((config_dir / "automation-improve-plan.md").is_file())

    def test_write_prompts_reuses_plan_execute_once(self) -> None:
        """plan+execute+combined must build each body once (not 4× via build_combined)."""
        signals = self._empty_signals()
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            with mock.patch.object(improve, "CONFIG_DIR", config_dir), mock.patch.object(
                improve, "PLAN_PATH", config_dir / "automation-improve-plan.md"
            ), mock.patch.object(
                improve, "EXECUTE_PATH", config_dir / "automation-improve-execute.md"
            ), mock.patch.object(
                improve, "COMBINED_PATH", config_dir / "automation-improve.md"
            ), mock.patch.object(
                improve, "build_plan_prompt", return_value="PLAN_BODY"
            ) as bp, mock.patch.object(
                improve, "build_execute_prompt", return_value="EXEC_BODY"
            ) as be:
                paths = improve.write_prompts(signals, plan=True, execute=True, combined=True)
                self.assertEqual(len(paths), 3)
                self.assertEqual(bp.call_count, 1)
                self.assertEqual(be.call_count, 1)
                combined = (config_dir / "automation-improve.md").read_text(encoding="utf-8")
                self.assertEqual(combined, "PLAN_BODY\n\n---\n\nEXEC_BODY\n")

    def test_write_prompts_skips_rewrite_when_unchanged(self) -> None:
        signals = self._empty_signals()
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            plan_path = config_dir / "automation-improve-plan.md"
            exec_path = config_dir / "automation-improve-execute.md"
            combined_path = config_dir / "automation-improve.md"
            with mock.patch.object(improve, "CONFIG_DIR", config_dir), mock.patch.object(
                improve, "PLAN_PATH", plan_path
            ), mock.patch.object(
                improve, "EXECUTE_PATH", exec_path
            ), mock.patch.object(
                improve, "COMBINED_PATH", combined_path
            ), mock.patch.object(
                improve, "WRITE_PROMPTS_FP_PATH", config_dir / "improve-prompts.fp"
            ), mock.patch.object(
                improve, "build_plan_prompt", return_value="PLAN_BODY"
            ), mock.patch.object(
                improve, "build_execute_prompt", return_value="EXEC_BODY"
            ):
                improve.write_prompts(signals, plan=True, execute=True, combined=True)
                mtimes = {
                    p: p.stat().st_mtime_ns
                    for p in (plan_path, exec_path, combined_path)
                }
                improve.write_prompts(signals, plan=True, execute=True, combined=True)
                for p, before in mtimes.items():
                    self.assertEqual(p.stat().st_mtime_ns, before, msg=p.name)



    def test_write_prompts_skips_build_when_fingerprint_ttl_fresh(self) -> None:
        """OVERSEER_WRITE_PROMPTS_TTL_2026_09_04 — no ASI rebuild when fp+TTL fresh."""
        signals = self._empty_signals()
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            with mock.patch.object(improve, "CONFIG_DIR", config_dir), mock.patch.object(
                improve, "PLAN_PATH", config_dir / "automation-improve-plan.md"
            ), mock.patch.object(
                improve, "EXECUTE_PATH", config_dir / "automation-improve-execute.md"
            ), mock.patch.object(
                improve, "COMBINED_PATH", config_dir / "automation-improve.md"
            ), mock.patch.object(
                improve, "WRITE_PROMPTS_FP_PATH", config_dir / "improve-prompts.fp"
            ), mock.patch.object(
                improve, "write_prompts_ttl_sec", return_value=120.0
            ), mock.patch.object(
                improve, "build_plan_prompt", return_value="PLAN_BODY"
            ) as bp, mock.patch.object(
                improve, "build_execute_prompt", return_value="EXEC_BODY"
            ) as be:
                first = improve.write_prompts(signals, plan=True, execute=True, combined=True)
                self.assertEqual(len(first), 3)
                self.assertEqual(bp.call_count, 1)
                second = improve.write_prompts(signals, plan=True, execute=True, combined=True)
                self.assertEqual(second, first)
                self.assertEqual(bp.call_count, 1)

    def test_write_prompts_rebuilds_when_signals_change(self) -> None:
        signals = self._empty_signals()
        changed = self._empty_signals()
        changed.audit_ok = False
        changed.audit_errors = ["stale"]
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            with mock.patch.object(improve, "CONFIG_DIR", config_dir), mock.patch.object(
                improve, "PLAN_PATH", config_dir / "automation-improve-plan.md"
            ), mock.patch.object(
                improve, "EXECUTE_PATH", config_dir / "automation-improve-execute.md"
            ), mock.patch.object(
                improve, "COMBINED_PATH", config_dir / "automation-improve.md"
            ), mock.patch.object(
                improve, "WRITE_PROMPTS_FP_PATH", config_dir / "improve-prompts.fp"
            ), mock.patch.object(
                improve, "write_prompts_ttl_sec", return_value=120.0
            ), mock.patch.object(
                improve, "build_plan_prompt", return_value="PLAN_BODY"
            ) as bp, mock.patch.object(
                improve, "build_execute_prompt", return_value="EXEC_BODY"
            ) as be:
                improve.write_prompts(signals, plan=True, execute=True, combined=True)
                improve.write_prompts(changed, plan=True, execute=True, combined=True)
                self.assertEqual(bp.call_count, 2)

    def test_signals_prompt_fingerprint_zlib_needle(self) -> None:
        """OVERSEER_IMPROVE_HUB_ZLIB_FP_2026_09_04 — hub zlib fp (no hashlib)."""
        signals = self._empty_signals()
        fp = improve._signals_prompt_fingerprint(signals)
        self.assertEqual(len(fp), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in fp))
        self.assertIn(
            "COMPRESSION_ZLIB_WRITE_PROMPTS_FP_2026_09_04",
            improve._signals_prompt_fingerprint.__doc__ or "",
        )


class ImproveMainTests(unittest.TestCase):
    def test_json_output_structure(self) -> None:
        with mock.patch.object(improve, "gather_signals") as gather:
            gather.return_value = improve.ImproveSignals(
                live={"tests_ok": True},
                audit_ok=True,
                audit_warnings=[],
                audit_errors=[],
                queue_drift=[],
                loop_state={},
                opportunities=[],
            )
            with mock.patch("sys.argv", ["automation_improve.py", "--json", "--plan"]):
                with mock.patch("sys.stdout") as stdout:
                    rc = improve.main()
                    self.assertEqual(rc, 0)
                    payload = json.loads("".join(c.args[0] for c in stdout.write.call_args_list if c.args))
                    self.assertIn("goals", payload)
                    self.assertIn("plan_prompt", payload)


class ImproveContinuousTests(unittest.TestCase):
    def test_has_continuous_work_from_opportunities(self) -> None:
        signals = improve.ImproveSignals(
            live={},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
            opportunities=[improve.Opportunity("smooth", "Fix peer_loop", "scope", priority=5)],
        )
        self.assertTrue(improve._has_continuous_work(signals))

    def test_wake_timeout_shorter_when_work_remains(self) -> None:
        idle = improve.improve_wake_timeout(has_work=False, elapsed=0.0)
        active = improve.improve_wake_timeout(has_work=True, elapsed=0.0)
        self.assertLess(active, idle)

    def test_continuous_min_cycle_below_idle_gap(self) -> None:
        self.assertLess(improve.improve_continuous_min_cycle_sec(), improve.MIN_CYCLE_GAP_SEC)

    def test_improve_wake_floors_hyper_overlay(self) -> None:
        """dgx_speed overlay of 3s must not become a 5s improve poll (probe miss)."""
        cfg = dict(improve.auto.CFG)
        cfg["improve_continuous_wake_sec"] = 3
        cfg["improve_continuous_min_cycle_sec"] = 3
        with unittest.mock.patch.object(improve.auto, "CFG", cfg):
            self.assertGreaterEqual(improve.improve_continuous_wake_sec(), 15.0)
            self.assertGreaterEqual(improve.improve_continuous_min_cycle_sec(), 10.0)

    def test_adapt_heal_check_helpers_roundtrip(self) -> None:
        """OVERSEER_ADAPT_HEAL_HELPERS_2026_09_04 — hub must define TTL helpers."""
        self.assertTrue(callable(improve.adapt_heal_check_fresh))
        self.assertTrue(callable(improve.mark_adapt_heal_check))
        with mock.patch.object(improve, "_ADAPT_HEAL_CHECK_PATH") as path:
            path.is_file.return_value = False
            self.assertFalse(improve.adapt_heal_check_fresh())
            path.is_file.return_value = True
            path.stat.return_value = mock.Mock(st_mtime=time.time())
            self.assertTrue(improve.adapt_heal_check_fresh())
            path.stat.return_value = mock.Mock(st_mtime=time.time() - 10_000)
            self.assertFalse(improve.adapt_heal_check_fresh())

    def test_idle_cycle_still_wakes_peer(self) -> None:
        """OVERSEER_IDLE_HEARTBEAT_WAKE_2026_09_04 — empty Active must wake."""
        signals = improve.ImproveSignals(
            live={"open_items": []},
            audit_ok=True,
            audit_warnings=[],
            audit_errors=[],
            queue_drift=[],
            loop_state={},
            opportunities=[],
        )
        logs: list[str] = []
        with mock.patch.object(improve, "gather_signals", return_value=signals):
            with mock.patch.object(improve, "write_prompts", return_value=[]):
                with mock.patch.object(improve, "write_horizon", return_value=["h"]):
                    with mock.patch.object(improve, "apply_mechanical", return_value=[]):
                        with mock.patch.object(
                            improve, "enqueue_work_opportunities", return_value=[]
                        ):
                            with mock.patch.object(
                                improve, "enqueue_phase_plan", return_value=None
                            ):
                                with mock.patch.object(
                                    improve, "_has_continuous_work", return_value=False
                                ):
                                    with mock.patch.object(
                                        improve, "wake_peer"
                                    ) as wake:
                                        with mock.patch(
                                            "automation_team.hand_out_worker_pool",
                                            return_value=[],
                                        ):
                                            improve.run_improve_cycle(
                                                quick=True,
                                                research=False,
                                                refresh_trends=False,
                                                log_fn=logs.append,
                                                run_verify=False,
                                            )
                                            wake.assert_called()
        self.assertTrue(
            any("heartbeat wake" in m.lower() or "healthy idle" in m.lower() for m in logs),
            logs[-8:],
        )


if __name__ == "__main__":
    unittest.main()
