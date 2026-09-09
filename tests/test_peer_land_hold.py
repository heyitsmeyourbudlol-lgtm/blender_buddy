"""Land-hold TTL + CLEAR_STALE_RESTORE_PAUSED."""
from __future__ import annotations
import sys, tempfile, time, unittest
from pathlib import Path
from unittest import mock
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import peer_land_hold as lh  # noqa: E402

class LandHoldFutureMtimeTests(unittest.TestCase):
    def test_future_mtime_age_exceeds_max(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hold = Path(tmp) / "OVERSEER_LAND_HOLD"
            hold.write_text("hold\n", encoding="utf-8")
            future = time.time() + 2 * 3600
            import os
            os.utime(hold, (future, future))
            age = lh.hold_age_sec(hold)
            self.assertIsNotNone(age)
            assert age is not None
            self.assertGreaterEqual(age, lh.MAX_AGE_SEC)

    def test_clear_expired_removes_future_mtime_hold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hold = Path(tmp) / "OVERSEER_LAND_HOLD"
            hold.write_text("hold\n", encoding="utf-8")
            future = time.time() + 7200
            import os
            os.utime(hold, (future, future))
            with mock.patch.object(lh, "HOLD_PATH", hold), mock.patch.object(
                lh, "ROOT_HOLD", Path(tmp) / "no-root"
            ), mock.patch.object(lh, "RESTORE_PAUSED_FLAGS", ()), mock.patch.object(
                lh, "unstub_restore", return_value="restore not paused"
            ):
                msg = lh.clear_expired()
            self.assertIn("cleared", msg)
            self.assertFalse(hold.exists())

    def test_fresh_hold_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hold = Path(tmp) / "OVERSEER_LAND_HOLD"
            hold.write_text("hold\n", encoding="utf-8")
            with mock.patch.object(lh, "HOLD_PATH", hold), mock.patch.object(
                lh, "ROOT_HOLD", Path(tmp) / "no-root"
            ), mock.patch.object(lh, "RESTORE_PAUSED_FLAGS", ()):
                msg = lh.clear_expired()
            self.assertIn("fresh", msg)
            self.assertTrue(hold.exists())

class ClearStaleRestorePausedTests(unittest.TestCase):
    def test_clear_stale_removes_flags_when_no_hold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            flag = hub / "RESTORE_PAUSED"
            nested = hub / "hub-protect" / "RESTORE_PAUSED"
            nested.parent.mkdir(parents=True)
            flag.write_text("1", encoding="utf-8")
            nested.write_text("1", encoding="utf-8")
            with mock.patch.object(lh, "HOLD_PATH", hub / "OVERSEER_LAND_HOLD"), mock.patch.object(
                lh, "RESTORE_PAUSED_FLAGS", (flag, nested)
            ):
                msg = lh.clear_stale_restore_paused(force=True)
            self.assertIn("cleared", msg)
            self.assertFalse(flag.exists())
            self.assertFalse(nested.exists())

    def test_clear_expired_drops_stale_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            flag = hub / "RESTORE_PAUSED"
            flag.write_text("1", encoding="utf-8")
            with mock.patch.object(lh, "HOLD_PATH", hub / "missing-hold"), mock.patch.object(
                lh, "ROOT_HOLD", hub / "missing-root"
            ), mock.patch.object(lh, "RESTORE_PAUSED_FLAGS", (flag,)), mock.patch.object(
                lh, "unstub_restore", return_value="restore not paused"
            ):
                msg = lh.clear_expired(force=True)
            self.assertIn("RESTORE_PAUSED", msg)
            self.assertFalse(flag.exists())

    def test_fresh_hold_keeps_pause_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            hold = hub / "OVERSEER_LAND_HOLD"
            hold.write_text("hold\n", encoding="utf-8")
            flag = hub / "RESTORE_PAUSED"
            flag.write_text("1", encoding="utf-8")
            with mock.patch.object(lh, "HOLD_PATH", hold), mock.patch.object(
                lh, "RESTORE_PAUSED_FLAGS", (flag,)
            ):
                msg = lh.clear_stale_restore_paused(force=False)
            self.assertIn("kept", msg)
            self.assertTrue(flag.exists())

class MacClobberStartedTests(unittest.TestCase):
    """OVERSEER_MAC_CLOBBER_STARTED_2026_09_04 — mtime refresh cannot starve forever."""

    def test_mtime_refresh_does_not_reset_started_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            hold = hub / "OVERSEER_LAND_HOLD"
            started = hub / "OVERSEER_LAND_HOLD.started"
            hold.write_text("mac-clobber-protect 1\n", encoding="utf-8")
            # First sighting was 2000s ago — past MAC_CLOBBER_PROTECT_MAX_AGE_SEC.
            started.write_text(f"{time.time() - 2000:.6f}\n", encoding="utf-8")
            with mock.patch.object(lh, "HOLD_PATH", hold), mock.patch.object(
                lh, "ROOT_HOLD", hub / "no-root"
            ), mock.patch.object(lh, "PROTECT_STARTED_PATH", started), mock.patch.object(
                lh, "RESTORE_PAUSED_FLAGS", ()
            ):
                self.assertFalse(lh.intentional_mac_clobber_protect())
                # Fresh mtime alone must not reopen the window.
                hold.write_text(f"mac-clobber-protect {int(time.time())}\n", encoding="utf-8")
                self.assertFalse(lh.intentional_mac_clobber_protect())

    def test_clear_expired_drops_protect_started(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hub = Path(tmp)
            hold = hub / "OVERSEER_LAND_HOLD"
            started = hub / "OVERSEER_LAND_HOLD.started"
            hold.write_text("hold\n", encoding="utf-8")
            started.write_text(f"{time.time() - 120:.6f}\n", encoding="utf-8")
            import os

            past = time.time() - 120
            os.utime(hold, (past, past))
            with mock.patch.object(lh, "HOLD_PATH", hold), mock.patch.object(
                lh, "ROOT_HOLD", hub / "no-root"
            ), mock.patch.object(lh, "PROTECT_STARTED_PATH", started), mock.patch.object(
                lh, "RESTORE_PAUSED_FLAGS", ()
            ), mock.patch.object(lh, "unstub_restore", return_value="restore not paused"):
                msg = lh.clear_expired(force=True)
            self.assertIn("cleared", msg)
            self.assertFalse(hold.exists())
            self.assertFalse(started.exists())


class RestoreUnstubTests(unittest.TestCase):
    def test_restore_is_paused_detects_stub(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp) / "restore-hub-protect.sh"
            stub.write_text('#!/usr/bin/env bash\necho "restore paused by overseer land"; exit 0\n')
            self.assertTrue(lh.restore_is_paused(stub))
            real = Path(tmp) / "real.sh"
            real.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho hub-protect restored=0\n")
            self.assertFalse(lh.restore_is_paused(real))

    def test_unstub_restore_copies_real(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            restore = Path(tmp) / "restore-hub-protect.sh"
            real = Path(tmp) / "restore-hub-protect.sh.real"
            restore.write_text('#!/usr/bin/env bash\necho "restore paused by overseer land"; exit 0\n')
            real.write_text("#!/usr/bin/env bash\n# real body\nset -euo pipefail\necho ok\n")
            with mock.patch.object(lh, "RESTORE", restore), mock.patch.object(
                lh, "RESTORE_REAL", real
            ), mock.patch.object(lh, "REPO_RESTORE", Path(tmp) / "missing.sh"):
                msg = lh.unstub_restore()
            self.assertIn("unstubbed", msg)
            self.assertFalse(lh.restore_is_paused(restore))
            self.assertIn("real body", restore.read_text())

if __name__ == "__main__":
    unittest.main()
