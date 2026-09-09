#!/usr/bin/env python3
"""Tests for peer_rule_shutdown — propose-only add/remove/modify/suspend + topic/severity."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_rule_shutdown as rshut  # noqa: E402


class RuleShutdownTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.reg = self.root / "rule-shutdown-registry.json"
        self.mirror = self.root / "RULE_SHUTDOWN.md"
        self.digest = self.root / "RULE_SHUTDOWN_DIGEST.md"
        self.catalog = self.root / "RULE_CATALOG.md"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_denylist_flags_but_allows_propose(self) -> None:
        self.assertTrue(rshut.is_denylisted("habit:secrets_scrub", "notes/PEN_TEST.md"))
        item = rshut.propose(
            rule_id="safety_gates_red",
            action="remove",
            from_role="factory_engineer",
            reason="question boundary",
            rule_ref="notes/SAFETY_GATES.md",
            topic="safety",
            severity="critical",
            registry_path=self.reg,
        )
        self.assertTrue(item["denylist_blocked"])
        self.assertEqual(item["status"], "draft")
        self.assertEqual(item["topic"], "safety")
        self.assertEqual(item["severity"], "critical")

    def test_dual_ack_promotes_to_proposed(self) -> None:
        a = rshut.propose(
            rule_id="habit:never_solo",
            action="suspend",
            from_role="factory_engineer",
            reason="blocks parallel",
            topic="agents-prefs",
            severity="medium",
            registry_path=self.reg,
        )
        self.assertEqual(a["status"], "draft")
        b = rshut.ack(item_id=a["id"], from_role="tech_writer", registry_path=self.reg)
        self.assertEqual(b["status"], "proposed")

    def test_overseer_solo_promotes(self) -> None:
        item = rshut.propose(
            rule_id="sop:compact_queue",
            action="modify",
            from_role="progress_monitor",
            reason="cap too low",
            topic="queue-sync",
            severity="high",
            registry_path=self.reg,
        )
        self.assertEqual(item["status"], "proposed")

    def test_all_four_actions(self) -> None:
        for act in ("suspend", "add", "remove", "modify"):
            item = rshut.propose(
                rule_id=f"demo:{act}",
                action=act,
                from_role="queue_steward",
                reason=f"test {act}",
                topic="other",
                severity="low",
                registry_path=self.reg,
            )
            self.assertEqual(item["action"], act)

    def test_topic_severity_sort_order(self) -> None:
        rows = [
            {"topic": "verify", "severity": "low", "rule_id": "z", "id": "1"},
            {"topic": "safety", "severity": "medium", "rule_id": "b", "id": "2"},
            {"topic": "safety", "severity": "critical", "rule_id": "a", "id": "3"},
            {"topic": "queue-sync", "severity": "high", "rule_id": "c", "id": "4"},
        ]
        ordered = rshut.sort_by_topic_severity(rows)
        self.assertEqual(
            [(r["topic"], r["severity"]) for r in ordered],
            [
                ("safety", "critical"),
                ("safety", "medium"),
                ("queue-sync", "high"),
                ("verify", "low"),
            ],
        )

    def test_pending_grouped_in_digest(self) -> None:
        rshut.propose(
            rule_id="habit:late",
            action="suspend",
            from_role="a",
            topic="verify",
            severity="low",
            registry_path=self.reg,
        )
        rshut.propose(
            rule_id="safety:x",
            action="modify",
            from_role="a",
            topic="safety",
            severity="critical",
            registry_path=self.reg,
        )
        rshut.propose(
            rule_id="habit:late",
            action="suspend",
            from_role="b",
            registry_path=self.reg,
        )
        rshut.propose(
            rule_id="safety:x",
            action="modify",
            from_role="b",
            registry_path=self.reg,
        )
        text = rshut.build_digest_md(rshut.load_registry(path=self.reg))
        self.assertIn("### Topic: `safety`", text)
        self.assertIn("### Topic: `verify`", text)
        self.assertLess(text.index("### Topic: `safety`"), text.index("### Topic: `verify`"))

    def test_list_by_topic(self) -> None:
        items = [
            {"id": "1", "topic": "comms", "severity": "low", "action": "add", "status": "draft", "rule_id": "c", "proposers": ["a"]},
            {"id": "2", "topic": "safety", "severity": "critical", "action": "remove", "status": "proposed", "rule_id": "s", "proposers": ["b"]},
        ]
        out = rshut.format_list(items, by_topic=True)
        self.assertIn("## safety", out)
        self.assertIn("## comms", out)
        self.assertLess(out.index("## safety"), out.index("## comms"))

    def test_accept_reject_transitions(self) -> None:
        item = rshut.propose(
            rule_id="habit:x",
            action="add",
            from_role="progress_monitor",
            reason="new habit",
            topic="agents-prefs",
            severity="medium",
            registry_path=self.reg,
        )
        closed = rshut.accept(item_id=item["id"], registry_path=self.reg)
        self.assertEqual(closed["status"], "made_permanent")
        item2 = rshut.propose(
            rule_id="habit:y",
            action="suspend",
            from_role="progress_monitor",
            reason="pause",
            registry_path=self.reg,
        )
        rejected = rshut.reinstate(item_id=item2["id"], registry_path=self.reg)
        self.assertEqual(rejected["status"], "reinstated")

    def test_catalog_write(self) -> None:
        path = rshut.write_catalog(catalog_path=self.catalog)
        text = path.read_text(encoding="utf-8")
        self.assertIn("## Topic: `safety`", text)
        self.assertIn("topic → severity", text.lower())

    def test_api_payload(self) -> None:
        rshut.propose(
            rule_id="habit:api",
            action="add",
            from_role="progress_monitor",
            topic="agents-prefs",
            severity="low",
            registry_path=self.reg,
        )
        with mock.patch.object(rshut, "REGISTRY_PATH", self.reg):
            payload = rshut.build_api_payload(registry_path=self.reg)
        self.assertIn("proposals", payload)
        self.assertIn("catalog", payload)
        self.assertGreaterEqual(payload["pending_count"], 1)
        self.assertEqual(payload["topics"][0], "safety")

    def test_hot_memory_pending_not_mute(self) -> None:
        rshut.propose(
            rule_id="habit:hot",
            action="suspend",
            from_role="progress_monitor",
            reason="noise",
            registry_path=self.reg,
        )
        block = rshut.format_hot_memory_block(rshut.load_registry(path=self.reg))
        self.assertIn("awaiting human", block)
        self.assertIn("do **not** stop applying", block)

    def test_glink_payload_propose_and_ack(self) -> None:
        item = rshut.handle_glink_payload(
            from_role="factory_engineer",
            payload={"act": "sus", "rid": "habit:glink", "why": "stall", "topic": "agents-prefs", "sev": "med"},
            registry_path=self.reg,
        )
        self.assertEqual(item["action"], "suspend")
        self.assertEqual(item["severity"], "medium")
        acked = rshut.handle_glink_payload(
            from_role="tech_writer",
            payload={"op": "ack", "id": item["id"]},
            registry_path=self.reg,
        )
        self.assertEqual(acked["status"], "proposed")

    def test_severity_aliases(self) -> None:
        self.assertEqual(rshut.normalize_severity("red"), "critical")
        self.assertEqual(rshut.normalize_severity("yellow"), "medium")
        self.assertEqual(rshut.normalize_severity("green"), "low")


class GLinkRuleNeedTests(unittest.TestCase):
    def test_rsusp_rchg_in_need_codes(self) -> None:
        import peer_agent_comms as pac

        self.assertIn("rsusp", pac.REQ_NEED_CODES)
        self.assertIn("rchg", pac.REQ_NEED_CODES)
        out = pac.validate_glink_payload(
            "REQ",
            {"need": "rchg", "args": {"act": "mod", "rid": "habit:x"}},
        )
        self.assertEqual(out["need"], "rchg")
        self.assertEqual(out["args"]["act"], "mod")


class HotMemoryIntegrationTests(unittest.TestCase):
    def test_format_harness_includes_rule_block(self) -> None:
        import peer_transcript as pt

        fake_block = "## Rule-change proposals (awaiting human — rules still ON)\n- test"
        with mock.patch("peer_rule_shutdown.format_hot_memory_block", return_value=fake_block):
            text = pt.format_harness_memory({"last_cycle": {}})
        self.assertIn("Rule-change proposals", text)


if __name__ == "__main__":
    unittest.main()
