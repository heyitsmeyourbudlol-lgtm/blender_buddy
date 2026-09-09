#!/usr/bin/env python3
"""Precision habits — needle-in-a-haystack accuracy for every model tier.

All agents (inherit, composer-2.5-fast, web-researcher, shell, security-review)
must narrow before they edit: locate → isolate → pinpoint → minimal touch → verify.

Usage:
  python3 scripts/peer_precision_habits.py --write
  python3 scripts/peer_precision_habits.py --block --role factory_engineer --model inherit
  ./scripts/peer precision
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

PRECISION_HABITS_MD = ROOT / "notes" / "PRECISION_HABITS.md"
HABITS_JSONL = auto.CONFIG_DIR / "precision-habits.jsonl"

PRECISION_MANDATE = """**Precision habits** — needle-in-a-haystack (every agent, every model):

Develop **surgical accuracy** over time. The repo is the haystack; your job is the **needle** — one root cause, one minimal diff, one verified outcome.

**Habit stack (build these every cycle):**
1. **Locate** — shrink the search space before reading randomly (stack trace → file:line → grep unique symbol).
2. **Isolate** — reproduce with the **smallest** surface (one test, one command, one log tail).
3. **Pinpoint** — name the needle in writing: "The bug is `_foo` in `path:line` because ___."
4. **Touch one** — edit ≤1 file first; run targeted verify; then expand only if needed.
5. **Measure** — report `{files, lines, test}` in GLink DONE; **compare expected vs actual output** before DONE; reject your own diff if scope ballooned."""

NEEDLE_METHOD = """**Needle-in-a-haystack method (mandatory workflow):**

```
Symptom → evidence path → grep/read ≤3 files → hypothesis (1 sentence)
    → single-file minimal fix → targeted verify → full verify → learn-record
```

