"""OVERSEER_CLOSE_LANDED_DONE_2026_09_04 — check landed Done opens in-place."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import project_automation as auto  # noqa: E402


class CloseLandedDoneOrphansTests(unittest.TestCase):
    def test_checks_proof_green_leaves_unknown(self) -> None:
        md = (
            "## Active\n"
            "- [x] **keep** — already done\n"
            "## Done\n"
            "- [ ] **[flaw-research] mark_local_verify on deferred arms cooldown → auto-commit theater** — "
            "should close when peer_loop land needle present\n"
            "- [ ] **[flaw-research] unknown unfinished under Done** — stay open for promote\n"
        )
        new_md, n = auto.close_landed_done_orphans(md)
        self.assertEqual(n, 1)
        self.assertIn(
            "- [x] **[flaw-research] mark_local_verify on deferred arms cooldown",
            new_md,
        )
        self.assertIn(
            "- [ ] **[flaw-research] unknown unfinished under Done**",
            new_md,
        )
        orphans = auto.open_done_orphan_items(new_md)
        self.assertEqual(len(orphans), 1)
        self.assertIn("unknown unfinished", orphans[0])

    def test_compact_wires_close_before_promote(self) -> None:
        src = (ROOT / "scripts" / "project_automation.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_CLOSE_LANDED_DONE_2026_09_04", src)
        self.assertIn("landed_closed = close_landed_done_orphans", src)
        close_at = src.find("landed_closed = close_landed_done_orphans")
        promote_at = src.find("promoted = promote_open_done_orphans", close_at)
        self.assertGreater(promote_at, close_at)



    def test_closes_repo_flaw_hub_protect_and_false_eval_repoison(self) -> None:
        """OVERSEER_CLOSE_REPO_FLAW_HUB_PROTECT_2026_09_04 + FALSE_EVAL_REPOISON."""
        md = (
            "## Active\n"
            "- [ ] **[flaw-research] REPO_FLAW_RESEARCH.md missing from HUB_PROTECT_PULL_EXCLUDES** — add\n"
            "- [ ] **[flaw-research] Stale peer worktrees re-poison false eval() flaws** — peer DIFF\n"
            "- [ ] **[kit] Stall-watch: keep Active queue non-empty under self_sufficient** — seed\n"
            "- [ ] **[kit] Stall-watch: refill Active when only deferred external_proof remains** — seed\n"
            "- [ ] **[kit] Stall-watch: Active seed on empty under self_sufficient** — when\n"
            "- [ ] **[kit] Stall-watch: prevent IDLE empty Active under self_sufficient** — when\n"
            "- [ ] **[flaw-research] unknown unfinished** — stay open\n"
        )
        new_md, n = auto.close_landed_done_orphans(md)
        self.assertEqual(n, 6)
        self.assertIn("- [x] **[flaw-research] REPO_FLAW_RESEARCH.md missing from HUB_PROTECT", new_md)
        self.assertIn("- [x] **[flaw-research] Stale peer worktrees re-poison false eval", new_md)
        self.assertIn("- [x] **[kit] Stall-watch: keep Active queue non-empty", new_md)
        self.assertIn("- [x] **[kit] Stall-watch: refill Active when only deferred", new_md)
        self.assertIn("- [x] **[kit] Stall-watch: Active seed on empty under self_sufficient", new_md)
        self.assertIn("- [x] **[kit] Stall-watch: prevent IDLE empty Active under self_sufficient", new_md)
        self.assertIn("- [ ] **[flaw-research] unknown unfinished**", new_md)

    def test_active_close_landed_needle_in_source(self) -> None:
        src = (ROOT / "scripts" / "project_automation.py").read_text(encoding="utf-8")
        self.assertIn("OVERSEER_ACTIVE_OPEN_CLOSE_LANDED_2026_09_04", src)
        self.assertIn("keep Active queue non-empty under self_sufficient", src)
        self.assertIn("refill Active when only deferred external_proof", src)
        self.assertIn("Active seed on empty under self_sufficient", src)
        self.assertIn("prevent IDLE empty Active under self_sufficient", src)
        self.assertIn("OVERSEER_LAND_PROOF_REFILL_ACTIVE_KIT_2026_09_04", src)
        self.assertIn("OVERSEER_LAND_PROOF_ACTIVE_SEED_EMPTY_2026_09_04", src)
        self.assertIn("OVERSEER_LAND_PROOF_IDLE_EMPTY_ACTIVE_2026_09_04", src)


if __name__ == "__main__":
    unittest.main()
