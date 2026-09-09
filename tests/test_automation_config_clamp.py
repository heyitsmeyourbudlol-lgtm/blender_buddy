"""cap_dgx_install_limits must clamp hub_worker_pool + top peer caps.

OVERSEER_HUB_WORKER_CLAMP_2026_09_04 — keep this module out of hub-protect
test_automation restore so the assert survives Mac/vault rewind.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import automation_config as ac  # noqa: E402


class CapDgxInstallLimitsTests(unittest.TestCase):
    def test_clamps_hub_worker_pool_and_peer_caps(self) -> None:
        out = ac.cap_dgx_install_limits(
            {
                "max_parallel_peers": 128,
                "parallel_peer_floor": 128,
                "max_parallel_agent_procs": 128,
                "hub_worker_pool": 128,
                "dgx_utilization": {
                    "target_agent_fill": 128,
                    "worktree_pool": 128,
                    "worktree_pool_size": 128,
                },
            }
        )
        self.assertEqual(out["max_parallel_peers"], 96)
        self.assertEqual(out["parallel_peer_floor"], 96)
        self.assertEqual(out["max_parallel_agent_procs"], 96)
        self.assertEqual(out["hub_worker_pool"], 96)
        self.assertEqual(out["dgx_utilization"]["target_agent_fill"], 96)
        self.assertEqual(out["dgx_utilization"]["worktree_pool"], 96)
        self.assertEqual(out["dgx_utilization"]["worktree_pool_size"], 96)

    def test_overlay_clamps_hub_worker_pool(self) -> None:
        overlay = {
            "max_parallel_peers": 128,
            "hub_worker_pool": 128,
            "factory_grid": {"hub_agents": 128, "global_agents": 128},
        }
        with tempfile.TemporaryDirectory(prefix="hub-clamp-") as tmp:
            root = Path(tmp)
            overlay_path = root / "scripts" / "dgx_speed.local.json"
            local_path = root / "automation.config.local.json"
            overlay_path.parent.mkdir(parents=True)
            overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
            local_path.write_text(
                json.dumps({"staff_all_niches": True, "hub_worker_pool": 12}),
                encoding="utf-8",
            )
            merged = ac.apply_dgx_speed_overlay(
                root=root, overlay_path=overlay_path, local_path=local_path
            )
        self.assertEqual(merged["max_parallel_peers"], 96)
        self.assertEqual(merged["hub_worker_pool"], 96)
        self.assertTrue(merged["staff_all_niches"])


if __name__ == "__main__":
    unittest.main()
