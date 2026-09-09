#!/usr/bin/env python3
"""Tests for remote agent dispatch (DGX Spark / SSH offload)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import peer_remote


class TestPeerRemote(unittest.TestCase):
    def test_translate_path_under_home(self) -> None:
        with mock.patch.object(peer_remote, "local_root", return_value=Path("/Users/togi")):
            with mock.patch.object(peer_remote, "remote_root", return_value="/home/arnavrastogi"):
                out = peer_remote.translate_path(Path("/Users/togi/Automation/.worktrees/peer-0"))
        self.assertEqual(out, "/home/arnavrastogi/Automation/.worktrees/peer-0")

    def test_translate_text_rewrites_prefix(self) -> None:
        with mock.patch.object(peer_remote, "local_root", return_value=Path("/Users/togi")):
            with mock.patch.object(peer_remote, "remote_root", return_value="/home/arnavrastogi"):
                text = peer_remote.translate_text("Work in /Users/togi/Automation only")
        self.assertIn("/home/arnavrastogi/Automation", text)
        self.assertNotIn("/Users/togi/Automation", text)

    def test_remote_enabled_respects_local_override(self) -> None:
        with mock.patch.dict("os.environ", {"PEER_AGENT_LOCAL": "1"}, clear=False):
            with mock.patch.object(peer_remote, "_cfg", return_value={"enabled": True, "ssh_host": "CLEAN"}):
                self.assertFalse(peer_remote.remote_enabled())

    def test_remote_enabled_requires_host(self) -> None:
        with mock.patch.object(peer_remote.auto, "CFG", {"agent_remote": {"enabled": True, "ssh_host": ""}, "dgx_host": {"primary": False}}):
            self.assertFalse(peer_remote.remote_enabled())

    def test_background_sync_false_does_not_wait_on_agent(self) -> None:
        """sync=False must return after launch, not block on cursor-agent."""
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)])
            # Simulate ssh returning a remote pid quickly.
            return mock.Mock(returncode=0, stdout="4242\n", stderr="")

        with (
            mock.patch.object(peer_remote, "remote_auth_ready", return_value=(True, "ok")),
            mock.patch.object(peer_remote, "translate_path", return_value="/home/x/CaaS"),
            mock.patch.object(peer_remote, "translate_text", side_effect=lambda t: t),
            mock.patch.object(peer_remote, "sync_project", return_value=True),
            # Product-cwd rsync is separate from agent wait; do not count it as blocking.
            mock.patch.object(peer_remote, "_rsync_to_remote", return_value=True),
            mock.patch.object(peer_remote, "_cfg", return_value={"sync_before_dispatch": True, "sync_after_dispatch": True}),
            mock.patch.object(peer_remote, "_ssh_base", return_value=["ssh", "CLEAN"]),
            mock.patch.object(peer_remote, "remote_agent_bin", return_value="cursor-agent"),
            mock.patch.object(peer_remote, "remote_config_namespace", return_value="automation"),
            mock.patch.object(peer_remote.subprocess, "run", side_effect=fake_run),
            mock.patch("peer_terminal.write_prompt_file"),
        ):
            rc, auth = peer_remote.run_remote_cursor_agent(
                "do work",
                log_fn=lambda _m: None,
                timeout_sec=7200.0,
                paid_api=False,
                cwd=Path("/Users/togi/CaaS"),
                sync=False,
            )
        self.assertEqual(rc, 0)
        self.assertFalse(auth)
        self.assertEqual(len(calls), 1)
        remote_script = calls[0][-1]
        self.assertIn("nohup", remote_script)
        self.assertNotIn("set -e; export PATH", remote_script[:20])  # background path

    def test_hub_protect_pull_excludes_queue_twin_and_oversight(self) -> None:
        ex = peer_remote.HUB_PROTECT_PULL_EXCLUDES
        self.assertIn("notes/WORK_QUEUE.md", ex)
        self.assertIn("notes/SYSTEM_OVERSIGHT.md", ex)
        self.assertIn("notes/REPO_FLAW_RESEARCH.md", ex)
        self.assertIn("scripts/self_improve_context.md", ex)
        self.assertIn("scripts/peer_oversight.py", ex)
        self.assertIn("scripts/peer_remote.py", ex)
        self.assertIn("scripts/dgx_utilization.py", ex)
        # Legal: Mac rsync must not reintroduce privacy-bad kit export tars
        self.assertIn("dist/automation-kit-*.tar.gz", ex)
        # OVERSEER_HUB_PROTECT_BITNET_FACTCHECK_2026_09_05
        self.assertIn("notes/BITNET_FACTCHECK.md", ex)
        self.assertIn("notes/NVFP4_LOCK_APPLICABILITY.md", ex)

    def test_rsync_push_applies_hub_protect_excludes(self) -> None:
        """OVERSEER_HUB_PROTECT_PUSH — push must not --delete protected needles."""
        logs: list[str] = []
        with mock.patch.object(peer_remote, "rsync_excludes", return_value=()), mock.patch.object(
            peer_remote, "ssh_host", return_value="fake-host"
        ), mock.patch.object(peer_remote.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            ok = peer_remote._rsync_to_remote(
                Path("/tmp/hub"), "/remote/hub", log_fn=logs.append
            )
        self.assertTrue(ok)
        self.assertTrue(any("rsync → hub-protect excludes=" in m for m in logs))
        cmd = run.call_args[0][0]
        self.assertIn("--exclude", cmd)
        self.assertIn("notes/WORK_QUEUE.md", cmd)


    def test_dgx_setup_excludes_cover_hub_protect(self) -> None:
        """OVERSEER_HUB_PROTECT_DGX_SETUP_2026_09_04 — Mac push must not --delete vault needles."""
        import re
        from pathlib import Path
        setup = (Path(__file__).resolve().parents[1] / "scripts" / "dgx_setup.sh").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_HUB_PROTECT_DGX_SETUP_2026_09_04", setup)
        flat = {a or b for a, b in re.findall(r"--exclude\s+'([^']+)'|--exclude\s+(\S+)", setup)}
        missing = []
        for rel in peer_remote.HUB_PROTECT_PULL_EXCLUDES:
            if rel in flat:
                continue
            # glob cover for tests/test_peer_*.py
            if rel.startswith("tests/test_peer_") and "tests/test_peer_*.py" in flat:
                continue
            missing.append(rel)
        self.assertEqual(missing, [], f"dgx_setup missing excludes: {missing}")


if __name__ == "__main__":
    unittest.main()
