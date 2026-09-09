"""Oversight stagnation fixes — self-check lock fail-closed + gitfile gcd."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_orchestrate as po  # noqa: E402
import peer_worktree as wt  # noqa: E402


class SelfCheckLockBusyTests(unittest.TestCase):
    def test_run_self_check_lock_busy_nonzero(self) -> None:
        with mock.patch.object(po, "_try_acquire_self_check_lock", return_value=False):
            rc = po.run_self_check(quick=True)
        self.assertEqual(rc, po.SELF_CHECK_LOCK_BUSY_RC)
        self.assertNotEqual(rc, 0)


class GitCommonDirGitfileTests(unittest.TestCase):
    def test_plain_git_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git = root / ".git"
            git.mkdir()
            with mock.patch.object(wt.subprocess, "run") as run:
                common = wt._git_common_dir(root)
            self.assertEqual(common, git.resolve())
            run.assert_not_called()

    def test_worktree_gitfile_commondir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            common_git = hub / ".git"
            wt_git = common_git / "worktrees" / "peer-0"
            wt_git.mkdir(parents=True)
            (wt_git / "commondir").write_text("../.." + chr(10), encoding="utf-8")
            slot = hub / ".worktrees" / "peer-0"
            slot.mkdir(parents=True)
            (slot / ".git").write_text("gitdir: %s" % wt_git + chr(10), encoding="utf-8")
            with mock.patch.object(wt.subprocess, "run") as run:
                common = wt._git_common_dir(slot)
            self.assertEqual(common, common_git.resolve())
            run.assert_not_called()

    def test_missing_git_no_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(wt.subprocess, "run") as run:
                common = wt._git_common_dir(root)
            self.assertIsNone(common)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

