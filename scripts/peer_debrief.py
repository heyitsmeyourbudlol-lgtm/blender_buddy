#!/usr/bin/env python3
"""Operating system layer — debriefs, institutional memory, optimization KPIs.

Maps three structural pillars to the automation kit:

1. **Data capture & debriefs** — AAR, post-mortems, blameless culture, KPIs
2. **Knowledge management** — DEBRIEF_LOG wiki, SOP index, versioned learnings
3. **Dedicated optimization** — flaw-scan cross-review, improve loop, factory metrics

Usage:
  python3 scripts/peer_debrief.py --status
  python3 scripts/peer_debrief.py --capture-cycle
  python3 scripts/peer_debrief.py --capture-flaw-round
  python3 scripts/peer_debrief.py --append --kind aar --title "..." --body "..."
  ./scripts/peer debrief
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

DEBRIEF_LOG_MD = ROOT / "notes" / "DEBRIEF_LOG.md"
SOP_INDEX_MD = ROOT / "notes" / "SOP_INDEX.md"
OPERATING_SYSTEM_MD = ROOT / "notes" / "OPERATING_SYSTEM.md"
DEBRIEF_JSONL = auto.CONFIG_DIR / "debrief-entries.jsonl"
# Sidecar count — status must not re-scan multi-MB JSONL every team_status tick.
DEBRIEF_COUNT_PATH = auto.CONFIG_DIR / "debrief-entries.count.json"
STATE_PATH = auto.CONFIG_DIR / "peer-loop-state.json"
FLAW_ROUND_PATH = auto.CONFIG_DIR / "peer-flaw-scan-round.json"

AAR_SECTIONS = (
    "What was supposed to happen",
    "What actually happened",
    "Why (process — blameless)",
    "SOP / kit change to try",
    "KPI gap addressed",
)

POSTMORTEM_SECTIONS = (
    "Impact",
    "Timeline",
    "Root cause (5-whys)",
    "Process flaw (not people)",
    "Prevention / detection",
    "Owner niche",
)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def kpi_snapshot(*, quick: bool = True) -> dict[str, Any]:
    """Factory progress dimensions — objective structural gap quantification."""
    try:
        import factory_progress as fp

        block = fp.compute_factory_progress(quick=quick).to_dict()
        return {
            "pct": block.get("pct"),
            "label": block.get("label"),
            "blockers": list(block.get("blockers") or [])[:6],
            "highlights": list(block.get("highlights") or [])[:6],
            "dimensions": [
                {
                    "id": d.get("id"),
                    "name": d.get("name"),
                    "score": d.get("score"),
                    "detail": d.get("detail"),
                }
                for d in (block.get("dimensions") or [])
                if isinstance(d, dict)
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@dataclass
class DebriefEntry:
    kind: str  # aar | postmortem | flaw_triage | cycle | knowledge
    title: str
    body: str
    kpis: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    ts: str = ""

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = _now_iso()


def append_entry(entry: DebriefEntry) -> Path:
    """Append to JSONL + human wiki (institutional memory)."""
    auto.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(asdict(entry), ensure_ascii=False)
    with DEBRIEF_JSONL.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    _bump_entry_count(+1)

    DEBRIEF_LOG_MD.parent.mkdir(parents=True, exist_ok=True)
    if not DEBRIEF_LOG_MD.is_file():
        DEBRIEF_LOG_MD.write_text(
            "# Debrief log — institutional memory\n\n"
            "Blameless AARs, post-mortems, flaw-scan synthesis. "
            "Synced from `peer_debrief.py` — do not delete history.\n\n",
            encoding="utf-8",
        )
    kpi_bit = ""
    if entry.kpis.get("pct") is not None:
        kpi_bit = f" · factory {entry.kpis.get('pct')}%"
    header = f"\n## {entry.ts} — {entry.kind.upper()}: {entry.title}{kpi_bit}\n\n"
    with DEBRIEF_LOG_MD.open("a", encoding="utf-8") as fh:
        fh.write(header + entry.body.strip() + "\n")
    return DEBRIEF_LOG_MD


# Hard cap — status/UI only need a handful of recent rows; never parse hundreds.
_LOAD_RECENT_MAX = 64


def _jsonl_witness() -> tuple[int, int] | None:
    if not DEBRIEF_JSONL.is_file():
        return None
    try:
        st = DEBRIEF_JSONL.stat()
        return int(st.st_mtime_ns), int(st.st_size)
    except OSError:
        return None


def _read_count_sidecar() -> int | None:
    """Return cached entry count when sidecar matches JSONL mtime+size."""
    witness = _jsonl_witness()
    if witness is None or not DEBRIEF_COUNT_PATH.is_file():
        return None
    try:
        data = json.loads(DEBRIEF_COUNT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        if int(data.get("mtime_ns", -1)) != witness[0]:
            return None
        if int(data.get("size", -1)) != witness[1]:
            return None
        return max(0, int(data.get("n", 0)))
    except (TypeError, ValueError):
        return None


def _write_count_sidecar(n: int, *, witness: tuple[int, int] | None = None) -> None:
    wit = witness if witness is not None else _jsonl_witness()
    if wit is None:
        return
    try:
        auto.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"n": int(n), "mtime_ns": wit[0], "size": wit[1]}
        DEBRIEF_COUNT_PATH.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def _scan_entry_count() -> int:
    """Chunked newline count — used once when sidecar is cold/stale (never full read_text)."""
    if not DEBRIEF_JSONL.is_file():
        return 0
    n = 0
    try:
        with DEBRIEF_JSONL.open("rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                n += chunk.count(b"\n")
    except OSError:
        return 0
    return n


def _bump_entry_count(delta: int) -> None:
    """O(1) update after append — avoid re-scanning multi-MB JSONL.

    After ``open(..., 'a')`` the JSONL mtime/size change, so a witness-matched
    sidecar read would miss and fall back to a full scan. Trust the prior ``n``
    and rewrite the sidecar against the new witness.
    """
    n_prev: int | None = None
    if DEBRIEF_COUNT_PATH.is_file():
        try:
            data = json.loads(DEBRIEF_COUNT_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                n_prev = max(0, int(data.get("n", 0)))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            n_prev = None
    if n_prev is None:
        n = _scan_entry_count()
    else:
        n = max(0, n_prev + int(delta))
    _write_count_sidecar(n)


def count_entries() -> int:
    """Entry count for status — sidecar first; one-time scan only when cold.

    ``status_dict`` used to call ``len(load_recent_entries(limit=999))``, which
    under-counted (tail window ~314 of ~15k) and parsed hundreds of JSON rows.
    Live debrief-entries.jsonl measured ~13 MB; full read_text ≈ +24.6 MB RSS.
    Sidecar hit keeps status_dict off the JSONL body entirely.
    """
    cached = _read_count_sidecar()
    if cached is not None:
        return cached
    n = _scan_entry_count()
    _write_count_sidecar(n)
    return n


def load_recent_entries(*, limit: int = 8) -> list[dict[str, Any]]:
    """Last *limit* JSONL rows — seek-tail only (debrief-entries can be multi-MB)."""
    if not DEBRIEF_JSONL.is_file() or limit <= 0:
        return []
    limit = min(int(limit), _LOAD_RECENT_MAX)
    # Over-read a little so partial first line after seek still yields *limit* rows.
    raw = auto.tail_text_lines(DEBRIEF_JSONL, max(limit * 2, limit + 4))
    out: list[dict[str, Any]] = []
    for line in raw[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def capture_cycle_debrief() -> DebriefEntry | None:
    """AAR or post-mortem from last peer-loop cycle."""
    state = _safe_read_json(STATE_PATH) or {}
    lc = state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else {}
    if not lc:
        return None

    verify_ok = lc.get("verify_ok")
    noop = lc.get("noop")
    note = str(lc.get("note") or "")
    failure_type = str(lc.get("failure_type") or "")
    kpis = kpi_snapshot()

    if verify_ok is False or failure_type:
        kind = "postmortem"
        title = f"Verify failure — {failure_type or 'unknown'}"
        body = _template_postmortem(
            impact=f"Cycle rc={lc.get('rc')} verify=FAIL {failure_type}",
            timeline=note or "see peer-loop.log",
            root_cause="(fill — blameless 5-whys)",
            process_flaw="(fill — which gate/SOP failed)",
            prevention="(fill — detection + fix)",
            owner="Verify Runner + Factory Engineer",
        )
    elif noop:
        kind = "aar"
        title = "Noop cycle — queue fingerprint unchanged"
        body = _template_aar(
            expected="Queue advances or scope shrinks",
            actual=f"Noop · {note}",
            why="(fill — replan loop? scope too large? verify-only?)",
            sop_change="(fill — executable queue / smaller peers)",
            kpi_gap="dispatch_delivery or executable_queue",
        )
    else:
        kind = "aar"
        title = "Cycle complete"
        body = _template_aar(
            expected="Ship scoped automation improvement",
            actual=f"rc={lc.get('rc')} verify={'ok' if verify_ok else '?'} · {note}",
            why="(fill — what worked in process)",
            sop_change="(fill — lock in if repeatable)",
            kpi_gap="(fill — which dimension moved)",
        )

    entry = DebriefEntry(kind=kind, title=title, body=body, kpis=kpis, meta={"last_cycle": lc})
    append_entry(entry)
    return entry


def capture_flaw_round_debrief() -> DebriefEntry | None:
    """Institutionalize daily flaw-scan triage into clearinghouse."""
    rnd = _safe_read_json(FLAW_ROUND_PATH)
    if not rnd or rnd.get("phase") != "complete":
        return None

    subjects = rnd.get("subjects") or []
    lines = [
        f"Round {rnd.get('round_date')} — 56 cross-reviews → 8 self-triages",
        "",
        "### Upgrades accepted (aggregate)",
    ]
    upgrades: list[str] = []
    rejected: list[str] = []
    for subj in subjects:
        if not isinstance(subj, dict):
            continue
        title = subj.get("job_title") or subj.get("role_id")
        for u in subj.get("upgrades_accepted") or []:
            upgrades.append(f"- **{title}:** {u}")
        for d in subj.get("downgrades_rejected") or []:
            rejected.append(f"- **{title}:** {d}")
        triage = subj.get("triage")
        if isinstance(triage, dict) and triage.get("summary"):
            lines.append(f"\n**{title} triage:** {triage['summary']}")

    lines.extend(upgrades or ["- (none recorded)"])
    lines.append("\n### Downgrades rejected (aggregate)")
    lines.extend(rejected or ["- (none recorded)"])
    lines.append("\n### SOP actions")
    lines.append("- [ ] Queue Steward: promote accepted upgrades to WORK_QUEUE")
    lines.append("- [ ] Factory Engineer: land kit changes for repeatable wins")

    entry = DebriefEntry(
        kind="flaw_triage",
        title=f"Flaw scan round {rnd.get('round_date')}",
        body="\n".join(lines),
        kpis=kpi_snapshot(),
        meta={"round_id": rnd.get("round_id")},
    )
    append_entry(entry)
    return entry


def _template_aar(
    *,
    expected: str,
    actual: str,
    why: str,
    sop_change: str,
    kpi_gap: str,
) -> str:
    parts = [
        f"**{AAR_SECTIONS[0]}:** {expected}",
        f"**{AAR_SECTIONS[1]}:** {actual}",
        f"**{AAR_SECTIONS[2]}:** {why}",
        f"**{AAR_SECTIONS[3]}:** {sop_change}",
        f"**{AAR_SECTIONS[4]}:** {kpi_gap}",
        "",
        "_Blameless: critique process and SOPs, not people._",
    ]
    return "\n".join(parts)


def _template_postmortem(
    *,
    impact: str,
    timeline: str,
    root_cause: str,
    process_flaw: str,
    prevention: str,
    owner: str,
) -> str:
    parts = [
        f"**{POSTMORTEM_SECTIONS[0]}:** {impact}",
        f"**{POSTMORTEM_SECTIONS[1]}:** {timeline}",
        f"**{POSTMORTEM_SECTIONS[2]}:** {root_cause}",
        f"**{POSTMORTEM_SECTIONS[3]}:** {process_flaw}",
        f"**{POSTMORTEM_SECTIONS[4]}:** {prevention}",
        f"**{POSTMORTEM_SECTIONS[5]}:** {owner}",
        "",
        "_Blameless post-mortem — root cause is structural._",
    ]
    return "\n".join(parts)


def build_debrief_prompt(*, cycle: bool = True, flaw_round: bool = False) -> str | None:
    """Orchestrator prompt: Optimization Unit runs debrief + knowledge capture."""
    sections: list[str] = [
        "# Optimization Unit — debrief & institutional memory",
        "",
        "You are the **Dedicated Optimization Unit** (separate from daily feature work).",
        "Blameless culture: critique **process and SOPs**, not people.",
        "",
        "## KPI snapshot (structural gaps)",
        "",
    ]
    kpis = kpi_snapshot()
    sections.append(f"- Factory readiness: **{kpis.get('pct', '?')}%** — {kpis.get('label', '')}")
    for b in kpis.get("blockers") or []:
        sections.append(f"- Blocker: {b}")
    for dim in kpis.get("dimensions") or []:
        if isinstance(dim, dict) and float(dim.get("score") or 0) < 0.5:
            sections.append(f"- Gap: {dim.get('name')} ({dim.get('score')}) — {dim.get('detail', '')[:80]}")

    sections.extend(
        [
            "",
            "## Your tasks (Queue Steward leads — others support)",
            "",
            "1. **After-Action Review** — fill blanks in latest cycle debrief (if any)",
            "2. **Post-mortem** — if verify failed, complete 5-whys (process root cause)",
            "3. **Knowledge** — append one SOP improvement to `notes/DEBRIEF_LOG.md` via:",
            "   `python3 scripts/peer_debrief.py --append --kind knowledge --title \"...\" --body \"...\"`",
            "4. **Clearinghouse** — sync accepted flaw-scan upgrades → `notes/WORK_QUEUE.md` "
            "↔ `scripts/self_improve_context.md`",
            "5. **Version control** — if SOP change is code, minimal diff + verify",
            "",
            "## SOP index",
            f"Read `{SOP_INDEX_MD.relative_to(ROOT)}` and `notes/OPERATING_SYSTEM.md`.",
            "",
        ]
    )

    recent = load_recent_entries(limit=3)
    if recent:
        sections.append("## Recent debriefs")
        for e in recent:
            sections.append(f"- [{e.get('kind')}] {e.get('title')} ({e.get('ts', '')[:10]})")
        sections.append("")

    if flaw_round:
        sections.append("## Flaw-scan round complete — synthesize triage into queue items")
        sections.append("Run: `python3 scripts/peer_debrief.py --capture-flaw-round` if not captured.")
        sections.append("")

    if cycle:
        sections.append("## Last cycle — complete blameless AAR/post-mortem stubs")
        sections.append("Run: `python3 scripts/peer_debrief.py --capture-cycle` then edit via --append.")
        sections.append("")

    return "\n".join(sections)


def ensure_sop_index() -> None:
    """Centralized wiki index — step-by-step workflow pointers."""
    if SOP_INDEX_MD.is_file():
        return
    SOP_INDEX_MD.parent.mkdir(parents=True, exist_ok=True)
    SOP_INDEX_MD.write_text(
        """# SOP index — standard operating procedures

