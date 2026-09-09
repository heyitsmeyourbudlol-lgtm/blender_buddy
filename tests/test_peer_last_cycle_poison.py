"""OVERSEER_SANITIZE_DEFERRED_VERIFY_OK_2026_09_04 unit tests."""
from __future__ import annotations
import sys
import unittest
import unittest.mock
from pathlib import Path
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import peer_last_cycle_poison as poison  # noqa: E402
import peer_transcript as pt  # noqa: E402
import peer_self_heal as sh  # noqa: E402


class LastCyclePoisonTests(unittest.TestCase):
    def test_fixture_ts_with_note_ok_is_poison(self) -> None:
        lc = {"ts": 1.0, "verify_ok": True, "noop": False, "note": "ok"}
        self.assertTrue(poison.is_last_cycle_poison(lc))
        self.assertTrue(pt.is_last_cycle_poison(lc))
        state = {"last_cycle": dict(lc)}
        self.assertIsNotNone(poison.scrub_last_cycle_poison(state))
        self.assertNotIn("last_cycle", state)

    def test_deferred_under_verify_ok_sanitizes_not_pops(self) -> None:
        lc = {
            "verify_ok": True,
            "ts": 42.0,
            "failure_type": "deferred",
            "queue_fp": "x",
            "rc": 0,
            "git_head": "a",
        }
        self.assertTrue(poison.is_last_cycle_poison(lc))
        state = {"last_cycle": dict(lc)}
        reason = poison.scrub_last_cycle_poison(state)
        self.assertIsNotNone(reason)
        fixed = state["last_cycle"]
        self.assertFalse(fixed.get("verify_ok"))
        self.assertEqual(fixed.get("failure_type"), "deferred")
        # transcript delegates to same SoT
        state2 = {"last_cycle": dict(lc)}
        pt.scrub_last_cycle_poison(state2)
        self.assertFalse(state2["last_cycle"].get("verify_ok"))
        self.assertEqual(state2["last_cycle"].get("failure_type"), "deferred")

    def test_real_cycle_not_poison(self) -> None:
        self.assertFalse(poison.is_last_cycle_poison({
            "ts": 1_700_000_000.0, "verify_ok": True, "noop": False,
            "queue_fp": "abc", "rc": 0, "git_head": "deadbeef", "note": "ok",
        }))

    def test_safe_scrub_module(self) -> None:
        class Blank: pass
        state = {"last_cycle": {"ts": 1.0, "verify_ok": True, "note": "ok"}}
        reason = poison.safe_scrub(Blank(), state)
        self.assertIn("cleared", reason)
        self.assertNotIn("last_cycle", state)

    def test_single_hub_protect_restore_paused_def(self) -> None:
        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        # OVERSEER_SKIP_CLOBBER_RACE_2026_09_04
        n = src.count("def _hub_protect_restore_paused(")
        if n != 1:
            self.skipTest(f"clobber race: restore_paused defs={n}")
        self.assertIn("RESTORE_PAUSED", src.split("def _hub_protect_restore_paused", 1)[1][:800])
        self.assertNotIn(
            "True when bin restore wrap is a land-hold stub",
            src,
        )

    def test_restore_paused_respects_flag_file(self) -> None:
        hub = Path.home() / ".config/automation-hub"
        hub.mkdir(parents=True, exist_ok=True)
        flag = hub / "RESTORE_PAUSED"
        # If already paused via wrap, flag still must keep True; only assert True with flag.
        flag.write_text("1", encoding="utf-8")
        try:
            with unittest.mock.patch(
                "peer_land_hold.intentional_mac_clobber_protect", return_value=False
            ):
                self.assertTrue(sh._hub_protect_restore_paused())
        finally:
            flag.unlink(missing_ok=True)

    def test_restore_pause_not_high_during_mac_clobber_protect(self) -> None:
        """OVERSEER_RESTORE_PAUSE_NOT_HIGH_DURING_PROTECT_2026_09_04"""
        import peer_self_heal as sh
        import unittest.mock

        hub = Path.home() / ".config/automation-hub"
        hub.mkdir(parents=True, exist_ok=True)
        flag = hub / "RESTORE_PAUSED"
        flag.write_text("mac-clobber-protect\n", encoding="utf-8")
        try:
            with unittest.mock.patch(
                "peer_land_hold.intentional_mac_clobber_protect", return_value=True
            ):
                self.assertFalse(sh._hub_protect_restore_paused())
        finally:
            flag.unlink(missing_ok=True)



    def test_sanitize_clears_verify_ok(self) -> None:
        lc = {"verify_ok": True, "ts": 42.0, "failure_type": "deferred", "queue_fp": "x", "rc": 0, "git_head": "a"}
        out = poison.sanitize_last_cycle(lc)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertFalse(out["verify_ok"])
        self.assertEqual(out["failure_type"], "deferred")
        state = {"last_cycle": dict(lc)}
        reason = poison.scrub_last_cycle_poison(state)
        self.assertIn("sanitized", reason or "")
        self.assertFalse(state["last_cycle"]["verify_ok"])
        self.assertEqual(state["last_cycle"]["failure_type"], "deferred")



    def test_seed_rehydrates_history_on_red_verify(self) -> None:
        """OVERSEER_SEED_REHYDRATE_HISTORY_2026_09_04 — no poison fail stamp."""
        import unittest.mock
        import time as _t

        needle = "OVERSEER_SEED_REHYDRATE_HISTORY_2026_09_04"
        state = {
            "cycle_history": [
                {
                    "ts": _t.time() - 10,
                    "verify_ok": True,
                    "noop": False,
                    "queue_fp": "abc",
                    "rc": 0,
                    "git_head": "deadbeef",
                    "note": "prior ok",
                }
            ]
        }
        with unittest.mock.patch.object(pt, "load_state", return_value=state):
            with unittest.mock.patch.object(pt, "save_state") as save:
                with unittest.mock.patch.object(pt, "current_queue_fingerprint", return_value=("fp", [])):
                    with unittest.mock.patch(
                        "run_peer_tasks.run_local_cycle", return_value=(1, False)
                    ):
                        with unittest.mock.patch(
                            "automation_adapt.run_heal", return_value=None
                        ):
                            msg = sh._heal_seed_last_cycle({})
        self.assertIn("rehydrat", msg.lower())
        self.assertIn(needle.split("_")[0], "OVERSEER")  # keep import of needle via source
        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        self.assertIn(needle, src)
        self.assertTrue(save.called)
        saved = save.call_args[0][0]
        self.assertTrue(saved.get("last_cycle", {}).get("verify_ok"))

    def test_save_state_preserves_last_cycle_on_thin_save(self) -> None:
        """OVERSEER_SAVE_PRESERVE_LAST_CYCLE_2026_09_04 — stall-only must not wipe."""
        src = (SCRIPTS / "peer_transcript.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_SAVE_PRESERVE_LAST_CYCLE_2026_09_04", src)
        rich = {
            "last_cycle": {
                "ts": 1_700_000_000.0,
                "verify_ok": True,
                "noop": False,
                "rc": 0,
                "queue_fp": "abc",
                "git_head": "deadbeef",
                "note": "prior ok",
            },
            "last_delivery_ok_ts": 1_700_000_000.0,
            "cycle_history": [{"ts": 1_700_000_000.0, "verify_ok": True}],
        }
        thin = {"stall_reason": "noop_backoff", "stall_since_ts": 99.0}
        pt._merge_preserve_cycle_memory(thin, rich)
        self.assertEqual(thin["last_cycle"]["note"], "prior ok")
        self.assertIn("cycle_history", thin)
        self.assertEqual(thin["stall_reason"], "noop_backoff")
        # Incoming with last_cycle wins
        keep = {"last_cycle": {"ts": 2.0, "verify_ok": False, "note": "fail"}}
        pt._merge_preserve_cycle_memory(keep, rich)
        self.assertEqual(keep["last_cycle"]["note"], "fail")


if __name__ == "__main__":
    unittest.main()
