#!/usr/bin/env python3
"""Tests for factory_fanout path resolution and config."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import factory_fanout  # noqa: E402


class FactoryFanoutTests(unittest.TestCase):
    def test_resolve_translates_missing_mac_path(self) -> None:
        def fake_is_dir(self: Path) -> bool:
            return str(self).startswith("/home/arnavrastogi/")

        with mock.patch.object(
            factory_fanout,
            "_path_roots",
            return_value=(Path("/Users/togi"), Path("/home/arnavrastogi")),
        ), mock.patch.object(Path, "is_dir", fake_is_dir):
            got = factory_fanout.resolve_repo_path("/Users/togi/CPT")
            self.assertIsNotNone(got)
            self.assertTrue(str(got).endswith("arnavrastogi/CPT"))

    def test_status_filter_defaults(self) -> None:
        with mock.patch.object(factory_fanout, "_fanout_cfg", return_value={}):
            self.assertIn("unaudited", factory_fanout.status_filter())

    def test_load_candidates_skips_hub(self) -> None:
        registry = {
            "repos": [
                {"name": "Hub", "path": str(ROOT), "status": "unaudited"},
                {"name": "CPT", "path": "/Users/togi/CPT", "status": "unaudited"},
            ]
        }
        with mock.patch("factory_fanout.REGISTRY") as reg:
            reg.is_file.return_value = True
            reg.read_text.return_value = json.dumps(registry)
            with mock.patch.object(
                factory_fanout,
                "resolve_repo_path",
                side_effect=lambda p: None if str(ROOT) in p else Path("/remote/CPT"),
            ):
                items = factory_fanout.load_candidates()
                self.assertEqual(len(items), 1)
                self.assertEqual(items[0]["name"], "CPT")

    def test_write_cycle_log_persists(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            cycle = Path(td) / "fanout_cycle.json"
            hub = Path(td) / "factory-fanout.log"
            hub_cycle = Path(td) / "hub-cycle.json"
            with mock.patch.object(factory_fanout, "CYCLE_LOG", cycle), mock.patch.object(
                factory_fanout, "HUB_CYCLE_LOG", hub_cycle
            ), mock.patch.object(
                factory_fanout, "HUB_FANOUT_LOG", hub
            ), mock.patch.object(factory_fanout, "_cursor_agent_count", return_value=24), mock.patch.object(
                factory_fanout, "_worktree_pool_count", return_value=97
            ), mock.patch.object(
                factory_fanout.auto, "parallel_peer_floor", return_value=96
            ), mock.patch.object(
                factory_fanout.auto, "max_parallel_peers", return_value=8
            ):
                # Clear stale FANOUT so floor comes from parallel_peer_floor then clamp.
                import os

                os.environ.pop("FANOUT_RESPAWN_BELOW", None)
                path = factory_fanout.write_cycle_log(
                    {"ts": "2026-09-06T00:00:00+00:00", "candidates": 0, "ok": 0, "fail": 0, "results": []},
                    log_fn=lambda _m: None,
                )
                self.assertEqual(path, cycle)
                data = json.loads(cycle.read_text(encoding="utf-8"))
                self.assertTrue(data["verify_ok"])
                self.assertEqual(data["floor"], 8)  # 96 clamped to max_parallel_peers
                self.assertTrue(data["pool_ge_floor"])
                self.assertTrue(data["agents_ge_floor"])  # 24 >= 8 after clamp
                self.assertTrue(hub.is_file())

    def test_kd_agent_floor_clamps_stale_fanout_env(self) -> None:
        """OVERSEER_KD_FLOOR_CLAMP_MAX_PEERS_2026_09_08 — FANOUT=96 → floor=8."""
        import os

        with mock.patch.dict(os.environ, {"FANOUT_RESPAWN_BELOW": "96"}, clear=False), mock.patch.object(
            factory_fanout.auto, "max_parallel_peers", return_value=8
        ):
            self.assertEqual(factory_fanout._kd_agent_floor(), 8)

    def test_cursor_agent_count_ttl_hit(self) -> None:
        """OVERSEER_FANOUT_AGENT_COUNT_TTL_2026_09_08 — remiss HIT skips ps shell."""
        factory_fanout.clear_cursor_agent_count_cache()
        calls: list[str] = []

        def fake_getoutput(cmd: str) -> str:
            calls.append(cmd)
            return "7"

        with mock.patch("factory_fanout.subprocess.getoutput", side_effect=fake_getoutput):
            a = factory_fanout._cursor_agent_count()
            b = factory_fanout._cursor_agent_count()
            c = factory_fanout._cursor_agent_count(force=True)
        self.assertEqual((a, b, c), (7, 7, 7))
        self.assertEqual(len(calls), 2)  # miss + force; HIT no shell
        factory_fanout.clear_cursor_agent_count_cache()


if __name__ == "__main__":
    unittest.main()
