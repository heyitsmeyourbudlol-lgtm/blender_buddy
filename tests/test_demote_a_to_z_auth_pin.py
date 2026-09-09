"""OVERSEER_DEMOTE_A_TO_Z_AUTH_PIN_2026_09_07 — red sequencing-lock Active demotes."""

from __future__ import annotations

import unittest

from project_automation import (
    demote_human_auth_blocked_active,
    demote_kit_theater_active,
    is_human_auth_blocked_item,
    is_kit_theater_active_item,
)


class DemoteAToZAuthPinTests(unittest.TestCase):
    def test_sequencing_lock_red_is_human_auth_blocked(self) -> None:
        item = (
            "[a-to-z] Factory A→Z sequencing lock — red until real PR/merge_note; "
            "do not jump ladder — OVERSEER_NO_JUMP_UNTIL_A_TO_Z_2026_09_07"
        )
        self.assertTrue(is_human_auth_blocked_item(item))

    def test_unrelated_a_to_z_not_blocked(self) -> None:
        item = "[a-to-z:phase3] Second registry target A→E — Doc2Api on CLEAN"
        self.assertFalse(is_human_auth_blocked_item(item))

    def test_demote_moves_active_to_creative(self) -> None:
        work = (
            "## Active\n"
            "- [ ] **[a-to-z] Factory A→Z sequencing lock** — red until real PR/merge_note; "
            "do not jump ladder — OVERSEER_NO_JUMP_UNTIL_A_TO_Z_2026_09_07\n"
            "\n"
            "## Creative backlog\n"
            "- [ ] **[a-to-z:phase4] Stamp green lock** — blocked: push_auth_missing "
            "on CLEAN (no SSH/gh) — demoted human-auth block · "
            "OVERSEER_DEMOTE_HUMAN_AUTH_BLOCK_2026_09_07\n"
        )
        ctx = work
        new_w, new_c, n = demote_human_auth_blocked_active(work, ctx)
        self.assertGreaterEqual(n, 1)
        self.assertNotIn("- [ ] **[a-to-z] Factory A→Z sequencing lock**", new_w.split("## Creative")[0])
        self.assertIn("sequencing lock", new_w.lower())
        self.assertIn("OVERSEER_DEMOTE_HUMAN_AUTH_BLOCK_2026_09_07", new_w)
        # Creative section holds the demoted open line
        cre = new_w.split("## Creative backlog", 1)[1]
        self.assertIn("- [ ] **[a-to-z] Factory A→Z sequencing lock**", cre)
        self.assertIn("sequencing lock", new_c.lower())

    def test_push_deferred_empty_git_credentials_is_blocked(self) -> None:
        """OVERSEER_DEMOTE_PUSH_DEFERRED_2026_09_08"""
        item = (
            "[top10] Newdrop production — Hard-Fix #66 Soft residual (kill switches) — "
            "file-scoped `/home/arnavrastogi/CaaS` (CLEAN mirror; Mac `/Users/togi/CaaS` "
            "missing; push deferred — empty git-credentials / no gh; "
            "OVERSEER_MAC_PATH_HOME_MIRROR_2026_09_08)"
        )
        self.assertTrue(is_human_auth_blocked_item(item))
        follow = (
            "[top10] Newdrop #66 Soft — push/PR when CLEAN git creds restored — "
            "local 95c1a617"
        )
        self.assertTrue(is_human_auth_blocked_item(follow))
        work = f"## Active\n- [ ] **{item}**\n\n## Creative backlog\n"
        new_w, _new_c, n = demote_human_auth_blocked_active(work, work)
        self.assertGreaterEqual(n, 1)
        self.assertIn("OVERSEER_DEMOTE_HUMAN_AUTH_BLOCK_2026_09_07", new_w)
        self.assertNotIn("- [ ] **[top10]", new_w.split("## Creative")[0])

    def test_soft_soft_land_ok_exempt_despite_push_blocked(self) -> None:
        """OVERSEER_SOFT_SOFT_LAND_OK_EXEMPT_2026_09_08"""
        soft = (
            "[top10] Newdrop tip-cover after #177 — next meaningful non-UI merge; "
            "push blocked (`gh` missing / git-credentials 0B) — Soft Soft-land OK; "
            "PR when CLEAN git auth · NO PAY"
        )
        self.assertFalse(is_human_auth_blocked_item(soft))
        blocked_only = (
            "[top10] Newdrop Soft push — push blocked (`gh` missing / "
            "git-credentials 0B) · NO PAY"
        )
        self.assertTrue(is_human_auth_blocked_item(blocked_only))

    def test_remaining_soft_push_stripped_from_both_twins(self) -> None:
        """OVERSEER_DEMOTE_REMAINING_BOTH_TWINS_2026_09_08 — WQ Remaining Soft-push."""
        soft = (
            "- [ ] **[top10] Newdrop Soft push/PR when CLEAN git creds restored** — "
            "Soft lands on `peer/external-proof-caas`: #73 `1d65b779`; open PR + merge · "
            "OVERSEER_DEMOTE_PUSH_DEFERRED_2026_09_08 · NO PAY — demoted human-auth block "
            "(Active→Creative; do not re-promote) · OVERSEER_DEMOTE_HUMAN_AUTH_BLOCK_2026_09_07"
        )
        work = (
            "## Active\n"
            "- [ ] **[top10] Newdrop production — Hard-Fix #82 Soft residual** — docs only\n"
            "\n"
            "## Remaining work (priority order)\n"
            f"{soft}\n"
            "\n"
            "## Creative backlog\n"
            f"{soft}\n"
        )
        ctx = work
        new_w, new_c, n = demote_human_auth_blocked_active(work, ctx)
        self.assertGreaterEqual(n, 1)
        # Remaining open Soft-push gone from both twins
        rem_w = new_w.split("## Remaining work", 1)[1].split("## Creative", 1)[0]
        rem_c = new_c.split("## Remaining work", 1)[1].split("## Creative", 1)[0]
        self.assertNotIn("- [ ] **[top10] Newdrop Soft push", rem_w)
        self.assertNotIn("- [ ] **[top10] Newdrop Soft push", rem_c)
        # Creative still holds demoted open
        self.assertIn("Soft push/PR when CLEAN git creds", new_w.split("## Creative backlog", 1)[1])

    def test_comms_improve_is_kit_theater(self) -> None:
        """OVERSEER_DEMOTE_KIT_THEATER_ACTIVE_2026_09_08"""
        item = (
            "[comms-improve] [comms] Structured file bus (GLink) vs English — "
            "Extend GLink schema"
        )
        self.assertTrue(is_kit_theater_active_item(item))
        self.assertFalse(is_kit_theater_active_item("[factory] Kit-run twenty-fifth"))

    def test_demote_kit_theater_moves_active_to_creative(self) -> None:
        """OVERSEER_DEMOTE_KIT_THEATER_ACTIVE_2026_09_08 — Active→Creative."""
        work = (
            "## Active\n"
            "- [ ] **[comms-improve] [comms] Structured file bus (GLink) vs English** — "
            "Extend GLink schema\n"
            "- [ ] **[factory] Kit-run twenty-fifth registry target** — next Mac residual\n"
            "\n"
            "## Creative backlog\n"
        )
        new_w, new_c, n = demote_kit_theater_active(work, work)
        self.assertGreaterEqual(n, 1)
        active = new_w.split("## Creative backlog", 1)[0]
        self.assertNotIn("- [ ] **[comms-improve]", active)
        self.assertIn("- [ ] **[factory] Kit-run twenty-fifth", active)
        cre = new_w.split("## Creative backlog", 1)[1]
        self.assertIn("[comms-improve]", cre)
        self.assertIn("OVERSEER_DEMOTE_KIT_THEATER_ACTIVE_2026_09_08", cre)
        self.assertIn("[comms-improve]", new_c)


if __name__ == "__main__":
    unittest.main()
