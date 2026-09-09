"""Tests for automation_adapt — project detection, dynamic overlay, heal helpers."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import automation_adapt as adapt  # noqa: E402
import project_automation as auto  # noqa: E402


class AdaptDetectionTests(unittest.TestCase):
    def test_detect_node_stack_and_pm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({"name": "my-app", "scripts": {"test": "echo ok"}}))
            (root / "pnpm-lock.yaml").write_text("")
            sig = adapt.detect_signals(root, quick=True)
            self.assertEqual(sig.stack, "node")
            self.assertEqual(sig.profile, "node")
            self.assertEqual(sig.package_manager, "pnpm")

    def test_detect_python_stack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text('[project]\nname = "pyapp"\n')
            sig = adapt.detect_signals(root, quick=True)
            self.assertEqual(sig.stack, "python")
            self.assertEqual(sig.profile, "python")

    def test_detect_caas_stack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENT_MEMORY.md").write_text("# mem\n")
            (root / "docs/agent").mkdir(parents=True)
            (root / "docs/agent/AGENT_WORKFLOW.md").write_text("# wf\n")
            sig = adapt.detect_signals(root, quick=True)
            self.assertEqual(sig.stack, "caas")
            self.assertEqual(sig.profile, "caas")

    def test_lean_caas_verify_strips_hub_unittests(self) -> None:
        """OVERSEER_CAAS_NATIVE_VERIFY_2026_09_07 — kit poison must not stick."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "peer_orchestrate.py").write_text("# stub\n")
            (scripts / "with-node.sh").write_text("#!/bin/bash\n")
            (root / "package.json").write_text(
                json.dumps(
                    {
                        "name": "newdrop",
                        "scripts": {
                            "test": "vitest run",
                            "check:controls": "node scripts/check.js",
                        },
                    }
                )
            )
            poisoned = [
                "python3 scripts/peer_orchestrate.py --self-check",
                "python3 -m unittest tests.test_automation -q",
                "python3 -m unittest tests.test_peer_worktree -q",
                "bash scripts/with-node.sh npm test",
            ]
            lean = adapt._lean_caas_verify_commands(poisoned, root=root)
            self.assertEqual(
                lean,
                [
                    "python3 scripts/peer_orchestrate.py --self-check",
                    "bash scripts/with-node.sh npm test",
                    "bash scripts/with-node.sh npm run check:controls",
                ],
            )
            self.assertFalse(any(adapt._is_hub_automation_unittest_cmd(c) for c in lean))
            cands = adapt._stack_verify_candidates(root, "caas", "npm")
            self.assertIn("bash scripts/with-node.sh npm test", cands)
            self.assertNotIn("python3 -m unittest discover -s tests -q", cands)
            # Kit-copied profiles/automation.json must not re-lean to hub suite.
            (root / "profiles").mkdir(exist_ok=True)
            (root / "profiles" / "automation.json").write_text("{}\n")
            (root / "AGENT_MEMORY.md").write_text("# mem\n")
            (root / "docs/agent").mkdir(parents=True)
            (root / "docs/agent/AGENT_WORKFLOW.md").write_text("# wf\n")
            applied = adapt.apply_local_profile(
                root,
                {"verify_commands": lean, "_generated_by": "test"},
                write=True,
            )
            self.assertEqual(applied["verify_count"], 3)
            written = json.loads((root / "profiles" / "local.json").read_text())[
                "verify_commands"
            ]
            self.assertEqual(written, lean)

    def test_detect_ram_stack_and_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ram_jetsam.py").write_text("# stub\n")
            (root / "ram_attention.py").write_text("# stub\n")
            sig = adapt.detect_signals(root, quick=True)
            self.assertEqual(sig.stack, "ram")
            self.assertIn("ram_jetsam", sig.module_scope)

    def test_detect_automation_hub_stack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "peer_orchestrate.py").write_text("# stub\n")
            (scripts / "automation_adapt.py").write_text("# stub\n")
            (root / "automation.config.json").write_text('{"project_name": "Hub"}\n')
            sig = adapt.detect_signals(root, quick=True)
            self.assertEqual(sig.stack, "automation")
            self.assertEqual(sig.profile, "automation")

    def test_scan_scripts_module_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "peer_orchestrate.py").write_text("# stub\n")
            (scripts / "automation_adapt.py").write_text("# stub\n")
            (root / "automation.config.json").write_text("{}\n")
            scope = adapt.scan_module_scope(root, "automation")
            self.assertIn("peer_orchestrate", scope)
            self.assertIn("automation_adapt", scope)
            self.assertEqual(scope["peer_orchestrate"], "scripts/peer_orchestrate.py")

    def test_extract_ci_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wf = root / ".github/workflows/ci.yml"
            wf.parent.mkdir(parents=True)
            wf.write_text("jobs:\n  test:\n    steps:\n      - run: npm test\n      - run: npm run lint\n")
            cmds = adapt._extract_ci_run_commands(root)
            self.assertIn("npm test", cmds)
            self.assertIn("npm run lint", cmds)

    def test_generate_local_profile_has_verify(self) -> None:
        sig = adapt.ProjectSignals(
            root="/tmp",
            stack="node",
            profile="node",
            package_manager="npm",
            frameworks=["react"],
            project_name="App",
            project_slug="app",
            config_namespace="app",
            launch_agent_label="com.togi.app-peer-loop",
            test_command=["npm", "test"],
            test_probe="ok",
            verify_commands=["python3 scripts/peer_orchestrate.py --self-check", "npm test"],
            module_scope={"billing": "src/lib/billing/"},
            rss_entrypoint=None,
            post_cycle_hook=None,
            has_kit=True,
            kit_complete=True,
        )
        profile = adapt.generate_local_profile(Path("/tmp"), sig)
        self.assertIn("verify_commands", profile)
        self.assertIn("fw_react", profile.get("task_templates", {}))
        self.assertTrue(any(r.get("template", "").startswith("scope_") for r in profile.get("match_rules", [])))


