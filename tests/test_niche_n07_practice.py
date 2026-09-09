"""Tests for N07 hallucination_block_fill practice distill/eval/serve.

OVERSEER_NICHE_PRACTICE_N07_2026_09_07
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

import niche_n07_practice as n07  # noqa: E402


class NicheN07PracticeTests(unittest.TestCase):
    """OVERSEER_NICHE_PRACTICE_N07_2026_09_07"""

    def test_needle_in_script(self) -> None:
        src = (SCRIPTS / "niche_n07_practice.py").read_text(encoding="utf-8")
        self.assertIn(n07.NEEDLE, src)

    def test_ckpt_and_heldout_bar(self) -> None:
        self.assertTrue(n07.CKPT_JSON.is_file())
        self.assertTrue(n07.WEIGHTS_PT.is_file())
        meta = json.loads(n07.CKPT_JSON.read_text(encoding="utf-8"))
        self.assertEqual(meta.get("needle"), n07.NEEDLE)
        self.assertGreaterEqual(float(meta.get("heldout_accuracy") or 0), 0.90)
        self.assertFalse(meta.get("corpus_prune"))
        blob = n07.load_weights_pt()
        self.assertEqual(blob.get("needle"), n07.NEEDLE)

    def test_predict_labels(self) -> None:
        self.assertEqual(
            n07.predict(
                "Classify hallucination_block_fill as hallucination block fill_yes. "
                "Context: Needle: `OVERSEER_EXAMPLE_2026_09_06` "
                "(Evidence/Hypothesis/Falsifier/Verify)"
            ),
            {"label": "hallucination block fill_yes"},
        )
        self.assertEqual(
            n07.predict("Factory abstain for hallucination_block_fill: fact_checker"),
            {"label": "abstain"},
        )
        self.assertEqual(
            n07.predict("Kit lock — Classify hallucination_block_fill as unknown."),
            {"label": "unknown"},
        )

    def test_heldout_eval_pass_bar(self) -> None:
        heldout = n07.load_jsonl(n07.HELDOUT_JSONL)
        acc = n07.eval_heldout(heldout)
        self.assertGreaterEqual(acc, 0.90, msg=f"{n07.NEEDLE} acc={acc}")

    def test_no_corpus_prune_paths(self) -> None:
        """Train/heldout JSONL must remain on disk (assignment: no corpus prune)."""
        self.assertTrue(n07.TRAIN_JSONL.is_file())
        self.assertTrue(n07.HELDOUT_JSONL.is_file())
        train_n = len(n07.load_jsonl(n07.TRAIN_JSONL))
        held_n = len(n07.load_jsonl(n07.HELDOUT_JSONL))
        self.assertGreaterEqual(train_n, 1)
        self.assertGreaterEqual(held_n, 1)


if __name__ == "__main__":
    unittest.main()
