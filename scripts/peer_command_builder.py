#!/usr/bin/env python3
"""Command Builder — probe gaps and emit a single-agent prompt for peer CLI recipes.

Needle: OVERSEER_COMMAND_BUILDER_COMMITTED_2026_09_07

Committed niche: agents should **execute** `./scripts/peer <id>` for repetitive
tasks; this agent **builds** those recipes when loops appear in logs.

Scope: ONLY scripts/peer_commands.py, scripts/peer, tests/test_peer_commands.py,
notes/AGENT_COMMANDS.md. No feature work, no queue essays.

Usage:
  python3 scripts/peer_command_builder.py --digest
  python3 scripts/peer_command_builder.py --prompt
  python3 scripts/peer_command_builder.py --harvest   # digest + print top gaps
  ./scripts/peer commands-build
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import peer_commands as pc  # noqa: E402
import project_automation as auto  # noqa: E402

DIGEST_PATH = ROOT / "notes" / "COMMAND_BUILDER.md"
PROMPT_PATH = auto.CONFIG_DIR / "command-builder-prompt.md"
PEER_LOG = auto.CONFIG_DIR / "peer-loop.log"
IMPROVE_LOG = auto.CONFIG_DIR / "improve-loop.log"
MINT_SUGGEST = ROOT / "notes" / "niche_distill" / "mint_suggestions.jsonl"
HARVEST_JSON = ROOT / "notes" / "command_builder_harvest.json"

ALLOWED_FILES = (
    "scripts/peer_commands.py",
    "scripts/peer",
    "tests/test_peer_commands.py",
    "notes/AGENT_COMMANDS.md",
)

CHARTER = """# Command Builder — agent charter

**Committed niche (always-on).** One job: turn repeated agent/dev shell loops into
`./scripts/peer <id>` recipes so **every other agent executes commands** instead of
retyping `python3 scripts/…` chains.

## Policy

1. If a task is repetitive → it should be a `./scripts/peer` command (or compound).
2. Other agents **run** commands; Command Builder **adds** them when gaps appear.
3. Prefer smallest compound that covers the loop (reuse existing ids when possible).

## Allowed edits (only these)

- `scripts/peer_commands.py` — `COMMANDS`, `COMPOUND_STEPS`, inner runners
- `scripts/peer` — case entry + help text for new ids
- `tests/test_peer_commands.py` — registry/compound tests
- Regenerate `notes/AGENT_COMMANDS.md` via `./scripts/peer commands-sync`

## Forbidden

- Feature work in peer_loop, orchestrate, adapt, improve
- WORK_QUEUE / horizon / strategy essays
- External OSS proof
- Mass niche training (use `niche-mint` / niche_distiller)

## Done when

