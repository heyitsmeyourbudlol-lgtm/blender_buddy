#!/usr/bin/env python3
"""Tests for peer_oversight."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_oversight as po  # noqa: E402


class TestPeerOversight(unittest.TestCase):
    def test_enabled_default(self) -> None:
        with mock.patch.object(po.cfg_mod, "CFG", {"oversight_enabled": True}):
            self.assertTrue(po.oversight_enabled())

    def test_build_digest_has_health(self) -> None:
        ctx = {
            "ts": "2026-01-01",
            "phase": "IDLE",
            "phase_detail": "ok",
            "queue_count": 5,
            "queue_source": "launch",
            "bottlenecks": [],
            "kit": {"daemons": {"peer_loop": True, "improve_loop": True}},
        }
        md = po.build_oversight_digest(
            ctx,
            flaws={"open": 2, "critical": 0, "high": 1, "top": ["[high] x"]},
            actions=["probe ok"],
            dispatched=False,
        )
        self.assertIn("System oversight", md)
        self.assertIn("Cursor agent notes", md)

    def test_build_digest_skips_leaked_digest_link_notes(self) -> None:
        ctx = {
            "ts": "2026-01-01",
            "phase": "WORKING",
            "phase_detail": "dirty",
            "queue_count": 2,
            "queue_source": "launch",
            "bottlenecks": [],
            "kit": {"daemons": {"peer_loop": True, "improve_loop": True}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            digest = Path(tmp) / "SYSTEM_OVERSIGHT.md"
            digest.write_text(
                "\n".join(
                    [
                        "## Cursor agent notes",
                        "",
                        "- **2026-01-01 oversight**",
                        "  - **Found:** ok",
                        "- Automation: `/tmp/notes/AUTOMATION_DIGEST.md`",
                        "- Repo flaws: `/tmp/notes/REPO_FLAW_RESEARCH.md`",
                        "",
                        "## Linked digests",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with mock.patch.object(po, "digest_path", return_value=digest):
                md = po.build_oversight_digest(
                    ctx,
                    flaws={"open": 0, "critical": 0, "high": 0, "top": [], "digest": "notes/REPO_FLAW_RESEARCH.md"},
                    actions=[],
                    dispatched=False,
                )
        notes = md.split("## Cursor agent notes", 1)[1].split("## Linked digests", 1)[0]
        self.assertIn("**2026-01-01 oversight**", notes)
        self.assertIn("**Found:** ok", notes)
        self.assertNotIn("AUTOMATION_DIGEST.md", notes)
        self.assertNotIn("REPO_FLAW_RESEARCH.md", notes)

    def test_agent_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            with mock.patch.object(po, "STATE_PATH", state_path):
                with mock.patch.object(po, "agent_interval_sec", return_value=900.0):
                    self.assertEqual(po.agent_cooldown_remaining(), 0.0)

    def test_run_cycle_digest_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            digest = Path(tmp) / "SYSTEM_OVERSIGHT.md"
            state = Path(tmp) / "state.json"
            with mock.patch.object(po, "digest_path", return_value=digest):
                with mock.patch.object(po, "STATE_PATH", state):
                    with mock.patch.object(po, "oversight_enabled", return_value=True):
                        with mock.patch.object(po, "_ensure_core_daemons", return_value=[]):
                            with mock.patch.object(po.self_heal, "run_cycle") as heal:
                                heal.return_value = mock.Mock(actions=[])
                                with mock.patch.object(po.investigate, "collect_context", return_value={"kit": {}, "bottlenecks": [], "last_cycle": {}}):
                                    with mock.patch.object(po.investigate, "write_digest"):
                                        with mock.patch.object(po, "_repo_flaw_summary", return_value={"open": 0, "top": []}):
                                            result = po.run_oversight_cycle(digest_only=True)
            self.assertIn("digest", result)
            self.assertTrue(digest.is_file())

    def test_disk_oversight_identity_uses_live_namespace(self) -> None:
        with mock.patch.object(
            po.cfg_mod, "load_config", return_value={"config_namespace": "automation"}
        ):
            ns, label, plist, log = po._disk_oversight_identity()
        self.assertEqual(ns, "automation")
        self.assertEqual(label, "com.togi.automation-oversight-loop")
        self.assertTrue(str(plist).endswith("com.togi.automation-oversight-loop.plist"))
        self.assertTrue(str(log).endswith("oversight-loop.log"))
        self.assertIn("/.config/automation/", str(log).replace("\\", "/"))

    def test_disk_oversight_identity_hub_namespace(self) -> None:
        with mock.patch.object(
            po.cfg_mod, "load_config", return_value={"config_namespace": "automation-hub"}
        ):
            ns, label, _plist, _log = po._disk_oversight_identity()
        self.assertEqual(ns, "automation-hub")
        self.assertEqual(label, "com.togi.automation-hub-oversight-loop")



class TestOverseerFanoutCap(unittest.TestCase):
    """OVERSEER_FANOUT_CAP_2026_09_03 — hard cap concurrent System Overseers."""

    def test_cmdline_matches_role_and_h1(self) -> None:
        pathish = (
            "/home/x/.cursor-server/.../cursor-agent-worker/.../cursor-agent "
            "-p # System overseer — event-triggered stagnation dispatch "
            "You are the **System Overseer** for Automation"
        )
        self.assertTrue(po._cmdline_is_overseer(pathish))

    def test_cmdline_rejects_worker_server_token(self) -> None:
        cmd = "cursor-agent worker-server --port 1 System Overseer"
        self.assertFalse(po._cmdline_is_overseer(cmd))

    def test_fanout_blocked_when_count_at_max(self) -> None:
        with mock.patch.object(po, "_overseer_running_count", return_value=1):
            with mock.patch.object(po, "OVERSEER_FANOUT_MAX", 1):
                self.assertTrue(po._overseer_fanout_blocked())

    def test_fanout_allows_when_zero(self) -> None:
        with mock.patch.object(po, "_overseer_running_count", return_value=0):
            self.assertFalse(po._overseer_fanout_blocked())



class TestLinuxOversightStatus(unittest.TestCase):
    """OVERSEER_LINUX_OVERSIGHT_STATUS_2026_09_04 — no launchctl on Linux."""

    def test_cmd_status_uses_systemd_on_linux(self) -> None:
        self.assertIn("OVERSEER_LINUX_OVERSIGHT_STATUS_2026_09_04", Path(po.__file__).read_text())
        import peer_self_heal as heal

        with mock.patch.object(po.sys, "platform", "linux"):
            with mock.patch.object(
                po,
                "_disk_oversight_identity",
                return_value=(
                    "automation-hub",
                    "com.togi.automation-hub-oversight-loop",
                    Path("/tmp/x.plist"),
                    Path("/tmp/x.log"),
                ),
            ):
                with mock.patch.object(po, "_load_state", return_value={}):
                    with mock.patch.object(po, "oversight_enabled", return_value=True):
                        with mock.patch.object(po, "agent_cooldown_remaining", return_value=0.0):
                            with mock.patch.object(heal, "_systemd_user_active", return_value=True):
                                with mock.patch.object(po.subprocess, "run") as run:
                                    rc = po.cmd_status()
        self.assertEqual(rc, 0)
        for call in run.call_args_list:
            args = call[0][0] if call[0] else []
            self.assertNotEqual(args[:1], ["launchctl"])

    def test_cmd_install_linux_calls_linux_install_daemon(self) -> None:
        import peer_self_heal as heal

        with mock.patch.object(po.sys, "platform", "linux"):
            with mock.patch.object(
                po,
                "_disk_oversight_identity",
                return_value=(
                    "automation-hub",
                    "com.togi.automation-hub-oversight-loop",
                    Path("/tmp/x.plist"),
                    Path("/tmp/x.log"),
                ),
            ):
                with mock.patch.object(heal, "linux_install_daemon", return_value="unit ok") as inst:
                    with mock.patch.object(po.subprocess, "run") as run:
                        rc = po.cmd_install()
        self.assertEqual(rc, 0)
        inst.assert_called_once_with("oversight")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

class TestOverseerFanoutFlockWire(unittest.TestCase):
    """OVERSEER_FANOUT_FLOCK_WIRE_TEST_2026_09_04 — flock must gate spawn."""

    def test_trim_and_lock_helpers_exist(self) -> None:
        self.assertTrue(callable(po.trim_excess_overseers))
        self.assertTrue(callable(po._try_overseer_dispatch_lock))
        self.assertTrue(callable(po._overseer_pids))
        src = Path(po.__file__).read_text(encoding="utf-8")
        self.assertIn("OVERSEER_FANOUT_FLOCK_WIRE_2026_09_04", src)
        self.assertGreaterEqual(src.count("_try_overseer_dispatch_lock("), 2)

    def test_trim_noop_when_under_cap(self) -> None:
        with mock.patch.object(po, "_overseer_pids", return_value=[111]):
            with mock.patch.object(po, "OVERSEER_FANOUT_MAX", 1):
                msg = po.trim_excess_overseers(keep=1, protect={111})
        self.assertIn("fanout ok", msg)
