"""OVERSEER_ADAPT_VERIFY_PROTECT_2026_09_03."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
from unittest import mock
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import automation_adapt as adapt
import dgx_ram_budget as budget

class AdaptVerifyProtectTests(unittest.TestCase):
    def test_needles(self):
        src = Path(adapt.__file__).read_text()
        self.assertIn("OVERSEER_ADAPT_VERIFY_PROTECT_2026_09_03", src)
        self.assertIn("start_new_session=True", src)
    def test_register_roundtrip(self):
        class Fake:
            pid=99; returncode=0
            def communicate(self, timeout=None): return ("", "")
            def kill(self): pass
            def wait(self, timeout=None): pass
        reg=[]; un=[]
        with mock.patch.object(adapt.subprocess, "Popen", return_value=Fake()), mock.patch.object(adapt, "_register_verify_protect", side_effect=lambda p: reg.append(p)), mock.patch.object(adapt, "_unregister_verify_protect", side_effect=lambda p: un.append(p)):
            adapt._run("python3 -m unittest x -q", cwd=ROOT, timeout=5)
        self.assertEqual(reg, [99]); self.assertEqual(un, [99])
    def test_budget_api(self):
        self.assertTrue(hasattr(budget, "register_verify_protect"))

class StormBrakeTests(unittest.TestCase):
    def test_no_pkill(self):
        import dgx_utilization as u
        src=Path(u.__file__).read_text()
        self.assertIn("OVERSEER_STORM_BRAKE_2026_09_03", src)
        self.assertNotIn('["pkill", "-9", "-f", "automation_adapt.py"]', src)

if __name__ == "__main__":
    unittest.main()
