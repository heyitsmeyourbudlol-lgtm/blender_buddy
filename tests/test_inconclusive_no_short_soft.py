"""OVERSEER_INCONCLUSIVE_NO_SHORT_SOFT_GREEN_2026_09_04 — short real fails stay red."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import project_automation as pa  # noqa: E402


class InconclusiveNoShortSoftTests(unittest.TestCase):
    def test_needle_and_no_blanket_len(self) -> None:
        src = Path(pa.__file__).read_text(encoding="utf-8")
        self.assertIn("OVERSEER_INCONCLUSIVE_NO_SHORT_SOFT_GREEN_2026_09_04", src)
        self.assertNotIn("return len(s) < 24", src)

    def test_short_real_fails_are_conclusive(self) -> None:
        for line in (
            "Permission denied",
            "Timeout",
            "Killed",
            "Segmentation fault",
            "tests failed",
        ):
            self.assertFalse(
                pa._inconclusive_quick_fail_line(line),
                msg=f"expected FAIL (not soft) for {line!r}",
            )

    def test_garbage_and_epilog_still_soft(self) -> None:
        self.assertTrue(pa._inconclusive_quick_fail_line(""))
        self.assertTrue(pa._inconclusive_quick_fail_line("failed"))
        self.assertTrue(
            pa._inconclusive_quick_fail_line("(pass --execute to run; never uses --force)")
        )


if __name__ == "__main__":
    unittest.main()
