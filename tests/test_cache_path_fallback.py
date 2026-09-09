"""Unwritable automation_cache_dir (e.g. macOS /dev/shm) must fall back."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402


class CachePathFallbackTests(unittest.TestCase):
    def tearDown(self) -> None:
        auto.reset_cache_path_resolution()

    def test_unwritable_custom_falls_back_to_config_dir(self) -> None:
        missing = Path("/dev/shm/automation-cache-nonexistent-peer5/state")
        with mock.patch.dict(auto.os.environ, {"AUTOMATION_CACHE_DIR": str(missing)}, clear=False):
            auto._cache_path_resolved = None
            path = auto.cache_path()
        self.assertEqual(path, auto.CONFIG_DIR / "automation_cache.json")
        self.assertEqual(auto.CACHE_PATH, path)

    def test_writable_custom_preferred(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-cache-ok-") as tmp:
            with mock.patch.dict(auto.os.environ, {"AUTOMATION_CACHE_DIR": tmp}, clear=False):
                auto._cache_path_resolved = None
                path = auto.cache_path()
            self.assertEqual(path, Path(tmp) / "automation_cache.json")
            self.assertTrue(path.parent.is_dir())


if __name__ == "__main__":
    unittest.main()
