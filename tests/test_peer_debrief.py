#!/usr/bin/env python3
"""Tests for debrief / operating system layer."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_debrief as debrief  # noqa: E402


class TestPeerDebrief(unittest.TestCase):
    def test_template_aar_blameless(self) -> None:
        body = debrief._template_aar(
            expected="x",
            actual="y",
            why="z",
            sop_change="s",
            kpi_gap="k",
        )
        self.assertIn("Blameless", body)
        self.assertIn("What was supposed to happen", body)

    def test_append_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_md = Path(tmp) / "DEBRIEF_LOG.md"
            jsonl = Path(tmp) / "entries.jsonl"
            with mock.patch.object(debrief, "DEBRIEF_LOG_MD", log_md):
                with mock.patch.object(debrief, "DEBRIEF_JSONL", jsonl):
                    debrief.append_entry(
                        debrief.DebriefEntry(
                            kind="knowledge",
                            title="Test SOP",
                            body="Lock in worktree pool ensure.",
                            kpis={"pct": 50},
                        )
                    )
            self.assertTrue(log_md.is_file())
            self.assertIn("Test SOP", log_md.read_text())
            self.assertTrue(jsonl.is_file())

    def test_build_debrief_prompt_has_kpis(self) -> None:
        text = debrief.build_debrief_prompt()
        self.assertIsNotNone(text)
        assert text is not None
        self.assertIn("Optimization Unit", text)
        self.assertIn("KPI", text)

    def test_ensure_sop_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sop = Path(tmp) / "SOP_INDEX.md"
            with mock.patch.object(debrief, "SOP_INDEX_MD", sop):
                debrief.ensure_sop_index()
            self.assertTrue(sop.is_file())
            self.assertIn("SOP", sop.read_text())


if __name__ == "__main__":
    unittest.main()