1. One new or improved compound/pivotal command with clear description
2. `./scripts/peer commands-sync` passes (md + check)
3. `python3 -m unittest tests.test_peer_commands -q` green
"""


@dataclass(frozen=True)
class CommandGap:
    severity: str
    title: str
    evidence: str
    suggestion: str


def _registered_ids() -> set[str]:
    ids = {c.id for c in pc.COMMANDS}
    ids.update(pc.COMPOUND_STEPS.keys())
    return ids


def _log_tail(path: Path, *, max_bytes: int = 96000) -> str:
    """Return the last ``max_bytes`` of ``path`` without loading the whole file.

    OVERSEER_LOG_TAIL_SEEK_2026_09_07 — ``read_text()[-n]`` decoded the full
    improve-loop / dgx logs (tens of MB) on every ``probe_gaps``; seek from EOF.
    """
    if not path.is_file():
        return ""
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            if size <= 0:
                return ""
            if size <= max_bytes:
                fh.seek(0)
                data = fh.read()
            else:
                fh.seek(size - max_bytes)
                data = fh.read()
                # Drop partial first line after a mid-file byte seek.
                nl = data.find(b"\n")
                if 0 <= nl < len(data) - 1:
                    data = data[nl + 1 :]
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _count_pattern(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, flags=re.IGNORECASE))


def _harvest_raw_script_loops(text: str) -> list[CommandGap]:
    """Find repeated `python3 scripts/foo.py` not yet wrapped as peer commands."""
    reg = _registered_ids()
    stems = re.findall(r"python3\s+scripts/([a-zA-Z0-9_]+)\.py", text)
    counts = Counter(stems)
    gaps: list[CommandGap] = []
    known_map = {
        "peer_orchestrate": "check",
        "automation_adapt": "adapt",
        "automation_improve": "improve",
        "automation_comms_improve": "comms-improve",
        "niche_mint": "niche-mint",
        "niche_bank_train": "niche-mint",
        "peer_command_builder": "commands-build",
        "run_peer_tasks": "verify-gate",
    }
    for stem, n in counts.most_common(12):
        if n < 4:
            continue
        mapped = known_map.get(stem)
        if mapped and mapped in reg:
            continue
        candidate = stem.replace("_", "-")
        if candidate in reg or stem in reg:
            continue
        gaps.append(
            CommandGap(
                severity="high" if n >= 8 else "medium",
                title=f"Raw script loop: scripts/{stem}.py",
                evidence=f"~{n} invocations in recent logs — agents should use ./scripts/peer",
                suggestion=(
                    f"Add `./scripts/peer {candidate}` wrapping `python3 scripts/{stem}.py` "
                    f"(or compound into an existing recipe). Agents must stop calling the script raw."
                ),
            )
        )
    return gaps


def _harvest_mint_suggestions() -> list[CommandGap]:
    if not MINT_SUGGEST.is_file():
        return []
    try:
        lines = MINT_SUGGEST.read_text(encoding="utf-8").splitlines()[-40:]
    except OSError:
        return []
    n = 0
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("action") == "suggest" and not row.get("duplicate_of"):
            n += 1
    if n < 3:
        return []
    return [
        CommandGap(
            severity="medium",
            title="Repeated niche-mint suggestions from assist escalate",
            evidence=f"~{n} recent mint_suggestions without duplicate",
            suggestion=(
                "Ensure `./scripts/peer niche-mint` is pivotal + documented; "
                "optional compound `niche-mint-train` = niche-mint --start --train"
            ),
        )
    ]


def probe_gaps() -> list[CommandGap]:
    """Mechanical hints — repeated log lines not yet a compound command."""
    gaps: list[CommandGap] = []
    reg = _registered_ids()
    peer_tail = _log_tail(PEER_LOG)
    improve_tail = _log_tail(IMPROVE_LOG)
    combined = peer_tail + "\n" + improve_tail

    patterns: list[tuple[str, str, str, str]] = [
        (
            r"compact-queue|compact_executable",
            "compact-queue",
            "Queue compact runs often",
            "Compound `dev-fast`: compact-queue → test-quick → check",
        ),
        (
            r"self-heal|bottleneck",
            "self-heal",
            "Self-heal invoked repeatedly",
            "Compound `dev-heal`: self-heal → commands-sync",
        ),
        (
            r"verify-gate|verify gate|run_verify",
            "verify-gate",
            "Verify gate runs in loops",
            "Ensure `post-cycle` or `dev-fast` covers your loop",
        ),
        (
            r"commands-md|write-md|AGENT_COMMANDS",
            "commands-md",
            "Manual commands-md without check",
            "Use `./scripts/peer commands-sync` (md + self-check)",
        ),
        (
            r"python3 scripts/automation_adapt\.py --heal",
            "adapt",
            "Raw adapt heal instead of peer adapt",
            "Document `./scripts/peer adapt` in AGENT_COMMANDS if missing",
        ),
        (
            r"niche.mint|niche_mint|niche-mint",
            "niche-mint",
            "Niche mint / on-demand specialist traffic",
            "Keep `./scripts/peer niche-mint` pivotal; compound train path if repeated",
        ),
        (
            r"factory.dynamics|factory_dynamics|gpu_share",
            "factory-dynamics",
            "Factory dynamics probes without peer command",
            "Add `./scripts/peer factory-dynamics` → `factory_dynamics.py --snapshot`",
        ),
    ]

    for regex, cmd_id, title, suggestion in patterns:
        hits = _count_pattern(combined, regex)
        if hits < 3:
            continue
        if cmd_id in reg or any(cmd_id == c or cmd_id in c for c in reg):
            continue
        gaps.append(
            CommandGap(
                severity="medium",
                title=title,
                evidence=f"~{hits} log hits in recent tail",
                suggestion=suggestion,
            )
        )

    gaps.extend(_harvest_raw_script_loops(combined))
    gaps.extend(_harvest_mint_suggestions())

    if "commands-sync" not in reg:
        gaps.insert(
            0,
            CommandGap(
                severity="high",
                title="commands-sync missing from registry",
                evidence="agents regenerate md without bundled check",
                suggestion="Add compound: commands-md → check",
            ),
        )

    if "commands-cycle" not in reg:
        gaps.append(
            CommandGap(
                severity="low",
                title="No commands-cycle compound",
                evidence="Command Builder needs a one-shot wake recipe",
                suggestion="Compound `commands-cycle`: commands-digest → commands-build",
            )
        )

    compound_count = len(pc.COMPOUND_STEPS)
    if compound_count < 10:
        gaps.append(
            CommandGap(
                severity="low",
                title="Few compound recipes",
                evidence=f"{compound_count} compounds registered",
                suggestion="Add dev-speed compounds (dev-fast, dev-heal, commands-sync)",
            )
        )

    seen: set[str] = set()
    uniq: list[CommandGap] = []
    for g in gaps:
        if g.title in seen:
            continue
        seen.add(g.title)
        uniq.append(g)
    return uniq[:10]


def write_harvest(gaps: list[CommandGap]) -> Path:
    HARVEST_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "needle": "OVERSEER_COMMAND_BUILDER_COMMITTED_2026_09_07",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_gaps": len(gaps),
        "gaps": [g.__dict__ for g in gaps],
        "policy": "Agents execute ./scripts/peer commands; Command Builder adds recipes.",
    }
    HARVEST_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return HARVEST_JSON


def write_digest(*, gaps: list[CommandGap] | None = None) -> Path:
    gaps = gaps if gaps is not None else probe_gaps()
    write_harvest(gaps)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        CHARTER.strip(),
        "",
        f"_Updated {now}_ · mechanical probe · Needle `OVERSEER_COMMAND_BUILDER_COMMITTED_2026_09_07`",
        "",
        "## Open gaps (build these next)",
        "",
    ]
    if not gaps:
        lines.append(
            "_No mechanical gaps — pick the slowest raw `python3 scripts/…` loop from today and compound it._"
        )
    else:
        for g in gaps:
            lines.append(f"- **[{g.severity}]** {g.title}")
            lines.append(f"  - Evidence: {g.evidence}")
            lines.append(f"  - Suggestion: {g.suggestion}")
    lines.extend(
        [
            "",
            "## Registry snapshot",
            "",
            f"- Commands: {len(pc.COMMANDS)} · Compounds: {len(pc.COMPOUND_STEPS)}",
            f"- Pivotal: {len(pc.list_commands(pivotal_only=True))}",
            "",
            "## Other agents",
            "",
            "Before inventing a shell chain, run `./scripts/peer commands-list --pivotal` "
            "or read `notes/AGENT_COMMANDS.md`. If missing → enqueue Command Builder "
            "(`./scripts/peer commands-cycle`).",
            "",
            "## Workflow",
            "",
            "```bash",
            "./scripts/peer commands-cycle   # digest + builder prompt",
            "./scripts/peer commands-build   # print agent prompt",
            "./scripts/peer commands-sync    # after edit: md + self-check",
            "./scripts/peer dev-fast         # fast local dev gate",
            "```",
            "",
        ]
    )
    DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return DIGEST_PATH


def build_prompt(*, gaps: list[CommandGap] | None = None) -> str:
    gaps = gaps if gaps is not None else probe_gaps()
    write_digest(gaps=gaps)
    gap_block = "\n".join(
        f"- [{g.severity}] {g.title}: {g.suggestion}" for g in gaps[:6]
    ) or "- Pick the most repeated shell sequence from peer-loop.log and compound it."

    return f"""# Command Builder — committed single-agent task

