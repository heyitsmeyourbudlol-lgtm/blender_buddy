"""Alias smoke for compression_train_profile → gpu_profile_once."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compression_train_profile as ctp  # noqa: E402


class CompressionTrainProfileAliasTests(unittest.TestCase):
    def test_needle_and_delegate(self) -> None:
        self.assertEqual(ctp.NEEDLE, "OVERSEER_GPU_PROFILE_ONCE_2026_09_05")
        self.assertTrue(callable(ctp.main))


if __name__ == "__main__":
    unittest.main()
