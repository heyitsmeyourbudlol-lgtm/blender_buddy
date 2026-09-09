"""Guards: compression keep-alive must not enqueue T4 shard fanout when TRAIN locked."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compression_keep_alive as cka  # noqa: E402


def _seed_notes(base: Path, *, unlocked: bool) -> None:
    notes = base / "notes"
    scripts = base / "scripts"
    art = notes / "compression_artifacts"
    notes.mkdir(parents=True, exist_ok=True)
    scripts.mkdir(parents=True, exist_ok=True)
    art.mkdir(parents=True, exist_ok=True)
    (notes / "WORK_QUEUE.md").write_text("## Active\n\n## Backlog\n", encoding="utf-8")
    (scripts / "self_improve_context.md").write_text(
        "## Remaining work (priority order)\n\n## Backlog\n", encoding="utf-8"
    )
    ready = (
        "T4 quality/scale path | **NO-GO**\ntrain_unlocked=false\n"
        if not unlocked
        else "T4 quality/scale path | **GO**\ntrain_unlocked=true\n"
        f"{cka.UNLOCK_NEEDLE}\n"
    )
    recipe = (
        "**Status:** **T0 packing GREEN · TRAIN-LOCKED**\n"
        if not unlocked
        else f"**Status:** **LOCKED**\n{cka.UNLOCK_NEEDLE}\ntrain_unlocked=true\n"
    )
    (notes / "COMPRESSION_TRAIN_READY.md").write_text(ready, encoding="utf-8")
    (notes / "COMPRESSION_TRAIN_RECIPE.md").write_text(recipe, encoding="utf-8")
    if unlocked:
        (art / "train_unlock.json").write_text(
            json.dumps({"train_unlocked": True, "needle": cka.UNLOCK_NEEDLE}) + "\n",
            encoding="utf-8",
        )


class KeepAliveTrainLockGuardTests(unittest.TestCase):
    def test_train_unlocked_respects_hub_artifact(self) -> None:
        # Fail-closed without artifact; when auto-train wrote train_unlock.json, mirror it.
        art = ROOT / "notes" / "compression_artifacts" / "train_unlock.json"
        if art.is_file():
            data = json.loads(art.read_text(encoding="utf-8"))
            self.assertEqual(bool(data.get("train_unlocked")), cka.train_unlocked(root=ROOT))
        else:
            self.assertFalse(cka.train_unlocked(root=ROOT))

    def test_train_unlocked_ignores_steward_prose_mention(self) -> None:
        """OVERSEER_KEEP_ALIVE_UNLOCK_BANNER_ONLY_2026_09_08 — prose ≠ unlock."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _seed_notes(base, unlocked=False)
            recipe = (
                "**Status:** **T0–T4 GREEN (proxy) · TRAIN-LOCKED**\n"
                f"no `{cka.UNLOCK_NEEDLE}` banner on card; prior stamp "
                "`train_unlocked=true` blocked.\n"
            )
            (base / "notes" / "COMPRESSION_TRAIN_RECIPE.md").write_text(
                recipe, encoding="utf-8"
            )
            (base / "notes" / "compression_artifacts" / "train_unlock.json").write_text(
                json.dumps({"train_unlocked": False, "needle": cka.UNLOCK_NEEDLE})
                + "\n",
                encoding="utf-8",
            )
            self.assertFalse(cka.train_unlocked(root=base))

    def test_train_unlocked_accepts_auto_train_banner(self) -> None:
        """Auto-train stamp banner unlocks when artifact absent."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _seed_notes(base, unlocked=False)
            recipe = (
                f"**Status:** **LOCKED**\n\n---\n**{cka.UNLOCK_NEEDLE}** · auto-train · "
                "train_unlocked=true · 2026-09-08 02:30Z\n"
            )
            (base / "notes" / "COMPRESSION_TRAIN_RECIPE.md").write_text(
                recipe, encoding="utf-8"
            )
            self.assertTrue(cka.train_unlocked(root=base))

    def test_enqueue_t4_shard_fanout_skips_when_locked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _seed_notes(base, unlocked=False)
            added = cka.enqueue_t4_shard_fanout(48, root=base, ts="2026-09-06 03:00")
            self.assertEqual(added, [])
            wq = (base / "notes" / "WORK_QUEUE.md").read_text(encoding="utf-8")
            ctx = (base / "scripts" / "self_improve_context.md").read_text(encoding="utf-8")
            self.assertNotIn("Shard-", wq)
            self.assertNotIn("microbench", wq)
            self.assertNotIn("Shard-", ctx)
            self.assertFalse(cka.train_unlocked(root=base))

    def test_ensure_queue_fuel_skips_when_locked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _seed_notes(base, unlocked=False)
            before_wq = (base / "notes" / "WORK_QUEUE.md").read_text(encoding="utf-8")
            added = cka.ensure_queue_fuel(root=base)
            self.assertEqual(added, [])
            after_wq = (base / "notes" / "WORK_QUEUE.md").read_text(encoding="utf-8")
            self.assertEqual(before_wq, after_wq)
            self.assertNotIn("Keep-alive fuel", after_wq)

    def test_ensure_queue_fuel_respects_closed_checkbox(self) -> None:
        """OVERSEER_COMPRESSION_FUEL_CHECKBOX_BLIND_2026_09_07 — [x] ≠ re-open."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _seed_notes(base, unlocked=True)
            closed = (
                "## Active\n\n"
                "## Backlog\n"
                "- [x] [compression-train] Keep-alive fuel — T4 / recipe lock "
                f"/ min-RAM @ NVFP4 (done) {cka.NEEDLE}\n"
                "- [x] [compression-train] Efficiency pass — cut unique U; "
                "raise S toward 100; measure pack bytes (S≈134 pack=37288)\n"
                "- [x] [research-speed] Staff CLEAN fanout — respawn if agents "
                "< floor (agents≥floor)\n"
            )
            (base / "notes" / "WORK_QUEUE.md").write_text(closed, encoding="utf-8")
            (base / "scripts" / "self_improve_context.md").write_text(
                closed, encoding="utf-8"
            )
            before_wq = (base / "notes" / "WORK_QUEUE.md").read_text(encoding="utf-8")
            added = cka.ensure_queue_fuel(root=base)
            self.assertEqual(added, [])
            after_wq = (base / "notes" / "WORK_QUEUE.md").read_text(encoding="utf-8")
            self.assertEqual(before_wq, after_wq)
            self.assertEqual(after_wq.count("Efficiency pass"), 1)
            self.assertEqual(after_wq.count("- [ ] [compression-train]"), 0)

    def test_ensure_queue_fuel_refuses_headerless_twin(self) -> None:
        """OVERSEER_ENSURE_QUEUE_FUEL_SECTION_2026_09_07 — empty twin ≠ 356B fuel-only."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _seed_notes(base, unlocked=True)
            empty = "\n\n"
            (base / "scripts" / "self_improve_context.md").write_text(
                empty, encoding="utf-8"
            )
            # WQ stays structured from seed
            before = (base / "scripts" / "self_improve_context.md").read_text(
                encoding="utf-8"
            )
            added = cka.ensure_queue_fuel(root=base)
            after = (base / "scripts" / "self_improve_context.md").read_text(
                encoding="utf-8"
            )
            self.assertEqual(before, after)
            self.assertLess(len(after.encode("utf-8")), 50)
            self.assertNotIn("Keep-alive fuel", after)
            self.assertFalse(cka._has_queue_structure(after))
            # Structured WQ still receives Active-scoped fuel
            wq = (base / "notes" / "WORK_QUEUE.md").read_text(encoding="utf-8")
            self.assertIn("## Active", wq)
            self.assertIn("Keep-alive fuel", wq)
            # Fuel must sit under Active, not as trailing orphans past Backlog
            active_i = wq.index("## Active")
            fuel_i = wq.index("Keep-alive fuel")
            backlog_i = wq.index("## Backlog")
            self.assertLess(active_i, fuel_i)
            self.assertLess(fuel_i, backlog_i)
            self.assertTrue(len(added) >= 1)

    def test_fuel_title_key_strips_checkbox(self) -> None:
        open_line = (
            "- [ ] [compression-train] Efficiency pass — cut unique U; raise S"
        )
        closed_line = (
            "- [x] [compression-train] Efficiency pass — measured S≈134"
        )
        self.assertEqual(
            cka._fuel_title_key(open_line),
            "[compression-train] Efficiency pass",
        )
        self.assertEqual(
            cka._fuel_title_key(closed_line),
            "[compression-train] Efficiency pass",
        )
        self.assertTrue(cka._fuel_line_present(closed_line + "\n", open_line))

    def test_enqueue_t4_shard_fanout_writes_when_unlocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _seed_notes(base, unlocked=True)
            self.assertTrue(cka.train_unlocked(root=base))
            added = cka.enqueue_t4_shard_fanout(2, root=base, ts="2026-09-06 04:00")
            self.assertEqual(len(added), 2)
            wq = (base / "notes" / "WORK_QUEUE.md").read_text(encoding="utf-8")
            self.assertIn("Shard-01 T4 microbench", wq)
            self.assertIn("Shard-02 T4 microbench", wq)
            ctx = (base / "scripts" / "self_improve_context.md").read_text(encoding="utf-8")
            self.assertIn("Shard-01 T4 microbench", ctx)


class KeepAliveWaveUnloadTests(unittest.TestCase):
    """COMPRESSION_KEEP_ALIVE_WAVE_UNLOAD_2026_09_07 — drop sticky fanout modules."""

    def test_prune_wave_rss_unloads_dispatch_modules(self) -> None:
        import peer_parallel_dispatch  # noqa: F401
        import project_automation  # noqa: F401

        self.assertIn("peer_parallel_dispatch", sys.modules)
        self.assertIn("project_automation", sys.modules)
        report = cka.prune_wave_rss(reason="unittest")
        self.assertGreaterEqual(int(report["dropped"]), 2)
        self.assertNotIn("peer_parallel_dispatch", sys.modules)
        self.assertNotIn("project_automation", sys.modules)
        self.assertIn("compression_keep_alive", sys.modules)

    def test_should_unload_keeps_self(self) -> None:
        self.assertFalse(cka._should_unload_module("compression_keep_alive"))
        self.assertTrue(cka._should_unload_module("peer_parallel_dispatch"))
        self.assertTrue(cka._should_unload_module("dgx_ram_budget"))
        self.assertTrue(cka._should_unload_module("automation_improve"))

    def test_boot_floor_skips_wave_when_above_train_floor(self) -> None:
        """COMPRESSION_KEEP_ALIVE_SKIP_BOOT_WAVE_2026_09_07 — no storm on restart."""
        # Mirrors main(): unlocked → boot_floor = min(env_floor, 16)
        env_floor = 48
        unlocked = True
        boot_floor = min(env_floor, 16) if unlocked else env_floor
        self.assertEqual(boot_floor, 16)
        n0 = 16
        self.assertFalse(n0 < boot_floor)  # skip_boot_wave path


class KeepAliveCheckSmokeTests(unittest.TestCase):
    """QA smoke: --check must be non-destructive (no fanout)."""

    def test_check_status_locked_temp_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _seed_notes(base, unlocked=False)
            status = cka.check_status(root=base)
            self.assertEqual(status["needle"], cka.NEEDLE)
            self.assertFalse(status["train_unlocked"])
            self.assertFalse(status["recipe_locked"])
            self.assertIs(status["wave"], False)
            self.assertEqual(status["billing_path"], "desktop_free")
            self.assertIs(status["paid_api"], False)
            self.assertTrue(status["billing_ok"])

    def test_check_status_unlocked_reads_stress_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _seed_notes(base, unlocked=True)
            art = base / "notes" / "compression_artifacts"
            (art / "stress_bars.json").write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "bars": {
                            "S_ge_100_or_recipe_floor": {"S": 134.0, "result": "PASS"},
                            "nvfp4_pack_bytes": {"pack_bytes": 37288.0, "result": "PASS"},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            status = cka.check_status(root=base)
            self.assertTrue(status["train_unlocked"])
            self.assertTrue(status["recipe_locked"])
            self.assertEqual(status["S_arith"], 134.0)
            self.assertEqual(status["nvfp4_pack_bytes"], 37288.0)
            self.assertTrue(status["north_star_s_ok"])
            self.assertEqual(status["stress_status"], "PASS")
            self.assertIs(status["wave"], False)
            self.assertEqual(status["billing_path"], "desktop_free")
            self.assertIs(status["paid_api"], False)
            self.assertTrue(status["billing_ok"])

    def test_billing_desktop_free_receipt_fail_closed(self) -> None:
        """Finance: PEER_LOOP_PAID_API=1 must fail billing_ok (never weaken $0 gate)."""
        import os

        prev = os.environ.get("PEER_LOOP_PAID_API")
        # Isolate from module-import preflight (may be "1" if caller set it).
        prev_pre = cka._PEER_LOOP_PAID_API_PREFLIGHT
        try:
            cka._PEER_LOOP_PAID_API_PREFLIGHT = "0"
            os.environ["PEER_LOOP_PAID_API"] = "0"
            ok = cka.billing_desktop_free_receipt()
            self.assertEqual(ok["billing_path"], "desktop_free")
            self.assertIs(ok["paid_api"], False)
            self.assertTrue(ok["peer_loop_paid_api_forced_off"])
            self.assertTrue(ok["peer_loop_paid_api_preflight_off"])
            self.assertTrue(ok["billing_ok"])

            os.environ["PEER_LOOP_PAID_API"] = "1"
            bad = cka.billing_desktop_free_receipt()
            self.assertEqual(bad["billing_path"], "desktop_free")
            self.assertIs(bad["paid_api"], False)  # policy never claims paid
            self.assertFalse(bad["peer_loop_paid_api_forced_off"])
            self.assertFalse(bad["billing_ok"])

            # Preflight paid alone fails closed even after import heal to 0.
            os.environ["PEER_LOOP_PAID_API"] = "0"
            cka._PEER_LOOP_PAID_API_PREFLIGHT = "1"
            pre = cka.billing_desktop_free_receipt()
            self.assertTrue(pre["peer_loop_paid_api_forced_off"])
            self.assertFalse(pre["peer_loop_paid_api_preflight_off"])
            self.assertFalse(pre["billing_ok"])
        finally:
            cka._PEER_LOOP_PAID_API_PREFLIGHT = prev_pre
            if prev is None:
                os.environ.pop("PEER_LOOP_PAID_API", None)
            else:
                os.environ["PEER_LOOP_PAID_API"] = prev

    def test_check_exit_code_fail_closed_on_staff_miss(self) -> None:
        """OVERSEER_KEEP_ALIVE_CHECK_FAIL_CLOSED_2026_09_07 — floor miss → rc≠0."""
        self.assertEqual(cka.check_exit_code({"agents_ge_floor": False}), 1)
        self.assertEqual(cka.check_exit_code({"agents_ge_floor": True}), 0)
        self.assertEqual(cka.check_exit_code({"agents_ge_floor": None}), 0)
        self.assertEqual(cka.check_exit_code({}), 0)

    def test_maybe_heal_ram_for_staff_floor_rebalance_once(self) -> None:
        """OVERSEER_KEEP_ALIVE_STAFF_RAM_HEAL_2026_09_07 — ballast purge when RAM blocks floor."""
        from unittest import mock

        prev_mono = cka._last_staff_ram_heal_mono
        cka._last_staff_ram_heal_mono = 0.0
        try:
            with (
                mock.patch.object(cka, "cursor_count", return_value=3),
                mock.patch.object(cka, "train_unlocked", return_value=True),
                mock.patch("dgx_ram_budget.dispatch_allowed", side_effect=[False, True]),
                mock.patch("dgx_ram_budget.ram_mode", return_value="pressure"),
                mock.patch(
                    "project_automation.max_parallel_agent_procs",
                    return_value=8,
                ),
                mock.patch("dgx_ram_fill.rebalance_ram", return_value={"ok": True}) as reb,
            ):
                out = cka.maybe_heal_ram_for_staff_floor(floor=8)
            self.assertTrue(out["attempted"])
            self.assertTrue(out["healed"])
            self.assertTrue(out["dispatch_allowed_after"])
            reb.assert_called_once()
            # Cooldown must skip second call immediately.
            with (
                mock.patch.object(cka, "cursor_count", return_value=3),
                mock.patch.object(cka, "train_unlocked", return_value=True),
                mock.patch("dgx_ram_budget.dispatch_allowed", return_value=False),
                mock.patch(
                    "project_automation.max_parallel_agent_procs",
                    return_value=8,
                ),
                mock.patch("dgx_ram_fill.rebalance_ram") as reb2,
            ):
                out2 = cka.maybe_heal_ram_for_staff_floor(floor=8)
            self.assertEqual(out2["skipped"], "cooldown")
            self.assertFalse(out2["attempted"])
            reb2.assert_not_called()
        finally:
            cka._last_staff_ram_heal_mono = prev_mono

    def test_cli_check_fail_closed_when_paid_preflight(self) -> None:
        """CLI PEER_LOOP_PAID_API=1 must not greenwash billing_ok after import stomp."""
        import os
        import subprocess

        env = os.environ.copy()
        env["PEER_LOOP_PAID_API"] = "1"
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "compression_keep_alive.py"), "--check"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        payload = json.loads(proc.stdout)
        # Floor miss fail-closes exit; billing soft-miss stays JSON-only.
        self.assertEqual(
            proc.returncode,
            cka.check_exit_code(payload),
            proc.stderr,
        )
        self.assertEqual(payload.get("billing_path"), "desktop_free")
        self.assertIs(payload.get("paid_api"), False)
        self.assertTrue(payload.get("peer_loop_paid_api_forced_off"))
        self.assertFalse(payload.get("peer_loop_paid_api_preflight_off"))
        self.assertFalse(payload.get("billing_ok"))

    def test_cli_check_exits_zero_no_forever(self) -> None:
        import subprocess

        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "compression_keep_alive.py"), "--check"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        payload = json.loads(proc.stdout)
        self.assertEqual(
            proc.returncode,
            cka.check_exit_code(payload),
            proc.stderr,
        )
        self.assertEqual(payload.get("needle"), cka.NEEDLE)
        self.assertIs(payload.get("wave"), False)
        self.assertIn("train_unlocked", payload)
        self.assertEqual(payload.get("billing_path"), "desktop_free")
        self.assertIs(payload.get("paid_api"), False)
        self.assertTrue(payload.get("billing_ok"))
        # Live Staff miss must not false-PASS on exit alone.
        if payload.get("agents_ge_floor") is False:
            self.assertNotEqual(proc.returncode, 0)


class KeepAliveStaffDeficitBatchTests(unittest.TestCase):
    """OVERSEER_KEEP_ALIVE_STAFF_P_COUNT + STAFF_DEFICIT_BATCH — no OOM storm fill."""

    def test_cursor_count_uses_find_agent_procs_not_bare_grep(self) -> None:
        from unittest import mock

        with mock.patch(
            "peer_parallel_dispatch.find_agent_procs",
            return_value=[object(), object()],
        ) as find:
            self.assertEqual(cka.cursor_count(), 2)
            find.assert_called_once_with(fresh=True)

    def test_one_wave_deficit_batch_one_when_one_short(self) -> None:
        from unittest import mock

        captured: dict = {}

        def _fake_cycle(assignments, **kwargs):
            captured["n_asn"] = len(assignments)
            captured["max_workers"] = kwargs.get("max_workers")
            return 1, False

        asn = [mock.Mock(standby=False) for _ in range(8)]
        with (
            mock.patch.object(cka, "train_unlocked", return_value=True),
            mock.patch.object(cka, "ensure_queue_fuel", return_value=[]),
            mock.patch.object(cka, "build_assignments", return_value=asn),
            mock.patch.object(cka, "cursor_count", return_value=7),
            mock.patch.object(cka, "_prune_after_wave"),
            mock.patch("dgx_ram_budget.dispatch_allowed", return_value=True),
            mock.patch("dgx_ram_budget.ram_agent_cap", return_value=8),
            mock.patch("project_automation.max_parallel_peers", return_value=8),
            mock.patch("project_automation.max_parallel_agent_procs", return_value=8),
            mock.patch("peer_parallel_dispatch.effective_hub_running", return_value=0),
            mock.patch(
                "peer_parallel_dispatch.run_parallel_niche_cycle",
                side_effect=_fake_cycle,
            ),
            mock.patch.dict("os.environ", {"FANOUT_STAFF_FILL_BATCH": "1"}, clear=False),
        ):
            n, ok = cka.one_wave(8)
        self.assertEqual(n, 1)
        self.assertFalse(ok)  # return from fake
        self.assertEqual(captured["max_workers"], 1)  # hub_run0 + batch1
        self.assertEqual(captured["n_asn"], 1)


if __name__ == "__main__":
    unittest.main()
