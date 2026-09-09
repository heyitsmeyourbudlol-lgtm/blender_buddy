"""Scrub legacy tracked automation.config.json dirt before pool align."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import peer_pool_scrub as scrub  # noqa: E402


class ScrubPoolTrackedConfigDirtTests(unittest.TestCase):
    def test_scrubs_tracked_config_and_parks_ns_in_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            slot = Path(tmp) / "peer-0"
            slot.mkdir()
            (slot / "automation.config.json").write_text(
                json.dumps({"config_namespace": "peer-0", "x": 1}) + "\n"
            )
            calls: list[tuple[tuple[str, ...], str]] = []

            def fake_run(argv, cwd):  # type: ignore[no-untyped-def]
                calls.append((tuple(argv), str(cwd)))
                if argv[:3] == ("git", "status", "--porcelain"):
                    return subprocess.CompletedProcess(
                        argv, 0, " M automation.config.json\n", ""
                    )
                if argv[:3] == ("git", "checkout", "--"):
                    # Simulate restore to hub-ish tracked file.
                    Path(cwd, "automation.config.json").write_text(
                        json.dumps({"config_namespace": "automation-hub"}) + "\n"
                    )
                    return subprocess.CompletedProcess(argv, 0, "", "")
                return subprocess.CompletedProcess(argv, 1, "", "unexpected")

            out = scrub.scrub_pool_tracked_config_dirt([slot], runner=fake_run)
            self.assertEqual(out, ["peer-0"])
            local = json.loads((slot / "automation.config.local.json").read_text())
            self.assertEqual(local["config_namespace"], "peer-0")
            tracked = json.loads((slot / "automation.config.json").read_text())
            self.assertEqual(tracked["config_namespace"], "automation-hub")
            self.assertTrue(
                any(c[0][:3] == ("git", "checkout", "--") for c in calls)
            )

    def test_skips_when_tracked_config_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            slot = Path(tmp) / "peer-1"
            slot.mkdir()
            (slot / "automation.config.json").write_text("{}\n")

            def fake_run(argv, cwd):  # type: ignore[no-untyped-def]
                if argv[:3] == ("git", "status", "--porcelain"):
                    return subprocess.CompletedProcess(argv, 0, "", "")
                return subprocess.CompletedProcess(argv, 1, "", "unexpected")

            self.assertEqual(
                scrub.scrub_pool_tracked_config_dirt([slot], runner=fake_run),
                [],
            )


if __name__ == "__main__":
    unittest.main()
