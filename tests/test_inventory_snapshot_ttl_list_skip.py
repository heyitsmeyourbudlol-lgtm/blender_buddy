"""Regression: inventory_snapshot defers porcelain when ensure TTL fast-path hits."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_worktree as wt  # noqa: E402


class InventorySnapshotTtlListSkipTests(unittest.TestCase):
    def tearDown(self) -> None:
        wt.clear_pool_ensure_fastpath_cache()

    def test_ttl_fastpath_defers_list_worktrees(self) -> None:
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
            with mock.patch.object(wt, "primary_worktree_root", return_value=hub), mock.patch.object(
                wt, "parallel_pool_config", return_value=(".worktrees", "peer")
            ), mock.patch.object(wt.auto, "parallel_peer_floor", return_value=2), mock.patch.object(
                wt.auto, "max_parallel_peers", return_value=8
            ), mock.patch.object(wt, "list_worktrees") as list_wt:
                logs: list[str] = []
                snap = wt.inventory_snapshot(hub, ensure_pool=True, log_fn=logs.append)
            list_wt.assert_not_called()
            self.assertTrue(snap.get("porcelain_deferred"))
            self.assertTrue(snap.get("pool_ready"))
            self.assertEqual(snap.get("parallel_count"), 2)
            self.assertTrue(any("porcelain deferred" in m for m in logs))
            self.assertTrue(any("healthy" in m for m in logs))

    def test_ttl_unhealthy_does_not_defer(self) -> None:
        """Nested pollution must not take porcelain-deferred TTL path."""
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            pool = hub / ".worktrees"
            pool.mkdir(parents=True)
            (hub / ".git").mkdir()
            for i in range(2):
                slot = pool / f"peer-{i}"
                slot.mkdir()
                (slot / ".git").write_text("gitdir: unused\n", encoding="utf-8")
            nest = pool / "peer-0" / ".worktrees" / "peer-x"
            nest.mkdir(parents=True)
            (nest / ".git").write_text("gitdir: unused\n", encoding="utf-8")
            wt.clear_pool_ensure_fastpath_cache()
            wt._pool_ensure_fastpath_at = wt.time.monotonic()
            fake = mock.Mock(path=str(pool / "peer-0"), branch="peer/0", head="abc")
            with mock.patch.object(wt, "primary_worktree_root", return_value=hub), mock.patch.object(
                wt, "parallel_pool_config", return_value=(".worktrees", "peer")
            ), mock.patch.object(wt.auto, "parallel_peer_floor", return_value=2), mock.patch.object(
                wt.auto, "max_parallel_peers", return_value=8
            ), mock.patch.object(
                wt, "list_worktrees", return_value=[fake]
            ) as list_wt, mock.patch.object(
                wt, "prune_nested_pool_pollution", return_value={"found": 1, "removed": [], "failed": []}
            ), mock.patch.object(
                wt,
                "prune_excess_parallel_pool",
                return_value={
                    "found": 0,
                    "removed": [],
                    "failed": [],
                    "orphans_found": 0,
                    "empty_nests_found": 0,
                },
            ), mock.patch.object(
                wt, "ensure_coding_worktree", side_effect=lambda **k: hub / k["rel_path"]
            ), mock.patch.object(wt, "sync_pool_adapt_refuse_null"), mock.patch.object(
                wt, "sync_pool_peer_worktree"
            ), mock.patch.object(wt, "isolate_pool_adapt_namespaces"), mock.patch.object(
                wt, "align_parallel_pool_to_hub"
            ), mock.patch.object(wt, "heal_hub_peer_worktree_sot"), mock.patch.object(
                wt, "parallel_entries", return_value=[fake]
            ), mock.patch.object(wt, "nested_pool_pollution_count", return_value=1):
                snap = wt.inventory_snapshot(hub, ensure_pool=True)
            list_wt.assert_called()
            self.assertFalse(snap.get("porcelain_deferred"))
            self.assertFalse(snap.get("inventory_healthy"))

    def test_cold_ensure_still_lists(self) -> None:
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
            fake = mock.Mock(
                path=str(pool / "peer-0"),
                branch="peer/0",
                head="abc",
            )
            with mock.patch.object(wt, "primary_worktree_root", return_value=hub), mock.patch.object(
                wt, "parallel_pool_config", return_value=(".worktrees", "peer")
            ), mock.patch.object(wt.auto, "parallel_peer_floor", return_value=2), mock.patch.object(
                wt.auto, "max_parallel_peers", return_value=8
            ), mock.patch.object(
                wt, "list_worktrees", return_value=[fake]
            ) as list_wt, mock.patch.object(
                wt, "prune_nested_pool_pollution", return_value={"found": 0, "removed": [], "failed": []}
            ), mock.patch.object(
                wt,
                "prune_excess_parallel_pool",
                return_value={
                    "found": 0,
                    "removed": [],
                    "failed": [],
                    "orphans_found": 0,
                    "empty_nests_found": 0,
                },
            ), mock.patch.object(
                wt, "ensure_coding_worktree", side_effect=lambda **k: hub / k["rel_path"]
            ), mock.patch.object(wt, "sync_pool_adapt_refuse_null"), mock.patch.object(
                wt, "sync_pool_peer_worktree"
            ), mock.patch.object(wt, "isolate_pool_adapt_namespaces"), mock.patch.object(
                wt, "align_parallel_pool_to_hub"
            ), mock.patch.object(wt, "parallel_entries", return_value=[fake]), mock.patch.object(
                wt, "nested_pool_pollution_count", return_value=0
            ):
                snap = wt.inventory_snapshot(hub, ensure_pool=True)
            list_wt.assert_called()
            self.assertFalse(snap.get("porcelain_deferred"))
            self.assertTrue(snap.get("pool_ready"))
            self.assertGreater(wt._pool_ensure_fastpath_at, 0.0)


if __name__ == "__main__":
    unittest.main()
