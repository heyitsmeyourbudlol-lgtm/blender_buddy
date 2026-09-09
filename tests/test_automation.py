"""Tests for automation scripts (queue parsing, plan building, config validation)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402
import peer_orchestrate as po  # noqa: E402
import peer_roles as roles  # noqa: E402


class AutomationQueueTests(unittest.TestCase):
    def test_parse_checkbox_remaining(self) -> None:
        md = """
## Remaining work (priority order)

1. [ ] **Gauge actions** — lazy load
2. [x] **Done item** — skip
"""
        items = auto.remaining_work_items(md)
        self.assertEqual(len(items), 1)
        self.assertIn("Gauge", items[0])

    def test_remaining_work_items_plain_header(self) -> None:
        """OVERSEER_REMAINING_PLAIN_HEADER_2026_09_07 — plain ## Remaining work."""
        md = """
## Remaining work

- [ ] **Plain header task** — must be visible to dual-brain
- [x] **Done item** — skip
"""
        items = auto.remaining_work_items(md)
        self.assertEqual(len(items), 1)
        self.assertIn("Plain header", items[0])

    def test_creative_backlog_items_short_heading(self) -> None:
        """OVERSEER_CREATIVE_BACKLOG_SHORT_HEADING_2026_09_08 — WQ uses short heading."""
        md = """
## Active

- [x] **Done active** — skip

## Creative backlog

- [ ] **[top10] Soft push when creds restored** — human-auth demote
- [x] **Done creative** — skip
"""
        items = auto.creative_backlog_items(md)
        self.assertEqual(len(items), 1)
        self.assertIn("Soft push", items[0])

    def test_active_twin_sic_no_false_dual_brain(self) -> None:
        """OVERSEER_ACTIVE_TWIN_DRIFT_2026_09_07 — Active-only twin ≠ context=0."""
        wq = """## Active

- [ ] **Ship factory fix** — real work
- [ ] **Top10 next** — keep open

## Backlog
"""
        ctx = wq  # heal restore / Mac twin: identical Active, no Remaining
        self.assertEqual(auto.remaining_work_items(ctx), [])
        opens = auto.context_queue_open_items(ctx)
        self.assertEqual(len(opens), 2)
        drift = auto.sync_queue_drift(ctx, wq)
        self.assertEqual(drift, [], drift)

    def test_newdrop_after_n_survives_open_done_strip(self) -> None:
        """OVERSEER_NEWDROP_QUEUE_KEY_AFTER_2026_09_07 — after #N ≠ landed #N key."""
        open_after = (
            "**[top10] Newdrop production — next meaningful non-UI merge** — "
            "after #53; file-scoped `/Users/togi/CaaS`"
        )
        landed = (
            "**[top10] Newdrop production — next meaningful non-UI merge** — "
            "landed 2026-09-08 [#53](https://example.invalid/53) · after #51 · NO PAY"
        )
        self.assertNotEqual(
            auto._normalize_queue_key(open_after),
            auto._normalize_queue_key(landed),
        )
        self.assertIn("after #53", auto._normalize_queue_key(open_after))
        self.assertIn("landed #53", auto._normalize_queue_key(landed))
        wq = f"""## Active

- [x] {landed}
- [ ] {open_after}
- [ ] **[factory] Kit-run eighth registry target** — pick next

## Backlog
"""
        # SIC mid-fuel: open after #N without the matching [x] yet → old key
        # collision stripped WQ open and left SIC-only dual-brain.
        ctx = f"""## Active

- [ ] {open_after}
- [ ] **[factory] Kit-run eighth registry target** — pick next

## Remaining work
"""
        new_wq, stripped_w = auto.strip_open_done_dupes(wq)
        new_ctx, stripped_c = auto.strip_open_done_dupes(ctx)
        self.assertEqual(stripped_w, 0, "after #53 must not strip against landed #53")
        self.assertEqual(stripped_c, 0)
        wq_opens = auto._parse_phased_work_items(new_wq)
        self.assertTrue(any("after #53" in i for i in wq_opens), wq_opens)
        drift = auto.sync_queue_drift(new_ctx, new_wq)
        self.assertEqual(drift, [], drift)
        self.assertIn(
            "OVERSEER_NEWDROP_QUEUE_KEY_AFTER_2026_09_07",
            Path(auto.__file__).read_text(encoding="utf-8"),
        )

    def test_dedupe_newdrop_after_n_keeps_highest(self) -> None:
        """OVERSEER_NEWDROP_AFTER_N_DEDUP_2026_09_08 — only highest after #N stays open."""
        md = """## Active

- [ ] **[top10] Newdrop production — next meaningful non-UI merge** — after #148; file-scoped
- [ ] **[top10] Newdrop production — next meaningful non-UI merge** — after #150; file-scoped
- [ ] **[factory] Kit-run twenty-first registry target** — freesurfsharkone

## Backlog
"""
        new_md, n = auto.dedupe_newdrop_after_n_opens(md)
        self.assertEqual(n, 1)
        self.assertIn("- [ ] **[top10] Newdrop production", new_md)
        self.assertIn("after #150", new_md)
        self.assertIn("- [x] **[top10] Newdrop production", new_md)
        self.assertIn("superseded by after #150", new_md)
        self.assertIn("after #148", new_md)
        self.assertIn("- [ ] **[factory] Kit-run twenty-first", new_md)
        self.assertIn(
            "OVERSEER_NEWDROP_AFTER_N_DEDUP_2026_09_08",
            Path(auto.__file__).read_text(encoding="utf-8"),
        )

    def test_dedupe_newdrop_after_n_collapses_active_remaining_twin(self) -> None:
        """Same highest after #N in Active + Remaining → keep Active only."""
        md = """## Active

- [ ] **[top10] Newdrop production — next meaningful non-UI merge** — after #161; file-scoped
- [ ] **[factory] Kit-run twenty-third registry target** — scratch

## Remaining work (priority order)
- [ ] **[top10] Newdrop production — next meaningful non-UI merge** — after #161; file-scoped
- [ ] **[factory] Kit-run twenty-third registry target** — scratch
"""
        new_md, n = auto.dedupe_newdrop_after_n_opens(md)
        self.assertEqual(n, 1)
        opens = [ln for ln in new_md.splitlines() if ln.startswith("- [ ]") and "newdrop" in ln.lower()]
        self.assertEqual(len(opens), 1)
        self.assertIn("after #161", opens[0])
        self.assertIn("Active∪Remaining twin of after #161", new_md)
        self.assertIn("OVERSEER_NEWDROP_AFTER_N_DEDUP_2026_09_08", new_md)

    def test_context_open_unions_stale_remaining_with_active(self) -> None:
        """OVERSEER_CTX_OPEN_UNION_ACTIVE_REMAINING_2026_09_07 — subset Remaining ≠ drift."""
        wq = """## Active

- [ ] **Alpha factory** — keep
- [ ] **Beta top10** — keep

## Backlog
"""
        # Remaining missing Beta while Active has both — old Remaining-only compare drifted.
        ctx = """## Active

- [ ] **Alpha factory** — keep
- [ ] **Beta top10** — keep

## Remaining work (priority order)
- [ ] **Alpha factory** — keep

## Backlog
"""
        opens = auto.context_queue_open_items(ctx)
        keys = {auto._normalize_queue_key(i) for i in opens}
        self.assertIn(auto._normalize_queue_key("**Beta top10** — keep"), keys)
        self.assertEqual(auto.sync_queue_drift(ctx, wq), [])
        self.assertIn(
            "OVERSEER_CTX_OPEN_UNION_ACTIVE_REMAINING_2026_09_07",
            Path(auto.__file__).read_text(encoding="utf-8"),
        )

    def test_insert_remaining_work_bullet_priority_order(self) -> None:
        md = "## Remaining work (priority order)\n\n- [ ] existing\n"
        out = auto.insert_remaining_work_bullet(md, "- [ ] **new** — task")
        self.assertIn("- [ ] **new** — task", out)
        self.assertTrue(out.index("new") < out.index("existing"))

    def test_insert_remaining_work_bullet_plain_header(self) -> None:
        md = "## Remaining work\n\n- [ ] existing\n"
        out = auto.insert_remaining_work_bullet(md, "- [ ] **new** — task")
        self.assertIn("- [ ] **new** — task", out)

    def test_open_work_items_prefers_work_queue(self) -> None:
        ctx = "## Remaining work (priority order)\n\n1. [ ] Context only"
        wq = "## Active items\n\n1. [ ] **From queue** — task\n\n## Done"
        state = auto.open_work_items(ctx, wq)
        self.assertEqual(state.source, "launch")
        self.assertIn("From queue", state.open_items[0])

    def test_open_work_items_parses_launch_phases(self) -> None:
        wq = """
## Phase 0 — Ship

1. [ ] **Newdrop changelog** — setup
2. [x] **Done item** — skip

## Phase 1 — GitHub

3. [ ] **Repo public** — release

## Creative backlog
"""
        state = auto.open_work_items("", wq)
        self.assertEqual(state.source, "launch")
        self.assertEqual(len(state.open_items), 2)
        self.assertIn("Newdrop", state.open_items[0])
        self.assertIn("Repo public", state.open_items[1])

    def test_launch_track_active(self) -> None:
        wq = "## Phase 0\n\n1. [ ] **Task** — x\n\n## Creative backlog"
        self.assertTrue(auto.launch_track_active(wq))
        wq_done = "## Phase 0\n\n1. [x] **Task** — x\n\n## Creative backlog"
        self.assertFalse(auto.launch_track_active(wq_done))

    def test_parse_phased_stops_on_double_space_backlog(self) -> None:
        # OVERSEER_PHASED_BACKLOG_FLEX_WS_2026_09_08 — "##  Backlog" must not
        # stay in Active track (startswith("## Backlog") misses extra ws).
        wq = """## Active

- [ ] **Keep active** — only this

##  Backlog (deferred — Top10 freeze)

- [ ] **Daily flaw scan** — demoted Top10 freeze
- [ ] **[niche-distill] Stamp practice runner N02** — demoted Top10 freeze

## Remaining work (priority order)

- [ ] **Should not matter** — remaining
"""
        phased = auto._parse_phased_work_items(wq)
        self.assertEqual(len(phased), 1)
        self.assertIn("Keep active", phased[0])
        self.assertFalse(any("Daily flaw" in t for t in phased))
        self.assertFalse(any("niche-distill" in t for t in phased))

    def test_done_line_inline_x(self) -> None:
        self.assertTrue(auto._is_done_line("1. **Foo** ([x] done)"))

    def test_strip_backlog_active_clones(self) -> None:
        wq = """## Active

- [ ] **[output] External proof** — do it now
- [ ] **Unique active** — stay

## Backlog (deferred)

- [ ] **[output] External proof** — older twin
- [ ] **Backlog only** — keep
"""
        new_md, removed = auto.strip_backlog_active_clones(wq)
        self.assertEqual(removed, 1)
        self.assertIn("Unique active", new_md)
        self.assertIn("Backlog only", new_md)
        self.assertEqual(new_md.count("External proof"), 1)
        self.assertIn("## Active", new_md)
        # Active copy kept
        active = new_md.split("## Backlog")[0]
        self.assertIn("External proof", active)

    def test_dedupe_open_work_queue_backlog_twins(self) -> None:
        wq = """## Active

- [ ] **Keep active** — one

## Backlog (deferred)

- [ ] **[auto] Break noop loop** — first
- [ ] **Backlog only** — keep
- [ ] **[auto] Break noop loop** — twin
"""
        new_md, removed = auto.dedupe_open_work_queue(wq)
        self.assertEqual(removed, 1)
        self.assertEqual(new_md.count("Break noop loop"), 1)
        self.assertIn("Keep active", new_md)
        self.assertIn("Backlog only", new_md)
        self.assertIn("— first", new_md)

    def test_resolve_satisfied_wake_interval_marks_done(self) -> None:
        md = """## Active

- [ ] **[efficiency-research] Tune wake interval — pre-dispatch over hyper poll** — continuous_wake_sec=3.0
- [ ] **Unblock dirty tree** — stay open
"""
        marked, resolved = auto.resolve_satisfied_wake_interval(md, wake_ok=True)
        self.assertEqual(resolved, 1)
        self.assertIn("- [x] **[efficiency-research] Tune wake interval", marked)
        self.assertIn("- [ ] **Unblock dirty tree**", marked)
        noop, resolved_off = auto.resolve_satisfied_wake_interval(md, wake_ok=False)
        self.assertEqual(resolved_off, 0)
        self.assertIn("- [ ] **[efficiency-research] Tune wake interval", noop)

    def test_md_has_open_marker_ignores_checked_off(self) -> None:
        md = """## Active

- [x] **[flaw-research] Peer loop daemon not running** — historical
- [ ] **Keep working** — real work
"""
        self.assertFalse(
            auto._md_has_open_marker(md, auto._STALE_DAEMON_FLAW_MARKERS)
        )
        open_md = md.replace(
            "- [x] **[flaw-research] Peer loop daemon not running**",
            "- [ ] **[flaw-research] Peer loop daemon not running**",
        )
        self.assertTrue(
            auto._md_has_open_marker(open_md, auto._STALE_DAEMON_FLAW_MARKERS)
        )

    def test_compact_skips_daemon_snapshot_when_no_open_markers(self) -> None:
        """COMPACT_SKIP_DAEMON_SNAP — checked-off markers must not force snapshot."""
        wq = """## Active

- [x] **[flaw-research] Peer loop daemon not running** — already fixed
- [x] **[efficiency-research] Tune wake interval — pre-dispatch over hyper poll** — done
"""
        ctx = "## Remaining work (priority order)\n\n- [ ] Discover clever non-obvious improvements\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wq_path = root / "WORK_QUEUE.md"
            ctx_path = root / "context.md"
            wq_path.write_text(wq, encoding="utf-8")
            ctx_path.write_text(ctx, encoding="utf-8")
            with unittest.mock.patch.object(auto, "WORK_QUEUE_PATH", wq_path), unittest.mock.patch.object(
                auto, "CONTEXT_PATH", ctx_path
            ), unittest.mock.patch.object(
                auto, "load_work_queue_md", return_value=wq
            ), unittest.mock.patch.object(
                auto, "load_context_md", return_value=ctx
            ), unittest.mock.patch(
                "peer_self_heal.daemon_status_snapshot"
            ) as snap, unittest.mock.patch(
                "peer_loop.effective_continuous_wake_sec"
            ) as wake:
                removed, actions = auto.compact_executable_queue(write=False, max_active=12)
                self.assertEqual(removed, 0)
                snap.assert_not_called()
                wake.assert_not_called()

    def test_compact_skips_met_transcript_when_no_open_met_markers(self) -> None:
        """COMPACT_SKIP_MET_TRANSCRIPT_NO_OPEN — Done MET history must not force transcript."""
        wq = """## Active

- [ ] **[top10] Real fuel** — keep open
- [x] **[auto] Break noop loop** — already closed MET history
- [x] **Fix verify gate** — seeded last_cycle already satisfied
"""
        ctx = "## Remaining work (priority order)\n\n- [ ] Discover clever non-obvious improvements\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wq_path = root / "WORK_QUEUE.md"
            ctx_path = root / "context.md"
            wq_path.write_text(wq, encoding="utf-8")
            ctx_path.write_text(ctx, encoding="utf-8")
            with unittest.mock.patch.object(auto, "WORK_QUEUE_PATH", wq_path), unittest.mock.patch.object(
                auto, "CONTEXT_PATH", ctx_path
            ), unittest.mock.patch.object(
                auto, "load_work_queue_md", return_value=wq
            ), unittest.mock.patch.object(
                auto, "load_context_md", return_value=ctx
            ), unittest.mock.patch(
                "peer_transcript.load_state"
            ) as load_state, unittest.mock.patch(
                "peer_worktree.continue_on_dirty_enabled"
            ) as cod, unittest.mock.patch.object(
                auto, "resolve_satisfied_met_theater", wraps=auto.resolve_satisfied_met_theater
            ) as met:
                removed, actions = auto.compact_executable_queue(write=False, max_active=12)
                self.assertEqual(removed, 0)
                load_state.assert_not_called()
                cod.assert_not_called()
                met.assert_not_called()

    def test_compact_calls_daemon_snapshot_when_open_daemon_flaw(self) -> None:
        wq = """## Active

- [ ] **[flaw-research] Peer loop daemon not running** — fix me
"""
        ctx = "## Remaining work (priority order)\n\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wq_path = root / "WORK_QUEUE.md"
            ctx_path = root / "context.md"
            wq_path.write_text(wq, encoding="utf-8")
            ctx_path.write_text(ctx, encoding="utf-8")
            with unittest.mock.patch.object(auto, "WORK_QUEUE_PATH", wq_path), unittest.mock.patch.object(
                auto, "CONTEXT_PATH", ctx_path
            ), unittest.mock.patch.object(
                auto, "load_work_queue_md", return_value=wq
            ), unittest.mock.patch.object(
                auto, "load_context_md", return_value=ctx
            ), unittest.mock.patch(
                "peer_self_heal.daemon_status_snapshot",
                return_value={
                    "peer_loop": True,
                    "improve_loop": True,
                    "dual_namespace": False,
                },
            ) as snap:
                removed, actions = auto.compact_executable_queue(write=False, max_active=12)
                snap.assert_called_once()
                self.assertGreaterEqual(removed, 1)

    def test_strip_flaw_research_drift_meta_orphans(self) -> None:
        md = """## Active

- [ ] **Keep me** — real work
  ✗ only in notes/WORK_QUEUE.md: **[efficiency-research] Tune wake interval — pre-dispa
- [x] **[flaw-research] peer_orchestrate self-check failed** — ✗ only in notes/WORK_QUEUE.md: wrapped
"""
        new_md, removed = auto.strip_flaw_research_drift_meta(md)
        self.assertGreaterEqual(removed, 1)
        self.assertIn("Keep me", new_md)
        self.assertNotIn("pre-dispa", new_md)

    def test_close_stale_sync_queue_meta(self) -> None:
        """OVERSEER_CLOSE_STALE_SYNC_META_2026_09_08 — Sync theater → [x]."""
        md = (
            "## Active\n\n"
            "- [ ] **Sync WORK_QUEUE ↔ context** — CLEAN empty-Active while context "
            "has Top10 opens — restore WORK_QUEUE (1 item(s); Mac↔CLEAN twin)\n"
            "- [ ] **[top10] Newdrop tip-cover after #177** — Soft Soft-land OK\n\n"
            "## Backlog\n"
        )
        new_md, closed = auto.close_stale_sync_queue_meta(md)
        self.assertEqual(closed, 1)
        self.assertIn("OVERSEER_CLOSE_STALE_SYNC_META_2026_09_08", new_md)
        self.assertRegex(new_md, r"- \[x\] \*\*Sync WORK_QUEUE")
        self.assertIn("- [ ] **[top10] Newdrop tip-cover after #177**", new_md)
        # Idempotent when already closed
        again, closed2 = auto.close_stale_sync_queue_meta(new_md)
        self.assertEqual(closed2, 0)
        self.assertEqual(again, new_md)


