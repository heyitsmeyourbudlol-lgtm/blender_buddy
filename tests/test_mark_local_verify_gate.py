"""Gate: mark_local_verify only when run_local_cycle ready (not deferred)."""
from __future__ import annotations
import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


class MarkLocalVerifyGateTests(unittest.TestCase):
    def _run(self, ready: bool):
        import peer_loop
        import peer_transcript as pt
        import run_peer_tasks as rpt

        state: dict = {}
        with unittest.mock.patch.object(pt, "local_verify_cooldown_remaining", return_value=0.0), unittest.mock.patch.object(
            rpt, "run_local_cycle", return_value=(0, ready)
        ), unittest.mock.patch.object(
            peer_loop.transcript, "mark_local_verify"
        ) as mark, unittest.mock.patch.object(peer_loop, "_after_verify_ok") as after:
            out = peer_loop._run_local_cycle(quick=True, log_fn=lambda _m: None, state=state)
            return out, mark, after, state

    def test_deferred_does_not_mark(self) -> None:
        (failed, verified), mark, after, state = self._run(False)
        self.assertFalse(failed)
        self.assertFalse(verified)
        mark.assert_not_called()
        after.assert_not_called()

    def test_ready_does_mark(self) -> None:
        (failed, verified), mark, after, state = self._run(True)
        self.assertFalse(failed)
        self.assertTrue(verified)
        mark.assert_called_once_with(state)
        after.assert_called_once()


if __name__ == "__main__":
    unittest.main()
