#!/usr/bin/env python3
"""Tests for amnesia-combat MVPs: auditor, quiz, health, episodic."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import peer_memory_auditor as auditor  # noqa: E402
import peer_memory_episodic as episodic  # noqa: E402
import peer_memory_health as health  # noqa: E402
import peer_memory_quiz as quiz  # noqa: E402


class MemoryAuditorTests(unittest.TestCase):
    def test_cited_claim_with_sot_needle(self) -> None:
        result = auditor.audit_claims(
            ["NO PAY free desktop only — see AGENTS.md"],
        )
        self.assertGreaterEqual(result["cited"], 1)
        self.assertEqual(result["rows"][0]["status"], "CITED")

    def test_uncited_gibberish(self) -> None:
        result = auditor.audit_claims(
            ["Zxqplorf9WaffleQ completely invented widgetron999 without any citation"],
        )
        self.assertEqual(result["uncited"], 1)
        self.assertFalse(result["ok"])
        self.assertIn("heal", (result.get("heal_hint") or "").lower())

    def test_extract_overseer_needle(self) -> None:
        needles = auditor.extract_needles(
            "See OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07 in notes"
        )
        self.assertIn("OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07", needles)

    def test_cli_claim_exit(self) -> None:
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = auditor.main(["--claim", "WORK_QUEUE Active items", "--json"])
        self.assertIn(code, (0, 1))
        self.assertIn("cited", buf.getvalue().lower())


class MemoryQuizTests(unittest.TestCase):
    def test_self_check_passes_structural(self) -> None:
        result = quiz.run_self_check()
        self.assertTrue(result["ok"], msg=json.dumps(result, indent=2)[:800])
        ids = {r["id"] for r in result["rows"]}
        self.assertIn("no_pay", ids)
        self.assertIn("pack_additive", ids)

    def test_grade_active_open_count(self) -> None:
        n = quiz._active_open_count()
        ok = quiz.grade_answers({"active_open_count": str(n)})
        self.assertTrue(ok["ok"])
        bad = quiz.grade_answers({"active_open_count": str(n + 99)})
        self.assertFalse(bad["ok"])
        self.assertIn("heal", (bad.get("heal_hint") or "").lower())

    def test_list_questions(self) -> None:
        qs = quiz.list_questions()
        self.assertGreaterEqual(len(qs), 5)


class MemoryHealthTests(unittest.TestCase):
    def test_build_health_has_fields(self) -> None:
        h = health.build_memory_health()
        self.assertIn("pack", h)
        self.assertIn("verify_ok", h)
        self.assertIn("prefer_librarian", h)
        self.assertIn("hot_stale_vs_span", h)
        self.assertIn("memory_span", h)
        self.assertIn("hot", h)
        self.assertIsInstance(h["prefer_librarian"], bool)

    def test_hot_stale_detection(self) -> None:
        now = 1_000_000.0
        with mock.patch.object(health, "_mtime") as mt:

            def side(path: Path) -> float | None:
                if path == health.HOT_PATH:
                    return now - 10_000
                if path == health.SPAN_PATH:
                    return now - 100
                if path == health.PACK_PATH:
                    return now - 50
                return None

            mt.side_effect = side
            with mock.patch.object(
                health,
                "resolve_verify_ok",
                return_value=(True, "mock", {}),
            ):
                with mock.patch(
                    "peer_fact_librarian.should_prefer_librarian",
                    return_value=(True, "mock prefer"),
                ):
                    h = health.build_memory_health(now=now)
        self.assertTrue(h["hot_stale_vs_span"])
        self.assertFalse(h["ok"])


class EpisodicTests(unittest.TestCase):
    def test_append_get_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "episodic_by_cycle.jsonl"
            with mock.patch.object(episodic, "STORE_PATH", store):
                with mock.patch.object(episodic.pmc, "ARTIFACT_DIR", Path(tmp)):
                    row = episodic.append_episode(
                        cycle_id="C_TEST_1",
                        note="unit test episode",
                        paths=["notes/WORK_QUEUE.md"],
                    )
                    self.assertEqual(row["cycle_id"], "C_TEST_1")
                    got = episodic.get_by_cycle("C_TEST_1")
                    self.assertEqual(len(got), 1)
                    self.assertEqual(got[0]["note"], "unit test episode")
                    self.assertEqual(len(episodic.tail(5)), 1)


if __name__ == "__main__":
    unittest.main()
