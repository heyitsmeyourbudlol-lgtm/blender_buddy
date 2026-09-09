#!/usr/bin/env python3
"""Tests for automation engine."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import automation_engine as engine  # noqa: E402
import automation_rules_config as arc  # noqa: E402


class AutomationEngineTests(unittest.TestCase):
    def test_match_rules_by_event_and_when(self) -> None:
        rules = [
            {"id": "a", "on": "peer.verify.fail", "when": {"verify_ok": False}, "actions": []},
            {"id": "b", "on": "peer.verify.ok", "when": {"verify_ok": True}, "actions": []},
        ]
        matched = engine.match_rules("peer.verify.fail", {"verify_ok": False}, rules)
        self.assertEqual([r["id"] for r in matched], ["a"])

    def test_emit_executes_wake_peer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(arc, "state_path", return_value=Path(tmp) / "state.json"), mock.patch.object(
                arc, "log_path", return_value=Path(tmp) / "log"
            ), mock.patch.object(arc, "enabled", return_value=True), mock.patch.object(
                engine, "load_rules", return_value=[
                    {"id": "wake", "on": "webhook.ci", "when": {"status": "success"}, "actions": [{"type": "wake_peer"}]}
                ]
            ), mock.patch.dict(
                "automation_actions.ACTIONS",
                {"wake_peer": lambda _p, _a: "wake_peer: touched peer-turn.signal"},
            ):
                result = engine.emit("webhook.ci", {"status": "success"})
            self.assertEqual(result.matched_rules, ["wake"])
            self.assertTrue(any("wake_peer" in line for line in result.action_results))

    def test_cooldown_skips_repeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            with mock.patch.object(arc, "state_path", return_value=state_path), mock.patch.object(
                arc, "log_path", return_value=Path(tmp) / "log"
            ), mock.patch.object(arc, "enabled", return_value=True), mock.patch.object(
                engine, "load_rules",
                return_value=[
                    {
                        "id": "once",
                        "on": "peer.verify.fail",
                        "cooldown_sec": 3600,
                        "actions": [{"type": "log", "message": "x"}],
                    }
                ],
            ), mock.patch("automation_actions.log_action", return_value="log: x"):
                first = engine.emit("peer.verify.fail", {"verify_ok": False})
                second = engine.emit("peer.verify.fail", {"verify_ok": False})
            self.assertEqual(first.matched_rules, ["once"])
            self.assertEqual(second.skipped_cooldown, ["once"])

    def test_default_rules_file_valid_json(self) -> None:
        path = Path(__file__).resolve().parents[1] / "automation.rules.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("rules", data)
        self.assertTrue(data["rules"])


if __name__ == "__main__":
    unittest.main()
