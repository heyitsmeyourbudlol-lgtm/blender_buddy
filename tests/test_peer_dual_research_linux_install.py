#!/usr/bin/env python3
"""OVERSEER_DUAL_RESEARCH_LINUX_INSTALL_2026_09_06 — no launchctl on Linux."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_dual_research as dr  # noqa: E402


class DualResearchLinuxInstallTests(unittest.TestCase):
    def test_cmd_install_linux_calls_linux_install_daemon(self) -> None:
        import peer_self_heal as heal

        with mock.patch.object(dr.sys, "platform", "linux"):
            with mock.patch.object(heal, "ensure_canonical_module"):
                with mock.patch.object(
                    heal, "linux_install_daemon", return_value="unit ok"
                ) as inst:
                    with mock.patch.object(dr.subprocess, "run") as run:
                        rc = dr.cmd_install()
        self.assertEqual(rc, 0)
        inst.assert_called_once_with("dual-research")
        run.assert_not_called()

    def test_cmd_uninstall_linux_calls_linux_uninstall_daemon(self) -> None:
        import peer_self_heal as heal

        with mock.patch.object(dr.sys, "platform", "linux"):
            with mock.patch.object(heal, "ensure_canonical_module"):
                with mock.patch.object(
                    heal, "linux_uninstall_daemon", return_value="gone"
                ) as un:
                    with mock.patch.object(dr.subprocess, "run") as run:
                        rc = dr.cmd_uninstall()
        self.assertEqual(rc, 0)
        un.assert_called_once_with("dual-research")
        run.assert_not_called()

    def test_cmd_status_linux_uses_systemd(self) -> None:
        import peer_self_heal as heal

        with mock.patch.object(dr.sys, "platform", "linux"):
            with mock.patch.object(heal, "_systemd_user_active", return_value=True):
                with mock.patch.object(dr, "_load_state", return_value={}):
                    with mock.patch.object(dr.subprocess, "run") as run:
                        rc = dr.cmd_status()
        self.assertEqual(rc, 0)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
