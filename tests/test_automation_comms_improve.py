"""Tests for automation_comms_improve."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import automation_comms_improve as ci  # noqa: E402


class TestCommsImprove(unittest.TestCase):
    def test_is_comms_kit_target(self) -> None:
        opp = ci.Opportunity("efficiency", "Extend GLink schema", "peer_agent_comms.py", priority=10)
        self.assertTrue(ci.is_comms_kit_target(opp))
        meta = ci.Opportunity("better", "Comms horizon cosmetic", "automation_comms_improve UI", priority=10)
        self.assertFalse(ci.is_comms_kit_target(meta))

    def test_rank_detects_disabled_comms(self) -> None:
        signals = ci.CommsSignals(
            live={},
            comms_status={"enabled": False, "bus_messages": 0},
            research={"gaps": [], "partials": []},
        )
        opps = ci.rank_opportunities(signals)
        self.assertTrue(any("Enable GLink" in o.title for o in opps))

    def test_plan_prompt_excludes_factory(self) -> None:
        signals = ci.CommsSignals(
            live={},
            comms_status={"enabled": True, "bus_messages": 1},
            research={"gap_count": 1, "partial_count": 2},
            opportunities=[ci.Opportunity("efficiency", "GLink validator", "peer_agent_comms", 10)],
        )
        text = ci.build_plan_prompt(signals)
        self.assertIn("communication efficiency", text.lower())
        self.assertIn("not in scope", text.lower())

    def test_verify_blocks_when_unittest_fails(self) -> None:
        with mock.patch.object(ci, "_run_comms_unittest_suite", return_value=(False, ["boom"])):
            with mock.patch.object(ci, "_run_comms_smoke_checks", return_value=(True, [])):
                result = ci.verify_comms_kit()
        self.assertFalse(result.ok)
        self.assertIn("red light", result.detail.lower())

    def test_verify_green_when_both_pass(self) -> None:
        with mock.patch.object(ci, "_run_comms_unittest_suite", return_value=(True, [])):
            with mock.patch.object(ci, "_run_comms_smoke_checks", return_value=(True, [])):
                result = ci.verify_comms_kit()
        self.assertTrue(result.ok)
        self.assertIn("green light", result.detail.lower())

    def test_run_comms_cycle_skips_enqueue_on_red(self) -> None:
        red = ci.CommsVerifyResult(False, False, False, "red light", ["fail"])
        with mock.patch.object(ci, "verify_comms_kit", return_value=red):
            with mock.patch.object(ci, "gather_signals") as gs:
                gs.return_value = ci.CommsSignals(
                    live={},
                    comms_status={"enabled": True},
                    research={},
                    opportunities=[
                        ci.Opportunity("efficiency", "GLink", "peer_agent_comms", 10),
                    ],
                )
                with mock.patch.object(ci, "wake_peer") as wake:
                    with mock.patch.object(ci, "enqueue_comms_work", return_value=["x"]) as enq:
                        with mock.patch.object(ci, "write_prompts", return_value=[]):
                            with mock.patch.object(ci, "write_horizon", return_value=[]):
                                ci.run_comms_cycle(quick=True, research=False, log_fn=lambda _m: None)
                    wake.assert_not_called()
                    enq.assert_not_called()

    def test_cmd_install_linux_calls_linux_install_daemon(self) -> None:
        """OVERSEER_COMMS_LINUX_INSTALL_2026_09_06 — no launchctl on Linux."""
        import peer_self_heal as heal

        with mock.patch.object(ci, "comms_self_test_required", return_value=False):
            with mock.patch.object(ci.sys, "platform", "linux"):
                with mock.patch.object(heal, "ensure_canonical_module"):
                    with mock.patch.object(
                        heal, "linux_install_daemon", return_value="unit ok"
                    ) as inst:
                        with mock.patch.object(ci.subprocess, "run") as run:
                            rc = ci.cmd_install()
        self.assertEqual(rc, 0)
        inst.assert_called_once_with("comms-improve")
        run.assert_not_called()

    def test_cmd_uninstall_linux_calls_linux_uninstall_daemon(self) -> None:
        """OVERSEER_COMMS_LINUX_INSTALL_2026_09_06"""
        import peer_self_heal as heal

        with mock.patch.object(ci.sys, "platform", "linux"):
            with mock.patch.object(heal, "ensure_canonical_module"):
                with mock.patch.object(
                    heal, "linux_uninstall_daemon", return_value="gone"
                ) as un:
                    with mock.patch.object(ci.subprocess, "run") as run:
                        rc = ci.cmd_uninstall()
        self.assertEqual(rc, 0)
        un.assert_called_once_with("comms-improve")
        run.assert_not_called()

    def test_enqueue_skips_done_wave19_items(self) -> None:
        """Re-enqueue of landed [x] items caused noop Active refill (wave-54)."""
        import tempfile

        done_line = (
            "- [x] **[comms-improve] Bus payload too verbose — enforce GLink codes** — "
            "landed wave-19 (MAX_PROSE_WORDS + reject)"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wq = root / "WORK_QUEUE.md"
            ctx = root / "self_improve_context.md"
            wq.write_text(f"## Active\n{done_line}\n\n## Backlog\n", encoding="utf-8")
            ctx.write_text(
                f"## Remaining work (priority order)\n{done_line}\n\n## Backlog\n",
                encoding="utf-8",
            )
            opp = ci.Opportunity(
                "efficiency",
                "Bus payload too verbose — enforce GLink codes",
                "Add validator in peer_agent_comms.post_glink; reject English-heavy p blobs",
                14,
            )
            signals = ci.CommsSignals(
                live={},
                comms_status={"enabled": True},
                research={},
                opportunities=[opp],
            )
            with mock.patch.object(ci.auto, "WORK_QUEUE_PATH", wq):
                with mock.patch.object(ci.auto, "CONTEXT_PATH", ctx):
                    logs: list[str] = []
                    inserted = ci.enqueue_comms_work(signals, log_fn=logs.append, cap=5)
            self.assertEqual(inserted, [])
            self.assertTrue(any("skip duplicate" in m for m in logs))
            self.assertNotIn("- [ ]", wq.read_text(encoding="utf-8"))

    def test_enqueue_parks_under_creative_not_active(self) -> None:
        """OVERSEER_DEMOTE_KIT_THEATER_ACTIVE_2026_09_08 — never Active."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wq = root / "WORK_QUEUE.md"
            ctx = root / "self_improve_context.md"
            cre = root / "CREATIVE_BACKLOG.md"
            wq.write_text(
                "## Active\n"
                "- [ ] **[factory] Kit-run twenty-fifth** — next\n\n"
                "## Creative backlog\n",
                encoding="utf-8",
            )
            ctx.write_text(
                "## Remaining work (priority order)\n"
                "- [ ] **[factory] Kit-run twenty-fifth** — next\n\n"
                "## Creative backlog\n",
                encoding="utf-8",
            )
            cre.write_text("# Creative\n\n## Next experiments\n", encoding="utf-8")
            opp = ci.Opportunity(
                "efficiency",
                "Brand new GLink correlator ids",
                "Add REQ/ACK correlation ids to STAT/DIFF",
                14,
            )
            signals = ci.CommsSignals(
                live={},
                comms_status={"enabled": True},
                research={},
                opportunities=[opp],
            )
            with mock.patch.object(ci.auto, "WORK_QUEUE_PATH", wq):
                with mock.patch.object(ci.auto, "CONTEXT_PATH", ctx):
                    with mock.patch.object(
                        ci.auto, "load_creative_backlog_md", return_value=cre.read_text()
                    ):
                        logs: list[str] = []
                        inserted = ci.enqueue_comms_work(
                            signals, log_fn=logs.append, cap=5
                        )
            self.assertEqual(inserted, ["Brand new GLink correlator ids"])
            wq_txt = wq.read_text(encoding="utf-8")
            active = wq_txt.split("## Creative backlog", 1)[0]
            self.assertNotIn("[comms-improve]", active)
            self.assertIn("[factory] Kit-run twenty-fifth", active)
            cre_sec = wq_txt.split("## Creative backlog", 1)[1]
            self.assertIn("[comms-improve]", cre_sec)
            self.assertIn("OVERSEER_DEMOTE_KIT_THEATER_ACTIVE_2026_09_08", cre_sec)
            self.assertTrue(any("enqueue: creative" in m for m in logs))


if __name__ == "__main__":
    unittest.main()
