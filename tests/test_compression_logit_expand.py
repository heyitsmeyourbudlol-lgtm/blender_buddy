"""Unit tests for T3 logit-bank expand (schema-aware; TRAIN locked)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compression_logit_expand as expand  # noqa: E402
import compression_t0_pack as t0  # noqa: E402
import compression_t3_bitdistill as t3  # noqa: E402


class CompressionLogitExpandTests(unittest.TestCase):
    def test_parent_n_examples_from_t3_schema(self) -> None:
        base = {"n_examples": 64, "xs": [[0.0] * 8] * 64}
        self.assertEqual(expand._parent_n_examples(base), 64)
        self.assertEqual(expand._parent_n_examples({"xs": [[0.0], [1.0]]}), 2)
        self.assertEqual(expand._parent_n_examples({"rows": [{}, {}]}), 2)

    def test_parent_dim_and_bank_seed(self) -> None:
        """dim=d_out; mean-pool bank wins over xs inputs."""
        bank = [
            [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
            [[3.0, 0.0, 0.0, 0.0], [0.0, 3.0, 0.0, 0.0]],
        ]
        base = {
            "n_examples": 2,
            "d_in": 8,
            "d_out": 4,
            "xs": [[9.0] * 8, [8.0] * 8],
            "bank": bank,
        }
        self.assertEqual(expand._parent_dim(base), 4)
        rows = expand._seed_rows_from_parent(base)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source"], "parent_bank")
        self.assertEqual(rows[0]["teacher_logits"][0], 2.0)
        self.assertEqual(len(rows[0]["teacher_logits"]), 4)

    def test_check_refuses_xs_seed_when_bank_exists(self) -> None:
        if not t3.DEFAULT_BANK_PATH.is_file():
            t3.ensure_default_bank()
        parent = json.loads(t3.DEFAULT_BANK_PATH.read_text(encoding="utf-8"))
        parent_n = int(parent["n_examples"])
        d_out = int(parent["d_out"])
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad_expand.json"
            rows = [
                {
                    "source": "parent_xs",
                    "text": f"parent_x_{i}",
                    "teacher_logits": [0.0] * d_out,
                }
                for i in range(parent_n)
            ]
            # Meet ensure floor so failure is xs_as_logits, not undersize.
            for i in range(expand.DEFAULT_EXPAND_SNIPS):
                rows.append(
                    {
                        "source": "peer_factory_expand",
                        "text": f"factory_{i}",
                        "teacher_logits": [0.1] * d_out,
                    }
                )
            bad.write_text(
                json.dumps(
                    {
                        "needle": expand.NEEDLE,
                        "parent_needle": parent["needle"],
                        "n_before": parent_n,
                        "n_after": len(rows),
                        "dim": d_out,
                        "data_prune": False,
                        "train_unlocked": False,
                        "canonical_untouched": True,
                        "rows": rows,
                    }
                ),
                encoding="utf-8",
            )
            check = expand.check_expanded(bad)
            self.assertFalse(check.get("expand_ok"), msg=check)
            self.assertIn(
                check.get("error"),
                ("xs_as_logits_refused", "missing_parent_bank_seed"),
            )

    def test_expand_advances_from_canonical_bank(self) -> None:
        """n_before must match T3 n_examples (not rows/logits miss → 0).

        Write via out_path tempfile — never clobber Lane-U durable EXPANDED.
        """
        if not t3.DEFAULT_BANK_PATH.is_file():
            t3.ensure_default_bank()
        parent = json.loads(t3.DEFAULT_BANK_PATH.read_text(encoding="utf-8"))
        parent_n = int(parent["n_examples"])
        self.assertGreater(parent_n, 0)
        with tempfile.TemporaryDirectory() as td:
            toy = Path(td) / "expanded_toy.json"
            summary = expand.expand(snip_limit=16, out_path=toy)
            self.assertEqual(summary["n_before"], parent_n)
            self.assertGreater(summary["n_after"], parent_n)
            self.assertEqual(summary["n_after"], parent_n + 16)
            self.assertEqual(summary["snip_limit"], 16)
            self.assertIs(summary["train_unlocked"], False)
            self.assertIs(summary["data_prune"], False)
            self.assertTrue(summary["canonical_untouched"])
            self.assertEqual(summary["needle"], expand.NEEDLE)
            self.assertTrue(toy.is_file())
            check = expand.check_expanded(toy)
            self.assertTrue(check.get("expand_ok"), msg=check)
        # Dual SoT canonical must remain green (expand is sidecar-only)
        dual = t0.dual_sot_check()
        self.assertTrue(dual["dual_sot_ok"])
        self.assertIs(dual["train_unlocked"], False)

    def test_durable_check_rejects_undersized_expand(self) -> None:
        """Lane-U --check must fail-closed when expand_rows < DEFAULT_EXPAND_SNIPS."""
        if not t3.DEFAULT_BANK_PATH.is_file():
            t3.ensure_default_bank()
        prior = None
        if expand.EXPANDED.is_file():
            prior = expand.EXPANDED.read_text(encoding="utf-8")
        try:
            expand.expand(snip_limit=16)  # intentional undersize → durable path
            bad = expand.check_expanded()
            self.assertFalse(bad.get("expand_ok"), msg=bad)
            self.assertEqual(bad.get("error"), "expand_rows_below_ensure_floor")
            self.assertLess(bad.get("expand_rows", 0), expand.DEFAULT_EXPAND_SNIPS)
        finally:
            if prior is not None:
                expand.EXPANDED.write_text(prior, encoding="utf-8")
            else:
                _path, checked = expand.ensure_expanded()
                self.assertTrue(checked.get("expand_ok"), msg=checked)

    def test_ensure_cli(self) -> None:
        if not t3.DEFAULT_BANK_PATH.is_file():
            t3.ensure_default_bank()
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "compression_logit_expand.py"),
                "--ensure",
                "--json",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr + proc.stdout)
        data = json.loads(proc.stdout)
        self.assertTrue(data["expand_ok"])
        self.assertGreater(data["n_before"], 0)
        self.assertGreater(data["n_after"], data["n_before"])
        self.assertGreaterEqual(data["expand_rows"], expand.DEFAULT_EXPAND_SNIPS)
        self.assertEqual(data["n_after"], data["n_before"] + data["expand_rows"])
        self.assertFalse(data["train_unlocked"])
        self.assertFalse(data["data_prune"])
        check = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "compression_logit_expand.py"),
                "--check",
                "--json",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(check.returncode, 0, msg=check.stderr + check.stdout)
        checked = json.loads(check.stdout)
        self.assertTrue(checked["expand_ok"])
        self.assertGreaterEqual(checked["expand_rows"], expand.DEFAULT_EXPAND_SNIPS)


if __name__ == "__main__":
    unittest.main()
