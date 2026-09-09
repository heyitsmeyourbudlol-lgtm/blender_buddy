#!/usr/bin/env python3
"""Tests for memory span tiered external memory."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_memory_span as ms  # noqa: E402


class TestPeerMemorySpan(unittest.TestCase):
    def test_tier_budget_100x_scale(self) -> None:
        b = ms.tier_budget()
        total = b.hot + b.warm + b.cold
        self.assertGreaterEqual(total, 50_000)

    def test_record_and_recall_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ms.JOURNAL_DIR = Path(tmp) / "journal"
            ms.SUMMARY_PATH = Path(tmp) / "summaries.jsonl"
            ms.record_memory("factory_engineer", "peer_loop wake at line 820", tags=["wake"])
            hits = ms.recall_from_journal("factory_engineer", "peer_loop wake")
            self.assertTrue(hits)
            self.assertIn("820", hits[0].get("text", ""))

    def test_memory_pack_has_tiers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ms.JOURNAL_DIR = Path(tmp) / "journal"
            ms.SUMMARY_PATH = Path(tmp) / "summaries.jsonl"
            ms.record_memory("verify_runner", "flake in test_peer_loop", tags=["flake"])
            pack = ms.format_memory_pack(
                role_id="verify_runner",
                assignment="fix unittest flake",
                include_cold=False,
            )
            self.assertIn("Hot memory", pack)
            self.assertIn("Warm memory", pack)
            self.assertIn("100x", pack)


if __name__ == "__main__":
    unittest.main()
