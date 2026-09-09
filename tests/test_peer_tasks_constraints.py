#!/usr/bin/env python3
"""peer_tasks product_constraints must not storm past pool cap."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PeerTasksConstraintsTests(unittest.TestCase):
    def test_product_constraints_no_target_48(self) -> None:
        data = json.loads((ROOT / "scripts" / "peer_tasks.json").read_text(encoding="utf-8"))
        pcs = data.get("product_constraints") or []
        joined = "\n".join(str(x) for x in pcs)
        self.assertNotIn("target 48 workers", joined)
        self.assertTrue(
            any("max_parallel_peers" in str(x) for x in pcs),
            "expected max_parallel_peers clamp language in product_constraints",
        )


if __name__ == "__main__":
    unittest.main()
