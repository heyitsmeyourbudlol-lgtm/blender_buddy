"""OVERSEER_AUDIT_RC_2026_09_03."""
from __future__ import annotations
import subprocess, sys, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import automation_adapt as adapt
class AuditVerifyReturncodeTests(unittest.TestCase):
    def test_failing_usable_command_is_not_ok(self) -> None:
        findings: list = []
        fake = subprocess.CompletedProcess(args=["x"], returncode=1, stdout="FAILED (failures=1)\n", stderr="")
        with mock.patch.object(adapt, "_run", return_value=fake), mock.patch.dict("os.environ", {"AUTOMATION_ADAPT_AUDIT_ACTIVE": "0"}, clear=False):
            results = adapt._audit_verify_commands(Path("/tmp"), ["python3 -m unittest x -q"], quick=False, findings=findings)
        self.assertFalse(results[0]["ok"])
        self.assertTrue(results[0].get("usable"))

    def test_audit_verify_sets_scripts_pythonpath(self) -> None:
        """OVERSEER_AUDIT_PYTHONPATH_SCRIPTS_2026_09_07 — unittests need scripts/ on path."""
        findings: list = []
        captured: dict[str, str] = {}
        fake = subprocess.CompletedProcess(args=["x"], returncode=0, stdout="OK\n", stderr="")

        def _capture(cmd, *, cwd, timeout, env=None):  # noqa: ANN001
            if env:
                captured["PYTHONPATH"] = env.get("PYTHONPATH") or ""
            return fake

        root = Path("/tmp/audit-pp-root")
        with mock.patch.object(adapt, "_run", side_effect=_capture), mock.patch.dict(
            "os.environ", {"AUTOMATION_ADAPT_AUDIT_ACTIVE": "0"}, clear=False
        ):
            results = adapt._audit_verify_commands(
                root, ["python3 -m unittest x -q"], quick=False, findings=findings
            )
        self.assertTrue(results[0]["ok"])
        self.assertIn(str((root / "scripts").resolve()), captured.get("PYTHONPATH", ""))


if __name__ == "__main__":
    unittest.main()
