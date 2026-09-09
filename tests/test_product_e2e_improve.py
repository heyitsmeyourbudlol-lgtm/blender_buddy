#!/usr/bin/env python3
"""Tests for product E2E improve gaps."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import product_e2e_improve as product_e2e  # noqa: E402


class ProductE2eImproveTests(unittest.TestCase):
    def test_opportunities_include_bootstrap_for_revenue_repo(self) -> None:
        registry = SCRIPTS.parent / "repos" / "registry.json"
        opps = product_e2e.product_e2e_opportunities(registry)
        self.assertGreaterEqual(len(opps), 5)
        titles = [o["title"] for o in opps]
        self.assertTrue(any("Bootstrap revenue/ship repo" in t for t in titles))

    def test_north_star_non_empty(self) -> None:
        self.assertIn("deploy proof", product_e2e.PRODUCT_E2E_NORTH_STAR)


if __name__ == "__main__":
    unittest.main()
