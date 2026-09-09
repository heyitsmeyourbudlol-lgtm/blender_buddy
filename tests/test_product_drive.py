"""Tests for product_drive — always ship external proof."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import product_drive as pdrive  # noqa: E402


class ProductDriveTests(unittest.TestCase):
    def test_prioritize_product_first(self) -> None:
        items = [
            "**[comms-improve] Prune bus**",
            "**[product] External proof: CPT** — adapt",
            "**[dgx-speed] Hot path**",
        ]
        out = pdrive.prioritize_product_items(items)
        self.assertIn("product", out[0].lower())

    def test_is_product_item(self) -> None:
        self.assertTrue(pdrive.is_product_item("[product] External proof: Newdrop"))
        self.assertFalse(pdrive.is_product_item("[comms-improve] GibberLink docs"))

    def test_registry_targets_exclude_hub(self) -> None:
        names = [str(r.get("name") or "") for r in pdrive.registry_product_targets(limit=5)]
        self.assertNotIn("Automation Hub", names)
        self.assertTrue(names)


if __name__ == "__main__":
    unittest.main()
