"""Tests for peer_self_heal bottleneck detection and mechanical heals."""

from __future__ import annotations

import json
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
        with unittest.mock.patch.object(heal.sys, "platform", "linux"):
            with unittest.mock.patch.object(
                heal, "_ensure_systemd_peer_unit", return_value="restarted peer-loop.service"
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
                    self.assertFalse(heal._peer_daemon_running())

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



if __name__ == "__main__":
    unittest.main()
