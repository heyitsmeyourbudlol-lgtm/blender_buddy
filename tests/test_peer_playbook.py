#!/usr/bin/env python3
"""Tests for peer_playbook."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_playbook as pb  # noqa: E402


class TestPeerPlaybook(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = Path(self.tmp.name) / "playbook-entries.json"
        self.md = Path(self.tmp.name) / "AGENT_ERROR_PLAYBOOK.md"
        patch_reg = mock.patch.object(pb, "REGISTRY_PATH", self.registry)
        patch_md = mock.patch.object(pb, "PLAYBOOK_MD", self.md)
        patch_reg.start()
        patch_md.start()
        self.addCleanup(patch_reg.stop)
        self.addCleanup(patch_md.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_match_noop(self) -> None:
        hits = pb.match_text("noop cycle — queue fingerprint unchanged")
        self.assertTrue(any(h.id == "noop_cycle" for h in hits))

    def test_record_novel_observation(self) -> None:
        entry = pb.record_observation(
            "CustomError: widget frobnicator timeout in peer loop",
            mechanical_fix=["./scripts/peer poke"],
        )
        self.assertEqual(entry.status, "draft")
        self.assertTrue(self.registry.is_file())
        again = pb.record_observation("CustomError: widget frobnicator timeout in peer loop")
        self.assertEqual(again.id, entry.id)
        self.assertGreaterEqual(again.hit_count, 1)

    def test_sync_markdown(self) -> None:
        path = pb.sync_markdown()
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("noop_cycle", text)
        self.assertIn("heal-all", text)

    def test_ingest_from_context(self) -> None:
        ctx = {
            "last_cycle": {"failure_type": "tests", "noop": True},
            "bottlenecks": [{"id": "queue_drift", "title": "WORK_QUEUE drift", "evidence": "mismatch"}],
            "peer_log_tail": ["ERROR unittest timed out after 30s"],
            "stall_reason": "",
        }
        hits = pb.ingest_from_context(ctx)
        ids = {h.id for h in hits}
        self.assertTrue("noop_cycle" in ids or "queue_drift" in ids or "unittest_storm" in ids)

    def test_format_instant_fixes(self) -> None:
        entry = pb.seed_entries()[0]
        block = pb.format_instant_fixes([entry])
        self.assertIn("heal-all", block)


if __name__ == "__main__":
    unittest.main()
