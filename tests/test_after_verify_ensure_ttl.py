"""Regression: _after_verify_ok skips ensure_parallel_pool when emit TTL healthy."""

from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


class AfterVerifyEnsureTtlTests(unittest.TestCase):
    def test_skips_ensure_when_emit_ttl_ready(self) -> None:
        import peer_loop

        peer_loop.clear_emit_ensure_cache()
        # Pretend continuous emit just ensured a healthy floor.
        peer_loop._emit_ensure_at = peer_loop.time.monotonic()
        with unittest.mock.patch.object(
            peer_loop.auto, "check_off_resolved_self_heal", return_value=[]
        ), unittest.mock.patch.object(
            peer_loop.auto, "dedupe_work_queue_files"
        ), unittest.mock.patch.object(
            peer_loop, "maybe_auto_commit_after_verify"
        ), unittest.mock.patch.object(
            peer_loop, "_mechanical_post_cycle"
        ), unittest.mock.patch.object(
            peer_loop.auto,
            "measure_live_state",
            return_value=unittest.mock.Mock(
                git_clean=True, tests_ok=True, git_detail="ok", tests_detail="ok"
            ),
        ), unittest.mock.patch.object(
            peer_loop, "metrics_green", return_value=True
        ), unittest.mock.patch.object(
            peer_loop, "_emit_automation_event"
        ), unittest.mock.patch.object(
            peer_loop, "_should_skip_emit_ensure", return_value=True
        ), unittest.mock.patch.object(
            peer_loop.peer_worktree, "ensure_parallel_pool"
        ) as ensure, unittest.mock.patch(
            "peer_roles.worker_pool_size", return_value=8
        ):
            logs: list[str] = []
            peer_loop._after_verify_ok(log_fn=logs.append, note="test")
        ensure.assert_not_called()
        self.assertTrue(any("ensure skipped" in m for m in logs))

    def test_ensures_when_ttl_cold(self) -> None:
        import peer_loop

        peer_loop.clear_emit_ensure_cache()
        with unittest.mock.patch.object(
            peer_loop.auto, "check_off_resolved_self_heal", return_value=[]
        ), unittest.mock.patch.object(
            peer_loop.auto, "dedupe_work_queue_files"
        ), unittest.mock.patch.object(
            peer_loop, "maybe_auto_commit_after_verify"
        ), unittest.mock.patch.object(
            peer_loop, "_mechanical_post_cycle"
        ), unittest.mock.patch.object(
            peer_loop.auto,
            "measure_live_state",
            return_value=unittest.mock.Mock(
                git_clean=True, tests_ok=True, git_detail="ok", tests_detail="ok"
            ),
        ), unittest.mock.patch.object(
            peer_loop, "metrics_green", return_value=True
        ), unittest.mock.patch.object(
            peer_loop, "_emit_automation_event"
        ), unittest.mock.patch.object(
            peer_loop, "_should_skip_emit_ensure", return_value=False
        ), unittest.mock.patch.object(
            peer_loop.peer_worktree,
            "ensure_parallel_pool",
            return_value=[Path(f"/tmp/peer-{i}") for i in range(8)],
        ) as ensure, unittest.mock.patch(
            "peer_roles.worker_pool_size", return_value=8
        ):
            logs: list[str] = []
            peer_loop._after_verify_ok(log_fn=logs.append, note="test")
        ensure.assert_called_once()
        self.assertTrue(any("8/8 ready" in m for m in logs))
        self.assertGreater(peer_loop._emit_ensure_at, 0.0)


if __name__ == "__main__":
    unittest.main()
