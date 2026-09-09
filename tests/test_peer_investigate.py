"""Tests for peer_investigate — scheduled cursor investigation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_investigate as investigate  # noqa: E402


class InvestigatePromptTests(unittest.TestCase):
    def test_build_prompt_includes_bottlenecks(self) -> None:
        ctx = {
            "ts": "2026-09-02 12:00:00",
            "focus": "automation_improve",
            "phase": "IDLE",
            "phase_detail": "noop backoff",
            "git_clean": False,
            "git_detail": "44 paths dirty",
            "queue_count": 12,
            "queue_source": "launch",
            "last_cycle_summary": "noop · verify=ok",
            "noop_backoff_sec": 30.0,
            "open_items": ["Harden peer_loop"],
            "bottlenecks": [
                {"severity": "medium", "title": "Long noop backoff", "evidence": "180s"},
            ],
            "peer_log_tail": ["2026 noop cycle"],
            "improve_log_tail": [],
            "last_cycle": {"noop": True, "verify_ok": True},
            "kit": {"asi_pct": 12, "active_phase": "grounded_loop", "daemons": {"peer_loop": True, "improve_loop": False}},
        }
        prompt = investigate.build_investigation_prompt(ctx)
        self.assertIn("Automation Overseer", prompt)
        self.assertIn("AUTOMATION_DIGEST", prompt)
        self.assertIn("near-perfect automation", prompt)

    def test_mechanical_digest_written(self) -> None:
        ctx = investigate.collect_context()
        text = investigate.build_mechanical_digest(ctx, actions=["test"], dispatched=False)
        self.assertIn("Automation digest", text)
        self.assertIn("At a glance", text)

    def test_cooldown_blocks_without_force(self) -> None:
        import time

        with mock.patch.object(investigate, "_load_state", return_value={"last_run_ts": time.time()}):
            with mock.patch.object(investigate, "investigate_enabled", return_value=True):
                result = investigate.run_investigation_once(log_fn=lambda _m: None)
        self.assertEqual(result.get("skipped"), "cooldown")


if __name__ == "__main__":
    unittest.main()
