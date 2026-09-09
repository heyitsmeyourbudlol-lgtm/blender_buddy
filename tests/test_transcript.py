"""Tests for cross-workspace Cursor transcript discovery + harness memory."""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_transcript as pt  # noqa: E402
import project_automation as auto  # noqa: E402


class TranscriptDiscoveryTests(unittest.TestCase):
    def test_workspace_slug_for_caas(self) -> None:
        slug = pt.workspace_slug_for_root(Path("/Users/togi/CaaS"))
        self.assertEqual(slug, "Users-togi-CaaS")

    def test_workspace_slug_for_ram(self) -> None:
        slug = pt.workspace_slug_for_root(Path("/Users/togi/ram"))
        self.assertEqual(slug, "Users-togi-ram")

    def test_transcript_roots_includes_primary(self) -> None:
        roots = pt.transcript_roots()
        self.assertTrue(roots)
        slugs = {r.parent.name for r in roots}
        self.assertIn(pt.workspace_slug_for_root(auto.ROOT), slugs)

    def test_find_latest_transcript_returns_path(self) -> None:
        path = pt.find_latest_transcript()
        if path is None:
            self.skipTest("no Cursor transcripts on machine")
        self.assertTrue(path.is_file())
        self.assertTrue(path.suffix == ".jsonl")

    def test_transcript_paths_cache_hit_and_clear(self) -> None:
        pt.clear_transcript_paths_cache()
        first = pt._parent_transcript_paths()
        second = pt._parent_transcript_paths()
        self.assertIs(first, second)
        pt.clear_transcript_paths_cache()
        third = pt._parent_transcript_paths()
        self.assertIsNot(first, third)
        self.assertEqual(len(first), len(third))

    def test_find_latest_scandir_matches_path_list_max(self) -> None:
        pt.clear_transcript_paths_cache()
        roots = pt.transcript_roots()
        if not roots:
            self.skipTest("no transcript roots")
        via_scandir = pt._find_latest_transcript_scandir(roots)
        paths = pt._parent_transcript_paths()
        if not paths:
            self.assertIsNone(via_scandir)
            return
        via_max = max(paths, key=lambda p: p.stat().st_mtime)
        self.assertEqual(via_scandir, via_max)

    def test_find_latest_ttl_returns_same_path(self) -> None:
        pt.clear_transcript_paths_cache()
        a = pt.find_latest_transcript(fresh=True)
        b = pt.find_latest_transcript()
        self.assertEqual(a, b)

    def test_parent_transcript_paths_mtime_cache(self) -> None:
        """OVERSEER_TRANSCRIPT_PATHS_CACHE_2026_09_07 — warm hit skips full iterdir."""
        pt.clear_transcript_paths_cache()
        first = pt._parent_transcript_paths()
        second = pt._parent_transcript_paths()
        self.assertIs(first, second)
        pt.clear_transcript_paths_cache()
        third = pt._parent_transcript_paths()
        self.assertIsNot(third, first)
        self.assertEqual(len(third), len(first))

    def test_find_latest_ttl_cache(self) -> None:
        """OVERSEER_TRANSCRIPT_PATHS_CACHE_2026_09_07 — short TTL on winner."""
        pt.clear_transcript_paths_cache()
        a = pt.find_latest_transcript(fresh=True)
        b = pt.find_latest_transcript()
        self.assertEqual(a, b)
        pt.clear_transcript_paths_cache()
        c = pt.find_latest_transcript(fresh=True)
        self.assertEqual(a, c)

    def test_find_latest_generation_hit_past_wall_ttl(self) -> None:
        """FIND_LATEST_ROOT_FP_GENERATION_2026_09_07 — same root fp skips scandir after TTL."""
        self.assertIn(
            "FIND_LATEST_ROOT_FP_GENERATION_2026_09_07",
            (SCRIPTS / "peer_transcript.py").read_text(encoding="utf-8"),
        )
        pt.clear_transcript_paths_cache()
        first = pt.find_latest_transcript(fresh=True)
        if first is None:
            self.skipTest("no Cursor transcripts on machine")
        self.assertIsNotNone(pt._LATEST_TRANSCRIPT_CACHE)
        # Age past wall TTL with stable roots fingerprint.
        ts, fp, path = pt._LATEST_TRANSCRIPT_CACHE
        pt._LATEST_TRANSCRIPT_CACHE = (time.time() - 30.0, fp, path)
        calls = {"n": 0}
        real = pt._find_latest_transcript_scandir

        def counted(roots):
            calls["n"] += 1
            return real(roots)

        with mock.patch.object(pt, "_find_latest_transcript_scandir", side_effect=counted):
            second = pt.find_latest_transcript()
        self.assertEqual(second, first)
        self.assertEqual(calls["n"], 0, "generation HIT must skip scandir")

    def test_find_latest_generation_remiss_when_root_fp_changes(self) -> None:
        """Root mtime fp change after wall TTL must rescan."""
        pt.clear_transcript_paths_cache()
        first = pt.find_latest_transcript(fresh=True)
        if first is None:
            self.skipTest("no Cursor transcripts on machine")
        _ts, fp, path = pt._LATEST_TRANSCRIPT_CACHE
        bogey = tuple(x + 1.0 for x in fp) if fp else (1.0,)
        pt._LATEST_TRANSCRIPT_CACHE = (time.time() - 30.0, bogey, path)
        calls = {"n": 0}
        real = pt._find_latest_transcript_scandir

        def counted(roots):
            calls["n"] += 1
            return real(roots)

        with mock.patch.object(pt, "_find_latest_transcript_scandir", side_effect=counted):
            # Soft call: live roots fp ≠ bogey → generation miss → scandir.
            third = pt.find_latest_transcript()
        self.assertEqual(calls["n"], 1)
        self.assertEqual(third, first)

    def test_peer_transcript_root_shim_loads_scripts(self) -> None:
        """PEER_TRANSCRIPT_ROOT_SHIM_2026_09_08 — cwd twin re-exports scripts SoT."""
        import importlib.util

        root = SCRIPTS.parent
        shim_path = root / "peer_transcript.py"
        self.assertTrue(shim_path.is_file(), "hub root peer_transcript.py missing")
        shim_src = shim_path.read_text(encoding="utf-8")
        self.assertIn("PEER_TRANSCRIPT_ROOT_SHIM_2026_09_08", shim_src)
        self.assertIn("scripts/peer_transcript.py", shim_src)
        # Stale twin must not remain (no full find_latest body at root).
        self.assertNotIn("def find_latest_transcript", shim_src)
        self.assertIn(
            "FIND_LATEST_ROOT_FP_GENERATION_2026_09_07",
            (SCRIPTS / "peer_transcript.py").read_text(encoding="utf-8"),
        )
        # Load shim under an isolated name; restore peer_transcript after.
        # Do not call find_latest here (17k-dir scandir) — generation HIT covered above.
        name = "_peer_transcript_root_shim_test"
        saved = sys.modules.get("peer_transcript")
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                del sys.modules[key]
        try:
            spec = importlib.util.spec_from_file_location(name, shim_path)
            self.assertIsNotNone(spec)
            assert spec is not None and spec.loader is not None
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
            self.assertTrue(callable(getattr(mod, "find_latest_transcript", None)))
            self.assertTrue(callable(getattr(mod, "clear_transcript_paths_cache", None)))
            self.assertTrue(callable(getattr(mod, "_transcript_roots_fingerprint", None)))
        finally:
            sys.modules.pop(name, None)
            if saved is not None:
                sys.modules["peer_transcript"] = saved


