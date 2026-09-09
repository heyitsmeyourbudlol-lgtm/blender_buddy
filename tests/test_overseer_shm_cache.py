"""OVERSEER_SHM_BALLAST_CAP + OVERSEER_ATOMIC_CACHE_WRITE (2026-09-04)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402


class AutomationCachePersistTests(unittest.TestCase):
    def test_compact_git_fingerprint_hashes_large_body(self) -> None:
        self.assertEqual(auto._compact_git_fingerprint("abc:short"), "abc:short")
        compact = auto._compact_git_fingerprint("abc:" + ("x" * 2000))
        self.assertTrue(compact.startswith("abc:sha256:"))
        self.assertEqual(len(compact.split(":", 2)[-1]), 64)

    def test_save_cache_atomic_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-cache-") as tmp:
            path = Path(tmp) / "automation_cache.json"
            with unittest.mock.patch.object(auto, "CACHE_PATH", path):
                auto._CACHE_MEM = None
                auto._CACHE_MEM_MTIME_NS = None
                auto._CACHE_MEM_TEXT = None
                auto._save_cache({"tests_ok": True, "tests_detail": "tests: smoke ok"})
                self.assertTrue(path.is_file())
                self.assertTrue(json.loads(path.read_text())["tests_ok"])
                path.write_text("{not-json")
                self.assertEqual(auto._load_cache(), {})
                self.assertFalse(path.is_file())


class ShmBallastCapTests(unittest.TestCase):
    def test_min_pinned_clamped_to_shm_capacity(self) -> None:
        import dgx_ram_fill as fill

        with unittest.mock.patch.object(
            fill, "_fill_cfg", return_value={"min_pinned_shm_gb": 92}
        ), unittest.mock.patch.object(fill, "_shm_capacity_gb", return_value=61.0):
            self.assertAlmostEqual(fill.min_pinned_shm_gb(), 59.0)


if __name__ == "__main__":
    unittest.main()
