#!/usr/bin/env python3
"""Critical thinking layer — intelligence gates for every agent persona.

Agents must reason before acting: evidence, root cause, assumptions, alternatives.
Wired into persona rules, TEAM_CONTEXT, and niche prompts.

Usage:
  python3 scripts/peer_critical_thinking.py --write
  python3 scripts/peer_critical_thinking.py --block --role factory_engineer
  ./scripts/peer think
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

CRITICAL_THINKING_MD = ROOT / "notes" / "CRITICAL_THINKING.md"

CRITICAL_THINKING_MANDATE = """**Critical thinking** — mandatory intelligence layer (every cycle):

Do not execute on autopilot. **Think → check evidence → act → verify → teach.**

| Gate | Ask yourself |
|------|----------------|
| **Evidence** | What file/log/metric proves the problem? Read it — don't trust summaries alone. |
| **Root cause** | Symptom fix or root fix? (verify fail → read first failure line, not random edits) |
| **Assumptions** | List 2 assumptions; try to falsify one before coding. |
| **Alternatives** | Name one simpler approach you rejected — why is your plan still best? |
| **Second-order** | Who else breaks? Scan GLink bus + grep callers of files you touch. |
| **Pre-mortem** | Finish: "This change fails if ___." |
| **Theater** | No file path in assignment? Narrow scope or escalate to Queue Steward — don't essay. |
| **Falsify** | What observation would prove you wrong? Check it if cheap. |
| **Expected vs actual** | State expected verify/output **before** run; compare side-by-side; any discrepancy → investigate before DONE. |
| **Hallucination** | Assume you **will** drift soon — write strategy block; ground every claim in file:line read this cycle. |
| **Human gaps** | You are not human — scan AGENT_VS_HUMAN matrix; run countermeasure command per row. |
| **Grounded ideas** | Novelty needs ≥2 anchors from this cycle — `./scripts/peer idea-articulate` before proposing. |"""

PLAN_GATE = """**Plan gate (answer briefly before any edit):**
1. What is the *actual* problem in one sentence (with evidence path or log)?
2. What is the smallest change that could work?
3. What would falsify this plan?

