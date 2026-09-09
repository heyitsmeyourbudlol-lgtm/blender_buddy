#!/usr/bin/env python3
"""Idea synthesis — articulate NEW ideas from CURRENT knowledge (not chat fantasy).

Agents must not invent ideas from vacuum. Novelty comes from **combining verified
anchors** in this repo: file:line facts, metrics, queue gaps, learnings, research.

Usage:
  python3 scripts/peer_idea_synthesis.py --write
  python3 scripts/peer_idea_synthesis.py --articulate
  python3 scripts/peer_idea_synthesis.py --record --role ROLE --title "..." \\
      --anchors "path:line fact" --hypothesis "..." [--experiment "..."]
  ./scripts/peer idea-articulate
  ./scripts/peer idea-record --role ROLE --title "..." --anchors "..." --hypothesis "..."
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

IDEA_SYNTHESIS_MD = ROOT / "notes" / "IDEA_SYNTHESIS.md"
IDEAS_JSONL = auto.CONFIG_DIR / "grounded-ideas.jsonl"
CREATIVE_BACKLOG = auto.CFG.get("creative_backlog", "notes/CREATIVE_BACKLOG.md")
if isinstance(CREATIVE_BACKLOG, str):
    CREATIVE_BACKLOG_PATH = ROOT / CREATIVE_BACKLOG
else:
    CREATIVE_BACKLOG_PATH = ROOT / "notes" / "CREATIVE_BACKLOG.md"

SYNTHESIS_MANDATE = """**Idea synthesis (grounded novelty — not hallucinated creativity):**

Humans connect dots from lived experience. You connect dots from **what you read
this cycle**. A new idea MUST cite ≥2 evidence anchors (file:line or metric) and
state why the combination is non-obvious."""

ARTICULATION_TEMPLATE = """**Grounded idea block (write when proposing something new):**

