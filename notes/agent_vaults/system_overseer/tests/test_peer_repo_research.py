#!/usr/bin/env python3
"""Tests for peer_repo_research."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_repo_research as prr  # noqa: E402


class TestPeerRepoResearch(unittest.TestCase):
    def test_make_id_stable(self) -> None:
        a = prr.RepoFlaw.make_id("audit", "missing config", "config")
        b = prr.RepoFlaw.make_id("audit", "missing config", "config")
        self.assertEqual(a, b)

    def test_merge_tracks_new_vs_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            findings = Path(tmp) / "findings.json"
            with mock.patch.object(prr, "FINDINGS_PATH", findings):
                flaw = prr.RepoFlaw(
                    id="abc123",
                    category="test",
                    severity="high",
                    title="Test flaw",
                    evidence="detail",
                )
                open_flaws, new_flaws = prr.merge_findings([flaw])
                self.assertEqual(len(new_flaws), 1)
                open_flaws2, new_flaws2 = prr.merge_findings([flaw])
                self.assertEqual(len(new_flaws2), 0)
                self.assertGreaterEqual(len(open_flaws2), 1)

    def test_merge_resolves_absent_bottleneck(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            findings = Path(tmp) / "findings.json"
            with mock.patch.object(prr, "FINDINGS_PATH", findings):
                flaw = prr.RepoFlaw(
                    id="bn1",
                    category="bottleneck",
                    severity="critical",
                    title="Daemon stopped",
                    evidence="no pid",
                )
                prr.merge_findings([flaw])
                open_flaws, _ = prr.merge_findings([])
                self.assertEqual(open_flaws, [])

    def test_merge_resolves_enqueued_ephemeral_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            findings = Path(tmp) / "findings.json"
            findings.write_text(
                json.dumps(
                    {
                        "items": {
                            "storm1": {
                                "id": "storm1",
                                "category": "bottleneck",
                                "severity": "high",
                                "title": "Unittest timeout storm",
                                "evidence": "10 timeout lines",
                                "status": "enqueued",
                            },
                            "orch1": {
                                "id": "orch1",
                                "category": "orchestrate",
                                "severity": "high",
                                "title": "peer_orchestrate self-check failed",
                                "evidence": "→ Role roster: 48 job title(s)",
                                "status": "enqueued",
                            },
                            "logic1": {
                                "id": "logic1",
                                "category": "logic",
                                "severity": "high",
                                "title": "plan-gate soften_recoverable_fails false-PASS",
                                "evidence": "landed leftover enqueued theater",
                                "status": "enqueued",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(prr, "FINDINGS_PATH", findings):
                open_flaws, _ = prr.merge_findings([])
                self.assertEqual(open_flaws, [])
                data = json.loads(findings.read_text(encoding="utf-8"))
                self.assertEqual(data["items"]["storm1"]["status"], "resolved")
                self.assertEqual(data["items"]["orch1"]["status"], "resolved")
                self.assertEqual(data["items"]["logic1"]["status"], "resolved")

    def test_merge_resolves_enqueued_defect_when_absent(self) -> None:
        """OVERSEER_RESOLVE_DEFECT_EPHEMERAL_2026_09_04 — stuck defect theater clears."""
        with tempfile.TemporaryDirectory() as tmp:
            findings = Path(tmp) / "findings.json"
            findings.write_text(
                json.dumps(
                    {
                        "items": {
                            "def1": {
                                "id": "def1",
                                "category": "defect",
                                "severity": "high",
                                "title": "_static_flaw_still_present inverted for eval_call/shell_true",
                                "evidence": "returns False on real eval() match",
                                "location": "scripts/peer_repo_research.py:646",
                                "status": "enqueued",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(prr, "FINDINGS_PATH", findings):
                open_flaws, _ = prr.merge_findings([])
                self.assertEqual(open_flaws, [])
                data = json.loads(findings.read_text(encoding="utf-8"))
                self.assertEqual(data["items"]["def1"]["status"], "resolved")

    def test_static_flaw_still_present_true_for_real_eval(self) -> None:
        """OVERSEER_STATIC_PRESENT_TRUE_ON_MATCH — real sink must stay present."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "scripts" / "evil.py"
            path.parent.mkdir(parents=True)
            path.write_text("x = eval(user_input)\n", encoding="utf-8")
            with mock.patch.object(prr, "ROOT", root):
                raw = {
                    "id": "eval_call:scripts/evil.py:1",
                    "location": "scripts/evil.py:1",
                    "evidence": "eval(user_input)",
                    "title": "eval() builtin — security/maintainability risk",
                }
                self.assertTrue(prr._static_flaw_still_present(raw))

    def test_static_flaw_still_present_false_for_tests_path(self) -> None:
        raw = {
            "location": "tests/test_peer_repo_research.py:66",
            "evidence": 'eval(x)',
            "title": "eval() usage",
        }
        self.assertFalse(prr._static_flaw_still_present(raw))

    def test_static_flaw_still_present_false_for_catalog_title(self) -> None:
        """Pattern catalog title strings must not keep static flaws open forever."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "scripts" / "peer_pen_test.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                '        "eval() builtin — code injection risk",\n'
                '        "subprocess shell=True — command injection risk",\n',
                encoding="utf-8",
            )
            with mock.patch.object(prr, "ROOT", root):
                raw = {
                    "location": "scripts/peer_pen_test.py:1",
                    "evidence": '"eval() builtin — code injection risk",',
                    "title": "eval() builtin — security/maintainability risk",
                }
                self.assertFalse(prr._static_flaw_still_present(raw))
                raw2 = {
                    "location": "scripts/peer_pen_test.py:2",
                    "evidence": '"subprocess shell=True — command injection risk",',
                    "title": "subprocess shell=True — injection risk",
                }
                self.assertFalse(prr._static_flaw_still_present(raw2))

    def test_probe_static_skips_pen_test_pattern_catalog(self) -> None:
        """SCAN_PATTERNS title strings in peer_pen_test.py are not sinks."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "scripts" / "peer_pen_test.py"
            path.parent.mkdir(parents=True)
            path.write_text(
                'SCAN_PATTERNS = (\n'
                '    ("eval_call", r"eval\\s*\\(", "high", "eval() builtin — code injection risk"),\n'
                '    ("shell_true", r"shell\\s*=\\s*True", "high", "subprocess shell=True — command injection risk"),\n'
                ')\n',
                encoding="utf-8",
            )
            with mock.patch.object(prr, "ROOT", root):
                flaws = prr.probe_static_flaws()
                self.assertEqual(flaws, [])

    def test_static_flaw_still_present_false_when_line_gone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "scripts" / "foo.py"
            path.parent.mkdir(parents=True)
            path.write_text("print('ok')\n", encoding="utf-8")
            with mock.patch.object(prr, "ROOT", root):
                raw = {
                    "location": "scripts/foo.py:1",
                    "evidence": "eval(x)",
                    "title": "eval() usage",
                }
                self.assertFalse(prr._static_flaw_still_present(raw))

    def test_build_digest_contains_summary(self) -> None:
        flaw = prr.RepoFlaw(
            id="x",
            category="static",
            severity="high",
            title="eval() usage",
            evidence="eval(x)",
            location="scripts/foo.py:1",
        )
        md = prr.build_digest(open_flaws=[flaw], new_flaws=[flaw], actions=["probed 1"], dispatched=False)
        self.assertIn("Repo flaw research", md)
        self.assertIn("eval()", md)
        self.assertIn("high", md)

    def test_build_digest_preserves_prior_agent_notes(self) -> None:
        """write_digest must not clobber ## Agent notes (peer_investigate retention)."""
        flaw = prr.RepoFlaw(
            id="x",
            category="static",
            severity="high",
            title="eval() usage",
            evidence="eval(x)",
            location="scripts/foo.py:1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            digest = Path(tmp) / "REPO_FLAW_RESEARCH.md"
            digest.write_text(
                "# Repo flaw research\n\n## Agent notes\n\n"
                "_Cursor-agent appends dated findings here after deep repo research._\n\n"
                "- **2026-09-02** Found: noop loop in peer_loop\n\n"
                "## Commands\n\n```bash\n./scripts/peer repo-research\n```\n",
                encoding="utf-8",
            )
            with mock.patch.object(prr, "digest_path", return_value=digest):
                md = prr.build_digest(
                    open_flaws=[flaw],
                    new_flaws=[],
                    actions=["rewrite"],
                    dispatched=False,
                )
                prr.write_digest(
                    open_flaws=[flaw],
                    new_flaws=[],
                    actions=["rewrite"],
                    dispatched=False,
                )
            second = digest.read_text(encoding="utf-8")
            self.assertIn("Found: noop loop in peer_loop", md)
            self.assertIn("Found: noop loop in peer_loop", second)
            self.assertIn("## Commands", second)
            # Boilerplate underscore line is not duplicated as a kept bullet
            self.assertEqual(second.count("Cursor-agent appends"), 1)


    def test_build_digest_preserves_hash_agent_notes(self) -> None:
        """OVERSEER_DIGEST_KEEP_HASH_NOTES_2026_09_04 — ### blocks survive rewrite."""
        flaw = prr.RepoFlaw(
            id="x",
            category="static",
            severity="high",
            title="eval() usage",
            evidence="eval(x)",
            location="scripts/foo.py:1",
        )
        with tempfile.TemporaryDirectory() as tmp:
            digest = Path(tmp) / "REPO_FLAW_RESEARCH.md"
            digest.write_text(
                "# Repo flaw research\n\n## Agent notes\n\n"
                "_Cursor-agent appends dated findings here after deep repo research._\n\n"
                "### 2026-09-04 research\n"
                "- Found: hash notes must stick\n"
                "**Severity:** medium\n\n"
                "## Commands\n\n```bash\n./scripts/peer repo-research\n```\n",
                encoding="utf-8",
            )
            with mock.patch.object(prr, "digest_path", return_value=digest):
                md = prr.build_digest(
                    open_flaws=[flaw], new_flaws=[], actions=["rewrite"], dispatched=False
                )
            self.assertIn("### 2026-09-04 research", md)
            self.assertIn("hash notes must stick", md)
            self.assertIn("**Severity:** medium", md)

    def test_mechanical_probe_with_mocks(self) -> None:
        with mock.patch.object(prr, "probe_audit_flaws", return_value=[]):
            with mock.patch.object(prr, "probe_bottleneck_flaws", return_value=[]):
                with mock.patch.object(prr, "probe_queue_flaws", return_value=[]):
                    with mock.patch.object(prr, "probe_live_flaws", return_value=[]):
                        with mock.patch.object(prr, "probe_static_flaws", return_value=[]):
                            flaws = prr.mechanical_probe()
        self.assertEqual(flaws, [])

    def test_probe_audit_skips_pass_info(self) -> None:
        class _F:
            def __init__(self, level: str, category: str, message: str) -> None:
                self.level = level
                self.category = category
                self.message = message

        class _R:
            ok = True
            findings = [
                _F("pass", "config", "automation.config.json valid"),
                _F("info", "verify", "SKIP quick: unittest"),
                _F("warn", "queue", "queue drift"),
                _F("error", "script", "compile fail"),
            ]
            checks_run = ["config"]

        with mock.patch.dict("sys.modules", {"automation_adapt": mock.Mock(run_audit=lambda *a, **k: _R())}):
            # Ensure import inside probe uses our mock
            import automation_adapt as adapt_mod  # noqa: F401

            with mock.patch("automation_adapt.run_audit", return_value=_R()):
                flaws = prr.probe_audit_flaws()
        titles = [f.title for f in flaws]
        self.assertTrue(any("queue drift" in t for t in titles))
        self.assertTrue(any("compile fail" in t for t in titles))
        self.assertFalse(any("valid" in t for t in titles))
        self.assertFalse(any("SKIP quick" in t for t in titles))


    def test_probe_live_ignores_in_flight_tests(self) -> None:
        live = mock.Mock(
            tests_ok=False,
            tests_detail="tests: skipped (another measure in flight)",
            git_clean=True,
            git_detail="git: clean",
        )
        with mock.patch.object(prr.auto, "measure_live_state", return_value=live):
            flaws = prr.probe_live_flaws()
        self.assertEqual(flaws, [])

    def test_probe_live_ignores_bare_fail_epilog(self) -> None:
        # OVERSEER_PROBE_SKIP_BARE_FAIL_2026_09_04 — empty epilog ≠ confirmed red.
        live = mock.Mock(
            tests_ok=False,
            tests_detail="tests: FAIL — failed",
            git_clean=True,
            git_detail="git: clean",
        )
        with mock.patch.object(prr.auto, "measure_live_state", return_value=live):
            flaws = prr.probe_live_flaws()
        self.assertEqual(flaws, [])
        src = Path(prr.__file__).read_text(encoding="utf-8")
        self.assertIn("OVERSEER_PROBE_SKIP_BARE_FAIL_2026_09_04", src)

    def test_probe_queue_dual_brain_detects_mismatch(self) -> None:
        """open_work_items(context_md=) must not be used — it still loads WORK_QUEUE."""
        work = (
            "## Active\n"
            "- [ ] **alpha task** — do alpha\n"
            "- [ ] **beta task** — do beta\n"
            "\n## Backlog (deferred — noop shrink)\n"
            "- [ ] **gamma task** — backlog only\n"
        )
        ctx = (
            "## Remaining work (priority order)\n"
            "- [ ] **alpha task** — do alpha\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wq = root / "WORK_QUEUE.md"
            cpath = root / "context.md"
            wq.write_text(work)
            cpath.write_text(ctx)
            with mock.patch.object(prr.auto, "WORK_QUEUE_PATH", wq):
                with mock.patch.object(prr.auto, "CONTEXT_PATH", cpath):
                    with mock.patch(
                        "automation_adapt.heal_queue_drift",
                        return_value=([], []),
                    ):
                        flaws = prr.probe_queue_flaws()
        dual = [f for f in flaws if "mismatch" in f.title.lower()]
        self.assertTrue(dual, f"expected dual-brain flaw, got {[f.title for f in flaws]}")
        self.assertIn("only_wq=", dual[0].evidence)

    def test_probe_queue_dual_brain_ignores_backlog_opens(self) -> None:
        """Backlog opens must not dual-brain HIGH; Remaining matches Active/phased only."""
        work = (
            "## Active\n"
            "- [ ] **alpha task** — do alpha\n"
            "\n## Backlog (deferred — noop shrink)\n"
            "- [ ] **gamma task** — backlog only\n"
        )
        ctx = (
            "## Remaining work (priority order)\n"
            "- [ ] **alpha task** — do alpha\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wq = root / "WORK_QUEUE.md"
            cpath = root / "context.md"
            wq.write_text(work)
            cpath.write_text(ctx)
            with mock.patch.object(prr.auto, "WORK_QUEUE_PATH", wq):
                with mock.patch.object(prr.auto, "CONTEXT_PATH", cpath):
                    with mock.patch(
                        "automation_adapt.heal_queue_drift",
                        return_value=([], []),
                    ):
                        flaws = prr.probe_queue_flaws()
        dual = [f for f in flaws if "mismatch" in f.title.lower()]
        self.assertEqual(dual, [], f"backlog-only extra must not HIGH, got {[f.evidence for f in dual]}")

    def test_probe_queue_dual_brain_ok_when_synced(self) -> None:
        work = (
            "## Active\n"
            "- [ ] **alpha task** — do alpha\n"
            "\n## Backlog (deferred — noop shrink)\n"
        )
        ctx = (
            "## Remaining work (priority order)\n"
            "- [ ] **alpha task** — do alpha\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wq = root / "WORK_QUEUE.md"
            cpath = root / "context.md"
            wq.write_text(work)
            cpath.write_text(ctx)
            with mock.patch.object(prr.auto, "WORK_QUEUE_PATH", wq):
                with mock.patch.object(prr.auto, "CONTEXT_PATH", cpath):
                    with mock.patch(
                        "automation_adapt.heal_queue_drift",
                        return_value=([], []),
                    ):
                        flaws = prr.probe_queue_flaws()
        dual = [f for f in flaws if "mismatch" in f.title.lower()]
        self.assertEqual(dual, [])

    def test_research_enabled_default(self) -> None:
        with mock.patch.object(prr.cfg_mod, "CFG", {"repo_research_enabled": True}):
            self.assertTrue(prr.research_enabled())

    def test_run_cycle_digest_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            findings = Path(tmp) / "findings.json"
            digest = Path(tmp) / "digest.md"
            with mock.patch.object(prr, "STATE_PATH", state):
                with mock.patch.object(prr, "FINDINGS_PATH", findings):
                    with mock.patch.object(prr, "research_enabled", return_value=True):
                        with mock.patch.object(prr, "digest_path", return_value=digest):
                            with mock.patch.object(
                                prr,
                                "mechanical_probe",
                                return_value=[
                                    prr.RepoFlaw(
                                        id="f1",
                                        category="test",
                                        severity="medium",
                                        title="Sample",
                                        evidence="e",
                                    )
                                ],
                            ):
                                result = prr.run_research_cycle(digest_only=True, force=True)
            self.assertIn("digest", result)
            self.assertTrue(digest.is_file())

    def test_static_scan_skips_todo_in_backtick_doc_examples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "scripts"
            scripts.mkdir()
            (scripts / "doc_example.py").write_text(
                'RULE = "| Search | never `rg TODO` or whole-repo skim |"\n',
                encoding="utf-8",
            )
            with mock.patch.object(prr, "ROOT", Path(tmp)):
                with mock.patch.object(prr, "STATIC_SCAN_ROOTS", ("scripts",)):
                    flaws = prr.probe_static_flaws()
        todo = [f for f in flaws if f.category == "static" and "TODO" in f.title]
        self.assertEqual(todo, [])

    def test_skip_mechanical_queue_drift_enqueue_true_for_only_in_evidence(self) -> None:
        flaw = prr.RepoFlaw(
            id="qd1",
            category="queue",
            severity="high",
            title="Queue drift",
            evidence="only in notes/WORK_QUEUE.md: foo",
        )
        self.assertTrue(prr._skip_mechanical_queue_drift_enqueue(flaw))

    def test_skip_mechanical_queue_drift_enqueue_false_for_bloated(self) -> None:
        flaw = prr.RepoFlaw(
            id="qb1",
            category="queue",
            severity="high",
            title="Executable queue bloated",
            evidence="open items above cap",
        )
        self.assertFalse(prr._skip_mechanical_queue_drift_enqueue(flaw))

    def test_skip_mechanical_self_check_fail_paste_theater(self) -> None:
        # OVERSEER_SKIP_SELFCHECK_PASTE_2026_09_04 — raw CLI must not become Active.
        flaw = prr.RepoFlaw(
            id="sc1",
            category="orchestrate",
            severity="high",
            title="peer_orchestrate self-check failed",
            evidence="✗ tests not ok: tests: FAIL — FAILED (failures=3)",
        )
        self.assertTrue(prr._skip_mechanical_queue_drift_enqueue(flaw))

    def test_probe_orchestrate_skips_lock_busy(self) -> None:
        proc = mock.Mock(returncode=75, stdout="SKIP: another self-check already running\n", stderr="")
        with mock.patch("subprocess.run", return_value=proc):
            self.assertEqual(prr.probe_orchestrate_flaws(), [])

    def test_cmd_status_linux_skips_launchctl(self) -> None:
        """OVERSEER_LINUX_REPO_RESEARCH_STATUS_2026_09_04"""
        with mock.patch.object(prr.sys, "platform", "linux"):
            with mock.patch("peer_self_heal._systemd_user_active", return_value=False):
                with mock.patch.object(prr, "_load_state", return_value={}):
                    with mock.patch.object(prr, "_load_findings_registry", return_value={"items": {}}):
                        with mock.patch("subprocess.run") as run:
                            rc = prr.cmd_status()
        self.assertEqual(rc, 1)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
