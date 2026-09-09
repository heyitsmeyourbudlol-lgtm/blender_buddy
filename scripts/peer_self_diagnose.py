#!/usr/bin/env python3
"""Self-diagnosis — instant system scan for errors, miscalculations, poor logic.

Agents must be self-sufficient: run diagnosis before Plan and when anything feels
wrong. Composes self-heal bottlenecks, last_cycle, queue drift, playbook, and
logic heuristics into one report.

Usage:
  python3 scripts/peer_self_diagnose.py --scan
  python3 scripts/peer_self_diagnose.py --write
  python3 scripts/peer_self_diagnose.py --block --role factory_engineer
  ./scripts/peer diagnose
  ./scripts/peer diagnose --quick
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

SELF_DIAGNOSE_MD = ROOT / "notes" / "SELF_DIAGNOSE.md"
LAST_SCAN_JSON = auto.CONFIG_DIR / "self-diagnose-last.json"

DIAGNOSE_MANDATE = """**Self-diagnosis (self-sufficient — run instantly):**

Before Plan and whenever output surprises you, **diagnose the system** — do not guess.

| Class | What to catch | Instant command |
|-------|---------------|-----------------|
| **Errors** | verify fail, daemon down, locks, timeouts, import breaks | `./scripts/peer diagnose` |
| **Miscalculations** | queue drift, noop claimed as progress, ETA miss, wrong metric | `./scripts/peer diagnose` |
| **Poor logic** | theater queue, scope creep, symptom-only fix, hero collapse | `./scripts/peer check-questions` + diagnose |

**Rule:** If diagnose returns critical/high findings → fix or `./scripts/peer heal-all` before new feature work."""

DIAGNOSE_WORKFLOW = """**Instant diagnose workflow:**

