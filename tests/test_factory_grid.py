#!/usr/bin/env python3
"""Tests for factory grid config."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import factory_grid as fg  # noqa: E402


class FactoryGridTests(unittest.TestCase):
    def test_caps_from_config(self) -> None:
        cfg = {
            "factory_grid": {
                "enabled": True,
                "hub_agents": 32,
                "external_agents": 16,
                "global_agents": 48,
            },
            # Pool must be ≥ hub_agents or hub_agent_cap clamps (see clamp test).
            "max_parallel_peers": 32,
        }
        with mock.patch.object(fg.auto, "CFG", cfg):
            self.assertEqual(fg.hub_agent_cap(), 32)
            self.assertEqual(fg.external_agent_cap(), 16)
            # global_agents clamped to max_parallel_peers (48→32)
            self.assertEqual(fg.global_agent_cap(), 32)

    def test_hub_agent_cap_clamps_to_max_parallel_peers(self) -> None:
        """hub_agents 32/48 must not outrun the worktree pool (extras → cwd=ROOT)."""
        cfg = {
            "factory_grid": {"hub_agents": 48},
            "max_parallel_peers": 8,
        }
        with mock.patch.object(fg.auto, "CFG", cfg):
            self.assertEqual(fg.hub_agent_cap(), 8)
        cfg32 = {
            "factory_grid": {"hub_agents": 32},
            "max_parallel_peers": 8,
        }
        with mock.patch.object(fg.auto, "CFG", cfg32):
            self.assertEqual(fg.hub_agent_cap(), 8)

    def test_global_agent_cap_clamps_to_max_parallel_peers(self) -> None:
        cfg = {
            "factory_grid": {"global_agents": 48},
            "max_parallel_peers": 8,
        }
        with mock.patch.object(fg.auto, "CFG", cfg):
            self.assertEqual(fg.global_agent_cap(), 8)

    def test_sprint_interval_floors_hyper_overlay(self) -> None:
        """DGX factory_grid.interval_sec=8 must not restore sub-15s sprint poll."""
        cfg = {"factory_grid": {"interval_sec": 8}}
        with mock.patch.object(fg.auto, "CFG", cfg):
            self.assertGreaterEqual(fg.sprint_interval_sec(), 15.0)
        cfg3 = {"factory_grid": {"interval_sec": 3}}
        with mock.patch.object(fg.auto, "CFG", cfg3):
            self.assertGreaterEqual(fg.sprint_interval_sec(), 15.0)


if __name__ == "__main__":
    unittest.main()
