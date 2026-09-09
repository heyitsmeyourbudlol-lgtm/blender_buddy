#!/usr/bin/env python3
"""Tests for peer_commands registry."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_commands as pc  # noqa: E402


class TestPeerCommands(unittest.TestCase):
    def test_registry_has_compounds(self) -> None:
        for cmd_id in (
            "bootstrap",
            "heal-all",
            "green",
            "noop-break",
            "stagnation-break",
            "soft-hub-writeback",
            "soft-soft-land-status",
            "commands-sync",
            "commands-cycle",
            "dev-fast",
            "idle-gate",
        ):
            self.assertIn(cmd_id, pc.COMPOUND_STEPS)

    def test_soft_soft_land_status_registered(self) -> None:
        ids = {c.id for c in pc.COMMANDS}
        self.assertIn("soft-soft-land-status", ids)
        self.assertIn("soft-soft-status", ids)
        self.assertIn("soft-soft-status", pc.INNER_RUNNERS)
        self.assertEqual(
            pc.COMPOUND_STEPS["soft-soft-land-status"],
            ["soft-soft-status", "queue-status"],
        )

    def test_all_compound_steps_resolve(self) -> None:
        ids = {c.id for c in pc.COMMANDS} | set(pc.COMPOUND_STEPS) | set(pc.INNER_RUNNERS)
        for compound_id, steps in pc.COMPOUND_STEPS.items():
            self.assertIn(compound_id, {c.id for c in pc.COMMANDS})
            for step in steps:
                self.assertIn(
                    step,
                    ids,
                    msg=f"compound {compound_id} references missing step {step}",
                )

    def test_pivotal_listed_in_peer_help_or_case(self) -> None:
        peer_sh = (Path(__file__).resolve().parents[1] / "scripts" / "peer").read_text(
            encoding="utf-8"
        )
        missing = []
        for cmd in pc.list_commands(pivotal_only=True):
            if cmd.id in pc.COMPOUND_STEPS:
                # compounds routed via peer_commands.py run in case group
                if "commands-sync" not in peer_sh and cmd.id == "commands-sync":
                    missing.append(cmd.id)
                continue
            # one-shots should appear as case or help
            if f"{cmd.id})" not in peer_sh and f"{cmd.id} " not in peer_sh:
                missing.append(cmd.id)
        # Allow a small set of pivotal that go only through peer_commands run
        # but require most are discoverable
        self.assertLessEqual(len(missing), 25, msg=f"pivotal missing from peer: {missing[:15]}")

    def test_factory_ai_verbs_registered(self) -> None:
        ids = {c.id for c in pc.COMMANDS}
        for cmd_id in (
            "niche-assist-once",
            "niche-bank-status",
            "niche-bank-eval",
            "factory-dynamics",
            "command-dispatch-audit",
            "command-ecosystem-finish",
        ):
            self.assertIn(cmd_id, ids)

    def test_compression_keep_alive_registered(self) -> None:
        # OVERSEER_COMPRESSION_KEEP_ALIVE_2026_09_05 — coverage gap wrap
        ids = {c.id for c in pc.COMMANDS}
        self.assertIn("compression-keep-alive", ids)
        cmd = next(c for c in pc.COMMANDS if c.id == "compression-keep-alive")
        self.assertTrue(cmd.pivotal)
        self.assertIn("--check", cmd.argv)
        self.assertIn("compression_keep_alive.py", " ".join(cmd.argv))
        peer_sh = (Path(__file__).resolve().parents[1] / "scripts" / "peer").read_text(
            encoding="utf-8"
        )
        self.assertIn("compression-keep-alive)", peer_sh)
        report = pc.run_command("compression-keep-alive", dry_run=True)
        self.assertTrue(report.ok)

    def test_niche_n02_practice_registered(self) -> None:
        # OVERSEER_NICHE_PRACTICE_N02_WRAP_2026_09_08 — coverage top gap wrap
        ids = {c.id for c in pc.COMMANDS}
        self.assertEqual(sum(1 for c in pc.COMMANDS if c.id == "niche-n02-practice"), 1)
        self.assertIn("niche-n02-practice", ids)
        cmd = next(c for c in pc.COMMANDS if c.id == "niche-n02-practice")
        self.assertTrue(cmd.pivotal)
        self.assertIn("--eval-only", cmd.argv)
        self.assertIn("--json", cmd.argv)
        self.assertIn("niche_n02_practice.py", " ".join(cmd.argv))
        peer_sh = (Path(__file__).resolve().parents[1] / "scripts" / "peer").read_text(
            encoding="utf-8"
        )
        self.assertEqual(peer_sh.count("niche-n02-practice)"), 1)
        self.assertIn("niche_n02_practice.py", peer_sh)
        report = pc.run_command("niche-n02-practice", dry_run=True)
        self.assertTrue(report.ok)

    def test_niche_distill_validate_registered(self) -> None:
        # OVERSEER_NICHE_DISTILL_VALIDATE_WRAP_2026_09_08 — sole COMMAND_COVERAGE gap
        ids = {c.id for c in pc.COMMANDS}
        self.assertEqual(sum(1 for c in pc.COMMANDS if c.id == "niche-distill-validate"), 1)
        self.assertIn("niche-distill-validate", ids)
        cmd = next(c for c in pc.COMMANDS if c.id == "niche-distill-validate")
        self.assertTrue(cmd.pivotal)
        self.assertEqual(cmd.category, "factory")
        self.assertNotIn("niche-distill-validate", pc.COMPOUND_STEPS)
        argv = " ".join(cmd.argv)
        self.assertIn("niche_distill_validate.py", argv)
        self.assertIn("--json", argv)
        self.assertTrue(Path(cmd.argv[1]).is_file(), cmd.argv[1])
        peer_sh = (Path(__file__).resolve().parents[1] / "scripts" / "peer").read_text(
            encoding="utf-8"
        )
        self.assertEqual(peer_sh.count("niche-distill-validate)"), 1)
        self.assertIn("niche_distill_validate.py", peer_sh)
        self.assertIn("--json", peer_sh)
        self.assertIn(
            "niche-distill-validate — niche distill schema + anti-prune floor JSON",
            peer_sh,
        )
        report = pc.run_command("niche-distill-validate", dry_run=True)
        self.assertTrue(report.ok, report.steps)

    def test_coverage_gate_registered(self) -> None:
        # OVERSEER_COVERAGE_GATE_2026_09_08 — fail-closed n_gaps
        ids = {c.id for c in pc.COMMANDS}
        self.assertEqual(sum(1 for c in pc.COMMANDS if c.id == "coverage-gate"), 1)
        self.assertIn("coverage-gate", ids)
        cmd = next(c for c in pc.COMMANDS if c.id == "coverage-gate")
        self.assertTrue(cmd.pivotal)
        self.assertEqual(cmd.category, "meta")
        self.assertNotIn("coverage-gate", pc.COMPOUND_STEPS)
        self.assertIn("coverage-gate", pc.INNER_RUNNERS)
        argv = " ".join(cmd.argv)
        self.assertIn("peer_commands.py", argv)
        self.assertIn("inner", argv)
        self.assertIn("coverage-gate", argv)
        peer_sh = (Path(__file__).resolve().parents[1] / "scripts" / "peer").read_text(
            encoding="utf-8"
        )
        self.assertEqual(peer_sh.count("coverage-gate)"), 1)
        self.assertIn("inner coverage-gate", peer_sh)
        self.assertIn(
            "coverage-gate — fail-closed CLI wrap coverage",
            peer_sh,
        )
        report = pc.run_command("coverage-gate", dry_run=True)
        self.assertTrue(report.ok, report.steps)

    def test_research_claim_arith_registered(self) -> None:
        # OVERSEER_RESEARCH_CLAIM_ARITH_WRAP_2026_09_08 — sole COMMAND_COVERAGE gap
        ids = {c.id for c in pc.COMMANDS}
        self.assertEqual(sum(1 for c in pc.COMMANDS if c.id == "research-claim-arith"), 1)
        self.assertIn("research-claim-arith", ids)
        cmd = next(c for c in pc.COMMANDS if c.id == "research-claim-arith")
        self.assertTrue(cmd.pivotal)
        self.assertEqual(cmd.category, "factory")
        self.assertNotIn("research-claim-arith", pc.COMPOUND_STEPS)
        argv = " ".join(cmd.argv)
        self.assertIn("research_claim_arith.py", argv)
        self.assertIn("--check-cache", argv)
        self.assertIn("--json", argv)
        self.assertTrue(Path(cmd.argv[1]).is_file(), cmd.argv[1])
        peer_sh = (Path(__file__).resolve().parents[1] / "scripts" / "peer").read_text(
            encoding="utf-8"
        )
        self.assertEqual(peer_sh.count("research-claim-arith)"), 1)
        self.assertIn("research_claim_arith.py", peer_sh)
        self.assertIn("--check-cache", peer_sh)
        self.assertIn("--json", peer_sh)
        self.assertIn(
            "research-claim-arith — arith research prefilter cache check",
            peer_sh,
        )
        report = pc.run_command("research-claim-arith", dry_run=True)
        self.assertTrue(report.ok, report.steps)

    def test_error_adapt_registered(self) -> None:
        # OVERSEER_ERROR_ADAPT_PEER_WRAP_2026_09_08 — hub id is peer-error-adapt
        ids = {c.id for c in pc.COMMANDS}
        self.assertIn("peer-error-adapt", ids)
        cmd = next(c for c in pc.COMMANDS if c.id == "peer-error-adapt")
        self.assertTrue(cmd.pivotal)
        self.assertIn("--from-gate", cmd.argv)
        self.assertIn("peer_error_adapt.py", " ".join(cmd.argv))
        peer_sh = (Path(__file__).resolve().parents[1] / "scripts" / "peer").read_text(
            encoding="utf-8"
        )
        self.assertIn("peer-error-adapt)", peer_sh)
        report = pc.run_command("peer-error-adapt", dry_run=True)
        self.assertTrue(report.ok)

    def test_compression_harvest_wraps_registered(self) -> None:
        # OVERSEER_COMMAND_BUILDER_HARVEST_WRAP_2026_09_08
        ids = {c.id for c in pc.COMMANDS}
        wraps = (
            "compression-ladder",
            "bitnet-fp4-expert-rss-smoke",
            "compression-ablation-schedule",
            "compression-auto-train",
            "compression-gpu-worker",
            "compression-logit-expand",
            "compression-result-watch",
            "compression-stress-suite",
            "compression-t0-pack",
            "compression-t1-share",
            "compression-t2-svd",
            "compression-t3-bitdistill",
            "compression-t4-scale",
            "compression-t5-serve",
            "compression-t6-quality",
            "compression-train-profile",
        )
        for cmd_id in wraps:
            self.assertIn(cmd_id, ids, msg=f"missing wrap {cmd_id}")
        self.assertEqual(
            pc.COMPOUND_STEPS["compression-ladder"],
            [
                "compression-t0-pack",
                "compression-t1-share",
                "compression-t2-svd",
                "compression-t3-bitdistill",
                "compression-t4-scale",
                "compression-t5-serve",
                "compression-t6-quality",
            ],
        )
        auto_train = next(c for c in pc.COMMANDS if c.id == "compression-auto-train")
        self.assertIn("--check", auto_train.argv)
        watch = next(c for c in pc.COMMANDS if c.id == "compression-result-watch")
        self.assertIn("--once", watch.argv)
        peer_sh = (Path(__file__).resolve().parents[1] / "scripts" / "peer").read_text(
            encoding="utf-8"
        )
        self.assertIn("compression-ladder)", peer_sh)
        self.assertIn("compression-t0-pack)", peer_sh)
        report = pc.run_command("compression-ladder", dry_run=True)
        self.assertTrue(report.ok)
        self.assertEqual(
            [s["step"] for s in report.steps],
            pc.COMPOUND_STEPS["compression-ladder"],
        )

    def test_residual_gap_wraps_registered(self) -> None:
        # OVERSEER_COMMAND_BUILDER_RESIDUAL_WRAP_2026_09_08
        ids = {c.id for c in pc.COMMANDS}
        wraps = (
            "github-feedback-fetch",
            "github-feedback-list",
            "github-feedback-render",
            "production-power",
            "scoreboard-write",
            "niche-bank-compress",
            "niche-hot-path",
            "factory-niche-runtime",
            "factory-lora-train",
            "compression-train-rung0",
            "gpu-profile-once",
            "dgx-resource-priority",
            "niche-domain-classifier-train",
            "agent-survival",
        )
        for cmd_id in wraps:
            self.assertIn(cmd_id, ids, msg=f"missing wrap {cmd_id}")
        hot = next(c for c in pc.COMMANDS if c.id == "niche-hot-path")
        self.assertIn("--inventory", hot.argv)
        self.assertIn("--json", hot.argv)
        rung0 = next(c for c in pc.COMMANDS if c.id == "compression-train-rung0")
        self.assertIn("--once", rung0.argv)
        clf = next(c for c in pc.COMMANDS if c.id == "niche-domain-classifier-train")
        self.assertIn("--eval-only", clf.argv)
        pp = next(c for c in pc.COMMANDS if c.id == "production-power")
        self.assertIn("--write", pp.argv)
        peer_sh = (Path(__file__).resolve().parents[1] / "scripts" / "peer").read_text(
            encoding="utf-8"
        )
        self.assertIn("github-feedback-fetch)", peer_sh)
        self.assertIn("production-power|scoreboard-write)", peer_sh)
        self.assertIn("niche-hot-path)", peer_sh)
        self.assertIn("compression-train-rung0)", peer_sh)
        report = pc.run_command("niche-hot-path", dry_run=True)
        self.assertTrue(report.ok)

    def test_idle_gate_steps(self) -> None:
        # OVERSEER_IDLE_GATE_COMPOUND_2026_09_05
        self.assertEqual(
            pc.COMPOUND_STEPS["idle-gate"],
            ["progress", "compact-queue", "pen-test-digest"],
        )
        report = pc.run_command("idle-gate", dry_run=True)
        self.assertTrue(report.ok)
        self.assertEqual(
            [s["step"] for s in report.steps],
            ["progress", "compact-queue", "pen-test-digest"],
        )

    def test_pivotal_commands_exist(self) -> None:
        pivotal = pc.list_commands(pivotal_only=True)
        self.assertGreaterEqual(len(pivotal), 20)
        ids = {c.id for c in pivotal}
        self.assertIn("check", ids)
        self.assertIn("compact-queue", ids)
        self.assertIn("research-claim-arith", ids)

    def test_run_dry_run_compound(self) -> None:
        report = pc.run_command("pre-dispatch", dry_run=True)
        self.assertTrue(report.ok)
        steps = [s["step"] for s in report.steps]
        self.assertIn("compact-queue", steps)
        self.assertIn("check", steps)

    def test_compact_queue_inner(self) -> None:
        with mock.patch.object(
            pc.auto,
            "compact_executable_queue",
            return_value=(2, ["demoted 1"]),
        ):
            with mock.patch.object(pc.auto, "open_work_items") as ow:
                ow.return_value.open_items = ["a", "b"]
                ow.return_value.source = "work_queue"
                rc, detail = pc.INNER_RUNNERS["compact-queue"]()
        self.assertEqual(rc, 0)
        self.assertIn("removed=2", detail)

    def test_format_markdown_includes_recipes(self) -> None:
        md = pc.format_markdown()
        self.assertIn("bootstrap", md)
        self.assertIn("Agent recipes", md)
        self.assertIn("research-claim-arith", md)


if __name__ == "__main__":
    unittest.main()
