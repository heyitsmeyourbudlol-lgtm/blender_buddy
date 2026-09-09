#!/usr/bin/env python3
"""Tests for SSM state pool and streaming encode."""

from __future__ import annotations

import sys
import unittest
from unittest import mock

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts"))

import knowledge_index_config as kcfg  # noqa: E402
import knowledge_mamba_ssm as ssm  # noqa: E402


class SSMStatePoolTests(unittest.TestCase):
    def setUp(self) -> None:
        ssm.manager().clear()

    def tearDown(self) -> None:
        ssm.manager().clear()

    def test_slot_budget_grows_with_repo(self) -> None:
        cfg = {
            "compression_stack": {"enabled": True, "l5_ssm_state": True},
            "ssm_state_pool": {
                "enabled": True,
                "dynamic": True,
                "base_slots": {"student": 128},
                "slots_per_1k_chunks": 16,
            },
        }
        with mock.patch.object(kcfg, "_cfg", return_value=cfg):
            small = ssm.compute_slot_budget("student", {"chunk_count": 0, "repo_gb": 0})
            large = ssm.compute_slot_budget("student", {"chunk_count": 10000, "repo_gb": 5})
        self.assertGreater(large, small)

    def test_stream_encode_ids_chunks_with_cache_carry(self) -> None:
        calls: list[int] = []

        def fake_forward(model, input_ids, attention_mask, *, cache_params):
            chunk_len = len(input_ids[0]) if isinstance(input_ids, list) else 3
            calls.append(chunk_len)
            return object(), {"step": len(calls)}, object()

        with mock.patch.object(ssm, "_forward_chunk", side_effect=fake_forward), mock.patch.object(
            ssm, "_pool_hidden", return_value=[1.0, 0.0]
        ), mock.patch.object(
            kcfg,
            "_cfg",
            return_value={
                "compression_stack": {"enabled": True, "l5_ssm_state": True},
                "ssm_state_pool": {"enabled": True, "chunk_step_tokens": {"student": 3}},
            },
        ):
            vec, cache, seen = ssm.stream_encode_ids(object(), list(range(10)), role="student")
        self.assertEqual(vec, [1.0, 0.0])
        self.assertEqual(seen, 10)
        self.assertGreater(len(calls), 1)
        self.assertIsNotNone(cache)

    def test_pool_mb_cap_evicts_lru(self) -> None:
        cfg = {
            "compression_stack": {"enabled": True, "l5_ssm_state": True},
            "ssm_state_pool": {
                "enabled": True,
                "ssm_max_pool_mb": 10,
                "slot_mb_estimate": {"student": 5},
                "base_slots": {"student": 100},
                "max_slots": {"student": 100},
            },
        }
        with mock.patch.object(kcfg, "_cfg", return_value=cfg):
            pool = ssm.SSMStatePool()
            pool.put_state("a", {"s": 1}, role="student")
            pool.put_state("b", {"s": 2}, role="student")
            pool.put_state("c", {"s": 3}, role="student")
            tier = pool._tiers["student"]
            self.assertLessEqual(pool._total_pool_mb(), 10)
            self.assertNotIn("a", tier.slots)

    def test_pair_encode_reuses_query_prefix_cache(self) -> None:
        encode_calls: list[str] = []

        class FakeTokenizer:
            def encode(self, text: str, add_special_tokens: bool = True) -> list[int]:
                encode_calls.append(text)
                return [1, 2, 3] if "QUERY" in text else [4, 5]

        with mock.patch.object(ssm, "supports_ssm_cache", return_value=True), mock.patch.object(
            ssm,
            "stream_encode_ids",
            side_effect=[
                ([], {"prefix": True}, 3),
                ([1.0, 0.0], {"done": True}, 2),
            ],
        ), mock.patch.object(ssm, "clone_cache", side_effect=lambda c: dict(c) if c else None):
            pool = ssm.SSMStatePool()
            vec = ssm.stream_encode_pair(
                object(),
                FakeTokenizer(),
                "QUERY",
                "doc body",
                role="teacher_1",
                pool=pool,
            )
        self.assertEqual(vec, [1.0, 0.0])
        self.assertIn("QUERY", encode_calls[0])


if __name__ == "__main__":
    unittest.main()
