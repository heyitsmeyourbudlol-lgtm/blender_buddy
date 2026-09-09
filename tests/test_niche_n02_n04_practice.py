"""Tests for N02 + N04 practice distill/eval/serve stamps.

OVERSEER_NICHE_PRACTICE_N02_2026_09_07
OVERSEER_NICHE_PRACTICE_N04_2026_09_07
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

import niche_n02_practice as n02  # noqa: E402
import niche_n04_practice as n04  # noqa: E402


class NicheN02PracticeTests(unittest.TestCase):
    """OVERSEER_NICHE_PRACTICE_N02_2026_09_07"""

    def test_land_proof_needle_present(self) -> None:
        src = (SCRIPTS / "niche_n02_practice.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_NICHE_PRACTICE_N02_2026_09_07", src)

    def test_checkpoint_landed(self) -> None:
        self.assertTrue(n02.CKPT_JSON.is_file())
        self.assertTrue(n02.WEIGHTS_PT.is_file())
        meta = json.loads(n02.CKPT_JSON.read_text(encoding="utf-8"))
        self.assertEqual(meta.get("needle"), n02.NEEDLE)
        self.assertGreaterEqual(float(meta.get("heldout_accuracy") or 0), 0.90)
        self.assertIs(meta.get("corpus_prune"), False)

    def test_weights_pt_loads(self) -> None:
        blob = n02.load_weights_pt()
        self.assertEqual(blob.get("needle"), n02.NEEDLE)

    def test_heldout_accuracy_pass_bar(self) -> None:
        acc = n02.eval_heldout(n02.load_jsonl(n02.HELDOUT_JSONL))
        self.assertGreaterEqual(acc, 0.90)

    def test_legend_paren_does_not_steal_label(self) -> None:
        line = (
            "Classify queue_kit_vs_research as kit. Context: "
            "Needle: `OVERSEER_EXAMPLE_2026_09_06` (kit/research/creative/defer)"
        )
        pred = n02.predict(line)
        self.assertEqual(pred["label"], "kit")


class NicheN04PracticeTests(unittest.TestCase):
    """OVERSEER_NICHE_PRACTICE_N04_2026_09_07"""

    def test_land_proof_needle_present(self) -> None:
        src = (SCRIPTS / "niche_n04_practice.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_NICHE_PRACTICE_N04_2026_09_07", src)

    def test_checkpoint_landed(self) -> None:
        self.assertTrue(n04.CKPT_JSON.is_file())
        self.assertTrue(n04.WEIGHTS_PT.is_file())
        meta = json.loads(n04.CKPT_JSON.read_text(encoding="utf-8"))
        self.assertEqual(meta.get("needle"), n04.NEEDLE)
        self.assertGreaterEqual(float(meta.get("heldout_accuracy") or 0), 0.90)
        self.assertIs(meta.get("corpus_prune"), False)

    def test_weights_pt_loads(self) -> None:
        blob = n04.load_weights_pt()
        self.assertEqual(blob.get("needle"), n04.NEEDLE)

    def test_heldout_accuracy_pass_bar(self) -> None:
        acc = n04.eval_heldout(n04.load_jsonl(n04.HELDOUT_JSONL))
        self.assertGreaterEqual(acc, 0.90)

    def test_serve_label_equals(self) -> None:
        line = (
            "Niche active_empty_seed_pick: label=abstain | empty Active | "
            "WORK_QUEUE Active empty"
        )
        pred = n04.predict(line)
        self.assertEqual(pred["label"], "abstain")


if __name__ == "__main__":
    unittest.main()
