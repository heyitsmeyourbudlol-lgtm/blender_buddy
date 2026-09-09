#!/usr/bin/env python3
"""Factory A+ scoreboard — phase exit criteria vs live signals.

Usage:
  python3 scripts/peer_factory_a_plus.py              # scoreboard
  python3 scripts/peer_factory_a_plus.py --json
  python3 scripts/peer_factory_a_plus.py --demote-theater --write
  python3 scripts/peer_factory_a_plus.py --install-queue --write
  ./scripts/peer factory-a-plus
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import asi_rubric  # noqa: E402
import automation_config as cfg_mod  # noqa: E402
import factory_progress as fp  # noqa: E402
import peer_self_heal as self_heal  # noqa: E402
import project_automation as auto  # noqa: E402

PLAN_MD = ROOT / "notes" / "FACTORY_A_PLUS_PLAN.md"
TASKS_MD = ROOT / "notes" / "FACTORY_A_PLUS_TASKS.md"

THEATER_MARKERS = fp._THEATER_MARKERS  # noqa: SLF001

FACTORY_A_PLUS_ITEMS: tuple[str, ...] = (
    "**[factory-a-plus:phase0] Dual-daemon proof — Mac + hub WORKING/IDLE 7d** — "
    "`./scripts/peer bootstrap`; confirm peer + improve LaunchAgents on Mac and hub",
    "**[factory-a-plus:phase0] Close improve→peer closed loop** — "
    "3 cycles improve→wake→peer→verify ok; ASI Phase 4 green",
    "**[factory-a-plus:phase0] Break noop loop + tune wake intervals** — "
    "fingerprint advances after ok cycles; continuous_wake_sec 45–90",
    "**[factory-a-plus:phase0] Self-repair zero-defect 7d** — "
    "0 high/med bottlenecks; digest matches status; shadow test dupes removed",
    "**[factory-a-plus:phase1] Demote theater — Active ≤12 executable only** — "
    "`peer factory-a-plus --demote-theater`; no crown/ASI/meta-exit in Active",
    "**[factory-a-plus:phase1] Freeze kit expansion until external proof** — "
    "no new peer_* modules; DEBRIEF_LOG tracks kit LOC weekly",
    "**[factory-a-plus:phase2] Prove parallel dispatch 10 cycles zero collisions** — "
    "peer_parallel_dispatch + worktree isolation regression",
    "**[factory-a-plus:phase2] Dirty-tree coding worktree path** — "
    "dispatch clear ≥95% with dirty main",
    "**[factory-a-plus:phase3] ASI Phases 1–3 runtime green** — asi_rubric ≥75% 7d",
    "**[factory-a-plus:phase3] Enable knowledge index on hub** — "
    "notes+transcripts inject ≤6000 chars on DGX",
    "**[factory-a-plus:phase4] External proof #1 — CPT or smallest adapted repo** — "
    "adapt+verify+PR in notes/EXTERNAL_PROOF.md",
    "**[factory-a-plus:phase4] Switch factory_meter_mode to external_proof** — "
    "after Phase 0–1 green; flip automation.config.json",
)


@dataclass
class PhaseStatus:
    phase: str
    label: str
    status: str  # green | yellow | red | pending
    evidence: str


def _is_theater(text: str) -> bool:
    low = text.lower()
    if any(m in low for m in THEATER_MARKERS):
        return True
    # self_sufficient meter: External-proof Active lines are deferred theater
    # (tank executable_queue). Demote them like crown/ASI chrome.
    try:
        if auto.factory_meter_mode() == "self_sufficient" and fp._is_deferred(text):
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _launchctl_running(label: str) -> bool:
    return fp._launchctl_running(label)  # noqa: SLF001


def _peer_improve_running() -> tuple[bool, bool]:
    snap = self_heal.daemon_status_snapshot()
    return snap["peer_loop"], snap["improve_loop"]


def _bottleneck_counts() -> tuple[int, int]:
    try:
        hits = self_heal.scan_bottlenecks()
    except Exception:  # noqa: BLE001
        return -1, -1
    high = sum(1 for b in hits if getattr(b, "severity", "") == "high")
    med = sum(1 for b in hits if getattr(b, "severity", "") == "medium")
    return high, med


def _asi_pct() -> int:
    try:
        result = asi_rubric.compute_asi_rubric(signals={})
        return int(result.pct)
    except Exception:  # noqa: BLE001
        return 0


def _factory_pct() -> int:
    try:
        prog = fp.compute_factory_progress()
        return int(prog.pct)
    except Exception:  # noqa: BLE001
        return 0


def _shadow_test_dupes() -> list[str]:
    """OVERSEER_PURGE_SCRIPTS_TEST_SHADOW_2026_09_04 — scripts/test_*.py poison discover."""
    dupes: list[str] = []
    for path in (ROOT / "test_autonomous_repair.py", SCRIPTS / "test_autonomous_repair.py"):
        if path.is_file():
            dupes.append(str(path.relative_to(ROOT)))
    for path in sorted(SCRIPTS.glob("test_*.py")):
        if path.is_file():
            dupes.append(str(path.relative_to(ROOT)))
    return dupes


def evaluate_phases() -> list[PhaseStatus]:
    peer_on, improve_on = _peer_improve_running()
    high, med = _bottleneck_counts()
    asi = _asi_pct()
    factory = _factory_pct()
    dupes = _shadow_test_dupes()
    cfg = cfg_mod.CFG
    meter_mode = str(cfg.get("factory_meter_mode") or "self_sufficient")
    ki = cfg.get("knowledge_index") if isinstance(cfg.get("knowledge_index"), dict) else {}
    ki_on = bool(ki.get("enabled"))
    collision = self_heal.dual_namespace_collision()

    open_items = auto.open_work_items().open_items
    theater_active = sum(1 for i in open_items if _is_theater(i))
    aplus_open = sum(1 for i in open_items if "factory-a-plus" in i.lower())

    # Phase 0
    if peer_on and improve_on and high == 0 and med == 0 and not collision.get("peer") and not collision.get("improve"):
        p0 = "green"
        p0_ev = "peer + improve running; bottlenecks clear; single namespace"
    elif collision.get("peer") or collision.get("improve"):
        p0 = "red"
        p0_ev = f"dual namespace peer={collision.get('peer')} improve={collision.get('improve')}"
    elif peer_on or improve_on:
        p0 = "yellow"
        p0_ev = f"peer={peer_on} improve={improve_on}; {high} high · {med} med bottlenecks"
    else:
        p0 = "red"
        p0_ev = "both daemons down — run ./scripts/peer bootstrap"

    if dupes:
        p0_ev += f"; shadow tests: {', '.join(dupes)}"

    # Phase 1
    if theater_active == 0 and len(open_items) <= 12:
        p1 = "green"
    elif theater_active <= 2:
        p1 = "yellow"
    else:
        p1 = "red"
    p1_ev = f"theater_active={theater_active}; open={len(open_items)}; aplus_items={aplus_open}"

    # Phase 2
    p2 = "yellow" if factory >= 85 else "pending"
    p2_ev = f"factory={factory}% dispatch dimension"

    # Phase 3
    if asi >= 75 and ki_on:
        p3 = "green"
    elif asi >= 50:
        p3 = "yellow"
    else:
        p3 = "pending"
    p3_ev = f"ASI={asi}%; knowledge_index={ki_on}"

    # Phase 4
    proof_path = ROOT / "notes" / "EXTERNAL_PROOF.md"
    proof_done = 0
    if proof_path.is_file():
        proof_done = len(re.findall(r"\|\s*\d+\s*\|[^|]+\|\s*factory-proven", proof_path.read_text()))
    if meter_mode == "external_proof" and proof_done >= 3:
        p4 = "green"
    elif proof_done >= 1:
        p4 = "yellow"
    else:
        p4 = "pending"
    p4_ev = f"meter={meter_mode}; factory-proven={proof_done}/3"

    # Phase 5
    crown = ROOT / "notes" / "CROWN_EXIT.md"
    if crown.is_file() and "Q1 2027" in crown.read_text():
        p5 = "yellow"
        p5_ev = "CROWN_EXIT draft exists"
    else:
        p5 = "pending"
        p5_ev = "CROWN_EXIT missing"

    return [
        PhaseStatus("0", "Stabilize", p0, p0_ev),
        PhaseStatus("1", "Queue discipline", p1, p1_ev),
        PhaseStatus("2", "Orchestration", p2, p2_ev),
        PhaseStatus("3", "Memory & cognition", p3, p3_ev),
        PhaseStatus("4", "Factory outcomes", p4, p4_ev),
        PhaseStatus("5", "Crown exit", p5, p5_ev),
    ]


def format_scoreboard(phases: list[PhaseStatus]) -> str:
    icons = {"green": "✓", "yellow": "~", "red": "✗", "pending": "○"}
    lines = [
        "# Factory A+ scoreboard",
        "",
        f"_As of {time.strftime('%Y-%m-%d %H:%M:%S')}_ · plan: notes/FACTORY_A_PLUS_PLAN.md",
        "",
        "| Phase | Status | Evidence |",
        "|-------|--------|----------|",
    ]
    for p in phases:
        lines.append(f"| {p.phase} {p.label} | {icons.get(p.status, '?')} {p.status} | {p.evidence} |")
    lines.extend(
        [
            "",
            f"Factory readiness: {_factory_pct()}% · ASI rubric: {_asi_pct()}%",
            "",
            "```bash",
            "./scripts/peer factory-a-plus --demote-theater --write",
            "./scripts/peer bootstrap",
            "./scripts/peer progress",
            "```",
        ]
    )
    return "\n".join(lines)


def _demote_theater_in_context(demoted_lines: list[str]) -> None:
    """Remove matching open theater lines from context Remaining work → Backlog."""
    if not demoted_lines:
        return
    ctx_path = auto.CONTEXT_PATH
    if not ctx_path.is_file():
        return
    keys = {
        auto._normalize_queue_key(auto._parse_work_item(line.strip()) or line.strip())  # noqa: SLF001
        for line in demoted_lines
    }
    lines = ctx_path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    moved: list[str] = []
    for line in lines:
        s = line.strip()
        if s.startswith("- [ ]"):
            item = auto._parse_work_item(s) or s  # noqa: SLF001
            if auto._normalize_queue_key(item) in keys:  # noqa: SLF001
                moved.append(line)
                continue
        out.append(line)
    if not moved:
        return
    bi = next((i for i, l in enumerate(out) if l.strip().startswith("## Backlog")), None)
    if bi is None:
        out.extend(["", "## Backlog (deferred — noop shrink)", ""])
        out.extend(moved)
    else:
        out = out[: bi + 1] + moved + out[bi + 1 :]
    ctx_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def demote_theater(*, write: bool = False) -> tuple[int, list[str]]:
    """Move theater-marked open Active items to Backlog."""
    work_md = auto.load_work_queue_md()
    lines = work_md.splitlines()
    out: list[str] = []
    demoted: list[str] = []
    in_active = False

    for line in lines:
        s = line.strip()
        if s.startswith("## Active") or s.startswith("## Phase"):
            in_active = True
            out.append(line)
            continue
        if in_active and s.startswith("## "):
            in_active = False
        if in_active and s.startswith("- [ ]"):
            item = auto._parse_work_item(s) or s  # noqa: SLF001
            if _is_theater(item) and "factory-a-plus" not in item.lower():
                demoted.append(line)
                continue
        out.append(line)

    if demoted:
        backlog_idx = next(
            (i for i, l in enumerate(out) if l.strip().startswith("## Backlog")),
            None,
        )
        if backlog_idx is None:
            out.extend(["", "## Backlog (deferred — noop shrink)", ""])
            out.extend(demoted)
        else:
            out = out[: backlog_idx + 1] + demoted + out[backlog_idx + 1 :]  # after header — before leaves Active track

    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"

    if write and new_md != work_md:
        auto.WORK_QUEUE_PATH.write_text(new_md, encoding="utf-8")
        # Sync context first — otherwise Remaining-work theater re-enters Active via heal.
        _demote_theater_in_context(demoted)
        import automation_adapt as adapt

        adapt.heal_queue_drift(root=ROOT, write=True)

    return len(demoted), demoted


def install_queue_items(*, write: bool = False) -> int:
    """Prepend factory-a-plus items to Active if missing."""
    work_md = auto.load_work_queue_md()
    existing_keys = {auto._normalize_queue_key(i) for i in auto.all_open_work_queue_items(work_md)}  # noqa: SLF001
    to_add: list[str] = []
    for item in FACTORY_A_PLUS_ITEMS:
        key = auto._normalize_queue_key(item)  # noqa: SLF001
        if key not in existing_keys:
            to_add.append(f"- [ ] {item}")

    if not to_add:
        return 0

    lines = work_md.splitlines()
    out: list[str] = []
    inserted = False
    for i, line in enumerate(lines):
        out.append(line)
        if not inserted and line.strip().startswith("## Active"):
            out.append("")
            out.extend(to_add)
            inserted = True

    if not inserted:
        out = ["## Active", ""] + to_add + [""] + lines

    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"

    if write:
        auto.WORK_QUEUE_PATH.write_text(new_md, encoding="utf-8")
        try:
            import automation_adapt as adapt

            adapt.heal_queue_drift(root=ROOT, write=True)
        except Exception:  # noqa: BLE001
            pass
        auto.compact_executable_queue(write=True)

    return len(to_add)


def remove_shadow_tests(*, write: bool = False) -> list[str]:
    """OVERSEER_PURGE_SCRIPTS_TEST_SHADOW_2026_09_04 — drop scripts/ + root shadows."""
    removed: list[str] = []
    candidates = [
        ROOT / "test_autonomous_repair.py",
        SCRIPTS / "test_autonomous_repair.py",
        *sorted(SCRIPTS.glob("test_*.py")),
    ]
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        if write:
            path.unlink()
        removed.append(str(path.relative_to(ROOT)))
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Factory A+ phase scoreboard")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--demote-theater", action="store_true")
    parser.add_argument("--install-queue", action="store_true")
    parser.add_argument("--remove-shadow-tests", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--phase0", action="store_true", help="Run Phase 0 mechanical fixes")
    args = parser.parse_args()

    if args.phase0:
        removed = remove_shadow_tests(write=args.write)
        if removed:
            label = "removed" if args.write else "would remove"
            print(f"shadow tests: {label} {removed}")
        n, _ = demote_theater(write=args.write)
        print(f"theater demoted: {n}" + ("" if args.write else " (dry-run)"))
        added = install_queue_items(write=args.write)
        if added:
            print(f"queue: added {added} factory-a-plus item(s)" + ("" if args.write else " (dry-run)"))
        if args.write:
            cfg_path = ROOT / "automation.config.json"
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            if float(cfg.get("continuous_wake_sec") or 0) < 45:
                cfg["continuous_wake_sec"] = 90
                cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
                print("config: continuous_wake_sec → 90")
        elif not removed and not n and not added:
            print("(dry-run — pass --write to apply)")
        return 0

    if args.demote_theater:
        n, items = demote_theater(write=args.write)
        print(f"demote-theater: {n} item(s)" + (" written" if args.write else " (dry-run)"))
        return 0

    if args.install_queue:
        n = install_queue_items(write=args.write)
        print(f"install-queue: {n} item(s) added" + (" written" if args.write else " (dry-run)"))
        return 0

    if args.remove_shadow_tests:
        removed = remove_shadow_tests(write=args.write)
        print(f"remove-shadow-tests: {removed}")
        return 0

    phases = evaluate_phases()
    if args.json:
        print(json.dumps([asdict(p) for p in phases], indent=2))
        return 0

    print(format_scoreboard(phases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