```
Title:       <short name>
Anchors:     <file:line or metric #1>; <file:line or metric #2>
Tension:     <what does not fit together today?>
Hypothesis:  <one sentence novel claim>
Why novel:   <why obvious fix was rejected — cite anchor>
Experiment:  <smallest test — command or diff scope>
Falsifier:   <what result kills the idea>
Record:      ./scripts/peer idea-record --role ROLE --title "..." --anchors "..." --hypothesis "..."
```"""

IDEA_RULES: tuple[str, ...] = (
    "No anchor → no idea. Chat memory alone does not count.",
    "≥2 independent anchors from reads this cycle (or memory-recall hits with paths).",
    "Reject ideas that duplicate an open WORK_QUEUE line — link instead.",
    "Prefer experiments that fit one peer session (ETA check via `./scripts/peer eta`).",
    "Verified wins → learn-record; promising experiments → CREATIVE_BACKLOG.",
    "Theater ideas (no falsifier, no experiment) → narrow scope or BLOCK.",
)

NICHE_IDEA_LENSES: dict[str, tuple[str, ...]] = {
    "orchestrator": (
        "Combine queue_fp signals + parallel peer utilization → dispatch experiment.",
        "Cross-niche assignment gaps → new ASN pattern with ETA proof.",
    ),
    "factory_engineer": (
        "Trace verify fail + worktree state → minimal kit gate change.",
        "factory_progress dimension stuck → one file lever with metric.",
    ),
    "efficiency_researcher": (
        "noop loop + wake latency → one measurable hypothesis.",
    ),
    "command_builder": (
        "Repeated shell in logs + peer_commands gap → compound recipe.",
    ),
    "compression_engineer": (
        "RSS metric + import hotspot → single lazy-import experiment.",
    ),
    "output_researcher": (
        "Research lane finding + factory meter → actionable backlog item.",
    ),
}


def base_role_id(role_id: str) -> str:
    rid = str(role_id or "").strip()
    m = re.match(r"^(.+)_L\d+$", rid)
    return m.group(1) if m else rid


def format_idea_rules() -> str:
    lines = ["## Grounded idea rules", ""]
    for i, rule in enumerate(IDEA_RULES, 1):
        lines.append(f"{i}. {rule}")
    return "\n".join(lines)


def format_niche_ideas(role_id: str) -> str:
    base = base_role_id(role_id)
    tips = NICHE_IDEA_LENSES.get(base, ())
    if not tips:
        return "- Combine two file:line facts you read this cycle into one falsifiable experiment."
    return "\n".join(f"- {t}" for t in tips)


def format_idea_synthesis_block(*, role_id: str | None = None) -> str:
    lines = [
        "## Idea synthesis (articulate from current knowledge)",
        "",
        SYNTHESIS_MANDATE,
        "",
        ARTICULATION_TEMPLATE,
        "",
        format_idea_rules(),
        "",
    ]
    if role_id:
        lines.extend(["**Niche lenses:**", format_niche_ideas(role_id), ""])
    lines.append(
        "_Propose novelty only after anchors exist; record via `./scripts/peer idea-record`._"
    )
    return "\n".join(lines).strip()


def _append_jsonl(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _validate_anchors(anchors: str) -> tuple[bool, str]:
    parts = [p.strip() for p in anchors.split(";") if p.strip()]
    if len(parts) < 2:
        return False, "need ≥2 anchors separated by ';'"
    for part in parts:
        if ":" not in part and not re.search(r"\d", part):
            return False, f"anchor must include file:line or metric: {part[:60]}"
    return True, ""


def record_idea(
    *,
    role_id: str,
    title: str,
    anchors: str,
    hypothesis: str,
    experiment: str = "",
    falsifier: str = "",
    also_backlog: bool = True,
) -> Path:
    row = {
        "ts": time.time(),
        "role": role_id,
        "title": title.strip(),
        "anchors": anchors.strip(),
        "hypothesis": hypothesis.strip(),
        "experiment": experiment.strip(),
        "falsifier": falsifier.strip(),
    }
    _append_jsonl(IDEAS_JSONL, row)

    if also_backlog and title.strip():
        line = f"- [ ] **{title.strip()}** — {hypothesis.strip()} _(anchors: {anchors.strip()})_"
        CREATIVE_BACKLOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        text = CREATIVE_BACKLOG_PATH.read_text(encoding="utf-8") if CREATIVE_BACKLOG_PATH.is_file() else ""
        if title.strip() not in text:
            marker = "## Next experiments (non-obvious)"
            if marker in text:
                text = text.replace(marker, marker + "\n" + line, 1)
            else:
                text = (text.rstrip() + "\n\n" + marker + "\n" + line + "\n").lstrip()
            CREATIVE_BACKLOG_PATH.write_text(text, encoding="utf-8")

    return IDEAS_JSONL


def recent_ideas(*, limit: int = 5) -> list[dict[str, object]]:
    if not IDEAS_JSONL.is_file():
        return []
    rows: list[dict[str, object]] = []
    for line in IDEAS_JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


def format_recent_ideas_block(*, limit: int = 3) -> str:
    items = recent_ideas(limit=limit)
    if not items:
        return ""
    lines = ["**Recent grounded ideas (team):**", ""]
    for row in reversed(items):
        title = row.get("title", "?")
        hyp = row.get("hypothesis", "")
        lines.append(f"- {title}: {hyp}")
    return "\n".join(lines)


def write_idea_synthesis_md() -> Path:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines = [
        "# Idea synthesis — grounded novelty",
        "",
        f"_Updated {now}_ · articulate new ideas from current knowledge only",
        "",
        SYNTHESIS_MANDATE,
        "",
        ARTICULATION_TEMPLATE,
        "",
        format_idea_rules(),
        "",
        "## Niche lenses",
        "",
    ]
    for rid in sorted(NICHE_IDEA_LENSES):
        title = rid.replace("_", " ").title()
        lines.extend([f"### {title}", format_niche_ideas(rid), ""])
    recent = format_recent_ideas_block(limit=5)
    if recent:
        lines.extend(["", recent, ""])
    lines.append("_Counterpart gap row: Agent vs human → Creativity → `./scripts/peer idea-articulate`_")
    IDEA_SYNTHESIS_MD.parent.mkdir(parents=True, exist_ok=True)
    IDEA_SYNTHESIS_MD.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return IDEA_SYNTHESIS_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Grounded idea synthesis")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--articulate", action="store_true")
    parser.add_argument("--block", action="store_true")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--role", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--anchors", default="")
    parser.add_argument("--hypothesis", default="")
    parser.add_argument("--experiment", default="")
    parser.add_argument("--falsifier", default="")
    parser.add_argument("--no-backlog", action="store_true")
    args = parser.parse_args()

    if args.articulate:
        print(ARTICULATION_TEMPLATE)
        print("")
        print(format_idea_rules())
        return 0

    if args.block:
        print(format_idea_synthesis_block(role_id=args.role or None))
        return 0

    if args.record:
        if not args.title or not args.anchors or not args.hypothesis:
            print("idea-record: need --title --anchors --hypothesis", file=sys.stderr)
            return 1
        ok, msg = _validate_anchors(args.anchors)
        if not ok:
            print(f"idea-record: {msg}", file=sys.stderr)
            return 1
        path = record_idea(
            role_id=args.role or "unknown",
            title=args.title,
            anchors=args.anchors,
            hypothesis=args.hypothesis,
            experiment=args.experiment,
            falsifier=args.falsifier,
            also_backlog=not args.no_backlog,
        )
        print(f"idea-record: {path}")
        return 0

    path = write_idea_synthesis_md()
    print(f"idea-synthesis: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
