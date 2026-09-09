"""Dataset curator gates — gen_all anti-prune + distill schema validate.

Needle: OVERSEER_NICHE_GEN_ALL_SKIP_EXISTING_2026_09_08
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import niche_bank_train as nbt  # noqa: E402
import niche_distill_validate as ndv  # noqa: E402


class GenAllSkipExistingTests(unittest.TestCase):
    """gen_all must never overwrite existing primary+heldout pairs."""

    def test_gen_all_skips_all_existing_corpora(self) -> None:
        catalog = nbt.parse_catalog() + nbt.extra_niches()
        wrote_paths: list[str] = []

        def _spy_write(path: Path, rows: list) -> None:  # noqa: ANN001
            wrote_paths.append(str(path))

        with mock.patch.object(nbt, "write_jsonl", side_effect=_spy_write):
            with mock.patch.object(nbt, "_ensure_label_jsonl_from_curated"):
                result = nbt.gen_all(catalog, skip_existing=True)

        self.assertEqual(result["wrote"], [])
        self.assertEqual(wrote_paths, [])
        self.assertGreaterEqual(len(result["skipped"]), 100)
        for nid in ("N01", "N02", "N03", "N08", "N65", "N74"):
            self.assertIn(nid, result["skipped"], msg=f"{nid} must be skip-protected")

    def test_gen_all_writes_only_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            distill = Path(tmp)
            niche = {
                "id": "N999",
                "name": "curator_probe",
                "input_shape": "text",
                "output_shape": "label",
                "helps": "test",
            }
            train_p = distill / "N999_curator_probe.jsonl"

            def _paths(nid: str, name: str) -> tuple[Path, Path]:
                base = distill / f"{nid}_{name}"
                return Path(str(base) + ".jsonl"), Path(str(base) + "_heldout.jsonl")

            with mock.patch.object(nbt, "jsonl_paths", side_effect=_paths):
                with mock.patch.object(
                    nbt,
                    "synthesize_rows",
                    return_value=(
                        [{"niche_id": "N999", "input": "a", "output": {"label": "x"}}],
                        [{"niche_id": "N999", "input": "b", "output": {"label": "y"}}],
                    ),
                ):
                    first = nbt.gen_all([niche], skip_existing=True)
                    self.assertEqual(first["wrote"], ["N999"])
                    self.assertTrue(train_p.is_file())
                    second = nbt.gen_all([niche], skip_existing=True)
                    self.assertEqual(second["wrote"], [])
                    self.assertIn("N999", second["skipped"])


class DistillValidateTests(unittest.TestCase):
    """endswith filters + live hub floors."""

    def test_endswith_filters_keep_n65_n74_primaries(self) -> None:
        self.assertTrue(ndv.is_primary_jsonl("N65_last_resort_stamp_seed.jsonl"))
        self.assertTrue(ndv.is_primary_jsonl("N74_heldout_split_ok.jsonl"))
        self.assertFalse(ndv.is_primary_jsonl("N65_last_resort_stamp_seed_heldout.jsonl"))
        self.assertFalse(ndv.is_primary_jsonl("N03_land_proof_needle_match_stamp.jsonl"))
        self.assertFalse(ndv.is_primary_jsonl("N03_land_proof_needle_match_stamp_heldout.jsonl"))
        self.assertTrue(ndv._is_corpus_jsonl("N74_heldout_split_ok_heldout.jsonl"))

    def test_validate_hub_ok(self) -> None:
        report = ndv.validate()
        self.assertTrue(report["ok"], msg=report.get("issues"))
        self.assertGreaterEqual(report["files"], 100)
        for name, floor in ndv.FLOOR_ROWS.items():
            self.assertGreaterEqual(
                report["counts"].get(name, 0),
                floor,
                msg=f"{name} below floor",
            )


if __name__ == "__main__":
    unittest.main()
