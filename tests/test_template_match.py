"""template_match — flaw_research must not lose to automation_audit bare keyword."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import template_match as tm  # noqa: E402


def _load_peer_tasks() -> dict:
    return json.loads((SCRIPTS / "peer_tasks.json").read_text(encoding="utf-8"))


class FlawResearchVsAutomationAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        data = _load_peer_tasks()
        self.templates = data["task_templates"]
        self.rules = data["match_rules"]

    def test_flaw_research_beats_automation_mention(self) -> None:
        item = (
            "[flaw-research] automation_audit steals [flaw-research] when item "
            "mentions automation — Fix automation_improve enqueue"
        )
        tid, tmpl = tm.match_template(item, self.templates, self.rules)
        self.assertEqual(tid, "flaw_research")
        self.assertEqual(tmpl.get("peer"), "implement")

    def test_audit_without_flaw_tag_still_matches_self_check(self) -> None:
        item = "Run peer_orchestrate --self-check; fix template/verify drift"
        tid, tmpl = tm.match_template(item, self.templates, self.rules)
        self.assertEqual(tid, "automation_audit")
        self.assertEqual(tmpl.get("peer"), "verify")

    def test_bare_automation_alone_does_not_steal_to_audit(self) -> None:
        """Regression: bare 'automation' must not be an audit any[] term."""
        audit_rules = [r for r in self.rules if r.get("template") == "automation_audit"]
        self.assertTrue(audit_rules)
        for rule in audit_rules:
            any_terms = [str(t).lower() for t in (rule.get("any") or [])]
            self.assertNotIn("automation", any_terms)

    def test_equal_priority_prefers_longer_matched_term(self) -> None:
        templates = {
            "flaw_research": {"peer": "implement"},
            "automation_audit": {"peer": "verify"},
        }
        rules = [
            {"template": "automation_audit", "any": ["automation"], "priority": 8},
            {"template": "flaw_research", "any": ["flaw-research"], "priority": 8},
        ]
        item = "[flaw-research] mentions automation in the body"
        tid, tmpl = tm.match_template(item, templates, rules)
        self.assertEqual(tid, "flaw_research")
        self.assertEqual(tmpl.get("peer"), "implement")


if __name__ == "__main__":
    unittest.main()