class AdaptHealTests(unittest.TestCase):
    def test_heal_queue_drift_syncs_context_to_work_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = root / "scripts" / "self_improve_context.md"
            wq = root / "notes" / "WORK_QUEUE.md"
            ctx.parent.mkdir(parents=True)
            wq.parent.mkdir(parents=True)
            ctx.write_text(
                "## Remaining work (priority order)\n\n"
                "- [ ] ****Only in context** — trun**\n\n"
                "## Product rules (never regress)\n\n- sync\n"
            )
            wq.write_text(
                "## Active\n\n"
                "- [ ] **Only in context** — full canonical text\n\n"
                "## Backlog\n"
            )
            actions, _ = adapt.heal_queue_drift(root=root, write=True)
            self.assertTrue(any("reconciled context" in a for a in actions))
            self.assertIn("full canonical text", ctx.read_text())
            self.assertNotIn("trun**", ctx.read_text())

    def test_heal_queue_drift_restores_headerless_sic(self) -> None:
        """OVERSEER_HEADERLESS_SIC_DRIFT_2026_09_07 — fuel-only twin → restore from WQ."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = root / "scripts" / "self_improve_context.md"
            wq = root / "notes" / "WORK_QUEUE.md"
            ctx.parent.mkdir(parents=True)
            wq.parent.mkdir(parents=True)
            wq_body = (
                "## Active\n\n"
                "- [ ] **Ship factory fix** — real work\n\n"
                "## Backlog\n\n"
                "- [ ] deferred theater\n"
            )
            # ~356B headerless fuel orphans (repro of keep-alive clobber)
            fuel_only = (
                "- [ ] [compression-train] Keep-alive fuel — T4 / recipe lock "
                "/ min-RAM @ NVFP4 (2026-09-07 20:00Z) NEEDLE\n"
                "- [ ] [compression-train] Efficiency pass — cut unique U; "
                "raise S toward 100; measure pack bytes (2026-09-07 20:00Z)\n"
                "- [ ] [research-speed] Staff CLEAN fanout — respawn if agents "
                "< floor (2026-09-07 20:00Z)\n"
            )
            wq.write_text(wq_body, encoding="utf-8")
            ctx.write_text(fuel_only, encoding="utf-8")
            self.assertTrue(
                __import__("project_automation", fromlist=["x"]).context_twin_structure_broken(
                    fuel_only, wq_body
                )
            )
            import project_automation as auto

            warns = auto.sync_queue_drift(fuel_only, wq_body)
            self.assertTrue(any("headerless twin" in w for w in warns), warns)
            actions, warnings = adapt.heal_queue_drift(root=root, write=True)
            self.assertTrue(
                any("restored headerless context twin" in a for a in actions), actions
            )
            restored = ctx.read_text(encoding="utf-8")
            self.assertIn("## Active", restored)
            self.assertIn("Ship factory fix", restored)
            self.assertFalse(auto.context_twin_structure_broken(restored, wq.read_text()))
            # Structure warning cleared after heal (item Remaining sync may remain)
            self.assertFalse(any("headerless twin" in w for w in warnings), warnings)

    def test_heal_queue_drift_removes_context_only_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = root / "scripts" / "self_improve_context.md"
            wq = root / "notes" / "WORK_QUEUE.md"
            ctx.parent.mkdir(parents=True)
            wq.parent.mkdir(parents=True)
            ctx.write_text(
                "## Remaining work (priority order)\n\n"
                "- [ ] **Only in context** — task\n\n"
                "## Product rules (never regress)\n\n- sync\n"
            )
            wq.write_text("## Active\n\n## Backlog\n")
            actions, _ = adapt.heal_queue_drift(root=root, write=True)
            self.assertTrue(any("removed from context" in a for a in actions))
            self.assertNotIn("Only in context", ctx.read_text())

    def test_heal_refuses_empty_active_drop_of_top10(self) -> None:
        """OVERSEER_MAC_CLEAN_QUEUE_TWIN_2026_09_07 — restore Top10 into WQ."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = root / "scripts" / "self_improve_context.md"
            wq = root / "notes" / "WORK_QUEUE.md"
            ctx.parent.mkdir(parents=True)
            wq.parent.mkdir(parents=True)
            top10 = (
                "**[top10] Newdrop — finish containment Stripe 503 PR** — "
                "land peer/backend-containment-stripe-503"
            )
            ctx.write_text(
                "## Active\n\n"
                f"- [ ] {top10}\n\n"
                "## Remaining work (priority order)\n\n"
                f"- [ ] {top10}\n\n"
                "## Backlog\n"
            )
            wq.write_text("## Active\n\n## Backlog\n")
            import project_automation as auto

            warns = auto.sync_queue_drift(ctx.read_text(), wq.read_text())
            self.assertTrue(
                any("CLEAN empty-Active while context has Top10" in w for w in warns),
                warns,
            )
            actions, warnings = adapt.heal_queue_drift(root=root, write=True)
            self.assertTrue(
                any("restored Top10 to WORK_QUEUE" in a for a in actions), actions
            )
            wq_text = wq.read_text()
            self.assertIn("containment Stripe 503", wq_text)
            self.assertIn("- [ ]", wq_text)
            # Must not strip Top10 from Remaining
            self.assertIn("containment Stripe 503", ctx.read_text())
            self.assertFalse(
                any("removed from context" in a and "top10" in a.lower() for a in actions),
                actions,
            )
            # Post-heal: Active opens match
            post = auto.sync_queue_drift(ctx.read_text(), wq.read_text())
            self.assertFalse(
                any("CLEAN empty-Active while context has Top10" in w for w in post),
                post,
            )
            self.assertFalse(any("only in self_improve_context" in w for w in post), post)

    def test_heal_inserts_remaining_when_active_already_mirrored(self) -> None:
        """OVERSEER_INSERT_CTX_REMAINING_ONLY_2026_09_07 — Active twin ≠ Remaining sync."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = root / "scripts" / "self_improve_context.md"
            wq = root / "notes" / "WORK_QUEUE.md"
            ctx.parent.mkdir(parents=True)
            wq.parent.mkdir(parents=True)
            item = (
                "**[factory] Example Remaining sync fuel item** — "
                "keep open until Remaining twin populated; NO PAY"
            )
            ctx.write_text(
                "## Active\n\n"
                f"- [ ] {item}\n\n"
                "## Remaining work (priority order)\n\n"
                "- [x] **old done** — closed\n\n"
                "## Product rules (never regress)\n\n- sync\n"
            )
            wq.write_text(
                "## Active\n\n"
                f"- [ ] {item}\n\n"
                "## Backlog\n"
            )
            actions, warnings = adapt.heal_queue_drift(root=root, write=True)
            self.assertTrue(any("synced to context" in a for a in actions), actions)
            self.assertEqual(warnings, [])
            import project_automation as auto

            remaining = auto.remaining_work_items(ctx.read_text())
            self.assertEqual(len(remaining), 1)
            self.assertIn("factory] example remaining", remaining[0].lower())

    def test_heal_mirrors_active_when_remaining_already_has_open(self) -> None:
        """OVERSEER_SIC_ACTIVE_MIRROR_HEAL_2026_09_08 — Remaining≠Active file twin."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = root / "scripts" / "self_improve_context.md"
            wq = root / "notes" / "WORK_QUEUE.md"
            ctx.parent.mkdir(parents=True)
            wq.parent.mkdir(parents=True)
            item = (
                "**[top10] Newdrop production — next meaningful non-UI merge** — "
                "after #163; file-scoped `/home/arnavrastogi/CaaS`; NO PAY"
            )
            ctx.write_text(
                "## Active\n\n"
                "- [x] **old closed** — landed\n\n"
                "## Remaining work (priority order)\n\n"
                f"- [ ] {item}\n\n"
            )
            wq.write_text(
                "## Active\n\n"
                f"- [ ] {item}\n\n"
                "## Backlog\n"
            )
            actions, warnings = adapt.heal_queue_drift(root=root, write=True)
            self.assertEqual(warnings, [])
            self.assertTrue(
                any("mirrored Active open" in a for a in actions),
                actions,
            )
            import project_automation as auto

            phased = auto._parse_phased_work_items(ctx.read_text())
            self.assertEqual(len(phased), 1)
            self.assertIn("after #163", phased[0])

    def test_heal_queue_drift_demotes_active_when_context_backlog(self) -> None:
        """OVERSEER_HEAL_DEMOTE_CTX_BACKLOG_2026_09_06 — prefer Backlog SoT."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = root / "scripts" / "self_improve_context.md"
            wq = root / "notes" / "WORK_QUEUE.md"
            ctx.parent.mkdir(parents=True)
            wq.parent.mkdir(parents=True)
            ctx.write_text(
                "## Remaining work (priority order)\n\n"
                "## Backlog\n\n"
                "- [ ] [compression-train] After full train: run ALL stress tests\n"
            )
            wq.write_text(
                "## Active\n\n"
                "- [ ] [compression-train] After full train: run ALL stress tests\n"
                "- [ ] **Ship something else** — keep active\n\n"
                "## Backlog\n\n"
            )
            actions, warnings = adapt.heal_queue_drift(root=root, write=True)
            self.assertTrue(any("demoted" in a and "Backlog" in a for a in actions), actions)
            self.assertEqual(warnings, [])
            text = wq.read_text()
            # Active should keep Ship; compression-train only under Backlog
            active = text.split("## Backlog")[0]
            self.assertNotIn("compression-train", active)
            self.assertIn("Ship something else", active)
            self.assertIn("compression-train", text.split("## Backlog", 1)[1])
            remaining = ctx.read_text()
            self.assertNotIn("compression-train", remaining.split("## Backlog")[0])

    def test_heal_queue_drift_strips_backlog_active_clones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = root / "scripts" / "self_improve_context.md"
            wq = root / "notes" / "WORK_QUEUE.md"
            ctx.parent.mkdir(parents=True)
            wq.parent.mkdir(parents=True)
            ctx.write_text(
                "## Remaining work (priority order)\n\n"
                "- [ ] **Ship proof** — active copy\n"
            )
            wq.write_text(
                "## Active\n\n"
                "- [ ] **Ship proof** — active copy\n\n"
                "## Backlog\n\n"
                "- [ ] **Ship proof** — backlog twin\n"
                "- [ ] **Keep backlog** — unique\n"
            )
            actions, warnings = adapt.heal_queue_drift(root=root, write=True)
            self.assertTrue(any("backlog active-clone" in a for a in actions))
            self.assertEqual(warnings, [])
            text = wq.read_text()
            self.assertEqual(text.count("Ship proof"), 1)
            self.assertIn("Keep backlog", text)

    def test_heal_queue_drift_strips_open_done_twins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = root / "scripts" / "self_improve_context.md"
            wq = root / "notes" / "WORK_QUEUE.md"
            ctx.parent.mkdir(parents=True)
            wq.parent.mkdir(parents=True)
            ctx.write_text(
                "## Remaining work (priority order)\n\n"
                "- [ ] **Unique factory item** — stay\n"
            )
            wq.write_text(
                "## Active\n\n"
                "- [ ] **[efficiency-research] Break noop loop — advance or shrink queue**"
                " — Last ok cycle left queue fingerprint unchanged\n"
                "- [x] **[efficiency-research] Break noop loop — advance or shrink queue**"
                " — Last ok cycle left queue fingerprint unchanged\n"
                "- [ ] **Unique factory item** — stay\n\n"
                "## Backlog\n"
            )
            actions, warnings = adapt.heal_queue_drift(root=root, write=True)
            self.assertTrue(any("open-done" in a for a in actions))
            self.assertEqual(warnings, [])
            wq_text = wq.read_text()
            ctx_text = ctx.read_text()
            self.assertNotRegex(
                wq_text, r"- \[ \] \*\*\[efficiency-research\] Break noop loop"
            )
            self.assertIn("Unique factory item", wq_text)
            self.assertIn("Unique factory item", ctx_text)
            self.assertNotIn("Break noop loop", ctx_text)

    def test_heal_queue_drift_closes_stale_sync_meta(self) -> None:
        """OVERSEER_CLOSE_STALE_SYNC_META_2026_09_08 — Sync meta dies after twin fuel match."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = root / "scripts" / "self_improve_context.md"
            wq = root / "notes" / "WORK_QUEUE.md"
            ctx.parent.mkdir(parents=True)
            wq.parent.mkdir(parents=True)
            sync = (
                "**Sync WORK_QUEUE ↔ context** — CLEAN empty-Active while context "
                "has Top10 opens — restore WORK_QUEUE (1 item(s); Mac↔CLEAN twin)"
            )
            top10 = (
                "**[top10] Newdrop tip-cover after #177** — Soft Soft-land OK; NO PAY"
            )
            ctx.write_text(
                "## Active\n\n"
                f"- [ ] {sync}\n"
                f"- [ ] {top10}\n\n"
                "## Remaining work (priority order)\n\n"
                f"- [ ] {top10}\n\n"
                "## Backlog\n"
            )
            wq.write_text(
                "## Active\n\n"
                f"- [ ] {top10}\n"
                f"- [ ] {sync}\n\n"
                "## Backlog\n"
            )
            actions, warnings = adapt.heal_queue_drift(root=root, write=True)
            self.assertTrue(
                any("stale Sync" in a for a in actions),
                actions,
            )
            self.assertFalse(
                any("CLEAN empty-Active while context has Top10" in w for w in warnings),
                warnings,
            )
            wq_text = wq.read_text()
            ctx_text = ctx.read_text()
            self.assertRegex(wq_text, r"- \[x\] \*\*Sync WORK_QUEUE")
            self.assertRegex(ctx_text, r"- \[x\] \*\*Sync WORK_QUEUE")
            self.assertIn("- [ ] **[top10] Newdrop tip-cover after #177**", wq_text)
            self.assertIn("- [ ] **[top10] Newdrop tip-cover after #177**", ctx_text)

    def test_sync_queue_drift_warns_headerless_fuel_twin(self) -> None:
        """Headerless ~356B fuel orphans must not be drift-blind when Active opens empty."""
        fuel = (
            "- [ ] [compression-train] Keep-alive fuel — T4 / recipe lock / min-RAM "
            "@ NVFP4 (2026-09-07 13:21Z) OVERSEER_X\n"
            "- [ ] [compression-train] Efficiency pass — cut unique U; raise S "
            "toward 100; measure pack bytes (2026-09-07 13:21Z)\n"
            "- [ ] [research-speed] Staff CLEAN fanout — respawn if agents < floor "
            "(2026-09-07 13:21Z)\n"
        )
        wq = "## Active\n\n- [x] **done only** — closed\n\n## Done\n"
        self.assertTrue(auto.context_twin_structure_broken(fuel, wq))
        warnings = auto.sync_queue_drift(fuel, wq)
        self.assertTrue(
            any("headerless twin" in w for w in warnings),
            msg=warnings,
        )

    def test_heal_queue_drift_restores_headerless_context_twin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = root / "scripts" / "self_improve_context.md"
            wq = root / "notes" / "WORK_QUEUE.md"
            ctx.parent.mkdir(parents=True)
            wq.parent.mkdir(parents=True)
            fuel = (
                "- [ ] [compression-train] Keep-alive fuel — T4 / recipe lock / "
                "min-RAM @ NVFP4 (2026-09-07 13:21Z) OVERSEER_X\n"
                "- [ ] [compression-train] Efficiency pass — cut unique U\n"
                "- [ ] [research-speed] Staff CLEAN fanout — respawn\n"
            )
            wq.write_text(
                "## Active\n\n"
                "- [ ] **Ship twin** — canonical open\n\n"
                "## Done\n"
            )
            ctx.write_text(fuel)
            actions, warnings = adapt.heal_queue_drift(root=root, write=True)
            self.assertTrue(
                any("restored headerless context twin" in a for a in actions),
                msg=actions,
            )
            text = ctx.read_text()
            self.assertIn("## Active", text)
            self.assertIn("Ship twin", text)
            self.assertFalse(auto.context_twin_structure_broken(text, wq.read_text()))
            self.assertEqual(warnings, [])

    def test_apply_local_profile_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sig = adapt.detect_signals(root, quick=True)
            sig.verify_commands = ["echo ok"]
            overlay = adapt.generate_local_profile(root, sig)
            result = adapt.apply_local_profile(root, overlay, write=True)
            self.assertTrue(result["written"])
            self.assertTrue((root / "profiles" / "local.json").is_file())

    def test_apply_local_profile_replaces_verify_commands(self) -> None:
        """deep_merge appends lists; verify_commands must drop stale probes."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "profiles" / "local.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "verify_commands": [
                            "python3 scripts/peer_orchestrate.py --self-check",
                            "python3 -m unittest tests.test_automation -q",
                            "python3 -m unittest discover -s tests -q",
                        ]
                    }
                )
                + "\n"
            )
            # Hub CFG task_profile=automation expands via _lean_automation_verify_commands.
            # OVERSEER_LEAN_PEER_REPO_RESEARCH_2026_09_04 — assert live lean (not frozen 5-list)
            expected = adapt._lean_automation_verify_commands(None, stack="automation")
            self.assertIn("python3 -m unittest tests.test_peer_repo_research -q", expected)
            self.assertIn("python3 -m unittest tests.test_peer_remote -q", expected)
            self.assertIn("python3 -m unittest tests.test_pool_ensure_fastpath -q", expected)
            self.assertIn(
                "python3 -m unittest tests.test_peer_dual_research_linux_install -q", expected
            )
            self.assertEqual(len(expected), 19)
            adapt.apply_local_profile(
                root,
                {
                    "verify_commands": [
                        "python3 scripts/peer_orchestrate.py --self-check",
                        "python3 -m unittest tests.test_automation -q",
                    ]
                },
                write=True,
            )
            written = json.loads(path.read_text())["verify_commands"]
            self.assertEqual(written, expected)
            self.assertNotIn("python3 -m unittest discover -s tests -q", written)

    def test_lean_automation_verify_strips_discover(self) -> None:
        mixed = [
            "python3 scripts/peer_orchestrate.py --self-check",
            "python3 -m unittest tests.test_automation -q",
            "python3 -m unittest discover -s tests -q",
        ]
        lean = adapt._lean_automation_verify_commands(mixed, stack="automation")
        # OVERSEER_LEAN_PEER_REPO_RESEARCH_2026_09_04 — live lean nonet
        # OVERSEER_LEAN_NONET_2026_09_04
        self.assertEqual(lean, adapt._lean_automation_verify_commands(None, stack="automation"))
        self.assertIn("python3 -m unittest tests.test_peer_repo_research -q", lean)
        self.assertIn("python3 -m unittest tests.test_peer_remote -q", lean)
        self.assertEqual(len(lean), 19)
        self.assertNotIn("python3 -m unittest discover -s tests -q", lean)
        # Scrambled cache must canonicalize — else test_command thrash on heal.
        scrambled = [
            "python3 -m unittest tests.test_run_peer_tasks -q",
            "python3 scripts/peer_orchestrate.py --self-check",
            "python3 -m unittest tests.test_peer_pen_test -q",
        "python3 -m unittest tests.test_peer_remote -q",
        "python3 -m unittest tests.test_peer_last_cycle_poison -q",
        "python3 -m unittest tests.test_peer_repo_research -q",
        ]
        lean_s = adapt._lean_automation_verify_commands(scrambled, stack="automation")
        self.assertEqual(lean_s[0], "python3 scripts/peer_orchestrate.py --self-check")
        self.assertEqual(lean_s[1], "python3 -m unittest tests.test_automation -q")
        self.assertEqual(lean_s[2], "python3 -m unittest tests.test_run_peer_tasks -q")
        # Discover alone (no lean smoke yet) must still drop — else local.json recontaminates.
        discover_only = [
            "python3 scripts/peer_orchestrate.py --self-check",
            "python3 -m unittest discover -s tests -q",
        ]
        stripped = adapt._lean_automation_verify_commands(discover_only, stack="automation")
        self.assertNotIn("python3 -m unittest discover -s tests -q", stripped)
        self.assertIn("python3 -m unittest tests.test_peer_worktree -q", stripped)
        # Non-automation stacks keep discover.
        kept = adapt._lean_automation_verify_commands(mixed, stack="python")
        self.assertIn("python3 -m unittest discover -s tests -q", kept)

    def test_probe_quick_cache_strips_discover(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cached = [
                "python3 scripts/peer_orchestrate.py --self-check",
                "python3 -m unittest tests.test_automation -q",
                "python3 -m unittest discover -s tests -q",
            ]
            out = adapt.probe_verify_commands(root, [], quick=True, cached=cached)
            self.assertNotIn("python3 -m unittest discover -s tests -q", out)
            # OVERSEER_LEAN_PEER_REPO_RESEARCH_2026_09_04 — nonet incl. repo_research + remote
            self.assertEqual(len(out), 19)
            self.assertIn("python3 -m unittest tests.test_peer_repo_research -q", out)
            self.assertIn("python3 -m unittest tests.test_peer_remote -q", out)
            self.assertIn("python3 -m unittest tests.test_pool_ensure_fastpath -q", out)

    def test_should_re_adapt_without_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(adapt.should_re_adapt(root))

    def test_sync_git_fingerprint_updates_stored_fp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            # Identity via -c (no global git config in CI/sandbox) — matches AdaptExportTests pattern
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.email=test@example.com",
                    "-c",
                    "user.name=test",
                    "commit",
                    "--allow-empty",
                    "-m",
                    "init",
                ],
                cwd=root,
                check=True,
                capture_output=True,
            )
            self.assertTrue(adapt.should_re_adapt(root))
            (root / "notes.txt").write_text("mechanical\n")
            self.assertTrue(adapt.should_re_adapt(root))
            self.assertTrue(adapt.sync_git_fingerprint(root))
            self.assertFalse(adapt.should_re_adapt(root))
            self.assertFalse(adapt.sync_git_fingerprint(root))


class AdaptHelperTests(unittest.TestCase):
    def test_parse_shell_command(self) -> None:
        self.assertEqual(adapt._parse_shell_command("npm run test"), ["npm", "run", "test"])
        self.assertEqual(adapt._parse_shell_command('echo "hello world"'), ["echo", "hello world"])

    def test_strip_generated_overlay(self) -> None:
        raw = {
            "match_rules": [{"template": "scope_foo", "any": ["foo"]}, {"template": "git_hygiene", "any": ["git"]}],
            "task_templates": {"scope_foo": {}, "git_hygiene": {}},
        }
        stripped = adapt._strip_generated_overlay(raw)
        self.assertEqual(len(stripped["match_rules"]), 1)
        self.assertIn("git_hygiene", stripped["task_templates"])
        self.assertNotIn("scope_foo", stripped["task_templates"])

    def test_makefile_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text("test:\n\tpytest\nlint:\n\tflake8\n")
            targets = adapt._makefile_targets(root)
            self.assertIn("test", targets)
            self.assertIn("lint", targets)


class AdaptAuditTests(unittest.TestCase):
    def test_save_adapt_state_refuses_null_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ns = f"null-fp-test-{Path(tmp).name}"
            (root / "automation.config.json").write_text(
                json.dumps({"config_namespace": ns}) + "\n"
            )
            state_path = adapt.adapt_state_path(root)
            if state_path.is_file():
                state_path.unlink()
            state_path.parent.mkdir(parents=True, exist_ok=True)
            with mock.patch.object(adapt, "_git_fingerprint", return_value=None):
                adapt.save_adapt_state(root, {"git_fingerprint": None, "verify_commands": ["echo ok"]})
            data = json.loads(state_path.read_text())
            self.assertNotIn("git_fingerprint", data)
            self.assertEqual(data.get("verify_commands"), ["echo ok"])
            with mock.patch.object(adapt, "_git_fingerprint", return_value="deadbeef:"):
                adapt.save_adapt_state(root, {"git_fingerprint": "deadbeef:", "verify_commands": ["echo ok"]})
            with mock.patch.object(adapt, "_git_fingerprint", return_value=None):
                adapt.save_adapt_state(root, {"git_fingerprint": None, "verify_commands": ["echo ok"]})
            data = json.loads(state_path.read_text())
            self.assertEqual(data.get("git_fingerprint"), "deadbeef:")

    def test_audit_warns_null_fingerprint_when_signals_fp_none(self) -> None:
        """Quick-audit blind spot: signals.adapt_fingerprint=None must still warn on null stored."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ns = f"null-fp-audit-{Path(tmp).name}"
            (root / "automation.config.json").write_text(
                json.dumps({"config_namespace": ns}) + "\n"
            )
            state_path = adapt.adapt_state_path(root)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps({"git_fingerprint": None, "verify_commands": ["echo ok"]}) + "\n")
            sig = adapt.ProjectSignals(
                root=str(root),
                stack="python",
                profile="generic",
                package_manager=None,
                frameworks=[],
                project_name="T",
                project_slug="t",
                config_namespace=ns,
                launch_agent_label="com.togi.t",
                test_command=None,
                test_probe=None,
                verify_commands=["echo ok"],
                module_scope={},
                rss_entrypoint=None,
                post_cycle_hook=None,
                has_kit=False,
                kit_complete=False,
                missing_kit_paths=[],
                registry_match=None,
                ci_commands=[],
                adapt_fingerprint=None,
            )
            findings: list = []
            outputs: dict = {}
            with mock.patch.object(adapt, "_git_fingerprint", return_value="abc:live"):
                adapt._audit_adapt_state(root, sig, ["echo ok"], findings, outputs)
            warns = [f for f in findings if f.level == "warn" and f.category == "adapt_state"]
            self.assertTrue(any("fingerprint stale" in f.message for f in warns), findings)

    def test_run_audit_on_minimal_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "automation.config.json").write_text(json.dumps({
                "project_name": "T",
                "project_slug": "t",
                "config_namespace": "t",
                "launch_agent_label": "com.togi.t-peer-loop",
                "task_profile": "generic",
            }) + "\n")
            (root / "profiles").mkdir()
            (root / "profiles" / "local.json").write_text(json.dumps({
                "_generated_at": "2026-01-01T00:00:00+00:00",
                "verify_commands": ["python3 -c 'print(1)'"],
            }) + "\n")
            audit = adapt.run_audit(root, quick=True, audit_self=False)
            self.assertIn("config", audit.checks_run)
            self.assertIn("verify", audit.checks_run)
            self.assertTrue(audit.meta_ok)
            self.assertTrue(any(r.get("ok") for r in audit.verify_results))

    def test_audit_meta_requires_all_categories(self) -> None:
        report = adapt.AuditReport(
            root="/tmp",
            ok=True,
            findings=[],
            checks_run=["config"],
            verify_results=[{"ok": True}],
            output_files={"x": {}},
            meta_ok=False,
        )
        self.assertFalse(adapt._audit_meta(["config"], [], report))


