"""compact-queue closes Mac-rsync theater via land-proof mark script."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load_mark():
    path = SCRIPTS / "_mark_flaw_research_landed.py"
    spec = importlib.util.spec_from_file_location("_mark_flaw_research_landed", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CompactLandProofTests(unittest.TestCase):
    def test_stall_adapt_ttl_proof_green(self) -> None:
        mark = _load_mark()
        self.assertTrue(mark._land_proof("stall_adapt_ttl"))

    def test_deferred_poison_scrub_on_load_proof_green(self) -> None:
        mark = _load_mark()
        self.assertTrue(mark._land_proof("deferred_poison"))

    def test_compact_queue_invokes_land_proof_mark(self) -> None:
        import peer_commands as pc

        with (
            mock.patch.object(
                pc.auto,
                "compact_executable_queue",
                return_value=(0, ["dedupe"]),
            ),
            mock.patch.object(
                pc.auto,
                "open_work_items",
                return_value=mock.Mock(open_items=[]),
            ),
            mock.patch.object(
                pc,
                "_run_land_proof_mark",
                return_value="land-proof-mark=2 open_needles=0",
            ) as mark_fn,
        ):
            rc, msg = pc._compact_queue_inner()
        self.assertEqual(rc, 0)
        self.assertIn("open=", msg)
        self.assertIn("land-proof-mark=2", msg)
        mark_fn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
