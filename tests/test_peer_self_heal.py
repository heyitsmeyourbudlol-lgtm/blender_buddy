"""Tests for peer_self_heal bottleneck detection and mechanical heals."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_self_heal as heal  # noqa: E402


class TestPeerSelfHeal(unittest.TestCase):
    def setUp(self) -> None:
        if hasattr(heal, "clear_scan_bottlenecks_cache"):
            heal.clear_scan_bottlenecks_cache()
        heal._invalidate_probe_cache()

    def test_bootout_legacy_skips_canonical_labels(self) -> None:
        with unittest.mock.patch.object(heal.auto, "LAUNCH_AGENT_LABEL", "com.togi.automation-peer-loop"):
            with unittest.mock.patch.object(heal, "_improve_label", return_value="com.togi.automation-improve-loop"):
                with unittest.mock.patch.object(
                    heal,
                    "_live_canonical_labels",
                    return_value={"com.togi.automation-peer-loop", "com.togi.automation-improve-loop"},
                ):
                    with unittest.mock.patch.object(heal.subprocess, "run") as run:
                        run.return_value = unittest.mock.Mock(returncode=0)
                        result = heal._bootout_legacy_peer_labels()
        booted = [c.args[0][2].split("/")[-1] for c in run.call_args_list]
        self.assertNotIn("com.togi.automation-peer-loop", booted)
        self.assertNotIn("com.togi.automation-improve-loop", booted)
        self.assertIn("com.togi.automation-hub-peer-loop", booted)
        self.assertIn("com.togi.automation-hub-improve-loop", booted)
        self.assertIn("legacy bootout", result)

    def test_bootout_legacy_stops_old_namespace_only(self) -> None:
        with unittest.mock.patch.object(heal.auto, "LAUNCH_AGENT_LABEL", "com.togi.automation-hub-peer-loop"):
            with unittest.mock.patch.object(
                heal, "_improve_label", return_value="com.togi.automation-hub-improve-loop"
            ):
                with unittest.mock.patch.object(
                    heal,
                    "_live_canonical_labels",
                    return_value={
                        "com.togi.automation-hub-peer-loop",
                        "com.togi.automation-hub-improve-loop",
                    },
                ):
                    with unittest.mock.patch.object(heal.subprocess, "run") as run:
                        run.return_value = unittest.mock.Mock(returncode=0)
                        result = heal._bootout_legacy_peer_labels()
        self.assertEqual(run.call_count, 2)
        booted = [c.args[0][2].split("/")[-1] for c in run.call_args_list]
        self.assertIn("com.togi.automation-peer-loop", booted)
        self.assertIn("com.togi.automation-improve-loop", booted)
        self.assertIn("legacy bootout", result)

    def test_bootout_legacy_protects_disk_canonical_when_memory_stale(self) -> None:
        """Stale hub-oversight process must not bootout live automation-peer."""
        with unittest.mock.patch.object(heal.auto, "LAUNCH_AGENT_LABEL", "com.togi.automation-hub-peer-loop"):
            with unittest.mock.patch.object(
                heal, "_improve_label", return_value="com.togi.automation-hub-improve-loop"
            ):
                with unittest.mock.patch.object(
                    heal,
                    "_live_canonical_labels",
                    return_value={"com.togi.automation-peer-loop", "com.togi.automation-improve-loop"},
                ):
                    with unittest.mock.patch.object(heal.subprocess, "run") as run:
                        run.return_value = unittest.mock.Mock(returncode=0)
                        heal._bootout_legacy_peer_labels()
        booted = [c.args[0][2].split("/")[-1] for c in run.call_args_list]
        self.assertNotIn("com.togi.automation-peer-loop", booted)
        self.assertNotIn("com.togi.automation-improve-loop", booted)
        self.assertIn("com.togi.automation-hub-peer-loop", booted)

    def test_scan_detects_dual_brain(self) -> None:
        with unittest.mock.patch.object(heal, "_launchctl_running", side_effect=lambda label: label == heal.RAM_PEER_LABEL):
            found = heal.scan_bottlenecks()
        ids = {b.id for b in found}
        self.assertIn("dual_brain_ram_peer", ids)

    def test_apply_heals_stops_ram_peer(self) -> None:
        bn = heal.Bottleneck(
            id="dual_brain_ram_peer",
            category="daemon",
            severity="high",
            title="dual brain",
            evidence="test",
            heal_action="stop",
        )
        registry: dict = {"last_heal": {}}
        with unittest.mock.patch.object(heal, "_bootout", return_value="stopped") as boot:
            actions = heal.apply_heals([bn], registry=registry)
        boot.assert_called_once_with(heal.RAM_PEER_LABEL)
        self.assertTrue(any("stopped" in a for a in actions))

    def test_stale_lock_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "verify.lock"
            lock.write_text("1\n")
            old = heal.VERIFY_LOCK
            heal.VERIFY_LOCK = lock
            try:
                with unittest.mock.patch.object(heal, "_file_age_sec", return_value=999.0):
                    with unittest.mock.patch.object(heal, "_launchctl_running", return_value=True):
                        with unittest.mock.patch.object(heal, "_tail_log", return_value=[]):
                            with unittest.mock.patch.object(heal, "_read_state", return_value={}):
                                with unittest.mock.patch.object(heal, "_read_status", return_value={}):
                                    found = heal.scan_bottlenecks()
                ids = {b.id for b in found}
                self.assertIn("stale_verify_lock", ids)
            finally:
                heal.VERIFY_LOCK = old

    def test_registry_persists_hit_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reg_path = Path(tmp) / "registry.json"
            heal.REGISTRY_PATH = reg_path
            bn = heal.Bottleneck(
                id="unittest_storm",
                category="tests",
                severity="high",
                title="storm",
                evidence="x",
            )
            registry = heal._load_registry()
            merged = heal._merge_history([bn], registry)
            self.assertEqual(merged[0].hit_count, 1)
            heal._save_registry(registry)
            registry2 = heal._load_registry()
            merged2 = heal._merge_history([bn], registry2)
            self.assertEqual(merged2[0].hit_count, 2)

    def test_extend_test_cache_ttl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            heal.CONFIG_DIR = Path(tmp)
            result = heal._extend_test_cache_ttl(min_ttl=600)
            self.assertIn("bumped", result)
            cache = json.loads((Path(tmp) / "automation_cache.json").read_text())
            self.assertEqual(cache.get("self_heal_test_ttl_bump"), 600)

    def test_count_unittest_timeouts_ignores_daemon_heal(self) -> None:
        lines = [
            "self-heal: daemon_improve_stopped failed (Command '['launchctl', 'kickstart' timed out after 15.0 seconds)",
            "FAILED (errors=1) tests.test_foo.TestBar.test_baz — timed out after 30s",
        ]
        self.assertEqual(heal._count_unittest_timeouts(lines), 1)

    def test_count_unittest_timeouts_ignores_wake_reason(self) -> None:
        lines = [
            "2026-09-02 15:35:20  wake reason=timeout (continuous, next≤5s)",
            "wake reason=timeout unittest poll",
            "FAILED tests.test_x — timed out after 30s",
        ]
        self.assertEqual(heal._count_unittest_timeouts(lines), 1)

    def test_daemon_heal_flock_creates_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_lock = heal.DAEMON_HEAL_LOCK
            old_cfg = heal.CONFIG_DIR
            heal.DAEMON_HEAL_LOCK = Path(tmp) / "daemon-heal.lock"
            heal.CONFIG_DIR = Path(tmp)
            try:
                with heal._daemon_heal_flock(timeout_sec=2.0):
                    self.assertTrue(heal.DAEMON_HEAL_LOCK.is_file())
            finally:
                heal.DAEMON_HEAL_LOCK = old_lock
                heal.CONFIG_DIR = old_cfg

    def test_daemon_heal_flock_nested_reentrant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_lock = heal.DAEMON_HEAL_LOCK
            old_cfg = heal.CONFIG_DIR
            heal.DAEMON_HEAL_LOCK = Path(tmp) / "daemon-heal.lock"
            heal.CONFIG_DIR = Path(tmp)
            try:
                with heal._daemon_heal_flock(timeout_sec=2.0):
                    with heal._daemon_heal_flock(timeout_sec=2.0):
                        self.assertTrue(heal.DAEMON_HEAL_LOCK.is_file())
            finally:
                heal.DAEMON_HEAL_LOCK = old_lock
                heal.CONFIG_DIR = old_cfg

    def test_kickstart_or_install_reports_running_after_bootstrap(self) -> None:
        label = "com.togi.automation-hub-improve-loop"
        with unittest.mock.patch.object(heal, "_kickstart", return_value="kickstart failed: Could not find service"):
            with unittest.mock.patch.object(heal, "autonomous_execution_enabled", return_value=True):
                with unittest.mock.patch.object(heal, "_launchctl_running", return_value=True):
                    with unittest.mock.patch("time.sleep"):
                        result = heal._kickstart_or_install(label, install_fn=lambda: 0)
        self.assertIn("running after bootstrap", result)

    def test_kickstart_or_install_accepts_bootstrap_race_when_running(self) -> None:
        label = "com.togi.automation-hub-improve-loop"
        with unittest.mock.patch.object(heal, "_kickstart", return_value="kickstart failed: Could not find service"):
            with unittest.mock.patch.object(heal, "autonomous_execution_enabled", return_value=True):
                with unittest.mock.patch.object(heal, "_launchctl_running", side_effect=[False, True]):
                    with unittest.mock.patch("time.sleep"):
                        result = heal._kickstart_or_install(label, install_fn=lambda: 1)
        self.assertIn("bootstrap race", result)

    def test_launchctl_running_true_when_print_state_running(self) -> None:
        label = "com.togi.automation-hub-improve-loop"
        print_out = "gui/501/com.togi.automation-hub-improve-loop = {\n\tstate = running\n}\n"
        heal._probe_cache.clear()

        def fake_run(cmd, **kwargs):
            class P:
                returncode = 1
                stdout = ""
                stderr = ""

            if cmd[:2] == ["launchctl", "list"] and len(cmd) > 2:
                return P()
            if cmd[:2] == ["launchctl", "list"]:
                p = P()
                p.returncode = 0
                p.stdout = "-	0	other.label\n"
                return p
            if cmd[:2] == ["launchctl", "print"]:
                p = P()
                p.returncode = 0
                p.stdout = print_out
                return p
            return P()

        # LAUNCHCTL_DARWIN_ONLY — Linux short-circuits False; exercise mac path.
        with unittest.mock.patch.object(heal.sys, "platform", "darwin"):
            with unittest.mock.patch.object(heal.subprocess, "run", side_effect=fake_run):
                self.assertTrue(heal._launchctl_running(label))

    def test_kickstart_defaults_without_kill_flag(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))

            class P:
                returncode = 0
                stdout = ""
                stderr = ""

            return P()

        with unittest.mock.patch.object(heal.subprocess, "run", side_effect=fake_run):
            heal._kickstart("com.togi.automation-hub-peer-loop")
        self.assertTrue(calls)
        self.assertNotIn("-k", calls[0])

        bn = heal.Bottleneck(
            id="daemon_improve_stopped",
            category="daemon",
            severity="critical",
            title="Improve forever daemon not running",
            evidence="no PID",
            heal_action="kickstart improve loop",
        )
        registry = {"last_heal": {f"heal:{bn.id}": time.time()}}
        with unittest.mock.patch.object(heal, "_improve_daemon_running", return_value=False):
            with unittest.mock.patch.object(
                heal, "_heal_improve_daemon", return_value="kickstarted improve"
            ) as healer:
                actions = heal.apply_heals([bn], registry=registry)
        healer.assert_called_once()
        self.assertTrue(any("kickstarted improve" in a for a in actions))
        self.assertEqual(bn.status, "healed")

    def test_apply_heals_keeps_cooldown_when_daemon_already_up(self) -> None:
        bn = heal.Bottleneck(
            id="daemon_peer_stopped",
            category="daemon",
            severity="critical",
            title="Peer loop daemon not running",
            evidence="inactive",
            heal_action="kickstart peer loop",
        )
        registry = {"last_heal": {f"heal:{bn.id}": time.time()}}
        with unittest.mock.patch.object(heal, "_peer_daemon_running", return_value=True):
            with unittest.mock.patch.object(heal, "_heal_peer_daemon") as healer:
                actions = heal.apply_heals([bn], registry=registry)
        healer.assert_not_called()
        self.assertEqual(actions, [])
        self.assertEqual(bn.status, "deferred")
        self.assertEqual(bn.heal_result, "cooldown")

    def test_merge_history_marks_absent_ids_healed(self) -> None:
        registry = {
            "history": {
                "unittest_storm": {
                    "first_seen": "2026-09-01",
                    "last_seen": "2026-09-01",
                    "hit_count": 3,
                    "title": "storm",
                    "category": "tests",
                    "severity": "high",
                    "status": "open",
                    "last_evidence": "timeout",
                }
            }
        }
        bn = heal.Bottleneck(
            id="queue_drift",
            category="queue",
            severity="medium",
            title="drift",
            evidence="x",
        )
        merged = heal._merge_history([bn], registry)
        self.assertEqual(len(merged), 1)
        self.assertEqual(registry["history"]["unittest_storm"]["status"], "healed")
        self.assertEqual(registry["history"]["unittest_storm"]["healed_reason"], "absent_from_scan")
        self.assertEqual(registry["history"]["queue_drift"]["status"], "open")

    def test_ensure_canonical_module_aliases_both_names(self) -> None:
        heal.ensure_canonical_module()
        self.assertIs(sys.modules.get("peer_self_heal"), sys.modules.get("scripts.peer_self_heal") or sys.modules["peer_self_heal"])
        # Simulate dual load then unify to the first-loaded object.
        class _Dup:
            pass

        dup = _Dup()
        primary = sys.modules["peer_self_heal"]
        sys.modules["scripts.peer_self_heal"] = dup  # type: ignore[assignment]
        heal.ensure_canonical_module()
        self.assertIs(sys.modules["peer_self_heal"], primary)
        self.assertIs(sys.modules["scripts.peer_self_heal"], primary)

    def test_heal_peer_daemon_uses_systemd_off_darwin(self) -> None:
        from contextlib import contextmanager

        @contextmanager
        def _ok_flock():
            yield

        with unittest.mock.patch.object(heal.sys, "platform", "linux"):
            with unittest.mock.patch.object(heal, "_daemon_heal_flock", _ok_flock):
                with unittest.mock.patch.object(
                    heal, "_peer_daemon_running", return_value=False
                ):
                    with unittest.mock.patch.object(
                        heal,
                        "_ensure_systemd_peer_unit",
                        return_value="restarted peer-loop.service",
                    ) as ensure:
                        result = heal._heal_peer_daemon({})
        ensure.assert_called_once()
        self.assertIn("restarted peer-loop.service", result)

    def test_peer_daemon_running_requires_canonical_label(self) -> None:
        with unittest.mock.patch.object(heal.sys, "platform", "darwin"):
            with unittest.mock.patch.object(
                heal, "_live_peer_label", return_value="com.togi.automation-peer-loop"
            ):
                with unittest.mock.patch.object(
                    heal,
                    "_launchctl_running",
                    side_effect=lambda lbl: lbl == "com.togi.automation-peer-loop",
                ):
                    self.assertTrue(heal._peer_daemon_running())

    def test_peer_daemon_running_false_when_only_hub_label(self) -> None:
        with unittest.mock.patch.object(heal.sys, "platform", "darwin"):
            with unittest.mock.patch.object(
                heal, "_live_peer_label", return_value="com.togi.automation-peer-loop"
            ):
                with unittest.mock.patch.object(
                    heal, "_launchctl_running", side_effect=lambda lbl: lbl == heal.HUB_PEER_LABEL
                ):
                    with unittest.mock.patch.object(
                        heal, "_peer_loop_process_pid", return_value=None
                    ):
                        self.assertFalse(heal._peer_daemon_running())

    def test_peer_daemon_running_true_via_forever_process(self) -> None:
        """Launchctl down but peer_loop --forever live → still running."""
        with unittest.mock.patch.object(heal.sys, "platform", "darwin"):
            with unittest.mock.patch.object(
                heal, "_live_peer_label", return_value="com.togi.automation-hub-peer-loop"
            ):
                with unittest.mock.patch.object(heal, "_launchctl_running", return_value=False):
                    with unittest.mock.patch.object(
                        heal, "_peer_loop_process_pid", return_value=4242
                    ):
                        self.assertTrue(heal._peer_daemon_running())

    def test_dual_namespace_collision_detects_rogue_hub(self) -> None:
        with unittest.mock.patch.object(heal.sys, "platform", "darwin"):
            with unittest.mock.patch.object(
                heal, "_live_peer_label", return_value="com.togi.automation-peer-loop"
            ):
                with unittest.mock.patch.object(
                    heal, "_live_improve_label", return_value="com.togi.automation-improve-loop"
                ):
                    with unittest.mock.patch.object(
                        heal,
                        "_launchctl_running",
                        side_effect=lambda lbl: lbl
                        in ("com.togi.automation-peer-loop", heal.HUB_PEER_LABEL),
                    ):
                        collision = heal.dual_namespace_collision()
        self.assertIn(heal.HUB_PEER_LABEL, collision["peer"])

    def test_dual_namespace_collision_ttl_hit(self) -> None:
        """DUAL_NAMESPACE_COLLISION_TTL — same config mtimes skip _live_cfg remiss."""
        heal.clear_dual_namespace_collision_cache()
        calls = {"n": 0}
        orig = heal._live_cfg

        def _wrap() -> dict:
            calls["n"] += 1
            return orig()

        with unittest.mock.patch.object(heal, "_live_cfg", side_effect=_wrap):
            a = heal.dual_namespace_collision()
            first = calls["n"]
            self.assertGreater(first, 0)
            b = heal.dual_namespace_collision()
            self.assertEqual(a, b)
            self.assertEqual(calls["n"], first)
            heal.clear_dual_namespace_collision_cache()
            heal.dual_namespace_collision()
            self.assertGreater(calls["n"], first)
        self.assertIn(
            "DUAL_NAMESPACE_COLLISION_TTL_2026_09_08",
            (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8"),
        )

    def test_improve_label_no_import_automation_improve(self) -> None:
        """IMPROVE_LABEL_NO_IMPORT — dual_ns/scan must not cold-import improve."""
        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        self.assertIn("IMPROVE_LABEL_NO_IMPORT_2026_09_08", src)
        # Formula body must not import (heal paths may still import elsewhere).
        start = src.index("def _improve_label()")
        end = src.index("\ndef ", start + 1)
        body = src[start:end]
        self.assertNotIn("import automation_improve", body)
        ns = str(heal.cfg_mod.CFG.get("config_namespace") or "automation-hub")
        self.assertEqual(heal._improve_label(), f"com.togi.{ns}-improve-loop")
        # Fresh dual-ns miss must not pull automation_improve into sys.modules.
        heal.clear_dual_namespace_collision_cache()
        sys.modules.pop("automation_improve", None)
        sys.modules.pop("scripts.automation_improve", None)
        with unittest.mock.patch.object(heal, "_running_launchctl_labels", return_value=[]):
            heal.dual_namespace_collision()
        self.assertNotIn("automation_improve", sys.modules)

    def test_rogue_oversight_detects_hub_twin(self) -> None:
        with unittest.mock.patch.object(heal.sys, "platform", "darwin"):
            with unittest.mock.patch.object(
                heal, "_live_oversight_label", return_value="com.togi.automation-oversight-loop"
            ):
                with unittest.mock.patch.object(
                    heal,
                    "_launchctl_running",
                    side_effect=lambda lbl: lbl
                    in (
                        "com.togi.automation-oversight-loop",
                        heal.HUB_OVERSIGHT_LABEL,
                    ),
                ):
                    rogue = heal.rogue_oversight_labels()
        self.assertEqual(rogue, [heal.HUB_OVERSIGHT_LABEL])

    def test_live_canonical_labels_read_disk_not_memory(self) -> None:
        with unittest.mock.patch.object(
            heal.cfg_mod,
            "load_config",
            return_value={
                "config_namespace": "automation",
                "launch_agent_label": "com.togi.automation-peer-loop",
            },
        ):
            labels = heal._live_canonical_labels()
        self.assertEqual(
            labels,
            {"com.togi.automation-peer-loop", "com.togi.automation-improve-loop"},
        )

    def test_heal_rogue_oversight_unlinks_plist_skips_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            plist = home / "Library" / "LaunchAgents" / f"{heal.HUB_OVERSIGHT_LABEL}.plist"
            plist.parent.mkdir(parents=True)
            plist.write_text("stub", encoding="utf-8")
            with unittest.mock.patch.object(
                heal, "rogue_oversight_labels", return_value=[heal.HUB_OVERSIGHT_LABEL]
            ):
                with unittest.mock.patch.object(
                    heal, "_bootout", return_value=f"stopped {heal.HUB_OVERSIGHT_LABEL}"
                ) as boot:
                    with unittest.mock.patch.object(heal.Path, "home", return_value=home):
                        result = heal._heal_rogue_oversight()
            boot.assert_called_once_with(heal.HUB_OVERSIGHT_LABEL)
            self.assertFalse(plist.is_file())
            self.assertIn("removed", result)

    def test_apply_heals_dual_brain_oversight_does_not_reinstall(self) -> None:
        bn = heal.Bottleneck(
            id="dual_brain_hub_oversight",
            category="daemon",
            severity="critical",
            title="rogue oversight",
            evidence="test",
            heal_action="bootout rogue oversight LaunchAgent",
        )
        registry: dict = {"last_heal": {}}
        with unittest.mock.patch.object(
            heal, "_heal_rogue_oversight", return_value="stopped hub-oversight"
        ) as rogue:
            actions = heal.apply_heals([bn], registry=registry)
        rogue.assert_called_once()
        self.assertTrue(any("stopped hub-oversight" in a for a in actions))
        self.assertEqual(heal._HEALERS["dual_brain_hub_oversight"], heal._heal_rogue_oversight)


    def test_hub_protect_units_present_when_masked_with_backup(self) -> None:
        """Masked → /dev/null must still be healable via .overseer-masked backup."""
        with tempfile.TemporaryDirectory() as tmp:
            user = Path(tmp)
            timer = user / "hub-protect-restore.timer"
            bak = user / "hub-protect-restore.timer.overseer-masked"
            timer.symlink_to("/dev/null")
            bak.write_text("[Unit]\nDescription=test\n", encoding="utf-8")
            with unittest.mock.patch.object(
                heal, "_systemd_unit_path", side_effect=lambda u: user / u
            ):
                self.assertTrue(heal._hub_protect_unit_masked("hub-protect-restore.timer"))
                self.assertTrue(heal._hub_protect_units_present())

    def test_unmask_hub_protect_units_restores_from_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cfg = home / ".config" / "systemd" / "user"
            cfg.mkdir(parents=True)
            timer = cfg / "hub-protect-restore.timer"
            bak = cfg / "hub-protect-restore.timer.overseer-masked"
            timer.symlink_to("/dev/null")
            bak.write_text("[Unit]\nDescription=restored\n", encoding="utf-8")
            with (
                unittest.mock.patch.object(heal, "_systemd_daemon_reload") as reload,
                unittest.mock.patch.object(
                    heal.subprocess,
                    "run",
                    return_value=unittest.mock.Mock(returncode=0),
                ),
                unittest.mock.patch("peer_self_heal.Path.home", return_value=home),
            ):
                parts = heal._unmask_hub_protect_units()
            self.assertTrue(any("unmasked" in p for p in parts))
            self.assertTrue(timer.is_file() and not timer.is_symlink())
            self.assertIn("restored", timer.read_text(encoding="utf-8"))
            reload.assert_called()



    def test_invalidate_probe_cache_clears_hub_protect_prefix(self) -> None:
        """OVERSEER_PROBE_CACHE_INVALIDATE_TEST_2026_09_04 — heal must drop stale inactive."""
        heal._probe_cache.clear()
        heal._probe_cache["systemd:hub-protect-restore.timer"] = (time.time(), False)
        heal._probe_cache["systemd:peer-loop.service"] = (time.time(), True)
        heal._invalidate_probe_cache("systemd:hub-protect")
        self.assertNotIn("systemd:hub-protect-restore.timer", heal._probe_cache)
        self.assertIn("systemd:peer-loop.service", heal._probe_cache)



    def test_verify_storm_ignores_aged_fail_lines(self) -> None:
        """OVERSEER_VERIFY_STORM_MAX_AGE_2026_09_04 — stale FAIL pair must not pin storm."""
        now = time.time()
        old = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 900))
        fresh = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 30))
        aged = [
            f"{old}  verify FAIL (1): FAILED (failures=3)",
            f"{old}  verify FAIL (1): FAILED (failures=3)",
        ]
        recent = [
            f"{fresh}  verify FAIL (1): FAILED (failures=1)",
            f"{fresh}  verify FAIL (1): FAILED (failures=1)",
        ]
        self.assertEqual(
            heal._count_recent_patterns(
                aged, ("verify TIMEOUT", "verify FAIL"), now=now
            ),
            0,
        )
        self.assertEqual(
            heal._count_recent_patterns(
                recent, ("verify TIMEOUT", "verify FAIL"), now=now
            ),
            2,
        )
        self.assertIn(
            "OVERSEER_VERIFY_STORM_MAX_AGE_2026_09_04",
            Path(heal.__file__).read_text(encoding="utf-8"),
        )

    def test_poison_heal_uses_fallback_module(self) -> None:
        """OVERSEER_POISON_HEAL_FALLBACK_TEST_2026_09_04 — no AttributeError on stripped scrub.

        OVERSEER_POISON_HEAL_SANITIZE_KEEP_FT_2026_09_04 — keep failure_type=deferred;
        set verify_ok=False (never pop-ft under green — greases delivery meters).
        """
        src = Path(heal.__file__).read_text(encoding="utf-8")
        self.assertIn("OVERSEER_POISON_HEAL_FALLBACK_2026_09_04", src)
        self.assertIn("OVERSEER_POISON_HEAL_SANITIZE_KEEP_FT_2026_09_04", src)
        self.assertEqual(src.count("def _heal_last_cycle_deferred_poison"), 1)
        self.assertIn("peer_last_cycle_poison", src)
        # Detect poison without transcript.scrub_*
        self.assertTrue(
            heal._is_last_cycle_deferred_poison(
                {"verify_ok": True, "failure_type": "deferred", "ts": 99.0}
            )
        )
        state = {
            "last_cycle": {
                "verify_ok": True,
                "failure_type": "deferred",
                "ts": 99.0,
                "note": "x",
                "queue_fp": "q",
            }
        }
        with (
            unittest.mock.patch("peer_transcript.load_state", return_value=state),
            unittest.mock.patch("peer_transcript.save_state") as save,
            unittest.mock.patch(
                "peer_transcript.scrub_last_cycle_poison",
                side_effect=AttributeError("module peer_transcript has no attribute scrub"),
                create=True,
            ),
        ):
            result = heal._heal_last_cycle_deferred_poison({})
        self.assertIn("scrubbed", result)
        # Fail-closed: deferred kept; verify_ok forced False (never pop-ft under green).
        self.assertEqual(state["last_cycle"].get("failure_type"), "deferred")
        self.assertIs(state["last_cycle"].get("verify_ok"), False)
        save.assert_called()



    def test_heal_seed_gates_on_ready_false(self) -> None:
        """OVERSEER_SEED_GATE_READY_2026_09_04 — deferred/idle (0, False) must not stamp green."""
        import peer_transcript as pt
        src = Path(heal.__file__).read_text(encoding="utf-8")
        self.assertIn("OVERSEER_SEED_GATE_READY_2026_09_04", src)
        self.assertIn("verify_ok = rc == 0 and bool(ready)", src)
        state = {
            "cycle_history": [
                {
                    "ts": time.time() - 5,
                    "verify_ok": True,
                    "noop": False,
                    "queue_fp": "prior-fp",
                    "rc": 0,
                    "git_head": "abc",
                    "note": "prior",
                }
            ]
        }
        with (
            unittest.mock.patch.object(pt, "load_state", return_value=state),
            unittest.mock.patch.object(pt, "save_state") as save,
            unittest.mock.patch.object(pt, "current_queue_fingerprint", return_value=("fp", [])),
            unittest.mock.patch("run_peer_tasks.run_local_cycle", return_value=(0, False)),
            unittest.mock.patch("peer_last_cycle_poison.safe_scrub", return_value=None),
        ):
            msg = heal._heal_seed_last_cycle({})
        self.assertIn("rehydrat", msg.lower())
        save.assert_called()
        saved = save.call_args[0][0]
        lc = saved.get("last_cycle") or {}
        self.assertTrue(lc.get("verify_ok"))
        self.assertIn("rehydrat", str(lc.get("note") or "").lower())
        self.assertNotIn("self-heal seeded last_cycle", str(lc.get("note") or ""))



    def test_ensure_systemd_improve_skips_restart_when_active(self) -> None:
        """OVERSEER_IMPROVE_SKIP_RESTART_IF_ACTIVE_2026_09_04"""
        with (
            unittest.mock.patch.object(heal, "_systemd_unit_usable", return_value=True),
            unittest.mock.patch.object(heal, "_systemd_unit_worktree_poisoned", return_value=False),
            unittest.mock.patch.object(heal, "_systemd_user_active", return_value=True),
            unittest.mock.patch.object(heal, "_systemd_restart") as restart,
        ):
            msg = heal._ensure_systemd_improve_unit()
        self.assertIn("skip restart", msg)
        restart.assert_not_called()

    def test_ensure_systemd_peer_skips_restart_when_active(self) -> None:
        """OVERSEER_PEER_SKIP_RESTART_IF_ACTIVE_2026_09_04"""
        with (
            unittest.mock.patch.object(heal, "_systemd_unit_usable", return_value=True),
            unittest.mock.patch.object(heal, "_systemd_unit_worktree_poisoned", return_value=False),
            unittest.mock.patch.object(heal, "_systemd_user_active", return_value=True),
            unittest.mock.patch.object(heal, "_systemd_restart") as restart,
        ):
            msg = heal._ensure_systemd_peer_unit()
        self.assertIn("skip restart", msg)
        restart.assert_not_called()

    def test_heal_improve_flock_busy_skips_restart_when_active(self) -> None:
        """OVERSEER_IMPROVE_SKIP_RESTART_IF_ACTIVE flock-busy path"""
        from contextlib import contextmanager

        @contextmanager
        def _busy():
            raise TimeoutError("flock busy")
            yield  # pragma: no cover

        with (
            unittest.mock.patch.object(heal.sys, "platform", "linux"),
            unittest.mock.patch.object(heal, "_daemon_heal_flock", _busy),
            unittest.mock.patch.object(heal, "_improve_daemon_running", return_value=True),
            unittest.mock.patch.object(heal, "_systemd_restart") as restart,
        ):
            msg = heal._heal_improve_daemon({})
        self.assertIn("skip restart", msg)
        restart.assert_not_called()

    def test_heal_horizon_stale_skips_restart_when_improve_up(self) -> None:
        """OVERSEER_HORIZON_SKIP_RESTART_2026_09_04"""
        with (
            unittest.mock.patch.object(heal, "_improve_daemon_running", return_value=True),
            unittest.mock.patch.object(
                heal, "_soft_refresh_horizon", return_value="horizon soft-refresh → x"
            ),
            unittest.mock.patch.object(heal, "_touch_signal", return_value="touched"),
            unittest.mock.patch.object(heal, "_append_improve_wake") as wake,
            unittest.mock.patch.object(heal, "_ensure_systemd_improve_unit") as ensure,
            unittest.mock.patch.object(heal, "_kickstart") as kick,
        ):
            msg = heal._heal_horizon_stale({})
        self.assertIn("skip_restart", msg)
        wake.assert_called_once()
        ensure.assert_not_called()
        kick.assert_not_called()

    def test_soft_refresh_no_cold_improve_import(self) -> None:
        """SOFT_REFRESH_NO_COLD_IMPROVE_IMPORT — unloaded path skips compile."""
        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        self.assertIn("SOFT_REFRESH_NO_COLD_IMPROVE_IMPORT_2026_09_08", src)
        self.assertIn('sys.modules.get("automation_improve")', src)
        # Cold path: improve not loaded → deferred, no import.
        sys.modules.pop("automation_improve", None)
        sys.modules.pop("scripts.automation_improve", None)
        msg = heal._soft_refresh_horizon()
        self.assertIn("deferred", msg)
        self.assertNotIn("automation_improve", sys.modules)
        # Warm path (daemon down + board stale): gather + write.
        fake = unittest.mock.MagicMock()
        fake.gather_signals.return_value = object()
        fake.write_horizon.return_value = ["/tmp/horizon-test.md"]
        with (
            unittest.mock.patch.dict(sys.modules, {"automation_improve": fake}),
            unittest.mock.patch.object(heal, "_improve_daemon_running", return_value=False),
            unittest.mock.patch.object(
                heal, "_file_age_sec", return_value=heal.HORIZON_STALE_SEC + 1.0
            ),
        ):
            warm = heal._soft_refresh_horizon()
        self.assertIn("horizon soft-refresh →", warm)
        fake.gather_signals.assert_called_once()
        fake.write_horizon.assert_called_once()

    def test_soft_refresh_defer_warm_gather_when_daemon_up(self) -> None:
        """SOFT_REFRESH_DEFER_WARM_GATHER_DAEMON_UP — skip gather+write when up."""
        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        self.assertIn("SOFT_REFRESH_DEFER_WARM_GATHER_DAEMON_UP_2026_09_08", src)
        fake = unittest.mock.MagicMock()
        with (
            unittest.mock.patch.dict(sys.modules, {"automation_improve": fake}),
            unittest.mock.patch.object(heal, "_improve_daemon_running", return_value=True),
        ):
            msg = heal._soft_refresh_horizon()
        self.assertIn("deferred", msg)
        self.assertIn("improve up", msg)
        fake.gather_signals.assert_not_called()
        fake.write_horizon.assert_not_called()

    def test_soft_refresh_skip_when_horizon_fresh(self) -> None:
        """SOFT_REFRESH_SKIP_WHEN_HORIZON_FRESH — no gather when board age ≤ stale."""
        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        self.assertIn("SOFT_REFRESH_SKIP_WHEN_HORIZON_FRESH_2026_09_08", src)
        self.assertIn("HORIZON_STALE_SEC", src)
        fake = unittest.mock.MagicMock()
        with (
            unittest.mock.patch.dict(sys.modules, {"automation_improve": fake}),
            unittest.mock.patch.object(heal, "_improve_daemon_running", return_value=False),
            unittest.mock.patch.object(heal, "_file_age_sec", return_value=15.0),
            unittest.mock.patch.object(
                heal, "_horizon_board_path", return_value=heal.HORIZON_PATH
            ),
        ):
            msg = heal._soft_refresh_horizon()
        self.assertIn("skipped", msg)
        self.assertIn("fresh", msg)
        fake.gather_signals.assert_not_called()
        fake.write_horizon.assert_not_called()

    def test_heal_improve_darwin_no_cold_improve_import(self) -> None:
        """HEAL_IMPROVE_DARWIN_NO_COLD_IMPROVE_IMPORT — kickstart-ok skips compile."""
        from contextlib import nullcontext

        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        self.assertIn("HEAL_IMPROVE_DARWIN_NO_COLD_IMPROVE_IMPORT_2026_09_08", src)
        self.assertIn("_lazy_improve_install", src)
        sys.modules.pop("automation_improve", None)
        sys.modules.pop("scripts.automation_improve", None)
        # Already-active: no import.
        with (
            unittest.mock.patch.object(heal.sys, "platform", "darwin"),
            unittest.mock.patch.object(heal, "_improve_daemon_running", return_value=True),
            unittest.mock.patch.object(heal, "ensure_canonical_module"),
            unittest.mock.patch.object(heal, "_live_improve_label", return_value="com.togi.test-improve"),
            unittest.mock.patch.object(heal, "_kickstart_or_install") as kick_or,
        ):
            msg = heal._heal_improve_daemon({})
        self.assertIn("skip restart", msg)
        kick_or.assert_not_called()
        self.assertNotIn("automation_improve", sys.modules)
        # Kickstart succeeds without install_fn → still no import.
        with (
            unittest.mock.patch.object(heal.sys, "platform", "darwin"),
            unittest.mock.patch.object(heal, "_improve_daemon_running", return_value=False),
            unittest.mock.patch.object(heal, "_improve_process_pid", return_value=None),
            unittest.mock.patch.object(heal, "ensure_canonical_module"),
            unittest.mock.patch.object(heal, "_live_improve_label", return_value="com.togi.test-improve"),
            unittest.mock.patch.object(heal, "_daemon_heal_flock", return_value=nullcontext()),
            unittest.mock.patch.object(
                heal, "_kickstart_or_install", return_value="kickstarted com.togi.test-improve"
            ) as kick_or,
            unittest.mock.patch.object(heal, "_bootout_legacy_peer_labels", return_value=""),
            unittest.mock.patch.object(heal, "_heal_rogue_oversight", return_value=""),
            unittest.mock.patch.object(heal, "_wait_launchctl_running", return_value=True),
        ):
            msg = heal._heal_improve_daemon({})
        self.assertIn("kickstarted", msg)
        kick_or.assert_called_once()
        self.assertNotIn("automation_improve", sys.modules)
        # install_fn only imports when invoked (missing LaunchAgent path).
        install_fn = kick_or.call_args.kwargs["install_fn"]
        fake = unittest.mock.MagicMock()
        fake._cmd_install_body.return_value = 0
        with unittest.mock.patch.dict(sys.modules, {"automation_improve": fake}):
            self.assertEqual(install_fn(), 0)
        fake._cmd_install_body.assert_called_once()

    def test_linux_install_daemon_covers_research_oversight(self) -> None:
        """OVERSEER_LINUX_INSTALL_RESEARCH_OVERSIGHT_2026_09_04"""
        self.assertTrue(callable(heal.linux_uninstall_daemon))
        with unittest.mock.patch.object(
            heal, "_ensure_systemd_repo_research_unit", return_value="ok-research"
        ) as ens:
            self.assertEqual(heal.linux_install_daemon("research"), "ok-research")
            ens.assert_called_once()
        with unittest.mock.patch.object(
            heal, "_ensure_systemd_oversight_unit", return_value="ok-oversight"
        ) as ens:
            self.assertEqual(heal.linux_install_daemon("oversight"), "ok-oversight")
            ens.assert_called_once()
        with unittest.mock.patch.object(heal.subprocess, "run") as run:
            run.return_value = unittest.mock.Mock(returncode=0, stdout="", stderr="removed")
            msg = heal.linux_uninstall_daemon("research")
        self.assertIn("repo-research-loop.service", msg)
        self.assertIn("unknown", heal.linux_install_daemon("not-a-daemon"))

    def test_scan_heals_stopped_research_daemon(self) -> None:
        """OVERSEER_HEAL_RESEARCH_DAEMON_2026_09_04 — STOPPED research is a heal target."""
        from contextlib import nullcontext

        src = Path(heal.__file__).read_text(encoding="utf-8")
        self.assertIn("OVERSEER_HEAL_RESEARCH_DAEMON_2026_09_04", src)
        self.assertIn("daemon_research_stopped", src)
        self.assertIn("def _repo_research_daemon_running", src)
        self.assertIn("def _heal_research_daemon", src)
        with unittest.mock.patch.object(heal, "_repo_research_daemon_running", return_value=False):
            found = heal.scan_bottlenecks()
        ids = {b.id for b in found}
        self.assertIn("daemon_research_stopped", ids)
        with (
            unittest.mock.patch.object(
                heal,
                "_ensure_systemd_repo_research_unit",
                return_value="enable --now repo-research-loop.service",
            ) as ens,
            unittest.mock.patch.object(heal, "_repo_research_daemon_running", return_value=False),
            unittest.mock.patch.object(heal, "_daemon_heal_flock", return_value=nullcontext()),
        ):
            msg = heal._heal_research_daemon({})
        self.assertIn("enable --now", msg)
        ens.assert_called_once()
        self.assertIn("daemon_research_stopped", heal._HEALERS)
        self.assertIn("daemon_research_stopped", heal._CRITICAL_DAEMON_HEALS)

    def test_scan_heals_stopped_dashboard_daemon(self) -> None:
        """OVERSEER_DASHBOARD_KEEPALIVE_2026_09_06 — :8765 down is a heal target."""
        from contextlib import nullcontext

        src = Path(heal.__file__).read_text(encoding="utf-8")
        self.assertIn("OVERSEER_DASHBOARD_KEEPALIVE_2026_09_06", src)
        self.assertIn("daemon_dashboard_stopped", src)
        self.assertIn("def _dashboard_daemon_running", src)
        self.assertIn("def _heal_dashboard_daemon", src)
        with unittest.mock.patch.object(heal, "_dashboard_daemon_running", return_value=False):
            found = heal.scan_bottlenecks()
        ids = {b.id for b in found}
        self.assertIn("daemon_dashboard_stopped", ids)
        with (
            unittest.mock.patch.object(heal, "_dashboard_daemon_running", return_value=False),
            unittest.mock.patch.object(heal, "_daemon_heal_flock", return_value=nullcontext()),
            unittest.mock.patch.object(heal, "_kickstart_or_install", return_value="installed dash") as kick,
            unittest.mock.patch.object(heal, "_wait_launchctl_running", return_value=True),
            unittest.mock.patch.object(heal.subprocess, "run") as run,
        ):
            run.return_value = unittest.mock.Mock(returncode=0, stdout="", stderr="")
            with unittest.mock.patch.object(heal, "sys") as mock_sys:
                mock_sys.platform = "darwin"
                mock_sys.executable = heal.sys.executable
                msg = heal._heal_dashboard_daemon({})
        self.assertIn("installed dash", msg)
        kick.assert_called_once()
        self.assertIn("daemon_dashboard_stopped", heal._HEALERS)
        self.assertIn("daemon_dashboard_stopped", heal._CRITICAL_DAEMON_HEALS)

    def test_merge_history_logs_registry_clear(self) -> None:
        registry = {
            "history": {
                "unittest_storm": {
                    "first_seen": "2026-09-01",
                    "last_seen": "2026-09-01",
                    "hit_count": 1,
                    "title": "storm",
                    "category": "tests",
                    "severity": "high",
                    "status": "open",
                }
            }
        }
        logs: list[str] = []
        heal._merge_history([], registry, log_fn=logs.append)
        self.assertTrue(
            any("self-heal registry clear: unittest_storm (absent_from_scan)" in m for m in logs)
        )

    def test_apply_heals_logs_cooldown_and_success(self) -> None:
        bn = heal.Bottleneck(
            id="queue_spam",
            category="queue",
            severity="medium",
            title="spam",
            evidence="dupes",
            heal_action="dedupe",
        )
        registry = {"last_heal": {f"heal:{bn.id}": time.time()}, "progress_fp": {}}
        logs: list[str] = []
        with unittest.mock.patch.object(heal, "progress_stalled", return_value=False):
            with unittest.mock.patch.object(heal, "_heal_queue_spam") as healer:
                heal.apply_heals([bn], registry=registry, log_fn=logs.append)
        healer.assert_not_called()
        self.assertEqual(bn.heal_result, "cooldown")
        self.assertTrue(any("self-heal: queue_spam → cooldown (deferred)" in m for m in logs))

        bn2 = heal.Bottleneck(
            id="queue_spam",
            category="queue",
            severity="medium",
            title="spam",
            evidence="dupes",
            heal_action="dedupe",
        )
        logs2: list[str] = []
        with unittest.mock.patch.object(heal, "progress_stalled", return_value=False):
            with unittest.mock.patch.object(
                heal, "_heal_queue_spam", return_value="deduped 2"
            ):
                heal.apply_heals([bn2], registry={"last_heal": {}}, log_fn=logs2.append)
        self.assertTrue(any("self-heal: queue_spam → deduped 2" in m for m in logs2))

    def test_cooldown_bypass_when_progress_stalled(self) -> None:
        bn = heal.Bottleneck(
            id="verify_storm",
            category="verify",
            severity="high",
            title="storm",
            evidence="x",
            heal_action="clear lock",
        )
        registry = {"last_heal": {f"heal:{bn.id}": time.time()}}
        logs: list[str] = []
        with unittest.mock.patch.object(heal, "progress_stalled", return_value=True):
            with unittest.mock.patch.object(
                heal, "_remove_lock", return_value="cleared verify.lock"
            ):
                # healer is lambda calling _remove_lock — patch via _HEALERS
                with unittest.mock.patch.dict(
                    heal._HEALERS,
                    {"verify_storm": lambda _r: "cleared verify.lock"},
                ):
                    heal.apply_heals([bn], registry=registry, log_fn=logs.append)
        self.assertEqual(bn.status, "healed")
        self.assertTrue(any("cooldown bypass (progress stalled)" in m for m in logs))
        self.assertTrue(any("self-heal: verify_storm → cleared verify.lock" in m for m in logs))

    def test_progress_fingerprint_has_core_sha(self) -> None:
        snap = heal.progress_fingerprint()
        self.assertIn("core_sha", snap)
        self.assertEqual(len(snap["core_sha"]), 16)

    def test_progress_fp_share_ps_axo_no_transcript(self) -> None:
        """PROGRESS_FP_SHARE_PS_AXO + NO_TRANSCRIPT — no ps -u; no peer_transcript."""
        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        self.assertIn("PROGRESS_FP_SHARE_PS_AXO_2026_09_08", src)
        self.assertIn("PROGRESS_FP_NO_TRANSCRIPT_IMPORT_2026_09_08", src)
        sample = [
            "111 50000 cursor-agent -p --force",
            "222 90000 python3 scripts/peer_loop.py --forever",
            "333 40000 /path/cursor-agent-worker/bin/cursor-agent",
        ]
        calls = {"ps_u": 0, "axo": 0}
        real_co = subprocess.check_output

        def fake_co(cmd, *args, **kwargs):
            if (
                isinstance(cmd, (list, tuple))
                and len(cmd) >= 2
                and cmd[0] == "ps"
                and "-u" in cmd
            ):
                calls["ps_u"] += 1
                raise AssertionError("progress_fingerprint must not shell ps -u")
            return real_co(cmd, *args, **kwargs)

        def fake_axo():
            calls["axo"] += 1
            return list(sample)

        # Drop transcript so cold path cannot cheat via already-loaded module.
        sys.modules.pop("peer_transcript", None)
        with unittest.mock.patch.object(heal.subprocess, "check_output", side_effect=fake_co):
            with unittest.mock.patch.object(heal, "_ps_axo_lines", side_effect=fake_axo):
                with unittest.mock.patch.object(
                    heal,
                    "_read_state",
                    return_value={
                        "last_cycle": {"verify_ok": True, "failure_type": ""},
                    },
                ):
                    snap = heal.progress_fingerprint()
        self.assertEqual(calls["ps_u"], 0)
        self.assertEqual(calls["axo"], 1)
        self.assertEqual(snap["agents"], 2)
        self.assertTrue(snap["verify_ok"])
        self.assertNotIn("peer_transcript", sys.modules)

    def test_progress_fp_head_gen_cache_skips_git(self) -> None:
        """PROGRESS_FP_HEAD_GEN_CACHE — second call skips rev-parse when gen HIT."""
        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        self.assertIn("PROGRESS_FP_HEAD_GEN_CACHE_2026_09_08", src)
        self.assertIn("def _progress_head_short", src)
        heal.clear_progress_head_generation_cache()
        calls = {"rev_parse": 0}
        real_co = subprocess.check_output

        def fake_co(cmd, *args, **kwargs):
            if (
                isinstance(cmd, (list, tuple))
                and len(cmd) >= 2
                and cmd[0] == "git"
                and "rev-parse" in cmd
            ):
                calls["rev_parse"] += 1
                return "abc123def4567890deadbeef\n"
            return real_co(cmd, *args, **kwargs)

        pinned_gen = (111, 222)
        with (
            unittest.mock.patch.object(
                heal, "_git_head_index_mtime_ns_for_scan", return_value=pinned_gen
            ),
            unittest.mock.patch.object(heal.subprocess, "check_output", side_effect=fake_co),
            unittest.mock.patch.object(heal, "_ps_axo_lines", return_value=[]),
            unittest.mock.patch.object(
                heal, "_read_state", return_value={"last_cycle": {"verify_ok": True}}
            ),
            unittest.mock.patch.object(heal, "_peer_daemon_running", return_value=True),
            unittest.mock.patch.object(heal, "_improve_daemon_running", return_value=True),
        ):
            snap1 = heal.progress_fingerprint()
            snap2 = heal.progress_fingerprint()
        self.assertEqual(calls["rev_parse"], 1)
        self.assertEqual(snap1["head"], "abc123def4567890")
        self.assertEqual(snap2["head"], snap1["head"])
        self.assertEqual(snap1["core_sha"], snap2["core_sha"])

    def test_healers_include_progress_eaters(self) -> None:
        for hid in ("plan_gate_chicken_egg", "ram_ballast", "paid_auth_park"):
            self.assertIn(hid, heal._HEALERS)
            self.assertIn(hid, heal._CRITICAL_DAEMON_HEALS)

    def test_gpu_compute_ballast_exempt_when_avail_ok(self) -> None:
        """Productive mamba-2.8b ~3–8GB must not be ballast while MemAvailable healthy."""
        self.assertTrue(heal._gpu_compute_ballast_exempt(avail_gb=57.0))
        self.assertIsNone(
            heal._ram_ballast_min_rss_kb(
                "python3 scripts/dgx_gpu_compute.py --forever",
                avail_gb=57.0,
            )
        )
        # Under pressure, only runaway ≥14GB counts.
        self.assertFalse(heal._gpu_compute_ballast_exempt(avail_gb=4.0))
        self.assertEqual(
            heal._ram_ballast_min_rss_kb(
                "python3 scripts/dgx_gpu_compute.py --forever",
                avail_gb=4.0,
            ),
            heal._RAM_BALLAST_GPU_COMPUTE_MIN_RSS_KB,
        )
        self.assertEqual(
            heal._ram_ballast_min_rss_kb(
                "python3 scripts/dgx_resource_poll.py --forever",
                avail_gb=57.0,
            ),
            heal._RAM_BALLAST_MIN_RSS_KB,
        )

    def test_scan_ram_ballast_skips_gpu_compute_when_ok(self) -> None:
        # PS_AXO_RSS_SHARE — Linux ballast reads axo snapshot (pid rss comm args).
        lines = [
            "3321929 3500000 python3 /home/arnavrastogi/Automation/scripts/dgx_gpu_compute.py --forever",
            "111 250000 python3 scripts/dgx_resource_poll.py --forever",
        ]
        with unittest.mock.patch.object(heal, "_avail_ram_gb", return_value=57.0):
            with unittest.mock.patch.object(heal, "_ps_axo_lines", return_value=lines):
                with unittest.mock.patch.object(heal, "_pid_owned_by_me", return_value=True):
                    found = heal._scan_ram_ballast()
        self.assertEqual(found, ["111:244MB:dgx_resource_poll.py"])
        with unittest.mock.patch.object(heal, "_avail_ram_gb", return_value=4.0):
            with unittest.mock.patch.object(heal, "_ps_axo_lines", return_value=lines):
                with unittest.mock.patch.object(heal, "_pid_owned_by_me", return_value=True):
                    # 3.4GB < 14GB runaway floor → still skip under pressure
                    found_tight = heal._scan_ram_ballast()
        self.assertEqual(found_tight, ["111:244MB:dgx_resource_poll.py"])
        runaway = [
            "3321929 16000000 python3 /home/arnavrastogi/Automation/scripts/dgx_gpu_compute.py --forever",
        ]
        with unittest.mock.patch.object(heal, "_avail_ram_gb", return_value=4.0):
            with unittest.mock.patch.object(heal, "_ps_axo_lines", return_value=runaway):
                with unittest.mock.patch.object(heal, "_pid_owned_by_me", return_value=True):
                    found_run = heal._scan_ram_ballast()
        self.assertEqual(found_run, ["3321929:15625MB:dgx_gpu_compute.py"])

    def test_probe_cached_ttl_aligns_diagnose_asi(self) -> None:
        """SELF_HEAL_PROBE_TTL_ALIGN — HIT after 2.1s; expire only past effective TTL."""
        self.assertGreaterEqual(heal._PROBE_TTL_SEC, 30.0)
        self.assertIn(
            "SELF_HEAL_PROBE_TTL_ALIGN_2026_09_05",
            (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8"),
        )
        calls = {"n": 0}

        def probe() -> bool:
            calls["n"] += 1
            return True

        heal._probe_cache.clear()
        self.assertTrue(heal._probe_cached("ttl-test", probe))
        self.assertEqual(calls["n"], 1)
        # Former 2s TTL would remiss; aligned 30s must HIT.
        with unittest.mock.patch.object(heal.time, "time", return_value=time.time() + 2.1):
            self.assertTrue(heal._probe_cached("ttl-test", probe))
        self.assertEqual(calls["n"], 1)
        past = heal.probe_effective_ttl_sec() + 1.0
        with unittest.mock.patch.object(heal.time, "time", return_value=time.time() + past):
            self.assertTrue(heal._probe_cached("ttl-test", probe))
        self.assertEqual(calls["n"], 2)
        heal._invalidate_probe_cache()
        self.assertEqual(heal._probe_cache, {})

    def test_probe_ttl_wake_floor_hits_at_wake_boundary(self) -> None:
        """PROBE_TTL_WAKE_FLOOR — wake==bare TTL must still HIT scan memo."""
        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        self.assertIn("PROBE_TTL_WAKE_FLOOR_2026_09_08", src)
        wake = float(heal.cfg_mod.CFG.get("continuous_wake_sec") or 0.0)
        eff = heal.probe_effective_ttl_sec()
        self.assertGreaterEqual(eff, heal._PROBE_TTL_SEC)
        if wake >= heal._PROBE_TTL_SEC:
            self.assertGreaterEqual(eff, wake + heal._PROBE_WAKE_SLACK_SEC)
        heal.clear_scan_bottlenecks_cache()
        calls = {"n": 0}
        fake = [
            heal.Bottleneck(
                id="wake_floor",
                category="test",
                severity="low",
                title="wake",
                evidence="x",
            )
        ]

        def body(*, daemons=None):
            calls["n"] += 1
            return list(fake)

        with unittest.mock.patch.object(heal, "_scan_bottlenecks_body", side_effect=body):
            heal.scan_bottlenecks()
            self.assertEqual(calls["n"], 1)
            # Age by continuous_wake — former bare TTL remissed here.
            heal._SCAN_BOTTLENECKS_CACHE["at"] = time.monotonic() - max(wake, heal._PROBE_TTL_SEC)
            heal.scan_bottlenecks()
            self.assertEqual(calls["n"], 1, "wake-boundary must HIT under wake floor")
            heal._SCAN_BOTTLENECKS_CACHE["at"] = time.monotonic() - (eff + 1.0)
            heal.scan_bottlenecks()
            self.assertEqual(calls["n"], 2, "past effective TTL must remiss")

    def test_scan_bottlenecks_ttl_hit_and_invalidate(self) -> None:
        """SCAN_BOTTLENECKS_TTL — factory remiss shares scan within probe TTL."""
        self.assertIn(
            "SCAN_BOTTLENECKS_TTL_2026_09_07",
            (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8"),
        )
        heal.clear_scan_bottlenecks_cache()
        calls = {"n": 0}
        fake = [
            heal.Bottleneck(
                id="ttl_probe",
                category="test",
                severity="low",
                title="ttl",
                evidence="x",
            )
        ]

        def body(*, daemons=None):
            calls["n"] += 1
            return list(fake)

        with unittest.mock.patch.object(heal, "_scan_bottlenecks_body", side_effect=body):
            first = heal.scan_bottlenecks()
            self.assertEqual(calls["n"], 1)
            self.assertEqual(first[0].id, "ttl_probe")
            second = heal.scan_bottlenecks()
            self.assertEqual(calls["n"], 1, "TTL HIT must skip body")
            self.assertIsNot(second, first)
            # Injected daemons bypass memo
            heal.scan_bottlenecks(daemons={"peer_loop": True, "improve_loop": True})
            self.assertEqual(calls["n"], 2)
            # Age past effective TTL → remiss
            heal._SCAN_BOTTLENECKS_CACHE["at"] = time.monotonic() - (
                heal.probe_effective_ttl_sec() + 1.0
            )
            heal.scan_bottlenecks()
            self.assertEqual(calls["n"], 3)
            heal.clear_scan_bottlenecks_cache()
            heal.scan_bottlenecks()
            self.assertEqual(calls["n"], 4)
            heal._invalidate_probe_cache()
            self.assertIsNone(heal._SCAN_BOTTLENECKS_CACHE.get("items"))

    def test_forever_python_ps_axo_ttl_hit(self) -> None:
        """FOREVER_PYTHON_PS_AXO_TTL — job_stopped / forever pid share one ps shell."""
        self.assertIn(
            "FOREVER_PYTHON_PS_AXO_TTL_2026_09_08",
            (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8"),
        )
        heal.clear_ps_axo_cache()
        sample = (
            "12345 8000 python3 /usr/bin/python3 scripts/peer_loop.py --forever\n"
            "12346 9000 python3 /usr/bin/python3 scripts/automation_improve.py --forever\n"
        )
        calls = {"n": 0}
        real_run = subprocess.run

        def fake_run(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] == "ps" and "-axo" in cmd:
                calls["n"] += 1
                return unittest.mock.Mock(returncode=0, stdout=sample, stderr="")
            return real_run(cmd, *args, **kwargs)

        # Force ps fallback — Linux PROC_SNAPSHOT would skip the shell otherwise.
        with unittest.mock.patch.object(heal, "_linux_proc_ps_like_lines", return_value=None):
            with unittest.mock.patch.object(heal.subprocess, "run", side_effect=fake_run):
                p1 = heal._forever_python_pid("peer_loop.py")
                p2 = heal._forever_python_pid("peer_loop.py")
                p3 = heal._forever_python_pid("run_peer_loop_gitfile.py")
                self.assertEqual(p1, 12345)
                self.assertEqual(p2, 12345)
                self.assertIsNone(p3)  # needle absent — still HIT, no re-shell
                self.assertEqual(calls["n"], 1, "TTL HIT must skip re-shell ps -axo")
                # Age past effective TTL (wake+slack may exceed _PROBE_TTL_SEC) → remiss
                heal._PS_AXO_CACHE["at"] = time.monotonic() - (
                    heal.probe_effective_ttl_sec() + 1.0
                )
                heal._forever_python_pid("peer_loop.py")
                self.assertEqual(calls["n"], 2)
                heal.clear_ps_axo_cache()
                heal._forever_python_pid("peer_loop.py")
                self.assertEqual(calls["n"], 3)
                heal._invalidate_probe_cache()
                self.assertIsNone(heal._PS_AXO_CACHE.get("lines"))

    def test_proc_snapshot_replace_ps_axo_skips_ps_shell(self) -> None:
        """PROC_SNAPSHOT_REPLACE_PS_AXO — Linux /proc snapshot; no ps shell."""
        self.assertIn(
            "PROC_SNAPSHOT_REPLACE_PS_AXO_2026_09_08",
            (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8"),
        )
        if sys.platform == "darwin":
            self.skipTest("darwin keeps ps -axo")
        heal.clear_ps_axo_cache()
        sample = [
            "12345 8000 /usr/bin/python3 scripts/peer_loop.py --forever",
            "12346 9000 /usr/bin/python3 scripts/automation_improve.py --forever",
        ]
        calls = {"n": 0}
        real_run = subprocess.run

        def fake_run(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "ps":
                calls["n"] += 1
            return real_run(cmd, *args, **kwargs)

        with unittest.mock.patch.object(heal, "_linux_proc_ps_like_lines", return_value=sample):
            with unittest.mock.patch.object(heal.subprocess, "run", side_effect=fake_run):
                lines = heal._ps_axo_lines()
                self.assertEqual(lines, sample)
                self.assertEqual(heal._forever_python_pid("peer_loop.py"), 12345)
                # TTL HIT — no remiss
                self.assertEqual(heal._ps_axo_lines(), sample)
        self.assertEqual(calls["n"], 0, "Linux proc path must not shell ps")
        heal.clear_ps_axo_cache()
        heal._invalidate_probe_cache()
        self.assertIsNone(heal._PS_AXO_CACHE.get("lines"))

    def test_proc_lazy_rss_ballast_needles(self) -> None:
        """PROC_LAZY_RSS_BALLAST_NEEDLES — status/VmRSS only for ballast args."""
        self.assertIn(
            "PROC_LAZY_RSS_BALLAST_NEEDLES_2026_09_08",
            (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8"),
        )
        if sys.platform == "darwin":
            self.skipTest("darwin keeps ps -axo")
        # Synthetic /proc tree: one forever (no RSS) + one ballast needle (RSS).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forever = root / "111"
            forever.mkdir()
            (forever / "cmdline").write_bytes(
                b"/usr/bin/python3\x00scripts/peer_loop.py\x00--forever\x00"
            )
            (forever / "status").write_text(
                "Name:\tpython3\nVmRSS:\t8000 kB\n", encoding="utf-8"
            )
            ballast = root / "222"
            ballast.mkdir()
            (ballast / "cmdline").write_bytes(
                b"/usr/bin/python3\x00scripts/dgx_gpu_compute.py\x00--forever\x00"
            )
            (ballast / "status").write_text(
                "Name:\tpython3\nVmRSS:\t126996 kB\n", encoding="utf-8"
            )
            other = root / "333"
            other.mkdir()
            (other / "cmdline").write_bytes(b"/bin/bash\x00-c\x00sleep\x001\x00")
            (other / "status").write_text(
                "Name:\tbash\nVmRSS:\t1304 kB\n", encoding="utf-8"
            )
            status_opens: list[str] = []
            real_open = open

            def fake_open(path, *a, **k):
                sp = str(path)
                if sp.startswith("/proc/"):
                    sp = sp.replace("/proc/", str(root) + "/", 1)
                if sp.endswith("/status"):
                    status_opens.append(sp)
                return real_open(sp, *a, **k)

            with unittest.mock.patch.object(
                heal.os, "listdir", return_value=["111", "222", "333", "cpuinfo"]
            ):
                with unittest.mock.patch.object(heal.os, "stat") as mock_stat:
                    mock_stat.return_value = unittest.mock.Mock(st_uid=os.getuid())
                    with unittest.mock.patch.object(
                        heal.os, "getuid", return_value=os.getuid()
                    ):
                        with unittest.mock.patch("builtins.open", side_effect=fake_open):
                            lines = heal._linux_proc_ps_like_lines()
        self.assertIsNotNone(lines)
        by_pid = {ln.split(None, 2)[0]: ln for ln in (lines or [])}
        self.assertIn("111", by_pid)
        self.assertIn("222", by_pid)
        self.assertTrue(by_pid["111"].startswith("111 0 "), by_pid["111"])
        self.assertTrue(by_pid["222"].startswith("222 126996 "), by_pid["222"])
        self.assertEqual(len(status_opens), 1, status_opens)
        self.assertTrue(status_opens[0].endswith("/222/status"), status_opens)
        # Ballast iter must see real RSS for needle; forever still resolves.
        with unittest.mock.patch.object(heal, "_ps_axo_lines", return_value=lines):
            with unittest.mock.patch.object(heal, "_pid_owned_by_me", return_value=True):
                rows = heal._iter_ram_ballast_pid_rss_args()
            self.assertEqual(
                rows, [(222, 126996, by_pid["222"].split(None, 2)[2])]
            )
            self.assertEqual(
                heal._forever_python_pid_from_lines(lines, "peer_loop.py"), 111
            )

    def test_job_stopped_one_pass_ps_lines(self) -> None:
        """FOREVER_PYTHON_JOB_STOPPED_ONE_PASS — one lines walk for peer+improve."""
        self.assertIn(
            "FOREVER_PYTHON_JOB_STOPPED_ONE_PASS_2026_09_08",
            (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8"),
        )
        ballast = [
            f"{1000 + i} python3 /usr/bin/python3 other_{i}.py --forever"
            for i in range(400)
        ]
        lines = ballast + [
            "12345 python3 /usr/bin/python3 scripts/peer_loop.py --forever",
            "12346 python3 /usr/bin/python3 scripts/automation_improve.py --forever",
        ]
        with unittest.mock.patch.object(heal, "_ps_axo_lines", return_value=lines):
            with unittest.mock.patch.object(
                heal, "_pid_job_control_stopped", return_value=True
            ) as stopped:
                out = heal._job_stopped_loop_python_pids()
        self.assertEqual(out, [("peer", 12345), ("improve", 12346)])
        self.assertEqual(stopped.call_count, 2)

    def test_systemd_is_active_batch_ttl(self) -> None:
        """SYSTEMD_IS_ACTIVE_BATCH — N unit probes share one is-active shell."""
        self.assertIn(
            "SYSTEMD_IS_ACTIVE_BATCH_2026_09_08",
            (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8"),
        )
        heal.clear_systemd_active_cache()
        heal._probe_cache.clear()
        units = list(heal._SYSTEMD_ACTIVE_BATCH_UNITS)
        sample = "\n".join(["active"] * len(units)) + "\n"
        calls = {"n": 0, "argv": None}
        real_run = subprocess.run

        def fake_run(cmd, *args, **kwargs):
            if (
                isinstance(cmd, (list, tuple))
                and len(cmd) >= 4
                and cmd[0] == "systemctl"
                and "is-active" in cmd
            ):
                calls["n"] += 1
                calls["argv"] = list(cmd)
                return unittest.mock.Mock(returncode=0, stdout=sample, stderr="")
            return real_run(cmd, *args, **kwargs)

        with unittest.mock.patch.object(heal.subprocess, "run", side_effect=fake_run):
            for u in units:
                self.assertTrue(heal._systemd_user_active(u), u)
            self.assertEqual(calls["n"], 1, "cold batch must be one systemctl")
            self.assertEqual(calls["argv"][3:], units)
            # TTL HIT — no re-shell even after probe-cache clear per-unit
            heal._probe_cache.clear()
            for u in units:
                self.assertTrue(heal._systemd_user_active_impl(u), u)
            self.assertEqual(calls["n"], 1, "TTL HIT must skip re-shell")
            heal._SYSTEMD_ACTIVE_CACHE["at"] = time.monotonic() - (
                heal.probe_effective_ttl_sec() + 1.0
            )
            heal._systemd_user_active_impl(units[0])
            self.assertEqual(calls["n"], 2)
            heal.clear_systemd_active_cache()
            heal._systemd_user_active_impl(units[0])
            self.assertEqual(calls["n"], 3)
            heal._invalidate_probe_cache()
            self.assertIsNone(heal._SYSTEMD_ACTIVE_CACHE.get("states"))

    def test_ps_axo_rss_share_ballast_no_second_ps(self) -> None:
        """PS_AXO_RSS_SHARE_BALLAST — ballast reuses snapshot; no second ps -u."""
        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        self.assertIn("PS_AXO_RSS_SHARE_BALLAST_2026_09_08", src)
        self.assertIn("PROC_SNAPSHOT_REPLACE_PS_AXO_2026_09_08", src)
        heal.clear_ps_axo_cache()
        sample = [
            "111 512000 python3 /usr/bin/python3 scripts/dgx_gpu_compute.py --forever",
            "222 90000 python3 /usr/bin/python3 scripts/peer_loop.py --forever",
        ]
        calls = {"snap": 0, "user": 0}
        real_co = subprocess.check_output

        def fake_linux() -> list[str]:
            calls["snap"] += 1
            return list(sample)

        def fake_co(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "ps" and "-u" in cmd:
                calls["user"] += 1
            return real_co(cmd, *args, **kwargs)

        with unittest.mock.patch.object(
            heal, "_linux_proc_ps_like_lines", side_effect=fake_linux
        ):
            with unittest.mock.patch.object(
                heal.subprocess, "check_output", side_effect=fake_co
            ):
                with unittest.mock.patch.object(heal, "_pid_owned_by_me", return_value=True):
                    with unittest.mock.patch.object(
                        heal, "_gpu_compute_ballast_exempt", return_value=False
                    ):
                        rows = heal._iter_ram_ballast_pid_rss_args()
                        pid = heal._forever_python_pid("peer_loop.py")
        self.assertEqual(pid, 222)
        self.assertTrue(any(r[0] == 111 and r[1] == 512000 for r in rows))
        self.assertEqual(calls["snap"], 1)
        self.assertEqual(calls["user"], 0, "must not shell second ps -u when snapshot HIT")

    def test_launchctl_darwin_only_skips_linux(self) -> None:
        """LAUNCHCTL_DARWIN_ONLY — Linux never shells launchctl for dual-brain."""
        self.assertIn(
            "LAUNCHCTL_DARWIN_ONLY_2026_09_08",
            (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8"),
        )
        if sys.platform == "darwin":
            self.skipTest("darwin keeps launchctl")
        calls = {"n": 0}
        real_run = subprocess.run

        def fake_run(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "launchctl":
                calls["n"] += 1
            return real_run(cmd, *args, **kwargs)

        with unittest.mock.patch.object(heal.subprocess, "run", side_effect=fake_run):
            self.assertFalse(heal._launchctl_running(heal.RAM_PEER_LABEL))
        self.assertEqual(calls["n"], 0)

    def test_scan_adapt_no_cold_import_automation_adapt(self) -> None:
        """SCAN_ADAPT_NO_COLD_IMPORT — scan MISS must not compile automation_adapt."""
        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        self.assertIn("SCAN_ADAPT_NO_COLD_IMPORT_2026_09_08", src)
        self.assertIn("def _should_re_adapt_for_scan", src)
        # Body of scan adapt check must call lite helper, not import adapt.
        start = src.index("def _scan_bottlenecks_body")
        end = src.index("\ndef ", start + 1)
        body = src[start:end]
        self.assertIn("_should_re_adapt_for_scan", body)
        # Comment may name the module; live import must stay out of scan body.
        self.assertNotRegex(body, r"(?m)^\s+import automation_adapt\b")
        # Lite agrees with adapt when both available.
        import automation_adapt as adapt  # noqa: WPS433 — parity check only

        lite = heal._should_re_adapt_for_scan(heal.ROOT)
        full = adapt.should_re_adapt(heal.ROOT)
        self.assertEqual(lite, full)
        # Fresh scan after dropping module must not re-import.
        heal.clear_scan_bottlenecks_cache()
        if hasattr(heal, "clear_ps_axo_cache"):
            heal.clear_ps_axo_cache()
        if hasattr(heal, "clear_systemd_active_cache"):
            heal.clear_systemd_active_cache()
        sys.modules.pop("automation_adapt", None)
        sys.modules.pop("scripts.automation_adapt", None)
        with unittest.mock.patch.object(heal, "_peer_daemon_running", return_value=True):
            with unittest.mock.patch.object(heal, "_improve_daemon_running", return_value=True):
                with unittest.mock.patch.object(
                    heal, "_repo_research_daemon_running", return_value=True
                ):
                    with unittest.mock.patch.object(
                        heal, "_dashboard_daemon_running", return_value=True
                    ):
                        with unittest.mock.patch.object(
                            heal, "_job_stopped_loop_python_pids", return_value=[]
                        ):
                            heal.scan_bottlenecks()
        self.assertNotIn("automation_adapt", sys.modules)

    def test_scan_adapt_fp_gen_cache_skips_git_shells(self) -> None:
        """SCAN_ADAPT_FP_GEN_CACHE — second lite fp call with same HEAD/index gen skips git."""
        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        self.assertIn("SCAN_ADAPT_FP_GEN_CACHE_2026_09_08", src)
        self.assertIn("def clear_live_adapt_fp_generation_cache", src)
        heal.clear_live_adapt_fp_generation_cache()
        shells: list[str] = []
        real_check = subprocess.check_output

        def fake_check(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "git":
                shells.append(" ".join(str(x) for x in cmd[:6]))
            return real_check(cmd, *args, **kwargs)

        # Pin gen — live hub index mtime churns under concurrent git and would
        # false-MISS the HIT assertion (peer worktrees are quieter).
        pinned_gen = (111, 222)
        with unittest.mock.patch.object(
            heal, "_git_head_index_mtime_ns_for_scan", return_value=pinned_gen
        ):
            with unittest.mock.patch.object(
                heal.subprocess, "check_output", side_effect=fake_check
            ):
                first = heal._live_adapt_git_fingerprint(heal.ROOT)
                miss_n = len(shells)
                shells.clear()
                second = heal._live_adapt_git_fingerprint(heal.ROOT)
                hit_n = len(shells)
            self.assertEqual(first, second)
            self.assertGreaterEqual(miss_n, 2)  # rev-parse + porcelain
            self.assertEqual(hit_n, 0)
            # clear_scan must drop gen cache (force remiss shells again)
            heal.clear_scan_bottlenecks_cache()
            shells.clear()
            with unittest.mock.patch.object(
                heal.subprocess, "check_output", side_effect=fake_check
            ):
                heal._live_adapt_git_fingerprint(heal.ROOT)
            self.assertGreaterEqual(len(shells), 2)

    def test_scan_poison_no_cold_import_peer_transcript(self) -> None:
        """SCAN_POISON_NO_TRANSCRIPT_IMPORT — detect via peer_last_cycle_poison."""
        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        self.assertIn("SCAN_POISON_NO_TRANSCRIPT_IMPORT_2026_09_08", src)
        start = src.index("def _is_last_cycle_deferred_poison")
        end = src.index("\ndef ", start + 1)
        body = src[start:end]
        self.assertIn("peer_last_cycle_poison", body)
        self.assertNotIn("import peer_transcript", body)
        self.assertTrue(
            heal._is_last_cycle_deferred_poison(
                {"verify_ok": True, "failure_type": "deferred", "ts": 99.0}
            )
        )
        heal.clear_scan_bottlenecks_cache()
        sys.modules.pop("peer_transcript", None)
        sys.modules.pop("scripts.peer_transcript", None)
        # Detect path alone must not pull transcript.
        heal._is_last_cycle_deferred_poison(
            {"verify_ok": True, "failure_type": "deferred", "ts": 99.0}
        )
        self.assertNotIn("peer_transcript", sys.modules)

    def test_hub_protect_pause_no_land_hold_import_when_clear(self) -> None:
        """HUB_PROTECT_PAUSE_NO_LAND_HOLD_IMPORT — clear path skips land_hold."""
        src = (SCRIPTS / "peer_self_heal.py").read_text(encoding="utf-8")
        self.assertIn("HUB_PROTECT_PAUSE_NO_LAND_HOLD_IMPORT_2026_09_08", src)
        sys.modules.pop("peer_land_hold", None)
        sys.modules.pop("scripts.peer_land_hold", None)
        # Live clear flags + real wrap → False without importing land_hold.
        self.assertFalse(heal._hub_protect_restore_paused())
        self.assertNotIn("peer_land_hold", sys.modules)
        # Flag present must consult land_hold (intentional protect may suppress).
        hub = Path.home() / ".config" / "automation-hub"
        flag = hub / "RESTORE_PAUSED"
        hub.mkdir(parents=True, exist_ok=True)
        created = False
        try:
            if not flag.is_file():
                flag.write_text("test-pause\n", encoding="utf-8")
                created = True
            with unittest.mock.patch.dict(sys.modules, {"peer_land_hold": unittest.mock.MagicMock()}):
                mod = sys.modules["peer_land_hold"]
                mod.intentional_mac_clobber_protect.return_value = False
                mod.restore_is_paused.return_value = True
                self.assertTrue(heal._hub_protect_restore_paused())
                mod.intentional_mac_clobber_protect.assert_called()
        finally:
            if created:
                flag.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
