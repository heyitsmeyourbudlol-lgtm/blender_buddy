#!/usr/bin/env python3
"""Project learning — cumulative inside-out mastery for all agent personas.

Agents must learn the codebase as they work: record insights each cycle, read shared
learnings before Plan, and deepen niche-specific mastery over time.

Usage:
  python3 scripts/peer_project_learning.py --write
  python3 scripts/peer_project_learning.py --record --role factory_engineer --text "..."
  ./scripts/peer learn
  ./scripts/peer learn-record --role ROLE --text "insight"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

PROJECT_LEARNING_MD = ROOT / "notes" / "PROJECT_LEARNING.md"
SHARED_LEARNINGS_JSONL = auto.CONFIG_DIR / "project-learnings.jsonl"
LEARNING_STATE_JSON = auto.CONFIG_DIR / "project-learning-state.json"

LEARNING_MANDATE = """**Learn as you work** — cumulative inside-out mastery (every cycle):

1. **Read before Plan** — `notes/PROJECT_LEARNING.md` + your niche notes in vault; never re-discover documented facts.
2. **Trace before edit** — follow imports/callers in your scope until you can explain the data flow in one paragraph.
3. **Record after work** — append ONE dated learning (non-obvious insight, trap, or file map) via `./scripts/peer learn-record`.
4. **Improve the kit** — mistake patterns → `notes/AGENT_ERROR_PLAYBOOK.md`; process wins → `notes/DEBRIEF_LOG.md` or SOP.
5. **Deepen over time** — each cycle you should know more of the repo than last cycle; teach the team in shared learnings."""

# Critical paths every agent should eventually know (inside-out map).
INSIDE_OUT_MAP: tuple[tuple[str, str], ...] = (
    ("scripts/peer_loop.py", "Forever driver — dispatch, verify gate, noop, worktrees"),
    ("scripts/peer_orchestrate.py", "Orchestrator plan — phase gates, Task peer tasks"),
    ("scripts/automation_improve.py", "Improve forever — horizon, enqueue, hand_out"),
    ("scripts/automation_team.py", "Improve ↔ peer bridge — worker pool, team gaps"),
    ("scripts/peer_team_context.py", "Shared brain — TEAM_CONTEXT, team-sync, cycle_id"),
    ("scripts/peer_persona_rules.py", "Hardwired MUST/MUST NOT per niche"),
    ("scripts/peer_agent_comms.py", "GLink bus + vaults + per-agent notes.jsonl"),
    ("scripts/peer_critical_thinking.py", "Intelligence layer — evidence, root cause, Plan/Act gates"),
    ("notes/CRITICAL_THINKING.md", "Critical thinking canon — read before Plan"),
    ("scripts/peer_hallucination_guard.py", "Hallucination guard — self-aware strategy to defy drift"),
    ("notes/HALLUCINATION_GUARD.md", "Assume hallucination soon — strategize before edit"),
    ("scripts/peer_agent_human_gap.py", "Agent vs human — gap matrix + countermeasures"),
    ("notes/AGENT_VS_HUMAN.md", "20 agent weaknesses vs humans — kit fix per row"),
    ("scripts/peer_idea_synthesis.py", "Grounded idea synthesis — novelty from current knowledge"),
    ("notes/IDEA_SYNTHESIS.md", "Articulate new ideas with ≥2 anchors — not chat fantasy"),
    ("scripts/peer_agent_gates.py", "Executable plan-gate + done-gate for all 20 gaps"),
    ("notes/AGENT_GATES.md", "Run plan-gate before edit; done-gate before DONE"),
    ("scripts/peer_precision_habits.py", "Precision habits — needle-in-a-haystack for all model tiers"),
    ("notes/PRECISION_HABITS.md", "Surgical accuracy canon — read before first edit"),
    ("scripts/peer_output_compare.py", "Expected vs actual output — discrepancy check before DONE"),
    ("notes/OUTPUT_COMPARE.md", "Output compare canon — expected vs actual side-by-side"),
    ("scripts/peer_agent_mini_apps.py", "Mini apps — self-built agent tools when repetition hurts"),
    ("notes/AGENT_MINI_APPS.md", "Mini app charter — scaffold, test, register, promote"),
    ("scripts/agent_tools/", "Directory for agent-built single-purpose scripts"),
    ("scripts/peer_self_diagnose.py", "Self-diagnosis — errors, miscalculations, poor logic"),
    ("notes/SELF_DIAGNOSE.md", "Diagnose canon — instant scan before Plan"),
    ("notes/AGENT_SURVIVAL.md", "Hazard map — stalls, chicken-eggs, false labels (read every cycle)"),
    ("scripts/peer_agent_survival.py", "Inject survival briefing into every persona prompt"),
    ("notes/AGENT_ERROR_PLAYBOOK.md", "Symptom → mechanical fix catalog"),
    ("scripts/peer_playbook.py", "Playbook match + sync AGENT_ERROR_PLAYBOOK.md"),
    ("scripts/peer_work_assign.py", "Peer assignment — ETA vs cursor-agent deadline, GLink ASN"),
    ("notes/WORK_ASSIGN.md", "Assignment canon — assign, eta, when=now|later|miss"),
    ("scripts/peer_memory_span.py", "Memory span — 100x tiered external memory (hot/warm/cold)"),
    ("notes/MEMORY_SPAN.md", "Memory canon — journal, retrieve, tier budgets"),
    ("scripts/peer_lessons.py", "Lessons curator — harvest + lossless squeeze (facts_preserved)"),
    ("scripts/peer_roles.py", "Job titles — assign_worker_pool, L-shards"),
    ("scripts/peer_tasks.json", "agent_roles, templates, verify_commands"),
    ("scripts/project_automation.py", "Config, live state, queue, factory_meter_mode"),
    ("scripts/factory_progress.py", "Self-sufficient / external-proof readiness meter"),
    ("scripts/peer_dual_research.py", "Efficiency + output research lanes"),
    ("notes/TEAM_CONTEXT.md", "Live team snapshot — read every cycle"),
    ("scripts/peer_agent_gates.py", "Plan-gate + done-gate — executable countermeasures"),
    ("notes/AGENT_GATES.md", "Run plan-gate before edit; done-gate before DONE"),
    ("scripts/peer_commands.py", "Agent CLI registry — compound recipes"),
    ("scripts/peer_parallel_dispatch.py", "Parallel cursor-agent niche dispatch"),
    ("scripts/peer_transcript.py", "Transcript → next prompt + last_cycle"),
    ("scripts/cursor_self_improve.py", "Paste/dispatch bridge to orchestrator"),
    ("scripts/peer_command_builder.py", "Command Builder agent prompt + digest"),
    ("notes/WORK_QUEUE.md", "Executable queue (sync with self_improve_context)"),
    ("notes/OPERATING_SYSTEM.md", "Debrief + flaw scan + optimization pillars"),
    ("AGENTS.md", "Operator preferences and verify commands"),
)

NICHE_MASTERY: dict[str, tuple[str, ...]] = {
    "debrief_optimizer": (
        "Master: DEBRIEF_LOG + peer_debrief kinds (aar/knowledge).",
        "Learn: convert one debrief into playbook or executable queue item.",
    ),
    "lessons_curator": (
        "Master: peer_lessons harvest → squeeze → promote; facts_preserved=true.",
        "Master: memory journal + PROJECT_LEARNING + playbook as SoT — no parallel stores.",
        "Learn: squeeze unique store (dedupe/fold); never prune distinct needles.",
    ),
    "factory_engineer": (
        "Master: peer_loop → orchestrate → parallel_dispatch dispatch path end-to-end.",
        "Master: worktree pool (peer_worktree), continue_on_dirty, post-agent verify.",
        "Learn: factory_progress dimensions — what moves self_sufficient %.",
    ),
    "verify_runner": (
        "Master: peer_tasks verify_commands + run_peer_tasks.py exit codes.",
        "Master: verify-gate-quick vs full unittest — when each runs.",
        "Learn: classify failures — test vs import vs lock vs timeout storm.",
    ),
    "adapt_specialist": (
        "Master: automation_adapt probe/heal/audit + profiles/local.json fingerprint.",
        "Master: repos/registry.json status fields and should_re_adapt().",
    ),
    "communications_engineer": (
        "Master: GLink message types, vault summary caps, bus append hot path.",
        "Master: automation_comms_improve verify gate and encoding options.",
    ),
    "queue_steward": (
        "Master: open_work_items sources (launch vs context) and sync_queue_drift.",
        "Master: theater markers vs factory-shaped queue lines.",
    ),
    "integration_architect": (
        "Master: registry → adapt → worktree → native verify → proof artifact chain.",
        "Master: factory_meter_mode deferral of external proof in self_sufficient mode.",
    ),
    "compression_engineer": (
        "Master: measure_live_state RSS path + daemon memory in peer/improve loops.",
        "Master: test_cache_ttl, quick vs full measure tradeoffs.",
    ),
    "safety_auditor": (
        "Master: SAFETY_GATES.md tiers (green/yellow/red) and veto workflow.",
        "Master: flaw-scan scanner persona — 7 reviews per subject niche.",
    ),
    "command_builder": (
        "Master: peer_commands COMMANDS + COMPOUND_STEPS registry pattern.",
        "Master: which shell loops in logs repeat → compound candidates.",
    ),
    "efficiency_researcher": (
        "Master: probe_efficiency findings and EFFICIENCY_RESEARCH agent notes format.",
        "Master: pre-dispatch, wake interval, noop-break interactions.",
    ),
    "pen_test_researcher": (
        "Master: peer_pen_test scan patterns + PEN_TEST agent notes — defensive harden only.",
        "Master: product-forge target preferred; never exploit PoCs.",
    ),
    "output_researcher": (
        "Master: probe_output + OUTPUT_RESEARCH; RESEARCH_SYNC handoff rules.",
        "Master: registry ready vs gap repos — when to defer in self_sufficient mode.",
    ),
    "orchestrator": (
        "Master: full phase gate flow and disjoint scope assignment across niches.",
        "Master: when team focus = verify_gate | flaw_scan | daemon_recovery.",
    ),
}


@dataclass(frozen=True)
class LearningEntry:
    role_id: str
    text: str
    ts: float
    cycle_id: str = ""
    paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "role_id": self.role_id,
            "text": self.text,
            "ts": self.ts,
            "ts_iso": datetime.fromtimestamp(self.ts).isoformat(timespec="seconds"),
            "cycle_id": self.cycle_id,
            "paths": list(self.paths),
        }


def base_role_id(role_id: str) -> str:
    rid = str(role_id or "").strip()
    m = re.match(r"^(.+)_L\d+$", rid)
    return m.group(1) if m else rid


def _read_jsonl(path: Path, *, limit: int = 500) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    except OSError:
        return []
    return rows[-limit:]


def record_learning(
    role_id: str,
    text: str,
    *,
    cycle_id: str = "",
    paths: list[str] | None = None,
    also_agent_note: bool = True,
) -> LearningEntry:
    """Append shared learning + optional per-agent comms note."""
    entry = LearningEntry(
        role_id=role_id,
        text=str(text or "").strip()[:2000],
        ts=time.time(),
        cycle_id=cycle_id or "",
        paths=tuple(paths or [])[:12],
    )
    if not entry.text:
        raise ValueError("learning text required")

    SHARED_LEARNINGS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with SHARED_LEARNINGS_JSONL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry.to_dict(), separators=(",", ":")) + "\n")

    if also_agent_note:
        try:
            import peer_agent_comms as comms

            if comms.comms_enabled():
                comms.append_note(
                    role_id,
                    entry.text[:4000],
                    kind="learn",
                )
                comms.post_glink(
                    msg_type=comms.MSG_SUM,
                    from_role=role_id,
                    payload={
                        "learn": entry.text[:200],
                        "cycle": entry.cycle_id,
                        "paths": list(entry.paths)[:6],
                    },
                )
        except Exception:  # noqa: BLE001
            pass

    write_project_learning_md()
    return entry


def recent_learnings(
    *,
    role_id: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    rows = _read_jsonl(SHARED_LEARNINGS_JSONL)
    if role_id:
        base = base_role_id(role_id)
        rows = [
            r
            for r in rows
            if r.get("role_id") == role_id
            or base_role_id(str(r.get("role_id") or "")) == base
        ]
    return rows[-limit:]


def _debrief_excerpt(*, max_lines: int = 6) -> str:
    path = ROOT / "notes" / "DEBRIEF_LOG.md"
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    body: list[str] = []
    for line in lines:
        if line.startswith("## ") and "20" in line[:30]:
            body.append(line)
        elif body and line.strip().startswith("-"):
            body.append(line)
        if len(body) >= max_lines:
            break
    return "\n".join(body)


def format_inside_out_map(*, max_entries: int = 14) -> str:
    lines = ["**Inside-out map** — learn these paths over time (trace imports, read on demand):"]
    for rel, desc in INSIDE_OUT_MAP[:max_entries]:
        exists = "✓" if (ROOT / rel).is_file() else "?"
        lines.append(f"- `{rel}` {exists} — {desc}")
    return "\n".join(lines)


def format_niche_mastery(role_id: str) -> str:
    base = base_role_id(role_id)
    tips = NICHE_MASTERY.get(base) or NICHE_MASTERY.get("orchestrator", ())
    if not tips:
        return "- Deepen mastery of your assignment scope and its callers each cycle."
    return "\n".join(f"- {t}" for t in tips)


def format_learning_block(*, role_id: str | None = None) -> str:
    """Prompt section: mandate + map + recent learnings + niche mastery."""
    lines = [
        "## Project learning (cumulative — read every cycle)",
        "",
        LEARNING_MANDATE,
        "",
        format_inside_out_map(),
        "",
    ]
    if role_id:
        lines.extend(["**Your niche mastery goals:**", format_niche_mastery(role_id), ""])
    shared = recent_learnings(limit=6)
    if shared:
        lines.append("**Recent team learnings (do not re-learn the hard way):**")
        for row in shared:
            who = row.get("role_id", "?")
            text = str(row.get("text") or "")[:160]
            lines.append(f"- `{who}`: {text}")
        lines.append("")
    deb = _debrief_excerpt()
    if deb:
        lines.extend(["**Debrief peek:**", deb, ""])
    return "\n".join(lines).strip()


def write_project_learning_md() -> Path:
    """Regenerate notes/PROJECT_LEARNING.md from map + recent learnings."""
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines = [
        "# Project learning — inside-out mastery",
        "",
        f"_Updated {now}_ · all agents read each cycle · record via `./scripts/peer learn-record`",
        "",
        LEARNING_MANDATE,
        "",
        "## Inside-out map",
        "",
    ]
    for rel, desc in INSIDE_OUT_MAP:
        mark = "✓" if (ROOT / rel).is_file() else "missing"
        lines.append(f"- `{rel}` ({mark}) — {desc}")

    lines.extend(["", "## Recent team learnings", ""])
    shared = recent_learnings(limit=20)
    if shared:
        for row in reversed(shared[-20:]):
            who = row.get("role_id", "?")
            ts = row.get("ts_iso") or "?"
            text = str(row.get("text") or "")
            paths = row.get("paths") or []
            path_bit = f" · paths: `{', '.join(paths[:4])}`" if paths else ""
            lines.append(f"- **{ts}** `{who}`: {text}{path_bit}")
    else:
        lines.append("_No learnings recorded yet — agents append via learn-record each cycle._")

    lines.extend(["", "## Niche mastery goals", ""])
    for rid in sorted(NICHE_MASTERY):
        if rid == "orchestrator":
            continue
        title = rid.replace("_", " ").title()
        lines.append(f"### {title}")
        lines.append(format_niche_mastery(rid))
        recent = recent_learnings(role_id=rid, limit=3)
        if recent:
            lines.append("")
            lines.append("_Recent:_")
            for row in recent:
                lines.append(f"- {str(row.get('text') or '')[:120]}")
        lines.append("")

    deb = _debrief_excerpt(max_lines=8)
    if deb:
        lines.extend(["## Debrief peek", "", deb, ""])

    PROJECT_LEARNING_MD.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_LEARNING_MD.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    LEARNING_STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    LEARNING_STATE_JSON.write_text(
        json.dumps({"updated": time.time(), "learning_count": len(shared)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return PROJECT_LEARNING_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Project learning — inside-out mastery")
    parser.add_argument("--write", action="store_true", help="Write notes/PROJECT_LEARNING.md")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--role", metavar="ROLE_ID")
    parser.add_argument("--text", metavar="INSIGHT")
    parser.add_argument("--cycle", default="", help="cycle_id cite")
    parser.add_argument("--paths", default="", help="comma-separated paths touched")
    parser.add_argument("--block", action="store_true", help="Print format_learning_block for role")
    args = parser.parse_args()

    if args.record:
        if not args.role or not args.text:
            print("learn-record: --role and --text required", file=sys.stderr)
            return 1
        paths = [p.strip() for p in args.paths.split(",") if p.strip()]
        entry = record_learning(args.role, args.text, cycle_id=args.cycle, paths=paths)
        print(json.dumps(entry.to_dict(), indent=2))
        return 0

    if args.block:
        print(format_learning_block(role_id=args.role or ""))
        return 0

    path = write_project_learning_md()
    print(f"project-learning: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
