"""Tests for CLEAN FP4 expert RSS/mmap smoke (no nvidia-fs/GDS).

OVERSEER_T0_SMOKE_UNITTEST_2026_09_04 — hub unittest for smoke harness
(gds_forbidden_ok + separate prompt_tok_s vs accepted_writing_tok_s).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import bitnet_fp4_expert_rss_smoke as smoke  # noqa: E402
import project_automation as auto  # noqa: E402


class CleanFp4ExpertRssMmapSmokeTests(unittest.TestCase):
    """OVERSEER_CLEAN_FP4_EXPERT_RSS_MMAP_SMOKE_2026_09_04
    OVERSEER_T0_SMOKE_UNITTEST_2026_09_04
    """

    def test_land_proof_needle_present(self) -> None:
        src = (SCRIPTS / "bitnet_fp4_expert_rss_smoke.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_CLEAN_FP4_EXPERT_RSS_MMAP_SMOKE_2026_09_04", src)
        self.assertIn("no nvidia-fs/GDS", src)
        self.assertIn("accepted_writing_tok_s", src)
        self.assertIn("prompt_tok_s", src)
        self.assertIn("mmap", src)

    def test_t0_smoke_unittest_needle(self) -> None:
        here = Path(__file__).read_text(encoding="utf-8")
        self.assertIn("OVERSEER_T0_SMOKE_UNITTEST_2026_09_04", here)
        self.assertTrue(auto._t0_smoke_unittest_landed())

    def test_forbidden_modules_exclude_gds(self) -> None:
        for name in ("nvidia_fs", "nvidia-fs", "cufile"):
            self.assertIn(name, smoke.FORBIDDEN_MODULES)
        self.assertTrue(smoke.assert_no_gds_imports())

    def test_fp4_pack_size(self) -> None:
        blob = smoke.pack_fp4_expert(4096)
        self.assertEqual(len(blob), 2048)  # 0.5 B/param

    def test_run_smoke_separates_meters(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fp4_test_") as td:
            meters = smoke.run_smoke(Path(td))
        self.assertGreater(meters.prompt_tok_s, 0.0)
        self.assertGreater(meters.accepted_writing_tok_s, 0.0)
        self.assertEqual(meters.n_experts, smoke.TOY_N_EXPERTS)
        self.assertEqual(meters.expert_bytes_mmap, smoke.BYTES_PER_EXPERT * smoke.TOY_N_EXPERTS)
        self.assertTrue(meters.gds_forbidden_ok)
        # Distinct keys — never a single conflated tok/s field.
        keys = set(smoke.iter_meter_keys())
        self.assertEqual(keys, {"prompt_tok_s", "accepted_writing_tok_s"})
        self.assertNotEqual(meters.prompt_tok_s, meters.accepted_writing_tok_s)

    def test_cli_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fp4_cli_") as td:
            rc = smoke.main(["--json", "--dir", td])
        self.assertEqual(rc, 0)

    def test_land_proof_closes_efficiency_queue_title(self) -> None:
        title = (
            "[efficiency-research] CLEAN FP4 expert RSS/mmap smoke under scripts/ "
            "(no nvidia-fs/GDS; meter prompt tok/s vs accepted Writing separately)."
        )
        self.assertTrue(auto._land_proof_present(title))

    def test_land_proof_closes_peer_loop_cursor_agent_exit_twin(self) -> None:
        title = (
            "[kit] peer_loop: after cursor-agent exit, if Active open=0 under "
            "self_sufficient, seed before returning to kqueue wait (scripts/peer_loop.py)."
        )
        self.assertTrue(auto._land_proof_present(title))

    def test_land_proof_closes_t0_unittest_queue_title(self) -> None:
        title = (
            "[kit] BitNet T0: unittest scripts/bitnet_fp4_expert_rss_smoke.py "
            "(gds_forbidden_ok + separate prompt_tok_s vs accepted_writing_tok_s; "
            "tests/test_bitnet_fp4_expert_rss_smoke.py)."
        )
        self.assertTrue(auto._land_proof_present(title))


if __name__ == "__main__":
    unittest.main()
