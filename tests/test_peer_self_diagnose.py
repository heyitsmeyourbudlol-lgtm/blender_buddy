#!/usr/bin/env python3
"""Tests for self-diagnosis layer."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_self_diagnose as sd  # noqa: E402


class TestPeerSelfDiagnose(unittest.TestCase):
    def test_block_includes_mandate(self) -> None:
        block = sd.format_self_diagnose_block(role_id="verify_runner", quick=True)
        self.assertIn("Self-diagnosis", block)
        self.assertIn("miscalculation", block.lower())

    def test_last_cycle_verify_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "peer-loop-state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "last_cycle": {
                            "verify_ok": False,
                            "note": "unittest fail",
                            "ts": 1,
                        }
                    }
                ),
                encoding="utf-8",
            )
            orig = sd.auto.CONFIG_DIR
            sd.auto.CONFIG_DIR = Path(tmp)
            sd.LAST_SCAN_JSON = Path(tmp) / "self-diagnose-last.json"
            try:
                import peer_self_heal as sh

                orig_scan = sh.scan_bottlenecks
                sh.scan_bottlenecks = lambda: []  # type: ignore[method-assign]
                findings = sd.run_instant_diagnosis(quick=True)
                sh.scan_bottlenecks = orig_scan  # type: ignore[method-assign]
            finally:
                sd.auto.CONFIG_DIR = orig
            titles = [f.title for f in findings]
            self.assertIn("Last cycle verify failed", titles)

    def test_write_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sd.SELF_DIAGNOSE_MD = Path(tmp) / "SELF_DIAGNOSE.md"
            sd.LAST_SCAN_JSON = Path(tmp) / "last.json"
            path = sd.write_self_diagnose_md()
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn("Logic checks", text)


if __name__ == "__main__":
    unittest.main()
