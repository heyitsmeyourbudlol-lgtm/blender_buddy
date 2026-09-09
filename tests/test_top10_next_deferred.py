#!/usr/bin/env python3
"""Tests for Top10 deferred: pack-gate, role-state, niche domain classify."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import niche_domain_classify as ndc  # noqa: E402
import peer_commands as pc  # noqa: E402
import peer_role_state as prs  # noqa: E402


class TestMemoryPackGateCompound(unittest.TestCase):
    def test_heal_all_includes_pack_gate(self) -> None:
        steps = pc.COMPOUND_STEPS["heal-all"]
        self.assertIn("memory-pack-gate", steps)
        self.assertLess(
            steps.index("memory-pack-gate"),
            steps.index("verify-gate"),
        )

    def test_pre_dispatch_includes_pack_gate(self) -> None:
        steps = pc.COMPOUND_STEPS["pre-dispatch"]
        self.assertEqual(
            steps,
            [
                "compact-queue",
                "memory-pack-gate",
                "plan-gate",
                "check",
                "ensure-pool",
            ],
        )

    def test_pack_gate_inner_soft_on_ok(self) -> None:
        with mock.patch("peer_memory_health.resolve_verify_ok") as rv:
            rv.return_value = (True, "header+json_sha256 ok", {"mode": "integrity"})
            rc, detail = pc.INNER_RUNNERS["memory-pack-gate"]()
        self.assertEqual(rc, 0)
        self.assertIn("ok", detail)

    def test_pack_gate_inner_hard_on_integrity_fail(self) -> None:
        with mock.patch("peer_memory_health.resolve_verify_ok") as rv:
            rv.return_value = (False, "integrity fail: boom", {"mode": "integrity"})
            rc, detail = pc.INNER_RUNNERS["memory-pack-gate"]()
        self.assertEqual(rc, 1)
        self.assertIn("FAIL", detail)

    def test_pack_gate_inner_soft_warn_when_none(self) -> None:
        with mock.patch("peer_memory_health.resolve_verify_ok") as rv:
            rv.return_value = (None, "no pack", {})
            rc, detail = pc.INNER_RUNNERS["memory-pack-gate"]()
        self.assertEqual(rc, 0)
        self.assertIn("warn", detail)

    def test_dry_run_pre_dispatch_lists_gate(self) -> None:
        report = pc.run_command("pre-dispatch", dry_run=True)
        self.assertTrue(report.ok)
        step_ids = [s["step"] for s in report.steps]
        self.assertIn("memory-pack-gate", step_ids)


class TestRoleState(unittest.TestCase):
    def test_roundtrip_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = prs.set_assignment(
                "factory_engineer",
                assignment="wire pack gate",
                files=["scripts/peer_commands.py"],
                verify_cmd="./scripts/peer test-quick",
                root=root,
            )
            self.assertEqual(state["role_id"], "factory_engineer")
            self.assertEqual(state["assignment"], "wire pack gate")
            self.assertEqual(state["files"], ["scripts/peer_commands.py"])
            self.assertFalse(state["blocked"])
            loaded = prs.load_state("factory_engineer", root=root)
            self.assertEqual(loaded["verify_cmd"], "./scripts/peer test-quick")
            errs = prs.validate_state(loaded)
            self.assertEqual(errs, [])

    def test_block_unblock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prs.set_assignment(
                "queue_steward",
                blocked=True,
                blocked_reason="waiting PR",
                root=root,
            )
            s = prs.load_state("queue_steward", root=root)
            self.assertTrue(s["blocked"])
            self.assertEqual(s["blocked_reason"], "waiting PR")
            prs.set_assignment("queue_steward", blocked=False, root=root)
            s2 = prs.load_state("queue_steward", root=root)
            self.assertFalse(s2["blocked"])
            self.assertEqual(s2["blocked_reason"], "")

    def test_list_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prs.set_assignment("a", assignment="1", root=root)
            prs.set_assignment("b", assignment="2", root=root)
            rows = prs.list_states(root=root)
            self.assertEqual({r["role_id"] for r in rows}, {"a", "b"})

    def test_invalid_role_id(self) -> None:
        with self.assertRaises(ValueError):
            prs.state_path("../evil")


class TestNicheDomainClassify(unittest.TestCase):
    def test_queue_query_heuristic(self) -> None:
        result = ndc.classify(
            "please open notes/WORK_QUEUE.md Active items",
            prefer_model=False,
        )
        self.assertEqual(result["domain_id"], "queue_sync")
        self.assertEqual(result["source"], "heuristic")
        self.assertGreater(result["confidence"], 0)

    def test_empty_stub(self) -> None:
        result = ndc.classify("")
        self.assertIsNone(result["domain_id"])
        self.assertEqual(result["source"], "stub")

    def test_cli_json(self) -> None:
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = ndc.main(["--json", "--no-model", "noop plan-gate peer_loop"])
        self.assertIn(code, (0, 1))
        data = json.loads(buf.getvalue())
        self.assertIn("domain_id", data)
        self.assertTrue(data.get("no_pay"))

    def test_model_checkpoint_infer(self) -> None:
        self.assertTrue(ndc.model_available(), "T10-09 checkpoint missing")
        # Soft paraphrase — keyword-weak; model should route peer_runtime
        result = ndc.classify(
            "forever runner fanout when coding sandbox is dirty",
            prefer_model=True,
        )
        self.assertEqual(result["source"], "model")
        self.assertEqual(result["domain_id"], "peer_runtime")
        self.assertGreater(result["confidence"], 0.2)
        self.assertTrue(result["model_ready"])

    def test_heldout_lift_vs_keyword(self) -> None:
        import niche_domain_classifier_train as train

        ckpt = ndc.load_checkpoint(force=True)
        self.assertIsNotNone(ckpt)
        held_path = train.HELDOUT_JSONL
        self.assertTrue(held_path.is_file())
        rows = []
        for line in held_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        report = train.eval_split(rows, ckpt)  # type: ignore[arg-type]
        self.assertGreater(report["lift"], 0.0)
        self.assertGreater(report["model_acc"], report["keyword_acc"])


class TestTop10PeerVerbs(unittest.TestCase):
    def test_top10_next_verb_wired(self) -> None:
        by_id = {c.id: c for c in pc.COMMANDS}
        self.assertIn("top10", by_id)
        self.assertIn("top10-refresh", by_id)
        self.assertIn("top10-next", by_id)
        self.assertEqual(by_id["top10-next"].argv[-1], "--next")

    def test_top10_next_dry_run(self) -> None:
        report = pc.run_command("top10-next", dry_run=True)
        self.assertTrue(report.ok)


if __name__ == "__main__":
    unittest.main()
