"""Arith prefilter — research_claim_arith (S06/S14).

OVERSEER_RESEARCH_CLAIM_ARITH_2026_09_08
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import research_claim_arith as rca  # noqa: E402


class ResearchClaimArithTests(unittest.TestCase):
    """OVERSEER_RESEARCH_CLAIM_ARITH_2026_09_08"""

    def test_needle_and_training_doc(self) -> None:
        src = (SCRIPTS / "research_claim_arith.py").read_text(encoding="utf-8")
        self.assertIn(rca.NEEDLE, src)
        research = (ROOT / "notes/RESEARCH_SPEED_TRAINING.md").read_text(encoding="utf-8")
        self.assertIn("research_claim_arith.py", research)

    def test_albert_matches_t0_geometry(self) -> None:
        row = rca.albert_closed_form(100_000)
        self.assertTrue(row.passed)
        self.assertEqual(row.u_unique, 1200)  # B=1000 + L*r*2 = 1000+200
        self.assertGreaterEqual(row.s_arith, rca.MIN_ARITH)
        self.assertEqual(row.quality, "UNKNOWN")

    def test_hive_matches_t0_geometry(self) -> None:
        row = rca.hive_closed_form(100_000)
        self.assertTrue(row.passed)
        # U = 100000/100 + 2 = 1002
        self.assertEqual(row.u_unique, 1002)
        self.assertGreaterEqual(row.s_arith, rca.MIN_ARITH)

    def test_fail_closed_low_share(self) -> None:
        # Huge LoRA rank → S collapses below MIN_ARITH
        row = rca.share_rank_closed_form(100_000, k=2, r=64)
        self.assertFalse(row.passed)
        self.assertIsNotNone(row.contradiction)
        self.assertLess(row.s_arith, rca.MIN_ARITH)

    def test_raw_fail_closed_zero_u(self) -> None:
        row = rca.raw_closed_form(1e6, 0)
        self.assertFalse(row.passed)
        self.assertIn("u_unique", row.contradiction or "")

    def test_scaffold_claim_range(self) -> None:
        stubs = rca.scaffold_rows(200, 202, stacks=[rca.albert_closed_form(100_000)])
        self.assertEqual([s["id"] for s in stubs], ["C200", "C201", "C202"])
        self.assertTrue(all(s["verdict"] == "UNKNOWN" for s in stubs))
        self.assertTrue(all(s["peer_range"] == "C200-C202" for s in stubs))

    def test_probe_before_after_speedup(self) -> None:
        # Tiny sleep so unittest stays fast; still must show cull win.
        probe = rca.probe_prefilter_vs_full(quality_proxy_ms=0.02)
        self.assertGreater(probe["after_reject"], 0)
        self.assertGreaterEqual(probe["approx_speedup"], 1.2)
        self.assertFalse(probe["train_unlocked"])
        self.assertEqual(probe["needle"], rca.PROBE_NEEDLE)

    def test_ensure_and_check_cache(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "claim_arith_report.json"
            payload = rca.build_default_report()
            rca.write_json(path, payload)
            hit = rca.check_cache(path)
            self.assertTrue(hit["ok"])
            self.assertTrue(hit["hit"])
            # Corrupt fp → MISS
            bad = dict(payload)
            bad["fp"] = "deadbeef"
            rca.write_json(path, bad)
            miss = rca.check_cache(path)
            self.assertFalse(miss["ok"])

    def test_cli_probe_write(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "probe.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "research_claim_arith.py"),
                    "--probe",
                    "--write",
                    "--quality-proxy-ms",
                    "0.02",
                    "--out",
                    str(out),
                    "--json",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout)
            self.assertGreaterEqual(data["approx_speedup"], 1.2)
            self.assertTrue(out.is_file())


if __name__ == "__main__":
    unittest.main()
