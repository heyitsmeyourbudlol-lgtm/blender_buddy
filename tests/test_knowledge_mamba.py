#!/usr/bin/env python3
"""Tests for memory-capped Mamba cascade reranker."""

from __future__ import annotations

import sys
import unittest
from unittest import mock

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts"))

import knowledge_index_config as kcfg  # noqa: E402
import knowledge_mamba as kmamba  # noqa: E402


class KnowledgeMambaTests(unittest.TestCase):
    def test_cascade_tiers_default(self) -> None:
        with mock.patch.object(kcfg, "_cfg", return_value={"mamba_mode": "cascade"}):
            tiers = kcfg.cascade_tiers()
        self.assertEqual(len(tiers), 3)
        self.assertEqual(tiers[0]["role"], "student")
        self.assertIn("130m", tiers[0]["model"])
        self.assertIn("790m", tiers[1]["model"])
        self.assertIn("2.8b", tiers[2]["model"])
        self.assertEqual(tiers[2]["compression"], "4bit")

    def test_budget_defaults_to_brain_carve(self) -> None:
        with mock.patch.object(kcfg, "_cfg", return_value={}):
            self.assertEqual(kcfg.knowledge_mamba_budget_gb(), 12.0)
            self.assertEqual(kcfg.mamba_max_ram_mb(), 12 * 1024)

    def test_explicit_max_ram_capped_by_carve(self) -> None:
        with mock.patch.object(
            kcfg,
            "_cfg",
            return_value={"knowledge_mamba_budget_gb": 4, "mamba_max_ram_mb": 8192},
        ):
            self.assertEqual(kcfg.knowledge_mamba_budget_gb(), 4.0)
            self.assertEqual(kcfg.mamba_max_ram_mb(), 4096)

    def test_28b_fp16_blocked_4bit_allowed(self) -> None:
        model = "state-spaces/mamba-2.8b-hf"
        self.assertGreater(kcfg.estimated_model_weight_mb(model, compression="fp16"), 2048)
        self.assertLessEqual(kcfg.estimated_model_weight_mb(model, compression="4bit"), 2048)

    def test_rejects_oversized_fp16_teacher(self) -> None:
        kmamba.unload()
        with mock.patch.object(
            kcfg, "mamba_max_ram_mb", return_value=2048
        ), mock.patch.object(
            kcfg, "estimated_model_weight_mb", side_effect=lambda mid, compression="fp16": 5600 if "2.8b" in mid and compression == "fp16" else 260
        ):
            ok = kmamba._load_model("state-spaces/mamba-2.8b-hf", compression="fp16")
        self.assertFalse(ok)

    def test_cascade_rerank_calls_tiers(self) -> None:
        kmamba.unload()
        hits = [
            {"text": "alpha", "sparse_score": 0.5, "path": "a", "source": "notes"},
            {"text": "beta mamba", "sparse_score": 0.5, "path": "b", "source": "notes"},
        ]
        loads: list[str] = []

        def fake_load(model_id: str, *, compression: str) -> bool:
            loads.append(f"{model_id}:{compression}")
            return True

        def fake_score(query: str, pool: list[dict]) -> list[dict]:
            return sorted(pool, key=lambda h: h["path"], reverse=True)

        with mock.patch.object(kcfg, "mamba_cascade_enabled", return_value=True), mock.patch.object(
            kcfg, "cascade_tiers",
            return_value=[
                {"role": "student", "model": "s-130m", "compression": "fp16", "top_k": 2},
                {"role": "teacher_1", "model": "t-790m", "compression": "fp16", "top_k": 1},
            ],
        ), mock.patch.object(kmamba, "_load_model", side_effect=fake_load), mock.patch.object(
            kmamba, "_score_hits", side_effect=fake_score
        ), mock.patch.object(kmamba, "unload"):
            out = kmamba.rerank("mamba", hits, top_k=1)
        self.assertEqual(len(loads), 2)
        self.assertEqual(out[0]["path"], "b")
        self.assertEqual(out[0].get("cascade_stage"), "teacher_1")

    def test_hybrid_rerank_hash_fallback(self) -> None:
        kmamba.unload()
        with mock.patch.object(kcfg, "mamba_cascade_enabled", return_value=False), mock.patch.object(
            kmamba, "_lazy_load", return_value=False
        ):
            hits = [
                {"text": "unrelated fluff", "sparse_score": 0.1, "path": "a", "source": "notes"},
                {"text": "mamba hybrid retrieval needle", "sparse_score": 0.1, "path": "b", "source": "notes"},
            ]
            out = kmamba.rerank("mamba hybrid retrieval", hits, top_k=2)
        self.assertEqual(out[0]["path"], "b")


if __name__ == "__main__":
    unittest.main()
