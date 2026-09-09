"""Tests for N03/N08 P1 practice distill/eval/serve.

OVERSEER_NICHE_P1_N03_N08_2026_09_06
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import niche_n03_practice as n03  # noqa: E402
import niche_n08_practice as n08  # noqa: E402


class NicheN03N08PracticeTests(unittest.TestCase):
    """OVERSEER_NICHE_P1_N03_N08_2026_09_06"""

    def test_land_proof_needle_present(self) -> None:
        recipe = (ROOT / "notes/niche_distill/RECIPE.md").read_text(encoding="utf-8")
        stress = (ROOT / "notes/niche_distill/STRESS_GAPS.md").read_text(encoding="utf-8")
        self.assertIn(n03.NEEDLE, recipe)
        self.assertIn(n03.NEEDLE, stress)
        self.assertIn("practice_n03", recipe)
        self.assertIn("practice_n08", recipe)

    def test_n03_ckpt_and_heldout_bar(self) -> None:
        self.assertTrue(n03.CKPT_JSON.is_file())
        self.assertTrue(n03.WEIGHTS_PT.is_file())
        meta = json.loads(n03.CKPT_JSON.read_text(encoding="utf-8"))
        self.assertEqual(meta.get("needle"), n03.NEEDLE)
        self.assertGreaterEqual(float(meta.get("heldout_accuracy") or 0), 0.90)
        blob = n03.load_weights_pt()
        self.assertEqual(blob.get("needle"), n03.NEEDLE)

    def test_n08_ckpt_and_heldout_bar(self) -> None:
        self.assertTrue(n08.CKPT_JSON.is_file())
        self.assertTrue(n08.WEIGHTS_PT.is_file())
        meta = json.loads(n08.CKPT_JSON.read_text(encoding="utf-8"))
        self.assertEqual(meta.get("needle"), n08.NEEDLE)
        self.assertGreaterEqual(float(meta.get("heldout_accuracy") or 0), 0.90)
        blob = n08.load_weights_pt()
        self.assertEqual(blob.get("needle"), n08.NEEDLE)

    def test_n03_predict_needle_and_null(self) -> None:
        line = (
            "[kit] peer_loop: continue_on_dirty — "
            "landed `OVERSEER_CONTINUE_ON_DIRTY_SKIP_GIT_CLEAN_WAIT_2026_09_04`"
        )
        self.assertEqual(
            n03.predict(line),
            "OVERSEER_CONTINUE_ON_DIRTY_SKIP_GIT_CLEAN_WAIT_2026_09_04",
        )
        self.assertIsNone(n03.predict("Mark done without needle after agent essay"))

    def test_n08_predict_stall_classes(self) -> None:
        self.assertEqual(
            n08.predict(
                {
                    "status": "plan-gate BLOCKED role=factory_engineer",
                    "log": "Episodic hard-fail; skip primary dispatch",
                }
            ),
            "plan_gate_blocked",
        )
        self.assertEqual(
            n08.predict(
                {
                    "status": "verify_ok=false failure_type=tests",
                    "log": "unittest FAIL: test_queue_drift AssertionError",
                }
            ),
            "verify_fail_tests",
        )
        self.assertEqual(
            n08.predict(
                {
                    "status": "Cycle lean-green=no-HOLD verify=ok",
                    "log": "last_cycle verify_ok=true noop=false; Active kit flowing",
                }
            ),
            "healthy",
        )
        # P2-G1: residual adapt_stale healed under green Cycle → healthy
        self.assertEqual(
            n08.predict(
                {
                    "status": "Cycle rc=0 · verify=ok",
                    "log": "last_cycle verify_ok=true; bottleneck_id=adapt_stale healed",
                }
            ),
            "healthy",
        )
        self.assertEqual(
            n08.predict(
                {
                    "status": "bottleneck id=adapt_stale",
                    "log": "should_re_adapt() true after scripts change",
                }
            ),
            "adapt_stale",
        )

    def test_heldout_eval_pass_bar(self) -> None:
        for mod in (n03, n08):
            heldout = mod.load_jsonl(mod.HELDOUT_JSONL)
            acc = mod.eval_heldout(heldout)
            self.assertGreaterEqual(acc, 0.90, msg=f"{mod.NEEDLE} {mod.__name__}")


if __name__ == "__main__":
    unittest.main()