| Step | Precision rule |
|------|----------------|
| Search | `rg` / grep with **specific** symbols — never bare marker searches or whole-repo skim |
| Read | Read **±40 lines** around the needle — not entire modules |
| Hypothesis | One active hypothesis; falsify before switching |
| Edit | Default **≤15 lines** changed unless assignment requires more — justify in Plan |
| Verify | Run **narrowest** test first (`pytest path::test` / one script), then gate |
| Abort | If >3 files touched before green verify — stop, revert scope, re-pinpoint |"""

HAYSTACK_QUESTIONS: tuple[str, ...] = (
    "Where is the **needle** (exact file:line or config key) — not the haystack (whole subsystem)?",
    "What **single** grep or log line proved it — did I read that line myself?",
    "Can I fix it in **one file** first — what would break if I'm wrong?",
    "Did I name the needle in one sentence before editing?",
    "After edit: files/lines touched — is this still surgical?",
)

MODEL_PRECISION: dict[str, tuple[str, ...]] = {
    "inherit": (
        "Do not explore the whole repo — **3-file read budget** before first edit.",
        "Prefer inherited repo conventions over inventing new patterns.",
        "Parallel breadth is for orchestrator — you stay on one needle.",
    ),
    "composer-2.5-fast": (
        "Speed ≠ sloppiness — **same read gates** as slower models; never skip file:line.",
        "Shell/verify role: run commands precisely; capture **first** failure line only.",
        "No bulk sed/replace without ripgrep proof of unique match count.",
    ),
    "default": (
        "Subagent type does not relax precision — locate → pinpoint → touch one.",
        "If unsure, post GLink REQ with exact file:line question — don't guess.",
    ),
}

SUBAGENT_PRECISION: dict[str, tuple[str, ...]] = {
    "shell": (
        "Output is the measurement — copy exact failing line, exit code, command.",
        "No code edits unless assignment explicitly scopes test fixtures.",
    ),
    "generalPurpose": (
        "Implementation peers: ≤3 files before first targeted verify.",
    ),
    "explore": (
        "Explore to **narrow**, not to refactor — return file:line map, then stop exploring.",
    ),
    "web-researcher": (
        "Research cites **repo file:line** for kit changes — not generic blog advice.",
    ),
    "security-review": (
        "Precision = PASS/BLOCK with **file:line + gate id** — zero vague warnings.",
    ),
}

NICHE_PRECISION: dict[str, tuple[str, ...]] = {
    "factory_engineer": (
        "Pinpoint dispatch bug in peer_loop/orchestrate — don't rewrite both.",
        "One mechanical fix per cycle (wake, noop, verify gate) — measure factory %.",
    ),
    "verify_runner": (
        "Needle = first failing test **file:line** — ignore downstream failures until fixed.",
    ),
    "adapt_specialist": (
        "Needle = adapt audit finding category + path — heal that path only first.",
    ),
    "queue_steward": (
        "Needle = one drift line or one theater marker — sync pair, don't rewrite queue essay.",
    ),
    "communications_engineer": (
        "Needle = one hot path byte/token win with before/after count.",
    ),
    "integration_architect": (
        "Needle = one registry repo + one worktree verify failure — not hub-wide adapt.",
    ),
    "compression_engineer": (
        "Needle = one cache/TTL knob with measured MB delta.",
    ),
    "safety_auditor": (
        "Needle = one gate violation at one line — or explicit PASS with files reviewed list.",
    ),
    "command_builder": (
        "Needle = one compound command replacing one logged loop pattern.",
    ),
    "efficiency_researcher": (
        "Needle = one hot path with metric proof — one file-scoped diff.",
    ),
    "pen_test_researcher": (
        "Needle = one fail-open/secret/injection at file:line — harden fail-closed.",
    ),
    "output_researcher": (
        "Needle = one registry step toward proof — honest deferral if not executable.",
    ),
    "orchestrator": (
        "Needle = disjoint scopes — each peer one haystack slice, one needle.",
    ),
}


def base_role_id(role_id: str) -> str:
    rid = str(role_id or "").strip()
    m = re.match(r"^(.+)_L\d+$", rid)
    return m.group(1) if m else rid


def normalize_model(model: str) -> str:
    m = str(model or "inherit").strip().lower()
    if m in MODEL_PRECISION:
        return m
    if "composer" in m or "fast" in m:
        return "composer-2.5-fast"
    return "inherit"


def format_model_precision(*, model: str = "inherit", subagent_type: str = "") -> str:
    key = normalize_model(model)
    lines = list(MODEL_PRECISION.get(key, MODEL_PRECISION["default"]))
    sub = str(subagent_type or "").strip().lower()
    if sub in SUBAGENT_PRECISION:
        lines.extend(SUBAGENT_PRECISION[sub])
    return "\n".join(f"- {line}" for line in lines)


def format_niche_precision(role_id: str) -> str:
    base = base_role_id(role_id)
    tips = NICHE_PRECISION.get(base, ())
    if not tips:
        return "- Find the single file:line needle before editing."
    return "\n".join(f"- {t}" for t in tips)


def format_precision_block(
    *,
    role_id: str | None = None,
    model: str = "inherit",
    subagent_type: str = "",
) -> str:
    lines = [
        "## Precision habits (needle in a haystack — all models)",
        "",
        PRECISION_MANDATE,
        "",
        NEEDLE_METHOD,
        "",
        "**Precision double-check (ask before edit):**",
        "",
    ]
    for i, q in enumerate(HAYSTACK_QUESTIONS, 1):
        lines.append(f"{i}. {q}")
    lines.append("")
    lines.append(f"**Model `{normalize_model(model)}` precision:**")
    lines.append(format_model_precision(model=model, subagent_type=subagent_type))
    if role_id:
        lines.extend(["", "**Niche needle focus:**", format_niche_precision(role_id), ""])
    lines.append(
        "_Habit:_ record precision wins via `./scripts/peer learn-record` with prefix `needle:` "
        "(file:line + one-line cause)."
    )
    return "\n".join(lines).strip()


def record_precision_note(
    role_id: str,
    needle: str,
    *,
    paths: list[str] | None = None,
) -> None:
    """Append a precision habit note (also flows to project learnings)."""
    text = f"needle: {needle.strip()[:500]}"
    try:
        import peer_project_learning as pl

        pl.record_learning(role_id, text, paths=paths, also_agent_note=True)
    except Exception:  # noqa: BLE001
        HABITS_JSONL.parent.mkdir(parents=True, exist_ok=True)
        row = {"role_id": role_id, "needle": needle, "ts": time.time(), "paths": paths or []}
        with HABITS_JSONL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")


def write_precision_habits_md() -> Path:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines = [
        "# Precision habits — needle in a haystack",
        "",
        f"_Updated {now}_ · all models · develop surgical accuracy every cycle",
        "",
        PRECISION_MANDATE,
        "",
        NEEDLE_METHOD,
        "",
        "## Haystack questions",
        "",
    ]
    for i, q in enumerate(HAYSTACK_QUESTIONS, 1):
        lines.append(f"{i}. {q}")
    lines.extend(["", "## Model tiers", ""])
    for model_key in ("inherit", "composer-2.5-fast", "default"):
        lines.append(f"### {model_key}")
        lines.append(format_model_precision(model=model_key))
        lines.append("")
    lines.extend(["", "## Subagent types", ""])
    for sub, tips in SUBAGENT_PRECISION.items():
        lines.append(f"### {sub}")
        lines.extend(f"- {t}" for t in tips)
        lines.append("")
    lines.extend(["", "## Niche needle focus", ""])
    for rid in sorted(NICHE_PRECISION):
        if rid == "orchestrator":
            continue
        title = rid.replace("_", " ").title()
        lines.append(f"### {title}")
        lines.append(format_niche_precision(rid))
        lines.append("")
    PRECISION_HABITS_MD.parent.mkdir(parents=True, exist_ok=True)
    PRECISION_HABITS_MD.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return PRECISION_HABITS_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Precision habits for all agent models")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--block", action="store_true")
    parser.add_argument("--role", default="")
    parser.add_argument("--model", default="inherit")
    parser.add_argument("--subagent-type", default="")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--needle", default="", help="Needle description file:line + cause")
    args = parser.parse_args()
    if args.record:
        if not args.role or not args.needle:
            print("precision --record requires --role and --needle", file=sys.stderr)
            return 1
        record_precision_note(args.role, args.needle)
        print(f"recorded needle for {args.role}")
        return 0
    if args.block:
        print(
            format_precision_block(
                role_id=args.role or None,
                model=args.model,
                subagent_type=args.subagent_type,
            )
        )
        return 0
    path = write_precision_habits_md()
    print(f"precision-habits: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
