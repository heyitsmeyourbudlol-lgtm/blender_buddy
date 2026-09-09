"""Tests for niche distill schema + anti-prune floors.

OVERSEER_NICHE_DISTILL_VALIDATE_2026_09_05
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import niche_bank_train as bank  # noqa: E402
import niche_distill_validate as v  # noqa: E402


class NicheDistillValidateTests(unittest.TestCase):
    """OVERSEER_NICHE_DISTILL_VALIDATE_2026_09_05"""

    def test_live_corpus_passes_floors(self) -> None:
        report = v.validate()
        self.assertTrue(report["ok"], msg=report.get("issues"))
        for name, floor in v.FLOOR_ROWS.items():
            self.assertGreaterEqual(
                report["counts"].get(name, 0),
                floor,
                msg=f"{name} below anti-prune floor",
            )

    def test_floor_fail_on_prune(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "N08_stall_class_label.jsonl").write_text(
                '{"niche_id":"N08","input":{"status":"x","log":"y"},"output":"healthy"}\n',
                encoding="utf-8",
            )
            (d / "N08_stall_class_label_heldout.jsonl").write_text(
                '{"niche_id":"N08","input":{"status":"x","log":"y"},"output":"healthy"}\n',
                encoding="utf-8",
            )
            # Minimal valid N01/N03 so load doesn't "missing file" drown the signal
            for name in (
                "N01_queue_bullet_parse.jsonl",
                "N01_queue_bullet_parse_heldout.jsonl",
                "N03_land_proof_needle_match.jsonl",
                "N03_land_proof_needle_match_heldout.jsonl",
            ):
                nid = name[:3]
                if nid == "N01":
                    row = {
                        "niche_id": "N01",
                        "input": "- [ ] x",
                        "output": {"kit": True, "scope": "", "needle": None},
                    }
                else:
                    row = {"niche_id": "N03", "input": "no needle", "output": None}
                # Write enough rows to meet floors so only N08 floor fails
                import json

                lines = "\n".join(json.dumps(row) for _ in range(v.FLOOR_ROWS[name])) + "\n"
                (d / name).write_text(lines, encoding="utf-8")
            report = v.validate(distill=d)
            self.assertFalse(report["ok"])
            self.assertTrue(
                any("N08_stall_class_label.jsonl" in x and "prune forbidden" in x for x in report["issues"])
            )

    def test_gen_all_skips_any_existing_pair(self) -> None:
        """Anti-prune: existing N02 primary+heldout must not be rewritten."""
        catalog = bank.parse_catalog()
        n02 = next(n for n in catalog if n["id"] == "N02")
        train_p, held_p = bank.jsonl_paths(n02["id"], n02["name"])
        self.assertTrue(train_p.is_file() and held_p.is_file())
        before = train_p.read_bytes()
        result = bank.gen_all([n02], skip_existing=True)
        self.assertIn("N02", result["skipped"])
        self.assertNotIn("N02", result["wrote"])
        self.assertEqual(before, train_p.read_bytes())


if __name__ == "__main__":
    unittest.main()
