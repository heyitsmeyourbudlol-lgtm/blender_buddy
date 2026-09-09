"""Regression: TTL-skip emit defers porcelain list_worktrees."""

from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


class EmitInventoryTtlListSkipTests(unittest.TestCase):
    def test_ttl_skip_does_not_call_list_worktrees(self) -> None:
        import peer_loop

        peer_loop.clear_emit_ensure_cache()
        peer_loop._emit_ensure_at = peer_loop.time.monotonic()
        with unittest.mock.patch.object(
            peer_loop, "_should_skip_emit_ensure", return_value=True
        ), unittest.mock.patch.object(
            peer_loop.peer_worktree, "ensure_parallel_pool"
        ) as ensure, unittest.mock.patch.object(
            peer_loop.peer_worktree, "list_worktrees"
        ) as list_wt, unittest.mock.patch(
            "peer_roles.worker_pool_size", return_value=8
        ):
            logs: list[str] = []
            peer_loop._emit_worktree_inventory(logs.append)
        ensure.assert_not_called()
        list_wt.assert_not_called()
        self.assertTrue(any("porcelain list deferred" in m for m in logs))
        self.assertTrue(any("8 parallel floor ready" in m for m in logs))

    def test_cold_ensure_still_lists(self) -> None:
        import peer_loop

        peer_loop.clear_emit_ensure_cache()
        fake_entry = unittest.mock.Mock(
            path="/tmp/peer-0",
            branch="peer/0",
            detached=False,
            head="abc1234",
        )
        with unittest.mock.patch.object(
            peer_loop, "_should_skip_emit_ensure", return_value=False
        ), unittest.mock.patch.object(
            peer_loop.peer_worktree,
            "ensure_parallel_pool",
            return_value=[Path(f"/tmp/peer-{i}") for i in range(8)],
        ) as ensure, unittest.mock.patch.object(
            peer_loop.peer_worktree,
            "list_worktrees",
            return_value=[fake_entry],
        ) as list_wt, unittest.mock.patch.object(
            peer_loop.peer_worktree,
            "parallel_entries",
            return_value=[fake_entry],
        ), unittest.mock.patch(
            "peer_roles.worker_pool_size", return_value=8
        ):
            logs: list[str] = []
            peer_loop._emit_worktree_inventory(logs.append)
        ensure.assert_called_once()
        list_wt.assert_called_once()
        self.assertTrue(any("registered" in m for m in logs))
        self.assertGreater(peer_loop._emit_ensure_at, 0.0)


if __name__ == "__main__":
    unittest.main()