class AutomationPlanTests(unittest.TestCase):
    def test_merge_same_peer(self) -> None:
        raw = [
            po.PeerTask("footprint", "generalPurpose", "green", "A", ["a.py"], "do A"),
            po.PeerTask("footprint", "generalPurpose", "green", "B", ["b.py"], "do B"),
        ]
        merged = po._merge_implementation_tasks(raw)
        self.assertEqual(len(merged), 1)
        self.assertEqual(set(merged[0].scope), {"a.py", "b.py"})

    def test_format_prompt_phase_gates(self) -> None:
        plan = po.PeerPlan(
            orchestrator_brief="Orchestrate test peers.",
            tasks=[
                po.PeerTask(
                    "reclaim",
                    "generalPurpose",
                    "yellow",
                    "Item A",
                    ["a.py"],
                    "do A",
                ),
                po.PeerTask(
                    "footprint",
                    "generalPurpose",
                    "green",
                    "Item B",
                    ["b.py"],
                    "do B",
                ),
                po.PeerTask(
                    "safety",
                    "generalPurpose",
                    "green",
                    "Safety review",
                    [],
                    "Review changes.",
                ),
                po.PeerTask(
                    "verify",
                    "shell",
                    "green",
                    "Verify",
                    [],
                    "Run tests.",
                ),
            ],
            live={},
            stop=False,
            stop_reason=None,
        )
        prompt = po.format_prompt(plan)
        self.assertIn("## Phase gates (run in order — do not skip)", prompt)
        self.assertIn("Plan / Orchestrate", prompt)
        self.assertIn("Parallel Implement", prompt)
        self.assertIn("## Phase 3 — Safety", prompt)
        self.assertIn("## Phase 4 — Verify", prompt)
        self.assertIn("## Phase 5 — Merge rules", prompt)
        self.assertIn("Maximize parallel Task peers", prompt)
        self.assertIn("ONE", prompt)
        # Prefer maximize-full-set wording over a bare ≥2 floor alone.
        self.assertTrue(
            "maximize parallel task peers" in prompt.lower(),
            "peer_orchestrate prompt should maximize parallel Task peers/subagents",
        )
        self.assertRegex(
            prompt,
            r"(?i)never solo|never collapse independent scopes",
        )

    def test_format_prompt_uses_hub_worker_pool_not_peer_floor(self) -> None:
        import peer_roles as roles

        plan = po.PeerPlan(
            orchestrator_brief="Orchestrate test peers.",
            tasks=[
                po.PeerTask("reclaim", "generalPurpose", "green", "Item A", ["a.py"], "do A"),
            ],
            live={},
            stop=False,
            stop_reason=None,
        )
        with unittest.mock.patch.object(auto, "max_parallel_peers", return_value=48):
            with unittest.mock.patch.object(auto, "parallel_peer_floor", return_value=48):
                with unittest.mock.patch.object(roles, "worker_pool_size", return_value=8):
                    text = po.format_prompt(plan)
        self.assertIn("launch **8** implementation Task tool calls", text)
        self.assertIn("hub launch ≤8", text)
        self.assertNotIn("target **48** workers", text)

    def test_hub_dispatch_cap_clamps_to_worker_pool(self) -> None:
        import peer_parallel_dispatch as ppd
        import peer_roles as roles

        # OVERSEER_HUB_CAP_TEST_IGNORE_LIVE_OVERSEER_2026_09_07 — live overseer
        # reserve (desk-over) must not flake this clamp unit when COD is up.
        with unittest.mock.patch.object(ppd, "max_parallel_agent_procs", return_value=48):
            with unittest.mock.patch.object(roles, "worker_pool_size", return_value=8):
                with unittest.mock.patch.object(ppd, "count_overseer_procs", return_value=0):
                    with unittest.mock.patch.object(ppd, "free_desktop_agent_cap", return_value=8):
                        self.assertEqual(ppd.hub_dispatch_cap(), 8)

    def test_validate_tasks_config_ok(self) -> None:
        cfg = auto.load_tasks_config()
        issues = auto.validate_tasks_config(cfg)
        self.assertEqual(issues, [])

    def test_build_plan_has_tasks_when_queue_open(self) -> None:
        os.environ["RAM_AUTOMATION_NO_SUBTEST"] = "1"
        try:
            plan = po.build_plan(force=True, quick=True)
            if plan.live.get("open_items"):
                self.assertGreater(len(plan.tasks), 0)
        finally:
            os.environ.pop("RAM_AUTOMATION_NO_SUBTEST", None)

    def test_next_experiment_items_skips_done(self) -> None:
        md = """
## Next experiments (non-obvious)

1. ~~**Done**~~ — skip
2. **GPU flush** — Metal caches
"""
        items = auto.next_experiment_items(md)
        self.assertEqual(len(items), 1)
        self.assertIn("GPU", items[0])

    def test_loop_plan_has_experiments_when_complete(self) -> None:
        os.environ["RAM_AUTOMATION_NO_SUBTEST"] = "1"
        try:
            plan = po.build_plan(quick=True, loop=True)
            if plan.live.get("queue_source") == "experiments":
                self.assertGreater(len(plan.tasks), 0)
                self.assertFalse(plan.stop)
        finally:
            os.environ.pop("RAM_AUTOMATION_NO_SUBTEST", None)

    def test_stop_reason_ignores_status_complete_in_loop(self) -> None:
        ctx = "## Status\n\ncomplete\n\n## Loop\n\nactive\n"
        live = auto.LiveState(True, "clean", True, "ok", 13.0, "ok")
        reason = auto.stop_reason(ctx, live, loop=True)
        self.assertIsNone(reason)

    def test_loop_mine_when_pipeline_empty(self) -> None:
        ctx = "## Loop\n\nactive\n"
        live = auto.LiveState(True, "clean", True, "ok", 13.0, "ok")
        # self_sufficient skips mine theater (queue_fp freeze); opt out for mine path.
        with unittest.mock.patch.object(auto, "factory_meter_mode", return_value="external"), unittest.mock.patch.object(
            auto, "next_experiment_items", return_value=[]
        ):
            q = auto.loop_work_items(ctx, "", live=live)
        self.assertEqual(q.source, "mine")
        self.assertIn("clever", q.open_items[0].lower())
        with unittest.mock.patch.object(auto, "factory_meter_mode", return_value="self_sufficient"):
            idle = auto.loop_work_items(ctx, "", live=live)
        self.assertEqual(idle.source, "empty")
        self.assertEqual(idle.open_items, [])

    def test_loop_exhausted_stops(self) -> None:
        ctx = "## Loop\n\nexhausted\n"
        live = auto.LiveState(True, "clean", True, "ok", 13.0, "ok")
        reason = auto.stop_reason(ctx, live, loop=True)
        self.assertIsNotNone(reason)
        self.assertIn("exhausted", reason.lower())


