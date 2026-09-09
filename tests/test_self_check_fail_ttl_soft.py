"""OVERSEER_SELF_CHECK_FAIL_TTL_SOFT_2026_09_04 — fail-ttl is tip, not ISSUES."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import peer_orchestrate as po  # noqa: E402

class SelfCheckFailTtlSoftTests(unittest.TestCase):
    def test_helper_and_needle(self) -> None:
        self.assertTrue(hasattr(po, "_tests_detail_inconclusive"))
        self.assertTrue(po._tests_detail_inconclusive("tests: FAIL (fail-ttl)"))
        self.assertTrue(po._tests_detail_inconclusive("tests: FAIL — failed"))
        self.assertTrue(
            po._tests_detail_inconclusive(
                "tests: FAIL — (pass --execute to run; never uses --force)"
            )
        )
        self.assertFalse(po._tests_detail_inconclusive("tests: FAIL — FAILED (failures=2)"))
        src = (SCRIPTS / "peer_orchestrate.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_SELF_CHECK_FAIL_TTL_SOFT_2026_09_04", src)
        self.assertIn("OVERSEER_PROBE_SKIP_BARE_FAIL_2026_09_04", src)
        self.assertIn("OVERSEER_INCONCLUSIVE_WORKTREE_EPILOG_2026_09_04", src)

if __name__ == "__main__":
    unittest.main()