You are the **Command Builder Agent** (always-on niche). Build **one** `./scripts/peer`
recipe so other agents **execute commands** for repetitive work — nothing else.

## Read first

- notes/COMMAND_BUILDER.md
- scripts/peer_commands.py (COMMANDS + COMPOUND_STEPS)
- notes/AGENT_COMMANDS.md
- notes/command_builder_harvest.json (if present)

## Mechanical gaps

{gap_block}

## Rules

1. Edit **only**: {", ".join(ALLOWED_FILES)}
2. Add **one** compound or pivotal one-shot — smallest diff that removes a repeated loop
3. Wire `scripts/peer` case + help line when adding a new id
4. Add/adjust test in tests/test_peer_commands.py
5. Finish with:
   ```bash
   ./scripts/peer commands-sync
   python3 -m unittest tests.test_peer_commands -q
   ```

Do not touch peer_loop, improve, orchestrate, WORK_QUEUE essays, or external OSS work.
"""


def write_prompt(*, gaps: list[CommandGap] | None = None) -> Path:
    PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROMPT_PATH.write_text(build_prompt(gaps=gaps) + "\n", encoding="utf-8")
    return PROMPT_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description="Command Builder probe + prompt")
    parser.add_argument("--digest", action="store_true", help="Write notes/COMMAND_BUILDER.md")
    parser.add_argument("--prompt", action="store_true", help="Write command-builder prompt file")
    parser.add_argument("--harvest", action="store_true", help="Digest + print gaps (committed wake)")
    parser.add_argument("--json", action="store_true", help="Print gaps as JSON")
    args = parser.parse_args()

    gaps = probe_gaps()
    if args.json:
        print(json.dumps([g.__dict__ for g in gaps], indent=2))
        return 0

    if args.harvest or args.digest or not args.prompt:
        path = write_digest(gaps=gaps)
        print(f"command-builder: digest → {path}")
        print(f"command-builder: harvest → {write_harvest(gaps)}")

    if args.prompt or args.harvest:
        path = write_prompt(gaps=gaps)
        print(f"command-builder: prompt → {path}")
        print(build_prompt(gaps=gaps))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
