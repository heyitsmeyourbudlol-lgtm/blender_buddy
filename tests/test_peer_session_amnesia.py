#!/usr/bin/env python3
"""Tests for session amnesia combat (SCOPE A)."""

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

import peer_session_amnesia as psa  # noqa: E402
import peer_transcript as pt  # noqa: E402


class ScrubSecretsTests(unittest.TestCase):
    def test_redacts_sk_live(self) -> None:
        out = psa.scrub_secrets("key sk_live_ABCDEFGHIJKLMNOP and done")
        self.assertIn("[REDACTED]", out)
        self.assertNotIn("sk_live_ABCDEFGHIJKLMNOP", out)

    def test_redacts_whsec(self) -> None:
        out = psa.scrub_secrets("sig whsec_abcdefghijklmnopqrstuv")
        self.assertIn("[REDACTED]", out)


class SessionLedgerTests(unittest.TestCase):
    def test_append_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            led = Path(tmp) / "session_ledger"
            with mock.patch.object(psa, "SESSION_LEDGER_DIR", led):
                path = psa.append_session_ledger(
                    decision="landed X",
                    paths=["notes/WORK_QUEUE.md", "scripts/peer_loop.py"],
                    needle="OVERSEER_TEST_NEEDLE",
                    falsifier="verify red",
                    role_id="factory_engineer",
                )
                self.assertTrue(path.is_file())
                row = json.loads(path.read_text(encoding="utf-8").strip().splitlines()[-1])
                self.assertEqual(row["decision"], "landed X")
                self.assertEqual(row["paths"][0], "notes/WORK_QUEUE.md")
                self.assertEqual(row["needle"], "OVERSEER_TEST_NEEDLE")
                self.assertEqual(row["kind"], "session_ledger")

    def test_append_scrubs_secrets_in_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            led = Path(tmp) / "session_ledger"
            with mock.patch.object(psa, "SESSION_LEDGER_DIR", led):
                path = psa.append_session_ledger(
                    decision="token sk_live_ABCDEFGHIJKLMNOP leaked",
                    paths=[],
                )
                body = path.read_text(encoding="utf-8")
                self.assertNotIn("sk_live_ABCDEFGHIJKLMNOP", body)
                self.assertIn("[REDACTED]", body)


class SpacedStickyTests(unittest.TestCase):
    def test_emits_every_n(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            with mock.patch.object(psa, "STATE_PATH", state_path):
                psa._save_state(
                    {
                        "hot_refresh_count": 0,
                        "last_sticky_at": 0,
                        "sticky_every_n": 3,
                    }
                )
                blocks = [psa.format_spaced_sticky_block(bump=True) for _ in range(3)]
                self.assertEqual(blocks[0], "")
                self.assertEqual(blocks[1], "")
                self.assertIn(psa.NO_PAY_STICKY, blocks[2])
                self.assertIn(psa.FACTORY_WORKS_STICKY, blocks[2])
                self.assertIn(psa.PACK_SAFE_STICKY, blocks[2])

    def test_force_preview_no_bump(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            with mock.patch.object(psa, "STATE_PATH", state_path):
                before = psa.sticky_status()["hot_refresh_count"]
                block = psa.format_spaced_sticky_block(force=True, bump=False)
                after = psa.sticky_status()["hot_refresh_count"]
                self.assertEqual(before, after)
                self.assertIn("NO PAY", block)


class DistillTests(unittest.TestCase):
    def test_distill_to_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conv = Path(tmp) / "PEER_CONVERSATION.md"
            conv.write_text(
                "# Peer conversation\n\n## Recent turns (since summary)\n\nold\n",
                encoding="utf-8",
            )
            with mock.patch.object(psa, "PEER_CONVERSATION_MD", conv):
                text = (
                    "- Fixed noop in `scripts/peer_loop.py:120`\n"
                    "- Needle `OVERSEER_TEST_NEEDLE` confirmed\n"
                    "- Vague without cite\n"
                )
                result = psa.distill_turn(text, target="conversation")
                self.assertEqual(result["bullets"], 3)
                self.assertEqual(result["uncited"], 1)
                body = conv.read_text(encoding="utf-8")
                self.assertIn("turn-end distill", body)
                self.assertIn("peer_loop.py", body)

    def test_distill_last_cycle_pins(self) -> None:
        state: dict = {"last_cycle": {"verify_ok": True, "note": "ok"}}
        bullets = ["WQ Active open count in `notes/WORK_QUEUE.md:1`", "no cite"]
        psa.distill_to_last_cycle_pins(bullets, state=state)
        pins = state["last_cycle"]["amnesia_pins"]
        self.assertEqual(len(pins), 2)
        self.assertTrue(pins[0]["cited"])
        self.assertFalse(pins[1]["cited"])


class ClaimLedgerTests(unittest.TestCase):
    def test_overclaim_without_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            claims = Path(tmp) / "claims"
            with mock.patch.object(psa, "CLAIM_LEDGER_DIR", claims):
                row = psa.evaluate_session_claim("verify green")
                self.assertEqual(row["verdict"], "OVERCLAIM")
                self.assertTrue((claims / f"{psa._utc_day()}.jsonl").is_file())

    def test_pass_with_matching_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            claims = Path(tmp) / "claims"
            # Use real always-read file that contains known tokens
            source = "notes/AGENT_WORKING_MEMORY.md:1"
            with mock.patch.object(psa, "CLAIM_LEDGER_DIR", claims):
                row = psa.evaluate_session_claim(
                    "Agent working memory always-read SoT index",
                    source=source,
                )
                self.assertIn(row["verdict"], ("PASS", "SPLIT"))
                self.assertTrue(row["source"].startswith("notes/"))

    def test_fail_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            claims = Path(tmp) / "claims"
            with mock.patch.object(psa, "CLAIM_LEDGER_DIR", claims):
                row = psa.evaluate_session_claim(
                    "phantom fact",
                    source="notes/DOES_NOT_EXIST_AMNESIA.md:1",
                )
                self.assertEqual(row["verdict"], "FAIL")


class HubRulesAndHotTests(unittest.TestCase):
    def test_hub_rules_mention_scratch(self) -> None:
        block = psa.worktree_hub_rules_block()
        self.assertIn("worktree_scratch", block)
        self.assertIn("Hub SoT", block)
        self.assertIn("never delete live SoT", block)

    def test_harness_still_builds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            with mock.patch.object(psa, "STATE_PATH", state_path):
                text = pt.format_harness_memory({"last_cycle": {}})
                self.assertIn("Always-read", text)

    def test_last_cycle_shows_pins(self) -> None:
        block = pt.format_last_cycle_block(
            {
                "last_cycle": {
                    "ts": 1.0,
                    "verify_ok": True,
                    "noop": False,
                    "amnesia_pins": [
                        {"text": "pin `notes/WORK_QUEUE.md:1`", "cited": True},
                    ],
                }
            }
        )
        self.assertIn("Amnesia pins", block)
        self.assertIn("WORK_QUEUE", block)


if __name__ == "__main__":
    unittest.main()
