"""OVERSEER_IMPROVE_READY_RC_2026_09_04 — improve marks verify only when ready."""
from __future__ import annotations
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
        self.assertIn("sys.exit(0 if ready else (rc if rc else 2))", src)
        self.assertIn('a == "local-cycle: ok"', src)
        self.assertNotIn('startswith("local-cycle:")', src)

    def test_bounded_deferred_not_ok_action(self) -> None:
        logs: list[str] = []
        proc = mock.Mock()
        proc.communicate.return_value = ("deferred\n", "")
        proc.returncode = 2
        with mock.patch.object(improve.subprocess, "Popen", return_value=proc):
            actions = improve._run_local_cycle_bounded(log_fn=logs.append)
        self.assertTrue(any(a.startswith("local-cycle: rc=") for a in actions))
        self.assertFalse(any(a == "local-cycle: ok" for a in actions))


if __name__ == "__main__":
    unittest.main()
