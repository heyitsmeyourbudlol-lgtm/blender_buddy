#!/usr/bin/env python3
"""Tests for Mamba compression stack and dynamic KV cache."""

from __future__ import annotations

import sys
import unittest
from unittest import mock

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts"))

import knowledge_index_config as kcfg  # noqa: E402
import knowledge_mamba_cache as kcache  # noqa: E402
import knowledge_mamba_stack as kstack  # noqa: E402


class CompressionStackTests(unittest.TestCase):
    def test_stack_tier_weights_4bit(self) -> None:
        cfg = {
            "mamba_mode": "cascade",
            "mamba_resident": True,
            "compression_stack": {
                "enabled": True,
                "l2_weight_format": True,
                "weights": {"student": "4bit", "teacher_1": "4bit", "teacher_2": "4bit"},
            },
        }
        with mock.patch.object(kcfg, "_cfg", return_value=cfg):
            self.assertEqual(kstack.tier_compression("student"), "4bit")
            self.assertEqual(kstack.tier_compression("teacher_2"), "4bit")
            self.assertTrue(kstack.use_mmap())

    def test_l0_retrieve_candidate_k(self) -> None:
        cfg = {
            "compression_stack": {"enabled": True, "l0_retrieve_less": True, "rerank_candidate_k": 64},
            "retrieve_candidate_k": 48,
            "retrieve_top_k": 8,
        }
        with mock.patch.object(kcfg, "_cfg", return_value=cfg):
            self.assertEqual(kstack.retrieve_candidate_k(), 64)


class DynamicKVCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        kcache.manager().clear()

    def tearDown(self) -> None:
        kcache.manager().clear()

    def test_generous_base_tokens(self) -> None:
        cfg = {
            "kv_cache": {
                "enabled": True,
                "dynamic": True,
                "base_tokens": {"student": 16384, "teacher_1": 32768, "teacher_2": 65536},
            }
        }
        with mock.patch.object(kcfg, "_cfg", return_value=cfg):
            scale = {"chunk_count": 0, "storage_gb": 0, "repo_gb": 0}
            self.assertEqual(kcache.compute_max_tokens("teacher_2", scale), 65536)

    def test_kv_grows_with_chunks(self) -> None:
        cfg = {
            "kv_cache": {
                "enabled": True,
                "dynamic": True,
                "base_tokens": {"student": 16384},
                "tokens_per_1k_chunks": 256,
                "max_tokens": {"student": 262144},
            }
        }
        with mock.patch.object(kcfg, "_cfg", return_value=cfg):
            small = {"chunk_count": 0, "storage_gb": 0, "repo_gb": 0}
            large = {"chunk_count": 10000, "storage_gb": 5, "repo_gb": 2}
            self.assertLess(
                kcache.compute_max_tokens("student", small),
                kcache.compute_max_tokens("student", large),
            )

    def test_manager_reconcile_updates_on_scale_change(self) -> None:
        cfg = {
            "kv_cache": {
                "enabled": True,
                "dynamic": True,
                "base_tokens": {"student": 8192},
                "tokens_per_1k_chunks": 256,
            }
        }
        with mock.patch.object(kcfg, "_cfg", return_value=cfg):
            mgr = kcache.MambaKVCacheManager()
            mgr.reconcile({"chunk_count": 0, "storage_gb": 0, "repo_files": 0, "repo_mb": 0})
            before = mgr._tiers["student"].max_tokens
            mgr.reconcile({"chunk_count": 50000, "storage_gb": 10, "repo_files": 1000, "repo_mb": 500})
            after = mgr._tiers["student"].max_tokens
        self.assertGreater(after, before)


if __name__ == "__main__":
    unittest.main()