class PeerLoopTests(unittest.TestCase):
    def test_metrics_green(self) -> None:
        import peer_loop

        live = auto.LiveState(True, "clean", True, "ok", 13.0, "ok")
        self.assertTrue(peer_loop.metrics_green(live))
        # WORKING + continue_on_dirty: dirty tree must not paint metrics red
        # Needle: OVERSEER_METRICS_DIRTY_OK_2026_09_03
        # OVERSEER_METRICS_TESTS_ONLY_2026_09_04 — assertFalse only when tests_ok=False
        dirty_ok = auto.LiveState(False, "dirty", True, "ok", 13.0, "ok")
        self.assertTrue(peer_loop.metrics_green(dirty_ok))
        tests_bad = auto.LiveState(True, "clean", False, "fail", 13.0, "ok")
        self.assertFalse(peer_loop.metrics_green(tests_bad))

    def test_resolve_coding_cwd_uses_coding_worktree_when_dirty(self) -> None:
        """T10-08: dirty hub + continue_on_dirty → coding worktree cwd."""
        import peer_loop
        import peer_worktree as wt

        coding = Path("/tmp/t10-08-peer-coding")
        logs: list[str] = []
        dirty = auto.LiveState(False, "dirty (242 paths)", True, "ok", 13.0, "ok")
        with unittest.mock.patch.object(wt, "continue_on_dirty_enabled", return_value=True):
            with unittest.mock.patch.object(
                wt, "ensure_coding_worktree", return_value=coding
            ):
                cwd, isolated = peer_loop._resolve_coding_cwd(dirty, logs.append)
        self.assertEqual(cwd, coding)
        self.assertTrue(isolated)
        self.assertTrue(any("coding worktree" in m for m in logs))

    def test_should_stop_when_exhausted(self) -> None:
        import peer_loop

        ctx = "## Loop\n\nexhausted\n"
        live = auto.LiveState(True, "clean", True, "ok", 13.0, "ok")
        self.assertIsNotNone(peer_loop.should_stop_loop(ctx, live))

    def test_output_generated_on_new_turn(self) -> None:
        import peer_transcript as pt

        meta = pt.TranscriptMeta(
            path=Path("/tmp/x.jsonl"),
            line_count=100,
            mtime=1.0,
            turn_ended=True,
            turn_status="success",
        )
        state = {"processed_lines": 50, "transcript_path": "/tmp/x.jsonl"}
        self.assertTrue(pt.output_generated(meta, state))

    def test_output_not_generated_when_already_processed(self) -> None:
        import peer_transcript as pt

        meta = pt.TranscriptMeta(
            path=Path("/tmp/x.jsonl"),
            line_count=100,
            mtime=1.0,
            turn_ended=True,
            turn_status="success",
        )
        state = {"processed_lines": 100, "transcript_path": "/tmp/x.jsonl"}
        self.assertFalse(pt.output_generated(meta, state))

    def test_format_conversation_includes_roles(self) -> None:
        import peer_transcript as pt

        text = pt.format_conversation([("user", "hello"), ("assistant", "world")])
        self.assertIn("USER", text)
        self.assertIn("ASSISTANT", text)

    def test_entire_conversation_prefers_summary_file(self) -> None:
        import peer_transcript as pt

        with unittest.mock.patch.object(pt, "CONVERSATION_SUMMARY_PATH") as mock_path:
            mock_path.is_file.return_value = True
            mock_path.read_text.return_value = "# Summary\nDone."
            block = pt.entire_conversation_block(None)
        self.assertIn("Summary", block)
        self.assertIn("Done", block)

    def test_fresh_chat_when_prompt_large(self) -> None:
        import peer_cursor

        self.assertTrue(peer_cursor.should_open_fresh_chat(turn_count=10, prompt_chars=12_000))
        self.assertFalse(peer_cursor.should_open_fresh_chat(turn_count=10, prompt_chars=1000))

    def test_find_cursor_agent(self) -> None:
        import peer_terminal

        path = peer_terminal.find_cursor_agent()
        if path is not None:
            self.assertTrue(path.is_file())

    def test_resolve_mode_defaults_background(self) -> None:
        import argparse

        import peer_loop

        args = argparse.Namespace(
            terminal=False,
            paid_api=False,
            direct_ui=False,
            cursor_ui=False,
            clipboard_only=False,
            background=False,
            daemon=False,
            once=True,
            forever=False,
        )
        self.assertEqual(peer_loop._resolve_mode(args), "background")

    def test_resolve_mode_paid_api_opt_in(self) -> None:
        import argparse

        import peer_loop

        args = argparse.Namespace(
            terminal=False,
            paid_api=True,
            direct_ui=False,
            cursor_ui=False,
            clipboard_only=False,
            background=False,
            daemon=False,
            once=False,
            forever=False,
        )
        self.assertEqual(peer_loop._resolve_mode(args), "terminal")

    def test_resolve_mode_background_default(self) -> None:
        import argparse

        import peer_loop

        args = argparse.Namespace(
            terminal=False,
            paid_api=False,
            direct_ui=False,
            cursor_ui=False,
            clipboard_only=False,
            background=False,
            daemon=False,
            once=False,
            forever=False,
        )
        self.assertEqual(peer_loop._resolve_mode(args), "background")

    def test_resolve_mode_background_explicit(self) -> None:
        import argparse

        import peer_loop

        args = argparse.Namespace(
            terminal=True,
            paid_api=False,
            direct_ui=False,
            cursor_ui=False,
            clipboard_only=False,
            background=True,
            daemon=False,
            once=False,
            forever=False,
        )
        self.assertEqual(peer_loop._resolve_mode(args), "background")

    def test_resolve_mode_clipboard_explicit(self) -> None:
        import argparse

        import peer_loop

        args = argparse.Namespace(
            terminal=False,
            paid_api=False,
            direct_ui=False,
            cursor_ui=False,
            clipboard_only=True,
            background=False,
            daemon=False,
            once=False,
            forever=False,
        )
        self.assertEqual(peer_loop._resolve_mode(args), "clipboard")

    def test_resolve_mode_cursor_ui_alias(self) -> None:
        import argparse

        import peer_loop

        args = argparse.Namespace(
            terminal=False,
            paid_api=False,
            direct_ui=False,
            cursor_ui=True,
            clipboard_only=False,
            background=False,
            daemon=False,
            once=False,
            forever=False,
        )
        self.assertEqual(peer_loop._resolve_mode(args), "direct-ui")

    def test_plist_body_default_background(self) -> None:
        import peer_loop

        body = peer_loop.plist_body()
        self.assertIn("--background", body)
        self.assertNotIn("--clipboard-only", body)
        self.assertNotIn("CURSOR_MINIMIZED", body)
        self.assertNotIn("--direct-ui", body)
        self.assertNotIn("--paid-api", body)
        self.assertIn("/usr/sbin", body)

    def test_plist_body_background_explicit(self) -> None:
        import peer_loop

        body = peer_loop.plist_body(install_mode="background")
        self.assertIn("--background", body)
        self.assertNotIn("--clipboard-only", body)
        self.assertNotIn("--direct-ui", body)
        self.assertNotIn("--paid-api", body)
        self.assertNotIn("CURSOR_MINIMIZED", body)

    def test_plist_body_clipboard_opt_in(self) -> None:
        import peer_loop

        body = peer_loop.plist_body(install_mode="clipboard")
        self.assertIn("--clipboard-only", body)
        self.assertIn("--from-transcript", body)
        self.assertIn("CURSOR_MINIMIZED", body)
        self.assertNotIn("--direct-ui", body)
        self.assertNotIn("--paid-api", body)

    def test_plist_body_direct_ui_opt_in(self) -> None:
        import peer_loop

        body = peer_loop.plist_body(install_mode="direct-ui")
        self.assertIn("--direct-ui", body)
        self.assertIn("--from-transcript", body)
        self.assertNotIn("--clipboard-only", body)
        self.assertNotIn("CURSOR_MINIMIZED", body)

    def test_inject_text_to_cursor_uses_ax_not_clipboard(self) -> None:
        import peer_cursor

        with unittest.mock.patch.object(peer_cursor, "_inject_via_ax", return_value=(True, "injected")) as mock_ax:
            ok, msg = peer_cursor.inject_text_to_cursor(
                "hello peer", press_enter=True, cursor_ui=True
            )
        self.assertTrue(ok)
        self.assertIn("Return", msg)
        mock_ax.assert_called_once()
        self.assertEqual(mock_ax.call_args.kwargs["press_enter"], True)
        self.assertTrue(mock_ax.call_args.kwargs["cursor_ui"])

    def test_inject_text_to_cursor_refuses_without_cursor_ui(self) -> None:
        import peer_cursor

        ok, msg = peer_cursor.inject_text_to_cursor("hello peer", press_enter=True)
        self.assertFalse(ok)
        self.assertIn("cursor-ui", msg.lower())

    def test_keystroke_available_non_invasive(self) -> None:
        import peer_cursor

        with unittest.mock.patch.object(peer_cursor.subprocess, "run") as mock_run:
            mock_run.return_value = unittest.mock.Mock(returncode=0, stdout="true\n", stderr="")
            self.assertTrue(peer_cursor.keystroke_available())
            script = mock_run.call_args[0][0]
            self.assertIn("swift", script)
            self.assertNotIn("keystroke", " ".join(script))

    def test_dispatch_prompt_text_direct_skips_clipboard(self) -> None:
        import peer_cursor
        import peer_loop

        logs: list[str] = []
        with unittest.mock.patch.object(
            peer_cursor,
            "inject_text_to_cursor",
            return_value=(True, "injected into Cursor chat and pressed Return"),
        ) as mock_inject, unittest.mock.patch.object(
            auto,
            "copy_to_clipboard",
        ) as mock_clip:
            rc, _ = peer_loop.dispatch_prompt_text(
                "peer task",
                mode="direct-ui",
                clipboard_only=False,
                press_enter=True,
                log_fn=logs.append,
            )
        self.assertEqual(rc, 0)
        mock_inject.assert_called_once()
        mock_clip.assert_not_called()

    def test_inject_via_transient_paste_uses_cmd_v(self) -> None:
        import peer_cursor

        with tempfile.TemporaryDirectory(prefix="ram-peer-test-") as tmp:
            path = Path(tmp) / "prompt.txt"
            path.write_text("hello peer", encoding="utf-8")
            with unittest.mock.patch.object(peer_cursor, "_run_osascript") as mock_run:
                with unittest.mock.patch.object(peer_cursor, "_clipboard_bytes", return_value=b"saved"):
                    with unittest.mock.patch.object(peer_cursor, "_set_clipboard_bytes") as mock_set:
                        mock_run.return_value = unittest.mock.Mock(returncode=0, stdout="ok\n", stderr="")
                        ok, msg = peer_cursor._inject_via_ax(
                            path, app_name="Cursor", press_enter=True, cursor_ui=True
                        )
            self.assertTrue(ok)
            script = mock_run.call_args[0][0]
            self.assertIn('keystroke "v"', script)
            self.assertIn("keystroke return", script)
            self.assertEqual(mock_set.call_count, 2)  # paste + restore

    def test_run_cursor_agent_blocked_api_key_without_paid_api(self) -> None:
        """Legacy block path when force_free_desktop_auth is off."""
        import peer_terminal

        logs: list[str] = []
        with tempfile.TemporaryDirectory(prefix="peer-prompt-") as tmp:
            prompt_path = Path(tmp) / "next-peer-prompt.md"
            with unittest.mock.patch.object(peer_terminal, "PROMPT_PATH", prompt_path):
                with unittest.mock.patch.object(
                    peer_terminal, "force_free_desktop_auth", return_value=False
                ):
                    with unittest.mock.patch.object(peer_terminal, "api_key_configured", return_value=True):
                        with unittest.mock.patch.object(peer_terminal, "require_paid_api_opt_in", return_value=False):
                            with unittest.mock.patch("peer_remote.remote_enabled", return_value=False):
                                rc, auth_failed = peer_terminal.run_cursor_agent(
                                    "test prompt", log_fn=logs.append, paid_api=False
                                )
        self.assertEqual(rc, 1)
        self.assertFalse(auth_failed)
        self.assertTrue(any("blocked" in line for line in logs))

    def test_force_free_desktop_ignores_api_key(self) -> None:
        """OVERSEER_FORCE_FREE_DESKTOP_2026_09_05 — API key never bills; desktop only."""
        import peer_terminal

        logs: list[str] = []
        agent = Path("/tmp/fake-cursor-agent")
        with tempfile.TemporaryDirectory(prefix="peer-prompt-") as tmp:
            prompt_path = Path(tmp) / "next-peer-prompt.md"
            with unittest.mock.patch.object(peer_terminal, "PROMPT_PATH", prompt_path):
                with unittest.mock.patch.object(
                    peer_terminal, "force_free_desktop_auth", return_value=True
                ), unittest.mock.patch.object(
                    peer_terminal, "api_key_configured", return_value=True
                ), unittest.mock.patch.object(
                    peer_terminal, "desktop_auth_ready", return_value=(True, "desktop login")
                ), unittest.mock.patch.object(
                    peer_terminal, "find_cursor_agent", return_value=agent
                ), unittest.mock.patch.object(
                    peer_terminal.subprocess,
                    "run",
                    return_value=unittest.mock.Mock(returncode=0, stdout="ok", stderr=""),
                ), unittest.mock.patch("peer_remote.remote_enabled", return_value=False):
                    rc, auth_failed = peer_terminal.run_cursor_agent(
                        "test prompt", log_fn=logs.append, paid_api=True
                    )
        self.assertEqual(rc, 0)
        self.assertFalse(auth_failed)
        self.assertTrue(any("FORCE FREE" in line or "desktop login" in line for line in logs))

    def test_force_free_strips_api_key_from_env(self) -> None:
        """FORCE FREE must not leak CURSOR_API_KEY into cursor-agent subprocess env."""
        import peer_terminal

        with unittest.mock.patch.object(
            peer_terminal, "force_free_desktop_auth", return_value=True
        ), unittest.mock.patch.dict(os.environ, {"CURSOR_API_KEY": "sk-test-not-real"}, clear=False):
            env = peer_terminal.agent_subprocess_env()
        self.assertNotIn("CURSOR_API_KEY", env)

    def test_force_free_desktop_auth_ready_ignores_key_file(self) -> None:
        """desktop_auth_ready must not fail-closed on key file when FORCE FREE."""
        import peer_terminal

        peer_terminal._auth_ready_cache = None
        agent = Path("/tmp/fake-cursor-agent")
        with unittest.mock.patch.object(
            peer_terminal, "force_free_desktop_auth", return_value=True
        ), unittest.mock.patch.object(
            peer_terminal, "api_key_configured", return_value=True
        ), unittest.mock.patch.object(
            peer_terminal, "find_cursor_agent", return_value=agent
        ), unittest.mock.patch.object(
            peer_terminal.subprocess,
            "run",
            return_value=unittest.mock.Mock(
                returncode=0, stdout="Logged in as test", stderr=""
            ),
        ):
            ready, detail = peer_terminal.desktop_auth_ready()
        self.assertTrue(ready)
        self.assertIn("desktop", detail.lower())
        self.assertNotIn("CURSOR_API_KEY set", detail)

    def test_run_cursor_agent_allows_desktop_without_paid_api(self) -> None:
        import peer_terminal

        logs: list[str] = []
        agent = Path("/tmp/fake-cursor-agent")
        with tempfile.TemporaryDirectory(prefix="peer-prompt-") as tmp:
            prompt_path = Path(tmp) / "next-peer-prompt.md"
            with unittest.mock.patch.object(peer_terminal, "PROMPT_PATH", prompt_path):
                with unittest.mock.patch.object(peer_terminal, "api_key_configured", return_value=False), unittest.mock.patch.object(
                    peer_terminal, "desktop_auth_ready", return_value=(True, "desktop login")
                ), unittest.mock.patch.object(peer_terminal, "find_cursor_agent", return_value=agent), unittest.mock.patch.object(
                    peer_terminal.subprocess, "run", return_value=unittest.mock.Mock(returncode=0, stdout="ok", stderr="")
                ):
                    rc, auth_failed = peer_terminal.run_cursor_agent(
                        "test prompt", log_fn=logs.append, paid_api=False
                    )
        self.assertEqual(rc, 0)
        self.assertFalse(auth_failed)

    def test_cursor_agent_argv_refuses_api_key_flag(self) -> None:
        """OVERSEER_CURSOR_AGENT_ARGV_NO_API_KEY_2026_09_07 — never put secrets on argv."""
        import peer_terminal

        safe = peer_terminal.build_cursor_agent_cmd("/tmp/fake-agent", "do work")
        self.assertNotIn("--api-key", safe)
        self.assertTrue(all(not a.startswith("--api-key=") for a in safe))
        self.assertTrue(all(not a.startswith("CURSOR_API_KEY=") for a in safe))

        with self.assertRaises(ValueError) as ctx:
            peer_terminal.assert_cursor_agent_argv_safe(
                ["cursor-agent", "--api-key", "REDACTED_PLACEHOLDER", "worker", "start"]
            )
        self.assertIn("SECURITY", str(ctx.exception))
        self.assertIn("--api-key", str(ctx.exception))

        with self.assertRaises(ValueError):
            peer_terminal.assert_cursor_agent_argv_safe(
                ["cursor-agent", "--api-key=REDACTED_PLACEHOLDER", "-p", "x"]
            )
        with self.assertRaises(ValueError):
            peer_terminal.assert_cursor_agent_argv_safe(
                ["cursor-agent", "CURSOR_API_KEY=REDACTED_PLACEHOLDER", "-p"]
            )

    def test_run_cursor_agent_spawn_argv_has_no_api_key(self) -> None:
        """Spawned subprocess argv must not include --api-key (env only)."""
        import peer_terminal

        logs: list[str] = []
        agent = Path("/tmp/fake-cursor-agent")
        captured: list[list[str]] = []

        def _capture_run(cmd, **kwargs):  # noqa: ANN001
            captured.append(list(cmd))
            return unittest.mock.Mock(returncode=0, stdout="ok", stderr="")

        with tempfile.TemporaryDirectory(prefix="peer-prompt-") as tmp:
            prompt_path = Path(tmp) / "next-peer-prompt.md"
            with unittest.mock.patch.object(peer_terminal, "PROMPT_PATH", prompt_path):
                with unittest.mock.patch.object(
                    peer_terminal, "force_free_desktop_auth", return_value=True
                ), unittest.mock.patch.object(
                    peer_terminal, "api_key_configured", return_value=True
                ), unittest.mock.patch.object(
                    peer_terminal, "desktop_auth_ready", return_value=(True, "desktop login")
                ), unittest.mock.patch.object(
                    peer_terminal, "find_cursor_agent", return_value=agent
                ), unittest.mock.patch.object(
                    peer_terminal.subprocess, "run", side_effect=_capture_run
                ), unittest.mock.patch("peer_remote.remote_enabled", return_value=False), unittest.mock.patch(
                    "peer_remote.should_dispatch_remote", return_value=False
                ):
                    rc, _ = peer_terminal.run_cursor_agent(
                        "test prompt", log_fn=logs.append, paid_api=True
                    )
        self.assertEqual(rc, 0)
        self.assertTrue(captured)
        for argv in captured:
            self.assertNotIn("--api-key", argv)
            self.assertTrue(all(not a.startswith("--api-key=") for a in argv))
            self.assertTrue(all(not a.startswith("CURSOR_API_KEY=") for a in argv))
            peer_terminal.assert_cursor_agent_argv_safe(argv)

    def test_dgx_setup_does_not_scrape_api_key_from_ps(self) -> None:
        """Setup must not scrape --api-key from ps or pass KEY as ssh argv."""
        setup = Path(__file__).resolve().parents[1] / "scripts" / "dgx_setup.sh"
        body = setup.read_text(encoding="utf-8")
        self.assertIn("OVERSEER_CURSOR_AGENT_ARGV_NO_API_KEY_2026_09_07", body)
        self.assertNotIn("ps -ax", body)
        self.assertNotIn("--api-key[[:space:]]", body)
        self.assertNotIn('"$KEY"', body)
        self.assertIn("cursor-agent.env", body)

    def test_write_prompt_file_refuses_tiny_clobber_of_live_payload(self) -> None:
        """OVERSEER_PEER_PROMPT_CLOBBER_GUARD_2026_09_05 — unittest must not erase argv blob."""
        import peer_terminal

        with tempfile.TemporaryDirectory(prefix="peer-prompt-guard-") as tmp:
            hub = Path(tmp)
            live = hub / "next-peer-prompt.md"
            live.write_text("X" * (peer_terminal.ARGV_PROMPT_SOFT_MAX + 100))
            with unittest.mock.patch.object(peer_terminal, "PROMPT_PATH", live):
                out = peer_terminal.write_prompt_file("test prompt")
            self.assertEqual(out, live)
            self.assertEqual(live.stat().st_size, peer_terminal.ARGV_PROMPT_SOFT_MAX + 100)
            # Force still overwrites
            with unittest.mock.patch.object(peer_terminal, "PROMPT_PATH", live):
                with unittest.mock.patch.dict(os.environ, {"AUTOMATION_PEER_PROMPT_FORCE": "1"}):
                    peer_terminal.write_prompt_file("test prompt")
            self.assertEqual(live.read_text(), "test prompt")


    def test_plist_body_paid_api_opt_in(self) -> None:
        import peer_loop

        body = peer_loop.plist_body(install_mode="paid-api")
        self.assertIn("--paid-api", body)
        self.assertNotIn("--clipboard-only", body)

    def test_agent_subprocess_env_sets_home(self) -> None:
        import peer_terminal

        env = peer_terminal.agent_subprocess_env()
        self.assertIn("HOME", env)
        self.assertTrue(env["HOME"])

    def test_output_requires_assistant_after_dispatch(self) -> None:
        import peer_transcript as pt

        meta = pt.TranscriptMeta(
            path=Path("/tmp/x.jsonl"),
            line_count=100,
            mtime=1.0,
            turn_ended=True,
            turn_status="success",
        )
        state = {"processed_lines": 50, "transcript_path": "/tmp/x.jsonl", "last_dispatch_ts": 9999999999}
        with unittest.mock.patch.object(pt, "read_conversation", return_value=[("user", "waiting")]):
            self.assertFalse(pt.output_generated(meta, state))

    def test_poke_turn_signal_creates_file(self) -> None:
        import peer_transcript as pt

        with tempfile.TemporaryDirectory(prefix="ram-peer-signal-") as tmp:
            signal = Path(tmp) / "peer-turn.signal"
            with unittest.mock.patch.object(pt, "SIGNAL_PATH", signal):
                pt.poke_turn_signal()
                self.assertTrue(signal.is_file())

    def test_quick_measure_uses_cache_without_rerunning_tests(self) -> None:
        import project_automation as auto

        # Poison guard: only tests_ok=True validates as git-unchanged cache hit.
        cache = {
            "git_fingerprint": "abc:",
            "git_head": "abc",
            "tests_ok": True,
            "tests_detail": "tests: smoke ok",
            "tests_ts": __import__("time").time(),
        }
        with unittest.mock.patch.object(auto, "_git_fingerprint", return_value="abc:"), unittest.mock.patch.object(
            auto, "_run"
        ) as run_mock:
            ok, detail = auto._measure_tests(quick=True, cache=cache)
        self.assertTrue(ok)
        self.assertIn("cached", detail)
        run_mock.assert_not_called()

    def test_git_soft_dirty_head_only_past_hard_ttl(self) -> None:
        """GIT_SOFT_DIRTY_HEAD_ONLY_2026_09_08 — dirty + HEAD match skips porcelain past hard TTL."""
        import project_automation as auto
        import time as time_mod

        hard = auto._git_measure_cache_ttl_sec()
        cache = {
            "git_fingerprint": "deadbeef:z:abc",
            "git_detail": "git: 3 changed path(s) (3 modified, 0 untracked)",
            "git_clean": False,
            "git_head": "deadbeef",
            "git_witness": "deadbeef:1:2",
            "git_ts": time_mod.time() - hard - 1.0,
        }
        with unittest.mock.patch.object(
            auto, "_git_witness", return_value="deadbeef:9:9"
        ), unittest.mock.patch.object(
            auto, "_git_head_ref", return_value="deadbeef"
        ), unittest.mock.patch.object(
            auto, "_git_snapshot"
        ) as snap:
            hit = auto._git_cache_fresh(cache)
            self.assertIsNotNone(hit)
            assert hit is not None
            self.assertEqual(hit[0], "deadbeef:z:abc")
            self.assertFalse(hit[1])
            snap.assert_not_called()
            # Clean cache must NOT soft-reuse on index churn (would miss dirty).
            cache["git_clean"] = True
            self.assertIsNone(auto._git_cache_fresh(cache))
        self.assertIn(
            "GIT_SOFT_DIRTY_HEAD_ONLY_2026_09_08",
            (Path(__file__).resolve().parents[1] / "scripts" / "project_automation.py").read_text(
                encoding="utf-8"
            ),
        )

    def test_git_head_ref_reads_packed_refs(self) -> None:
        """GIT_HEAD_REF_PACKED_REFS_2026_09_08 — packed-only branch refs resolve without spawn."""
        import project_automation as auto
        import tempfile
        from pathlib import Path as P

        with tempfile.TemporaryDirectory() as tmp:
            root = P(tmp)
            common = root / "common.git"
            wt = root / "worktrees" / "peer-1"
            common.mkdir(parents=True)
            wt.mkdir(parents=True)
            (common / "packed-refs").write_text(
                "# pack-refs with: peeled fully-peeled sorted\n"
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa refs/heads/peer/10\n"
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb refs/heads/peer/1\n"
                "cccccccccccccccccccccccccccccccccccccccc refs/heads/peer/11\n",
                encoding="utf-8",
            )
            (wt / "commondir").write_text("../..\n", encoding="utf-8")
            # Relative ../.. from worktrees/peer-1 → root; point to common.git via abs path.
            (wt / "commondir").write_text(str(common) + "\n", encoding="utf-8")
            (wt / "HEAD").write_text("ref: refs/heads/peer/1\n", encoding="utf-8")
            # No loose refs/heads/peer/1 — packed only.
            self.assertEqual(
                auto._git_packed_ref_oid(common, "refs/heads/peer/1"),
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            )
            self.assertIsNone(auto._git_packed_ref_oid(common, "refs/heads/peer/99"))
            with unittest.mock.patch.object(auto, "_resolve_git_dir", return_value=wt):
                self.assertEqual(
                    auto._git_head_ref(),
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                )
        self.assertIn(
            "GIT_HEAD_REF_PACKED_REFS_2026_09_08",
            (Path(__file__).resolve().parents[1] / "scripts" / "project_automation.py").read_text(
                encoding="utf-8"
            ),
        )

    def test_quick_measure_runs_self_check_not_full_suite(self) -> None:
        import project_automation as auto

        cache: dict = {}
        proc = unittest.mock.Mock(returncode=0, stdout="", stderr="")
        with unittest.mock.patch.object(auto, "_quick_cache_valid", return_value=False), unittest.mock.patch.object(
            auto, "_fail_cache_fresh", return_value=False
        ), unittest.mock.patch.object(
            auto, "_git_snapshot", return_value=("abc:", True, "git: clean working tree")
        ), unittest.mock.patch.object(
            auto, "_try_acquire_test_measure_lock", return_value=True
        ), unittest.mock.patch.object(auto, "_release_test_measure_lock"), unittest.mock.patch.object(
            auto, "_run", return_value=proc
        ) as run_mock, unittest.mock.patch.object(
            auto, "_git_head", return_value="abc"
        ), unittest.mock.patch.object(
            auto, "_git_fingerprint", return_value="abc:"
        ):
            ok, detail = auto._measure_tests(quick=True, cache=cache)
        self.assertTrue(ok)
        self.assertIn("smoke", detail)
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.args[0], auto.quick_test_command())

    def test_measure_tests_timeout_returns_stale_cache(self) -> None:
        import project_automation as auto

        cache = {
            "tests_ok": True,
            "tests_detail": "tests: self-check ok",
            "tests_ts": __import__("time").time(),
        }
        with unittest.mock.patch.object(auto, "_quick_cache_valid", return_value=False), unittest.mock.patch.object(
            auto, "_try_acquire_test_measure_lock", return_value=True
        ), unittest.mock.patch.object(auto, "_release_test_measure_lock"), unittest.mock.patch.object(
            auto, "_run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)
        ):
            ok, detail = auto._measure_tests(quick=True, cache=cache)
        self.assertTrue(ok)
        self.assertIn("stale cache", detail)

    def test_quick_cache_invalidates_on_git_change(self) -> None:
        import project_automation as auto

        fp_a = "abc123:"
        fp_b = "def456:"
        cache = {
            "git_fingerprint": fp_a,
            "git_head": "abc123",
            "tests_ok": True,
            "tests_detail": "tests: ok",
            "tests_ts": __import__("time").time(),
        }
        with unittest.mock.patch.object(auto, "_git_fingerprint", return_value=fp_a), unittest.mock.patch.object(
            auto, "_git_head", return_value="abc123"
        ):
            self.assertTrue(auto._quick_cache_valid(cache))
        with unittest.mock.patch.object(auto, "_git_fingerprint", return_value=fp_b), unittest.mock.patch.object(
            auto, "_git_head", return_value="def456"
        ):
            self.assertFalse(auto._quick_cache_valid(cache))

    def test_quick_cache_ttl_same_head_survives_porcelain_churn(self) -> None:
        import project_automation as auto
        import time as time_mod

        cache = {
            "git_fingerprint": "abc:old",
            "git_head": "abc",
            "tests_ok": True,
            "tests_detail": "tests: ok",
            "tests_ts": time_mod.time(),
        }
        with unittest.mock.patch.object(auto, "_git_fingerprint", return_value="abc:new"), unittest.mock.patch.object(
            auto, "_git_head", return_value="abc"
        ):
            self.assertTrue(auto._quick_cache_valid(cache))
        cache["tests_ts"] = time_mod.time() - 9999
        with unittest.mock.patch.object(auto, "_git_fingerprint", return_value="abc:new"), unittest.mock.patch.object(
            auto, "_git_head", return_value="abc"
        ):
            self.assertFalse(auto._quick_cache_valid(cache))

    def test_live_from_quick_cache_skips_unusable_tests_fail(self) -> None:
        """tests_ok=False never validates — poison guard in _quick_cache_valid + live miss."""
        import project_automation as auto
        import time as time_mod

        now = time_mod.time()
        fail_cache = {
            "git_fingerprint": "abc:",
            "git_head": "abc",
            "git_clean": True,
            "git_detail": "git: clean working tree",
            "git_ts": now,
            "tests_ok": False,
            "tests_detail": "tests: FAIL — AssertionError",
            "tests_ts": now,
        }
        with unittest.mock.patch.object(auto, "_git_fingerprint", return_value="abc:"):
            self.assertFalse(auto._quick_cache_valid(fail_cache))
            self.assertIsNone(auto._live_from_quick_cache(fail_cache))
            # Poison guard: tests_ok=False never usable (smoke label alone insufficient)
            smoke_fail = {**fail_cache, "tests_detail": "tests: smoke ok"}
            self.assertFalse(auto._quick_test_cache_usable(smoke_fail))
            self.assertFalse(auto._quick_cache_valid(smoke_fail))
            self.assertIsNone(auto._live_from_quick_cache(smoke_fail))
            ok_cache = {
                **fail_cache,
                "tests_ok": True,
                "tests_detail": "tests: smoke ok",
            }
            self.assertTrue(auto._quick_cache_valid(ok_cache))
            live = auto._live_from_quick_cache(ok_cache)
        self.assertIsNotNone(live)
        assert live is not None
        self.assertTrue(live.tests_ok)
        self.assertIn("cached, git unchanged", live.tests_detail)

    def test_peer_event_timeout_reason(self) -> None:
        import peer_transcript as pt

        watcher = pt.PeerEventWatcher()
        watcher._available = True
        watcher._kq = unittest.mock.Mock()
        watcher._kq.control.return_value = []
        with unittest.mock.patch.object(watcher, "refresh_transcript_watch"), unittest.mock.patch.object(
            pt, "find_latest_transcript", return_value=None
        ), unittest.mock.patch.object(pt, "SIGNAL_PATH", unittest.mock.Mock(is_file=lambda: False)):
            event = watcher.wait(timeout=1.0)
        self.assertEqual(event.reason, "timeout")
        watcher.close()

    def test_peer_event_stale_turn_ended_is_timeout(self) -> None:
        """Stale turn_ended must not masquerade as a fresh transcript wake."""
        import peer_transcript as pt

        with tempfile.TemporaryDirectory(prefix="peer-stale-turn-") as tmp:
            path = Path(tmp) / "chat.jsonl"
            path.write_text(
                '{"type":"turn_ended","status":"success"}\n',
                encoding="utf-8",
            )
            meta = pt.read_transcript_meta(path)
            watcher = pt.PeerEventWatcher()
            watcher._available = True
            watcher._kq = unittest.mock.Mock()
            watcher._kq.control.return_value = []
            watcher._last_transcript_event_mtime = path.stat().st_mtime
            with unittest.mock.patch.object(watcher, "refresh_transcript_watch"), unittest.mock.patch.object(
                pt, "find_latest_transcript", return_value=path
            ), unittest.mock.patch.object(pt, "read_transcript_meta", return_value=meta), unittest.mock.patch.object(
                pt, "SIGNAL_PATH", unittest.mock.Mock(is_file=lambda: False)
            ):
                event = watcher.wait(timeout=0.1)
            self.assertEqual(event.reason, "timeout")
            watcher.close()

    def test_peer_event_drain_clears_pending(self) -> None:
        import peer_transcript as pt

        watcher = pt.PeerEventWatcher()
        watcher._available = True
        watcher._kq = unittest.mock.Mock()
        watcher._kq.control.side_effect = [[object(), object()], []]
        with unittest.mock.patch.object(watcher, "refresh_transcript_watch"), unittest.mock.patch.object(
            watcher, "_seed_transcript_baseline"
        ):
            n = watcher.drain()
        self.assertEqual(n, 2)
        watcher.close()

    def test_local_verify_cooldown(self) -> None:
        import peer_transcript as pt

        state: dict = {}
        self.assertEqual(pt.local_verify_cooldown_remaining(state), 0.0)
        with unittest.mock.patch.object(pt, "save_state"):
            pt.mark_local_verify(state)
        self.assertGreater(pt.local_verify_cooldown_remaining(state), 0.0)
        state["last_local_verify_ts"] = 0.0
        self.assertEqual(pt.local_verify_cooldown_remaining(state), 0.0)

    def test_fallback_poll_default_is_long(self) -> None:
        import peer_loop
        import peer_transcript as pt

        self.assertGreaterEqual(pt.FALLBACK_POLL_SEC, 300.0)
        self.assertEqual(peer_loop.DEFAULT_FALLBACK_POLL_SEC, pt.FALLBACK_POLL_SEC)

    def test_continuous_wake_timeout_when_work(self) -> None:
        import peer_loop

        with unittest.mock.patch.object(peer_loop, "effective_continuous_wake_sec", return_value=90.0):
            self.assertEqual(
                peer_loop.continuous_wake_timeout(has_work=True, noop_remaining=0),
                90.0,
            )
        self.assertEqual(
            peer_loop.continuous_wake_timeout(has_work=True, noop_remaining=10),
            10.0,
        )
        self.assertIsNone(peer_loop.continuous_wake_timeout(has_work=False, noop_remaining=0))

    def test_post_wait_find_latest_reuses_wait_cache(self) -> None:
        """Event post-wait must not force=True — wait() already force-scanned."""
        import peer_loop

        self.assertFalse(
            peer_loop.POST_WAIT_FIND_LATEST_FORCE,
            "post-wait force=True double-pays find_latest after wait kevent scan",
        )

    def test_should_skip_post_wait_transcript_rescan(self) -> None:
        import peer_loop

        self.assertTrue(
            peer_loop.should_skip_post_wait_transcript_rescan(
                timed_out=True, watcher_available=True
            )
        )
        self.assertFalse(
            peer_loop.should_skip_post_wait_transcript_rescan(
                timed_out=True, watcher_available=False
            )
        )
        self.assertFalse(
            peer_loop.should_skip_post_wait_transcript_rescan(
                timed_out=False, watcher_available=True
            )
        )
        # Linux: no kqueue — fallback sleep must reuse loop-head (not rescan).
        self.assertTrue(
            peer_loop.should_skip_post_wait_transcript_rescan(
                timed_out=False,
                watcher_available=False,
                event_reason="fallback",
            )
        )
        self.assertFalse(
            peer_loop.should_skip_post_wait_transcript_rescan(
                timed_out=False,
                watcher_available=False,
                event_reason="transcript",
            )
        )
        self.assertTrue(
            peer_loop.should_skip_post_wait_live_refresh(
                timed_out=True, watcher_available=True
            )
        )
        self.assertFalse(
            peer_loop.should_skip_post_wait_live_refresh(
                timed_out=False, watcher_available=True
            )
        )
        self.assertTrue(
            peer_loop.should_skip_post_wait_live_refresh(
                timed_out=False,
                watcher_available=False,
                event_reason="fallback",
            )
        )

    def test_shallow_wake_floor_ignores_hyper_overlay(self) -> None:
        import peer_loop

        cfg = {
            "continuous_wake_sec": 3,
            "continuous_agent_min_interval_sec": 1,
            "continuous_wake_shallow_floor_sec": 30,
            "continuous_wake_shallow_max_items": 8,
        }
        with unittest.mock.patch.object(peer_loop, "_live_wake_cfg", return_value=cfg):
            self.assertEqual(peer_loop._shallow_wake_floor(cfg), 30.0)
            self.assertEqual(peer_loop.effective_continuous_wake_sec(open_queue_count=4), 30.0)
            self.assertGreaterEqual(peer_loop.effective_continuous_wake_sec(open_queue_count=20), 15.0)
            self.assertNotEqual(peer_loop.effective_continuous_wake_sec(open_queue_count=20), 3)

    def test_shallow_wake_floor_keeps_base_ninety(self) -> None:
        import peer_loop

        cfg = {
            "continuous_wake_sec": 90,
            "continuous_wake_shallow_floor_sec": 30,
            "continuous_wake_shallow_max_items": 8,
        }
        with unittest.mock.patch.object(peer_loop, "_live_wake_cfg", return_value=cfg):
            self.assertEqual(peer_loop.effective_continuous_wake_sec(open_queue_count=4), 90.0)

    def test_dgx_speed_overlay_wake_is_not_hyper_poll(self) -> None:
        """dgx_install_services.sh merges this overlay onto local.json — must not restore wake≤5."""
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "scripts" / "dgx_speed.local.json"
        self.assertTrue(path.is_file(), msg=str(path))
        data = json.loads(path.read_text())
        wake = float(data.get("continuous_wake_sec") or 0)
        self.assertGreater(wake, 5.0, msg="speed overlay hyper-polls probe_efficiency")
        self.assertGreaterEqual(float(data.get("continuous_wake_shallow_floor_sec") or 0), 15.0)
        self.assertGreaterEqual(float(data.get("continuous_agent_min_interval_sec") or 0), 15.0)
        improve_wake = float(data.get("improve_continuous_wake_sec") or 0)
        self.assertGreater(improve_wake, 5.0, msg="speed overlay improve loop hyper-polls")
        self.assertGreaterEqual(float(data.get("improve_continuous_min_cycle_sec") or 0), 10.0)

    def test_dgx_speed_overlay_peer_caps_at_ceiling(self) -> None:
        """Overlay defaults must stay ≤96 so install cannot re-explode floor/max/grid unboundedly."""
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "scripts" / "dgx_speed.local.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ("max_parallel_peers", "parallel_peer_floor", "max_parallel_agent_procs"):
            self.assertLessEqual(int(data[key]), 96, msg=key)
        grid = data.get("factory_grid") or {}
        for key in ("hub_agents", "external_agents", "global_agents"):
            self.assertLessEqual(int(grid[key]), 96, msg=key)

    def test_root_dgx_speed_peer_caps_match_scripts_overlay(self) -> None:
        """Repo-root dgx_speed.local.json must not re-landmine floor/max/grid unboundedly."""
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        root_path = root / "dgx_speed.local.json"
        scripts_path = root / "scripts" / "dgx_speed.local.json"
        self.assertTrue(root_path.is_file(), msg=str(root_path))
        data = json.loads(root_path.read_text(encoding="utf-8"))
        scripts = json.loads(scripts_path.read_text(encoding="utf-8"))
        for key in (
            "max_parallel_peers",
            "parallel_peer_floor",
            "max_parallel_agent_procs",
            "improve_enqueue_cap",
        ):
            self.assertLessEqual(int(data[key]), 96, msg=key)
            self.assertEqual(int(data[key]), int(scripts[key]), msg=key)
        self.assertEqual(
            int(data["dgx_unittest_cap"]), int(scripts["dgx_unittest_cap"])
        )
        grid = data.get("factory_grid") or {}
        scripts_grid = scripts.get("factory_grid") or {}
        for key in ("hub_agents", "global_agents"):
            self.assertLessEqual(int(grid[key]), 96, msg=key)
            self.assertEqual(int(grid[key]), int(scripts_grid[key]), msg=key)

    def test_dgx_install_merges_overlay_instead_of_cp_clobber(self) -> None:
        """Install must merge+cap, not ``cp`` the overlay over local.json."""
        import json

        import automation_config as ac

        installer = Path(__file__).resolve().parents[1] / "scripts" / "dgx_install_services.sh"
        text = installer.read_text(encoding="utf-8")
        self.assertNotIn("cp \"$AUTOMATION/scripts/dgx_speed.local.json\"", text)
        self.assertIn("--apply-dgx-speed-overlay", text)
        overlay = {
            "max_parallel_peers": 48,
            "parallel_peer_floor": 48,
            "max_parallel_agent_procs": 48,
            "factory_grid": {"hub_agents": 32, "external_agents": 16, "global_agents": 48},
        }
        existing = {
            "staff_all_niches": True,
            "max_parallel_peers": 8,
            "factory_grid": {"enabled": False, "hub_agents": 8},
        }
        with tempfile.TemporaryDirectory(prefix="dgx-overlay-") as tmp:
            root = Path(tmp)
            overlay_path = root / "scripts" / "dgx_speed.local.json"
            local_path = root / "automation.config.local.json"
            overlay_path.parent.mkdir(parents=True)
            overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
            local_path.write_text(json.dumps(existing), encoding="utf-8")
            merged = ac.apply_dgx_speed_overlay(
                root=root, overlay_path=overlay_path, local_path=local_path
            )
        self.assertTrue(merged["staff_all_niches"])
        self.assertEqual(merged["max_parallel_peers"], 48)
        self.assertEqual(merged["parallel_peer_floor"], 48)
        self.assertEqual(merged["max_parallel_agent_procs"], 48)
        self.assertEqual(merged["factory_grid"]["hub_agents"], 32)
        self.assertEqual(merged["factory_grid"]["global_agents"], 48)
        self.assertFalse(merged["factory_grid"]["enabled"])

    def test_dgx_install_caps_fresh_local_from_stale_overlay(self) -> None:
        import json

        import automation_config as ac

        overlay = {
            "max_parallel_peers": 48,
            "factory_grid": {"hub_agents": 48, "global_agents": 48},
        }
        with tempfile.TemporaryDirectory(prefix="dgx-overlay-fresh-") as tmp:
            root = Path(tmp)
            overlay_path = root / "scripts" / "dgx_speed.local.json"
            local_path = root / "automation.config.local.json"
            overlay_path.parent.mkdir(parents=True)
            overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
            merged = ac.apply_dgx_speed_overlay(
                root=root, overlay_path=overlay_path, local_path=local_path
            )
            self.assertEqual(merged["max_parallel_peers"], 48)
            self.assertEqual(merged["factory_grid"]["hub_agents"], 48)
            self.assertTrue(local_path.is_file())

    def test_peer_event_watcher_linux_mtime_mode(self) -> None:
        """OVERSEER_LINUX_MTIME_EVENT_WATCH_2026_09_08 — Linux setup uses mtime poll (not unavailable)."""
        import peer_transcript as pt

        watcher = pt.PeerEventWatcher()
        with unittest.mock.patch.object(pt.sys, "platform", "linux"):
            self.assertTrue(watcher.setup())
            self.assertTrue(watcher.available)
            self.assertTrue(watcher._mtime_mode)
            self.assertIsNone(watcher._kq)
        watcher.close()

    def test_peer_event_watcher_mtime_signal_wake(self) -> None:
        """OVERSEER_LINUX_MTIME_EVENT_WATCH_2026_09_08 — mtime wait wakes on peer-turn.signal."""
        import peer_transcript as pt

        with tempfile.TemporaryDirectory(prefix="mtime-signal-") as tmp:
            sig = Path(tmp) / "peer-turn.signal"
            sig.write_text("0\n", encoding="utf-8")
            watcher = pt.PeerEventWatcher()
            with unittest.mock.patch.object(pt.sys, "platform", "linux"), unittest.mock.patch.object(
                pt, "SIGNAL_PATH", sig
            ), unittest.mock.patch.object(pt, "find_latest_transcript", return_value=None):
                self.assertTrue(watcher.setup())
                self.assertTrue(watcher._mtime_mode)
                baseline = watcher._signal_mtime
                sig.write_text("1\n", encoding="utf-8")
                # Bump mtime past baseline even on coarse filesystems.
                os.utime(sig, (baseline + 2.0, baseline + 2.0))
                event = watcher.wait(timeout=0.5)
            self.assertEqual(event.reason, "signal")
            watcher.close()

    def test_peer_event_watcher_mtime_log_extra_baseline(self) -> None:
        """LINUX_MTIME_LOG_EXTRA_REASON_BASELINE_2026_09_08 — log extras wake once as log, then timeout."""
        import peer_transcript as pt

        with tempfile.TemporaryDirectory(prefix="mtime-log-") as tmp:
            sig = Path(tmp) / "peer-turn.signal"
            log = Path(tmp) / "improve-loop.log"
            sig.write_text("0\n", encoding="utf-8")
            log.write_text("seed\n", encoding="utf-8")
            watcher = pt.PeerEventWatcher()
            with unittest.mock.patch.object(pt.sys, "platform", "linux"), unittest.mock.patch.object(
                pt, "SIGNAL_PATH", sig
            ), unittest.mock.patch.object(pt, "find_latest_transcript", return_value=None):
                self.assertTrue(watcher.setup())
                self.assertTrue(watcher.watch_path(log))
                baseline = float(watcher._extra_mtimes.get(str(log.resolve()), 0.0))
                log.write_text("seed\nappend\n", encoding="utf-8")
                os.utime(log, (baseline + 2.0, baseline + 2.0))
                first = watcher.wait(timeout=0.5)
                second = watcher.wait(timeout=0.2)
            self.assertEqual(first.reason, "log")
            self.assertEqual(second.reason, "timeout")
            self.assertNotEqual(first.reason, "signal")
            src = (SCRIPTS / "peer_transcript.py").read_text(encoding="utf-8")
            self.assertIn("LINUX_MTIME_LOG_EXTRA_REASON_BASELINE_2026_09_08", src)
            watcher.close()

    def test_metric_snapshot_live_git_head_needle(self) -> None:
        """OVERSEER_METRIC_SNAP_LIVE_GIT_HEAD_2026_09_08 — verify-gate pin for empty last_cycle HEAD."""
        import peer_oversight_events as events

        src = (SCRIPTS / "peer_oversight_events.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_METRIC_SNAP_LIVE_GIT_HEAD_2026_09_08", src)
        ctx = {
            "queue_count": 0,
            "queue_source": "empty",
            "phase": "WORKING",
            "last_cycle": {"noop": False, "verify_ok": True, "git_head": ""},
            "kit": {"factory_pct": 100, "asi_pct": 100},
            "ram": {},
        }
        with unittest.mock.patch.object(events, "_active_queue_metrics", return_value=("", 0)):
            with unittest.mock.patch("peer_transcript.load_state", return_value={}):
                with unittest.mock.patch(
                    "peer_transcript.git_head_oneline",
                    return_value="67489f1 peer cycle: verify ok",
                ):
                    snap = events.metric_snapshot(ctx, {"open": 0})
        self.assertTrue(str(snap["git_head"]).startswith("67489f1"))
        self.assertEqual(events._comparable_git_head(snap["git_head"]), "67489f1")

    def test_read_transcript_meta_detects_turn_ended(self) -> None:
        import peer_transcript as pt

        with tempfile.TemporaryDirectory(prefix="ram-peer-transcript-") as tmp:
            path = Path(tmp) / "chat.jsonl"
            path.write_text(
                '{"role":"user","message":{"content":[{"type":"text","text":"hi"}]}}\n'
                '{"type":"turn_ended","status":"success"}\n',
                encoding="utf-8",
            )
            meta = pt.read_transcript_meta(path)
            self.assertIsNotNone(meta)
            assert meta is not None
            self.assertTrue(meta.turn_ended)
            self.assertEqual(meta.turn_status, "success")

    def test_maybe_dispatch_background_local_marks_processed(self) -> None:
        """Local-only background must mark the turn so it cannot re-fire forever."""
        import peer_loop
        import peer_transcript as pt
        import project_automation as auto

        with tempfile.TemporaryDirectory(prefix="ram-peer-mark-") as tmp:
            path = Path(tmp) / "chat.jsonl"
            path.write_text(
                '{"role":"assistant","message":{"content":[{"type":"text","text":"done"}]}}\n'
                '{"type":"turn_ended","status":"success"}\n',
                encoding="utf-8",
            )
            meta = pt.read_transcript_meta(path)
            assert meta is not None
            live = auto.LiveState(
                git_clean=True,
                git_detail="clean",
                tests_ok=True,
                tests_detail="ok",
                import_rss_mb=10.0,
                footprint_detail="ok",
            )
            state: dict = {"processed_lines": 0}
            with unittest.mock.patch.object(pt, "has_new_assistant_since_dispatch", return_value=True), \
                 unittest.mock.patch.object(pt, "STATE_PATH", Path(tmp) / "state.json"), \
                 unittest.mock.patch.object(pt, "save_state", lambda s: None):
                new_state, auth_failed = peer_loop._maybe_dispatch_on_turn(
                    quick=True,
                    mode="background",
                    clipboard_only=False,
                    press_enter=False,
                    log_fn=lambda _m: None,
                    state=state,
                    paid_api=False,
                    use_agent=False,
                    meta=meta,
                    path=path,
                    live=live,
                    watcher=None,
                    fallback_poll_sec=300.0,
                    done_timeout_sec=60.0,
                )
            self.assertFalse(auth_failed)
            self.assertEqual(new_state.get("processed_lines"), meta.line_count)

    def test_asi_close_tokens_open_ignores_docs_and_factory_phrase(self) -> None:
        import peer_loop

        md = (
            "- [ ] **[efficiency-research] Skip close-asi rubric when no ASI-phase open** — "
            "Active **0** `[asi phase:` / maximize-parallel; WQ token scan\n"
            "- [ ] **[factory:verify_memory] Harden active capability** — "
            "maximize parallel Task peers per cycle\n"
            "- [x] **[asi phase:grounded_loop] done**\n"
        )
        self.assertFalse(peer_loop._asi_close_tokens_open(md))
        self.assertTrue(
            peer_loop._asi_close_tokens_open(
                "- [ ] **[asi phase:grounded_loop] Harden grounded_loop**\n"
            )
        )
        self.assertTrue(
            peer_loop._asi_close_tokens_open("- [ ] **[maximize-parallel] kit**\n")
        )

    def test_close_asi_skips_rubric_when_no_phase_token(self) -> None:
        import peer_loop

        wq = (
            "- [ ] **[efficiency-research] Skip close-asi** — Active **0** "
            "`[asi phase:` / maximize-parallel\n"
            "- [ ] **[factory:verify_memory] Harden** — maximize parallel Task peers\n"
        )
        with (
            unittest.mock.patch("automation_improve.gather_signals") as gs,
            unittest.mock.patch("asi_rubric.compute_asi_rubric") as rub,
            unittest.mock.patch.object(peer_loop.auto, "check_off_queue_lines") as cof,
        ):
            out = peer_loop._close_completed_asi_phase_plans(
                lambda _m: None, queue_md=wq
            )
        self.assertFalse(out)
        gs.assert_not_called()
        rub.assert_not_called()
        cof.assert_not_called()

    def test_close_asi_runs_rubric_when_phase_token_open(self) -> None:
        import peer_loop

        fake = unittest.mock.Mock(completed_phase_ids=(), phases=[])
        with (
            unittest.mock.patch("automation_improve.gather_signals", return_value="sig") as gs,
            unittest.mock.patch("asi_rubric.compute_asi_rubric", return_value=fake) as rub,
            unittest.mock.patch.object(
                peer_loop.auto, "check_off_queue_lines", return_value=[]
            ) as cof,
        ):
            out = peer_loop._close_completed_asi_phase_plans(
                lambda _m: None,
                queue_md="- [ ] **[asi phase:grounded_loop] Harden grounded_loop**\n",
            )
        self.assertFalse(out)
        gs.assert_called_once()
        rub.assert_called_once()
        cof.assert_called_once()


