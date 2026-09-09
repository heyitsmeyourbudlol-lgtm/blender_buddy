"""Regression: ensure_parallel_pool TTL fast-path skips porcelain when floor ready."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_worktree as wt  # noqa: E402


class EnsureParallelPoolFastpathTests(unittest.TestCase):
    def tearDown(self) -> None:
        wt.clear_pool_ensure_fastpath_cache()

    def test_ttl_fastpath_skips_porcelain_when_floor_ready(self) -> None:
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
            ), mock.patch.object(
                wt, "list_worktrees", return_value=[]
            ) as list_wt, mock.patch.object(
                wt, "prune_nested_pool_pollution"
            ) as prune_n, mock.patch.object(wt, "prune_excess_parallel_pool") as prune_e, mock.patch.object(
                wt, "align_parallel_pool_to_hub"
            ) as align, mock.patch.object(
                wt, "sync_pool_adapt_refuse_null"
            ), mock.patch.object(wt, "sync_pool_peer_worktree"), mock.patch.object(
                wt, "isolate_pool_adapt_namespaces"
            ), mock.patch.object(wt, "parallel_entries", return_value=[]):
                logs: list[str] = []
                paths = wt.ensure_parallel_pool(count=2, log_fn=logs.append)
            # Floor prune still skipped; extras path may list once.
            prune_n.assert_not_called()
            prune_e.assert_not_called()
            align.assert_not_called()  # no extras
            self.assertEqual(len(paths), 2)
            self.assertTrue(any("fast-path TTL" in m for m in logs))
            self.assertTrue(any("floor+healthy" in m for m in logs))
            self.assertTrue(any("extras aligned=0" in m for m in logs))
            list_wt.assert_called()  # extras discovery still runs

    def test_ttl_fastpath_refuses_when_excess_dir(self) -> None:
        """OVERSEER_POOL_TTL_HEALTHY_INV_2026_09_06 — excess peer-N aborts TTL skip."""
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            pool = hub / ".worktrees"
            pool.mkdir(parents=True)
            (hub / ".git").mkdir()
            for i in range(2):
                slot = pool / f"peer-{i}"
                slot.mkdir()
                (slot / ".git").write_text("gitdir: unused\n", encoding="utf-8")
            # Excess beyond cap=8
            excess = pool / "peer-99"
            excess.mkdir()
            (excess / ".git").write_text("gitdir: unused\n", encoding="utf-8")
            wt.clear_pool_ensure_fastpath_cache()
            wt._pool_ensure_fastpath_at = wt.time.monotonic()
            with mock.patch.object(wt, "primary_worktree_root", return_value=hub), mock.patch.object(
                wt, "parallel_pool_config", return_value=(".worktrees", "peer")
            ), mock.patch.object(wt.auto, "parallel_peer_floor", return_value=2), mock.patch.object(
                wt.auto, "max_parallel_peers", return_value=8
            ), mock.patch.object(
                wt, "list_worktrees", return_value=[]
            ), mock.patch.object(
                wt, "prune_nested_pool_pollution", return_value={"found": 0, "removed": [], "failed": []}
            ) as prune_n, mock.patch.object(
                wt,
                "prune_excess_parallel_pool",
                return_value={
                    "found": 1,
                    "removed": [],
                    "failed": [],
                    "orphans_found": 0,
                    "empty_nests_found": 0,
                },
            ) as prune_e, mock.patch.object(
                wt, "ensure_coding_worktree", side_effect=lambda **k: hub / k["rel_path"]
            ), mock.patch.object(wt, "sync_pool_adapt_refuse_null"), mock.patch.object(
                wt, "sync_pool_peer_worktree"
            ), mock.patch.object(wt, "isolate_pool_adapt_namespaces"), mock.patch.object(
                wt, "align_parallel_pool_to_hub"
            ), mock.patch.object(wt, "heal_hub_peer_worktree_sot"), mock.patch.object(
                wt, "parallel_entries", return_value=[]
            ):
                logs: list[str] = []
                paths = wt.ensure_parallel_pool(count=2, log_fn=logs.append)
            # Must fall through to full ensure (prune called).
            prune_n.assert_called()
            prune_e.assert_called()
            self.assertEqual(len(paths), 2)
            self.assertFalse(any("floor+healthy" in m for m in logs))

    def test_ttl_fastpath_aligns_extras_when_floor_dirs_exist(self) -> None:
        """OVERSEER_ENSURE_POOL_ALIGN_EXTRAS_FLOOR_READY_2026_09_04.

        Floor dirs already exist (TTL ready) must still align peer-coding extras.
        """
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp) / "hub"
            pool = hub / ".worktrees"
            pool.mkdir(parents=True)
            (hub / ".git").mkdir()
            for i in range(2):
                slot = pool / f"peer-{i}"
                slot.mkdir()
                (slot / ".git").write_text("gitdir: unused\n", encoding="utf-8")
            coding = pool / "peer-coding"
            coding.mkdir()
            (coding / ".git").write_text("gitdir: unused\n", encoding="utf-8")
            entries = [
                wt.WorktreeEntry(path=str(hub), head="hubtip", branch="main"),
                wt.WorktreeEntry(path=str(pool / "peer-0"), head="a", branch="peer/0"),
                wt.WorktreeEntry(path=str(pool / "peer-1"), head="b", branch="peer/1"),
                wt.WorktreeEntry(path=str(coding), head="stale", branch="peer/coding"),
            ]
            align_batches: list[list[str]] = []

            def fake_align(paths, **kwargs):  # type: ignore[no-untyped-def]
                align_batches.append([Path(p).name for p in paths])
                return {"aligned": [Path(p).name for p in paths], "skipped_dirty": [], "skipped_other": []}

            wt.clear_pool_ensure_fastpath_cache()
            wt._pool_ensure_fastpath_at = wt.time.monotonic()
            with mock.patch.object(wt, "primary_worktree_root", return_value=hub), mock.patch.object(
                wt, "parallel_pool_config", return_value=(".worktrees", "peer")
            ), mock.patch.object(wt.auto, "parallel_peer_floor", return_value=2), mock.patch.object(
                wt.auto, "max_parallel_peers", return_value=8
            ), mock.patch.object(wt, "list_worktrees", return_value=entries), mock.patch.object(
                wt, "prune_nested_pool_pollution"
            ) as prune_n, mock.patch.object(
                wt, "prune_excess_parallel_pool"
            ) as prune_e, mock.patch.object(
                wt, "align_parallel_pool_to_hub", side_effect=fake_align
            ), mock.patch.object(
                wt, "isolate_pool_adapt_namespaces", return_value=[]
            ), mock.patch.object(
                wt, "sync_pool_adapt_refuse_null", return_value=[]
            ), mock.patch.object(wt, "sync_pool_peer_worktree", return_value=[]):
                logs: list[str] = []
                paths = wt.ensure_parallel_pool(count=2, log_fn=logs.append)
            prune_n.assert_not_called()
            prune_e.assert_not_called()
            self.assertEqual(len(paths), 2)
            self.assertTrue(any("peer-coding" in b for b in align_batches))
            # Floor slots must NOT be in the extras align batch on fast-path.
            extras = next(b for b in align_batches if "peer-coding" in b)
            self.assertNotIn("peer-0", extras)
            self.assertNotIn("peer-1", extras)
            self.assertTrue(any("extras aligned=1" in m for m in logs))

    def test_force_bypasses_fastpath(self) -> None:
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
            ), mock.patch.object(
                wt, "list_worktrees", return_value=[]
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
            ), mock.patch.object(wt, "parallel_entries", return_value=[]):
                paths = wt.ensure_parallel_pool(count=2, force=True, log_fn=lambda _m: None)
            list_wt.assert_called()
            self.assertEqual(len(paths), 2)


if __name__ == "__main__":
    unittest.main()
