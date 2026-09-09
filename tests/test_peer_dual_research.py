#!/usr/bin/env python3
"""Tests for peer_dual_research — efficiency + output lanes."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_dual_research as dr  # noqa: E402


class TestPeerDualResearch(unittest.TestCase):
    def test_make_id_stable(self) -> None:
        a = dr.ResearchFinding.make_id("efficiency", "noop loop")
        b = dr.ResearchFinding.make_id("efficiency", "noop loop")
        self.assertEqual(a, b)

    def test_merge_tracks_new(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            findings = Path(tmp) / "findings.json"
            with mock.patch.object(dr, "FINDINGS_PATH", findings):
                f = dr.ResearchFinding(
                    id="abc",
                    lane="efficiency",
                    severity="high",
                    title="Test",
                    evidence="detail",
                    action="fix",
                    enqueue_title="Fix test",
                )
                open_f, new_f = dr.merge_findings("efficiency", [f])
                self.assertEqual(len(new_f), 1)
                open_f2, new_f2 = dr.merge_findings("efficiency", [f])
                self.assertEqual(len(new_f2), 0)

    def test_build_sync_digest(self) -> None:
        eff = dr.LaneReport(
            lane="efficiency",
            findings=[
                dr.ResearchFinding(
                    id="1",
                    lane="efficiency",
                    severity="high",
                    title="Speed win",
                    evidence="slow path",
                    action="./scripts/peer pre-dispatch",
                )
            ],
        )
        out = dr.LaneReport(
            lane="output",
            findings=[
                dr.ResearchFinding(
                    id="2",
                    lane="output",
                    severity="high",
                    title="External proof",
                    evidence="registry idle",
                    action="factory-sprint",
                )
            ],
        )
        md = dr.build_sync_digest(eff, out)
        self.assertIn("Research sync", md)
        self.assertIn("Efficiency lane", md)
        self.assertIn("Output lane", md)

    def test_findings_to_opportunities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            findings = Path(tmp) / "findings.json"
            payload = {
                "items": {
                    "x1": {
                        "lane": "efficiency",
                        "severity": "high",
                        "title": "Compact queue",
                        "enqueue_title": "Compact queue to 12",
                        "evidence": "55 items",
                        "action": "compact",
                        "status": "open",
                    }
                }
            }
            findings.write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch.object(dr, "FINDINGS_PATH", findings):
                with mock.patch.object(
                    dr, "_open_queue_items", return_value=["x"] * 20
                ):
                    with mock.patch.object(
                        dr, "_loop_state", return_value={"verify_ok": True, "noop": True}
                    ):
                        with mock.patch.object(dr, "_queue_has_title", return_value=False):
                            opps = dr.findings_to_opportunities(known=set())
        self.assertEqual(len(opps), 1)
        self.assertEqual(opps[0]["category"], "efficiency")

    def test_findings_to_opportunities_skips_empty_enqueue_title(self) -> None:
        """OVERSEER_DUAL_RESEARCH_ENQUEUE_TITLE_ONLY_2026_09_08 — no title fallback."""
        with tempfile.TemporaryDirectory() as tmp:
            findings = Path(tmp) / "findings.json"
            payload = {
                "items": {
                    "stale": {
                        "lane": "output",
                        "severity": "medium",
                        "title": "Factory progress below self-sufficient target",
                        "enqueue_title": "",
                        "evidence": "factory_progress=53%",
                        "action": "./scripts/peer progress",
                        "status": "open",
                    }
                }
            }
            findings.write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch.object(dr, "FINDINGS_PATH", findings):
                with mock.patch.object(
                    dr, "resolve_satisfied_dual_research_findings", return_value=0
                ):
                    opps = dr.findings_to_opportunities(known=set())
        self.assertEqual(opps, [])

    def test_findings_to_opportunities_suppresses_satisfied_met(self) -> None:
        """OVERSEER_DUAL_RESEARCH_SUPPRESS_MET_2026_09_08 — live-ok MET titles stay out."""
        with tempfile.TemporaryDirectory() as tmp:
            findings = Path(tmp) / "findings.json"
            payload = {
                "items": {
                    "v1": {
                        "lane": "efficiency",
                        "severity": "critical",
                        "title": "Verify gate blocking dispatch",
                        "enqueue_title": "Fix verify gate — unblock worker dispatch",
                        "evidence": "self-heal seeded last_cycle",
                        "action": "heal",
                        "status": "open",
                    },
                    "c1": {
                        "lane": "efficiency",
                        "severity": "high",
                        "title": "Executable queue bloated",
                        "enqueue_title": "Compact queue to 12 executable file-scoped items",
                        "evidence": "18 open items",
                        "action": "compact",
                        "status": "enqueued",
                    },
                    "a1": {
                        "lane": "output",
                        "severity": "medium",
                        "title": "Irreversible artifact gate not enforced",
                        "enqueue_title": (
                            "Irreversible artifact gate — peer success = "
                            "merged diff or PR note"
                        ),
                        "evidence": "Peer success should mean PR",
                        "action": "gate",
                        "status": "enqueued",
                    },
                }
            }
            findings.write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch.object(dr, "FINDINGS_PATH", findings):
                with mock.patch.object(dr, "_open_queue_items", return_value=["real work"]):
                    with mock.patch.object(
                        dr,
                        "_loop_state",
                        return_value={"verify_ok": True, "noop": False},
                    ):
                        with mock.patch.object(
                            dr.auto, "factory_meter_mode", return_value="self_sufficient"
                        ):
                            with mock.patch(
                                "factory_progress.compute_factory_progress",
                                return_value=mock.Mock(pct=96.0),
                            ):
                                n = dr.resolve_satisfied_dual_research_findings(write=True)
                                opps = dr.findings_to_opportunities(known=set())
                                saved = json.loads(findings.read_text(encoding="utf-8"))
            self.assertGreaterEqual(n, 3)
            self.assertEqual(opps, [])
            for item in saved["items"].values():
                self.assertEqual(item.get("status"), "resolved")

    def test_probe_efficiency_noop(self) -> None:
        with mock.patch.object(dr, "_open_queue_items", return_value=["item"] * 20):
            with mock.patch.object(dr, "_loop_state", return_value={"noop": True}):
                with mock.patch.object(dr.cfg_mod, "CFG", {"role_pool_expand": False}):
                    findings = dr.probe_efficiency()
        titles = {f.title for f in findings}
        self.assertIn("Executable queue bloated", titles)
        self.assertIn("Noop loop — zero queue advance", titles)

    def test_soft_verify_false_skips_fix_verify_gate_theater(self) -> None:
        """OVERSEER_SKIP_SOFT_VERIFY_GATE_THEATER — deferred≠enqueue Fix verify gate."""
        soft = {
            "verify_ok": False,
            "failure_type": "deferred",
            "note": "verify deferred (swarm/lock)",
        }
        self.assertTrue(dr._soft_verify_false(soft))
        with mock.patch.object(dr, "_open_queue_items", return_value=[]):
            with mock.patch.object(dr, "_loop_state", return_value=soft):
                with mock.patch.object(dr.cfg_mod, "CFG", {"role_pool_expand": False}):
                    findings = dr.probe_efficiency()
        titles = {f.title for f in findings}
        self.assertNotIn("Verify gate blocking dispatch", titles)
        hard = {"verify_ok": False, "failure_type": "tests", "note": "unittest failed"}
        self.assertFalse(dr._soft_verify_false(hard))
        with mock.patch.object(dr, "_open_queue_items", return_value=[]):
            with mock.patch.object(dr, "_loop_state", return_value=hard):
                with mock.patch.object(dr.cfg_mod, "CFG", {"role_pool_expand": False}):
                    findings = dr.probe_efficiency()
        self.assertIn("Verify gate blocking dispatch", {f.title for f in findings})

    def test_run_cycle_digest_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            findings = Path(tmp) / "findings.json"
            digest = Path(tmp) / "sync.md"
            with mock.patch.object(dr, "STATE_PATH", state):
                with mock.patch.object(dr, "FINDINGS_PATH", findings):
                    with mock.patch.object(dr, "SYNC_DIGEST", digest):
                        with mock.patch.object(dr, "EFFICIENCY_DIGEST", Path(tmp) / "eff.md"):
                            with mock.patch.object(dr, "OUTPUT_DIGEST", Path(tmp) / "out.md"):
                                with mock.patch.object(dr, "research_enabled", return_value=True):
                                    with mock.patch.object(dr, "probe_efficiency", return_value=[]):
                                        with mock.patch.object(dr, "probe_output", return_value=[]):
                                            report = dr.run_research_cycle(digest_only=True, force=True)
        self.assertIn("digests", report)
        self.assertGreater(len(report.get("digests") or []), 0)

    def test_merge_lane_digest_keeps_agent_notes_and_extras(self) -> None:
        existing = (
            "# Output research\n\n"
            "## This cycle\n\n- old probe\n\n"
            "## Kit expansion freeze (Phase 1)\n\n| Metric | Gate |\n\n"
            "## Agent notes\n\n"
            "- **2026-09-02 22:45** — restore + Rekor deferral\n"
        )
        new = dr.build_lane_digest(
            lane="output",
            open_findings=[],
            new_findings=[],
            actions=["probed 0 finding(s); 0 new"],
            enqueued=[],
        )
        merged = dr.merge_lane_digest(existing, new)
        self.assertIn("2026-09-02 22:45", merged)
        self.assertIn("Kit expansion freeze", merged)
        self.assertNotIn(dr.AGENT_NOTES_STUB, merged.split("## Agent notes", 1)[-1])

    def test_write_digest_if_changed_skips_unchanged_body(self) -> None:
        """DIGEST_WRITE_SKIP_UNCHANGED — _Updated churn must not bump mtime."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "eff.md"
            body = (
                "# Efficiency research\n\n"
                "_Updated 2026-09-07T00:00:00Z_ · **Efficiency Research Agent**\n\n"
                "## This cycle\n\n- probed 1 finding(s); 0 new\n\n"
                "## Open findings\n\n- (none)\n\n"
                "## Agent notes\n\n- keep me\n"
            )
            path.write_text(body, encoding="utf-8")
            m0 = path.stat().st_mtime_ns
            rewritten = body.replace("2026-09-07T00:00:00Z", "2026-09-07T23:59:59Z")
            wrote = dr._write_digest_if_changed(path, rewritten)
            self.assertFalse(wrote)
            self.assertEqual(path.stat().st_mtime_ns, m0)
            changed = rewritten.replace("- (none)", "- **[high]** Hot path")
            wrote2 = dr._write_digest_if_changed(path, changed)
            self.assertTrue(wrote2)
            self.assertIn("Hot path", path.read_text(encoding="utf-8"))

    def test_run_cycle_witness_skip(self) -> None:
        """DUAL_RESEARCH_WITNESS_SKIP — second force=False cycle skips probe."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            state_path = tmp_p / "state.json"
            findings = tmp_p / "findings.json"
            findings.write_text("{}", encoding="utf-8")
            witness = (1, 2, 3, 4, "self_sufficient")
            with mock.patch.object(dr, "STATE_PATH", state_path), mock.patch.object(
                dr, "FINDINGS_PATH", findings
            ), mock.patch.object(dr, "EFFICIENCY_DIGEST", tmp_p / "eff.md"), mock.patch.object(
                dr, "OUTPUT_DIGEST", tmp_p / "out.md"
            ), mock.patch.object(dr, "SYNC_DIGEST", tmp_p / "sync.md"), mock.patch.object(
                dr, "research_enabled", return_value=True
            ), mock.patch.object(dr, "research_interval_sec", return_value=0.0), mock.patch.object(
                dr, "_probe_input_witness", return_value=witness
            ), mock.patch.object(dr, "_run_lane") as run_lane, mock.patch.object(
                dr, "write_digests", return_value=[tmp_p / "eff.md"]
            ) as wd:
                run_lane.side_effect = lambda lane: dr.LaneReport(lane=lane, findings=[])
                r1 = dr.run_research_cycle(digest_only=True, force=False, log_fn=lambda _m: None)
                self.assertNotEqual(r1.get("skipped"), "witness")
                self.assertEqual(run_lane.call_count, 2)
                run_lane.reset_mock()
                wd.reset_mock()
                r2 = dr.run_research_cycle(digest_only=True, force=False, log_fn=lambda _m: None)
                self.assertEqual(r2.get("skipped"), "witness")
                run_lane.assert_not_called()
                wd.assert_not_called()

    def test_preserve_sync_lane_unions_output_bullets(self) -> None:
        existing = (
            "# Research sync\n\n"
            "## Output lane (monster factory)\n\n"
            "- **[info]** Hub registry honesty — 0 adapted\n\n"
            "## Executable enqueue (improve + peer)\n\n- (none this cycle)\n"
        )
        new = (
            "# Research sync\n\n"
            "## Output lane (monster factory)\n\n"
            "- **[medium]** Factory progress below self-sufficient target — ./scripts/peer progress\n\n"
            "## Executable enqueue (improve + peer)\n\n- (none this cycle)\n"
        )
        out = dr.preserve_sync_lane(existing, new, "Output lane (monster factory)")
        self.assertIn("Factory progress", out)
        self.assertIn("Hub registry honesty", out)

    def test_probe_output_factory_progress_fail_no_unboundlocal(self) -> None:
        """except path must not UnboundLocalError on has_external/has_artifact."""
        boom = RuntimeError("compute_report boom")

        class _FP:
            @staticmethod
            def compute_factory_progress():
                raise boom

        with mock.patch.dict(sys.modules, {"factory_progress": _FP}), mock.patch.object(
            dr.auto, "factory_meter_mode", return_value="self_sufficient"
        ), mock.patch.object(dr, "_open_queue_items", return_value=[]), mock.patch.object(
            dr, "ROOT", Path("/tmp/no-registry-here")
        ):
            findings = dr.probe_output()
        titles = {f.title for f in findings}
        self.assertIn("Factory progress probe failed", titles)
        self.assertTrue(
            all("external proof" not in (f.enqueue_title or "").lower() for f in findings)
        )

    def test_cmd_install_linux_calls_linux_install_daemon(self) -> None:
        """OVERSEER_DUAL_RESEARCH_LINUX_INSTALL_2026_09_06 — no launchctl on Linux."""
        import peer_self_heal as heal

        with mock.patch.object(dr.sys, "platform", "linux"):
            with mock.patch.object(heal, "ensure_canonical_module"):
                with mock.patch.object(
                    heal, "linux_install_daemon", return_value="unit ok"
                ) as inst:
                    with mock.patch.object(dr.subprocess, "run") as run:
                        rc = dr.cmd_install()
        self.assertEqual(rc, 0)
        inst.assert_called_once_with("dual-research")
        run.assert_not_called()

    def test_cmd_uninstall_linux_calls_linux_uninstall_daemon(self) -> None:
        """OVERSEER_DUAL_RESEARCH_LINUX_INSTALL_2026_09_06"""
        import peer_self_heal as heal

        with mock.patch.object(dr.sys, "platform", "linux"):
            with mock.patch.object(heal, "ensure_canonical_module"):
                with mock.patch.object(
                    heal, "linux_uninstall_daemon", return_value="gone"
                ) as un:
                    with mock.patch.object(dr.subprocess, "run") as run:
                        rc = dr.cmd_uninstall()
        self.assertEqual(rc, 0)
        un.assert_called_once_with("dual-research")
        run.assert_not_called()

    def test_cmd_status_linux_uses_systemd(self) -> None:
        """OVERSEER_DUAL_RESEARCH_LINUX_INSTALL_2026_09_06"""
        import peer_self_heal as heal

        with mock.patch.object(dr.sys, "platform", "linux"):
            with mock.patch.object(heal, "_systemd_user_active", return_value=True):
                with mock.patch.object(dr, "_load_state", return_value={}):
                    with mock.patch.object(dr.subprocess, "run") as run:
                        rc = dr.cmd_status()
        self.assertEqual(rc, 0)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
