"""Fail-closed self-check lock contention."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_orchestrate as po  # noqa: E402


class SelfCheckLockFailClosedTests(unittest.TestCase):
    def test_lock_contention_returns_nonzero(self) -> None:
        with mock.patch.object(po, "_try_acquire_self_check_lock", return_value=False):
            rc = po.run_self_check(quick=True)
        self.assertEqual(rc, po.SELF_CHECK_LOCK_BUSY_RC)
        self.assertNotEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