class PeerWatchTests(unittest.TestCase):
    def test_classify_working_when_agent_alive(self) -> None:
        import peer_watch as pw

        agent = pw.AgentProc(pid=1, etime="0:05", state="S")
        phase, detail = pw.classify_phase(
            daemon_ok=True,
            agent=agent,
            last_log="event-driven: kqueue",
            queue_count=0,
            git_clean=True,
        )
        self.assertEqual(phase, "WORKING")
        self.assertIn("pid 1", detail)

    def test_classify_idle_on_empty_queue(self) -> None:
        import peer_watch as pw

        phase, _ = pw.classify_phase(
            daemon_ok=True,
            agent=None,
            last_log="idle: queue empty — waiting",
            queue_count=0,
            git_clean=True,
        )
        self.assertEqual(phase, "IDLE")

    def test_classify_stopped(self) -> None:
        import peer_watch as pw

        phase, _ = pw.classify_phase(
            daemon_ok=False,
            agent=None,
            last_log="",
            queue_count=1,
            git_clean=True,
        )
        self.assertEqual(phase, "STOPPED")

    def test_porcelain_path(self) -> None:
        import peer_watch as pw

        self.assertEqual(pw._porcelain_path(" M battery/policy.py"), "battery/policy.py")
        self.assertEqual(pw._porcelain_path("?? ram_wire_budget.py"), "ram_wire_budget.py")

    def test_collect_snapshot_lazy_imports(self) -> None:
        # OVERSEER_WATCH_LAZY_COLLECT_2026_09_07 — bare peer_terminal/transcript
        # names after COMPRESSION lazy-import strip must not NameError.
        import peer_watch as pw

        snap = pw.collect_snapshot()
        self.assertIsInstance(snap.phase, str)
        self.assertTrue(snap.phase)



