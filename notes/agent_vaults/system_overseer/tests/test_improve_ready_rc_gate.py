"""OVERSEER_IMPROVE_READY_RC_2026_09_04 — improve marks verify only when ready."""
from __future__ import annotations
import subprocess
import sys
import unittest
import unittest.mock as mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import automation_improve as improve  # noqa: E402


class ImproveReadyRcGateTests(unittest.TestCase):
    def test_source_needles(self) -> None:
        src = Path(improve.__file__).read_text(encoding="utf-8")
        self.assertIn("OVERSEER_IMPROVE_READY_RC_2026_09_04", src)
        self.assertIn("OVERSEER_IMPROVE_QUIET_BEFORE_KILL_2026_09_04", src)
        self.assertIn("OVERSEER_IMPROVE_SWARM_FAST_DEFER_2026_09_04", src)
        self.assertIn("OVERSEER_LOCAL_CYCLE_TIMEOUT_SOFT_2026_09_04", src)
        self.assertIn("OVERSEER_STOP_FORGE_SELF_SUFFICIENT_2026_09_04", src)
        self.assertIn("sys.exit(0 if ready else (rc if rc else 2))", src)
        self.assertIn("AUTOMATION_VERIFY_QUIET_TIMEOUT_SEC", src)
        self.assertIn('a == "local-cycle: ok"', src)
        self.assertNotIn('startswith("local-cycle:")', src)
        # Comment may mention the stampede phrase; live log_fn must not.
        self.assertNotIn('log_fn(f"mechanical: local cycle timed out after', src)

    def test_bounded_deferred_not_ok_action(self) -> None:
        logs: list[str] = []
        proc = mock.Mock()
        proc.communicate.return_value = ("deferred\n", "")
        proc.returncode = 2
        with mock.patch.object(improve, "_swarm_hot_for_improve_verify", return_value=False), mock.patch.object(
            improve.subprocess, "Popen", return_value=proc
        ) as popen:
            actions = improve._run_local_cycle_bounded(log_fn=logs.append)
        self.assertTrue(any(a.startswith("local-cycle: rc=") for a in actions))
        self.assertFalse(any(a == "local-cycle: ok" for a in actions))
        env = popen.call_args.kwargs.get("env") or {}
        self.assertEqual(
            env.get("AUTOMATION_VERIFY_QUIET_TIMEOUT_SEC"),
            str(improve.IMPROVE_VERIFY_QUIET_TIMEOUT_SEC),
        )

    def test_swarm_fast_defer_skips_spawn(self) -> None:
        # OVERSEER_IMPROVE_SWARM_FAST_DEFER_2026_09_04
        logs: list[str] = []
        with mock.patch.object(improve, "_swarm_hot_for_improve_verify", return_value=True), mock.patch.object(
            improve.subprocess, "Popen"
        ) as popen:
            actions = improve._run_local_cycle_bounded(log_fn=logs.append)
        popen.assert_not_called()
        self.assertEqual(actions, ["local-cycle: deferred (swarm)"])
        self.assertTrue(any("swarm active" in m for m in logs))

    def test_timeout_soft_deferred_no_stampede_phrase(self) -> None:
        """OVERSEER_LOCAL_CYCLE_TIMEOUT_SOFT_2026_09_04"""
        logs: list[str] = []
        proc = mock.Mock()
        proc.pid = 4242
        proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=90)
        with mock.patch.object(improve, "_swarm_hot_for_improve_verify", return_value=False):
            with mock.patch.object(improve.subprocess, "Popen", return_value=proc):
                with mock.patch.object(improve.os, "killpg"):
                    actions = improve._run_local_cycle_bounded(log_fn=logs.append)
        self.assertIn("local-cycle: deferred (timeout)", actions)
        self.assertFalse(any("timed out after" in m for m in logs))
        self.assertTrue(any("soft-skip" in m for m in logs))

    def test_outer_exceeds_quiet(self) -> None:
        self.assertGreater(
            improve._local_cycle_outer_timeout_sec(),
            improve.IMPROVE_VERIFY_QUIET_TIMEOUT_SEC,
        )


if __name__ == "__main__":
    unittest.main()
