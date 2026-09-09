"""OVERSEER_PEER_LINUX_INSTALL_2026_09_04 — peer install/uninstall on Linux."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_loop as pl  # noqa: E402


class PeerLinuxInstallTests(unittest.TestCase):
    def test_needle_present(self) -> None:
        src = Path(pl.__file__).read_text(encoding="utf-8")
        self.assertIn("OVERSEER_PEER_LINUX_INSTALL_2026_09_04", src)
        self.assertIn('linux_install_daemon("peer")', src)
        self.assertIn('linux_uninstall_daemon("peer")', src)

    def test_cmd_install_linux_calls_linux_install_daemon(self) -> None:
        import peer_self_heal as heal

        with mock.patch.object(pl.sys, "platform", "linux"):
            with mock.patch.object(heal, "linux_install_daemon", return_value="unit ok") as inst:
                with mock.patch.object(pl.subprocess, "run") as run:
                    rc = pl._cmd_install_body(install_mode="background")
        self.assertEqual(rc, 0)
        inst.assert_called_once_with("peer")
        run.assert_not_called()

    def test_cmd_uninstall_linux_calls_linux_uninstall_daemon(self) -> None:
        import peer_self_heal as heal

        with mock.patch.object(pl.sys, "platform", "linux"):
            with mock.patch.object(heal, "linux_uninstall_daemon", return_value="gone") as un:
                with mock.patch.object(pl.subprocess, "run") as run:
                    rc = pl.cmd_uninstall()
        self.assertEqual(rc, 0)
        un.assert_called_once_with("peer")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
