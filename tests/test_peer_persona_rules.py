#!/usr/bin/env python3
"""Tests for hardwired agent persona rules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_persona_rules as pr  # noqa: E402
import project_automation as auto  # noqa: E402


class TestPeerPersonaRules(unittest.TestCase):
    def test_all_agent_roles_have_persona(self) -> None:
        issues = pr.validate_persona_coverage()
        self.assertEqual(issues, [], msg="; ".join(issues))

    def test_shard_inherits_base(self) -> None:
        self.assertEqual(pr.base_role_id("factory_engineer_L3"), "factory_engineer")
        rules = pr.get_persona_rules("verify_runner_L2")
        self.assertIsNotNone(rules)
        assert rules is not None
        self.assertEqual(rules.role_id, "verify_runner")

    def test_verify_runner_must_not_edit(self) -> None:
        rules = pr.get_persona_rules("verify_runner")
        assert rules is not None
        block = rules.format_block()
        self.assertIn("MUST NOT", block)
        self.assertIn("Edit implementation", block)

    def test_command_builder_allowed_files(self) -> None:
        rules = pr.get_persona_rules("command_builder")
        assert rules is not None
        text = " ".join(rules.must)
        self.assertIn("peer_commands.py", text)

    def test_format_fallback(self) -> None:
        block = pr.format_persona_rules_block("unknown_role_xyz", fallback_job_title="Test")
        self.assertIn("Persona rules", block)


if __name__ == "__main__":
    unittest.main()
