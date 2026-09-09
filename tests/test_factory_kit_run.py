"""Guards for factory_kit_run dry-run / registry resolve."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load():
    path = SCRIPTS / "factory_kit_run.py"
    spec = importlib.util.spec_from_file_location("factory_kit_run", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["factory_kit_run"] = mod
    spec.loader.exec_module(mod)
    return mod


class FactoryKitRunTests(unittest.TestCase):
    def test_dry_run_cpt_ok(self) -> None:
        mod = _load()
        report = mod.run_kit("CPT", dry_run=True, stop_after="C")
        self.assertTrue(report.get("ok"), report)
        self.assertEqual(report.get("dry_run"), True)
        steps = {s.get("step") for s in report.get("steps") or []}
        self.assertIn("A_adapt", steps)
        self.assertIn("B_verify", steps)
        self.assertIn("C_worktree", steps)

    def test_dry_run_cpt_through_e(self) -> None:
        """Phase2 A→E dry-run — OVERSEER_KIT_RUN_AE_2026_09_07."""
        mod = _load()
        report = mod.run_kit("CPT", dry_run=True, stop_after="E")
        self.assertTrue(report.get("ok"), report)
        steps = {s.get("step") for s in report.get("steps") or []}
        self.assertEqual(
            steps,
            {"A_adapt", "B_verify", "C_worktree", "D_artifact", "E_writeback"},
        )
        self.assertEqual(report.get("needle_ae"), "OVERSEER_KIT_RUN_AE_2026_09_07")

    def test_artifact_blocked_without_origin(self) -> None:
        mod = _load()
        # Honest blocked receipt is ok=True (Phase 2 stamp path)
        d = mod.step_artifact(
            Path("/tmp"),
            worktree_path=None,
            branch="peer/kit-test",
            dry_run=False,
        )
        self.assertTrue(d.get("ok"), d)
        self.assertEqual(d.get("mode"), "blocked_receipt")
        reasons = (d.get("blocked_receipt") or {}).get("reasons") or []
        self.assertTrue(reasons, d)

    def test_adapt_cmd_uses_target_not_root(self) -> None:
        """Live A must pass --target; --root is unrecognized (Phase2 false-green)."""
        mod = _load()
        a = mod.step_adapt(Path("/home/arnavrastogi/CPT"), dry_run=True)
        cmd = a.get("cmd") or []
        self.assertIn("--target", cmd)
        self.assertNotIn("--root", cmd)
        self.assertIn("--quick", cmd)  # OVERSEER_KIT_RUN_A_QUICK_2026_09_08
        self.assertIn("/home/arnavrastogi/CPT", cmd)

    def test_worktree_start_ref_prefers_origin_main(self) -> None:
        """OVERSEER_KIT_RUN_C_ORIGIN_MAIN_2026_09_08 — dirty HEAD must not be sole tip."""
        mod = _load()
        calls: list[list[str]] = []

        def fake_run(cmd, *, cwd, timeout=30):  # noqa: ANN001
            calls.append(list(cmd))
            if cmd[:3] == ["git", "rev-parse", "--verify"] and cmd[3] == "origin/main":
                return {"exit": 0, "stdout_tail": "abc\n", "stderr_tail": ""}
            return {"exit": 1, "stdout_tail": "", "stderr_tail": "missing"}

        with mock.patch.object(mod, "_run", side_effect=fake_run):
            ref = mod._worktree_start_ref(Path("/tmp/fake-repo"))
        self.assertEqual(ref, "origin/main")
        self.assertTrue(any("origin/main" in c for c in calls))

    def test_worktree_stamp_collision_retries(self) -> None:
        """OVERSEER_KIT_WT_STAMP_COLLISION_2026_09_08 — path-exists must not hard-fail C."""
        import tempfile

        mod = _load()
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "CyberActivity"
            target.mkdir()
            # Pre-create first stamp path so attempt 0 collides.
            stamps = ["20260908T04280800", "20260908T04280800r1"]
            first = target.parent / f"{target.name}-kit-a-to-z-{stamps[0]}"
            first.mkdir()
            calls = {"n": 0}

            def fake_stamp(*, attempt: int = 0) -> str:
                return stamps[min(attempt, len(stamps) - 1)]

            def fake_run(cmd, *, cwd, timeout=30):  # noqa: ANN001
                if cmd[:2] == ["git", "status"]:
                    return {"exit": 0, "stdout_tail": " M x\n", "stderr_tail": ""}
                if cmd[:3] == ["git", "worktree", "add"]:
                    calls["n"] += 1
                    # git worktree add -b <branch> <path> HEAD → path at index 5
                    Path(cmd[5]).mkdir(parents=True, exist_ok=True)
                    return {"exit": 0, "stdout_tail": "Preparing worktree\n", "stderr_tail": ""}
                return {"exit": 1, "stdout_tail": "", "stderr_tail": "unexpected"}

            with mock.patch.object(mod, "_kit_worktree_stamp", side_effect=fake_stamp):
                with mock.patch.object(mod, "_run", side_effect=fake_run):
                    out = mod.step_worktree(target, dry_run=False)
            self.assertTrue(out.get("ok"), out)
            self.assertEqual(out.get("status"), "worktree_added")
            self.assertGreaterEqual(out.get("attempts"), 2)
            self.assertIn("r1", out.get("suggested_branch", ""))
            self.assertEqual(calls["n"], 1)

    def test_heal_missing_verify_paths_copies_donor(self) -> None:
        """OVERSEER_KIT_RUN_HEAL_DONOR_2026_09_08 — origin/main tip may lack with-node."""
        import tempfile

        mod = _load()
        with tempfile.TemporaryDirectory() as td:
            wt = Path(td) / "wt"
            donor = Path(td) / "donor"
            wt.mkdir()
            (donor / "scripts").mkdir(parents=True)
            src = donor / "scripts" / "with-node.sh"
            src.write_text("#!/bin/bash\nexec \"$@\"\n", encoding="utf-8")
            src.chmod(0o755)

            def fake_run(cmd, *, cwd, timeout=30):  # noqa: ANN001
                # HEAD never has the path
                return {"exit": 1, "stdout_tail": "", "stderr_tail": "missing"}

            with mock.patch.object(mod, "_run", side_effect=fake_run):
                healed = mod.heal_missing_verify_paths_from_head(
                    wt,
                    ["bash scripts/with-node.sh npm test"],
                    donor=donor,
                )
            dest = wt / "scripts" / "with-node.sh"
            self.assertTrue(dest.is_file(), healed)
            self.assertTrue(any("with-node" in h for h in healed), healed)

    def test_patch_proof_md_upserts_run_and_last_compound(self) -> None:
        """OVERSEER_KIT_RUN_PROOF_UPSERT_2026_09_08 — always insert Runs + Last compound."""
        import tempfile

        mod = _load()
        with tempfile.TemporaryDirectory() as td:
            proof = Path(td) / "FACTORY_A_TO_Z_PROOF.md"
            proof.write_text(
                "# Factory A→Z proof\n\n"
                "## Lock status\n\n"
                "| Field | Value |\n"
                "|-------|-------|\n"
                "| Status | **green** |\n"
                "| First target | CPT |\n"
                "P26-09-08 Old A→E (blocked_receipt)|\n"
                "\n"
                "## Runs\n\n"
                "| Date | Repo | A adapt | B verify | C worktree | D artifact | E writeback | Notes |\n"
                "|------|------|---------|----------|------------|------------|-------------|-------|\n"
                "| 2026-09-07 | CPT | ok | ok | ok | pr | ok | prior |\n",
                encoding="utf-8",
            )
            with mock.patch.object(mod, "PROOF_MD", proof):
                mod._patch_proof_md(
                    repo="Newdrop (CaaS)",
                    steps=[
                        {"step": "A_adapt", "ok": True},
                        {"step": "B_verify", "ok": True},
                        {"step": "C_worktree", "ok": True},
                        {"step": "D_artifact", "ok": True},
                        {"step": "E_writeback", "ok": True},
                    ],
                    artifact={
                        "mode": "blocked_receipt",
                        "blocked_receipt": {"reasons": ["gh_cli_missing"]},
                    },
                )
            text = proof.read_text(encoding="utf-8")
            self.assertNotIn("P26-09-08", text)
            self.assertIn("| Last compound |", text)
            self.assertIn("| Newdrop (CaaS) |", text)
            self.assertIn("blocked:gh_cli_missing", text)

    def test_patch_proof_md_date_leading_last_compound_no_octal(self) -> None:
        """OVERSEER_KIT_RUN_PROOF_DATE_BACKREF_2026_09_08 — \\12026 must not become P26."""
        import tempfile

        mod = _load()
        with tempfile.TemporaryDirectory() as td:
            proof = Path(td) / "FACTORY_A_TO_Z_PROOF.md"
            proof.write_text(
                "# Factory A→Z proof\n\n"
                "## Lock status\n\n"
                "| Field | Value |\n"
                "|-------|-------|\n"
                "| Status | **green** |\n"
                "| First target | CPT |\n"
                "| Last compound | 2026-09-08 Newdrop (CaaS) A→E (pr) |\n"
                "\n"
                "## Runs\n\n"
                "| Date | Repo | A adapt | B verify | C worktree | D artifact | E writeback | Notes |\n"
                "|------|------|---------|----------|------------|------------|-------------|-------|\n"
                "| 2026-09-07 | CPT | ok | ok | ok | pr | ok | prior |\n",
                encoding="utf-8",
            )
            with mock.patch.object(mod, "PROOF_MD", proof):
                mod._patch_proof_md(
                    repo="Automation Hub",
                    steps=[
                        {"step": "A_adapt", "ok": True},
                        {"step": "B_verify", "ok": True},
                        {"step": "C_worktree", "ok": True},
                        {"step": "D_artifact", "ok": True},
                        {"step": "E_writeback", "ok": True},
                    ],
                    artifact={
                        "mode": "blocked_receipt",
                        "blocked_receipt": {
                            "reasons": ["no_origin_remote", "gh_cli_missing"]
                        },
                    },
                )
            text = proof.read_text(encoding="utf-8")
            self.assertNotIn("P26-09-08", text)
            self.assertIn(
                "| Last compound | 2026-09-08 Automation Hub A→E (blocked_receipt) |",
                text,
            )
            self.assertIn("| Automation Hub |", text)
            self.assertIn("blocked:no_origin_remote,gh_cli_missing", text)

    def test_find_repo_cpt(self) -> None:
        mod = _load()
        row = mod.find_repo(mod.load_registry(), "CPT")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertIn("CPT", str(row.get("name")))

    def test_home_mirrors_no_users_literal(self) -> None:
        """Static scanners flag hardcoded /Users/… — mirrors must be Path.home()-relative."""
        src = (SCRIPTS / "factory_kit_run.py").read_text(encoding="utf-8")
        self.assertNotIn('"/Users/', src)
        self.assertNotIn("'/Users/", src)
        mod = _load()
        with mock.patch.dict(os.environ, {"AUTOMATION_MAC_HOME": "/home/kit_mirror"}):
            for name, ns, must in (
                ("CPT", "cpt", "CPT"),
                ("ram-park", "ram-park", "ram"),
                ("Newdrop CaaS", "newdrop", "CaaS"),
                ("Doc2Api", "doc2api", "Doc2Api"),
            ):
                paths = mod._home_mirror_candidates(name, ns)
                self.assertTrue(paths, (name, ns))
                for path in paths:
                    self.assertTrue(path.startswith("/home/kit_mirror/"), path)
                self.assertTrue(
                    any(p.rstrip("/").endswith(must) for p in paths),
                    (name, ns, paths),
                )

    def test_home_mirrors_hyphen_slug_for_spaced_name(self) -> None:
        """OVERSEER_KIT_RUN_HYPHEN_MIRROR_2026_09_08 — spaced Mac name → hyphen CLEAN clone."""
        mod = _load()
        with mock.patch.dict(os.environ, {"AUTOMATION_MAC_HOME": "/home/kit_mirror"}):
            cands = mod._home_mirror_candidates(
                "Congressional App Challenge", "congressional-app-challenge"
            )
        self.assertIn("/home/kit_mirror/Congressional App Challenge", cands)
        self.assertIn("/home/kit_mirror/Congressional-App-Challenge", cands)
        self.assertIn("/home/kit_mirror/congressional-app-challenge", cands)

    def test_classify_push_auth_missing(self) -> None:
        mod = _load()
        reason = mod.classify_push_failure(
            exit_code=128,
            stderr="fatal: could not read Username for 'https://github.com': No such device or address",
        )
        self.assertEqual(reason, "push_auth_missing")
        generic = mod.classify_push_failure(exit_code=1, stderr="remote rejected")
        self.assertEqual(generic, "push_failed:1")

    def test_discover_origin_kit_prs_adopts_public_open(self) -> None:
        """OVERSEER_KIT_RUN_PUBLIC_OPEN_PR_2026_09_08 — public open kit PR beats blocked_receipt."""
        import io
        import json as _json

        mod = _load()
        payload = [
            {
                "number": 2,
                "state": "open",
                "merged_at": None,
                "html_url": "https://github.com/heyitsmeyourbudlol-lgtm/scratch/pull/2",
                "head": {
                    "ref": "peer/kit-a-to-z-20260908T053051",
                    "sha": "6673b7dabcdef0123456789",
                },
            }
        ]

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return _json.dumps(payload).encode()

        with mock.patch.object(
            mod,
            "_run",
            return_value={
                "exit": 0,
                "stdout_tail": "https://github.com/heyitsmeyourbudlol-lgtm/scratch.git\n",
            },
        ):
            with mock.patch("urllib.request.urlopen", return_value=_Resp()):
                hit = mod.discover_origin_kit_prs(Path("/tmp/scratch"))
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit["pr_url"], "https://github.com/heyitsmeyourbudlol-lgtm/scratch/pull/2")
        self.assertEqual(hit["branch"], "peer/kit-a-to-z-20260908T053051")
        self.assertIn("OVERSEER_KIT_RUN_PUBLIC_OPEN_PR_2026_09_08", hit["needle"])

        # step_artifact adopts when local push/gh blocked
        def fake_run(cmd, *, cwd, timeout=30):  # noqa: ANN001
            if cmd[:2] == ["git", "remote"] and len(cmd) == 2:
                return {"exit": 0, "stdout_tail": "origin\n"}
            if cmd[:3] == ["git", "remote", "get-url"]:
                return {
                    "exit": 0,
                    "stdout_tail": "https://github.com/heyitsmeyourbudlol-lgtm/scratch.git\n",
                }
            if cmd[:2] == ["git", "push"]:
                return {
                    "exit": 128,
                    "stderr_tail": "fatal: could not read Username for 'https://github.com'",
                    "stdout_tail": "",
                }
            return {"exit": 1, "stdout_tail": "", "stderr_tail": ""}

        with mock.patch.object(mod, "_run", side_effect=fake_run):
            with mock.patch.object(mod.shutil, "which", return_value=None):
                with mock.patch.object(mod, "discover_origin_kit_prs", return_value=hit):
                    d = mod.step_artifact(
                        Path("/tmp/scratch"),
                        worktree_path="/tmp/scratch-wt",
                        branch="peer/kit-local",
                        dry_run=False,
                    )
        self.assertEqual(d.get("mode"), "pr", d)
        self.assertTrue(d.get("adopted_public_pr"), d)
        self.assertEqual(d.get("pr_url"), hit["pr_url"])

    def test_green_lock_rejects_blocked_receipt(self) -> None:
        mod = _load()
        ok, why = mod.green_lock_eligible({"artifact_mode": "blocked_receipt"})
        self.assertFalse(ok)
        self.assertEqual(why, "blocked_receipt")
        # OVERSEER_FALSE_GREEN_LOCK_2026_09_07 — PR URL alone must not unlock.
        ok2, why2 = mod.green_lock_eligible(
            {
                "mode": "pr",
                "pr_url": "https://github.com/heyitsmeyourbudlol-lgtm/CPT/pull/1",
                "ok": True,
            }
        )
        self.assertFalse(ok2)
        self.assertEqual(why2, "pr_remote_ref_missing")
        ok3, why3 = mod.green_lock_eligible({"mode": "pr", "pr_url": "not-a-url", "ok": True})
        self.assertFalse(ok3)
        self.assertEqual(why3, "pr_url_missing")

    def test_green_lock_pr_requires_origin_ls_remote(self) -> None:
        """Eligible PR only when worktree exists and origin ls-remote hits branch."""
        import tempfile

        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp)
            (probe / ".git").mkdir()
            receipt = {
                "mode": "pr",
                "pr_url": "https://github.com/heyitsmeyourbudlol-lgtm/CPT/pull/1",
                "ok": True,
                "branch": "peer/kit-a-to-z",
                "worktree_path": str(probe),
            }
            with mock.patch.object(
                mod,
                "_run",
                return_value={"exit": 0, "stdout_tail": "abc123\trefs/heads/peer/kit-a-to-z\n"},
            ):
                ok, why = mod.green_lock_eligible(receipt)
            self.assertTrue(ok, why)
            self.assertEqual(why, "pr")
            with mock.patch.object(
                mod, "_run", return_value={"exit": 0, "stdout_tail": ""}
            ):
                ok_miss, why_miss = mod.green_lock_eligible(receipt)
            self.assertFalse(ok_miss)
            self.assertEqual(why_miss, "pr_remote_ref_missing")

    def test_heal_false_green_forces_red(self) -> None:
        """OVERSEER_FALSE_GREEN_LOCK_2026_09_07 — Status green + blocked receipt → force red."""
        import json
        import tempfile

        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes = root / "notes"
            notes.mkdir()
            proof = notes / "FACTORY_A_TO_Z_PROOF.md"
            proof.write_text(
                "# Factory A→Z proof\n\n"
                "## Lock status\n\n"
                "| Field | Value |\n"
                "|-------|-------|\n"
                "| Status | **green** |\n"
                "| Green lock stamped | fake PR |\n",
                encoding="utf-8",
            )
            receipt = notes / "factory_a_to_z_last.json"
            receipt.write_text(
                json.dumps(
                    {
                        "ok": True,
                        "artifact_mode": "blocked_receipt",
                        "steps": [
                            {
                                "step": "D_artifact",
                                "mode": "blocked_receipt",
                                "blocked_receipt": {
                                    "reasons": ["push_auth_missing", "gh_cli_missing"]
                                },
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            ext = notes / "EXTERNAL_PROOF.md"
            ext.write_text(
                "| # | Repo | Status | Verify | PR / merge | Date |\n"
                "|---|------|--------|--------|------------|------|\n"
                "| 1 | CPT | kit A→E **green** | ok | #1 | 2026-09-07 |\n",
                encoding="utf-8",
            )
            tasks = notes / "FACTORY_A_TO_Z_TASKS.md"
            tasks.write_text(
                "## Phase 4 — Green lock\n\n"
                "- [x] **[a-to-z:phase4] Stamp green lock** — fake\n"
                "- [x] **[a-to-z] Factory A→Z sequencing lock** — fake\n",
                encoding="utf-8",
            )
            with mock.patch.object(mod, "ROOT", root), mock.patch.object(
                mod, "PROOF_MD", proof
            ), mock.patch.object(mod, "PROOF_JSON", receipt), mock.patch.object(
                mod, "EXTERNAL_PROOF", ext
            ), mock.patch.object(mod, "TASKS_MD", tasks):
                heal = mod.heal_false_green_lock(write=True)
            self.assertTrue(heal.get("healed"), heal)
            self.assertEqual(heal.get("action"), "force_red")
            text = proof.read_text(encoding="utf-8")
            self.assertIn("**red**", text)
            self.assertIn(mod.NEEDLE_FALSE_GREEN, text)
            loaded = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(loaded.get("artifact_mode"), "blocked_receipt")
            self.assertIn("push_auth_missing", ext.read_text(encoding="utf-8"))
            self.assertIn("- [ ] **[a-to-z:phase4]", tasks.read_text(encoding="utf-8"))

    def test_dry_run_skips_live_receipt_write(self) -> None:
        """Dry-run must not clobber notes/factory_a_to_z_last.json."""
        import tempfile

        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "receipt.json"
            path.write_text('{"sentinel": true}\n', encoding="utf-8")
            with mock.patch.object(mod, "PROOF_JSON", path):
                report = {"ok": True, "dry_run": True}
                mod._commit_receipt(report, dry_run=True)
            self.assertEqual(path.read_text(encoding="utf-8"), '{"sentinel": true}\n')
            self.assertEqual(report.get("receipt_skipped"), "dry_run")

    def test_commit_receipt_live_writes_once(self) -> None:
        """Live path must call write_receipt — not recurse on _commit_receipt."""
        import json
        import tempfile

        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "receipt.json"
            with mock.patch.object(mod, "PROOF_JSON", path):
                report = {"ok": True, "artifact_mode": "blocked_receipt", "needle": "t"}
                mod._commit_receipt(report, dry_run=False)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded.get("artifact_mode"), "blocked_receipt")
            self.assertNotIn("receipt_skipped", report)

    def test_verify_cmd_paths_extracts_scripts(self) -> None:
        mod = _load()
        paths = mod._verify_cmd_paths(
            ["python3 scripts/peer_orchestrate.py --self-check", "bash scripts/with-node.sh npm test"]
        )
        self.assertEqual(paths, ["scripts/peer_orchestrate.py", "scripts/with-node.sh"])

    def test_heal_missing_verify_paths_from_head(self) -> None:
        """OVERSEER_KIT_RUN_B_ON_CLEAN_WT_2026_09_08 — restore deleted wrappers."""
        import tempfile

        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            wrapper = scripts / "with-node.sh"
            wrapper.write_text("#!/bin/bash\nexec \"$@\"\n", encoding="utf-8")
            wrapper.chmod(0o755)
            subprocess_calls: list[list[str]] = []

            def fake_run(cmd, *, cwd, timeout=900):  # noqa: ANN001
                subprocess_calls.append(list(cmd))
                if cmd[:3] == ["git", "cat-file", "-e"]:
                    return {"exit": 0, "stdout_tail": "", "stderr_tail": ""}
                if cmd[:3] == ["git", "checkout", "HEAD"]:
                    # simulate restore
                    wrapper.write_text("#!/bin/bash\n# healed\nexec \"$@\"\n", encoding="utf-8")
                    wrapper.chmod(0o755)
                    return {"exit": 0, "stdout_tail": "", "stderr_tail": ""}
                return {"exit": 1, "stdout_tail": "", "stderr_tail": "unexpected"}

            wrapper.unlink()
            self.assertFalse(wrapper.exists())
            with mock.patch.object(mod, "_run", side_effect=fake_run):
                healed = mod.heal_missing_verify_paths_from_head(
                    root, ["bash scripts/with-node.sh npm test"]
                )
            self.assertEqual(healed, ["scripts/with-node.sh"])
            self.assertTrue(wrapper.exists())

    def test_dry_run_creates_worktree_before_verify(self) -> None:
        """B runs after C in step list — dirty-main safe verify."""
        mod = _load()
        report = mod.run_kit("CPT", dry_run=True, stop_after="E")
        names = [s.get("step") for s in report.get("steps") or []]
        self.assertEqual(
            names,
            ["A_adapt", "C_worktree", "B_verify", "D_artifact", "E_writeback"],
        )
        b = next(s for s in report["steps"] if s.get("step") == "B_verify")
        self.assertEqual(b.get("needle_b_clean_wt"), mod.NEEDLE_B_CLEAN_WT)

    def test_ensure_node_modules_symlink(self) -> None:
        import tempfile

        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "main"
            wt = root / "wt"
            src.mkdir()
            wt.mkdir()
            (src / "node_modules").mkdir()
            (src / "node_modules" / ".bin").mkdir()
            action = mod.ensure_node_modules_for_verify(wt, src)
            self.assertEqual(action, "symlinked")
            self.assertTrue((wt / "node_modules").is_symlink())
            self.assertIsNone(mod.ensure_node_modules_for_verify(wt, src))


if __name__ == "__main__":
    unittest.main()