class HarnessMemoryTests(unittest.TestCase):
    def test_format_last_cycle_includes_noop_and_verify(self) -> None:
        state = {
            "last_cycle": {
                "ts": time.time(),
                "rc": 0,
                "verify_ok": True,
                "queue_fp": "aaa",
                "queue_fp_before": "aaa",
                "noop": True,
                "git_head": "deadbeef",
                "note": "stuck",
            }
        }
        text = pt.format_last_cycle_block(state)
        self.assertIn("## Last cycle", text)
        self.assertIn("Verify: ok", text)
        self.assertIn("Noop (same queue after ok): True", text)
        self.assertIn("Note: stuck", text)
        self.assertIn("did not advance the queue", text)

    def test_format_last_cycle_verify_fail_instruction(self) -> None:
        state = {
            "last_cycle": {
                "ts": time.time(),
                "rc": 1,
                "verify_ok": False,
                "queue_fp": "b",
                "queue_fp_before": "a",
                "noop": False,
                "git_head": "abc",
                "note": "",
            }
        }
        text = pt.format_last_cycle_block(state)
        self.assertIn("Verify: FAIL", text)
        self.assertIn("fix verify failures first", text)

    def test_format_last_cycle_deferred_soft_skip_in_hot_memory(self) -> None:
        """OVERSEER_LAND_DEFERRED_HOT_MEMORY_2026_09_03"""
        state = {
            "last_cycle": {
                "ts": time.time(),
                "rc": 0,
                "verify_ok": False,
                "failure_type": "deferred",
                "queue_fp": "c",
                "queue_fp_before": "c",
                "noop": False,
                "git_head": "def",
                "note": "verify deferred (swarm/lock)",
            }
        }
        text = pt.format_last_cycle_block(state)
        self.assertIn("Failure type: deferred", text)
        self.assertIn("deferred (soft-skip", text)
        self.assertIn("soft-skip only", text)
        self.assertNotIn("fix verify failures first", text)

    def test_format_trend_hint_present_and_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.md"
            self.assertEqual(pt.format_trend_hint(trends_path=missing), "")
            present = Path(tmp) / "AUTOMATION_TRENDS.md"
            present.write_text("# trends\n")
            hint = pt.format_trend_hint(trends_path=present)
            self.assertIn("notes/AUTOMATION_TRENDS.md", hint)

    def test_format_harness_memory_combines_cycle_and_trend(self) -> None:
        state = {
            "last_cycle": {
                "ts": time.time(),
                "rc": 0,
                "verify_ok": True,
                "queue_fp": "x",
                "queue_fp_before": "x",
                "noop": False,
                "git_head": "h",
                "note": "",
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            trends = Path(tmp) / "t.md"
            trends.write_text("ok")
            text = pt.format_harness_memory(state, trends_path=trends)
            self.assertIn("## Last cycle", text)
            self.assertIn("notes/AUTOMATION_TRENDS.md", text)

    def test_with_harness_memory_prefixes_peer_body(self) -> None:
        import cursor_self_improve as csi

        fake = "## Last cycle\n- Verify: ok\n- Trends: skim `notes/AUTOMATION_TRENDS.md`"
        with mock.patch.object(pt, "format_harness_memory", return_value=fake):
            out = csi._with_harness_memory("PEER BODY")
        self.assertTrue(out.startswith("## Last cycle"))
        self.assertIn("PEER BODY", out)
        with mock.patch.object(pt, "format_harness_memory", return_value=""):
            self.assertEqual(csi._with_harness_memory("PEER BODY"), "PEER BODY")



class StatePreserveTests(unittest.TestCase):
    """OVERSEER_STATE_SAVE_PRESERVE_LAST_CYCLE_2026_09_04 + LOAD_TIMEOUT_NO_WIPE."""

    def test_thin_save_preserves_disk_last_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "peer-loop-state.json"
            rich = {
                "last_cycle": {
                    "ts": time.time(),
                    "rc": 0,
                    "verify_ok": True,
                    "queue_fp": "keep-me",
                    "noop": False,
                    "note": "rich",
                },
                "cycle_history": [{"ts": 1, "verify_ok": True}],
                "last_delivery_ok_ts": 99.0,
            }
            state_path.write_text(
                __import__("json").dumps(rich, indent=2) + "\n", encoding="utf-8"
            )
            with mock.patch.object(pt, "STATE_PATH", state_path):
                thin = {"stall_reason": "noop_backoff", "stall_since_ts": time.time()}
                pt.save_state(thin)
                saved = __import__("json").loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved.get("stall_reason"), "noop_backoff")
            self.assertEqual(saved["last_cycle"]["queue_fp"], "keep-me")
            self.assertEqual(saved.get("last_delivery_ok_ts"), 99.0)

    def test_load_timeout_falls_back_to_unlocked_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "peer-loop-state.json"
            payload = {
                "last_cycle": {
                    "ts": time.time(),
                    "rc": 0,
                    "verify_ok": True,
                    "queue_fp": "unlocked",
                    "noop": False,
                }
            }
            state_path.write_text(
                __import__("json").dumps(payload) + "\n", encoding="utf-8"
            )

            @__import__("contextlib").contextmanager
            def boom(*, shared: bool = False, timeout_sec=None):  # noqa: ANN001
                raise TimeoutError("flock timeout")
                yield  # pragma: no cover

            with mock.patch.object(pt, "STATE_PATH", state_path):
                with mock.patch.object(pt, "_state_file_lock", boom):
                    loaded = pt.load_state()
            self.assertEqual(loaded["last_cycle"]["queue_fp"], "unlocked")


if __name__ == "__main__":
    unittest.main()
