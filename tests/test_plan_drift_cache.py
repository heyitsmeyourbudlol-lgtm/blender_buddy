#!/usr/bin/env python3
"""Tests for plan drift cache skip."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import plan_drift_cache as pdc  # noqa: E402


class PlanDriftCacheTests(unittest.TestCase):
    def test_skip_after_record(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            with mock.patch.object(pdc, "_state_dir", return_value=tdir):
                ctx, wq = "ctx", "wq"
                self.assertFalse(pdc.should_skip_drift_sync(context_md=ctx, work_md=wq))
                pdc.record_drift_sync(context_md=ctx, work_md=wq)
                self.assertTrue(pdc.should_skip_drift_sync(context_md=ctx, work_md=wq))


if __name__ == "__main__":
    unittest.main()
