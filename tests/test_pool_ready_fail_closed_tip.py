"""Fail-closed pool_ready when readable HEADs skew vs hub tip."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_worktree as wt  # noqa: E402


class PoolReadyFailClosedTipTests(unittest.TestCase):
    def tearDown(self) -> None:
        wt.clear_pool_ensure_fastpath_cache()

    def test_skew_report_unchecked_when_heads_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            slot = Path(tmp) / "peer-0"
            hub.mkdir()
            slot.mkdir()
            rep = wt.pool_tip_skew_report([slot], hub=hub)
            self.assertFalse(rep.get("checked"))
            self.assertEqual(rep.get("skew"), 0)

    def test_inventory_fastpath_pool_ready_false_on_skew(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            pool = hub / ".worktrees"
            pool.mkdir(parents=True)
            (hub / ".git").mkdir()
            for i in range(2):
                slot = pool / f"peer-{i}"
                slot.mkdir()
                (slot / ".git").write_text("gitdir: unused\n", encoding="utf-8")
            wt.clear_pool_ensure_fastpath_cache()
            wt._pool_ensure_fastpath_at = wt.time.monotonic()
            skew = {
                "tip": "aaa",
                "matched": 0,
                "skew": 2,
                "unknown": 0,
                "checked": True,
            }
            with mock.patch.object(wt, "primary_worktree_root", return_value=hub), mock.patch.object(
                wt, "parallel_pool_config", return_value=(".worktrees", "peer")
            ), mock.patch.object(wt.auto, "parallel_peer_floor", return_value=2), mock.patch.object(
                wt.auto, "max_parallel_peers", return_value=8
            ), mock.patch.object(wt, "pool_tip_skew_report", return_value=skew), mock.patch.object(
                wt, "list_worktrees"
            ) as list_wt:
                snap = wt.inventory_snapshot(hub, ensure_pool=True)
            list_wt.assert_not_called()
            self.assertTrue(snap.get("porcelain_deferred"))
            self.assertFalse(snap.get("pool_ready"))
            self.assertEqual(snap.get("pool_tip_skew", {}).get("skew"), 2)


if __name__ == "__main__":
    unittest.main()
