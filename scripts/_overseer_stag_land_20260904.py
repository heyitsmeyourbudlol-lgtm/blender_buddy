#!/usr/bin/env python3
"""One-shot overseer land: global_agent_cap clamp + heal promote orphans + tests + vault."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

ROOT = Path("/home/arnavrastogi/Automation")
HOLD = Path.home() / ".config/automation-hub/OVERSEER_LAND_HOLD"
FUTURE = time.time() + 4 * 3600

GLOBAL_FN = '''def global_agent_cap() -> int:  # MARKER_XYZ123
    """Total agents to launch — never above ``max_parallel_peers``.

    Raw ``global_agents`` (local/dgx_speed often 48) filled the swarm while the
    worktree pool stayed at 8 — starve verify. Always ``min(raw, peers)``.
    OVERSEER_LAND_2026_09_04 — hub-protect needle: min(cap, peers).
    """
    peers = auto.max_parallel_peers()
    try:
        cap = int(_grid().get("global_agents") or 0)
        if cap > 0:
            return max(1, min(cap, peers))
    except (TypeError, ValueError):
        pass
    return max(1, min(hub_agent_cap() + external_agent_cap(), peers))


'''

PROMOTE_NEEDLE = (
    "    new_context, new_work = context_md, work_md\n"
    "    new_work, active_clones = auto.strip_backlog_active_clones(new_work)\n"
)
PROMOTE_INSERT = (
    "    new_context, new_work = context_md, work_md\n"
    "    # OVERSEER_LAND_2026_09_04 — promote Done orphans on sync/heal (not compact-only)\n"
    "    new_work, promoted = auto.promote_open_done_orphans(new_work)\n"
    "    if promoted:\n"
    '        actions.append(f"promoted {promoted} open-done orphan(s) to Active")\n'
    "\n"
    "    new_work, active_clones = auto.strip_backlog_active_clones(new_work)\n"
)

TEST_MARKER = (
    '            self.assertNotIn("Break noop loop", ctx_text)\n\n'
    "    def test_apply_local_profile_writes_file(self) -> None:"
)

TEST_BLOCK = '''            self.assertNotIn("Break noop loop", ctx_text)

    def test_heal_queue_drift_promotes_done_orphans(self) -> None:
        """sync-queue/heal must promote open ## Done orphans (not compact-only)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = root / "scripts" / "self_improve_context.md"
            wq = root / "notes" / "WORK_QUEUE.md"
            ctx.parent.mkdir(parents=True)
            wq.parent.mkdir(parents=True)
            ctx.write_text(
                "## Remaining work (priority order)\\n\\n"
                "- [ ] **Keep active** — one\\n"
            )
            wq.write_text(
                "## Active\\n\\n"
                "- [ ] **Keep active** — one\\n\\n"
                "## Done\\n\\n"
                "- [ ] **Orphan under Done** — invisible to dispatch\\n"
                "- [x] **Already finished** — ok\\n"
            )
            actions, warnings = adapt.heal_queue_drift(root=root, write=True)
            self.assertTrue(any("promoted" in a and "orphan" in a for a in actions))
            wq_text = wq.read_text()
            self.assertEqual(auto.open_done_orphan_items(wq_text), [])
            open_items = auto._parse_phased_work_items(wq_text)
            self.assertTrue(any("Orphan under Done" in i for i in open_items))
            self.assertFalse(any("invisible to dispatch" in w for w in warnings))
            self.assertIn("Orphan under Done", ctx.read_text())

    def test_apply_local_profile_writes_file(self) -> None:'''


def _fix_block() -> str:
    # Convert intentional \\n inside write_text string literals to real \n escapes.
    return (
        TEST_BLOCK.replace("\\\\n\\n", "\\n\\n")
        .replace("\\\\n", "\\n")
    )


def _touch(path: Path) -> None:
    os.utime(path, (FUTURE, FUTURE))


def _vault(src: Path) -> None:
    for base in (
        Path.home() / ".config/automation-hub/hub-protect/scripts",
        Path.home() / ".config/automation-hub/hub-protect-golden/scripts/scripts",
    ):
        dst = base / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        _touch(dst)


def main() -> None:
    HOLD.parent.mkdir(parents=True, exist_ok=True)
    HOLD.write_text(f"overseer-stag-20260904 {time.time()}\n", encoding="utf-8")
    _touch(HOLD)

    fg = ROOT / "scripts/factory_grid.py"
    text = fg.read_text(encoding="utf-8")
    start = text.find("def global_agent_cap()")
    end = text.find("def sprint_interval_sec()")
    if start < 0 or end < 0 or end <= start:
        raise SystemExit(f"factory_grid anchors missing {start=} {end=}")
    fg.write_text(text[:start] + GLOBAL_FN + text[end:], encoding="utf-8")
    _touch(fg)
    _vault(fg)

    ad = ROOT / "scripts/automation_adapt.py"
    at = ad.read_text(encoding="utf-8")
    chunk = at[at.find("def heal_queue_drift") : at.find("def heal_queue_drift") + 800]
    if "promote_open_done_orphans" not in chunk:
        if PROMOTE_NEEDLE not in at:
            raise SystemExit("adapt promote needle missing")
        at = at.replace(PROMOTE_NEEDLE, PROMOTE_INSERT, 1)
        ad.write_text(at, encoding="utf-8")
    _touch(ad)
    _vault(ad)

    tp = ROOT / "tests/test_automation_adapt.py"
    tt = tp.read_text(encoding="utf-8")
    if "import project_automation as auto" not in tt:
        tt = tt.replace(
            "import automation_adapt as adapt  # noqa: E402\n",
            "import automation_adapt as adapt  # noqa: E402\n"
            "import project_automation as auto  # noqa: E402\n",
            1,
        )
    if "test_heal_queue_drift_promotes_done_orphans" not in tt:
        block = _fix_block()
        # Fix write_text payloads: use real backslash-n sequences in source
        block = '''            self.assertNotIn("Break noop loop", ctx_text)

    def test_heal_queue_drift_promotes_done_orphans(self) -> None:
        """sync-queue/heal must promote open ## Done orphans (not compact-only)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = root / "scripts" / "self_improve_context.md"
            wq = root / "notes" / "WORK_QUEUE.md"
            ctx.parent.mkdir(parents=True)
            wq.parent.mkdir(parents=True)
            ctx.write_text(
                "## Remaining work (priority order)\\n\\n"
                "- [ ] **Keep active** — one\\n"
            )
            wq.write_text(
                "## Active\\n\\n"
                "- [ ] **Keep active** — one\\n\\n"
                "## Done\\n\\n"
                "- [ ] **Orphan under Done** — invisible to dispatch\\n"
                "- [x] **Already finished** — ok\\n"
            )
            actions, warnings = adapt.heal_queue_drift(root=root, write=True)
            self.assertTrue(any("promoted" in a and "orphan" in a for a in actions))
            wq_text = wq.read_text()
            self.assertEqual(auto.open_done_orphan_items(wq_text), [])
            open_items = auto._parse_phased_work_items(wq_text)
            self.assertTrue(any("Orphan under Done" in i for i in open_items))
            self.assertFalse(any("invisible to dispatch" in w for w in warnings))
            self.assertIn("Orphan under Done", ctx.read_text())

    def test_apply_local_profile_writes_file(self) -> None:'''
        # In the above triple-quoted string, \\n is one backslash + n in the .py file content we write.
        if TEST_MARKER not in tt:
            raise SystemExit("test marker missing")
        tt = tt.replace(TEST_MARKER, block, 1)
    tp.write_text(tt, encoding="utf-8")
    _touch(tp)

    # Proof
    fg_t = fg.read_text(encoding="utf-8")
    ad_t = ad.read_text(encoding="utf-8")
    tt_t = tp.read_text(encoding="utf-8")
    print(
        {
            "fg_clamp": "return max(1, min(cap, peers))" in fg_t,
            "ad_promote": "promote_open_done_orphans" in ad_t[ad_t.find("def heal_queue_drift") :][:800],
            "test_method": "test_heal_queue_drift_promotes_done_orphans" in tt_t,
            "auto_import": "import project_automation as auto" in tt_t,
            "hold": HOLD.is_file(),
        }
    )


if __name__ == "__main__":
    main()
