#!/usr/bin/env python3
"""Tests for DGX watch helper."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dgx_watch  # noqa: E402


class TestDgxWatch(unittest.TestCase):
    def test_dgx_primary_default(self) -> None:
        with mock.patch.object(dgx_watch, "_dgx_cfg", return_value={}):
            self.assertTrue(dgx_watch.dgx_primary())

    def test_mac_unittest_cap(self) -> None:
        with mock.patch.object(dgx_watch, "_dgx_cfg", return_value={"mac_unittest_cap": 20}):
            self.assertEqual(dgx_watch.mac_unittest_cap(), 20)

    def test_next_interval_critical(self) -> None:
        sec = dgx_watch.next_interval_sec({"level": "critical"})
        self.assertEqual(sec, 10)

    def test_guard_dgx_ram_ok_skips_heal(self) -> None:
        with mock.patch.object(dgx_watch, "fetch_remote_mem", return_value={"avail_gb": 50, "level": "ok"}):
            out = dgx_watch.guard_dgx_ram(heal=True)
        self.assertEqual(out["action"], "ok")

    def test_guard_dgx_ram_heals_when_low(self) -> None:
        heal_json = '{"avail_gb":5.0,"level":"critical","actions":"restarted_peer_loop"}'
        with mock.patch.object(
            dgx_watch, "fetch_remote_mem", return_value={"avail_gb": 5, "level": "critical"}
        ), mock.patch.object(dgx_watch, "_ssh", return_value=(0, heal_json)):
            out = dgx_watch.guard_dgx_ram(heal=True)
        self.assertEqual(out["action"], "healed")

    def test_rogue_mac_daemons_exclude_hub_peer_improve(self) -> None:
        self.assertIn("com.togi.ram-peer-loop", dgx_watch.ROGUE_MAC_DAEMONS)
        self.assertIn("com.togi.automation-hub-oversight-loop", dgx_watch.ROGUE_MAC_DAEMONS)
        self.assertNotIn("com.togi.automation-hub-peer-loop", dgx_watch.ROGUE_MAC_DAEMONS)
        self.assertNotIn("com.togi.automation-hub-improve-loop", dgx_watch.ROGUE_MAC_DAEMONS)

    def test_rogue_mac_targets_offloaded_includes_peer_improve(self) -> None:
        with mock.patch.object(dgx_watch, "mac_offloaded", return_value=True):
            targets = dgx_watch.rogue_mac_targets()
        self.assertIn("com.togi.automation-peer-loop", targets)
        self.assertIn("com.togi.automation-improve-loop", targets)
        self.assertIn("com.togi.automation-oversight-loop", targets)
        self.assertIn("com.togi.ram-peer-loop", targets)
        # Mac-local dashboard UI stays up even when loops run on CLEAN
        self.assertNotIn("com.togi.automation-hub-dashboard", targets)

    def test_mac_keep_local_includes_dashboard(self) -> None:
        self.assertIn("com.togi.automation-hub-dashboard", dgx_watch.MAC_KEEP_LOCAL)

    def test_rogue_mac_targets_skips_disk_live_hub_oversight(self) -> None:
        import peer_self_heal as heal

        with mock.patch.object(dgx_watch, "mac_offloaded", return_value=False), mock.patch.object(
            heal, "_live_peer_label", return_value="com.togi.automation-hub-peer-loop"
        ), mock.patch.object(
            heal, "_live_improve_label", return_value="com.togi.automation-hub-improve-loop"
        ), mock.patch.object(
            heal, "_live_oversight_label", return_value="com.togi.automation-hub-oversight-loop"
        ):
            targets = dgx_watch.rogue_mac_targets()
        self.assertIn("com.togi.ram-peer-loop", targets)
        self.assertNotIn("com.togi.automation-hub-oversight-loop", targets)

    def test_rogue_mac_targets_boots_hub_oversight_when_live_is_automation(self) -> None:
        import peer_self_heal as heal

        with mock.patch.object(dgx_watch, "mac_offloaded", return_value=False), mock.patch.object(
            heal, "_live_peer_label", return_value="com.togi.automation-peer-loop"
        ), mock.patch.object(
            heal, "_live_improve_label", return_value="com.togi.automation-improve-loop"
        ), mock.patch.object(
            heal, "_live_oversight_label", return_value="com.togi.automation-oversight-loop"
        ):
            targets = dgx_watch.rogue_mac_targets()
        self.assertIn("com.togi.ram-peer-loop", targets)
        self.assertIn("com.togi.automation-hub-oversight-loop", targets)

    def test_stop_mac_daemons_only_targets_rogues(self) -> None:
        calls: list[str] = []

        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["launchctl", "bootout"]:
                calls.append(cmd[2])

            class P:
                returncode = 0
                stdout = ""
                stderr = ""

            return P()

        with mock.patch.object(
            dgx_watch,
            "rogue_mac_targets",
            return_value=("com.togi.ram-peer-loop", "com.togi.automation-hub-oversight-loop"),
        ), mock.patch.object(dgx_watch, "mac_offloaded", return_value=False), mock.patch.object(
            dgx_watch.subprocess, "run", side_effect=fake_run
        ):
            stopped = dgx_watch.stop_mac_daemons()
        self.assertEqual(
            stopped,
            ["com.togi.ram-peer-loop", "com.togi.automation-hub-oversight-loop"],
        )
        self.assertTrue(any("ram-peer-loop" in c for c in calls))
        self.assertTrue(any("hub-oversight-loop" in c for c in calls))
        self.assertFalse(any("automation-hub-peer-loop" in c for c in calls))

    def test_stop_mac_daemons_no_hardcoded_users_path(self) -> None:
        """OVERSEER_NO_HARDCODED_CURSOR_AGENT_PATH_2026_09_05 — portable pkill pats."""
        src = Path(dgx_watch.__file__).read_text(encoding="utf-8")
        self.assertNotIn("/Users/togi/.local/bin/cursor-agent", src)
        self.assertIn('"cursor-agent"', src)

    def test_remote_ram_guard_restart_cooldown_and_rc(self) -> None:
        """OVERSEER_DGX_WATCH_RESTART_COOLDOWN_2026_09_06 — no false-success thrash."""
        guard = dgx_watch._REMOTE_RAM_GUARD
        self.assertIn("PEER_RESTART_COOLDOWN_SEC", guard)
        self.assertIn("skip_restart_cooldown", guard)
        self.assertIn("trim_before_restart", guard)
        self.assertIn("restart_peer_failed", guard)
        self.assertIn("peer-loop-ram-restart.ts", guard)
        # Must not mark success after `systemctl … || true`.
        self.assertNotRegex(
            guard,
            r"systemctl --user restart peer-loop\.service 2>/dev/null \|\| true\s*\n\s*restarted_peer=1",
        )
        self.assertIn(
            "if systemctl --user restart peer-loop.service 2>/dev/null; then",
            guard,
        )
        self.assertIn("PEER_RESTART_COOLDOWN_SEC=", Path(dgx_watch.__file__).read_text())


if __name__ == "__main__":
    unittest.main()