Version-controlled via git. Update when debriefs lock in new best practices.

| SOP | Location | Owner niche |
|-----|----------|-------------|
| Peer orchestration | `notes/PEER_ORCHESTRATION.md` | Factory Engineer |
| Agent roles (8 workers) | `notes/AGENT_ROLES.md` | Orchestrator |
| Work queue sync | `notes/WORK_QUEUE.md` ↔ `scripts/self_improve_context.md` | Queue Steward |
| Verify gate | `scripts/run_peer_tasks.py`, `peer_tasks.json` verify_commands | Verify Runner |
| Adapt / heal | `scripts/automation_adapt.py`, `IMPORT.md` | Adapt & Heal Specialist |
| External proof | `repos/registry.json`, worktree flow | OSS Integration Architect |
| Daily flaw scan | `scripts/peer_flaw_scan.py`, `notes/AGENT_ROLES.md` | All 8 scanners |
| Debriefs & AAR | `scripts/peer_debrief.py`, `notes/DEBRIEF_LOG.md` | Queue Steward |
| Factory KPIs | `scripts/factory_progress.py`, `/progress` | Queue Steward |
| Agent comms | `scripts/peer_agent_comms.py`, `automation_comms_improve` | Communications Engineer |
| Safety gates | `notes/SAFETY_GATES.md` | Safety Auditor |
| Performance | `automation.config.json` cooldowns/cache | Compression Engineer |
| Operating system map | `notes/OPERATING_SYSTEM.md` | Optimization Unit |

