#!/usr/bin/env python3
"""Tests for lessons curator — lossless squeeze / harvest."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_lessons as lessons  # noqa: E402


class TestPeerLessons(unittest.TestCase):
    def test_fact_key_same_needle_merges(self) -> None:
        n = "OVERSEER_LESSONS_CURATOR_2026_09_06"
        a = lessons.fact_key(f"{n} stall heal ram", needle=n)
        b = lessons.fact_key(f"{n} different prose agents=99", needle=n)
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("needle:"))

    def test_normalize_paths_lossless(self) -> None:
        t = lessons.normalize_text("/Users/togi/Automation/scripts/peer_loop.py  woke")
        self.assertIn("~/Automation/scripts/peer_loop.py", t)
        self.assertIn("woke", t)

    def test_squeeze_preserves_distinct_needles(self) -> None:
        f1 = lessons.LessonFact(
            key="needle:OVERSEER_A_2026_09_06",
            text="OVERSEER_A_2026_09_06 first lesson",
            needle="OVERSEER_A_2026_09_06",
            hit_count=1,
        )
        f2 = lessons.LessonFact(
            key="needle:OVERSEER_B_2026_09_06",
            text="OVERSEER_B_2026_09_06 second lesson",
            needle="OVERSEER_B_2026_09_06",
            hit_count=1,
        )
        f1b = lessons.LessonFact(
            key="needle:OVERSEER_A_2026_09_06",
            text="OVERSEER_A_2026_09_06 first lesson with more detail here",
            needle="OVERSEER_A_2026_09_06",
            hit_count=2,
        )
        out, report = lessons.squeeze_facts([f1, f2, f1b])
        self.assertTrue(report["facts_preserved"])
        needles = {f.needle for f in out}
        self.assertEqual(needles, {"OVERSEER_A_2026_09_06", "OVERSEER_B_2026_09_06"})
        self.assertEqual(len(out), 2)
        self.assertLessEqual(report["bytes_after"], report["bytes_before"])
        a = next(f for f in out if f.needle.endswith("_A_2026_09_06"))
        self.assertGreaterEqual(a.hit_count, 3)

    def test_squeeze_never_drops_sha_keys(self) -> None:
        facts = [
            lessons.LessonFact(key="sha:aaaa", text="unique alpha fact about adapt_stale"),
            lessons.LessonFact(key="sha:bbbb", text="unique beta fact about plan_gate"),
            lessons.LessonFact(
                key="sha:aaaa",
                text="unique alpha fact about adapt_stale again",
                hit_count=1,
            ),
        ]
        out, report = lessons.squeeze_facts(facts)
        self.assertTrue(report["facts_preserved"])
        self.assertEqual({f.key for f in out}, {"sha:aaaa", "sha:bbbb"})

    def test_watchdog_fold_keeps_needle(self) -> None:
        n = "OVERSEER_COMPRESSION_RESULT_WATCH_2026_09_06"
        long = (
            f"WATCHDOG: results stalled — diagnose next gate (2026-09-06 09:10Z) {n} "
            + ("x" * 200)
        )
        text = lessons.normalize_text(f"{n} · {long[:120]}")
        self.assertIn(n, text)
        key = lessons.fact_key(text, needle=n)
        self.assertEqual(key, f"needle:{n}")

    def test_to_dense_includes_hits(self) -> None:
        f = lessons.LessonFact(
            key="needle:OVERSEER_X_2026_09_06",
            text="OVERSEER_X_2026_09_06 body text",
            needle="OVERSEER_X_2026_09_06",
            hit_count=5,
        )
        d = f.to_dense()
        self.assertIn("OVERSEER_X_2026_09_06", d)
        self.assertIn("hits=5", d)

    def test_rewrite_preserves_existing_needles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            learnings = tmp_path / "project-learnings.jsonl"
            rows = [
                {
                    "role_id": "factory_engineer",
                    "text": "OVERSEER_KEEP_ME_2026_09_06 unique keep",
                    "ts": 1.0,
                },
                {
                    "role_id": "factory_engineer",
                    "text": "OVERSEER_KEEP_ME_2026_09_06 unique keep again agents=3",
                    "ts": 2.0,
                },
                {
                    "role_id": "verify_runner",
                    "text": "OVERSEER_OTHER_2026_09_06 other fact",
                    "ts": 3.0,
                },
            ]
            learnings.write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            import peer_project_learning as pl

            with mock.patch.object(pl, "SHARED_LEARNINGS_JSONL", learnings):
                with mock.patch.object(
                    pl, "write_project_learning_md", return_value=tmp_path / "PL.md"
                ):
                    report = lessons.rewrite_shared_learnings_squeezed([], write=True)
            self.assertTrue(report["facts_preserved"])
            self.assertLessEqual(report["rows_after"], report["rows_before"])
            text = learnings.read_text(encoding="utf-8")
            self.assertIn("OVERSEER_KEEP_ME_2026_09_06", text)
            self.assertIn("OVERSEER_OTHER_2026_09_06", text)


if __name__ == "__main__":
    unittest.main()