**Plan → draft numbered steps → execute (mandatory — every agent, every cycle):**
1. **Draft a written plan** before any file edit — problem, goal, constraints, falsifier.
2. **Number every step** (`1…N`) with: action · file paths · expected result · verify command.
3. **Do not execute** until the plan has **≥3 concrete steps** (or a documented 1-step hotfix with evidence file:line).
4. **Execute only the drafted steps** in order; if you skip/reorder, rewrite the plan first.
5. After each step: mark `done` / `blocked`; before DONE: map steps → diffs + `./scripts/peer done-gate`."""

PLAN_EXECUTE_MANDATE = """**Plan → draft steps → execute (non-negotiable):**
Write a numbered step plan **before the first edit**. Each step = action + paths + expected result + verify.
Execute **only** those steps. No autopilot coding. Theater plans without paths → escalate to Queue Steward."""

ACT_GATE = """**Act gate (before merge / DONE):**
1. Did verify/tests address the root cause you named in Plan?
2. **Expected vs actual** — does command/test output match what you predicted? List discrepancies or "match".
3. Did you introduce scope creep outside persona MUST rules?
4. What did you learn that the team should not rediscover? → `learn-record`"""

# Self-questioning — agents must **ask and answer** these aloud in the prompt (double-check).
SELF_CHECK_INSTRUCTION = (
    "**Required:** Write short answers to the Plan + Done questions below **before you edit** "
    "and again **before you declare DONE**. If any answer is worrying, stop and fix or post GLink BLOCK."
)

PLAN_QUESTIONS: tuple[str, ...] = (
    "Did I draft a **numbered step plan** (≥3 steps with paths + expected + verify) before any edit?",
    "What exact evidence (file:line, log tail, metric) shows the problem — did I read it myself?",
    "Is this assignment clearly **in my persona scope** — or am I doing someone else's job?",
    "Am I fixing **root cause** or patching a symptom?",
    "Did I check GLink bus / grep for another niche already touching my target paths?",
    "What is the **smallest** change that could work — and what simpler option did I reject?",
    "What result would prove me **wrong** — and did I check it if cheap?",
    "What goes wrong if I ship this? (one-sentence pre-mortem)",
    "What output do I **expect** after my fix (exit code + key lines or metric)?",
    "What would indicate I am **hallucinating** (confident but no file:line read)?",
    "What **new idea** could combine two facts I read this cycle — with falsifier?",
)

MIDWORK_QUESTIONS: tuple[str, ...] = (
    "Have I edited any file **outside** my stated scope?",
    "Did verify or a test fail since my last check — have I read the **first** failure line?",
    "Am I adding complexity without moving queue_fp, factory %, verify, or latency?",
    "Did I compare **expected vs actual** output for my last verify/command — any discrepancy?",
    "Should I post GLink REQ for help instead of guessing?",
)

DONE_QUESTIONS: tuple[str, ...] = (
    "Did verify/tests pass for the **same root cause** I named in Plan?",
    "Expected vs actual: does output match my Plan prediction — paste compare or `./scripts/peer output-compare`?",
    "Did a measurable outcome move (queue_fp, factory %, verify green, latency, drift=0)?",
    "Did I stay inside persona MUST / MUST NOT rules?",
    "Did I post GLink DONE with cycle_id + paths touched?",
    "Did I record `./scripts/peer learn-record` if I learned something non-obvious?",
    "Would Queue Steward / Verify Runner / Safety call this **theater** or incomplete?",
)

NICHE_QUESTIONS: dict[str, tuple[str, ...]] = {
    "orchestrator": (
        "Do any two Task peers share a file path this cycle?",
        "Does team focus (verify blocked / flaw scan) change who should work today?",
        "Did I answer Plan questions for the **team**, not just one peer?",
    ),
    "factory_engineer": (
        "Will `peer_orchestrate --self-check` pass if I touched orchestration?",
        "Did I grep callers of every function I changed?",
    ),
    "verify_runner": (
        "Is this a flake, env issue, or real code break — which one and why?",
        "Am I about to edit code when my persona is **run-only**?",
    ),
    "adapt_specialist": (
        "Did `--audit` pass after `--heal` — or am I leaving drift?",
    ),
    "communications_engineer": (
        "Did I run `comms-verify` — and measure bytes/tokens saved?",
    ),
    "queue_steward": (
        "Are WORK_QUEUE and self_improve_context **identical** for open items right now?",
        "Does every Active line have a file path or explicit peer command?",
    ),
    "integration_architect": (
        "Is registry status honest for factory_meter_mode (defer external proof if self_sufficient)?",
        "Did worktree verify run **in that worktree**?",
    ),
    "compression_engineer": (
        "Do I have before/after RSS numbers in the diff or GLink DONE?",
    ),
    "safety_auditor": (
        "If I PASS, what harm occurs if I'm wrong?",
        "Does every BLOCK cite file:line + gate?",
    ),
    "command_builder": (
        "Does `./scripts/peer commands-sync` + test_peer_commands pass?",
        "Does this compound replace a **logged** repeated loop?",
    ),
    "efficiency_researcher": (
        "Is my finding backed by a metric in TEAM_CONTEXT or logs?",
    ),
    "output_researcher": (
        "Is this output research or disguised kit polish?",
    ),
}

NICHE_THINKING: dict[str, tuple[str, ...]] = {
    "orchestrator": (
        "Are Task peer scopes **disjoint** on files? Overlap = merge conflict — split again.",
        "Does team focus (verify_gate / flaw_scan) override normal queue priority?",
        "Are you launching enough peers in ONE message without hero-agent collapse?",
    ),
    "factory_engineer": (
        "Is this the **minimal** kit diff that moves factory % or unblocks dispatch?",
        "Did you read call sites of the function you change — not just the function body?",
        "Will self-check + unittest catch a regression you introduced?",
    ),
    "verify_runner": (
        "Flake vs real failure vs environment — classify before blaming code.",
        "First failing line only — don't rerun full suite in a loop without fixing.",
        "Is verify skipped due to cooldown? That's keep-working, not PASS.",
    ),
    "adapt_specialist": (
        "Is should_re_adapt() the real trigger — or a red herring from dirty tree?",
        "Does profile change explain verify fail, or is there a separate test break?",
    ),
    "communications_engineer": (
        "Does this change reduce tokens/bytes on the **hot path** (measurable)?",
        "Backward compatible with existing bus.jsonl lines?",
    ),
    "queue_steward": (
        "Is each open item **executable** (file path + verify) or theater?",
        "Would demoting this line lose real work — or only strategy noise?",
    ),
    "integration_architect": (
        "In self_sufficient mode: defer external proof without lying about progress.",
        "Is worktree verify green **in that tree** before registry status=active?",
    ),
    "compression_engineer": (
        "Measured before/after RSS — or guessing?",
        "Could this prune break correctness under load?",
    ),
    "safety_auditor": (
        "BLOCK requires file:line + gate id — not vibe.",
        "What harm if you PASS incorrectly?",
    ),
    "command_builder": (
        "Does this compound replace a **repeated** loop seen in logs — or invented busywork?",
        "Fewer steps than the shell it replaces?",
    ),
    "efficiency_researcher": (
        "Finding backed by metric (wake, noop, queue_fp) — not opinion?",
        "One file-scoped diff — not a research essay?",
    ),
    "output_researcher": (
        "Breakthrough vs kit polish — honest label?",
        "Registry target exists and is the right next proof step?",
    ),
}


def base_role_id(role_id: str) -> str:
    rid = str(role_id or "").strip()
    m = re.match(r"^(.+)_L\d+$", rid)
    return m.group(1) if m else rid


def format_niche_thinking(role_id: str) -> str:
    base = base_role_id(role_id)
    tips = NICHE_THINKING.get(base, ())
    if not tips:
        return "- Apply evidence + root-cause gates to your assignment."
    return "\n".join(f"- {t}" for t in tips)


def format_question_list(title: str, questions: tuple[str, ...]) -> str:
    lines = [title, ""]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q}")
    return "\n".join(lines)


def format_niche_questions(role_id: str) -> str:
    base = base_role_id(role_id)
    qs = NICHE_QUESTIONS.get(base, ())
    if not qs:
        return ""
    lines = ["**Persona double-check questions:**", ""]
    for i, q in enumerate(qs, 1):
        lines.append(f"{i}. {q}")
    return "\n".join(lines)


def format_self_check_questions(*, role_id: str | None = None) -> str:
    """Structured Q&A agents must answer to catch mistakes before/during/after work."""
    lines = [
        "## Self-check questions (ask & answer — mandatory)",
        "",
        SELF_CHECK_INSTRUCTION,
        "",
        format_question_list("**Before Plan / before any edit:**", PLAN_QUESTIONS),
        "",
        format_question_list("**During work (pause if any answer is bad):**", MIDWORK_QUESTIONS),
        "",
        format_question_list("**Before DONE / GLink (double-check):**", DONE_QUESTIONS),
        "",
    ]
    if role_id:
        niche = format_niche_questions(role_id)
        if niche:
            lines.extend([niche, ""])
    lines.append(
        "_If any answer is \"no\", \"unsure\", or \"symptom only\" — stop, fix scope, or post GLink BLOCK._"
    )
    return "\n".join(lines)


def format_critical_thinking_block(*, role_id: str | None = None) -> str:
    lines = [
        "## Critical thinking (mandatory intelligence layer)",
        "",
        CRITICAL_THINKING_MANDATE,
        "",
        PLAN_GATE,
        "",
        ACT_GATE,
        "",
    ]
    if role_id:
        lines.extend(["**Your persona lens:**", format_niche_thinking(role_id), ""])
    lines.extend(["", format_self_check_questions(role_id=role_id)])
    return "\n".join(lines).strip()


def write_critical_thinking_md() -> Path:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines = [
        "# Critical thinking — agent intelligence layer",
        "",
        f"_Updated {now}_ · wired into every persona + TEAM_CONTEXT",
        "",
        CRITICAL_THINKING_MANDATE,
        "",
        "## Plan gate",
        "",
        PLAN_GATE,
        "",
        "## Act gate",
        "",
        ACT_GATE,
        "",
        "## Persona lenses",
        "",
    ]
    for rid in sorted(NICHE_THINKING):
        title = rid.replace("_", " ").title()
        lines.append(f"### {title}")
        lines.append(format_niche_thinking(rid))
        lines.append("")
    lines.extend([
        "## Self-check questions (all agents)",
        "",
        format_self_check_questions(),
        "",
        "## Persona-specific questions",
        "",
    ])
    for rid in sorted(NICHE_QUESTIONS):
        title = rid.replace("_", " ").title()
        lines.append(f"### {title}")
        lines.append(format_niche_questions(rid))
        lines.append("")
    CRITICAL_THINKING_MD.parent.mkdir(parents=True, exist_ok=True)
    CRITICAL_THINKING_MD.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return CRITICAL_THINKING_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Critical thinking layer for agents")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--block", action="store_true")
    parser.add_argument("--questions", action="store_true", help="Self-check questions only")
    parser.add_argument("--role", default="")
    args = parser.parse_args()
    if args.questions:
        print(format_self_check_questions(role_id=args.role or None))
        return 0
    if args.block:
        print(format_critical_thinking_block(role_id=args.role or None))
        return 0
    path = write_critical_thinking_md()
    print(f"critical-thinking: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
