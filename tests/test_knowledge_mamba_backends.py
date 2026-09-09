#!/usr/bin/env python3
"""T10-10 — Mamba brain carve + abstract backends (NO PAY)."""

from __future__ import annotations

import sys
import unittest
from unittest import mock

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts"))

import knowledge_index_config as kcfg  # noqa: E402
import knowledge_mamba_backends as backends  # noqa: E402


class BrainCarveTests(unittest.TestCase):
    def test_budget_separate_from_default(self) -> None:
        with mock.patch.object(kcfg, "_cfg", return_value={"knowledge_mamba_budget_gb": 8}):
            self.assertEqual(kcfg.knowledge_mamba_budget_gb(), 8.0)
            self.assertEqual(kcfg.mamba_max_ram_mb(), 8192)

    def test_nested_mamba_budget_gb(self) -> None:
        with mock.patch.object(kcfg, "_cfg", return_value={"mamba": {"budget_gb": 10, "backend": "cascade"}}):
            self.assertEqual(kcfg.knowledge_mamba_budget_gb(), 10.0)
            self.assertEqual(kcfg.mamba_backend(), "cascade")


class BackendAbstractTests(unittest.TestCase):
    def test_hash_backend_encode(self) -> None:
        be = backends.HashBackend()
        self.assertTrue(be.available())
        self.assertTrue(be.local_only)
        vecs = be.encode(["mamba brain carve needle"])
        self.assertEqual(len(vecs), 1)
        self.assertGreater(len(vecs[0]), 8)

    def test_get_backend_aliases(self) -> None:
        self.assertEqual(backends.get_backend("hf").name, "transformers-fp16")
        self.assertEqual(backends.get_backend("vllm").name, "vllm-nvfp4")
        self.assertFalse(backends.get_backend("vllm-nvfp4").available())

    def test_carve_status_no_paid_api(self) -> None:
        with mock.patch.object(kcfg, "_cfg", return_value={"knowledge_mamba_budget_gb": 12, "mamba_backend": "hash"}):
            snap = backends.carve_status()
        self.assertEqual(snap["knowledge_mamba_budget_gb"], 12.0)
        self.assertTrue(snap["separate_from_agent_cap"])
        self.assertFalse(snap["paid_api"])
        self.assertEqual(snap["backend"], "hash")

    def test_encode_dispatch(self) -> None:
        with mock.patch.object(kcfg, "_cfg", return_value={"mamba_backend": "hash"}):
            out = backends.encode(["alpha", "beta"])
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
