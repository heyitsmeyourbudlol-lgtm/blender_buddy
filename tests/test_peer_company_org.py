"""Tests for company org gap audit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import peer_company_org as org  # noqa: E402
import peer_critical_thinking as ct  # noqa: E402


class CompanyOrgTests(unittest.TestCase):
    def test_catalog_has_departments(self) -> None:
        depts = {r.department for r in org.COMPANY_ROLES}
        self.assertIn("Engineering", depts)
        self.assertIn("Product", depts)
        self.assertIn("GTM", depts)
        self.assertGreaterEqual(len(org.COMPANY_ROLES), 20)

    def test_audit_zero_missing_after_staff(self) -> None:
        report = org.audit()
        self.assertEqual(report.missing, [], [r.role_id for r in report.missing])
        self.assertGreaterEqual(len(report.present), 20)
        self.assertIn("progress_monitor", report.present)

    def test_plan_execute_mandate(self) -> None:
        self.assertIn("numbered", ct.PLAN_EXECUTE_MANDATE.lower())
        self.assertIn("numbered", ct.PLAN_GATE.lower())


if __name__ == "__main__":
    unittest.main()
