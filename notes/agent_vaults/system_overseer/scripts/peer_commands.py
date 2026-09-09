#!/usr/bin/env python3
"""Agent command registry — repetitive pivotal tasks as one-shot CLI recipes.

Agents should prefer `./scripts/peer <command>` over re-inventing shell loops.
Compound commands chain multiple steps for cold-start, heal, verify, and standup.

Usage:
  python3 scripts/peer_commands.py --list
  python3 scripts/peer_commands.py --list --pivotal
  python3 scripts/peer_commands.py run bootstrap
  python3 scripts/peer_commands.py run heal-all --dry-run
  python3 scripts/peer_commands.py --write-md
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

AGENT_COMMANDS_MD = ROOT / "notes" / "AGENT_COMMANDS.md"
PEER = ROOT / "scripts" / "peer"


@dataclass(frozen=True)
class PeerCommand:
    id: str
    category: str
    description: str
    argv: tuple[str, ...]
    pivotal: bool = False
    tags: tuple[str, ...] = ()


@dataclass
class RunReport:
    command_id: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    ok: bool = True

    def add(self, *, step: str, rc: int, detail: str = "") -> None:
        self.steps.append({"step": step, "rc": rc, "detail": detail[:500]})
        if rc != 0:
            self.ok = False


def _py(script: str, *args: str) -> tuple[str, ...]:
    return ("python3", str(SCRIPTS / script), *args)


def _peer(*args: str) -> tuple[str, ...]:
    return (str(PEER), *args)


COMMANDS: list[PeerCommand] = [
    PeerCommand("bootstrap", "compound", "Cold start: install daemons → self-heal → compact → check → digest", (), pivotal=True, tags=("start", "daemon")),
    PeerCommand("heal-all", "compound", "Full mechanical heal: self-heal → compact → sync → verify gate", (), pivotal=True, tags=("heal",)),
    PeerCommand("green", "compound", "Health gate: check + progress + self-heal-scan (exit 1 if blocked)", (), pivotal=True, tags=("verify", "health")),
    PeerCommand("install-all", "compound", "Install peer + improve LaunchAgents", (), pivotal=True, tags=("daemon",)),
    PeerCommand("pre-dispatch", "compound", "Before agent: compact → plan-gate → check → ensure-pool", (), pivotal=True, tags=("dispatch", "gate")),
    PeerCommand("post-cycle", "compound", "After agent cycle: verify → self-heal → digest", (), pivotal=True, tags=("dispatch",)),
    PeerCommand("standup", "compound", "Morning standup: digest → improve-status → progress → self-heal-status", (), pivotal=True, tags=("status",)),
    PeerCommand("noop-break", "compound", "Break noop: compact → poke → investigate-force", (), pivotal=True, tags=("noop",)),
    PeerCommand(
        "stagnation-break",
        "compound",
        "Overseer stagnation: heal-all → noop-break → progress",
        (),
        pivotal=True,
        tags=("noop", "oversight", "stagnation"),
    ),
    PeerCommand("commands-sync", "compound", "After command edits: regenerate AGENT_COMMANDS.md → self-check", (), pivotal=True, tags=("commands", "dev")),
    PeerCommand("dev-fast", "compound", "Fast dev gate: compact → test-quick → check", (), pivotal=True, tags=("dev", "speed")),
    PeerCommand("dev-heal", "compound", "Dev recovery: self-heal → commands-sync", (), pivotal=True, tags=("dev", "heal")),
    PeerCommand("plan-gate", "agent", "Plan gate — all agent-vs-human countermeasures before edit", _peer("plan-gate"), pivotal=True, tags=("gate", "plan")),
    PeerCommand("done-gate", "agent", "Done gate — diagnose + compare before DONE", _peer("done-gate"), pivotal=True, tags=("gate", "done")),
    PeerCommand("diagnose", "agent", "Self-diagnosis scan (errors, math, logic)", _peer("diagnose"), pivotal=True, tags=("gate",)),
    PeerCommand("diagnose-quick", "agent", "Self-diagnosis quick (critical/high only)", _peer("diagnose-quick"), pivotal=True),
    PeerCommand("hallucination-guard", "agent", "Refresh HALLUCINATION_GUARD.md", _peer("hallucination-guard")),
    PeerCommand("hallucination-strategy", "agent", "Print defy strategy template", _peer("hallucination-strategy"), pivotal=True),
    PeerCommand("agent-gap", "agent", "Refresh AGENT_VS_HUMAN.md gap matrix", _peer("agent-gap")),
    PeerCommand("idea-articulate", "agent", "Grounded idea template (≥2 anchors)", _peer("idea-articulate"), pivotal=True),
    PeerCommand("idea-record", "agent", "Record grounded idea to backlog", _peer("idea-record")),
    PeerCommand("idea-synthesis", "agent", "Refresh IDEA_SYNTHESIS.md", _peer("idea-synthesis")),
    PeerCommand("agent-gates", "agent", "Refresh AGENT_GATES.md", _peer("agent-gates")),
    PeerCommand("think", "agent", "Critical thinking block", _peer("think")),
    PeerCommand("check-questions", "agent", "Plan/Done self-check questions", _peer("check-questions"), pivotal=True),
    PeerCommand("precision", "agent", "Precision habits block", _peer("precision")),
    PeerCommand("output-compare", "agent", "Expected vs actual output compare", _peer("output-compare"), pivotal=True),
    PeerCommand("learn", "agent", "Refresh PROJECT_LEARNING.md", _peer("learn")),
    PeerCommand("learn-record", "agent", "Append team learning", _peer("learn-record"), pivotal=True),
    PeerCommand("memory", "agent", "Refresh MEMORY_SPAN.md", _peer("memory")),
    PeerCommand("memory-record", "agent", "Append memory journal fact", _peer("memory-record"), pivotal=True),
    PeerCommand("memory-recall", "agent", "Recall memory tiers", _peer("memory-recall"), pivotal=True),
    PeerCommand("assign", "agent", "Peer-to-peer work assignment", _peer("assign")),
    PeerCommand("eta", "agent", "ETA vs session deadline", _peer("eta"), pivotal=True),
    PeerCommand("team-context", "agent", "Refresh TEAM_CONTEXT.md", _peer("team-context"), pivotal=True),
    PeerCommand("digest", "health", "Refresh notes/AUTOMATION_DIGEST.md (mechanical snapshot)", _peer("digest"), pivotal=True),
    PeerCommand("oversight", "health", "Progress Monitor one cycle (24/7 niche)", _peer("oversight"), pivotal=True),
    PeerCommand("oversight-force", "health", "Force Progress Monitor → cursor-agent", _peer("oversight-force"), pivotal=True),
    PeerCommand("oversight-digest", "health", "Progress Monitor mechanical only", _peer("oversight-digest")),
    PeerCommand("oversight-status", "health", "Progress Monitor daemon status", _peer("oversight-status"), pivotal=True),
    PeerCommand("oversight-install", "health", "Install Progress Monitor forever LaunchAgent", _peer("oversight-install"), pivotal=True),
    PeerCommand("progress-monitor", "health", "24/7 Progress Monitor status", _peer("progress-monitor"), pivotal=True, tags=("org",)),
    PeerCommand("progress-monitor-once", "health", "Progress Monitor one review cycle", _peer("progress-monitor-once"), tags=("org",)),
    PeerCommand("progress-monitor-force", "health", "Force Progress Monitor → cursor-agent", _peer("progress-monitor-force"), tags=("org",)),
    PeerCommand("progress-monitor-install", "health", "Ensure Progress Monitor LaunchAgent 24/7", _peer("progress-monitor-install"), pivotal=True, tags=("org",)),
    PeerCommand("repo-research", "health", "Mechanical repo flaw probe + digest", _peer("repo-research"), pivotal=True),
    PeerCommand("repo-research-digest", "health", "Repo flaw probe only (no agent)", _peer("repo-research-digest")),
    PeerCommand("repo-research-status", "health", "Repo research daemon + last run", _peer("repo-research-status")),
    PeerCommand("repo-research-install", "health", "Install repo research LaunchAgent", _peer("repo-research-install")),
    PeerCommand("pen-test", "health", "Defensive pen-test scan + enqueue + optional harden agent", _peer("pen-test"), pivotal=True, tags=("security",)),
    PeerCommand("pen-test-digest", "health", "Pen-test mechanical scan only (no agent)", _peer("pen-test-digest"), tags=("security",)),
    PeerCommand("pen-test-status", "health", "Pen-test last run + product-forge target", _peer("pen-test-status"), tags=("security",)),
    PeerCommand("dual-research", "health", "Efficiency + output research probe", _peer("dual-research"), pivotal=True),
    PeerCommand("dual-research-status", "health", "Dual research last run", _peer("dual-research-status")),
    PeerCommand("company-org", "health", "Company teams→roles gap audit + digest", _peer("company-org"), pivotal=True, tags=("org",)),
    PeerCommand("company-org-md", "health", "Refresh notes/COMPANY_TEAMS.md", _peer("company-org-md"), tags=("org",)),
    PeerCommand("company-org-enqueue", "health", "Enqueue missing company roles", _peer("company-org-enqueue"), tags=("org",)),
    PeerCommand("investigate-force", "health", "Overseer now (ignore cooldown)", _peer("investigate-force"), pivotal=True),
    PeerCommand("investigate-status", "health", "Overseer cooldown + last run", _peer("investigate-status")),
    PeerCommand("self-heal", "health", "Scan bottlenecks + apply mechanical heals", _peer("self-heal"), pivotal=True),
    PeerCommand("self-heal-scan", "health", "Detect bottlenecks only", _peer("self-heal-scan")),
    PeerCommand("self-heal-status", "health", "Bottleneck registry table", _peer("self-heal-status")),
    PeerCommand("playbook", "health", "Ingest errors + show instant fixes from live context", _peer("playbook"), pivotal=True),
    PeerCommand("playbook-lookup", "health", "Match error text to playbook fixes", _peer("playbook-lookup"), pivotal=True),
    PeerCommand("playbook-sync", "health", "Regenerate notes/AGENT_ERROR_PLAYBOOK.md", _peer("playbook-sync")),
    PeerCommand("playbook-add", "health", "Add manual playbook entry", _peer("playbook-add")),
    PeerCommand("watch", "health", "Live peer-loop terminal dashboard", _peer("watch"), pivotal=True),
    PeerCommand("status", "health", "One-shot peer-loop snapshot", _peer("status")),
    PeerCommand("poke", "health", "Wake blocked peer loop (touch signal)", _peer("poke")),
    PeerCommand("check", "verify", "peer_orchestrate self-check (primary verify gate)", _peer("check"), pivotal=True),
    PeerCommand("test", "verify", "Full unittest discover -s tests", ("python3", "-m", "unittest", "discover", "-s", "tests", "-q"), pivotal=True),
    PeerCommand("test-quick", "verify", "Fast automation + worktree/constraints/grid/last_cycle_poison + self_check_fail_ttl_soft tests", ("python3", "-m", "unittest", "tests.test_automation", "tests.test_run_peer_tasks", "tests.test_peer_worktree", "tests.test_peer_pen_test", "tests.test_peer_tasks_constraints", "tests.test_factory_grid", "tests.test_peer_last_cycle_poison", "tests.test_self_check_fail_ttl_soft", "-q"), pivotal=True),
    PeerCommand("verify-gate", "verify", "Run configured verify_commands from config", _py("run_peer_tasks.py"), pivotal=True),
    PeerCommand("audit", "verify", "Adapt self-audit (script + config + outputs)", _peer("audit"), pivotal=True),
    PeerCommand("audit-json", "verify", "Adapt audit JSON to stdout", _peer("audit-json")),
    PeerCommand("comms-verify", "verify", "Comms kit self-test gate", _peer("comms-verify")),
    PeerCommand("compact-queue", "queue", "Strip adapt dupes, dedupe, cap Active to 12", _py("peer_commands.py", "inner", "compact-queue"), pivotal=True),
    PeerCommand("sync-queue", "queue", "Heal WORK_QUEUE ↔ context drift", _py("peer_commands.py", "inner", "sync-queue"), pivotal=True),
    PeerCommand("queue-status", "queue", "Open item count + source", _py("peer_commands.py", "inner", "queue-status")),
    PeerCommand("adapt", "adapt", "Quick adapt heal (cached verify)", _peer("adapt"), pivotal=True),
    PeerCommand("adapt-deep", "adapt", "Full re-probe + rewrite profiles", _peer("adapt-deep")),
    PeerCommand("adapt-all", "adapt", "Adapt every registry repo", _peer("adapt-all"), pivotal=True),
    PeerCommand("improve-plan", "improve", "Write improve plan prompt only", _peer("improve-plan")),
    PeerCommand("improve-run", "improve", "Write improve execute prompt only", _peer("improve-run")),
    PeerCommand("improve-write", "improve", "Plan + execute + write + research (one shot)", _py("automation_improve.py", "--write", "--research", "--plan", "--execute"), pivotal=True),
    PeerCommand("improve-status", "improve", "Improve daemon + horizon board", _peer("improve-status"), pivotal=True),
    PeerCommand("improve-watch", "improve", "Live IMPROVE_HORIZON refresh", _peer("improve-watch")),
    PeerCommand("trends", "improve", "Refresh industry trends doc", _py("automation_research.py", "--refresh", "--write"), pivotal=True),
    PeerCommand("research", "improve", "Trend scan + kit gap mapping", _peer("research", "--write")),
    PeerCommand("progress", "factory", "Factory readiness score (real outcomes)", _peer("progress"), pivotal=True),
    PeerCommand("factory-a-plus", "factory", "Factory A+ phase scoreboard", _py("peer_factory_a_plus.py"), pivotal=True),
    PeerCommand("factory-a-plus-install", "factory", "Install A+ queue items + demote theater + shadow test cleanup", _py("peer_factory_a_plus.py", "--phase0", "--write")),
    PeerCommand("product", "factory", "External-proof sprint + registry fanout", _peer("product")),
    PeerCommand("product-status", "factory", "Product drive cooldown + queue", _peer("product-status")),
    PeerCommand("factory-sprint", "factory", "Launch external-repo cursor-agent lanes", _peer("factory-sprint")),
    PeerCommand("factory-fanout", "factory", "Parallel adapt probe on registry repos", _peer("factory-fanout")),
    PeerCommand("agents", "factory", "8-niche agent board", _peer("agents")),
    PeerCommand("plan", "factory", "Dry-run peer orchestration prompt", _peer("plan"), pivotal=True),
    PeerCommand("ensure-pool", "worktree", "Create parallel worktree pool", _peer("ensure-pool", "--count", "8"), pivotal=True),
    PeerCommand("worktree-list", "worktree", "List git worktrees", _py("peer_worktree.py", "list")),
    PeerCommand("stall-pivot", "worktree", "Preview stall-pivot prompt", _peer("stall-pivot")),
    PeerCommand("install", "daemon", "Install peer-loop LaunchAgent", _peer("install"), pivotal=True),
    PeerCommand("improve-install", "daemon", "Install improve-loop LaunchAgent", _peer("improve-install"), pivotal=True),
    PeerCommand("dashboard-install", "daemon", "Install dashboard LaunchAgent", _peer("dashboard-install")),
    PeerCommand("loop", "daemon", "Peer forever loop (foreground)", _peer("loop")),
    PeerCommand("improve-loop", "daemon", "Improve forever loop (foreground)", _peer("improve-loop")),
    PeerCommand("once", "daemon", "Single peer-loop cycle", _peer("once")),
    PeerCommand("ram-status", "ram", "RAM budget stats + pressure level", _py("dgx_ram_budget.py")),
    PeerCommand("ram-purge", "ram", "Rebalance RAM (trim storms + productive fill)", _py("dgx_ram_budget.py", "--rebalance"), tags=("danger",)),
    PeerCommand("ram-cap-flags", "ram", "Show RAM dispatch_allowed + agent cap", _py("dgx_ram_budget.py", "--ram-snapshot")),
    PeerCommand("ram-govern", "ram", "Priority governor — evict low tier or fill high", _py("dgx_ram_budget.py", "--govern")),
    PeerCommand("autonomous-repair", "ops", "Mechanical repair pass (dedupe, cache, git)", _py("peer_commands.py", "inner", "autonomous-repair"), pivotal=True),
    PeerCommand("dgx-status", "ram", "DGX watch snapshot", _peer("dgx-status")),
    PeerCommand("dgx-watch", "ram", "DGX watch loop", _peer("dgx-watch")),
    PeerCommand("debrief", "ops", "AAR / post-mortem + KPI snapshot", _peer("debrief")),
    PeerCommand("flaw-scan", "ops", "Daily flaw-scan status", _peer("flaw-scan")),
    PeerCommand("flaw-scan-preview", "ops", "Print flaw-scan orchestrator prompt", _peer("flaw-scan-preview")),
    PeerCommand("comms-init", "ops", "Init GLink bus + agent vaults", _peer("comms-init")),
    PeerCommand("comms-bus", "ops", "Tail structured comms bus", _peer("comms-bus")),
    PeerCommand("export-kit", "ops", "Tar automation kit to dist/", _peer("export")),
    PeerCommand("commands-list", "meta", "List all peer commands (this registry)", _py("peer_commands.py", "--list")),
    PeerCommand("commands-build", "meta", "Command Builder agent prompt (peer CLI recipes only)", _py("peer_command_builder.py", "--prompt"), pivotal=True, tags=("commands", "dev")),
    PeerCommand("commands-digest", "meta", "Refresh notes/COMMAND_BUILDER.md gap probe", _py("peer_command_builder.py", "--digest")),
]

COMPOUND_STEPS: dict[str, list[str]] = {
    "bootstrap": ["install-all", "self-heal", "compact-queue", "check", "digest"],
    "heal-all": ["self-heal", "compact-queue", "sync-queue", "verify-gate"],
    "green": ["check", "progress", "self-heal-scan"],
    "install-all": ["install", "improve-install", "oversight-install", "repo-research-install"],
    "pre-dispatch": ["compact-queue", "plan-gate", "check", "ensure-pool"],
    "post-cycle": ["verify-gate", "done-gate", "self-heal", "digest"],
    "standup": ["digest", "improve-status", "progress", "self-heal-status"],
    "noop-break": ["compact-queue", "poke", "investigate-force"],
    "stagnation-break": ["heal-all", "noop-break", "progress"],
    "factory-a-plus-init": ["factory-a-plus", "factory-a-plus-install", "compact-queue", "sync-queue"],
    "commands-sync": ["commands-md", "check"],
    "dev-fast": ["compact-queue", "test-quick", "check"],
    "dev-heal": ["self-heal", "commands-sync"],
}

INNER_RUNNERS: dict[str, Callable[[], tuple[int, str]]] = {}


def _register_inner(name: str, fn: Callable[[], tuple[int, str]]) -> None:
    INNER_RUNNERS[name] = fn


def _run_argv(argv: tuple[str, ...], *, dry_run: bool = False) -> tuple[int, str]:
    if not argv:
        return 0, "(compound — no argv)"
    cmd = list(argv)
    if dry_run:
        return 0, " ".join(cmd)
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), check=False)
        return proc.returncode, " ".join(cmd)
    except OSError as exc:
        return 1, str(exc)


def _run_land_proof_mark() -> str:
    """OVERSEER_COMPACT_LAND_PROOF_MARK_2026_09_04 — close Mac-reopened theater.

    compact-queue / heal-all / noop-break must re-close landed flaw-research
    needles when Mac rsync rewrites context/WQ opens. Without this, queue_fp
    stays sticky on 3 theater items while scripts are already fixed.
    """
    mark = SCRIPTS / "_mark_flaw_research_landed.py"
    if not mark.is_file():
        return "land-proof-mark=skip (missing)"
    try:
        proc = subprocess.run(
            [sys.executable, str(mark)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        marked = 0
        open_needles = 0
        raw = (proc.stdout or "").strip()
        if raw:
            data = json.loads(raw)
            for key in ("wq", "ctx"):
                block = data.get(key) or {}
                marked += int(block.get("marked") or 0)
                open_needles += int(block.get("open_needles") or 0)
        if proc.returncode != 0 and not raw:
            return f"land-proof-mark=rc{proc.returncode}"
        return f"land-proof-mark={marked} open_needles={open_needles}"
    except Exception as exc:  # noqa: BLE001
        return f"land-proof-mark=err:{exc}"


def _compact_queue_inner() -> tuple[int, str]:
    try:
        removed, actions = auto.compact_executable_queue(write=True, max_active=12)
        land = _run_land_proof_mark()
        open_n = len(auto.open_work_items().open_items)
        parts = [f"removed={removed}", f"open={open_n}"]
        if actions:
            parts.append("; ".join(actions))
        parts.append(land)
        return 0, " ".join(parts)
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def _sync_queue_inner() -> tuple[int, str]:
    try:
        import automation_adapt as adapt

        healed, warns = adapt.heal_queue_drift(root=ROOT, write=True)
        return 0, f"healed={len(healed)} warns={len(warns)}"
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


def _queue_status_inner() -> tuple[int, str]:
    q = auto.open_work_items()
    preview = "; ".join(i[:50] for i in q.open_items[:4])
    return 0, f"source={q.source} open={len(q.open_items)} preview={preview}"


def _autonomous_repair_inner() -> tuple[int, str]:
    try:
        import autonomous_repair as ar

        lines: list[str] = []

        def log_fn(msg: str) -> None:
            lines.append(msg)

        results = ar.run_mechanical_repairs(log_fn=log_fn)
        detail = "; ".join(results) if results else "no actions"
        return 0, detail
    except Exception as exc:  # noqa: BLE001
        return 1, str(exc)


_register_inner("compact-queue", _compact_queue_inner)
_register_inner("sync-queue", _sync_queue_inner)
_register_inner("queue-status", _queue_status_inner)
_register_inner("autonomous-repair", _autonomous_repair_inner)


def command_by_id(cmd_id: str) -> PeerCommand | None:
    for cmd in COMMANDS:
        if cmd.id == cmd_id:
            return cmd
    return None


def list_commands(*, pivotal_only: bool = False) -> list[PeerCommand]:
    if pivotal_only:
        return [c for c in COMMANDS if c.pivotal]
    return list(COMMANDS)


def run_command(cmd_id: str, *, dry_run: bool = False) -> RunReport:
    report = RunReport(command_id=cmd_id)

    if cmd_id in INNER_RUNNERS:
        if dry_run:
            report.add(step=cmd_id, rc=0, detail="(dry-run inner)")
            return report
        rc, detail = INNER_RUNNERS[cmd_id]()
        report.add(step=cmd_id, rc=rc, detail=detail)
        return report

    if cmd_id in COMPOUND_STEPS:
        for step_id in COMPOUND_STEPS[cmd_id]:
            sub = run_command(step_id, dry_run=dry_run)
            for s in sub.steps:
                report.add(step=s["step"], rc=s["rc"], detail=s.get("detail", ""))
        return report

    cmd = command_by_id(cmd_id)
    if cmd is None:
        report.add(step=cmd_id, rc=1, detail="unknown command")
        return report

    rc, detail = _run_argv(cmd.argv, dry_run=dry_run)
    report.add(step=cmd.id, rc=rc, detail=detail)
    return report


def _peer_doc(*args: str) -> str:
    return "./scripts/peer " + " ".join(args) if args else "./scripts/peer"


def format_markdown() -> str:
    lines = [
        "# Agent commands — pivotal repetitive tasks",
        "",
        "_Generated from `scripts/peer_commands.py`. Prefer `./scripts/peer <id>` — agents should not reinvent these loops._",
        "",
        "## Compound (run these first)",
        "",
        "| Command | Description |",
        "|---------|-------------|",
    ]
    for cmd in COMMANDS:
        if cmd.id in COMPOUND_STEPS:
            lines.append(f"| `{cmd.id}` | {cmd.description} |")
    lines.extend(["", "## Pivotal one-shots", ""])
    by_cat: dict[str, list[PeerCommand]] = {}
    for cmd in COMMANDS:
        if cmd.pivotal and cmd.id not in COMPOUND_STEPS:
            by_cat.setdefault(cmd.category, []).append(cmd)
    for cat in sorted(by_cat):
        lines.append(f"### {cat}")
        lines.append("")
        for cmd in by_cat[cat]:
            if cmd.argv and cmd.argv[0] == str(PEER):
                argv = _peer_doc(*cmd.argv[1:])
            elif cmd.argv:
                argv = " ".join(cmd.argv).replace(str(ROOT) + "/", "")
            else:
                argv = f"(compound: {', '.join(COMPOUND_STEPS.get(cmd.id, []))})"
            lines.append(f"- **`{cmd.id}`** — {cmd.description}")
            lines.append(f"  - `{argv}`")
        lines.append("")
    lines.extend(
        [
            "## Agent recipes",
            "",
            "| When | Run |",
            "|------|-----|",
            "| Cold start / after reboot | `./scripts/peer bootstrap` |",
            "| Before spawning cursor-agent | `./scripts/peer pre-dispatch` (includes plan-gate) |",
            "| Before first edit in session | `./scripts/peer plan-gate --role ROLE` |",
            "| Before marking DONE | `./scripts/peer done-gate --expected \"...\" --actual \"...\"` |",
            "| After agent cycle lands diff | `./scripts/peer post-cycle` (includes done-gate) |",
            "| Noop / queue fingerprint stuck | `./scripts/peer noop-break` |",
            "| Overseer stagnation dispatch | `./scripts/peer stagnation-break` |",
            "| Daily standup / human update | `./scripts/peer standup` |",
            "| Verify gate red | `./scripts/peer heal-all` then `./scripts/peer test-quick` |",
            "| Full health check | `./scripts/peer green` |",
            "",
            "## Meta",
            "",
            "```bash",
            "./scripts/peer commands-list",
            "./scripts/peer commands-list --pivotal",
            "python3 scripts/peer_commands.py run heal-all --dry-run",
            "python3 scripts/peer_commands.py --write-md",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_markdown() -> Path:
    AGENT_COMMANDS_MD.parent.mkdir(parents=True, exist_ok=True)
    AGENT_COMMANDS_MD.write_text(format_markdown(), encoding="utf-8")
    return AGENT_COMMANDS_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Peer command registry for agents")
    parser.add_argument("--list", action="store_true", help="List commands")
    parser.add_argument("--pivotal", action="store_true", help="With --list: pivotal only")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--write-md", action="store_true", help="Write notes/AGENT_COMMANDS.md")
    parser.add_argument("subcmd", nargs="?", help="run | inner")
    parser.add_argument("command_id", nargs="?", help="Command id")
    parser.add_argument("--dry-run", action="store_true", help="Print steps only")
    args = parser.parse_args()

    if args.write_md:
        path = write_markdown()
        print(f"wrote {path}")
        return 0

    if args.list:
        cmds = list_commands(pivotal_only=args.pivotal)
        if args.json:
            print(json.dumps([asdict(c) for c in cmds], indent=2))
        else:
            for cmd in cmds:
                tag = " *" if cmd.pivotal else ""
                print(f"{cmd.id:22} [{cmd.category:10}]{tag} {cmd.description}")
        return 0

    if args.subcmd == "inner" and args.command_id:
        if args.command_id not in INNER_RUNNERS:
            print(f"unknown inner: {args.command_id}", file=sys.stderr)
            return 1
        rc, detail = INNER_RUNNERS[args.command_id]()
        print(detail)
        return rc

    if args.subcmd == "run" and args.command_id:
        report = run_command(args.command_id, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(asdict(report), indent=2))
        else:
            for step in report.steps:
                status = "ok" if step["rc"] == 0 else "FAIL"
                print(f"[{status}] {step['step']}: {step.get('detail', '')[:120]}")
        return 0 if report.ok else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
