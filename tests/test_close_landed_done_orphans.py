"""OVERSEER_CLOSE_LANDED_DONE_2026_09_04 — check landed Done opens in-place."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

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
            "- [ ] **[flaw-research] unknown unfinished** — stay open\n"
        )
        new_md, n = auto.close_landed_done_orphans(md)
        self.assertEqual(n, 2)
        self.assertIn("- [x] **[flaw-research] REPO_FLAW_RESEARCH.md missing from HUB_PROTECT", new_md)
        self.assertIn("- [x] **[flaw-research] Stale peer worktrees re-poison false eval", new_md)
        self.assertIn("- [ ] **[flaw-research] unknown unfinished**", new_md)


    def test_closes_kit_run_tenth_when_receipt_exists(self) -> None:
        """OVERSEER_CLOSE_KIT_RUN_RECEIPT_2026_09_08 — receipt beats peer reopen."""
        receipt = ROOT / "notes" / "KIT_A_TO_Z_TENTH_TARGET.md"
        self.assertTrue(receipt.is_file(), "tenth receipt must exist for live close")
        md = (
            "## Active\n"
            "- [ ] **[factory] Kit-run tenth registry target** — pick next repos/registry.json "
            "target with .git on CLEAN; prefer residual RAM reaffirm; NO PAY\n"
            "- [ ] **[top10] TOP10_NEXT T10-04 non-noop ≥8/day** — keep open\n"
        )
        new_md, n = auto.close_landed_done_orphans(md)
        self.assertEqual(n, 1)
        self.assertIn("- [x] **[factory] Kit-run tenth registry target**", new_md)
        self.assertIn("KIT_A_TO_Z_TENTH_TARGET.md", new_md)
        self.assertIn("- [ ] **[top10] TOP10_NEXT T10-04", new_md)
        self.assertNotIn("- [ ] **[factory] Kit-run tenth", new_md)

    def test_closes_kit_run_twelfth_when_receipt_exists(self) -> None:
        """OVERSEER_KIT_RUN_ORDINAL_THIRTEENTH_PLUS_2026_09_08 — twelfth still maps."""
        receipt = ROOT / "notes" / "KIT_A_TO_Z_TWELFTH_TARGET.md"
        self.assertTrue(receipt.is_file(), "twelfth receipt must exist for live close")
        md = (
            "## Active\n"
            "- [ ] **[factory] Kit-run twelfth registry target** — Marketplace seed; NO PAY\n"
            "- [ ] **[top10] TOP10_NEXT T10-04 non-noop ≥8/day** — keep open\n"
        )
        new_md, n = auto.close_landed_done_orphans(md)
        self.assertEqual(n, 1)
        self.assertIn("- [x] **[factory] Kit-run twelfth registry target**", new_md)
        self.assertIn("KIT_A_TO_Z_TWELFTH_TARGET.md", new_md)
        self.assertNotIn("- [ ] **[factory] Kit-run twelfth", new_md)

    def test_kit_run_thirteenth_ordinal_parses(self) -> None:
        """Ordinal map must recognize thirteenth+ (auto-close when receipt lands)."""
        item = (
            "- [ ] **[factory] Kit-run thirteenth registry target** — "
            "SaaS Health Dashboard; NO PAY"
        )
        self.assertEqual(auto._kit_run_ordinal_from_item(item), 13)
        self.assertEqual(auto._KIT_RUN_ORDINAL_WORDS.get("thirteenth"), 13)
        self.assertEqual(auto._KIT_RUN_ORDINAL_WORDS.get("twentieth"), 20)

    def test_kit_run_twenty_first_ordinal_and_receipt_path(self) -> None:
        """OVERSEER_KIT_RUN_ORDINAL_TWENTY_FIRST_PLUS_2026_09_08."""
        item = (
            "- [ ] **[factory] Kit-run twenty-first registry target** — "
            "freesurfsharkone; NO PAY"
        )
        self.assertEqual(auto._kit_run_ordinal_from_item(item), 21)
        self.assertEqual(auto._KIT_RUN_ORDINAL_WORDS.get("twenty-first"), 21)
        self.assertEqual(auto._KIT_RUN_ORDINAL_WORDS.get("twenty-fifth"), 25)
        path = auto._kit_run_receipt_path("twenty-first")
        self.assertTrue(path.name.endswith("TWENTY_FIRST_TARGET.md"), path.name)
        self.assertNotIn("-", path.name)


    def test_queue_md_index_single_pass_memo(self) -> None:
        """QUEUE_MD_INDEX_SINGLE_PASS — orphan + known share one memoized scan."""
        auto.clear_queue_md_index_cache()
        md = (
            "## Active\n"
            "- [ ] **live open** — keep\n"
            "## Done\n"
            "- [x] **shipped** — done\n"
            "- [ ] **orphan under done** — promote\n"
            "- [ ] **shipped** — twin of checked (skip)\n"
        )
        orphans = auto.open_done_orphan_items(md)
        self.assertEqual(orphans, ["**orphan under done** — promote"])
        known = auto.queue_md_known_keys(md)
        self.assertIn(auto._normalize_queue_key("**live open** — keep"), known)
        self.assertIn(auto._normalize_queue_key("**shipped** — done"), known)
        self.assertIn(auto._normalize_queue_key("**orphan under done** — promote"), known)
        self.assertEqual(len(auto._QUEUE_MD_INDEX_CACHE), 1)
        orphans2 = auto.open_done_orphan_items(md)
        self.assertEqual(orphans2, orphans)
        self.assertEqual(len(auto._QUEUE_MD_INDEX_CACHE), 1)
        self.assertIn(
            "QUEUE_MD_INDEX_SINGLE_PASS_2026_09_05",
            (ROOT / "scripts" / "project_automation.py").read_text(encoding="utf-8"),
        )
        auto.clear_queue_md_index_cache()
        self.assertEqual(len(auto._QUEUE_MD_INDEX_CACHE), 0)

    def test_queue_md_index_done_open_early_skips_orphan_filter(self) -> None:
        """QUEUE_MD_INDEX_DONE_OPEN_EARLY — no Done opens ⇒ orphans () + known intact."""
        auto.clear_queue_md_index_cache()
        md = (
            "## Active\n"
            "- [x] **already shipped** — keep\n"
            "- [ ] **still open** — work\n"
            "## Done\n"
            "- [x] **historic** — done\n"
        )
        self.assertFalse(auto._done_section_has_open(md))
        idx = auto._queue_md_index(md)
        self.assertEqual(idx.orphan_items, ())
        self.assertIn(auto._normalize_queue_key("**still open** — work"), idx.known_keys)
        self.assertIn(auto._normalize_queue_key("**historic** — done"), idx.known_keys)
        md_open = (
            "## Active\n"
            "- [x] **shipped** — done\n"
            "## Done\n"
            "- [ ] **orphan under done** — promote\n"
            "- [ ] **shipped** — twin skip\n"
        )
        self.assertTrue(auto._done_section_has_open(md_open))
        orphans = auto.open_done_orphan_items(md_open)
        self.assertEqual(orphans, ["**orphan under done** — promote"])
        self.assertIn(
            "QUEUE_MD_INDEX_DONE_OPEN_EARLY_2026_09_05",
            (ROOT / "scripts" / "project_automation.py").read_text(encoding="utf-8"),
        )
        auto.clear_queue_md_index_cache()

    def test_queue_md_index_phased_shared_with_sync(self) -> None:
        """QUEUE_MD_INDEX_PHASED — parse_phased + sync share one memoized scan."""
        auto.clear_queue_md_index_cache()
        md = (
            "## Active\n"
            "- [ ] **live open** — keep\n"
            "## Done\n"
            "- [ ] **orphan under done** — promote\n"
        )
        ctx = "## Remaining work\n- [ ] **live open** — keep\n"
        phased = auto._parse_phased_work_items(md)
        self.assertEqual(phased, ["**live open** — keep"])
        self.assertEqual(len(auto._QUEUE_MD_INDEX_CACHE), 1)
        warns = auto.sync_queue_drift(ctx, md)
        # Hub sync also indexes context via context_queue_open_items (Active twin);
        # WQ blob must remain a HIT (not re-scanned).
        self.assertIn(hash(md), auto._QUEUE_MD_INDEX_CACHE)
        self.assertTrue(any("open under ## Done" in w for w in warns))
        self.assertIn(
            "QUEUE_MD_INDEX_PHASED_2026_09_05",
            (ROOT / "scripts" / "project_automation.py").read_text(encoding="utf-8"),
        )
        auto.clear_queue_md_index_cache()

    def test_close_landed_early_exit_no_open(self) -> None:
        """CLOSE_LANDED_EARLY_EXIT_NO_OPEN — all-[x] WQ returns identity, 0 closed."""
        md = (
            "## Active\n"
            "- [x] **already shipped** — done\n"
            "## Done\n"
            "- [x] **also done** — done\n"
        )
        new_md, n = auto.close_landed_done_orphans(md)
        self.assertEqual(n, 0)
        self.assertIs(new_md, md)
        self.assertIn(
            "CLOSE_LANDED_EARLY_EXIT_NO_OPEN_2026_09_05",
            (ROOT / "scripts" / "project_automation.py").read_text(encoding="utf-8"),
        )
        # Open checkbox still takes the slow path (may or may not close).
        open_md = (
            "## Active\n"
            "- [ ] **unknown unfinished** — stay open\n"
        )
        new2, n2 = auto.close_landed_done_orphans(open_md)
        self.assertEqual(n2, 0)
        self.assertIn("- [ ] **unknown unfinished**", new2)
        self.assertTrue(auto._md_has_closeable_open_line(open_md))
        self.assertFalse(auto._md_has_closeable_open_line(md))

    def test_close_landed_content_hash_memo_hit(self) -> None:
        """CLOSE_LANDED_CONTENT_HASH_MEMO — same blob second call skips proof scan."""
        auto.clear_close_landed_cache()
        md = (
            "## Active\n"
            "- [ ] **unknown unfinished** — stay open\n"
            "## Done\n"
            "- [x] **shipped** — done\n"
        )
        calls = {"n": 0}
        orig = auto._landed_done_proof_ok

        def _wrap(item: str) -> bool:
            calls["n"] += 1
            return orig(item)

        with mock.patch.object(auto, "_landed_done_proof_ok", side_effect=_wrap):
            a, n1 = auto.close_landed_done_orphans(md)
            b, n2 = auto.close_landed_done_orphans(md)
            self.assertEqual(n1, n2)
            self.assertEqual(a, b)
            self.assertEqual(calls["n"], 1)
            auto.clear_close_landed_cache()
            c, _ = auto.close_landed_done_orphans(md)
            self.assertEqual(calls["n"], 2)
            self.assertEqual(c, a)
        self.assertIn(
            "CLOSE_LANDED_CONTENT_HASH_MEMO_2026_09_08",
            (ROOT / "scripts" / "project_automation.py").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
