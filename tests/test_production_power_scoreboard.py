"""OVERSEER_SCOREBOARD_GH_FALLBACK_2026_09_07 · OVERSEER_NON_NOOP_DAY_ROLLUP_2026_09_07"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import peer_transcript as transcript
import production_power_scoreboard as sb


class ScoreboardGhFallbackTests(unittest.TestCase):
    def test_external_proof_fallback_counts_newdrop_prs(self) -> None:
        body = """# External proof

| # | Repo | Status | Verify | PR / merge | Date |
|---|------|--------|--------|------------|------|
| 3 | Newdrop (CaaS) | ok | ok | [#16](https://github.com/heyitsmeyourbudlol-lgtm/caas-changelog/pull/16) · [#22](https://github.com/heyitsmeyourbudlol-lgtm/caas-changelog/pull/22) | 2026-09-07 |

### 2026-09-07 Top10 — cookie
- PR: [#21](https://github.com/heyitsmeyourbudlol-lgtm/caas-changelog/pull/21) `abc`
"""
        with tempfile.TemporaryDirectory() as td:
            proof = Path(td) / "EXTERNAL_PROOF.md"
            proof.write_text(body, encoding="utf-8")
            with mock.patch.object(sb, "EXTERNAL_PROOF", proof):
                n, hits = sb._external_proof_merges_7d(fallback_note="gh missing")
        self.assertEqual(n, 3)
        self.assertTrue(any("#16" in h for h in hits))
        self.assertTrue(any("#21" in h for h in hits))
        self.assertTrue(any("#22" in h for h in hits))
        self.assertTrue(any("EXTERNAL_PROOF" in h for h in hits))

    def test_gh_oserror_falls_back_to_external_proof(self) -> None:
        body = (
            "### 2026-09-07 land\n"
            "- PR: https://github.com/heyitsmeyourbudlol-lgtm/caas-changelog/pull/18\n"
        )
        with tempfile.TemporaryDirectory() as td:
            proof = Path(td) / "EXTERNAL_PROOF.md"
            proof.write_text(body, encoding="utf-8")
            with mock.patch.object(sb, "EXTERNAL_PROOF", proof), mock.patch(
                "production_power_scoreboard.subprocess.run",
                side_effect=FileNotFoundError("gh"),
            ):
                n, hits = sb._gh_merges_7d()
        self.assertEqual(n, 1)
        self.assertTrue(any("#18" in h for h in hits))

    def test_render_includes_non_noop_day(self) -> None:
        snap = {
            "as_of": "2026-09-08 00:00 UTC",
            "merges_7d": "3",
            "merge_notes": "none",
            "daemons": "CLEAN up",
            "theater": "0%",
            "agent_cap": "8",
            "non_noop_day": "9 today · proj 12/day · week_avg 9 (bar ≥8) [PASS]",
        }
        block = sb.render_current_block(snap)
        self.assertIn("Non-noop cycles/day", block)
        self.assertIn("9 today", block)


class NonNoopDayRollupTests(unittest.TestCase):
    def test_seed_from_history_once(self) -> None:
        now = time.time()
        live = {
            "cycle_history": [
                {"ts": now - 10, "noop": False},
                {"ts": now - 5, "noop": True},
                {"ts": now - 1, "noop": False},
            ]
        }
        with tempfile.TemporaryDirectory() as td:
            side = Path(td) / "non_noop_by_day.json"
            with mock.patch.object(transcript, "NON_NOOP_DAY_PATH", side):
                transcript.seed_non_noop_day_from_history(live)
                day = transcript._utc_day_key(now)
                self.assertEqual(live["non_noop_by_day"][day], 2)
                # second seed is stable (max-merge)
                transcript.seed_non_noop_day_from_history(live)
                self.assertEqual(live["non_noop_by_day"][day], 2)

    def test_seed_skips_local_only(self) -> None:
        now = time.time()
        live = {
            "cycle_history": [
                {"ts": now - 10, "noop": False, "local_only": True},
                {"ts": now - 1, "noop": False, "local_only": False},
            ]
        }
        with tempfile.TemporaryDirectory() as td:
            side = Path(td) / "non_noop_by_day.json"
            with mock.patch.object(transcript, "NON_NOOP_DAY_PATH", side):
                transcript.seed_non_noop_day_from_history(live)
                day = transcript._utc_day_key(now)
                self.assertEqual(live["non_noop_by_day"][day], 1)
                transcript.bump_non_noop_day_rollup(
                    live, ts=now, noop=False, local_only=True
                )
                self.assertEqual(live["non_noop_by_day"][day], 1)

    def test_seed_and_bump_skip_deferred(self) -> None:
        now = time.time()
        live = {
            "cycle_history": [
                {"ts": now - 10, "noop": False, "local_only": False, "failure_type": "deferred"},
                {"ts": now - 1, "noop": False, "local_only": False},
            ]
        }
        with tempfile.TemporaryDirectory() as td:
            side = Path(td) / "non_noop_by_day.json"
            with mock.patch.object(transcript, "NON_NOOP_DAY_PATH", side):
                transcript.seed_non_noop_day_from_history(live)
                day = transcript._utc_day_key(now)
                self.assertEqual(live["non_noop_by_day"][day], 1)
                transcript.bump_non_noop_day_rollup(
                    live, ts=now, noop=False, local_only=False, failure_type="deferred"
                )
                self.assertEqual(live["non_noop_by_day"][day], 1)

    def test_thin_save_preserves_day_rollup(self) -> None:
        now = time.time()
        day = transcript._utc_day_key(now)
        rich = {"non_noop_by_day": {day: 5}, "last_cycle": {"ts": now, "verify_ok": True}}
        thin: dict = {"stall": True}
        with tempfile.TemporaryDirectory() as td:
            side = Path(td) / "non_noop_by_day.json"
            with mock.patch.object(transcript, "NON_NOOP_DAY_PATH", side):
                transcript._save_non_noop_day_sidecar({day: 3})
                note = transcript._merge_preserve_cycle_memory(thin, rich)
                self.assertIsNotNone(note)
                self.assertEqual(thin["non_noop_by_day"][day], 5)
                # wipe live buckets — sidecar+rich rehydrate
                wiped: dict = {"cycle_history": []}
                transcript.rehydrate_non_noop_day(wiped)
                self.assertEqual(wiped["non_noop_by_day"][day], 5)

    def test_bump_and_stats_meet_bar(self) -> None:
        live: dict = {}
        now = time.time()
        day = transcript._utc_day_key(now)
        with tempfile.TemporaryDirectory() as td:
            side = Path(td) / "non_noop_by_day.json"
            with mock.patch.object(transcript, "NON_NOOP_DAY_PATH", side):
                for _ in range(8):
                    transcript.bump_non_noop_day_rollup(live, ts=now, noop=False)
                transcript.bump_non_noop_day_rollup(live, ts=now, noop=True)
                self.assertEqual(live["non_noop_by_day"][day], 8)
                stats = transcript.non_noop_day_stats(live, now=now)
                self.assertEqual(stats["today_non_noop"], 8)
                self.assertTrue(stats["meets_bar"])

    def test_proj_alone_does_not_meet_bar(self) -> None:
        """T10-04: high projection must not false-PASS before ≥8 observed today."""
        live: dict = {}
        # 4h into UTC day → 4 observed projects to 24/day, still GAP.
        day_start = 1_725_760_000.0  # fixed UTC anchor
        now = day_start + 4.0 * 3600.0
        day = transcript._utc_day_key(now)
        with tempfile.TemporaryDirectory() as td:
            side = Path(td) / "non_noop_by_day.json"
            with mock.patch.object(transcript, "NON_NOOP_DAY_PATH", side):
                live["non_noop_by_day"] = {day: 4}
                stats = transcript.non_noop_day_stats(live, now=now)
                self.assertEqual(stats["today_non_noop"], 4)
                self.assertGreaterEqual(stats["projected_per_day"], 8.0)
                self.assertFalse(stats["meets_bar"])


if __name__ == "__main__":
    unittest.main()