class AdaptExportTests(unittest.TestCase):
    def test_export_tarball_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = adapt.export_tarball(Path(tmp))
            self.assertTrue(path.is_file())
            self.assertTrue(path.name.startswith("automation-kit-"))

    def test_export_tarball_excludes_local_json_and_dotenv(self) -> None:
        """OVERSEER_KIT_EXPORT_NO_LOCAL_SECRETS_2026_09_05 — consent export filter."""
        import tarfile

        with tempfile.TemporaryDirectory() as tmp:
            path = adapt.export_tarball(Path(tmp))
            names = tarfile.open(path, "r:gz").getnames()
            basenames = {Path(n).name for n in names}
            self.assertNotIn("dgx_speed.local.json", basenames)
            self.assertTrue(all(not b.startswith(".env") for b in basenames))
            self.assertNotIn("cursor-agent.env", basenames)
            self.assertTrue(
                any(n.endswith("automation_adapt.py") for n in names),
                msg="kit scripts must still export",
            )

    def test_export_tarball_excludes_model_weight_suffixes(self) -> None:
        """OVERSEER_KIT_EXPORT_NO_WEIGHTS_2026_09_07 — local-only model export control."""

        class _TI:
            def __init__(self, name: str) -> None:
                self.name = name

        self.assertTrue(hasattr(adapt, "_KIT_EXPORT_WEIGHT_SUFFIXES"))
        self.assertTrue(hasattr(adapt, "_kit_basename_is_weight"))
        self.assertIn(".pt", adapt._KIT_EXPORT_WEIGHT_SUFFIXES)
        src = Path(adapt.__file__).read_text(encoding="utf-8")
        self.assertIn("OVERSEER_KIT_EXPORT_NO_WEIGHTS_2026_09_07", src)
        self.assertIn("OVERSEER_KIT_INSTALL_NO_WEIGHTS_2026_09_07", src)
        for keep in ("notes/ok.md", "scripts/automation_adapt.py", "rung0_train_status.json"):
            self.assertIsNotNone(adapt._kit_export_tarinfo_filter(_TI(keep)))
            self.assertFalse(adapt._kit_basename_is_weight(keep))
        for drop in (
            "notes/compression_artifacts/rung0_checkpoints/rung0_final.pt",
            "weights/n02_queue.nvfp4.pt",
            "model.safetensors",
            "adapter.pth",
            "expert.gguf",
            "run.ckpt",
            "graph.onnx",
        ):
            self.assertIsNone(
                adapt._kit_export_tarinfo_filter(_TI(drop)),
                msg=f"expected DROP for {drop}",
            )
            self.assertTrue(adapt._kit_basename_is_weight(drop))

    def test_install_kit_skips_model_weight_files(self) -> None:
        """OVERSEER_KIT_INSTALL_NO_WEIGHTS_2026_09_07 — --install must not copy local .pt."""
        import unittest.mock

        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            target = Path(tmp) / "target"
            notes = hub / "notes" / "compression_artifacts" / "rung0_checkpoints"
            notes.mkdir(parents=True)
            (notes / "rung0_latest.pt").write_bytes(b"WEIGHT")
            (hub / "notes" / "ok.md").write_text("keep\n", encoding="utf-8")
            (hub / "scripts").mkdir()
            (hub / "scripts" / "automation_adapt.py").write_text("# stub\n", encoding="utf-8")
            with unittest.mock.patch.object(adapt, "kit_root", return_value=hub):
                with unittest.mock.patch.object(
                    adapt,
                    "KIT_COPY_PATHS",
                    ("notes", "scripts"),
                ):
                    actions = adapt.install_kit(target, force_scripts=True)
            self.assertFalse(
                (target / "notes/compression_artifacts/rung0_checkpoints/rung0_latest.pt").exists()
            )
            self.assertTrue((target / "notes/ok.md").is_file())
            self.assertTrue(any(a.startswith("skip (weight):") for a in actions))

    def test_install_kit_skips_local_secret_files(self) -> None:
        """OVERSEER_KIT_INSTALL_NO_LOCAL_SECRETS_2026_09_08 — --install must match export secret drop."""
        import unittest.mock

        self.assertTrue(hasattr(adapt, "_kit_basename_is_local_secret"))
        src = Path(adapt.__file__).read_text(encoding="utf-8")
        self.assertIn("OVERSEER_KIT_INSTALL_NO_LOCAL_SECRETS_2026_09_08", src)
        for keep in ("ok.md", "automation_adapt.py", "automation.config.json"):
            self.assertFalse(adapt._kit_basename_is_local_secret(keep))
        for drop in (
            "dgx_speed.local.json",
            "automation.config.local.json",
            ".env",
            ".env.local",
            "cursor-agent.env",
            "credentials.json",
        ):
            self.assertTrue(adapt._kit_basename_is_local_secret(drop), msg=drop)

        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            target = Path(tmp) / "target"
            (hub / "notes").mkdir(parents=True)
            (hub / "notes" / "ok.md").write_text("keep\n", encoding="utf-8")
            (hub / "scripts").mkdir()
            (hub / "scripts" / "automation_adapt.py").write_text("# stub\n", encoding="utf-8")
            (hub / "scripts" / "dgx_speed.local.json").write_text("{}\n", encoding="utf-8")
            (hub / "scripts" / "automation.config.local.json").write_text("{}\n", encoding="utf-8")
            (hub / "dgx_speed.local.json").write_text("{}\n", encoding="utf-8")
            (hub / ".env").write_text("SECRET=1\n", encoding="utf-8")
            with unittest.mock.patch.object(adapt, "kit_root", return_value=hub):
                with unittest.mock.patch.object(
                    adapt,
                    "KIT_COPY_PATHS",
                    ("notes", "scripts", "dgx_speed.local.json", ".env"),
                ):
                    actions = adapt.install_kit(target, force_scripts=True)
            self.assertTrue((target / "notes/ok.md").is_file())
            self.assertTrue((target / "scripts/automation_adapt.py").is_file())
            self.assertFalse((target / "dgx_speed.local.json").exists())
            self.assertFalse((target / "scripts/dgx_speed.local.json").exists())
            self.assertFalse((target / "scripts/automation.config.local.json").exists())
            self.assertFalse((target / ".env").exists())
            self.assertTrue(any(a.startswith("skip (secret):") for a in actions))


