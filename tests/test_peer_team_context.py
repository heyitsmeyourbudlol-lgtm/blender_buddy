#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import peer_team_context as tc


def _seed_team_context_disk(*, stamp: bool = True) -> tc.TeamContextBundle:
    """Write minimal MD+JSON without full build_team_context (hub learning JSONL OOMs)."""
    bundle = tc.TeamContextBundle(
        as_of=time.time(),
        sections={
            "build_mode": "- factory_meter_mode: `self_sufficient`",
            "factory": "- Readiness: **99%**",
            "last_cycle": "- Verify: ok",
            "live": "- git: clean",
            "queue": "- open: 1",
            "assignments": "- none",
        },
    )
    tc.TEAM_CONTEXT_MD.parent.mkdir(parents=True, exist_ok=True)
    tc.TEAM_CONTEXT_MD.write_text(bundle.markdown(), encoding="utf-8")
    tc.TEAM_CONTEXT_JSON.parent.mkdir(parents=True, exist_ok=True)
    tc.TEAM_CONTEXT_JSON.write_text(json.dumps(bundle.to_dict(), indent=2) + "\n", encoding="utf-8")
    if stamp:
        tc._stamp_team_context_write()
    else:
        tc.clear_team_context_write_stamp()
    return bundle


class TestPeerTeamContext(unittest.TestCase):
    def test_shared_reads_include_canon_docs(self):
        paths = tc.shared_read_paths()
        self.assertIn("notes/TEAM_CONTEXT.md", paths)

    def test_from_dict_roundtrip(self):
        raw = {
            "as_of": 1.5,
            "sections": {"build_mode": "x"},
            "assignments": [{"task": "t"}],
        }
        b = tc.TeamContextBundle.from_dict(raw)
        self.assertEqual(b.as_of, 1.5)
        self.assertEqual(b.sections["build_mode"], "x")
        self.assertEqual(b.assignments[0]["task"], "t")

    def test_write_team_context_ttl_skips_fresh(self):
        fake = _seed_team_context_disk()
        path = tc.TEAM_CONTEXT_MD
        path.touch()
        m = path.stat().st_mtime
        with mock.patch.object(tc, "build_team_context", return_value=fake) as build:
            out = tc.write_team_context()
        build.assert_not_called()
        self.assertEqual(out, path)
        self.assertEqual(path.stat().st_mtime, m)

    def test_write_team_context_force_rebuilds(self):
        fake = _seed_team_context_disk()
        with mock.patch.object(tc, "build_team_context", return_value=fake) as build:
            tc.write_team_context(force=True)
        build.assert_called_once()

    def test_write_team_context_generation_skips_past_wall_ttl(self):
        """TEAM_CONTEXT_GENERATION_ONLY_2026_09_05 — same input key ignores wall age."""
        tc.clear_team_context_write_stamp()
        fake = _seed_team_context_disk(stamp=True)
        path = tc.TEAM_CONTEXT_MD
        stale = time.time() - tc.TEAM_CONTEXT_WRITE_TTL_SEC - 5.0
        os.utime(path, (stale, stale))
        with mock.patch.object(tc, "build_team_context", return_value=fake) as build:
            out = tc.write_team_context()
        build.assert_not_called()
        self.assertEqual(out, path)

    def test_write_team_context_generation_remiss_when_key_changes(self):
        tc.clear_team_context_write_stamp()
        _seed_team_context_disk(stamp=True)
        stale = time.time() - tc.TEAM_CONTEXT_WRITE_TTL_SEC - 5.0
        os.utime(tc.TEAM_CONTEXT_MD, (stale, stale))
        key = tc._team_context_input_key()
        changed = (key[0] + 1, key[1], key[2])
        fake = tc.TeamContextBundle(
            as_of=time.time(),
            sections={"build_mode": "- factory_meter_mode: `gen`"},
        )
        with mock.patch.object(tc, "_team_context_input_key", return_value=changed):
            with mock.patch.object(tc, "build_team_context", return_value=fake) as build:
                tc.write_team_context()
        build.assert_called_once()

    def test_format_team_snapshot_reuses_fresh_json(self):
        _seed_team_context_disk(stamp=True)
        with mock.patch.object(tc, "build_team_context") as build:
            text = tc.format_team_snapshot(max_chars=2500)
        build.assert_not_called()
        self.assertIn("Team snapshot", text)

    def test_format_team_snapshot_reuses_json_past_wall_ttl(self):
        """EFFICIENCY_SNAPSHOT_JSON_GENERATION_2026_09_07 — stamp ignores wall age."""
        tc.clear_team_context_write_stamp()
        _seed_team_context_disk(stamp=True)
        json_mtime = float(tc.TEAM_CONTEXT_JSON.stat().st_mtime)
        with mock.patch.object(
            tc.time, "time", return_value=json_mtime + tc.TEAM_CONTEXT_WRITE_TTL_SEC + 10.0
        ):
            with mock.patch.object(tc, "build_team_context") as build:
                text = tc.format_team_snapshot(max_chars=2500)
        build.assert_not_called()
        self.assertIn("Team snapshot", text)

    def test_format_team_snapshot_reuses_json_past_wall_ttl_cold(self):
        """Cold process: disk generation (json_mtime_ns >= max(key)) ignores wall age."""
        tc.clear_team_context_write_stamp()
        _seed_team_context_disk(stamp=False)
        json_mtime = float(tc.TEAM_CONTEXT_JSON.stat().st_mtime)
        # Pin input key below JSON mtime so concurrent WQ remiss cannot defeat disk HIT.
        cold_key = (1, 1, 1)
        with mock.patch.object(tc, "_team_context_input_key", return_value=cold_key):
            with mock.patch.object(
                tc.time, "time", return_value=json_mtime + tc.TEAM_CONTEXT_WRITE_TTL_SEC + 10.0
            ):
                with mock.patch.object(tc, "build_team_context") as build:
                    text = tc.format_team_snapshot(max_chars=2500)
        build.assert_not_called()
        self.assertIn("Team snapshot", text)

    def test_format_team_snapshot_rebuilds_when_generation_changes(self):
        tc.clear_team_context_write_stamp()
        _seed_team_context_disk(stamp=False)
        json_mtime = float(tc.TEAM_CONTEXT_JSON.stat().st_mtime)
        key = tc._team_context_input_key()
        changed = (int(tc.TEAM_CONTEXT_JSON.stat().st_mtime_ns) + 10**12, key[1], key[2])
        fake = tc.TeamContextBundle(
            as_of=time.time(),
            sections={"build_mode": "- factory_meter_mode: `test`"},
        )
        with mock.patch.object(
            tc.time, "time", return_value=json_mtime + tc.TEAM_CONTEXT_WRITE_TTL_SEC + 10.0
        ):
            with mock.patch.object(tc, "_team_context_input_key", return_value=changed):
                with mock.patch.object(
                    tc, "build_team_snapshot_context", return_value=fake
                ) as build:
                    with mock.patch.object(tc, "build_team_context") as full:
                        text = tc.format_team_snapshot(max_chars=800)
        build.assert_called_once()
        full.assert_not_called()
        self.assertIn("Team snapshot", text)
        self.assertIn("factory_meter_mode", text)

    def test_format_team_snapshot_ops_only_skips_full_build(self):
        """EFFICIENCY_SNAPSHOT_OPS_ONLY — miss path must not call build_team_context."""
        self.assertIn(
            "EFFICIENCY_SNAPSHOT_OPS_ONLY_2026_09_08",
            Path(tc.__file__).read_text(encoding="utf-8"),
        )
        tc.clear_team_context_write_stamp()
        if tc.TEAM_CONTEXT_JSON.is_file():
            tc.TEAM_CONTEXT_JSON.unlink()
        with mock.patch.object(tc, "build_team_context") as full:
            text = tc.format_team_snapshot(max_chars=2500)
        full.assert_not_called()
        self.assertIn("Team snapshot", text)
        self.assertIn("factory_meter_mode", text)

    def test_snapshot_ops_miss_skips_scan_and_transcript(self) -> None:
        """SNAPSHOT_FACTORY_SKIP_SCAN + SNAPSHOT_LAST_CYCLE_NO_TRANSCRIPT."""
        src = Path(tc.__file__).read_text(encoding="utf-8")
        self.assertIn("SNAPSHOT_FACTORY_SKIP_SCAN_2026_09_08", src)
        self.assertIn("SNAPSHOT_LAST_CYCLE_NO_TRANSCRIPT_2026_09_08", src)
        self.assertIn("_factory_progress_for_snapshot", src)
        self.assertIn("_format_last_cycle_block_light", src)

        import factory_progress as fp
        import peer_self_heal as heal

        fp.clear_factory_progress_cache()
        if hasattr(heal, "clear_scan_bottlenecks_cache"):
            heal.clear_scan_bottlenecks_cache()
        sys.modules.pop("peer_transcript", None)
        scan_calls = {"n": 0}
        real_scan = heal.scan_bottlenecks

        def counting_scan(*args, **kwargs):
            scan_calls["n"] += 1
            return real_scan(*args, **kwargs)

        with mock.patch.object(heal, "scan_bottlenecks", side_effect=counting_scan):
            bundle = tc.build_team_snapshot_context()
        self.assertEqual(scan_calls["n"], 0, "ops snapshot miss must not scan_bottlenecks")
        self.assertNotIn("peer_transcript", sys.modules)
        self.assertIn("factory", bundle.sections)
        self.assertIn("Readiness:", bundle.sections["factory"])


if __name__ == "__main__":
    unittest.main()
