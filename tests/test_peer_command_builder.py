#!/usr/bin/env python3
"""Tests for Command Builder probe + prompt."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_command_builder as cb  # noqa: E402
import peer_commands as pc  # noqa: E402


class TestPeerCommandBuilder(unittest.TestCase):
    def test_log_tail_seeks_end_not_full_read(self) -> None:
        """Large logs must not be fully decoded — seek last max_bytes only."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big.log"
            # 256 KiB of lines — full read_text would load all; seek reads end.
            line = b"x" * 127 + b"\n"
            path.write_bytes(line * 2048)
            with mock.patch.object(Path, "read_text", side_effect=AssertionError("no full read")):
                text = cb._log_tail(path, max_bytes=4096)
            self.assertTrue(text)
            self.assertLessEqual(len(text.encode("utf-8")), 4096)
            self.assertIn("x", text)

    def test_new_compounds_registered(self) -> None:
        for cmd_id in ("commands-sync", "dev-fast", "dev-heal"):
            self.assertIn(cmd_id, pc.COMPOUND_STEPS)

    def test_commands_sync_steps(self) -> None:
        self.assertEqual(pc.COMPOUND_STEPS["commands-sync"], ["commands-md", "check"])

    def test_write_digest(self) -> None:
        path = cb.write_digest(gaps=[])
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("Command Builder", text)
        self.assertIn("commands-sync", text)

    def test_build_prompt_scoped(self) -> None:
        prompt = cb.build_prompt(gaps=[])
        self.assertIn("peer_commands.py", prompt)
        self.assertIn("commands-sync", prompt)
        self.assertIn("Do not touch peer_loop", prompt)


if __name__ == "__main__":
    unittest.main()