class IntelligenceCracksTests(unittest.TestCase):
    def test_scope_hints_from_backticks(self) -> None:
        scopes = po._scope_hints_from_item("Foo (`src/a.py`) and (`src/b.py`)")
        self.assertIn("src/a.py", scopes)
        self.assertIn("src/b.py", scopes)

    def test_merge_keeps_per_item_guidance(self) -> None:
        raw = [
            po.PeerTask("reclaim", "generalPurpose", "yellow", "A", ["a.py"], "do A"),
            po.PeerTask("reclaim", "generalPurpose", "yellow", "B", ["b.py"], "do B"),
        ]
        merged = po._merge_implementation_tasks(raw)
        self.assertEqual(len(merged), 1)
        self.assertIn("Per-item guidance", merged[0].prompt)
        self.assertIn("do A", merged[0].prompt)
        self.assertIn("do B", merged[0].prompt)
        self.assertEqual(set(merged[0].scope), {"a.py", "b.py"})

    def test_format_conversation_keeps_newest(self) -> None:
        import peer_transcript as pt

        turns = [("user", "OLD"), ("assistant", "old-a"), ("user", "NEW DECISION"), ("assistant", "new-a")]
        text = pt.format_conversation(turns, max_chars=45)
        self.assertIn("NEW DECISION", text)
        self.assertNotIn("\nOLD\n", "\n" + text + "\n")

    def test_queue_fingerprint_stable(self) -> None:
        import peer_transcript as pt

        a = pt.queue_fingerprint(["Zed", "Alpha"])
        b = pt.queue_fingerprint(["Alpha", "Zed"])
        self.assertEqual(a, b)

    def test_queue_fp_lite_dry_project_automation(self) -> None:
        """QUEUE_FP_LITE_DRY_PROJECT_AUTOMATION — auto SoT matches tx + improve + peer_loop."""
        import peer_loop
        import peer_transcript as pt
        import automation_improve as improve

        items = ["Zed", "Alpha"]
        auto_fp = auto.queue_fingerprint_items(items)
        self.assertEqual(auto_fp, pt.queue_fingerprint(items))
        self.assertEqual(auto_fp, improve.queue_fingerprint_items(items))
        lite_fp, lite_items = auto.current_queue_fingerprint_lite()
        self.assertEqual(lite_fp, peer_loop._open_queue_content_fingerprint())
        self.assertEqual(lite_fp, improve.current_queue_fingerprint_lite()[0])
        self.assertIsInstance(lite_items, list)
        self.assertIn(
            "QUEUE_FP_LITE_DRY_PROJECT_AUTOMATION_2026_09_08",
            auto.queue_fingerprint_items.__doc__ or "",
        )

    def test_record_cycle_marks_noop(self) -> None:
        import peer_transcript as pt

        with tempfile.TemporaryDirectory(prefix="ram-cycle-") as tmp:
            state_path = Path(tmp) / "state.json"
            with unittest.mock.patch.object(pt, "STATE_PATH", state_path):
                state: dict = {}
                pt.record_cycle_outcome(
                    state,
                    rc=0,
                    verify_ok=True,
                    queue_fp_before="abc",
                    queue_fp_after="abc",
                    note="unit-test",
                )
                self.assertTrue(state["last_cycle"]["noop"])
                self.assertIn("Last cycle", pt.format_last_cycle_block(state))

    def test_local_only_cycle_does_not_arm_noop(self) -> None:
        import peer_transcript as pt

        with tempfile.TemporaryDirectory(prefix="ram-cycle-") as tmp:
            state_path = Path(tmp) / "state.json"
            with unittest.mock.patch.object(pt, "STATE_PATH", state_path):
                state: dict = {}
                pt.record_cycle_outcome(
                    state,
                    rc=0,
                    verify_ok=True,
                    queue_fp_before="abc",
                    queue_fp_after="abc",
                    note="local tick",
                    local_only=True,
                )
                self.assertFalse(state["last_cycle"]["noop"])
                self.assertEqual(pt.noop_backoff_remaining(state, backoff_sec=120.0), 0.0)

    def test_run_local_continuous_skips_after_verify_on_cooldown(self) -> None:
        """Cooldown carry of prior verify_ok must not auto-commit unverified WIP."""
        import peer_loop
        import peer_transcript as pt

        state: dict = {
            "last_cycle": {"verify_ok": True, "ts": 1.0},
            "last_local_verify_ts": __import__("time").time(),
        }
        after_calls: list[str] = []
        with unittest.mock.patch.object(pt, "current_queue_fingerprint", return_value=("fpA", [])):
            with unittest.mock.patch.object(pt, "noop_backoff_remaining", return_value=0.0):
                with unittest.mock.patch.object(pt, "local_verify_cooldown_remaining", return_value=90.0):
                    with unittest.mock.patch.object(peer_loop, "_emit_worktree_inventory"):
                        with unittest.mock.patch.object(peer_loop, "_close_completed_asi_phase_plans"):
                            with unittest.mock.patch.object(peer_loop, "_prepare_continuous_prompts"):
                                with unittest.mock.patch.object(peer_loop, "_maybe_adapt"):
                                    with unittest.mock.patch.object(
                                        peer_loop,
                                        "_after_verify_ok",
                                        side_effect=lambda **kw: after_calls.append(kw.get("note", "")),
                                    ):
                                        with unittest.mock.patch.object(pt, "record_cycle_outcome") as rec:
                                            peer_loop._run_local_continuous(
                                                quick=True, log_fn=lambda _m: None, state=state
                                            )
        self.assertEqual(after_calls, [])
        self.assertTrue(rec.called)
        self.assertTrue(rec.call_args.kwargs.get("verify_ok"))

    def test_run_local_continuous_skips_after_verify_on_deferred(self) -> None:
        """Deferred/idle (rc=0, not ready) must not trigger continuous auto-commit."""
        import peer_loop
        import peer_transcript as pt

        state: dict = {}
        after_calls: list[str] = []
        with unittest.mock.patch.object(pt, "current_queue_fingerprint", return_value=("fpB", [])):
            with unittest.mock.patch.object(pt, "noop_backoff_remaining", return_value=0.0):
                with unittest.mock.patch.object(pt, "local_verify_cooldown_remaining", return_value=0.0):
                    with unittest.mock.patch.object(peer_loop, "_emit_worktree_inventory"):
                        with unittest.mock.patch.object(peer_loop, "_close_completed_asi_phase_plans"):
                            with unittest.mock.patch.object(peer_loop, "_prepare_continuous_prompts"):
                                with unittest.mock.patch.object(peer_loop, "_maybe_adapt"):
                                    with unittest.mock.patch.object(
                                        peer_loop,
                                        "_run_local_cycle",
                                        # _run_local_continuous unpacks (verify_failed, verified).
                                        return_value=(False, False),
                                    ) as cycle:
                                        with unittest.mock.patch.object(
                                            peer_loop,
                                            "_after_verify_ok",
                                            side_effect=lambda **kw: after_calls.append(
                                                kw.get("note", "")
                                            ),
                                        ):
                                            with unittest.mock.patch.object(pt, "record_cycle_outcome"):
                                                peer_loop._run_local_continuous(
                                                    quick=True, log_fn=lambda _m: None, state=state
                                                )
        cycle.assert_called_once()
        self.assertEqual(after_calls, [])

    def test_run_local_continuous_passes_backoff_sec_from_open_items(self) -> None:
        """open_items → noop backoff_sec threaded; untuned remasure path must not measure."""
        import peer_loop
        import peer_transcript as pt
        import project_automation as auto

        captured: dict = {}

        def _capture_noop(*, state, log_fn, backoff_sec=None):  # noqa: ARG001
            captured["backoff_sec"] = backoff_sec
            return 5.0

        def _boom_measure(*_a, **_k):  # pragma: no cover
            raise AssertionError("measure_live_state must not run when open_n known")

        state = {
            "last_cycle": {
                "verify_ok": True,
                "ts": 1e12,
                "local_only": True,
            }
        }
        cfg = dict(auto.CFG)
        cfg["stall_pivot_noop_backoff_sec"] = 0
        expected_backoff = None
        with unittest.mock.patch.object(auto, "CFG", cfg):
            expected_backoff = peer_loop.effective_noop_backoff_sec(open_queue_count=2)
            with unittest.mock.patch.object(
                pt, "current_queue_fingerprint", return_value=("fp", ["item-a", "item-b"])
            ):
                with unittest.mock.patch.object(auto, "measure_live_state", side_effect=_boom_measure):
                    with unittest.mock.patch.object(
                        peer_loop, "_noop_remaining_or_clear", side_effect=_capture_noop
                    ):
                        with unittest.mock.patch.object(peer_loop.stall, "maybe_pivot"):
                            peer_loop._run_local_continuous(
                                quick=True,
                                log_fn=lambda *_a, **_k: None,
                                state=state,
                                open_items=["item-a", "item-b"],
                            )
        self.assertIsNotNone(captured.get("backoff_sec"))
        self.assertEqual(captured["backoff_sec"], expected_backoff)
        self.assertEqual(expected_backoff, peer_loop.NOOP_BACKOFF_SEC)

    def test_maybe_auto_commit_skips_when_disabled(self) -> None:
        import peer_loop

        logs: list[str] = []
        with unittest.mock.patch.object(peer_loop.auto, "auto_commit_after_verify_enabled", return_value=False):
            ok = peer_loop.maybe_auto_commit_after_verify(log_fn=logs.append, note="test")
        self.assertTrue(ok)
        self.assertEqual(logs, [])

    def _init_auto_commit_repo(self, root: Path) -> None:
        subprocess.run(["git", "init"], cwd=root, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=root,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=root,
            capture_output=True,
            check=True,
        )

    def test_maybe_auto_commit_commits_dirty_tree(self) -> None:
        import peer_loop

        with tempfile.TemporaryDirectory(prefix="peer-auto-commit-") as tmp:
            root = Path(tmp)
            self._init_auto_commit_repo(root)
            (root / "hello.txt").write_text("hi\n", encoding="utf-8")
            logs: list[str] = []
            with unittest.mock.patch.object(peer_loop, "ROOT", root):
                with unittest.mock.patch.object(
                    peer_loop, "_commit_paths_after_verify", return_value=[root]
                ):
                    with unittest.mock.patch.object(
                        peer_loop.auto, "auto_commit_after_verify_enabled", return_value=True
                    ):
                        with unittest.mock.patch.object(
                            peer_loop.auto, "auto_push_after_commit_enabled", return_value=False
                        ):
                            with unittest.mock.patch.object(
                                peer_loop.auto, "auto_commit_max_passes", return_value=2
                            ):
                                with unittest.mock.patch.object(
                                    peer_loop.auto,
                                    "auto_commit_git_timeout_sec",
                                    return_value=60.0,
                                ):
                                    with unittest.mock.patch.object(
                                        peer_loop.auto,
                                        "auto_commit_exclude_pathspecs",
                                        return_value=[":(exclude)*.pt", ":(exclude)*.local.json"],
                                    ):
                                        ok = peer_loop.maybe_auto_commit_after_verify(
                                            log_fn=logs.append, note="unit"
                                        )
            self.assertTrue(ok)
            self.assertTrue(any("auto-commit: ok" in line for line in logs))
            proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(proc.stdout.strip(), "")

    def test_maybe_auto_commit_excludes_weights_and_local(self) -> None:
        """Smart commit always lands code; leaves weights/local soft-dirty."""
        import peer_loop

        with tempfile.TemporaryDirectory(prefix="peer-auto-commit-ex-") as tmp:
            root = Path(tmp)
            self._init_auto_commit_repo(root)
            (root / "app.py").write_text("print(1)\n", encoding="utf-8")
            (root / "model.pt").write_bytes(b"\x00\x01weights")
            (root / "secret.local.json").write_text('{"x":1}\n', encoding="utf-8")
            logs: list[str] = []
            with unittest.mock.patch.object(peer_loop, "ROOT", root):
                with unittest.mock.patch.object(
                    peer_loop, "_commit_paths_after_verify", return_value=[root]
                ):
                    with unittest.mock.patch.object(
                        peer_loop.auto, "auto_commit_after_verify_enabled", return_value=True
                    ):
                        with unittest.mock.patch.object(
                            peer_loop.auto, "auto_push_after_commit_enabled", return_value=False
                        ):
                            with unittest.mock.patch.object(
                                peer_loop.auto, "auto_commit_max_passes", return_value=2
                            ):
                                with unittest.mock.patch.object(
                                    peer_loop.auto,
                                    "auto_commit_git_timeout_sec",
                                    return_value=60.0,
                                ):
                                    with unittest.mock.patch.object(
                                        peer_loop.auto,
                                        "auto_commit_exclude_pathspecs",
                                        return_value=[
                                            ":(exclude)*.pt",
                                            ":(exclude)*.local.json",
                                        ],
                                    ):
                                        ok = peer_loop.maybe_auto_commit_after_verify(
                                            log_fn=logs.append, note="unit"
                                        )
            self.assertTrue(ok)
            self.assertTrue(any("auto-commit: ok" in line for line in logs))
            proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            porcelain = proc.stdout
            self.assertNotIn("app.py", porcelain)
            self.assertIn("model.pt", porcelain)
            self.assertIn("secret.local.json", porcelain)
            # Second pass: only excludes left → soft-dirty success, no new commit required
            logs2: list[str] = []
            with unittest.mock.patch.object(peer_loop, "ROOT", root):
                with unittest.mock.patch.object(
                    peer_loop, "_commit_paths_after_verify", return_value=[root]
                ):
                    with unittest.mock.patch.object(
                        peer_loop.auto, "auto_commit_after_verify_enabled", return_value=True
                    ):
                        with unittest.mock.patch.object(
                            peer_loop.auto, "auto_push_after_commit_enabled", return_value=False
                        ):
                            with unittest.mock.patch.object(
                                peer_loop.auto, "auto_commit_max_passes", return_value=2
                            ):
                                with unittest.mock.patch.object(
                                    peer_loop.auto,
                                    "auto_commit_git_timeout_sec",
                                    return_value=60.0,
                                ):
                                    with unittest.mock.patch.object(
                                        peer_loop.auto,
                                        "auto_commit_exclude_pathspecs",
                                        return_value=[
                                            ":(exclude)*.pt",
                                            ":(exclude)*.local.json",
                                        ],
                                    ):
                                        ok2 = peer_loop.maybe_auto_commit_after_verify(
                                            log_fn=logs2.append, note="unit2"
                                        )
            self.assertTrue(ok2)
            self.assertTrue(any("soft-dirty only" in line for line in logs2))


