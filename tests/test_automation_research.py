"""Tests for automation_research — curated trends and web refresh."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import automation_research as ar  # noqa: E402


class ResearchCuratedTests(unittest.TestCase):
    def test_curated_trends_non_empty(self) -> None:
        self.assertGreaterEqual(len(ar.CURATED_TRENDS), 5)

    def test_trends_to_opportunities_skips_have(self) -> None:
        report = {"trends": [asdict(t) for t in ar.CURATED_TRENDS]}
        opps = ar.trends_to_opportunities(report)
        self.assertTrue(all("[trend]" in o["title"] for o in opps))
        self.assertTrue(all(o.get("kit_status") in ("gap", "partial") for o in opps))
        skipped_ids = {t.id for t in ar.CURATED_TRENDS if t.kit_status == "have"}
        self.assertIn("self_healing_ci", skipped_ids)
        self.assertIn("phase_orchestration", skipped_ids)
        self.assertIn("harness_memory", skipped_ids)
        opp_ids = {o.get("trend_id") for o in opps}
        self.assertTrue(skipped_ids.isdisjoint(opp_ids))
        for theme in (
            "Self-healing CI",
            "Phase-based orchestration",
            "Agent harness",
            "Event-driven agent wake",
        ):
            self.assertFalse(any(theme.lower() in o["title"].lower() for o in opps), theme)

    def test_kit_fingerprint_detects_status_drift(self) -> None:
        live = ar._kit_fingerprint(ar.CURATED_TRENDS)
        stale = dict(live)
        stale["self_healing_ci"] = "partial"
        self.assertNotEqual(live, stale)


class ResearchReportTests(unittest.TestCase):
    def test_build_report_without_network(self) -> None:
        report = ar.build_trend_report(refresh=False, persist=False)
        self.assertGreater(report["curated_count"], 0)
        self.assertIn("trends", report)

    def test_format_report_includes_gaps(self) -> None:
        report = ar.build_trend_report(refresh=False, persist=False)
        text = ar.format_report(report)
        self.assertIn("Kit mapping", text)
        self.assertIn("worktree", text.lower())
        # have-status themes must not appear as actionable gaps
        self.assertNotIn("Self-healing", text)
        self.assertNotIn("Phase-based", text)


class ResearchFetchTests(unittest.TestCase):
    def test_refresh_uses_fetch(self) -> None:
        fake = [ar.Headline(title="Test story", url="https://example.com", source="hn", points=10)]
        with mock.patch.object(ar, "refresh_web_headlines", return_value=fake):
            report = ar.build_trend_report(refresh=True, persist=False)
        self.assertEqual(len(report["headlines"]), 1)
        self.assertEqual(report["headlines"][0]["title"], "Test story")


def asdict(t: ar.Trend) -> dict:
    return {
        "id": t.id,
        "theme": t.theme,
        "summary": t.summary,
        "kit_status": t.kit_status,
        "opportunity": t.opportunity,
        "sources": t.sources,
        "priority": t.priority,
    }


if __name__ == "__main__":
    unittest.main()
