#!/usr/bin/env python3
"""OVERSEER_SCRUB_ORPHAN_FORGE_* — stagnation land 2026-09-04."""
from __future__ import annotations
import sys, tempfile, unittest
from pathlib import Path
from unittest import mock
SCRIPTS = Path("/home/arnavrastogi/Automation/scripts")
sys.path.insert(0, str(SCRIPTS))
import automation_improve as improve
import peer_product_forge as forge
import run_peer_tasks as rpt

class OverseerForgeScrubTests(unittest.TestCase):
    def test_prepare_verify_lane_scrubs_inactive_forge_orphans(self) -> None:
        logs: list[str] = []
        with mock.patch("dgx_ram_budget.trim_unittest_storm", return_value=0), mock.patch(
            "dgx_ram_budget.trim_self_check_storm", return_value=0
        ), mock.patch("peer_product_forge.forge_active", return_value=False), mock.patch(
            "peer_product_forge.scrub_orphan_forge_agents", return_value=3
        ) as scrub:
            rpt._prepare_verify_lane(log_fn=logs.append)
        scrub.assert_called_once()
        self.assertTrue(any("scrubbed 3" in m for m in logs))

    def test_scrub_fallback_no_hardcoded_user_home(self) -> None:
        text = Path(forge.__file__).read_text(encoding="utf-8")
        start = text.index("def scrub_orphan_forge_agents")
        end = text.index("\ndef dispatch_forge_agents", start)
        body = text[start:end]
        code = "\n".join(ln for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith("#"))
        self.assertNotIn('Path("/Users/', code)
        self.assertNotIn('Path("/home/', code)
        self.assertIn("CAAS_ROOT", body)
        self.assertIn('Path.home() / "CaaS"', body)

    def test_scrub_fallback_uses_caas_root_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            caas = Path(tmp) / "CaaS"
            caas.mkdir()
            state.write_text('{"active": false}\n')
            fake = mock.Mock(pid=424243)
            with mock.patch.object(forge, "STATE_PATH", state), mock.patch.dict(
                "os.environ", {"CAAS_ROOT": str(caas)}, clear=False
            ), mock.patch("peer_parallel_dispatch.find_agent_procs", return_value=[fake]), mock.patch(
                "peer_parallel_dispatch._proc_cwd", return_value=caas
            ), mock.patch("os.kill") as kill:
                n = forge.scrub_orphan_forge_agents()
            self.assertEqual(n, 1)
            kill.assert_called_once()

    def test_apply_mechanical_scrubs_inactive_forge_orphans(self) -> None:
        signals = improve.ImproveSignals(live={}, audit_ok=True, audit_warnings=[], audit_errors=[], queue_drift=[], loop_state={})
        with mock.patch.object(improve.adapt, "should_re_adapt", return_value=False), mock.patch(
            "peer_self_heal.self_heal_enabled", return_value=False
        ), mock.patch.object(improve.subprocess, "Popen"), mock.patch(
            "peer_product_forge.forge_active", return_value=False
        ), mock.patch("peer_product_forge.scrub_orphan_forge_agents", return_value=5) as scrub:
            actions = improve.apply_mechanical(signals, log_fn=lambda _m: None, run_verify=False)
        scrub.assert_called_once()
        self.assertTrue(any("scrubbed 5" in a for a in actions))

if __name__ == "__main__":
    raise SystemExit(unittest.main())
