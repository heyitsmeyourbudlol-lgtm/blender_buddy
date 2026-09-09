#!/usr/bin/env python3
"""Agent survival briefing — inject hazard map into every persona/prompt.

Canon: notes/AGENT_SURVIVAL.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

SURVIVAL_MD = ROOT / "notes" / "AGENT_SURVIVAL.md"

# Compact must-know lines for prompt injection (full doc still in reads).
_COMPACT_LINES = (
    "Assume stalls: plan-gate skip-primary, verify_ok=false (often agent exit), adapt_stale "
    "(often queue drift), peer quiet, namespace flip, oversight down.",
    "Chicken-egg: verify_ok=false → Episodic fail → nobody fixes — soft warn = keep working; "
    "heal with sync-queue / adapt / heal-all / poke.",
    "Never paste self-check/unittest stdout into WORK_QUEUE (corrupt Active lines forever-block).",
    "verify_quiet_max_agents is 0–2 — not max_parallel_agent_procs.",
    "Full map: notes/AGENT_SURVIVAL.md · playbook: notes/AGENT_ERROR_PLAYBOOK.md",
)


def survival_path() -> Path:
    return SURVIVAL_MD


def format_survival_block(*, compact: bool = True, max_chars: int = 1800) -> str:
    """Markdown block injected into every agent persona prompt."""
    lines = [
        "## Survival (what will happen to you — mandatory)",
        "",
    ]
    if compact:
        lines.append("You **will** hit these. Do not rediscover from zero:")
        for i, rule in enumerate(_COMPACT_LINES, 1):
            lines.append(f"{i}. {rule}")
        lines.append("")
        lines.append("Before Plan: skim `notes/AGENT_SURVIVAL.md` hazard table for your symptom.")
        lines.append("")
        return "\n".join(lines)

    if not SURVIVAL_MD.is_file():
        lines.append("_Survival doc missing — run kit heal / restore notes/AGENT_SURVIVAL.md._")
        lines.append("")
        return "\n".join(lines)

    body = SURVIVAL_MD.read_text(encoding="utf-8", errors="replace").strip()
    # Drop H1 title if present — section header already names it.
    if body.startswith("# "):
        body = body.split("\n", 1)[-1].strip()
    if len(body) > max_chars:
        body = body[: max_chars - 20].rstrip() + "\n\n_(truncated — read full notes/AGENT_SURVIVAL.md)_"
    lines.append(body)
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent survival briefing")
    parser.add_argument("--compact", action="store_true", help="Print compact prompt block")
    parser.add_argument("--full", action="store_true", help="Print fuller block from markdown")
    args = parser.parse_args()
    print(format_survival_block(compact=not args.full))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
