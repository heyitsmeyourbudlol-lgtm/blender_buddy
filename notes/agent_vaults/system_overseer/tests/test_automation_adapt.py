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
            self.assertEqual(len(expected), 9)
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
        self.assertEqual(len(lean), 9)
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
            self.assertEqual(len(out), 9)
            self.assertIn("python3 -m unittest tests.test_peer_repo_research -q", out)
            self.assertIn("python3 -m unittest tests.test_peer_remote -q", out)

    def test_should_re_adapt_without_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(adapt.should_re_adapt(root))

    def test_sync_git_fingerprint_updates_stored_fp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=root, check=True, capture_output=True)
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


if __name__ == "__main__":
    unittest.main()
