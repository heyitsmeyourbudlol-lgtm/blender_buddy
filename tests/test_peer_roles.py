#!/usr/bin/env python3
"""Tests for job-title role assignment."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_roles as roles  # noqa: E402
import project_automation as auto  # noqa: E402


class TestPeerRoles(unittest.TestCase):
    def test_assign_worker_pool_fills_floor_niches(self) -> None:
        cfg = auto.load_tasks_config()
        pool = roles.worker_pool_size(cfg)
        assigns = roles.assign_worker_pool(["**One queue item** — fix peer_loop"], cfg)
        self.assertGreaterEqual(len(assigns), pool)
        self.assertEqual(len({a.role.id for a in assigns[:pool]}), pool)
        niche_lines = [a for a in assigns if "niche" in a.item.lower()]
        self.assertGreaterEqual(len(niche_lines), 1)

    def test_worker_pool_ignores_peer_floor_48(self) -> None:
        cfg = auto.load_tasks_config()
        with mock.patch.object(auto, "parallel_peer_floor", return_value=48):
            with mock.patch.object(auto, "max_parallel_peers", return_value=48):
                with mock.patch.dict(auto.CFG, {"hub_worker_pool": 8}, clear=False):
                    self.assertEqual(roles.worker_pool_size(cfg), 8)
                    self.assertEqual(roles.DEFAULT_HUB_WORKER_POOL, 8)
                    assigns = roles.assign_worker_pool(
                        ["**One item**"], cfg, worker_count=roles.worker_pool_size(cfg)
                    )
                    # Hub may append idle niches; first N must still be the worker pool.
                    self.assertGreaterEqual(len(assigns), 8)
                    self.assertEqual(len({a.role.id for a in assigns[:8]}), 8)

    def test_hub_pool_assignments_clamps_to_ceiling(self) -> None:
        cfg = auto.load_tasks_config()
        pool = roles.worker_pool_size(cfg)
        raw = roles.assign_worker_pool(["**One queue item** — fix peer_loop"], cfg)
        hub = roles.hub_pool_assignments(raw, cfg)
        self.assertEqual(len(hub), pool)
        self.assertEqual(pool, auto.max_parallel_peers())
        self.assertLessEqual(pool, 24)  # OVERSEER_DGX_ROSTER_EXPAND_2026_09_05 ceiling
        self.assertTrue(all(not getattr(a, "standby", False) for a in hub))
        self.assertEqual(len({a.role.id for a in hub}), pool)

    def test_load_roles_from_config(self) -> None:
        cfg = auto.load_tasks_config()
        loaded = roles.load_roles(cfg)
        expected = len([r for r in (cfg.get("agent_roles") or []) if isinstance(r, dict)])
        self.assertEqual(len(loaded), expected)
        self.assertGreaterEqual(len(loaded), 8)
        titles = {r.job_title for r in loaded}
        self.assertIn("Factory Engineer", titles)

    def test_as_role_parses_prefer_remote_and_host(self) -> None:
        role = roles._as_role(
            {
                "id": "factory_engineer",
                "job_title": "Factory Engineer",
                "prefer_remote": "true",
                "host": "CLEAN",
                "strengths": ["factory"],
            }
        )
        assert role is not None
        self.assertTrue(role.prefer_remote)
        self.assertEqual(role.host, "CLEAN")

    def test_as_role_prefer_remote_false_strings(self) -> None:
        role = roles._as_role(
            {
                "id": "verify_runner",
                "job_title": "Verify Runner",
                "prefer_remote": "false",
                "strengths": ["test"],
            }
        )
        assert role is not None
        self.assertFalse(role.prefer_remote)
        self.assertEqual(role.host, "")

    def test_role_shard_copies_prefer_remote(self) -> None:
        base = roles.AgentRole(
            id="factory_engineer",
            job_title="Factory Engineer",
            subagent_type="generalPurpose",
            model="inherit",
            strengths=("factory",),
            responsibilities="Ship factory work.",
            prefer_remote=True,
            host="CLEAN",
        )
        shard = roles._role_shard(base, 1)
        self.assertTrue(shard.prefer_remote)
        self.assertEqual(shard.host, "CLEAN")
        self.assertEqual(shard.id, "factory_engineer_L2")

    def test_verify_item_routes_to_verify_runner(self) -> None:
        cfg = auto.load_tasks_config()
        loaded = roles.load_roles(cfg)
        asn = roles.pick_role(
            "**Fix failing unit tests** — run unittest self-check audit",
            loaded,
            template_peer="verify",
        )
        self.assertEqual(asn.role.id, "verify_runner")

    def test_external_proof_routes_to_integration_architect(self) -> None:
        cfg = auto.load_tasks_config()
        loaded = roles.load_roles(cfg)
        asn = roles.pick_role(
            "**External proof: adapt + native verify on RAM**",
            loaded,
            template_peer="implement",
        )
        self.assertEqual(asn.role.id, "integration_architect")

    def test_comms_item_routes_to_communications_engineer(self) -> None:
        cfg = auto.load_tasks_config()
        loaded = roles.load_roles(cfg)
        asn = roles.pick_role(
            "**[comms-improve] GLink validator** — enforce compact REQ/ACK on bus",
            loaded,
            template_peer="launch",
        )
        self.assertEqual(asn.role.id, "communications_engineer")

    def test_ram_item_routes_to_compression_engineer(self) -> None:
        cfg = auto.load_tasks_config()
        loaded = roles.load_roles(cfg)
        asn = roles.pick_role(
            "**Reduce RAM usage** — peer loop daemon memory hog; retain all features",
            loaded,
            template_peer="footprint",
        )
        self.assertEqual(asn.role.id, "compression_engineer")

    def test_roster_includes_comms_and_compression(self) -> None:
        cfg = auto.load_tasks_config()
        ids = {r.id for r in roles.load_roles(cfg)}
        self.assertIn("communications_engineer", ids)
        self.assertIn("compression_engineer", ids)
        self.assertNotIn("research_analyst", ids)
        self.assertNotIn("performance_tuner", ids)

    def test_orchestrator_block_mentions_job_titles(self) -> None:
        cfg = auto.load_tasks_config()
        loaded = roles.load_roles(cfg)
        assigns = roles.assign_items(
            ["**Dirty-tree hygiene**", "**External proof on CPT**"],
            cfg,
            template_peers=["verify", "implement"],
        )
        block = roles.format_orchestrator_assignment_block(assigns)
        self.assertIn("Orchestrator", block)
        self.assertIn("Job title", block)
        self.assertTrue(
            any(a.role.model for a in assigns),
            "assignments should include a model field",
        )
        self.assertIn(assigns[0].role.model, block)


if __name__ == "__main__":
    unittest.main()
