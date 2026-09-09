#!/usr/bin/env python3
"""Tests for agent mini apps layer."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_agent_mini_apps as ma  # noqa: E402


class TestPeerAgentMiniApps(unittest.TestCase):
    def test_block_includes_scaffold(self) -> None:
        block = ma.format_mini_apps_block(role_id="verify_runner")
        self.assertIn("mini app", block.lower())
        self.assertIn("agent_tools", block)

    def test_scaffold_and_register(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ma.AGENT_TOOLS_DIR = root / "agent_tools"
            ma.REGISTRY_PATH = root / "registry.json"
            ma.MINI_APPS_MD = root / "AGENT_MINI_APPS.md"
            path = ma.scaffold_mini_app("test_probe", purpose="Probe example")
            self.assertTrue(path.is_file())
            self.assertIn("--help", path.read_text(encoding="utf-8"))
            ma.register_mini_app("test_probe", purpose="Probe example", role_id="verify_runner")
            apps = ma.load_registry()
            self.assertEqual(len(apps), 1)
            self.assertEqual(apps[0]["name"], "test_probe")


if __name__ == "__main__":
    unittest.main()
