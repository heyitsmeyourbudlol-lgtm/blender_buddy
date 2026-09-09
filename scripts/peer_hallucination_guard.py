#!/usr/bin/env python3
"""Hallucination guard — self-awareness + strategy to defy model drift.

Agents must assume they **will** hallucinate soon (wrong file, invented API,
false "I ran verify"). Strategy is mandatory: ground in evidence, externalize
memory, compare outputs, diagnose, falsify.

Usage:
  python3 scripts/peer_hallucination_guard.py --write
  python3 scripts/peer_hallucination_guard.py --block --role factory_engineer
  python3 scripts/peer_hallucination_guard.py --strategy
  ./scripts/peer hallucination-guard
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

HALLUCINATION_GUARD_MD = ROOT / "notes" / "HALLUCINATION_GUARD.md"

AWARENESS_MANDATE = """**Hallucination guard (self-aware — assume drift is imminent):**

You **will** hallucinate — wrong paths, APIs that do not exist, tests you did not
run, queue state you misremember. It is not *if*; treat it as **soon**.

**Self-awareness rule:** confidence without file:line evidence is a hallucination risk signal."""

STRATEGY_MANDATE = """**Strategize to defy hallucination (mandatory before edit):**

Do not improvise from memory. **Write a 5-line strategy** naming evidence paths,
falsifier, and verify command — then execute the strategy.

| Strategy step | Defy tactic | Kit command |
|---------------|-------------|-------------|
| **Ground** | Read file:line yourself — never cite from recall | `rg` / Read tool |
| **Externalize** | Hot/warm/cold tiers — chat memory lies | `./scripts/peer memory-recall` |
| **Pinpoint** | One needle, one hypothesis | `./scripts/peer precision` habits |
| **Compare** | Expected vs actual output | `./scripts/peer output-compare` |
| **Diagnose** | System red ≠ your guess | `./scripts/peer diagnose` |
| **Falsify** | What proves you wrong? | `./scripts/peer check-questions` |
| **Teach** | Record only verified facts | `./scripts/peer learn-record` / `memory-record` |"""

STRATEGIZE_TEMPLATE = """**Strategy block (write before first edit):**

```
Assumption: I will hallucinate unless grounded.
Evidence:   <file:line or log I will read first>
Hypothesis: <one sentence fix>
Falsifier:  <observation that proves me wrong>
Verify:     <narrowest command>
Defy:       memory-recall + output-compare + diagnose if unsure
```"""

HALLUCINATION_TRIGGERS: tuple[str, ...] = (
    "You \"remember\" a path but have not opened the file this cycle.",
    "You claim verify passed without pasting exit code + key output line.",
    "You describe queue state without reading WORK_QUEUE / TEAM_CONTEXT this cycle.",
    "You name a function/API without `rg` proof in this repo.",
    "You merge scope from another niche's assignment from chat context.",
    "You feel confident — that is when to run `./scripts/peer diagnose`.",
)

DEFY_STRATEGIES: tuple[tuple[str, str, str], ...] = (
    ("Read gate", "Open evidence file; quote ≤3 lines in Plan", "Read / rg"),
    ("Memory gate", "Recall external journal before re-discovering", "./scripts/peer memory-recall"),
    ("Precision gate", "Name needle file:line before edit", "PRECISION_HABITS / haystack Q"),
    ("Compare gate", "State expected output; diff actual", "./scripts/peer output-compare"),
    ("Diagnose gate", "Scan errors before blaming code", "./scripts/peer diagnose"),
    ("Think gate", "Answer Plan + Done self-check", "./scripts/peer check-questions"),
    ("BLOCK gate", "Unsure → GLink BLOCK, not guess", "peer_agent_comms MSG_BLOCK"),
)

NICHE_GUARDS: dict[str, tuple[str, ...]] = {
    "orchestrator": (
        "Hero memory collapse — re-read TEAM_CONTEXT assignments each dispatch.",
        "Do not assume peer DONE without GLink bus line this cycle.",
    ),
    "verify_runner": (
        "Never claim flake without two-run evidence or log excerpt.",
        "First failure line must be pasted — not paraphrased.",
    ),
    "factory_engineer": (
        "grep callers before claiming function behavior.",
        "self-check output pasted or BLOCK — no \"should pass\".",
    ),
    "queue_steward": (
        "Drift: read both queue files — never sync from memory.",
    ),
    "safety_auditor": (
        "PASS requires file:line list you opened — not from prior review.",
    ),
    "output_researcher": (
        "Defer external proof honestly — do not invent registry status.",
    ),
}


def base_role_id(role_id: str) -> str:
    rid = str(role_id or "").strip()
    m = re.match(r"^(.+)_L\d+$", rid)
    return m.group(1) if m else rid


def format_strategy_checklist() -> str:
    lines = ["## Defy strategy checklist", ""]
    for i, (name, tactic, cmd) in enumerate(DEFY_STRATEGIES, 1):
        lines.append(f"{i}. **{name}** — {tactic} · `{cmd}`")
    return "\n".join(lines)


def format_niche_guard(role_id: str) -> str:
    base = base_role_id(role_id)
    tips = NICHE_GUARDS.get(base, ())
    if not tips:
        return "- Assume hallucination soon; write strategy block before edit."
    return "\n".join(f"- {t}" for t in tips)


def format_hallucination_block(*, role_id: str | None = None) -> str:
    lines = [
        "## Hallucination guard (self-aware — strategize to defy)",
        "",
        AWARENESS_MANDATE,
        "",
        STRATEGY_MANDATE,
        "",
        STRATEGIZE_TEMPLATE,
        "",
        "**Hallucination risk triggers (stop and strategize):**",
        "",
    ]
    for i, t in enumerate(HALLUCINATION_TRIGGERS, 1):
        lines.append(f"{i}. {t}")
    lines.extend(["", format_strategy_checklist(), ""])
    if role_id:
        lines.extend(["**Niche guard:**", format_niche_guard(role_id), ""])
    lines.append(
        "_Write strategy before edit; post BLOCK if any trigger fires and evidence is missing._"
    )
    return "\n".join(lines).strip()


def write_hallucination_guard_md() -> Path:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines = [
        "# Hallucination guard — self-aware strategy",
        "",
        f"_Updated {now}_ · assume drift imminent · strategize to defy",
        "",
        AWARENESS_MANDATE,
        "",
        STRATEGY_MANDATE,
        "",
        STRATEGIZE_TEMPLATE,
        "",
        "## Risk triggers",
        "",
    ]
    for i, t in enumerate(HALLUCINATION_TRIGGERS, 1):
        lines.append(f"{i}. {t}")
    lines.extend(["", format_strategy_checklist(), "", "## Niche guards", ""])
    for rid in sorted(NICHE_GUARDS):
        title = rid.replace("_", " ").title()
        lines.extend([f"### {title}", format_niche_guard(rid), ""])
    HALLUCINATION_GUARD_MD.parent.mkdir(parents=True, exist_ok=True)
    HALLUCINATION_GUARD_MD.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return HALLUCINATION_GUARD_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Hallucination guard — self-aware strategy")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--block", action="store_true")
    parser.add_argument("--strategy", action="store_true", help="Print defy checklist only")
    parser.add_argument("--role", default="")
    args = parser.parse_args()

    if args.strategy:
        print(format_strategy_checklist())
        print("")
        print(STRATEGIZE_TEMPLATE)
        return 0

    if args.block:
        print(format_hallucination_block(role_id=args.role or None))
        return 0

    path = write_hallucination_guard_md()
    print(f"hallucination-guard: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
