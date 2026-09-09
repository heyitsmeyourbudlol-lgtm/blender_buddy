#!/usr/bin/env python3
"""dgx_utilization fill/pool must clamp to max_parallel_peers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
# Prefer this worktree's scripts; fall back to hub (DGX stack may live only there).
HUB = ROOT
if ".worktrees" in ROOT.parts:
    HUB = Path(*ROOT.parts[: ROOT.parts.index(".worktrees")])
if (HUB / "scripts").is_dir():
    sys.path.insert(0, str(HUB / "scripts"))
if (ROOT / "scripts" / "dgx_utilization.py").is_file():
    sys.path.insert(0, str(ROOT / "scripts"))

import dgx_utilization as util  # noqa: E402


class UtilizationPeerClampTests(unittest.TestCase):
    def test_target_agent_fill_clamps_to_max_parallel_peers(self) -> None:
        """Stale target_agent_fill:48 with peers=8 must not nudge toward 48."""
        cfg = {
            "max_parallel_peers": 8,
            "dgx_utilization": {"target_agent_fill": 48, "worktree_pool": 48},
            "factory_grid": {"hub_agents": 48, "global_agents": 48},
        }
        with mock.patch.object(util.auto, "CFG", cfg):
            self.assertEqual(util.target_agent_fill(), 8)
            self.assertEqual(util.worktree_pool_size(), 8)

    def test_worktree_pool_respects_peers_below_eight(self) -> None:
        """Former max(8, raw) floor must not ignore a smaller peer cap."""
        cfg = {
            "max_parallel_peers": 4,
            "dgx_utilization": {"worktree_pool": 48},
            "factory_grid": {},
        }
        with mock.patch.object(util.auto, "CFG", cfg):
            self.assertEqual(util.worktree_pool_size(), 4)

    def test_nudge_agents_uses_clamped_target(self) -> None:
        cfg = {
            "max_parallel_peers": 8,
            "dgx_utilization": {"target_agent_fill": 48, "hub_dispatch": False},
            "factory_grid": {"enabled": False},
        }
        with mock.patch.object(util.auto, "CFG", cfg), mock.patch.object(
            util.eff, "agent_count", return_value=8
        ), mock.patch.object(util.budget, "ram_mode", return_value="hold"), mock.patch.object(
            util.budget, "ram_agent_cap", return_value=48
        ), mock.patch.object(util.budget, "dispatch_allowed", return_value=True):
            report = util._nudge_agents(log_fn=lambda _m: None)
        self.assertEqual(report["target"], 8)
        self.assertTrue(report.get("at_cap"))
        self.assertFalse(report.get("nudged"))



class EnsureWorktreePoolPruneTests(unittest.TestCase):
    def test_overseer_ready_prune_needle_present(self) -> None:
        """OVERSEER_READY_PRUNE_2026_09_03 — hub-protect must see the land needle."""
        src = Path(util.__file__).read_text()
        self.assertIn("OVERSEER_READY_PRUNE_2026_09_03", src)
        # Regression: floor-ready early return must stay gone.
        self.assertNotIn('return {"pool": want, "target": want, "ready": True}', src)

    def test_floor_dirs_still_call_ensure_parallel_pool(self) -> None:
        """Ready floor (peer-0..7) must not skip ensure_parallel_pool / prune_excess."""
        cfg = {
            "max_parallel_peers": 8,
            "dgx_utilization": {"worktree_pool": 8},
            "factory_grid": {},
        }
        pool_root = Path("/hub/.worktrees")

        def fake_is_dir(self: Path) -> bool:  # noqa: ANN001
            name = self.name
            if name.startswith("peer-") and name[5:].isdigit():
                return int(name[5:]) < 8
            return True

        ensure = mock.Mock(return_value=[pool_root / f"peer-{i}" for i in range(8)])
        prune = mock.Mock(
            return_value={
                "found": 40,
                "removed": [f"/hub/.worktrees/peer-{i}" for i in range(8, 48)],
                "failed": [],
            }
        )
        with mock.patch.object(util.auto, "CFG", cfg), mock.patch.object(
            util.wt, "parallel_pool_config", return_value=(".worktrees", "peer")
        ), mock.patch.object(util, "ROOT", Path("/hub")), mock.patch.object(
            Path, "is_dir", fake_is_dir
        ), mock.patch.object(
            util.wt, "prune_excess_parallel_pool", prune
        ), mock.patch.object(util.wt, "ensure_parallel_pool", ensure):
            report = util._ensure_worktree_pool(log_fn=lambda _m: None)
        prune.assert_called_once()
        self.assertEqual(prune.call_args.kwargs.get("cap"), 8)
        ensure.assert_called_once()
        self.assertEqual(ensure.call_args.kwargs.get("count"), 8)
        self.assertEqual(report.get("pool"), 8)
        self.assertEqual(report.get("target"), 8)
        self.assertEqual(report.get("excess_found"), 40)
        self.assertEqual(report.get("excess_removed"), 40)
        self.assertTrue(report.get("ready"))


if __name__ == "__main__":
    unittest.main()
