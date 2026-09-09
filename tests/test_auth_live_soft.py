"""OVERSEER_AUTH_LIVE_SOFT_2026_09_04 — stale auth log must not critical-stampede."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_oversight_events as oevents  # noqa: E402


class AuthLiveSoftTests(unittest.TestCase):
    def _isolate_live_probes(self):
        """Block live dual-brain / drift / Active probes (flaky critical under race)."""
        return (
            mock.patch.object(oevents, "_dual_brain_mismatch", return_value=False),
            mock.patch.object(oevents, "_queue_drift_count", return_value=0),
            mock.patch.object(oevents, "_active_queue_metrics", return_value=("", 0)),
        )

    def test_auth_hit_skipped_when_desktop_ready(self) -> None:
        ctx = {
            "last_cycle": {},
            "kit": {},
            "ram": {},
            "queue_count": 0,
            "phase": "WORKING",
            "auth_ready": True,
        }
        dbrain, drift, active = self._isolate_live_probes()
        with mock.patch.object(
            oevents,
            "scan_live_error_hits",
            return_value=["live log: auth not ready — pt: cleared autonomy delays"],
        ), mock.patch(
            "peer_terminal.desktop_auth_ready",
            return_value=(True, "desktop login"),
        ), dbrain, drift, active:
            rep = oevents.evaluate_stagnation(ctx, {"open": 0}, state={"snapshots": []})
        self.assertFalse(any("auth not ready" in r for r in rep.reasons))
        self.assertFalse(rep.critical)

    def test_auth_hit_noncritical_when_auth_down(self) -> None:
        ctx = {
            "last_cycle": {},
            "kit": {},
            "ram": {},
            "queue_count": 0,
            "phase": "WORKING",
            "auth_ready": False,
        }
        dbrain, drift, active = self._isolate_live_probes()
        with mock.patch.object(
            oevents,
            "scan_live_error_hits",
            return_value=["live log: auth not ready — run cursor-agent login"],
        ), mock.patch(
            "peer_terminal.desktop_auth_ready",
            return_value=(False, "not logged in"),
        ), dbrain, drift, active:
            rep = oevents.evaluate_stagnation(ctx, {"open": 0}, state={"snapshots": []})
        self.assertTrue(any("auth not ready" in r for r in rep.reasons))
        self.assertFalse(rep.critical)

    def test_paid_api_key_auth_detail_soft_skipped(self) -> None:
        """OVERSEER_AUTH_PAID_API_SOFT_2026_09_04 — KEY redirect ≠ auth down."""
        src = (SCRIPTS / "peer_oversight_events.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_AUTH_PAID_API_SOFT_2026_09_04", src)
        ctx = {
            "last_cycle": {"verify_ok": True, "noop": False, "rc": 0},
            "kit": {
                "factory_pct": 99,
                "daemons": {"peer_loop": True, "improve_loop": True},
                "tests_ok": True,
                "audit_ok": True,
                "queue_drift": 0,
            },
            "ram": {"dispatch_allowed": True},
            "queue_count": 0,
            "phase": "WORKING",
            "noop_backoff_sec": 0,
            "auth_ready": False,
            "auth_detail": "CURSOR_API_KEY set — use --paid-api for API billing path",
            "daemon_running": True,
            "bottlenecks": [],
            "git_clean": True,
        }
        with mock.patch.object(oevents, "scan_live_error_hits", return_value=[]), mock.patch.object(
            oevents, "_dual_brain_mismatch", return_value=False
        ), mock.patch.object(oevents, "_queue_drift_count", return_value=0), mock.patch.object(
            oevents, "_active_queue_metrics", return_value=("", 0)
        ):
            rep = oevents.evaluate_stagnation(
                ctx, {"open": 0, "critical": 0, "high": 0}, state={"snapshots": []}
            )
        self.assertFalse(any("cursor auth not ready" in r for r in rep.reasons))


if __name__ == "__main__":
    unittest.main()
