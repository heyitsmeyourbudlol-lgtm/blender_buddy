#!/usr/bin/env python3
"""Tests for peer_error_adapt — never-idle recovery."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_error_adapt as err  # noqa: E402


class TestPeerErrorAdapt(unittest.TestCase):
    def test_soften_recoverable_keeps_secrets_hard(self) -> None:
        report = MagicMock()
        soft = MagicMock(status="fail", gap="Institutional memory", detail="drift")
        hard = MagicMock(status="fail", gap="Secret hygiene", detail="sk-xxx")
        report.results = [soft, hard]
        n = err.soften_recoverable_fails(report)
        self.assertEqual(n, 1)
        self.assertEqual(soft.status, "warn")
        self.assertEqual(hard.status, "fail")

    def test_adapt_plan_gate_clears_after_heal(self) -> None:
        blocked = MagicMock()
        blocked.blocked = True
        blocked.role_id = "orchestrator"
        blocked.results = [
            MagicMock(status="fail", gap="Institutional memory", detail="1 drift"),
        ]
        clear = MagicMock()
        clear.blocked = False
        clear.results = []
        with (
            patch.object(err, "heal_recoverable_gate_fails", return_value=["sync-queue:1"]),
            patch("peer_agent_gates.run_plan_gate", return_value=clear),
        ):
            still, acts = err.adapt_plan_gate(blocked, log_fn=lambda _m: None, use_agent=False)
        self.assertFalse(still)
        self.assertIn("gate-clear", acts)

    def test_adapt_plan_gate_pivots_when_hard(self) -> None:
        blocked = MagicMock()
        blocked.blocked = True
        blocked.role_id = "orchestrator"
        blocked.results = [
            MagicMock(status="fail", gap="Secret hygiene", detail="secret"),
        ]
        with (
            patch.object(err, "heal_recoverable_gate_fails", return_value=[]),
            patch("peer_agent_gates.run_plan_gate", return_value=blocked),
            patch("peer_stall_pivot.maybe_pivot", return_value=True) as pivot,
            patch.object(err, "_wake_loops"),
        ):
            still, acts = err.adapt_plan_gate(blocked, log_fn=lambda _m: None, use_agent=False)
        self.assertTrue(still)
        self.assertIn("stall-pivot", acts)
        pivot.assert_called_once()
        self.assertEqual(pivot.call_args.kwargs.get("reason"), "plan_gate_blocked")


    def test_clear_autonomy_delays_clears_noop_and_cooldown(self) -> None:
        state = {
            "last_cycle": {"noop": True, "verify_ok": True, "ts": 1},
            "last_local_verify_ts": 9999999999.0,
            "stall_reason": "noop_backoff",
        }
        with (
            patch.object(err, "_load_loop_state_lite", return_value=state),
            patch("peer_transcript.save_state") as save,
            patch.object(err, "_wake_loops"),
            patch.object(err, "never_delay_on_error", return_value=True),
        ):
            acts = err.clear_autonomy_delays(reason="noop-mislabel")
        self.assertIn("noop-cleared", acts)
        self.assertIn("verify-cooldown-cleared", acts)
        self.assertFalse(state["last_cycle"]["noop"])
        self.assertEqual(state["last_local_verify_ts"], 0.0)
        save.assert_called_once()

    def test_clear_autonomy_keeps_noop_on_generic_error(self) -> None:
        """OVERSEER_CLEAR_DELAYS_KEEP_NOOP_2026_09_07"""
        state = {
            "last_cycle": {"noop": True, "verify_ok": True, "ts": 1},
            "last_local_verify_ts": 9999999999.0,
            "stall_reason": "noop_backoff",
        }
        with (
            patch.object(err, "_load_loop_state_lite", return_value=state),
            patch("peer_transcript.save_state") as save,
            patch.object(err, "_wake_loops"),
            patch.object(err, "never_delay_on_error", return_value=True),
        ):
            acts = err.clear_autonomy_delays(reason="verify-fail-bypass")
        self.assertNotIn("noop-cleared", acts)
        self.assertIn("verify-cooldown-cleared", acts)
        self.assertTrue(state["last_cycle"]["noop"])
        save.assert_called_once()

    def test_clear_autonomy_delays_clean_no_tx_no_improve_import(self) -> None:
        """CLEAR_DELAYS_LITE_STATE_NO_TX_IMPORT + WAKE_NO_COLD_IMPROVE."""
        self.assertIn(
            "CLEAR_DELAYS_LITE_STATE_NO_TX_IMPORT_2026_09_08",
            (SCRIPTS / "peer_error_adapt.py").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "CLEAR_DELAYS_WAKE_NO_COLD_IMPROVE_IMPORT_2026_09_08",
            (SCRIPTS / "peer_error_adapt.py").read_text(encoding="utf-8"),
        )
        # Already-clean state: no save → peer_transcript must stay unloaded.
        clean = {"last_cycle": {"noop": False, "verify_ok": True}, "last_local_verify_ts": 0.0}
        for mod in list(sys.modules):
            if mod == "peer_transcript" or mod.startswith("peer_transcript."):
                del sys.modules[mod]
            if mod == "automation_improve" or mod.startswith("automation_improve."):
                del sys.modules[mod]
        with (
            patch.object(err, "_load_loop_state_lite", return_value=dict(clean)),
            patch.object(err, "never_delay_on_error", return_value=True),
            tempfile.TemporaryDirectory() as tmp,
        ):
            cfg = Path(tmp)
            with patch.object(err.auto, "CONFIG_DIR", cfg):
                acts = err.clear_autonomy_delays(reason="bench-clean")
            self.assertNotIn("peer_transcript", sys.modules)
            self.assertNotIn("automation_improve", sys.modules)
            self.assertTrue((cfg / "peer-turn.signal").is_file())
            self.assertTrue((cfg / "improve-wake.signal").is_file())
            # No mutations → no action labels (wake still fires, but actions empty).
            self.assertEqual(acts, [])

    def test_clear_autonomy_skips_auth_not_ready(self) -> None:
        """Auth thrash: clear_autonomy on 'auth not ready' must not wake loops."""
        with (
            patch.object(err, "never_delay_on_error", return_value=True),
            patch.object(err, "_wake_loops") as wake,
            patch.object(err, "_load_loop_state_lite") as load,
        ):
            acts = err.clear_autonomy_delays(reason="live log: auth not ready — pt")
        self.assertEqual(acts, ["auth-hold"])
        load.assert_not_called()
        wake.assert_not_called()

    def test_adapt_plan_gate_soften_omits_clear_autonomy(self) -> None:
        from peer_agent_gates import GateReport, GateResult
        blocked = GateReport(
            phase="plan", role_id="orchestrator",
            results=[GateResult(gap="Institutional memory", weakness="drift", status="fail", detail="1 drift", command="sync-queue")],
        )
        with (
            patch.object(err, "heal_recoverable_gate_fails", return_value=[]),
            patch("peer_agent_gates.run_plan_gate", return_value=blocked),
            patch.object(err, "clear_autonomy_delays", return_value=["cleared"]) as clear,
            patch.object(err, "_wake_loops"),
        ):
            still, acts = err.adapt_plan_gate(blocked, log_fn=lambda _m: None, use_agent=False)
        self.assertFalse(still)
        self.assertTrue(any(str(a).startswith("soften:") for a in acts))
        clear.assert_not_called()

    def test_adapt_agent_failure_auth_hold_no_clear(self) -> None:
        with patch.object(err, "clear_autonomy_delays", return_value=["cleared"]) as clear:
            acts = err.adapt_agent_failure(
                rc=1, note="auth not ready", auth_failed=True, log_fn=lambda _m: None
            )
        clear.assert_not_called()
        self.assertIn("auth-hold", acts)

    def test_ensure_driving_auth_hold_skips_live_clear(self) -> None:
        clear_report = MagicMock(blocked=False, results=[])
        with (
            patch("peer_agent_gates.run_plan_gate", return_value=clear_report),
            patch("peer_oversight_events.scan_live_error_hits", return_value=["auth not ready"]),
            patch.object(err, "clear_autonomy_delays", return_value=["cleared"]) as clear,
            patch("peer_terminal.cursor_agent_auth_ready", return_value=(False, "auth not ready")),
        ):
            out = err.ensure_driving(log_fn=lambda _m: None, quick=True)
        self.assertIn("auth-hold", out.get("actions") or [])
        clear.assert_not_called()

    def test_heal_all_expands_without_nested_verify(self) -> None:
        """OVERSEER_ERROR_ADAPT_NO_NESTED_VERIFY_2026_09_07"""
        self.assertEqual(
            err._playbook_verbs("heal-all"),
            ("self-heal", "compact-queue", "sync-queue"),
        )
        self.assertNotIn("verify-gate", err._playbook_verbs("heal-all"))
        actions: list[str] = []
        calls: list[list[str]] = []

        def _fake_run(cmd, **kwargs):  # noqa: ANN001
            calls.append(list(cmd))
            return MagicMock(returncode=0)

        with patch.object(err.subprocess, "run", side_effect=_fake_run):
            err._try_playbook_command(
                "./scripts/peer heal-all",
                log_fn=lambda _m: None,
                actions=actions,
            )
        verbs = [c[1] for c in calls]
        self.assertEqual(verbs, ["self-heal", "compact-queue", "sync-queue"])
        self.assertTrue(all(a.startswith("cmd:heal-all->") for a in actions))


if __name__ == "__main__":
    unittest.main()