class AdaptHealFreshTests(unittest.TestCase):
    def test_run_heal_fresh_invokes_subprocess_not_inprocess(self) -> None:
        """Daemon heal must shell out so refuse-null is loaded from disk."""
        import unittest.mock

        fake = unittest.mock.Mock(
            returncode=0,
            stdout="=== automation adapt/heal ===\n  ✓ local profile: 2 verify command(s) written\n",
            stderr="",
        )
        stub_signals = adapt.ProjectSignals(
            root="/tmp",
            stack="automation",
            profile="automation",
            package_manager=None,
            frameworks=[],
            project_name="t",
            project_slug="t",
            config_namespace="t",
            launch_agent_label="com.togi.t",
            test_command=None,
            test_probe=None,
            verify_commands=[],
            module_scope={},
            rss_entrypoint=None,
            post_cycle_hook=None,
            has_kit=True,
            kit_complete=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with unittest.mock.patch.object(adapt.subprocess, "run", return_value=fake) as run_mock:
                with unittest.mock.patch.object(adapt, "detect_signals", return_value=stub_signals):
                    report = adapt.run_heal_fresh(write=True, target=root, quick=True)
        run_mock.assert_called_once()
        argv = run_mock.call_args.args[0]
        self.assertIn("--heal", argv)
        self.assertIn("--write", argv)
        self.assertIn("--quick", argv)
        self.assertIn("--target", argv)
        self.assertTrue(any("local profile" in a for a in report.actions))
        self.assertIn("run_heal_fresh", adapt.SCRIPT_REQUIRED_FUNCS)




class SyncVerifyCommandsStateTests(unittest.TestCase):
    """OVERSEER_SYNC_VERIFY_CMDS_2026_09_04."""

    def test_sync_verify_commands_state_aligns_local_and_adapt(self) -> None:
        self.assertTrue(hasattr(adapt, "sync_verify_commands_state"))
        self.assertIn("OVERSEER_SYNC_VERIFY_CMDS_2026_09_04", Path(adapt.__file__).read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "--allow-empty", "-m", "init"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            ns = f"sync-vc-{root.name}"
            (root / "automation.config.json").write_text(
                json.dumps({"config_namespace": ns, "task_profile": "automation"}) + "\n"
            )
            (root / "profiles").mkdir()
            incomplete = [
                "python3 scripts/peer_orchestrate.py --self-check",
                "python3 -m unittest tests.test_automation -q",
            ]
            (root / "profiles" / "local.json").write_text(
                json.dumps({"verify_commands": incomplete}) + "\n"
            )
            adapt.save_adapt_state(
                root,
                {"verify_commands": incomplete + ["echo stale"], "git_fingerprint": "old:"},
            )
            self.assertTrue(adapt.sync_verify_commands_state(root))
            local = json.loads((root / "profiles" / "local.json").read_text())
            state = adapt.load_adapt_state(root)
            lean = adapt._lean_automation_verify_commands([], stack="automation")
            self.assertEqual(local.get("verify_commands"), lean)
            self.assertEqual(state.get("verify_commands"), lean)
            self.assertFalse(adapt.should_re_adapt(root))
            self.assertIn("tests.test_peer_remote", " ".join(lean))


if __name__ == "__main__":
    unittest.main()
