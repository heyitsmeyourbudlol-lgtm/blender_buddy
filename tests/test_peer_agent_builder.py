#!/usr/bin/env python3
"""Tests for Agent Builder — schema validate + dry-run provision + who routing."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import peer_agent_builder as ab  # noqa: E402
import peer_commands as pc  # noqa: E402
import peer_roles as pr  # noqa: E402
import template_match as tm  # noqa: E402


def _minimal_cfg() -> dict:
    return {
        "agent_roles": [
            {
                "id": "factory_engineer",
                "job_title": "Factory Engineer",
                "legacy_peer": "implement",
                "strengths": ["factory", "implement"],
                "responsibilities": "kit",
                "niche_task": "kit",
                "reads": ["AGENTS.md"],
            },
            {
                "id": "top10_implementer",
                "job_title": "TOP10 Next Implementer",
                "legacy_peer": "implement",
                "strengths": ["TOP10_NEXT", "top10_implementer", "[top10-next]"],
                "responsibilities": "top10",
                "niche_task": "top10",
                "reads": ["notes/TOP10_NEXT.md"],
            },
        ],
        "task_templates": {
            "top10_next": {
                "peer": "implement",
                "safety_tier": "green",
                "scope": ["notes/TOP10_NEXT.md"],
                "prompt": "top10",
            },
            "generic_task": {
                "peer": "implement",
                "safety_tier": "green",
                "scope": [],
                "prompt": "generic",
            },
        },
        "match_rules": [
            {
                "template": "top10_next",
                "any": ["TOP10_NEXT", "[top10-next]", "top10_implementer"],
                "priority": 1,
            }
        ],
        "role_importance_order": ["factory_engineer", "top10_implementer"],
    }


class TestSchemaValidate(unittest.TestCase):
    def test_valid_spec(self) -> None:
        spec = {
            "id": "demo_widget_sme",
            "job_title": "Demo Widget SME",
            "strengths": ["demo_widget", "[demo-widget]"],
            "responsibilities": "demo only",
            "niche_task": "**Demo** — NO PAY",
            "reads": ["AGENTS.md"],
            "legacy_peer": "implement",
            "safety_tier": "green",
            "match": ["demo_widget", "[demo-widget]"],
            "template_prompt": "You are demo_widget_sme. NO PAY.",
        }
        self.assertEqual(ab.validate_spec(spec), [])

    def test_refuse_billing_id_without_ack(self) -> None:
        spec = {
            "id": "stripe_billing_bot",
            "job_title": "Stripe Billing Bot",
            "strengths": ["stripe", "billing"],
            "responsibilities": "charge cards",
            "niche_task": "billing",
            "reads": ["AGENTS.md"],
            "legacy_peer": "launch",
            "safety_tier": "green",
            "match": ["stripe"],
            "template_prompt": "Enable Stripe checkout.",
        }
        issues = ab.validate_spec(spec, human_ack=False)
        self.assertTrue(any("NO-PAY" in i for i in issues))
        self.assertEqual(ab.validate_spec(spec, human_ack=True), [])

    def test_bad_id(self) -> None:
        spec = {
            "id": "Bad-Id",
            "job_title": "X",
            "strengths": ["x"],
            "responsibilities": "r",
            "niche_task": "n",
            "reads": ["AGENTS.md"],
            "legacy_peer": "implement",
            "safety_tier": "green",
            "match": ["x"],
            "template_prompt": "p",
        }
        self.assertTrue(any("id must match" in i for i in ab.validate_spec(spec)))


class TestDryRunProvision(unittest.TestCase):
    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_path = root / "peer_tasks.json"
            cfg = _minimal_cfg()
            cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            before = cfg_path.read_text(encoding="utf-8")
            spec = {
                "id": "demo_widget_sme",
                "job_title": "Demo Widget SME",
                "strengths": ["demo_widget", "[demo-widget]"],
                "responsibilities": "demo",
                "niche_task": "demo",
                "reads": ["AGENTS.md"],
                "legacy_peer": "implement",
                "safety_tier": "green",
                "match": ["demo_widget", "[demo-widget]"],
                "template_prompt": "demo prompt NO PAY",
                "create_vault": False,
                "create_cursor_rule": False,
            }
            # Monkeypatch paths used only after write — call build with cfg_path
            result = ab.build(
                spec,
                write=False,
                skip_self_check=True,
                cfg_path=cfg_path,
            )
            self.assertTrue(result["ok"])
            self.assertTrue(result["dry_run"])
            self.assertEqual(cfg_path.read_text(encoding="utf-8"), before)
            self.assertEqual(result["plan"]["id"], "demo_widget_sme")
            self.assertTrue(result["plan"]["other_roles_untouched"])

    def test_write_upsert_preserves_others(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_path = root / "peer_tasks.json"
            cfg = _minimal_cfg()
            cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
            spec = {
                "id": "demo_widget_sme",
                "job_title": "Demo Widget SME",
                "strengths": ["demo_widget", "[demo-widget]", "demo_widget_sme"],
                "responsibilities": "demo",
                "niche_task": "demo",
                "reads": ["AGENTS.md"],
                "legacy_peer": "implement",
                "safety_tier": "green",
                "match": ["demo_widget", "[demo-widget]"],
                "template_prompt": "demo prompt",
                "match_priority": 12,
                "create_vault": False,
                "create_cursor_rule": False,
            }
            # Avoid vault/automation/domain side effects by patching helpers
            orig_vault = ab.write_vault_stub
            orig_rule = ab.write_cursor_rule
            orig_auto = ab.patch_automation_md
            orig_dom = ab.patch_domain_sme
            ab.write_vault_stub = lambda s: root / "skip"  # type: ignore[assignment]
            ab.write_cursor_rule = lambda s: None  # type: ignore[assignment]
            ab.patch_automation_md = lambda s: False  # type: ignore[assignment]
            ab.patch_domain_sme = lambda s: False  # type: ignore[assignment]
            try:
                result = ab.build(
                    spec,
                    write=True,
                    skip_self_check=True,
                    cfg_path=cfg_path,
                )
            finally:
                ab.write_vault_stub = orig_vault  # type: ignore[assignment]
                ab.write_cursor_rule = orig_rule  # type: ignore[assignment]
                ab.patch_automation_md = orig_auto  # type: ignore[assignment]
                ab.patch_domain_sme = orig_dom  # type: ignore[assignment]
            self.assertTrue(result["ok"])
            loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
            ids = [r["id"] for r in loaded["agent_roles"]]
            self.assertIn("factory_engineer", ids)
            self.assertIn("top10_implementer", ids)
            self.assertIn("demo_widget_sme", ids)
            self.assertIn("demo_widget_sme", loaded["task_templates"])
            self.assertTrue(
                any(r.get("template") == "demo_widget_sme" for r in loaded["match_rules"])
            )
            # who routes
            who = ab.who_for_task("[demo-widget] fix tooltip", cfg=loaded)
            self.assertEqual(who["role_id"], "demo_widget_sme")
            self.assertEqual(who["template"], "demo_widget_sme")


class TestExistingMatchingIntact(unittest.TestCase):
    def test_top10_still_routes(self) -> None:
        cfg = ab.load_peer_tasks()
        who = ab.who_for_task(
            "[top10-next] Implement TOP10_NEXT item T10-01",
            cfg=cfg,
        )
        self.assertEqual(who["template"], "top10_next")
        self.assertEqual(who["role_id"], "top10_implementer")

    def test_agent_builder_routes(self) -> None:
        cfg = ab.load_peer_tasks()
        who = ab.who_for_task(
            "[agent-builder] refine specialist spec for factory",
            cfg=cfg,
        )
        self.assertEqual(who["template"], "agent_builder")
        self.assertEqual(who["role_id"], "agent_builder")


class TestPeerCommandsRegistered(unittest.TestCase):
    def test_commands_present(self) -> None:
        ids = {c.id for c in pc.COMMANDS}
        for need in (
            "agent-build",
            "agent-build-list",
            "agent-build-validate",
            "agent-who",
        ):
            self.assertIn(need, ids)


if __name__ == "__main__":
    unittest.main()
