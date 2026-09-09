#!/usr/bin/env python3
"""Scope B amnesia combat — DOMAIN_OWNERS, librarian receipt, read-ack."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_agent_gates as gates  # noqa: E402
import peer_fact_librarian as fl  # noqa: E402


class TestDomainOwners(unittest.TestCase):
    def test_format_includes_all_domains(self) -> None:
        body = fl.format_domain_owners_md()
        self.assertIn("DOMAIN_OWNERS", body)
        self.assertIn("CODEOWNERS-like", body)
        for d in fl.list_domains():
            self.assertIn(f"`{d['id']}`", body)

    def test_write_domain_owners_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "DOMAIN_OWNERS.md"
            written = fl.write_domain_owners_md(path=out)
            self.assertTrue(written.is_file())
            text = written.read_text(encoding="utf-8")
            self.assertIn("peer_runtime", text)
            self.assertIn("@memory_remembrance/", text)

    def test_domain_for_path_routes_owners(self) -> None:
        d = fl.domain_for_path("notes/WORK_QUEUE.md")
        self.assertIsNotNone(d)
        assert d is not None
        self.assertEqual(d.get("id"), "queue_sync")

    def test_auto_pick_uses_path_token(self) -> None:
        d, scores = fl.auto_pick_domain("please open notes/WORK_QUEUE.md Active")
        self.assertIsNotNone(d)
        assert d is not None
        self.assertEqual(d.get("id"), "queue_sync")
        self.assertTrue(any(s[0] == "queue_sync" and s[1] > 0 for s in scores))


class TestLibrarianReceipt(unittest.TestCase):
    def test_write_and_load_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fact-query-receipt.json"
            relay = {
                "ts": 1_700_000_000.0,
                "query": "noop plan-gate",
                "domain": {"id": "peer_runtime", "source": "auto"},
                "remembrance": {"prefer_librarian": True},
            }
            with patch("peer_fact_librarian.time.time", return_value=1_700_000_000.0):
                fl.write_fact_query_receipt(relay, path=path)
            ok, data, detail = fl.load_fact_query_receipt(
                path=path,
                max_age_sec=10**9,
            )
            self.assertTrue(ok, msg=detail)
            self.assertEqual(data.get("domain_id"), "peer_runtime")
            self.assertTrue(str(data.get("receipt_id") or ""))

    def test_stale_receipt_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text(
                json.dumps({"receipt_id": "abc", "ts": 1.0, "query": "x"}),
                encoding="utf-8",
            )
            ok, _, detail = fl.load_fact_query_receipt(path=path, max_age_sec=60)
            self.assertFalse(ok)
            self.assertIn("stale", detail)


class TestPlanGateAmnesia(unittest.TestCase):
    def test_read_ack_pass_with_required_paths(self) -> None:
        ok, cited, detail = gates.load_always_read_ack(
            path=Path("/nonexistent-ack.json"),
            extra_paths=[
                "notes/AGENT_WORKING_MEMORY.md",
                "notes/WORK_QUEUE.md",
                "AGENTS.md",
            ],
        )
        self.assertTrue(ok, msg=detail)
        self.assertIn("notes/AGENT_WORKING_MEMORY.md", cited)

    def test_read_ack_from_plan_text(self) -> None:
        plan = (
            "Open notes/AGENT_WORKING_MEMORY.md and notes/WORK_QUEUE.md; "
            "respect AGENTS.md NO PAY."
        )
        ok, _, detail = gates.load_always_read_ack(
            path=Path("/nonexistent-ack.json"),
            plan_text=plan,
        )
        self.assertTrue(ok, msg=detail)

    def test_librarian_soft_warn_when_prefer_missing_receipt(self) -> None:
        with patch.object(fl, "should_prefer_librarian", return_value=(True, "pack large")):
            with patch.object(
                fl,
                "load_fact_query_receipt",
                return_value=(False, {}, "no fact-query receipt"),
            ):
                row = gates._librarian_receipt_gate(
                    prefer_librarian=True,
                    prefer_why="pack large",
                    read_ack_ok=False,
                    soft_mode=True,
                )
        self.assertEqual(row.status, "warn")
        self.assertIn("soft→require", row.detail)

    def test_librarian_hard_fail_when_prefer_missing_receipt(self) -> None:
        with patch.object(
            fl,
            "load_fact_query_receipt",
            return_value=(False, {}, "no fact-query receipt"),
        ):
            row = gates._librarian_receipt_gate(
                prefer_librarian=True,
                prefer_why="pack large",
                read_ack_ok=False,
                soft_mode=False,
            )
        self.assertEqual(row.status, "fail")
        self.assertTrue(row.status == "fail")

    def test_librarian_pass_via_read_ack(self) -> None:
        with patch.object(
            fl,
            "load_fact_query_receipt",
            return_value=(False, {}, "no fact-query receipt"),
        ):
            row = gates._librarian_receipt_gate(
                prefer_librarian=True,
                prefer_why="pack large",
                read_ack_ok=True,
                soft_mode=False,
            )
        self.assertEqual(row.status, "pass")
        self.assertIn("always-read ack", row.detail)

    def test_plan_gate_hard_blocks_without_ack(self) -> None:
        with (
            patch.object(gates, "_team_context_fresh", return_value=(True, "fresh")),
            patch.object(gates, "_last_cycle_ok", return_value=(True, "ok")),
            patch.object(gates, "_queue_drift_ok", return_value=(True, "sync")),
            patch.object(gates, "_worktree_pool_ok", return_value=(True, "worktrees=2")),
            patch.object(gates, "_open_miss_assignments", return_value=(0, "none")),
            patch.object(gates, "_human_only_queue_items", return_value=(0, "none")),
            patch.object(gates, "_secret_scan_staged", return_value=(True, "clean")),
            patch(
                "peer_self_diagnose.run_instant_diagnosis",
                return_value=[],
            ),
            patch.object(fl, "should_prefer_librarian", return_value=(True, "pack large")),
            patch.object(
                fl,
                "load_fact_query_receipt",
                return_value=(False, {}, "no receipt"),
            ),
            patch.object(
                gates,
                "load_always_read_ack",
                return_value=(False, [], "missing citations"),
            ),
        ):
            report = gates.run_plan_gate(
                role_id="factory_engineer",
                refresh=False,
                quick=True,
                soft_librarian=False,
            )
        self.assertTrue(report.blocked)
        gaps = {r.gap: r.status for r in report.results}
        self.assertEqual(gaps.get("Librarian receipt"), "fail")
        self.assertEqual(gaps.get("Read-ack"), "fail")

    def test_plan_gate_pass_with_read_ack_paths(self) -> None:
        with (
            patch.object(gates, "_team_context_fresh", return_value=(True, "fresh")),
            patch.object(gates, "_last_cycle_ok", return_value=(True, "ok")),
            patch.object(gates, "_queue_drift_ok", return_value=(True, "sync")),
            patch.object(gates, "_worktree_pool_ok", return_value=(True, "worktrees=2")),
            patch.object(gates, "_open_miss_assignments", return_value=(0, "none")),
            patch.object(gates, "_human_only_queue_items", return_value=(0, "none")),
            patch.object(gates, "_secret_scan_staged", return_value=(True, "clean")),
            patch(
                "peer_self_diagnose.run_instant_diagnosis",
                return_value=[],
            ),
            patch.object(fl, "should_prefer_librarian", return_value=(True, "pack large")),
            patch.object(
                fl,
                "load_fact_query_receipt",
                return_value=(False, {}, "no receipt"),
            ),
            tempfile.TemporaryDirectory() as tmp,
        ):
            ack_path = Path(tmp) / "ack.json"
            with patch.object(gates, "ALWAYS_READ_ACK_JSON", ack_path):
                report = gates.run_plan_gate(
                    role_id="factory_engineer",
                    refresh=False,
                    quick=True,
                    read_ack_paths=[
                        "notes/AGENT_WORKING_MEMORY.md",
                        "notes/WORK_QUEUE.md",
                        "AGENTS.md",
                    ],
                    write_ack=True,
                    soft_librarian=False,
                )
        self.assertFalse(report.blocked)
        gaps = {r.gap: r.status for r in report.results}
        self.assertEqual(gaps.get("Read-ack"), "pass")
        self.assertEqual(gaps.get("Librarian receipt"), "pass")


if __name__ == "__main__":
    unittest.main()