```
1. ./scripts/peer diagnose          # full scan (errors + math + logic hints)
2. Read first finding + evidence    # file:line or bottleneck id
3. ./scripts/peer playbook-lookup "<symptom>"  # mechanical fix
4. Re-run targeted verify           # narrowest test first
5. memory-record / learn-record     # teach the team the root cause
```"""

LOGIC_CHECKS: tuple[str, ...] = (
    "Am I fixing **root cause** or patching a symptom visible in logs only?",
    "Does my Plan cite **evidence I read** — not a summary I assumed?",
    "Is this assignment **executable** (file path + verify) or theater?",
    "Did I confuse **correlation** with cause (noop + green verify ≠ queue advance)?",
    "Would another niche call this **scope creep** or wrong persona?",
)

MISCHECK_CHECKS: tuple[str, ...] = (
    "Did queue_fp or factory % **actually move** — or did I claim progress without metric?",
    "Expected vs actual: did I run `./scripts/peer output-compare` before DONE?",
    "Peer assign ETA: did I run `./scripts/peer eta` before promising when=now?",
    "Are WORK_QUEUE and self_improve_context **identical** for open items?",
)

ERROR_CHECKS: tuple[str, ...] = (
    "Did verify/self-check pass on the **same** root cause I named?",
    "First failing line only — not rerunning full suite in a loop?",
    "Any open self-heal bottleneck with severity high/critical?",
    "Daemon + last_cycle present — or am I dispatching into a dead loop?",
)

NICHE_DIAGNOSE: dict[str, tuple[str, ...]] = {
    "verify_runner": (
        "Classify: flake vs env vs code — evidence for each before editing.",
        "Run-only: do not edit production code unless assignment explicitly scopes it.",
    ),
    "factory_engineer": (
        "Dispatch path: peer_loop → orchestrate → parallel_dispatch — which link broke?",
        "self-check must pass after orchestration edits.",
    ),
    "queue_steward": (
        "Drift pair sync before demoting lines — miscalculation if only one file updated.",
    ),
    "orchestrator": (
        "Hero collapse = poor logic — split scopes before implementing.",
        "Run diagnose before dispatch when last_cycle verify_ok=false.",
    ),
    "safety_auditor": (
        "PASS without file:line list = poor logic — BLOCK or cite gates.",
    ),
}


@dataclass
class DiagnosisFinding:
    category: str  # error | miscalculation | poor_logic
    severity: str
    title: str
    evidence: str
    fix_commands: list[str] = field(default_factory=list)
    agent_action: str = ""

    def format_line(self) -> str:
        fixes = " · ".join(f"`{c}`" for c in self.fix_commands[:3]) if self.fix_commands else ""
        base = f"- **[{self.severity}] {self.title}** ({self.category}) — {self.evidence[:120]}"
        if fixes:
            base += f" → {fixes}"
        return base


def base_role_id(role_id: str) -> str:
    rid = str(role_id or "").strip()
    m = re.match(r"^(.+)_L\d+$", rid)
    return m.group(1) if m else rid


def _load_loop_state() -> dict:
    path = auto.CONFIG_DIR / "peer-loop-state.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _queue_drift_lines() -> list[str]:
    try:
        return auto.sync_queue_drift(auto.load_context_md(), auto.load_work_queue_md())
    except Exception:  # noqa: BLE001
        return []


def _findings_from_bottlenecks(*, quick: bool = False) -> list[DiagnosisFinding]:
    findings: list[DiagnosisFinding] = []
    try:
        import peer_self_heal as sh

        bottlenecks = sh.scan_bottlenecks()
        if quick:
            bottlenecks = [b for b in bottlenecks if b.severity in ("critical", "high")][:8]
        for bn in bottlenecks[:12 if not quick else 8]:
            try:
                import peer_playbook as pb

                entry = pb.match_bottleneck_id(bn.id)
                fixes = list(entry.mechanical_fix[:3]) if entry else []
                agent = entry.agent_fix if entry else ""
            except Exception:  # noqa: BLE001
                fixes = ["./scripts/peer self-heal --write"]
                agent = bn.heal_action or ""
            if not fixes and bn.auto_healable:
                fixes = ["./scripts/peer self-heal --write"]
            findings.append(
                DiagnosisFinding(
                    category="error",
                    severity=bn.severity,
                    title=bn.title,
                    evidence=str(bn.evidence or bn.id)[:200],
                    fix_commands=fixes,
                    agent_action=agent[:200],
                )
            )
    except Exception as exc:  # noqa: BLE001
        findings.append(
            DiagnosisFinding(
                category="error",
                severity="medium",
                title="Self-heal scan unavailable",
                evidence=str(exc)[:120],
                fix_commands=["./scripts/peer self-heal-scan"],
            )
        )
    return findings


def _findings_from_last_cycle() -> list[DiagnosisFinding]:
    findings: list[DiagnosisFinding] = []
    state = _load_loop_state()
    lc = state.get("last_cycle")
    if not isinstance(lc, dict) or not lc:
        findings.append(
            DiagnosisFinding(
                category="error",
                severity="high",
                title="No last_cycle memory",
                evidence="peer-loop-state.json missing last_cycle",
                fix_commands=["./scripts/peer self-heal --write", "./scripts/peer once"],
                agent_action="Bootstrap cycle memory before dispatch.",
            )
        )
        return findings
    ft = str(lc.get("failure_type") or "").strip()
    if lc.get("verify_ok") is False and ft != "deferred":
        # adapt_stale / timeout: soft — agents must dispatch; hard-block is deadlock.
        soft_ft = ft.lower() in ("adapt_stale", "timeout")
        findings.append(
            DiagnosisFinding(
                category="error",
                severity="medium" if soft_ft else "high",
                title="Last cycle verify failed",
                evidence=str(lc.get("note") or lc.get("failure_type") or "verify_ok=false")[:200],
                fix_commands=[
                    "./scripts/peer autonomous-repair",
                    "./scripts/peer verify-gate-quick",
                ],
                agent_action="Fix first failing test line before new scope.",
            )
        )
    if ft == "deferred":
        findings.append(
            DiagnosisFinding(
                category="poor_logic",
                severity="low",
                title="Verify deferred soft-skip (not FAIL)",
                evidence=str(lc.get("note") or "failure_type=deferred")[:200],
                fix_commands=["./scripts/peer poke"],
                agent_action="Retry next wake — lock/swarm soft-skip is not a verify storm.",
            )
        )
    if lc.get("noop") and lc.get("verify_ok") and ft != "deferred":
        findings.append(
            DiagnosisFinding(
                category="miscalculation",
                severity="medium",
                title="Noop cycle — queue did not advance",
                evidence=f"queue_fp {lc.get('queue_fp_before')} → {lc.get('queue_fp')}",
                fix_commands=["./scripts/peer noop-break", "./scripts/peer diagnose"],
                agent_action="Diagnose why open items stayed open — wrong scope or BLOCK.",
            )
        )
    if lc.get("local_only") and lc.get("verify_ok"):
        findings.append(
            DiagnosisFinding(
                category="poor_logic",
                severity="low",
                title="Local-only verify tick",
                evidence=str(lc.get("note") or "local verify cooldown path")[:120],
                fix_commands=["./scripts/peer green"],
                agent_action="Do not treat local-only tick as full factory progress.",
            )
        )
    return findings


def _findings_from_queue() -> list[DiagnosisFinding]:
    findings: list[DiagnosisFinding] = []
    drift = _queue_drift_lines()
    if drift:
        findings.append(
            DiagnosisFinding(
                category="miscalculation",
                severity="high",
                title="WORK_QUEUE ↔ self_improve_context drift",
                evidence=drift[0][:160],
                fix_commands=["./scripts/peer heal-all"],
                agent_action="Queue Steward: sync pair to identical open items.",
            )
        )
    open_items = auto.open_work_items().open_items
    theater = 0
    for item in open_items[:20]:
        text = str(item)
        if not re.search(r"[\w/]+\.(py|md|json|sh)|scripts/peer\s+\w+", text):
            theater += 1
    if theater >= 3:
        findings.append(
            DiagnosisFinding(
                category="poor_logic",
                severity="medium",
                title="Theater-shaped queue lines",
                evidence=f"{theater} open item(s) lack file path or peer command",
                fix_commands=["./scripts/peer standup"],
                agent_action="Demote or rewrite to executable scope with verify path.",
            )
        )
    return findings


def _findings_from_assignments() -> list[DiagnosisFinding]:
    findings: list[DiagnosisFinding] = []
    try:
        import peer_work_assign as wa

        for row in wa.list_open_assignments():
            if row.get("when") == wa.WHEN_MISS:
                findings.append(
                    DiagnosisFinding(
                        category="miscalculation",
                        severity="high",
                        title=f"Assignment {row.get('id')} missed deadline",
                        evidence=str(row.get("task", ""))[:120],
                        fix_commands=["./scripts/peer assignments"],
                        agent_action="Split scope or reassign with fresh eta.",
                    )
                )
    except Exception:  # noqa: BLE001
        pass
    return findings


def run_instant_diagnosis(*, quick: bool = False, role_id: str = "") -> list[DiagnosisFinding]:
    """Compose full diagnosis from mechanical scanners + logic heuristics."""
    findings: list[DiagnosisFinding] = []
    findings.extend(_findings_from_last_cycle())
    if not quick:
        findings.extend(_findings_from_queue())
        findings.extend(_findings_from_assignments())
    findings.extend(_findings_from_bottlenecks(quick=quick))

    # Playbook enrichment on combined evidence
    try:
        import peer_playbook as pb

        blob = " ".join(f"{f.title} {f.evidence}" for f in findings)
        if role_id:
            blob += f" {role_id}"
        hits = pb.match_many([blob], limit=4)
        known_titles = {f.title.lower() for f in findings}
        for entry in hits:
            if entry.symptom.lower() in known_titles:
                continue
            findings.append(
                DiagnosisFinding(
                    category="error",
                    severity=entry.severity,
                    title=entry.symptom,
                    evidence=f"playbook:{entry.id}",
                    fix_commands=list(entry.mechanical_fix[:3]),
                    agent_action=entry.agent_fix[:200],
                )
            )
    except Exception:  # noqa: BLE001
        pass

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: (order.get(f.severity, 9), f.category, f.title))
    return findings


def save_last_scan(findings: list[DiagnosisFinding]) -> None:
    payload = {
        "ts": time.time(),
        "count": len(findings),
        "critical": sum(1 for f in findings if f.severity == "critical"),
        "high": sum(1 for f in findings if f.severity == "high"),
        "findings": [
            {
                "category": f.category,
                "severity": f.severity,
                "title": f.title,
                "evidence": f.evidence[:300],
            }
            for f in findings[:20]
        ],
    }
    LAST_SCAN_JSON.parent.mkdir(parents=True, exist_ok=True)
    LAST_SCAN_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def format_diagnosis_report(findings: list[DiagnosisFinding], *, max_entries: int = 12) -> str:
    if not findings:
        return "- **Diagnose:** no open errors/miscalculations/logic flags — proceed with Plan gates."
    lines = ["## Self-diagnosis report", ""]
    by_cat: dict[str, list[DiagnosisFinding]] = {}
    for f in findings[:max_entries]:
        by_cat.setdefault(f.category, []).append(f)
    for cat in ("error", "miscalculation", "poor_logic"):
        rows = by_cat.get(cat) or []
        if not rows:
            continue
        lines.append(f"**{cat.replace('_', ' ').title()}:**")
        for row in rows:
            lines.append(row.format_line())
            if row.agent_action:
                lines.append(f"  - Logic: {row.agent_action[:160]}")
        lines.append("")
    return "\n".join(lines).strip()


def format_niche_diagnose(role_id: str) -> str:
    base = base_role_id(role_id)
    tips = NICHE_DIAGNOSE.get(base, ())
    if not tips:
        return "- Run `./scripts/peer diagnose` before Plan when unsure."
    return "\n".join(f"- {t}" for t in tips)


def format_self_diagnose_block(*, role_id: str | None = None, quick: bool = False) -> str:
    findings = run_instant_diagnosis(quick=quick, role_id=role_id or "")
    save_last_scan(findings)
    lines = [
        "## Self-diagnosis (instant — errors, miscalculations, poor logic)",
        "",
        DIAGNOSE_MANDATE,
        "",
        DIAGNOSE_WORKFLOW,
        "",
        format_diagnosis_report(findings, max_entries=8 if quick else 12),
        "",
        "**Logic checks (answer if any finding above):**",
        "",
    ]
    for i, q in enumerate(LOGIC_CHECKS[:4], 1):
        lines.append(f"{i}. {q}")
    if role_id:
        lines.extend(["", "**Niche diagnose:**", format_niche_diagnose(role_id), ""])
    lines.append(
        "_Run:_ `./scripts/peer diagnose` · _Playbook:_ `./scripts/peer playbook-lookup \"<symptom>\"`"
    )
    return "\n".join(lines).strip()


def write_self_diagnose_md() -> Path:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    findings = run_instant_diagnosis()
    save_last_scan(findings)
    lines = [
        "# Self-diagnosis — instant system scan",
        "",
        f"_Updated {now}_ · self-sufficient · errors + miscalculations + poor logic",
        "",
        DIAGNOSE_MANDATE,
        "",
        DIAGNOSE_WORKFLOW,
        "",
        format_diagnosis_report(findings, max_entries=20),
        "",
        "## Error checks",
        "",
    ]
    for i, q in enumerate(ERROR_CHECKS, 1):
        lines.append(f"{i}. {q}")
    lines.extend(["", "## Miscalculation checks", ""])
    for i, q in enumerate(MISCHECK_CHECKS, 1):
        lines.append(f"{i}. {q}")
    lines.extend(["", "## Logic checks", ""])
    for i, q in enumerate(LOGIC_CHECKS, 1):
        lines.append(f"{i}. {q}")
    lines.extend(["", "## Niche guidance", ""])
    for rid in sorted(NICHE_DIAGNOSE):
        title = rid.replace("_", " ").title()
        lines.extend([f"### {title}", format_niche_diagnose(rid), ""])
    SELF_DIAGNOSE_MD.parent.mkdir(parents=True, exist_ok=True)
    SELF_DIAGNOSE_MD.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return SELF_DIAGNOSE_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Self-diagnosis for agent system")
    parser.add_argument("--scan", action="store_true", help="Run instant diagnosis (default)")
    parser.add_argument("--quick", action="store_true", help="Critical/high + last_cycle only")
    parser.add_argument("--write", action="store_true", help="Write notes/SELF_DIAGNOSE.md")
    parser.add_argument("--block", action="store_true")
    parser.add_argument("--role", default="")
    args = parser.parse_args()

    if args.block:
        print(format_self_diagnose_block(role_id=args.role or None, quick=args.quick))
        return 0

    if args.write:
        path = write_self_diagnose_md()
        print(f"self-diagnose: {path}")
        return 0

    findings = run_instant_diagnosis(quick=args.quick, role_id=args.role)
    save_last_scan(findings)
    print(format_diagnosis_report(findings))
    critical = sum(1 for f in findings if f.severity in ("critical", "high"))
    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
