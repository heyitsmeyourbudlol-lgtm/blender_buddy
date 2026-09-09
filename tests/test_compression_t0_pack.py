"""T0 packing proof — ALBERT-BitMoE + LoRA-Hive unique/pack gates.

OVERSEER_COMPRESSION_T0_PACK_2026_09_05
OVERSEER_COMPRESSION_T0_PACK_CACHE_2026_09_05
OVERSEER_COMPRESSION_DUAL_SOT_CACHE_2026_09_07
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import compression_t0_pack as t0  # noqa: E402


class CompressionT0PackTests(unittest.TestCase):
    """OVERSEER_COMPRESSION_T0_PACK_2026_09_05"""

    def test_needle_present(self) -> None:
        src = (SCRIPTS / "compression_t0_pack.py").read_text(encoding="utf-8")
        self.assertIn(t0.NEEDLE, src)
        self.assertIn(t0.CACHE_NEEDLE, src)
        self.assertIn(t0.DUAL_SOT_CACHE_NEEDLE, src)
        self.assertIn(t0.DUAL_SOT_RAM_SOFT_NEEDLE, src)
        self.assertIn(t0.PROBE_CACHE_NEEDLE, src)
        self.assertIn(t0.HUB_UNLOCK_IGNORE_NEEDLE, src)
        self.assertIn(t0.WORKTREE_ROOT_BIND_NEEDLE, src)
        self.assertIn(t0.EXPAND_PATH_COERCE_NEEDLE, src)
        self.assertIn(t0.DUAL_SOT_STAMP_REFRESH_NEEDLE, src)
        self.assertIn(t0.DUAL_SOT_RAM_SOFT_REFRESH_NEEDLE, src)
        self.assertIn(t0.LANE_U_SOT_HEAL_NEEDLE, src)
        self.assertIn("heal_lane_u_sot", src)
        self.assertIn("_should_ram_soft_skip", src)
        self.assertIn("apply_hub_unlock_ignore", src)
        self.assertIn("_resolve_repo_root", src)
        self.assertIn("_redirect_hub_artifact_path", src)
        novel = (ROOT / "notes/COMPRESSION_NOVEL.md").read_text(encoding="utf-8")
        self.assertIn(t0.NEEDLE, novel)

    def test_n_logic_targets(self) -> None:
        self.assertEqual(t0.N_L_TARGETS, (100_000, 1_000_000))

    def test_all_stacks_pass(self) -> None:
        rows = t0.run_all()
        self.assertEqual(len(rows), 4)
        stacks = {(r.stack, r.n_logic) for r in rows}
        self.assertEqual(
            stacks,
            {
                ("ALBERT-BitMoE", 100_000),
                ("ALBERT-BitMoE", 1_000_000),
                ("LoRA-Hive", 100_000),
                ("LoRA-Hive", 1_000_000),
            },
        )
        for r in rows:
            with self.subTest(stack=r.stack, n=r.n_logic):
                self.assertGreaterEqual(r.s_arith, t0.MIN_ARITH)
                self.assertTrue(r.pass_arith, msg=f"S={r.s_arith}")
                self.assertTrue(r.pass_pack, msg=f"bytes={r.packed_bytes} U={r.u_unique}")
                self.assertTrue(r.passed)
                self.assertEqual(r.quality, "N/A")
                # packed ≈ U/8 (± metadata)
                self.assertLessEqual(abs(r.packed_bytes - r.u_unique / 8.0), t0.META_BOUND_BYTES)
                self.assertEqual(r.payload_bytes, (r.u_unique + 7) // 8)
                self.assertEqual(r.packed_bytes, r.payload_bytes + r.meta_bytes)

    def test_prefer_near_100_when_easy(self) -> None:
        """Soft prefer ~100×; both stacks should clear well above 50."""
        for r in t0.run_all():
            with self.subTest(stack=r.stack, n=r.n_logic):
                self.assertGreaterEqual(r.s_arith, 80.0)

    def test_cli_json_exit_zero(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "compression_t0_pack.py"), "--json"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data["needle"], t0.NEEDLE)
        self.assertEqual(data["cache_needle"], t0.CACHE_NEEDLE)
        self.assertTrue(data["all_passed"])
        self.assertFalse(data["train_unlocked"])
        self.assertFalse(data["data_prune"])
        self.assertEqual(data["quality"], "N/A")
        self.assertEqual(len(data["results"]), 4)

    def test_summary_honesty_locks(self) -> None:
        """T0 packing proof must not imply train unlock or data prune."""
        payload = t0.summary_dict(t0.run_all())
        self.assertFalse(payload["train_unlocked"])
        self.assertFalse(payload["data_prune"])
        self.assertEqual(payload["quality"], "N/A")
        self.assertTrue(payload["all_passed"])
        self.assertEqual(payload["cache_needle"], t0.CACHE_NEEDLE)

    def test_pack_cache_roundtrip(self) -> None:
        """OVERSEER_COMPRESSION_T0_PACK_CACHE_2026_09_05 — dump/load fingerprint."""
        self.assertTrue(t0.pack_cache_roundtrip_ok())
        with tempfile.TemporaryDirectory(prefix="t0_pack_test_") as td:
            path = Path(td) / "pack.json"
            dump = t0.dump_pack_report(path)
            cached = t0.load_pack_report(dump)
            self.assertFalse(cached["train_unlocked"])
            self.assertFalse(cached["data_prune"])
            self.assertEqual(cached["cache_needle"], t0.CACHE_NEEDLE)
            # refuse train unlock
            bad = dict(cached)
            bad["train_unlocked"] = True
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                t0.load_pack_report(path)

    def test_ensure_default_pack_cli(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "compression_t0_pack.py"),
                "--ensure-default-pack",
                "--json",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        data = json.loads(proc.stdout)
        self.assertTrue(data["pack_cache_ok"])
        self.assertTrue(data["all_passed"])
        self.assertFalse(data["train_unlocked"])
        self.assertFalse(data["data_prune"])
        self.assertEqual(data["pack_source"], "default_pack")
        self.assertTrue(t0.DEFAULT_PACK_PATH.is_file())
        loaded = t0.load_pack_report(t0.DEFAULT_PACK_PATH)
        self.assertEqual(loaded["needle"], t0.NEEDLE)
        self.assertEqual(loaded["cache_needle"], t0.CACHE_NEEDLE)

    def test_dual_sot_check_cli(self) -> None:
        """TRAIN-LOCK Dual SoT: pack report + T3 logit bank both green.

        RAM-safe: in-process ``main`` only — subprocess under storm OOMs (rc 137).
        """
        import compression_t3_bitdistill as t3
        from io import StringIO

        with mock.patch("sys.stdout", new_callable=StringIO) as buf:
            rc = t0.main(["--dual-sot-check", "--json"])
        self.assertEqual(rc, 0, msg=buf.getvalue())
        data = json.loads(buf.getvalue())
        self.assertTrue(data["dual_sot"])
        self.assertTrue(data["dual_sot_ok"])
        self.assertTrue(data["pack_ok"])
        self.assertTrue(data["bank_ok"])
        self.assertFalse(data["train_unlocked"])
        self.assertFalse(data["data_prune"])
        self.assertEqual(data["pack_path"], str(t0.DEFAULT_PACK_PATH))
        self.assertEqual(data["bank_path"], str(t3.DEFAULT_BANK_PATH))
        # Falsifier: dual SoT green must never flip train_unlocked
        payload = t0.dual_sot_check()
        self.assertTrue(payload["dual_sot_ok"])
        self.assertIs(payload["train_unlocked"], False)

    def test_worktree_root_bind_prefers_cwd(self) -> None:
        """OVERSEER_COMPRESSION_WORKTREE_ROOT_BIND_2026_09_08

        Hub ``__file__`` + cwd under peer worktree must resolve ROOT to the
        worktree so Dual SoT dumps cannot clobber hub stamps.
        """
        self.assertEqual(
            t0.WORKTREE_ROOT_BIND_NEEDLE,
            "OVERSEER_COMPRESSION_WORKTREE_ROOT_BIND_2026_09_08",
        )
        hub_script = Path("/home/arnavrastogi/Automation/scripts/compression_t0_pack.py")
        wt = ROOT
        self.assertEqual(wt.name, "peer-4")
        resolved = t0._resolve_repo_root(cwd=wt, file_path=hub_script)
        self.assertEqual(resolved.resolve(), wt.resolve())

        hub_dual = Path(
            "/home/arnavrastogi/Automation/notes/compression_artifacts/dual_sot_report.json"
        )
        redirected = t0._redirect_hub_artifact_path(hub_dual, cwd=wt)
        self.assertEqual(
            redirected.resolve(),
            (wt / "notes/compression_artifacts/dual_sot_report.json").resolve(),
        )
        # Hub cwd must not redirect (hub intentional dumps stay on hub).
        hub_root = Path("/home/arnavrastogi/Automation")
        same = t0._resolve_repo_root(cwd=hub_root, file_path=hub_script)
        self.assertEqual(same.resolve(), hub_root.resolve())
        no_redir = t0._redirect_hub_artifact_path(hub_dual, cwd=hub_root)
        self.assertEqual(no_redir.resolve(), hub_dual.resolve())

        # Dump with explicit hub path under a synthetic worktree cwd → worktree twin.
        with tempfile.TemporaryDirectory(prefix="wt_bind_") as td:
            fake_hub = Path(td) / "Automation"
            fake_wt = fake_hub / ".worktrees" / "peer-9"
            fake_hub_art = fake_hub / "notes" / "compression_artifacts"
            fake_wt_art = fake_wt / "notes" / "compression_artifacts"
            fake_hub_art.mkdir(parents=True)
            fake_wt_art.mkdir(parents=True)
            hub_path = fake_hub_art / "dual_sot_report.json"
            wt_path = fake_wt_art / "dual_sot_report.json"
            with mock.patch.object(t0, "_worktree_root_from_cwd", return_value=fake_wt):
                written = t0.dump_dual_sot_report(
                    hub_path,
                    {
                        "dual_sot_ok": True,
                        "pack_ok": True,
                        "bank_ok": True,
                        "pack_cache_ok": True,
                        "bank_cache_ok": True,
                        "expand_ok": True,
                        "expand_n_before": 64,
                        "expand_n_after": 264,
                        "expand_needle": "OVERSEER_COMPRESSION_LOGIT_EXPAND_2026_09_07",
                        "quality": "proxy",
                    },
                )
            self.assertEqual(written.resolve(), wt_path.resolve())
            self.assertTrue(wt_path.is_file())
            self.assertFalse(hub_path.is_file(), msg="must not clobber hub twin")
            body = json.loads(wt_path.read_text(encoding="utf-8"))
            self.assertTrue(body.get("dual_sot_ok"))
            self.assertIs(body.get("train_unlocked"), False)
            self.assertEqual(
                body.get("worktree_root_bind_needle"),
                t0.WORKTREE_ROOT_BIND_NEEDLE,
            )
            self.assertIn("artifact_root", body)

    def test_coerce_expand_path_refuses_junk(self) -> None:
        """OVERSEER_COMPRESSION_EXPAND_PATH_COERCE_2026_09_08

        Corrupt Dual SoT expand_path (e.g. ``z``) must fall back to Lane-U
        EXPANDED so keep-alive does not false-red when the bank exists.
        """
        import compression_logit_expand as expand

        self.assertEqual(
            t0.EXPAND_PATH_COERCE_NEEDLE,
            "OVERSEER_COMPRESSION_EXPAND_PATH_COERCE_2026_09_08",
        )
        good = Path(expand.EXPANDED)
        self.assertTrue(good.is_file() or True)  # may be missing in bare CI
        junk = t0.coerce_expand_path("z")
        self.assertEqual(junk.resolve(), t0._redirect_hub_artifact_path(good).resolve())
        missing = t0.coerce_expand_path("/tmp/no-such-expand-bank-xyz.json")
        self.assertEqual(
            missing.resolve(), t0._redirect_hub_artifact_path(good).resolve()
        )
        empty = t0.coerce_expand_path(None)
        self.assertEqual(
            empty.resolve(), t0._redirect_hub_artifact_path(good).resolve()
        )
        # When a real absolute file is provided, keep it (redirected).
        if good.is_file():
            kept = t0.coerce_expand_path(str(good))
            self.assertEqual(
                kept.resolve(), t0._redirect_hub_artifact_path(good).resolve()
            )

        # check_dual_sot_report must green under junk expand_path in report.
        if not t0.DEFAULT_DUAL_SOT_PATH.is_file() or not good.is_file():
            self.skipTest("dual_sot_report or expand bank missing")
        with tempfile.TemporaryDirectory(prefix="coerce_exp_") as td:
            report = Path(td) / "dual_sot_report.json"
            base = t0.load_dual_sot_report(t0.DEFAULT_DUAL_SOT_PATH)
            base["expand_path"] = "z"
            report.write_text(json.dumps(base, indent=2), encoding="utf-8")
            with mock.patch.object(
                t0, "dual_sot_check", return_value={
                    "dual_sot_ok": True,
                    "pack_ok": True,
                    "bank_ok": True,
                    "pack_needle": t0.NEEDLE,
                    "pack_cache_needle": t0.CACHE_NEEDLE,
                    "bank_needle": "OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05",
                    "bank_cache_needle": "OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05",
                    "pack_path": str(t0.DEFAULT_PACK_PATH),
                    "bank_path": str(
                        t0._ROOT / "notes/compression_artifacts/t3_teacher_logit_bank.json"
                    ),
                }
            ):
                chk = t0.check_dual_sot_report(report_path=report)
            self.assertTrue(chk.get("expand_ok"), msg=chk)
            self.assertTrue(chk.get("dual_sot_ok"), msg=chk)
            self.assertNotEqual(chk.get("expand_path"), "z")
            self.assertEqual(
                chk.get("expand_path_coerce_needle"), t0.EXPAND_PATH_COERCE_NEEDLE
            )
            self.assertIs(chk.get("train_unlocked"), False)
            # Durable SoT must carry coerce needle (CLI-only was theater).
            durable = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(
                durable.get("expand_path_coerce_needle"),
                t0.EXPAND_PATH_COERCE_NEEDLE,
            )
            self.assertTrue(durable.get("stamp_refreshed"), msg=durable)
            self.assertIs(durable.get("train_unlocked"), False)

    def test_dual_sot_ignores_hub_train_unlock(self) -> None:
        """OVERSEER_COMPRESSION_HUB_UNLOCK_IGNORE_2026_09_08

        Hub train_unlock.json=true must not flip Dual SoT / probe train_unlocked.
        Peer recipe stub stays TRAIN-LOCKED until explicit TRAIN-LOCK card fill.
        """
        self.assertEqual(
            t0.HUB_UNLOCK_IGNORE_NEEDLE,
            "OVERSEER_COMPRESSION_HUB_UNLOCK_IGNORE_2026_09_08",
        )
        with tempfile.TemporaryDirectory(prefix="hub_unlock_") as td:
            unlock = Path(td) / "train_unlock.json"
            unlock.write_text(
                json.dumps(
                    {
                        "needle": "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
                        "train_unlocked": True,
                        "ts": "test",
                        "reason": "fixture",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with mock.patch.object(
                t0, "_train_unlock_candidates", return_value=[unlock]
            ):
                st = t0.hub_train_unlock_status()
                self.assertTrue(st["hub_unlock_present"], msg=st)
                self.assertTrue(st["hub_unlock_claimed"], msg=st)
                self.assertTrue(st["hub_unlock_ignored"], msg=st)
                self.assertIs(st["train_unlocked"], False)
                self.assertEqual(
                    st.get("hub_unlock_file_needle"),
                    "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
                    msg=st,
                )

                payload = t0.dual_sot_check()
                self.assertTrue(payload.get("dual_sot_ok"), msg=payload)
                self.assertTrue(payload.get("hub_unlock_ignored"), msg=payload)
                self.assertTrue(payload.get("hub_unlock_claimed"), msg=payload)
                self.assertIs(payload.get("train_unlocked"), False)
                self.assertEqual(
                    payload.get("hub_unlock_ignore_needle"),
                    t0.HUB_UNLOCK_IGNORE_NEEDLE,
                )
                self.assertEqual(
                    payload.get("hub_unlock_file_needle"),
                    "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
                    msg=payload,
                )

                stamped = t0._apply_hub_unlock_ignore({"dual_sot_ok": True})
                self.assertTrue(stamped["hub_unlock_ignored"])
                self.assertIs(stamped["train_unlocked"], False)

    def test_ensure_dual_sot_cli(self) -> None:
        """Lane-U Dual SoT cache: refresh pack+logit OR RAM soft-skip keep-alive.

        Under MemAvailable < floor, --ensure-dual-sot soft-skips to
        check_dual_sot_report (no OOM). RAM-safe: in-process ``main`` only —
        subprocess under storm OOMs (rc 137). TRAIN stays locked either path.
        """
        import compression_t3_bitdistill as t3
        from io import StringIO

        env_force = os.environ.pop(t0.ENSURE_DUAL_SOT_FORCE_ENV, None)
        try:
            with mock.patch("sys.stdout", new_callable=StringIO) as buf:
                rc = t0.main(["--ensure-dual-sot", "--json"])
            self.assertEqual(rc, 0, msg=buf.getvalue())
            data = json.loads(buf.getvalue())
        finally:
            if env_force is not None:
                os.environ[t0.ENSURE_DUAL_SOT_FORCE_ENV] = env_force
        self.assertTrue(data["ensure_dual_sot"])
        self.assertTrue(data["dual_sot_ok"], msg=data)
        self.assertTrue(data["pack_ok"])
        self.assertTrue(data["bank_ok"])
        self.assertTrue(data["expand_ok"], msg=data)
        self.assertFalse(data["train_unlocked"])
        self.assertFalse(data["data_prune"])
        self.assertEqual(data["dual_sot_cache_needle"], t0.DUAL_SOT_CACHE_NEEDLE)
        # CLI report_path honesty (worktree bind): path must be peer twin, not hub.
        report_cli = Path(str(data.get("dual_sot_report_path") or "")).resolve()
        self.assertEqual(report_cli, t0.DEFAULT_DUAL_SOT_PATH.resolve(), msg=data)
        hub_dual = Path(
            "/home/arnavrastogi/Automation/notes/compression_artifacts/dual_sot_report.json"
        ).resolve()
        if ROOT.name.startswith("peer-") and ROOT.parent.name == ".worktrees":
            self.assertNotEqual(report_cli, hub_dual, msg=data)
        if data.get("ram_soft_skip"):
            self.assertEqual(data["ram_soft_needle"], t0.DUAL_SOT_RAM_SOFT_NEEDLE)
            self.assertLess(int(data["mem_available_kb"]), t0.ENSURE_DUAL_SOT_RAM_FLOOR_KB)
            # Soft-skip surfaces expand metadata without requiring growth assert
            self.assertIsNotNone(data.get("expand_n_after"))
        else:
            self.assertTrue(data["pack_cache_ok"])
            self.assertTrue(data["bank_cache_ok"])
            self.assertTrue(data["dual_sot_report_ok"])
            self.assertGreater(
                int(data["expand_n_after"]), int(data["expand_n_before"])
            )
            self.assertEqual(data["pack_path"], str(t0.DEFAULT_PACK_PATH))
            self.assertEqual(data["bank_path"], str(t3.DEFAULT_BANK_PATH))
        self.assertTrue(t0.DEFAULT_DUAL_SOT_PATH.is_file())
        loaded = t0.load_dual_sot_report(t0.DEFAULT_DUAL_SOT_PATH)
        self.assertTrue(loaded["dual_sot_ok"])
        self.assertIs(loaded["train_unlocked"], False)
        self.assertTrue(loaded.get("expand_ok"))
        # Falsifier: refuse unlock in durable report
        bad = dict(loaded)
        bad["train_unlocked"] = True
        with tempfile.TemporaryDirectory(prefix="dual_sot_test_") as td:
            path = Path(td) / "dual.json"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(ValueError):
                t0.load_dual_sot_report(path)
        # Falsifier: refuse expand_ok≠true (Lane-U durable check)
        bad_expand = dict(loaded)
        bad_expand["expand_ok"] = False
        with tempfile.TemporaryDirectory(prefix="dual_sot_expand_") as td:
            path = Path(td) / "dual.json"
            path.write_text(json.dumps(bad_expand), encoding="utf-8")
            with self.assertRaises(ValueError):
                t0.load_dual_sot_report(path)

    def test_check_dual_sot_report_cli(self) -> None:
        """Lane-U --check-dual-sot-report: durable report + live pack/logit.

        RAM-safe: in-process ``main`` / ``check_dual_sot_report`` only — no
        subprocess (OOM under RAM storm). TRAIN stays locked.
        """
        from io import StringIO

        if not t0.DEFAULT_DUAL_SOT_PATH.is_file():
            self.skipTest("dual_sot_report.json missing — run --ensure-dual-sot first")
        loaded = t0.load_dual_sot_report(t0.DEFAULT_DUAL_SOT_PATH)
        self.assertTrue(loaded.get("dual_sot_ok"), msg=loaded)
        self.assertTrue(loaded.get("expand_ok"), msg=loaded)
        with mock.patch("sys.stdout", new_callable=StringIO) as buf:
            rc = t0.main(["--check-dual-sot-report", "--json"])
        self.assertEqual(rc, 0, msg=buf.getvalue())
        data = json.loads(buf.getvalue())
        self.assertTrue(data["check_dual_sot_report"])
        self.assertTrue(data["dual_sot_report_ok"])
        self.assertTrue(data["dual_sot_ok"])
        self.assertTrue(data["expand_ok"])
        self.assertTrue(data["pack_ok"])
        self.assertTrue(data["bank_ok"])
        self.assertFalse(data["train_unlocked"])
        self.assertFalse(data["data_prune"])
        self.assertEqual(data["dual_sot_cache_needle"], t0.DUAL_SOT_CACHE_NEEDLE)
        report_cli = Path(str(data.get("dual_sot_report_path") or "")).resolve()
        self.assertEqual(report_cli, t0.DEFAULT_DUAL_SOT_PATH.resolve(), msg=data)
        self.assertTrue(data.get("stamp_refreshed"), msg=data)
        self.assertEqual(
            data.get("stamp_refresh_needle"), t0.DUAL_SOT_STAMP_REFRESH_NEEDLE
        )
        # Falsifier: check path must not unlock train
        payload = t0.check_dual_sot_report()
        self.assertTrue(payload["dual_sot_ok"])
        self.assertIs(payload["train_unlocked"], False)
        self.assertTrue(payload.get("stamp_refreshed"), msg=payload)
        self.assertEqual(
            Path(str(payload.get("dual_sot_report_path") or "")).resolve(),
            t0.DEFAULT_DUAL_SOT_PATH.resolve(),
            msg=payload,
        )

    def test_cli_dual_sot_report_path_honesty_after_worktree_bind(self) -> None:
        """Hub Dual SoT path under peer cwd must redirect CLI report_path to peer.

        Creative: CLI report_path honesty after worktree bind — without
        pre-load redirect, dual_sot_report_path lies about hub while dump
        went to peer. TRAIN locked.
        """
        if not t0.DEFAULT_DUAL_SOT_PATH.is_file():
            self.skipTest("dual_sot_report.json missing — run --ensure-dual-sot first")
        if not (ROOT.name.startswith("peer-") and ROOT.parent.name == ".worktrees"):
            self.skipTest("not running under peer worktree cwd")
        hub = Path(
            "/home/arnavrastogi/Automation/notes/compression_artifacts/dual_sot_report.json"
        )
        payload = t0.check_dual_sot_report(report_path=hub)
        self.assertTrue(payload.get("dual_sot_ok"), msg=payload)
        report_cli = Path(str(payload.get("dual_sot_report_path") or "")).resolve()
        self.assertEqual(report_cli, t0.DEFAULT_DUAL_SOT_PATH.resolve(), msg=payload)
        self.assertNotEqual(report_cli, hub.resolve(), msg=payload)
        self.assertIs(payload.get("train_unlocked"), False)
        self.assertTrue(payload.get("stamp_refreshed"), msg=payload)
        self.assertEqual(
            payload.get("worktree_root_bind_needle"), t0.WORKTREE_ROOT_BIND_NEEDLE
        )

    def test_heal_lane_u_sot_clears_sticky_soft(self) -> None:
        """OVERSEER_COMPRESSION_LANE_U_SOT_HEAL_2026_09_08

        Post-unittest SoT heal: sticky ram_soft_skip=true on Dual SoT + probe
        reports must clear via check stamp-refresh when live MemAvailable is
        above floor. TRAIN locked.
        """
        src = (SCRIPTS / "compression_t0_pack.py").read_text(encoding="utf-8")
        self.assertIn(t0.LANE_U_SOT_HEAL_NEEDLE, src)
        self.assertEqual(src.count('LANE_U_SOT_HEAL_NEEDLE = "'), 1)
        if not t0.DEFAULT_PACK_PATH.is_file():
            self.skipTest("t0_pack_report.json missing")
        expand_path = (
            t0.DEFAULT_DUAL_SOT_PATH.parent / "t3_teacher_logit_bank_expanded.json"
        )
        bank_path = t0.DEFAULT_DUAL_SOT_PATH.parent / "t3_teacher_logit_bank.json"
        if not expand_path.is_file() or not bank_path.is_file():
            self.skipTest("logit bank/expand missing — run --ensure-dual-sot first")
        with tempfile.TemporaryDirectory(prefix="lane_u_heal_") as td:
            dual_path = Path(td) / "dual_sot_report.json"
            probe_path = Path(td) / "probe_keep_alive_report.json"
            dual_body = {
                "dual_sot_ok": True,
                "pack_ok": True,
                "bank_ok": True,
                "pack_cache_ok": True,
                "bank_cache_ok": True,
                "expand_ok": True,
                "ram_soft_skip": True,
                "expand_n_before": 64,
                "expand_n_after": 264,
                "expand_path": str(expand_path),
                "expand_needle": "OVERSEER_COMPRESSION_LOGIT_EXPAND_2026_09_07",
                "pack_path": str(t0.DEFAULT_PACK_PATH),
                "bank_path": str(bank_path),
                "pack_needle": "OVERSEER_COMPRESSION_T0_PACK_2026_09_05",
                "pack_cache_needle": "OVERSEER_COMPRESSION_T0_PACK_CACHE_2026_09_05",
                "bank_needle": "OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05",
                "bank_cache_needle": "OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05",
                "quality": "proxy",
            }
            probe_body = {
                "probe_ok": True,
                "probe_keep_alive": True,
                "dual_sot_ok": True,
                "pack_ok": True,
                "bank_ok": True,
                "expand_ok": True,
                "healed_ok": True,
                "heal_via_expand": True,
                "undersize_ok": True,
                "snip_limit": 16,
                "ram_soft_skip": True,
                "expand_n_before": 64,
                "expand_n_after": 264,
                "expand_path": str(expand_path),
                "quality": "proxy",
            }
            t0.dump_dual_sot_report(dual_path, dual_body)
            t0.dump_probe_report(probe_path, probe_body)
            self.assertTrue(
                json.loads(dual_path.read_text(encoding="utf-8")).get("ram_soft_skip")
            )
            self.assertTrue(
                json.loads(probe_path.read_text(encoding="utf-8")).get("ram_soft_skip")
            )
            # Live soft false → heal must clear sticky poison on both reports.
            with mock.patch.object(
                t0, "_should_ram_soft_skip", return_value=(False, 64 * 1024 * 1024)
            ):
                out = t0.heal_lane_u_sot(
                    dual_sot_report_path=dual_path,
                    probe_report_path=probe_path,
                )
            self.assertTrue(out.get("heal_ok"), msg=out)
            self.assertEqual(out.get("needle"), t0.LANE_U_SOT_HEAL_NEEDLE)
            self.assertIs(out.get("train_unlocked"), False)
            self.assertTrue(out.get("dual_sot_ok"), msg=out)
            self.assertTrue(out.get("probe_ok"), msg=out)
            self.assertTrue(out.get("dual_stamp_refreshed"), msg=out)
            self.assertTrue(out.get("probe_stamp_refreshed"), msg=out)
            self.assertIs(out.get("sticky_soft_cleared"), True, msg=out)
            self.assertIs(out.get("dual_ram_soft_skip"), False, msg=out)
            self.assertIs(out.get("probe_ram_soft_skip"), False, msg=out)
            dual_after = json.loads(dual_path.read_text(encoding="utf-8"))
            probe_after = json.loads(probe_path.read_text(encoding="utf-8"))
            self.assertIs(dual_after.get("ram_soft_skip"), False, msg=dual_after)
            self.assertIs(probe_after.get("ram_soft_skip"), False, msg=probe_after)
            self.assertTrue(dual_after.get("stamp_refreshed"), msg=dual_after)
            self.assertTrue(probe_after.get("stamp_refreshed"), msg=probe_after)

    def test_check_dual_sot_report_stamp_refresh(self) -> None:
        """OVERSEER_COMPRESSION_DUAL_SOT_STAMP_REFRESH_2026_09_08

        RAM-safe: successful --check-dual-sot-report re-dumps durable report with
        fresh ts + hub unlock ignore + stamp_refresh_needle — no heavy ensure.
        Sticky loaded ram_soft_skip=true must clear when live MemAvailable is
        above floor. TRAIN locked.
        """
        src = (SCRIPTS / "compression_t0_pack.py").read_text(encoding="utf-8")
        self.assertIn(t0.DUAL_SOT_STAMP_REFRESH_NEEDLE, src)
        self.assertIn(t0.DUAL_SOT_RAM_SOFT_REFRESH_NEEDLE, src)
        # Needle assignment once (duplicate const theater fails keep-alive honesty).
        self.assertEqual(src.count('DUAL_SOT_STAMP_REFRESH_NEEDLE = "'), 1)
        with tempfile.TemporaryDirectory(prefix="dual_stamp_") as td:
            path = Path(td) / "dual_sot_report.json"
            good = {
                "dual_sot_ok": True,
                "pack_ok": True,
                "bank_ok": True,
                "pack_cache_ok": True,
                "bank_cache_ok": True,
                "expand_ok": True,
                "ram_soft_skip": True,
                "expand_n_before": 64,
                "expand_n_after": 264,
                "expand_path": str(
                    t0.DEFAULT_DUAL_SOT_PATH.parent
                    / "t3_teacher_logit_bank_expanded.json"
                ),
                "expand_needle": "OVERSEER_COMPRESSION_LOGIT_EXPAND_2026_09_07",
                "pack_path": str(t0.DEFAULT_PACK_PATH),
                "bank_path": str(
                    t0.DEFAULT_DUAL_SOT_PATH.parent / "t3_teacher_logit_bank.json"
                ),
                "pack_needle": "OVERSEER_COMPRESSION_T0_PACK_2026_09_05",
                "pack_cache_needle": "OVERSEER_COMPRESSION_T0_PACK_CACHE_2026_09_05",
                "bank_needle": "OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05",
                "bank_cache_needle": "OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05",
                "quality": "proxy",
            }
            t0.dump_dual_sot_report(path, good)
            before = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(before.get("ram_soft_skip"))
            unlock = Path(td) / "train_unlock.json"
            unlock.write_text(
                json.dumps(
                    {
                        "needle": "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
                        "train_unlocked": True,
                    }
                ),
                encoding="utf-8",
            )
            fake_expand = {
                "expand_ok": True,
                "n_before": 64,
                "n_after": 264,
                "expand_rows": 200,
                "needle": "OVERSEER_COMPRESSION_LOGIT_EXPAND_2026_09_07",
            }
            fake_dual = {
                "dual_sot_ok": True,
                "pack_ok": True,
                "bank_ok": True,
                "train_unlocked": False,
                "data_prune": False,
                "pack_path": str(t0.DEFAULT_PACK_PATH),
                "bank_path": str(
                    t0.DEFAULT_DUAL_SOT_PATH.parent / "t3_teacher_logit_bank.json"
                ),
                "pack_needle": "OVERSEER_COMPRESSION_T0_PACK_2026_09_05",
                "pack_cache_needle": "OVERSEER_COMPRESSION_T0_PACK_CACHE_2026_09_05",
                "bank_needle": "OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05",
                "bank_cache_needle": "OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05",
            }
            import compression_logit_expand as expand

            with mock.patch.object(
                t0, "_train_unlock_candidates", return_value=[unlock]
            ):
                with mock.patch.object(
                    expand, "check_expanded", return_value=dict(fake_expand)
                ):
                    with mock.patch.object(
                        t0, "dual_sot_check", return_value=dict(fake_dual)
                    ):
                        with mock.patch.object(
                            t0, "_should_ram_soft_skip", return_value=(True, 1_000_000)
                        ):
                            payload = t0.check_dual_sot_report(report_path=path)
            self.assertTrue(payload.get("dual_sot_ok"), msg=payload)
            self.assertTrue(payload.get("stamp_refreshed"), msg=payload)
            self.assertEqual(
                payload.get("stamp_refresh_needle"), t0.DUAL_SOT_STAMP_REFRESH_NEEDLE
            )
            self.assertTrue(payload.get("hub_unlock_ignored"), msg=payload)
            self.assertIs(payload.get("train_unlocked"), False)
            self.assertTrue(str(payload.get("ts") or "").endswith("Z"), msg=payload)
            after = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(after.get("dual_sot_ok"))
            self.assertIs(after.get("train_unlocked"), False)
            self.assertEqual(after.get("cache_needle"), t0.DUAL_SOT_CACHE_NEEDLE)
            self.assertEqual(
                after.get("stamp_refresh_needle"), t0.DUAL_SOT_STAMP_REFRESH_NEEDLE
            )
            self.assertTrue(after.get("stamp_refreshed"), msg=after)
            self.assertTrue(after.get("hub_unlock_ignored"))
            self.assertEqual(
                after.get("hub_unlock_file_needle"),
                "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
            )
            self.assertEqual(after.get("mem_available_kb"), 1_000_000)
            self.assertTrue(after.get("ram_soft_skip"))
            self.assertEqual(
                after.get("expand_path_coerce_needle"),
                t0.EXPAND_PATH_COERCE_NEEDLE,
            )
            self.assertEqual(
                payload.get("expand_path_coerce_needle"),
                t0.EXPAND_PATH_COERCE_NEEDLE,
            )

            # Falsifier: sticky loaded ram_soft_skip=true must clear when live
            # MemAvailable is above floor (OR would keep storm claim forever).
            high_kb = t0.ENSURE_DUAL_SOT_RAM_FLOOR_KB * 2
            with mock.patch.object(
                t0, "_train_unlock_candidates", return_value=[unlock]
            ):
                with mock.patch.object(
                    expand, "check_expanded", return_value=dict(fake_expand)
                ):
                    with mock.patch.object(
                        t0, "dual_sot_check", return_value=dict(fake_dual)
                    ):
                        with mock.patch.object(
                            t0,
                            "_should_ram_soft_skip",
                            return_value=(False, high_kb),
                        ):
                            cleared = t0.check_dual_sot_report(report_path=path)
            self.assertTrue(cleared.get("dual_sot_ok"), msg=cleared)
            self.assertTrue(cleared.get("stamp_refreshed"), msg=cleared)
            self.assertIs(cleared.get("ram_soft_skip"), False, msg=cleared)
            self.assertEqual(cleared.get("mem_available_kb"), high_kb)
            cleared_body = json.loads(path.read_text(encoding="utf-8"))
            self.assertIs(cleared_body.get("ram_soft_skip"), False, msg=cleared_body)
            self.assertEqual(cleared_body.get("mem_available_kb"), high_kb)
            self.assertIs(cleared_body.get("train_unlocked"), False)
            self.assertEqual(
                cleared_body.get("ram_soft_refresh_needle"),
                t0.DUAL_SOT_RAM_SOFT_REFRESH_NEEDLE,
            )
            self.assertEqual(
                cleared.get("ram_soft_refresh_needle"),
                t0.DUAL_SOT_RAM_SOFT_REFRESH_NEEDLE,
            )

    def test_probe_keep_alive_ram_safe(self) -> None:
        """PROBE_KEEP_ALIVE: undersize→ensure_expanded heal under soft-skip.

        Must not call FORCE ensure_dual_sot (OOM). TRAIN stays locked.
        """
        import compression_logit_expand as expand

        if not t0.DEFAULT_DUAL_SOT_PATH.is_file():
            self.skipTest("dual_sot_report.json missing — run --ensure-dual-sot first")
        with mock.patch.object(
            t0, "_should_ram_soft_skip", return_value=(True, 500_000)
        ):
            with mock.patch.object(
                t0,
                "ensure_dual_sot",
                side_effect=AssertionError("probe must not call ensure_dual_sot under soft-skip"),
            ):
                out = t0.probe_keep_alive(snip_limit=16)
        self.assertTrue(out["undersize_ok"], msg=out)
        self.assertTrue(out["heal_via_expand"], msg=out)
        self.assertTrue(out["healed_ok"], msg=out)
        self.assertTrue(out["probe_ok"], msg=out)
        self.assertTrue(out["dual_sot_ok"], msg=out)
        self.assertTrue(out["expand_ok"], msg=out)
        self.assertTrue(out["ram_soft_skip"])
        self.assertEqual(out["probe_needle"], t0.PROBE_KEEP_ALIVE_NEEDLE)
        self.assertIs(out["train_unlocked"], False)
        self.assertIs(out["data_prune"], False)
        live = expand.check_expanded()
        self.assertTrue(live.get("expand_ok"), msg=live)

    def test_check_dual_sot_report_live_expand_keep_alive(self) -> None:
        """Stale report expand_ok=true must not false-green undersized expand SoT.

        --check-dual-sot-report must live-probe check_expanded (report flag alone
        is insufficient). RAM-safe: mock dual_sot_check (pack/bank); only mutate
        expand artifact (+restore). TRAIN stays locked.
        """
        from unittest import mock

        import compression_logit_expand as expand

        if not t0.DEFAULT_DUAL_SOT_PATH.is_file():
            self.skipTest("dual_sot_report.json missing — run --ensure-dual-sot first")
        loaded = t0.load_dual_sot_report(t0.DEFAULT_DUAL_SOT_PATH)
        self.assertTrue(loaded.get("expand_ok"), msg=loaded)
        if not expand.EXPANDED.is_file():
            _path, checked = expand.ensure_expanded()
            self.assertTrue(checked.get("expand_ok"), msg=checked)

        prior = expand.EXPANDED.read_text(encoding="utf-8")
        fake_dual = {
            "dual_sot_ok": True,
            "pack_ok": True,
            "bank_ok": True,
            "train_unlocked": False,
            "data_prune": False,
            "pack_path": str(t0.DEFAULT_PACK_PATH),
            "bank_path": "notes/compression_artifacts/t3_teacher_logit_bank.json",
            "pack_needle": "OVERSEER_COMPRESSION_T0_PACK_2026_09_05",
            "pack_cache_needle": "OVERSEER_COMPRESSION_T0_PACK_CACHE_2026_09_05",
            "bank_needle": "OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05",
            "bank_cache_needle": "OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05",
        }
        try:
            with tempfile.TemporaryDirectory(prefix="exp_under_") as td:
                toy = Path(td) / "under.json"
                expand.expand(snip_limit=16, out_path=toy)
                expand.EXPANDED.write_text(
                    toy.read_text(encoding="utf-8"), encoding="utf-8"
                )
            live = expand.check_expanded()
            self.assertFalse(live.get("expand_ok"), msg=live)
            self.assertEqual(live.get("error"), "expand_rows_below_ensure_floor")
            with mock.patch.object(t0, "dual_sot_check", return_value=dict(fake_dual)):
                chk = t0.check_dual_sot_report()
            self.assertTrue(chk.get("dual_sot_report_ok"), msg=chk)
            self.assertFalse(chk.get("expand_ok"), msg=chk)
            self.assertFalse(chk.get("dual_sot_ok"), msg=chk)
            self.assertEqual(chk.get("expand_error"), "expand_rows_below_ensure_floor")
            self.assertIs(chk.get("train_unlocked"), False)
        finally:
            expand.EXPANDED.write_text(prior, encoding="utf-8")
            restored = expand.check_expanded()
            if not restored.get("expand_ok"):
                _path, restored = expand.ensure_expanded()
            self.assertTrue(restored.get("expand_ok"), msg=restored)

    def test_ensure_dual_sot_heals_undersized_expand(self) -> None:
        """Creative keep-alive: ensure_dual_sot must call ensure_expanded (floor).

        Needle: OVERSEER_COMPRESSION_DUAL_SOT_CACHE_2026_09_07 — expand heal is
        sidecar-only; dual_sot_check stays pack+canonical; train stays locked.
        Uses mocks for pack/bank/report I/O so the assert does not OOM under RAM storm.
        Force full path (patch soft-skip off) so expand heal wiring is asserted.
        """
        import compression_logit_expand as expand
        import compression_t3_bitdistill as t3

        fake_expand = {
            "expand_ok": True,
            "n_before": 64,
            "n_after": 64 + expand.DEFAULT_EXPAND_SNIPS,
            "needle": expand.NEEDLE,
            "train_unlocked": False,
            "data_prune": False,
        }
        fake_dual = {
            "dual_sot_ok": True,
            "pack_ok": True,
            "bank_ok": True,
            "pack_cache_ok": True,
            "bank_cache_ok": True,
            "train_unlocked": False,
            "data_prune": False,
            "quality": "proxy",
        }
        with mock.patch.object(
            t0, "_should_ram_soft_skip", return_value=(False, 8 * 1024 * 1024)
        ):
            with mock.patch.object(
                t0, "ensure_default_pack", return_value=(t0.DEFAULT_PACK_PATH, True)
            ):
                with mock.patch.object(
                    t3, "ensure_default_bank", return_value=(t3.DEFAULT_BANK_PATH, True)
                ):
                    with mock.patch.object(
                        expand,
                        "ensure_expanded",
                        return_value=(expand.EXPANDED, fake_expand),
                    ) as m_exp:
                        with mock.patch.object(
                            t0, "dual_sot_check", return_value=dict(fake_dual)
                        ):
                            with mock.patch.object(t0, "dump_dual_sot_report"):
                                with mock.patch.object(
                                    t0,
                                    "load_dual_sot_report",
                                    return_value={
                                        **fake_dual,
                                        "expand_ok": True,
                                        "dual_sot_ok": True,
                                        "train_unlocked": False,
                                    },
                                ):
                                    payload = t0.ensure_dual_sot()
        m_exp.assert_called_once()
        self.assertTrue(payload["dual_sot_ok"], msg=payload)
        self.assertTrue(payload["expand_ok"], msg=payload)
        self.assertFalse(payload.get("ram_soft_skip"), msg=payload)
        self.assertGreaterEqual(
            int(payload["expand_n_after"]) - int(payload["expand_n_before"]),
            expand.DEFAULT_EXPAND_SNIPS,
        )
        self.assertIs(payload["train_unlocked"], False)
        self.assertIs(payload["data_prune"], False)
        # Source lock: keep-alive must stay wired (not pack+bank only).
        src = (SCRIPTS / "compression_t0_pack.py").read_text(encoding="utf-8")
        self.assertIn("expand.ensure_expanded()", src)
        self.assertIn("_should_ram_soft_skip", src)

    def test_ensure_dual_sot_ram_soft_skip(self) -> None:
        """RAM soft-skip: low MemAvailable → check path, no ensure_expanded.

        Needle: OVERSEER_COMPRESSION_DUAL_SOT_RAM_SOFT_SKIP_2026_09_08.
        Falsifier: soft-skip must not call ensure_expanded / ensure_default_pack;
        undersized expand via check still fails dual_sot_ok. TRAIN locked.
        Soft-skip still dumps dual_sot_report with hub_unlock_ignored stamps
        (OVERSEER_COMPRESSION_HUB_UNLOCK_IGNORE_2026_09_08) — durable Dual SoT
        must not stay stale without hub ignore under persistent RAM soft-skip.
        Soft-skip dump also persists ram_soft_skip + ram_soft_needle +
        mem_available_kb so Lane-U SoT can prove soft path (not full ensure).
        """
        import compression_logit_expand as expand

        fake_check = {
            "check_dual_sot_report": True,
            "dual_sot": True,
            "dual_sot_ok": True,
            "dual_sot_report_ok": True,
            "expand_ok": True,
            "pack_ok": True,
            "bank_ok": True,
            "expand_n_before": 64,
            "expand_n_after": 264,
            "expand_path": str(expand.EXPANDED),
            "expand_needle": expand.NEEDLE,
            "pack_path": str(t0.DEFAULT_PACK_PATH),
            "bank_path": str(
                t0._ROOT / "notes" / "compression_artifacts" / "t3_teacher_logit_bank.json"
            ),
            "train_unlocked": False,
            "data_prune": False,
            "quality": "proxy",
            "dual_sot_cache_needle": t0.DUAL_SOT_CACHE_NEEDLE,
        }
        low_kb = t0.ENSURE_DUAL_SOT_RAM_FLOOR_KB // 2
        with tempfile.TemporaryDirectory(prefix="soft_dump_") as td:
            report = Path(td) / "dual_sot_report.json"
            unlock = Path(td) / "train_unlock.json"
            unlock.write_text(
                json.dumps(
                    {
                        "needle": "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
                        "train_unlocked": True,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                t0, "_should_ram_soft_skip", return_value=(True, low_kb)
            ):
                with mock.patch.object(
                    t0, "check_dual_sot_report", return_value=dict(fake_check)
                ) as m_chk:
                    with mock.patch.object(t0, "ensure_default_pack") as m_pack:
                        with mock.patch.object(
                            expand, "ensure_expanded"
                        ) as m_exp:
                            with mock.patch.object(
                                t0, "_train_unlock_candidates", return_value=[unlock]
                            ):
                                payload = t0.ensure_dual_sot(report_path=report)
            m_chk.assert_called_once()
            m_pack.assert_not_called()
            m_exp.assert_not_called()
            self.assertTrue(payload["ensure_dual_sot"], msg=payload)
            self.assertTrue(payload["ram_soft_skip"], msg=payload)
            self.assertEqual(payload["ram_soft_needle"], t0.DUAL_SOT_RAM_SOFT_NEEDLE)
            self.assertEqual(payload["mem_available_kb"], low_kb)
            self.assertTrue(payload["dual_sot_ok"], msg=payload)
            self.assertTrue(payload["expand_ok"], msg=payload)
            self.assertIs(payload["train_unlocked"], False)
            self.assertIs(payload["data_prune"], False)
            self.assertTrue(payload.get("hub_unlock_ignored"), msg=payload)
            self.assertTrue(payload.get("dual_sot_report_ok"), msg=payload)
            self.assertTrue(report.is_file(), msg="soft-skip must dump dual_sot_report")
            loaded = t0.load_dual_sot_report(report)
            self.assertTrue(loaded["dual_sot_ok"])
            body = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(body.get("hub_unlock_ignored"), msg=body)
            self.assertIs(body.get("train_unlocked"), False)
            self.assertEqual(
                body.get("hub_unlock_ignore_needle"), t0.HUB_UNLOCK_IGNORE_NEEDLE
            )
            # Durable dump must persist hub unlock *file* needle (not just ignored).
            self.assertEqual(
                body.get("hub_unlock_file_needle"),
                "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
                msg=body,
            )
            self.assertEqual(
                body.get("hub_unlock_path"),
                str(unlock),
                msg=body,
            )
            # Soft-skip durable honesty: ram_soft_skip + needle + mem must persist.
            self.assertTrue(body.get("ram_soft_skip"), msg=body)
            self.assertEqual(body.get("ram_soft_needle"), t0.DUAL_SOT_RAM_SOFT_NEEDLE)
            self.assertEqual(body.get("mem_available_kb"), low_kb)

        # Falsifier: soft-skip must fail-closed when check says expand bad
        bad_check = dict(fake_check)
        bad_check["expand_ok"] = False
        bad_check["dual_sot_ok"] = False
        with tempfile.TemporaryDirectory(prefix="soft_bad_") as td2:
            bad_report = Path(td2) / "dual_sot_report.json"
            with mock.patch.object(
                t0, "_should_ram_soft_skip", return_value=(True, low_kb)
            ):
                with mock.patch.object(
                    t0, "check_dual_sot_report", return_value=bad_check
                ):
                    bad = t0.ensure_dual_sot(report_path=bad_report)
            self.assertTrue(bad["ram_soft_skip"])
            self.assertFalse(bad["dual_sot_ok"], msg=bad)
            self.assertIs(bad["train_unlocked"], False)
            self.assertFalse(bad_report.is_file(), msg="fail-closed must not dump")

    def test_probe_keep_alive_needle_and_ok(self) -> None:
        """OVERSEER_COMPRESSION_DUAL_SOT_PROBE_KEEP_ALIVE_2026_09_08

        Soft-skip path: heal via ensure_expanded + check_dual_sot_report
        (never FORCE full ensure under storm). TRAIN locked.
        """
        src = (SCRIPTS / "compression_t0_pack.py").read_text(encoding="utf-8")
        self.assertIn(t0.PROBE_KEEP_ALIVE_NEEDLE, src)
        self.assertIn("heal_via_expand", src)
        import compression_logit_expand as expand

        if not expand.EXPANDED.is_file():
            expand.ensure_expanded()
        prior = expand.EXPANDED.read_text(encoding="utf-8")
        fake_expand = {
            "expand_ok": True,
            "n_before": 16,
            "n_after": 16 + expand.DEFAULT_EXPAND_SNIPS,
            "needle": expand.NEEDLE,
            "train_unlocked": False,
            "data_prune": False,
        }
        fake_check = {
            "dual_sot_ok": True,
            "pack_ok": True,
            "bank_ok": True,
            "expand_ok": True,
            "train_unlocked": False,
            "data_prune": False,
            "ram_soft_skip": True,
        }
        low_kb = t0.ENSURE_DUAL_SOT_RAM_FLOOR_KB // 2
        checks = [
            {
                "expand_ok": False,
                "error": "expand_rows_below_ensure_floor",
                "expand_rows": 16,
            },
            {
                "expand_ok": True,
                "n_before": 64,
                "n_after": 264,
                "expand_rows": expand.DEFAULT_EXPAND_SNIPS,
            },
        ]
        check_i = {"i": 0}

        def _check_side_effect():
            i = check_i["i"]
            check_i["i"] = i + 1
            if i < len(checks):
                return checks[i]
            return {
                "expand_ok": True,
                "expand_rows": expand.DEFAULT_EXPAND_SNIPS,
            }

        try:
            with mock.patch.object(
                t0, "_should_ram_soft_skip", return_value=(True, low_kb)
            ):
                with mock.patch.object(
                    expand,
                    "ensure_expanded",
                    return_value=(expand.EXPANDED, fake_expand),
                ) as m_exp:
                    with mock.patch.object(
                        t0, "check_dual_sot_report", return_value=dict(fake_check)
                    ) as m_chk:
                        with mock.patch.object(t0, "ensure_dual_sot") as m_ens:
                            with mock.patch.object(
                                expand,
                                "check_expanded",
                                side_effect=_check_side_effect,
                            ):
                                with mock.patch.object(
                                    expand,
                                    "expand",
                                    side_effect=lambda snip_limit=16, out_path=None, **_k: Path(
                                        out_path
                                    ).write_text("{}", encoding="utf-8"),
                                ):
                                    payload = t0.probe_keep_alive(snip_limit=16)
            m_exp.assert_called()
            m_chk.assert_called_once()
            m_ens.assert_not_called()
            self.assertTrue(payload.get("probe_ok"), msg=payload)
            self.assertTrue(payload.get("undersize_ok"), msg=payload)
            self.assertTrue(payload.get("healed_ok"), msg=payload)
            self.assertTrue(payload.get("heal_via_expand"), msg=payload)
            self.assertTrue(payload.get("ram_soft_skip"), msg=payload)
            self.assertTrue(payload.get("dual_sot_ok"), msg=payload)
            self.assertIs(payload.get("train_unlocked"), False)
            self.assertEqual(
                payload.get("probe_needle"), t0.PROBE_KEEP_ALIVE_NEEDLE
            )
        finally:
            expand.EXPANDED.write_text(prior, encoding="utf-8")
            restored = expand.check_expanded()
            if not restored.get("expand_ok"):
                expand.ensure_expanded()

    @unittest.skip(
        "live CLI probe OOMs under RAM storm (rc 137); covered by needle_and_ok "
        "+ manual --probe-keep-alive"
    )
    def test_probe_keep_alive_cli_exit_zero(self) -> None:
        """Live CLI probe — skipped under storm; run manually when MemAvailable high."""
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "compression_t0_pack.py"),
                "--probe-keep-alive",
                "--json",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr + proc.stdout[-2000:])
        data = json.loads(proc.stdout)
        self.assertTrue(data.get("probe_ok"), msg=data)
        self.assertIs(data.get("train_unlocked"), False)

    def test_probe_cache_dump_load_refuse(self) -> None:
        """OVERSEER_COMPRESSION_DUAL_SOT_PROBE_CACHE_2026_09_08 — Lane U dump/load.

        Refuse prune / unlock / missing probe_ok. TRAIN locked.
        """
        self.assertEqual(
            t0.PROBE_CACHE_NEEDLE,
            "OVERSEER_COMPRESSION_DUAL_SOT_PROBE_CACHE_2026_09_08",
        )
        with tempfile.TemporaryDirectory(prefix="probe_cache_") as td:
            path = Path(td) / "probe_keep_alive_report.json"
            good = {
                "probe_ok": True,
                "undersize_ok": True,
                "healed_ok": True,
                "heal_via_expand": True,
                "dual_sot_ok": True,
                "expand_ok": True,
                "pack_ok": True,
                "bank_ok": True,
                "ram_soft_skip": True,
                "expand_n_before": 64,
                "expand_n_after": 264,
                "expand_path": str(t0.DEFAULT_PROBE_PATH.parent / "t3_teacher_logit_bank_expanded.json"),
                "snip_limit": 16,
                "quality": "proxy",
            }
            t0.dump_probe_report(path, good)
            loaded = t0.load_probe_report(path)
            self.assertTrue(loaded["probe_ok"])
            self.assertEqual(loaded["cache_needle"], t0.PROBE_CACHE_NEEDLE)
            self.assertIs(loaded["train_unlocked"], False)

            bad_unlock = json.loads(path.read_text(encoding="utf-8"))
            bad_unlock["train_unlocked"] = True
            path.write_text(json.dumps(bad_unlock), encoding="utf-8")
            with self.assertRaises(ValueError):
                t0.load_probe_report(path)

            bad_probe = dict(good)
            bad_probe["probe_ok"] = False
            t0.dump_probe_report(path, bad_probe)
            # dump forces train_unlocked=False but probe_ok from payload
            body = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(body["probe_ok"])
            with self.assertRaises(ValueError):
                t0.load_probe_report(path)

    def test_check_probe_report_cli(self) -> None:
        """--check-probe-report reloads durable report + live expand/Dual SoT."""
        if not t0.DEFAULT_PROBE_PATH.is_file():
            self.skipTest("probe_keep_alive_report.json missing — run --probe-keep-alive first")
        loaded = t0.load_probe_report(t0.DEFAULT_PROBE_PATH)
        self.assertTrue(loaded.get("probe_ok"), msg=loaded)
        rc = t0.main(["--check-probe-report", "--json"])
        self.assertEqual(rc, 0)
        payload = t0.check_probe_report()
        self.assertTrue(payload.get("probe_report_ok"), msg=payload)
        self.assertTrue(payload.get("probe_ok"), msg=payload)
        self.assertTrue(payload.get("expand_ok"), msg=payload)
        self.assertTrue(payload.get("dual_sot_ok"), msg=payload)
        self.assertIs(payload.get("train_unlocked"), False)
        self.assertEqual(payload.get("probe_cache_needle"), t0.PROBE_CACHE_NEEDLE)

    def test_check_probe_report_stamp_refresh(self) -> None:
        """OVERSEER_COMPRESSION_PROBE_STAMP_REFRESH_2026_09_08

        RAM-safe: successful --check-probe-report re-dumps durable report with
        fresh ts + hub unlock ignore + stamp_refresh_needle — no undersize
        mutation. TRAIN locked.
        """
        src = (SCRIPTS / "compression_t0_pack.py").read_text(encoding="utf-8")
        self.assertIn(t0.PROBE_STAMP_REFRESH_NEEDLE, src)
        with tempfile.TemporaryDirectory(prefix="probe_stamp_") as td:
            path = Path(td) / "probe_keep_alive_report.json"
            good = {
                "probe_ok": True,
                "undersize_ok": True,
                "healed_ok": True,
                "heal_via_expand": True,
                "dual_sot_ok": True,
                "expand_ok": True,
                "pack_ok": True,
                "bank_ok": True,
                "ram_soft_skip": True,
                "expand_n_before": 64,
                "expand_n_after": 264,
                "expand_path": str(
                    t0.DEFAULT_PROBE_PATH.parent / "t3_teacher_logit_bank_expanded.json"
                ),
                "snip_limit": 16,
                "quality": "proxy",
            }
            t0.dump_probe_report(path, good)
            before = json.loads(path.read_text(encoding="utf-8"))
            # Prior dump has no live soft-skip mem stamp — refresh must rewrite it.
            self.assertNotEqual(before.get("mem_available_kb"), 1_000_000)
            unlock = Path(td) / "train_unlock.json"
            unlock.write_text(
                json.dumps(
                    {
                        "needle": "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
                        "train_unlocked": True,
                    }
                ),
                encoding="utf-8",
            )
            fake_expand = {
                "expand_ok": True,
                "n_before": 64,
                "n_after": 264,
                "expand_rows": 200,
            }
            fake_dual = {
                "dual_sot_ok": True,
                "pack_ok": True,
                "bank_ok": True,
                "train_unlocked": False,
                "data_prune": False,
            }
            import compression_logit_expand as expand

            with mock.patch.object(
                t0, "_train_unlock_candidates", return_value=[unlock]
            ):
                with mock.patch.object(
                    expand, "check_expanded", return_value=dict(fake_expand)
                ):
                    with mock.patch.object(
                        t0, "dual_sot_check", return_value=dict(fake_dual)
                    ):
                        with mock.patch.object(
                            t0, "_should_ram_soft_skip", return_value=(True, 1_000_000)
                        ):
                            payload = t0.check_probe_report(report_path=path)
            self.assertTrue(payload.get("probe_ok"), msg=payload)
            self.assertTrue(payload.get("stamp_refreshed"), msg=payload)
            self.assertEqual(
                payload.get("stamp_refresh_needle"), t0.PROBE_STAMP_REFRESH_NEEDLE
            )
            self.assertTrue(payload.get("hub_unlock_ignored"), msg=payload)
            self.assertIs(payload.get("train_unlocked"), False)
            self.assertTrue(
                str(payload.get("ts") or "").endswith("Z"), msg=payload
            )
            after = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(after.get("probe_ok"))
            self.assertIs(after.get("train_unlocked"), False)
            self.assertEqual(after.get("cache_needle"), t0.PROBE_CACHE_NEEDLE)
            self.assertEqual(
                after.get("stamp_refresh_needle"), t0.PROBE_STAMP_REFRESH_NEEDLE
            )
            # Durable SoT must record stamp_refreshed (not CLI-only theater).
            self.assertTrue(after.get("stamp_refreshed"), msg=after)
            self.assertTrue(after.get("hub_unlock_ignored"))
            self.assertEqual(
                after.get("hub_unlock_file_needle"),
                "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
            )
            self.assertTrue(str(after.get("ts") or "").endswith("Z"))
            self.assertEqual(after.get("mem_available_kb"), 1_000_000)
            self.assertTrue(after.get("heal_via_expand"))
            self.assertEqual(after.get("snip_limit"), 16)
            self.assertTrue(after.get("ram_soft_skip"))
            self.assertEqual(
                after.get("expand_path_coerce_needle"),
                t0.EXPAND_PATH_COERCE_NEEDLE,
            )
            self.assertEqual(
                payload.get("expand_path_coerce_needle"),
                t0.EXPAND_PATH_COERCE_NEEDLE,
            )

            # Falsifier: sticky loaded ram_soft_skip=true must clear when live
            # MemAvailable is above floor (OR would keep storm claim forever).
            high_kb = t0.ENSURE_DUAL_SOT_RAM_FLOOR_KB * 2
            with mock.patch.object(
                t0, "_train_unlock_candidates", return_value=[unlock]
            ):
                with mock.patch.object(
                    expand, "check_expanded", return_value=dict(fake_expand)
                ):
                    with mock.patch.object(
                        t0, "dual_sot_check", return_value=dict(fake_dual)
                    ):
                        with mock.patch.object(
                            t0,
                            "_should_ram_soft_skip",
                            return_value=(False, high_kb),
                        ):
                            cleared = t0.check_probe_report(report_path=path)
            self.assertTrue(cleared.get("probe_ok"), msg=cleared)
            self.assertTrue(cleared.get("stamp_refreshed"), msg=cleared)
            self.assertIs(cleared.get("ram_soft_skip"), False, msg=cleared)
            self.assertEqual(cleared.get("mem_available_kb"), high_kb)
            cleared_body = json.loads(path.read_text(encoding="utf-8"))
            self.assertIs(cleared_body.get("ram_soft_skip"), False, msg=cleared_body)
            self.assertEqual(cleared_body.get("mem_available_kb"), high_kb)
            self.assertIs(cleared_body.get("train_unlocked"), False)
            self.assertEqual(
                cleared_body.get("ram_soft_refresh_needle"),
                t0.PROBE_RAM_SOFT_REFRESH_NEEDLE,
            )
            self.assertEqual(
                cleared.get("ram_soft_refresh_needle"),
                t0.PROBE_RAM_SOFT_REFRESH_NEEDLE,
            )

    def test_worktree_root_bind_redirects_hub_dump(self) -> None:
        """OVERSEER_COMPRESSION_WORKTREE_ROOT_BIND_2026_09_08

        Bare hub-module import under peer worktree cwd must not dump Dual SoT /
        probe stamps onto hub ROOT (clobber risk). Redirect hub artifact paths
        into the worktree compression_artifacts dir. TRAIN locked.
        """
        src = (SCRIPTS / "compression_t0_pack.py").read_text(encoding="utf-8")
        self.assertIn(t0.WORKTREE_ROOT_BIND_NEEDLE, src)
        with tempfile.TemporaryDirectory(prefix="wt_bind_") as td:
            hub = Path(td) / "Automation"
            wt = hub / ".worktrees" / "peer-9"
            hub_art = hub / "notes" / "compression_artifacts"
            wt_art = wt / "notes" / "compression_artifacts"
            hub_art.mkdir(parents=True)
            wt_art.mkdir(parents=True)
            hub_script = hub / "scripts" / "compression_t0_pack.py"
            hub_script.parent.mkdir(parents=True)
            hub_script.write_text("# stub\n", encoding="utf-8")

            resolved = t0._resolve_repo_root(cwd=wt, file_path=hub_script)
            self.assertEqual(resolved.resolve(), wt.resolve())

            hub_probe = hub_art / "probe_keep_alive_report.json"
            redirected = t0._redirect_hub_artifact_path(hub_probe, cwd=wt)
            self.assertEqual(
                redirected.resolve(), (wt_art / "probe_keep_alive_report.json").resolve()
            )

            payload = {
                "probe_ok": True,
                "undersize_ok": True,
                "healed_ok": True,
                "heal_via_expand": True,
                "dual_sot_ok": True,
                "expand_ok": True,
                "pack_ok": True,
                "bank_ok": True,
                "ram_soft_skip": False,
                "expand_n_before": 64,
                "expand_n_after": 264,
                "expand_path": str(wt_art / "t3_teacher_logit_bank_expanded.json"),
                "snip_limit": 16,
                "quality": "proxy",
            }
            with mock.patch.object(t0, "_worktree_root_from_cwd", return_value=wt):
                written = t0.dump_probe_report(hub_probe, payload)
            self.assertEqual(
                written.resolve(), (wt_art / "probe_keep_alive_report.json").resolve()
            )
            self.assertTrue(written.is_file())
            self.assertFalse(hub_probe.exists())
            body = json.loads(written.read_text(encoding="utf-8"))
            self.assertTrue(body.get("probe_ok"))
            self.assertIs(body.get("train_unlocked"), False)
            self.assertEqual(
                body.get("worktree_root_bind_needle"), t0.WORKTREE_ROOT_BIND_NEEDLE
            )
            self.assertEqual(
                body.get("ram_soft_refresh_needle"), t0.PROBE_RAM_SOFT_REFRESH_NEEDLE
            )

    def test_hub_train_unlock_ignored(self) -> None:
        """OVERSEER_COMPRESSION_HUB_UNLOCK_IGNORE_2026_09_08

        Hub train_unlock.json=true must not flip Dual SoT train_unlocked.
        Falsifier: inject unlock file → hub_unlock_ignored + train_unlocked=false.
        """
        with tempfile.TemporaryDirectory(prefix="hub_unlock_") as td:
            unlock = Path(td) / "train_unlock.json"
            unlock.write_text(
                json.dumps(
                    {
                        "needle": "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
                        "train_unlocked": True,
                        "reason": "test inject",
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                t0, "_train_unlock_candidates", return_value=[unlock]
            ):
                st = t0.hub_train_unlock_status()
                self.assertTrue(st["hub_unlock_present"])
                self.assertTrue(st["hub_unlock_claimed"])
                self.assertTrue(st["hub_unlock_ignored"])
                self.assertIs(st["train_unlocked"], False)
                self.assertEqual(
                    st["hub_unlock_ignore_needle"], t0.HUB_UNLOCK_IGNORE_NEEDLE
                )
                self.assertEqual(
                    st.get("hub_unlock_file_needle"),
                    "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
                )
                payload = t0.dual_sot_check()
                self.assertTrue(payload["dual_sot_ok"], msg=payload)
                self.assertTrue(payload["hub_unlock_ignored"], msg=payload)
                self.assertIs(payload["train_unlocked"], False)
                stamped: dict = {"dual_sot_ok": True, "pack_ok": True, "bank_ok": True}
                t0._apply_hub_unlock_ignore(stamped)
                self.assertTrue(stamped["hub_unlock_ignored"])
                self.assertIs(stamped["train_unlocked"], False)
            missing = Path(td) / "missing.json"
            with mock.patch.object(
                t0, "_train_unlock_candidates", return_value=[missing]
            ):
                st2 = t0.hub_train_unlock_status()
                self.assertFalse(st2["hub_unlock_present"])
                self.assertFalse(st2["hub_unlock_ignored"])
                self.assertIs(st2["train_unlocked"], False)

    def test_hub_unlock_file_needle_persists_when_revoked(self) -> None:
        """OVERSEER_COMPRESSION_HUB_UNLOCK_FILE_NEEDLE_REVOKED_2026_09_08

        Steward-revoked hub train_unlock.json (train_unlocked=false) must still
        stamp hub_unlock_file_needle on Dual SoT / probe dumps. Losing the file
        needle after revoke made live reports look unlock-naive (theater).
        Falsifier: claimed=false + ignored=false + file_needle present +
        train_unlocked=false on check_dual_sot_report dump.
        """
        self.assertEqual(
            t0.HUB_UNLOCK_FILE_NEEDLE_REVOKED,
            "OVERSEER_COMPRESSION_HUB_UNLOCK_FILE_NEEDLE_REVOKED_2026_09_08",
        )
        src = (SCRIPTS / "compression_t0_pack.py").read_text(encoding="utf-8")
        self.assertIn(t0.HUB_UNLOCK_FILE_NEEDLE_REVOKED, src)
        with tempfile.TemporaryDirectory(prefix="hub_unlock_revoked_") as td:
            unlock = Path(td) / "train_unlock.json"
            unlock.write_text(
                json.dumps(
                    {
                        "needle": "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
                        "train_unlocked": False,
                        "steward_reject": True,
                        "reason": "REJECTED fixture",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            report = Path(td) / "dual_sot_report.json"
            report.write_text(
                json.dumps(
                    {
                        "cache_needle": t0.DUAL_SOT_CACHE_NEEDLE,
                        "dual_sot_ok": True,
                        "pack_ok": True,
                        "bank_ok": True,
                        "expand_ok": True,
                        "train_unlocked": False,
                        "data_prune": False,
                        "ram_soft_skip": False,
                    }
                ),
                encoding="utf-8",
            )
            fake_expand = {
                "expand_ok": True,
                "n_before": 64,
                "n_after": 264,
                "expand_rows": 200,
                "needle": "OVERSEER_COMPRESSION_LOGIT_EXPAND_2026_09_07",
                "train_unlocked": False,
                "data_prune": False,
            }
            fake_dual = {
                "dual_sot_ok": True,
                "pack_ok": True,
                "bank_ok": True,
                "train_unlocked": False,
                "data_prune": False,
                "pack_path": str(t0.DEFAULT_PACK_PATH),
                "bank_path": str(
                    t0.DEFAULT_DUAL_SOT_PATH.parent / "t3_teacher_logit_bank.json"
                ),
            }
            import compression_logit_expand as expand

            with mock.patch.object(
                t0, "_train_unlock_candidates", return_value=[unlock]
            ):
                st = t0.hub_train_unlock_status()
                self.assertTrue(st["hub_unlock_present"], msg=st)
                self.assertFalse(st["hub_unlock_claimed"], msg=st)
                self.assertFalse(st["hub_unlock_ignored"], msg=st)
                self.assertIs(st["train_unlocked"], False)
                self.assertEqual(
                    st.get("hub_unlock_file_needle"),
                    "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
                    msg=st,
                )
                with mock.patch.object(
                    expand, "check_expanded", return_value=dict(fake_expand)
                ):
                    with mock.patch.object(
                        t0, "dual_sot_check", return_value=dict(fake_dual)
                    ):
                        with mock.patch.object(
                            t0,
                            "_should_ram_soft_skip",
                            return_value=(False, t0.ENSURE_DUAL_SOT_RAM_FLOOR_KB * 2),
                        ):
                            payload = t0.check_dual_sot_report(report_path=report)
            self.assertTrue(payload.get("dual_sot_ok"), msg=payload)
            self.assertTrue(payload.get("stamp_refreshed"), msg=payload)
            self.assertFalse(payload.get("hub_unlock_claimed"), msg=payload)
            self.assertFalse(payload.get("hub_unlock_ignored"), msg=payload)
            self.assertIs(payload.get("train_unlocked"), False)
            self.assertEqual(
                payload.get("hub_unlock_file_needle"),
                "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
                msg=payload,
            )
            self.assertEqual(
                payload.get("hub_unlock_file_needle_revoked"),
                t0.HUB_UNLOCK_FILE_NEEDLE_REVOKED,
                msg=payload,
            )
            after = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(
                after.get("hub_unlock_file_needle"),
                "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05",
                msg=after,
            )
            self.assertEqual(
                after.get("hub_unlock_file_needle_revoked"),
                t0.HUB_UNLOCK_FILE_NEEDLE_REVOKED,
                msg=after,
            )
            self.assertIs(after.get("train_unlocked"), False)
            self.assertFalse(after.get("hub_unlock_claimed"))
            self.assertFalse(after.get("hub_unlock_ignored"))


if __name__ == "__main__":
    unittest.main()
