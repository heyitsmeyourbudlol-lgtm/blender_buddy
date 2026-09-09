#!/usr/bin/env python3
"""Tests for daily flaw-detection cross-review."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_flaw_scan as flaw  # noqa: E402
import peer_roles as roles  # noqa: E402


class TestPeerFlawScan(unittest.TestCase):
    def test_build_review_pairs_count(self) -> None:
        pool = roles.load_roles()
        pairs = flaw.build_review_pairs(pool[:8])
        self.assertEqual(len(pairs), 56)
        self.assertEqual(len({(p["reviewer_role_id"], p["target_role_id"]) for p in pairs}), 56)
        for p in pairs:
            self.assertNotEqual(p["reviewer_role_id"], p["target_role_id"])
            self.assertTrue(p["reviewer_title"].startswith("Flaw Detection Scanner +"))

    def test_build_review_pairs_hard_caps_catalog(self) -> None:
        """staff_all catalogs (50 roles) must still yield 56 pairs, not N×(N-1)."""
        pool = roles.load_roles()
        self.assertGreater(len(pool), 8)
        pairs = flaw.build_review_pairs(pool)
        self.assertEqual(len(pairs), flaw.FLAW_SCAN_PAIR_TOTAL)
        self.assertEqual(len(pairs), 56)

    def test_normalize_bloated_round_advances_to_triage(self) -> None:
        """Live bug: 46×45=2070 pairs left scanning forever despite 56 done reviews."""
        with tempfile.TemporaryDirectory() as tmp:
            rnd_path = Path(tmp) / "round.json"
            st_path = Path(tmp) / "state.json"
            pool8 = roles.load_roles()[:8]
            all_roles = roles.load_roles()
            self.assertGreater(len(all_roles), 8)
            bloated = all_roles  # full catalog — historically inflated start_round
            # Simulate historical catalog bloat N×(N-1) that bypassed the hard-cap helper:
            pairs = []
            for reviewer in bloated:
                for target in bloated:
                    if reviewer.id == target.id:
                        continue
                    pairs.append(
                        {
                            "reviewer_role_id": reviewer.id,
                            "reviewer_title": flaw.scanner_title(reviewer),
                            "target_role_id": target.id,
                            "target_job_title": target.job_title,
                            "status": "pending",
                            "review": None,
                        }
                    )
            self.assertEqual(len(pairs), len(bloated) * (len(bloated) - 1))
            self.assertGreater(len(pairs), flaw.FLAW_SCAN_PAIR_TOTAL)
            # Mark the canonical 8×7 reviews done
            body = "### REVIEW\n- Flaws: none\n- Severity: low"
            for reviewer in pool8:
                for target in pool8:
                    if reviewer.id == target.id:
                        continue
                    for p in pairs:
                        if p["reviewer_role_id"] == reviewer.id and p["target_role_id"] == target.id:
                            p["status"] = "done"
                            p["review"] = body
                            break
            subjects = [
                {
                    "role_id": r.id,
                    "job_title": r.job_title,
                    "reviews_received": [],
                    "triage": None,
                    "upgrades_accepted": [],
                    "downgrades_rejected": [],
                }
                for r in bloated
            ]
            rnd = {
                "version": 1,
                "round_date": "2026-09-07",
                "phase": flaw.PHASE_SCAN,
                "pairs": pairs,
                "subjects": subjects,
            }
            with mock.patch.object(flaw, "ROUND_PATH", rnd_path):
                with mock.patch.object(flaw, "STATE_PATH", st_path):
                    rnd_path.write_text(json.dumps(rnd), encoding="utf-8")
                    self.assertTrue(flaw._scan_complete(rnd))
                    self.assertFalse(all(p["status"] == "done" for p in pairs))
                    flaw._maybe_advance_phase(rnd)
                    saved = json.loads(rnd_path.read_text(encoding="utf-8"))
                    self.assertEqual(saved["phase"], flaw.PHASE_TRIAGE)
                    self.assertEqual(len(saved["pairs"]), 56)
                    self.assertEqual(len(saved["subjects"]), 8)
                    done = sum(1 for p in saved["pairs"] if p["status"] == "done")
                    self.assertEqual(done, 56)
                    for s in saved["subjects"]:
                        self.assertEqual(len(s["reviews_received"]), 7)

    def test_record_review_and_advance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rnd_path = Path(tmp) / "round.json"
            st_path = Path(tmp) / "state.json"
            with mock.patch.object(flaw, "ROUND_PATH", rnd_path):
                with mock.patch.object(flaw, "STATE_PATH", st_path):
                    flaw.start_round(force=True)
                    ok = flaw.record_review("factory_engineer", "verify_runner", "Add cache to verify gate")
                    self.assertTrue(ok)
                    rnd = json.loads(rnd_path.read_text())
                    done = sum(1 for p in rnd["pairs"] if p["status"] == "done")
                    self.assertEqual(done, 1)
                    self.assertEqual(len(rnd["pairs"]), 56)
                    vr = next(s for s in rnd["subjects"] if s["role_id"] == "verify_runner")
                    self.assertEqual(len(vr["reviews_received"]), 1)

    def test_normalize_round_collapses_staff_all_bloat(self) -> None:
        """OVERSEER_FLAW_SCAN_POOL_CAP_8_2026_09_07 — 2070→56; unlock triage."""
        with tempfile.TemporaryDirectory() as tmp:
            rnd_path = Path(tmp) / "round.json"
            st_path = Path(tmp) / "state.json"
            with mock.patch.object(flaw, "ROUND_PATH", rnd_path):
                with mock.patch.object(flaw, "STATE_PATH", st_path):
                    with mock.patch.object(flaw, "REVIEWS_DIR", Path(tmp) / "reviews"):
                        flaw.start_round(force=True)
                        rnd = json.loads(rnd_path.read_text())
                        # Inject catalog bloat (staff_all-style extra pairs).
                        for extra in ("safety_auditor", "command_builder", "output_researcher"):
                            rnd["pairs"].append(
                                {
                                    "reviewer_role_id": extra,
                                    "target_role_id": "factory_engineer",
                                    "status": "pending",
                                    "review": None,
                                }
                            )
                            rnd["subjects"].append(
                                {
                                    "role_id": extra,
                                    "job_title": extra,
                                    "reviews_received": [],
                                    "triage": None,
                                }
                            )
                        # Mark all hub 8×7 pairs done.
                        for pair in rnd["pairs"]:
                            if pair["reviewer_role_id"] in {
                                r.id for r in flaw._scan_pool()
                            } and pair["target_role_id"] in {
                                r.id for r in flaw._scan_pool()
                            }:
                                pair["status"] = "done"
                                pair["review"] = f"ok {pair['reviewer_role_id']}→{pair['target_role_id']}"
                        rnd_path.write_text(json.dumps(rnd))
                        self.assertGreater(len(rnd["pairs"]), 56)
                        out = flaw.normalize_round(save=True)
                        assert out is not None
                        self.assertEqual(len(out["pairs"]), 56)
                        self.assertEqual(len(out["subjects"]), 8)
                        done = sum(1 for p in out["pairs"] if p["status"] == "done")
                        self.assertEqual(done, 56)
                        flaw._maybe_advance_phase(out)
                        reloaded = json.loads(rnd_path.read_text())
                        self.assertEqual(reloaded["phase"], flaw.PHASE_TRIAGE)

    def test_scanner_title(self) -> None:
        role = roles.load_roles()[0]
        self.assertIn(role.job_title, flaw.scanner_title(role))

    def test_should_dispatch_after_daily_time(self) -> None:
        cfg = flaw.FlawScanConfig(enabled=True, daily_time="00:00", min_hour=0, min_minute=0)
        with mock.patch.object(flaw, "load_config", return_value=cfg):
            with mock.patch.object(flaw, "load_state", return_value={}):
                with mock.patch.object(flaw, "load_round", return_value=None):
                    with mock.patch.object(flaw, "start_round", return_value={"phase": flaw.PHASE_SCAN}):
                        self.assertTrue(flaw.should_dispatch_flaw_scan())

    def test_compile_ingests_hub_reviews_when_namespace_empty(self) -> None:
        """Peer namespace REVIEWS_DIR missing → still compile from HUB_REVIEWS_DIR."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            rnd_path = tmp_path / "round.json"
            st_path = tmp_path / "state.json"
            local_reviews = tmp_path / "local-reviews"  # intentionally absent
            hub_reviews = tmp_path / "hub-reviews"
            hub_reviews.mkdir()
            pool8 = roles.load_roles()[:8]
            body = (
                "### REVIEW:target\n- Flaws: path drift\n"
                "- Efficiency upgrades: compile hub fallback\n"
                "- Holistic advice: one SoT\n- Severity: med"
            )
            for reviewer in pool8:
                for target in pool8:
                    if reviewer.id == target.id:
                        continue
                    (hub_reviews / f"{reviewer.id}__{target.id}.md").write_text(
                        body.replace("target", target.id), encoding="utf-8"
                    )
            with mock.patch.object(flaw, "ROUND_PATH", rnd_path):
                with mock.patch.object(flaw, "STATE_PATH", st_path):
                    with mock.patch.object(flaw, "REVIEWS_DIR", local_reviews):
                        with mock.patch.object(flaw, "HUB_REVIEWS_DIR", hub_reviews):
                            flaw.start_round(force=True)
                            n = flaw.compile_from_review_files()
                            self.assertEqual(n, 56)
                            st = flaw.status_dict()
                            self.assertEqual(st["round"]["reviews_done"], 56)
                            self.assertEqual(st["round"]["phase"], flaw.PHASE_TRIAGE)

    def test_format_scanner_task_uses_reviews_dir(self) -> None:
        role = roles.load_roles()[0]
        text = flaw._format_scanner_task(role, [])
        self.assertIn(str(flaw.REVIEWS_DIR), text)
        self.assertIn(str(flaw.HUB_REVIEWS_DIR), text)


if __name__ == "__main__":
    unittest.main()
