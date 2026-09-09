#!/usr/bin/env python3
"""Agent vs human — known weaknesses and kit countermeasures.

Humans have persistent memory, embodied judgment, and social accountability.
Agents have speed, parallelism, and tireless repetition — but systematic failure
modes. This module maps every major gap to an executable kit fix.

Usage:
  python3 scripts/peer_agent_human_gap.py --write
  python3 scripts/peer_agent_human_gap.py --block
  ./scripts/peer agent-gap
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

AGENT_VS_HUMAN_MD = ROOT / "notes" / "AGENT_VS_HUMAN.md"

# (human_strength, agent_weakness, symptom, kit_fix, command)
GAP_ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "Long-term memory",
        "Context evaporates each session",
        "Re-discovers same files; contradicts prior cycle",
        "Tiered external memory + team learnings",
        "./scripts/peer memory-recall · learn-record · TEAM_CONTEXT",
    ),
    (
        "Episodic recall",
        "Truncation drops newest turns",
        "Forgets assignment mid-cycle; repeats DONE work",
        "Hot/warm/cold pack + last_cycle retrospect",
        "./scripts/peer memory-pack · peer-loop-state",
    ),
    (
        "Ground truth sense",
        "Hallucination / confabulation",
        "Invented paths, APIs, \"verify passed\"",
        "Assume drift soon; strategy block before edit",
        "./scripts/peer hallucination-strategy",
    ),
    (
        "Reality check",
        "No embodied world model",
        "Claims outcome without log excerpt",
        "Expected vs actual compare before DONE",
        "./scripts/peer output-compare",
    ),
    (
        "Skepticism",
        "Overconfidence on partial reads",
        "Symptom fix; wrong root cause",
        "Plan/Act gates + falsify question",
        "./scripts/peer check-questions · think",
    ),
    (
        "Attention to detail",
        "Needle-in-haystack misses",
        "Edits wrong file; bare keyword match",
        "One hypothesis, one file:line",
        "./scripts/peer precision",
    ),
    (
        "Self-correction",
        "Blind to own logic errors",
        "Broken imports; queue drift; stale config",
        "Instant system scan before Plan",
        "./scripts/peer diagnose",
    ),
    (
        "Parallel cognition",
        "Serial repo exploration",
        "One agent greps entire tree",
        "Disjoint Task peers in one message",
        "peer_orchestrate parallel dispatch",
    ),
    (
        "Time awareness",
        "No felt deadline",
        "Starts scope that cannot finish in session",
        "ETA vs cursor-agent session limit",
        "./scripts/peer eta · assign",
    ),
    (
        "Delegation",
        "Hero agent collapse",
        "Orchestrator implements instead of assigns",
        "Peer-to-peer ASN + job titles",
        "./scripts/peer assign",
    ),
    (
        "Institutional memory",
        "Chat-only teaching",
        "Team re-learns traps every week",
        "PROJECT_LEARNING + playbook + debrief",
        "./scripts/peer learn-record · playbook-lookup",
    ),
    (
        "Execution bias",
        "Plan theater without diffs",
        "Long markdown, zero verify",
        "Factory queue + verify gate + minimal diff rubric",
        "run_verify_commands · WORK_QUEUE",
    ),
    (
        "Scope discipline",
        "Scope creep across niches",
        "Touches files outside persona MUST",
        "Persona rules + precision scope line",
        "./scripts/peer persona-rules",
    ),
    (
        "Safety intuition",
        "Misses second-order harm",
        "Reclaim merged before audit",
        "Safety peer on yellow/red + flaw scan",
        "notes/SAFETY_GATES.md · safety_auditor",
    ),
    (
        "Tool building",
        "Repeats manual shell loops",
        "Same rg/pytest incantation every cycle",
        "Mini apps under scripts/agent_tools/",
        "./scripts/peer mini-apps --scaffold",
    ),
    (
        "Creativity",
        "Generic ideas / no novelty",
        "Repeats obvious queue chores",
        "Grounded idea synthesis from current knowledge",
        "./scripts/peer idea-articulate · idea-record",
    ),
    (
        "Stakeholder judgment",
        "Cannot own product/business tradeoffs",
        "Automates paid ads or secrets",
        "Human-only gates (launch Phase 6, RED tier)",
        "notes/LAUNCH.md · SAFETY_GATES",
    ),
    (
        "Consistency",
        "Inconsistent process turn-to-turn",
        "Skips gates when \"confident\"",
        "Same TEAM_CONTEXT + persona every cycle",
        "./scripts/peer team-context --write",
    ),
    (
        "Accountability",
        "No blame, no ownership",
        "Marks DONE without GLink proof",
        "GLink ACK/DONE/BLOCK + output compare",
        "peer_agent_comms bus.jsonl",
    ),
    (
        "Secret hygiene",
        "Leaks keys into diffs/chat",
        "Tokens in commits or prompts",
        "Env-var names only; rotate on leak",
        "AGENTS.md secret rules",
    ),
)

GAP_MANDATE = """**Agent vs human (know your gaps — use the kit, don't pretend to be human):**

You are fast and parallel; you are **not** a human. Do not rely on intuition, memory,
or social pressure. For each gap below, run the listed countermeasure **before** you
claim DONE."""


def format_gap_table(*, max_rows: int | None = None) -> str:
    rows = GAP_ROWS if max_rows is None else GAP_ROWS[:max_rows]
    lines = [
        "| Human strength | Agent weakness | Symptom | Kit fix | Command |",
        "|----------------|----------------|---------|---------|---------|",
    ]
    for human, weak, sym, fix, cmd in rows:
        lines.append(f"| {human} | {weak} | {sym} | {fix} | `{cmd}` |")
    return "\n".join(lines)


def format_human_gap_block(*, compact: bool = False) -> str:
    lines = [
        "## Agent vs human — gaps and countermeasures",
        "",
        GAP_MANDATE,
        "",
    ]
    if compact:
        lines.append(format_gap_table(max_rows=8))
        lines.append("")
        lines.append(
            f"_Full matrix ({len(GAP_ROWS)} gaps): `notes/AGENT_VS_HUMAN.md` · "
            "Creativity gap → `./scripts/peer idea-articulate`_"
        )
    else:
        lines.append(format_gap_table())
        lines.append("")
        lines.append(
            "**Rule:** If you feel \"human-like confidence,\" you are probably in a gap row — "
            "run the command column before editing."
        )
    return "\n".join(lines).strip()


def write_agent_vs_human_md() -> Path:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines = [
        "# Agent vs human — problems and kit solutions",
        "",
        f"_Updated {now}_ · {len(GAP_ROWS)} known gaps · countermeasure per row",
        "",
        GAP_MANDATE,
        "",
        "## Full gap matrix",
        "",
        format_gap_table(),
        "",
        "## How to use",
        "",
        "1. **Start of Plan** — scan matrix; which rows apply to this task?",
        "2. **Before edit** — run countermeasures for hallucination, precision, memory rows.",
        "3. **Before DONE** — output-compare + diagnose + learn-record rows.",
        "4. **When stuck on novelty** — `./scripts/peer idea-articulate` (grounded synthesis).",
        "",
        "## What agents should not pretend to do",
        "",
        "- Product pricing, paid distribution, secret handling → **human only**",
        "- \"I remember from last month\" → **read external memory**",
        "- \"This should work\" → **paste verify output**",
        "",
        "_See also: HALLUCINATION_GUARD, MEMORY_SPAN, CRITICAL_THINKING, SELF_IMPROVE_RUBRIC._",
    ]
    AGENT_VS_HUMAN_MD.parent.mkdir(parents=True, exist_ok=True)
    AGENT_VS_HUMAN_MD.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return AGENT_VS_HUMAN_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent vs human gap matrix")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--block", action="store_true")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    if args.block:
        print(format_human_gap_block(compact=args.compact))
        return 0

    path = write_agent_vs_human_md()
    print(f"agent-gap: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