Cross-department clearinghouse: `notes/DEBRIEF_LOG.md` + `notes/CREATIVE_BACKLOG.md`.
""",
        encoding="utf-8",
    )


def status_dict() -> dict[str, Any]:
    ensure_sop_index()
    return {
        "debrief_log": str(DEBRIEF_LOG_MD.relative_to(ROOT)),
        "sop_index": str(SOP_INDEX_MD.relative_to(ROOT)),
        "entries": count_entries(),
        "recent": load_recent_entries(limit=5),
        "kpis": kpi_snapshot(),
    }


def format_status() -> str:
    st = status_dict()
    k = st.get("kpis") or {}
    lines = [
        f"Debrief log: {st['debrief_log']} ({st['entries']} entries)",
        f"SOP index: {st['sop_index']}",
        f"Factory KPI: {k.get('pct', '?')}%",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Debriefs + knowledge + optimization KPIs")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--capture-cycle", action="store_true")
    parser.add_argument("--capture-flaw-round", action="store_true")
    parser.add_argument("--preview", action="store_true", help="Optimization Unit prompt")
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--kind", default="knowledge")
    parser.add_argument("--title", default="")
    parser.add_argument("--body", default="")
    parser.add_argument("--init-sop", action="store_true")
    args = parser.parse_args(argv)

    ensure_sop_index()

    if args.init_sop:
        print(f"ok: {SOP_INDEX_MD}")
        return 0

    if args.capture_cycle:
        e = capture_cycle_debrief()
        print(f"capture: {e.kind if e else 'nothing'} → {DEBRIEF_LOG_MD}")
        return 0

    if args.capture_flaw_round:
        e = capture_flaw_round_debrief()
        print(f"capture: {e.kind if e else 'round not complete'} → {DEBRIEF_LOG_MD}")
        return 0

    if args.append:
        if not args.title or not args.body:
            print("need --title and --body", file=sys.stderr)
            return 1
        append_entry(
            DebriefEntry(
                kind=args.kind,
                title=args.title,
                body=args.body,
                kpis=kpi_snapshot(),
            )
        )
        print(f"appended → {DEBRIEF_LOG_MD}")
        return 0

    if args.preview:
        print(build_debrief_prompt() or "(empty)")
        return 0

    st = status_dict()
    if args.json:
        print(json.dumps(st, indent=2))
    else:
        print(format_status())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
