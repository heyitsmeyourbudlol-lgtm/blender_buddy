#!/usr/bin/env python3
"""Tests for peer_product_forge — autonomous product mode."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_product_forge as forge  # noqa: E402


class TestPeerProductForge(unittest.TestCase):
    def test_slug(self) -> None:
        self.assertEqual(forge._slug("Newdrop MVP!"), "newdrop-mvp")

    def test_build_prompt_contains_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / "notes").mkdir()
            (target / "notes" / "WORK_QUEUE.md").write_text("## Active\n- [ ] **[forge] test**\n")
            prompt = forge.build_forge_prompt(brief="Ship widget", target=target, profile="caas")
            self.assertIn("Ship widget", prompt)
            self.assertIn("[forge]", prompt)
            self.assertIn("vibe-ship", prompt)

    def test_seed_target_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            slices = forge.seed_target_queue(target, brief="Demo app", profile="node")
            self.assertGreaterEqual(len(slices), 3)
            wq = target / "notes" / "WORK_QUEUE.md"
            self.assertTrue(wq.is_file())
            text = wq.read_text(encoding="utf-8")
            self.assertIn("[forge]", text)

    def test_start_and_stop_forge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            target = Path(tmp) / "app"
            target.mkdir()
            with mock.patch.object(forge, "STATE_PATH", state):
                with mock.patch.object(forge, "bootstrap_repo", return_value=["ok"]):
                    with mock.patch.object(forge, "_hub_enqueue_forge"):
                        with mock.patch("automation_improve.wake_peer"):
                            with mock.patch.object(forge, "scrub_orphan_forge_agents", return_value=0):
                                report = forge.start_forge(
                                    brief="Test app",
                                    path=str(target),
                                    bootstrap=False,
                                )
                                self.assertTrue(report.get("active"))
                                self.assertTrue(forge.forge_active())
                                forge.stop_forge()
                                self.assertFalse(forge.forge_active())

    def test_scrub_orphan_forge_when_inactive(self) -> None:
        """OVERSEER_SCRUB_ORPHAN_FORGE_2026_09_04"""
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            target = Path(tmp) / "app"
            target.mkdir()
            state.write_text('{"active": false}\n')
            fake = mock.Mock(pid=424242)
            with mock.patch.object(forge, "STATE_PATH", state), mock.patch(
                "peer_parallel_dispatch.find_agent_procs", return_value=[fake]
            ), mock.patch(
                "peer_parallel_dispatch._proc_cwd", return_value=target
            ), mock.patch("os.kill") as kill:
                n = forge.scrub_orphan_forge_agents(target=target)
            self.assertEqual(n, 1)
            kill.assert_called_once()

    def test_dispatch_uses_remaining_slots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            target = Path(tmp) / "app"
            target.mkdir()
            state.write_text(
                '{"active": true, "brief": "x", "target_path": "%s", "profile": "caas"}'
                % target
            )
            with mock.patch.object(forge, "STATE_PATH", state), mock.patch.object(
                forge, "max_forge_agents", return_value=4
            ), mock.patch(
                "peer_parallel_dispatch.count_agents_under", return_value=3
            ), mock.patch(
                "dgx_ram_budget.dispatch_allowed", return_value=True
            ), mock.patch(
                "peer_terminal.desktop_auth_ready", return_value=(True, "ok")
            ), mock.patch(
                "peer_terminal.run_cursor_agent", return_value=(0, False)
            ) as run:
                report = forge.dispatch_forge_agents()
            self.assertEqual(report.get("launched"), 1)  # remaining=1
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
