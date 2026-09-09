"""Tests for N01 live dispatch hot path.

OVERSEER_NICHE_HOT_PATH_N01_2026_09_07
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import factory_niche_runtime as niche_rt  # noqa: E402
import niche_hot_path as nhp  # noqa: E402
import peer_orchestrate as po  # noqa: E402


class NicheHotPathTests(unittest.TestCase):
    """OVERSEER_NICHE_HOT_PATH_N01_2026_09_07"""

    def test_inventory_n01_n03_n08_ready(self) -> None:
        inv = nhp.inventory_ready()
        self.assertEqual(inv.get("hot_path"), "N01")
        self.assertEqual(inv.get("needle"), nhp.NEEDLE)
        by_id = {e["id"]: e for e in inv["experts"]}
        self.assertTrue(by_id["N01"]["ready"])
        self.assertTrue(by_id["N03"]["ready"])
        self.assertTrue(by_id["N08"]["ready"])
        self.assertGreaterEqual(inv["n_ready"], 3)

    def test_parse_queue_bullet_kit_scope_needle(self) -> None:
        line = (
            "- [ ] **[kit] peer_loop: IDLE seed** — file `scripts/peer_loop.py`; "
            "Needle: `OVERSEER_PEER_IDLE_SEED_LOG_LAST_RESORT_2026_09_04`."
        )
        parsed = nhp.parse_queue_bullet(line)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["niche_id"], "N01")
        self.assertTrue(parsed["kit"])
        self.assertEqual(parsed["scope"], "scripts/peer_loop.py")
        self.assertEqual(
            parsed["needle"], "OVERSEER_PEER_IDLE_SEED_LOG_LAST_RESORT_2026_09_04"
        )
        self.assertEqual(parsed["source"], "n01_practice")

    def test_parse_fail_closed_when_disabled(self) -> None:
        with mock.patch.dict(os.environ, {"FACTORY_NICHE_HOT_PATH": "0"}):
            self.assertIsNone(
                nhp.parse_queue_bullet(
                    "- [ ] **[kit] x** — `scripts/peer_loop.py` Needle: `OVERSEER_X`."
                )
            )

    def test_scope_hints_prefers_n01_then_backticks(self) -> None:
        item = (
            "- [ ] **[kit] Fix stall** — touch `scripts/peer_stall_pivot.py`; "
            "also see `scripts/peer_loop.py`; Needle: `OVERSEER_STALL_X_2026_09_07`."
        )
        scopes = po._scope_hints_from_item(item)
        self.assertTrue(scopes)
        # N01 primary scope leads; backtick extras still appended.
        self.assertIn("scripts/peer_stall_pivot.py", scopes)
        self.assertEqual(scopes[0], "scripts/peer_stall_pivot.py")

    def test_scope_hints_fail_closed_to_backticks(self) -> None:
        with mock.patch.object(nhp, "parse_queue_bullet", side_effect=RuntimeError("boom")):
            scopes = po._scope_hints_from_item("Foo (`scripts/peer_loop.py`) bar")
        self.assertEqual(scopes, ["scripts/peer_loop.py"])

    def test_mechanical_prompt_prefix(self) -> None:
        line = (
            "- [ ] **[kit] sync** — `scripts/peer_orchestrate.py` "
            "Needle: `OVERSEER_NICHE_HOT_PATH_N01_2026_09_07`."
        )
        block = po._n01_mechanical_prompt_prefix(line)
        self.assertIn("Mechanical N01 parse", block)
        self.assertIn("scripts/peer_orchestrate.py", block)
        self.assertIn("OVERSEER_NICHE_HOT_PATH_N01_2026_09_07", block)

    def test_assist_pre_dispatch_uses_n01_without_neural(self) -> None:
        logs: list[str] = []
        line = (
            "- [ ] **[kit] gate** — `scripts/peer_orchestrate.py` "
            "Needle: `OVERSEER_NICHE_HOT_PATH_N01_2026_09_07`."
        )
        with mock.patch.object(
            niche_rt, "_active_queue_lines", return_value=[line]
        ), mock.patch.object(
            niche_rt, "route_and_serve", side_effect=AssertionError("neural must not run")
        ):
            out = niche_rt.assist_pre_dispatch(log_fn=logs.append)
        self.assertEqual(out.get("n01_practice_hits"), 1)
        self.assertEqual(out["results"][0].get("source"), "n01_practice")
        self.assertTrue(any("N01 practice gate" in m for m in logs))

    def test_assist_pre_dispatch_fail_closed_to_neural(self) -> None:
        logs: list[str] = []
        line = "- [ ] mystery without paths"
        with mock.patch.object(
            niche_rt, "_active_queue_lines", return_value=[line]
        ), mock.patch.object(
            nhp, "parse_queue_bullet", return_value=None
        ), mock.patch.object(
            niche_rt,
            "route_and_serve",
            return_value={
                "best": {"niche_id": "N02", "label": "kit", "score": 0.9},
                "serves": [],
            },
        ) as route:
            out = niche_rt.assist_pre_dispatch(log_fn=logs.append)
        route.assert_called_once()
        self.assertEqual(out.get("n01_practice_hits"), 0)
        self.assertEqual(out["results"][0]["best"]["niche_id"], "N02")


if __name__ == "__main__":
    unittest.main()