class SpawnSlotCapTests(unittest.TestCase):
    def test_spawn_refuses_slot_outside_cap(self) -> None:
        """test-quick must see spawn refuse (not only tests.test_peer_worktree)."""
        import peer_worktree as wt

        with unittest.mock.patch.object(wt.auto, "max_parallel_peers", return_value=8):
            with self.assertRaises(RuntimeError) as ctx:
                wt.spawn_parallel_worktree(47, root=Path("/repo"), dry_run=True)
            self.assertIn("refuse slot 47", str(ctx.exception))
            with self.assertRaises(RuntimeError) as ctx20:
                wt.spawn_parallel_worktree(
                    label="20", root=Path("/repo"), dry_run=True
                )
            self.assertIn("refuse slot 20", str(ctx20.exception))


class HubParallelPoolOnDiskTests(unittest.TestCase):
    """Self-check must hub-anchor pool isdir (not linked peer-N ROOT)."""

    def test_counts_under_primary_worktree_root(self) -> None:
        import peer_worktree as wt
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            hub = Path(td)
            for i in range(8):
                (hub / ".worktrees" / f"peer-{i}").mkdir(parents=True)
            # Linked-worktree illusion: auto.ROOT has no nested .worktrees.
            fake_peer_root = hub / ".worktrees" / "peer-1"
            with unittest.mock.patch.object(po.auto, "ROOT", fake_peer_root), unittest.mock.patch.object(
                wt, "primary_worktree_root", return_value=hub
            ), unittest.mock.patch.object(
                wt, "parallel_pool_config", return_value=(".worktrees", "peer")
            ):
                self.assertEqual(po._hub_parallel_pool_on_disk(8), 8)
                self.assertEqual(po._hub_parallel_pool_on_disk(4), 4)

    def test_zero_when_hub_floor_missing(self) -> None:
        import peer_worktree as wt
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            hub = Path(td)
            (hub / ".worktrees").mkdir()
            fake_peer_root = hub / "peer-checkout"
            fake_peer_root.mkdir()
            with unittest.mock.patch.object(po.auto, "ROOT", fake_peer_root), unittest.mock.patch.object(
                wt, "primary_worktree_root", return_value=hub
            ), unittest.mock.patch.object(
                wt, "parallel_pool_config", return_value=(".worktrees", "peer")
            ):
                self.assertEqual(po._hub_parallel_pool_on_disk(8), 0)


if __name__ == "__main__":
    unittest.main()
