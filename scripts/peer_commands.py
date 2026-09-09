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
    PeerCommand("bootstrap", "compound", "Cold start: install daemons → self-heal → compact → check → digest", (), pivotal=True, tags=("life", "start", "daemon")),
    PeerCommand(
        "heal-all",
        "compound",
        "Full mechanical heal: self-heal → compact → sync → memory-pack-gate → verify gate",
        (),
        pivotal=True,
        tags=("life", "heal"),
    ),
    PeerCommand("green", "compound", "Health gate: check + progress + self-heal-scan (exit 1 if blocked)", (), pivotal=True, tags=("life", "verify", "health")),
    PeerCommand("install-all", "compound", "Install peer + improve LaunchAgents", (), pivotal=True, tags=("life", "daemon")),
    PeerCommand(
        "pre-dispatch",
        "compound",
        "Before agent: compact → memory-pack-gate → plan-gate → check → ensure-pool",
        (),
        pivotal=True,
        tags=("dispatch", "gate"),
    ),
    PeerCommand("post-cycle", "compound", "After agent cycle: verify → self-heal → digest", (), pivotal=True, tags=("dispatch",)),
    PeerCommand("standup", "compound", "Morning standup: digest → rule-shutdown-digest → improve-status → progress → self-heal-status", (), pivotal=True, tags=("life", "status")),
    PeerCommand("noop-break", "compound", "Break noop: compact → poke → investigate-force", (), pivotal=True, tags=("life", "noop")),
    PeerCommand(
        "stagnation-break",
        "compound",
        "Overseer stagnation: heal-all → noop-break → progress",
        (),
        pivotal=True,
        tags=("life", "noop", "oversight", "stagnation"),
    ),
    PeerCommand(
        "soft-hub-writeback",
        "compound",
        "After Soft Soft CaaS land: scoreboard → sync-queue → poke (hub writeback; break Soft Soft-without-WQ noop)",
        (),
        pivotal=True,
        tags=("life", "noop", "top10", "newdrop"),
    ),
    PeerCommand(
        "soft-soft-land-status",
        "compound",
        "Soft Soft status: Active Soft Soft opens + latest INTEGRATION_PROOF_*_SOFT mtimes → queue-status",
        (),
        pivotal=True,
        tags=("life", "top10", "newdrop", "status"),
    ),
    PeerCommand(
        "soft-soft-status",
        "queue",
        "Print Active Soft Soft opens + latest Newdrop Soft Soft proof mtimes",
        _py("peer_commands.py", "inner", "soft-soft-status"),
        tags=("top10", "newdrop", "status"),
    ),
    PeerCommand("commands-sync", "compound", "After command edits: regenerate AGENT_COMMANDS.md → self-check", (), pivotal=True, tags=("dev", "commands")),
    PeerCommand(
        "commands-cycle",
        "compound",
        "Wake Command Builder: harvest gaps → write digest + agent prompt",
        (),
        pivotal=True,
        tags=("dev", "commands"),
    ),
    PeerCommand("dev-fast", "compound", "Fast dev gate: compact → test-quick → check", (), pivotal=True, tags=("dev", "speed")),
    PeerCommand("dev-heal", "compound", "Dev recovery: self-heal → commands-sync", (), pivotal=True, tags=("dev", "heal")),
    PeerCommand(
        "idle-gate",
        "compound",
        "Healthy-idle affirm: progress → compact-queue → pen-test-digest",
        (),
        pivotal=True,
        tags=("life", "health"),
    ),
    PeerCommand("plan-gate", "agent", "Plan gate — all agent-vs-human countermeasures before edit", _peer("plan-gate"), pivotal=True, tags=("dispatch", "gate", "plan")),
    PeerCommand("done-gate", "agent", "Done gate — diagnose + compare before DONE", _peer("done-gate"), pivotal=True, tags=("dispatch", "gate", "done")),
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
    PeerCommand(
        "lessons",
        "agent",
        "Lessons curator status (institutional memory)",
        _py("peer_lessons.py", "--status"),
        pivotal=True,
        tags=("memory",),
    ),
    PeerCommand(
        "lessons-harvest",
        "agent",
        "Mine logs/journals → fold lessons (no prune)",
        _py("peer_lessons.py", "--harvest"),
        pivotal=True,
        tags=("memory", "heal"),
    ),
    PeerCommand(
        "lessons-squeeze",
        "agent",
        "Lossless squeeze shared learnings (facts_preserved)",
        _py("peer_lessons.py", "--squeeze", "--write"),
        pivotal=True,
        tags=("memory",),
    ),
    PeerCommand("memory", "agent", "Refresh MEMORY_SPAN.md", _peer("memory")),
    PeerCommand("memory-record", "agent", "Append memory journal fact", _peer("memory-record"), pivotal=True),
    PeerCommand("memory-recall", "agent", "Recall memory tiers", _peer("memory-recall"), pivotal=True),
    PeerCommand(
        "memory-compress",
        "agent",
        "Lossless additive whole-repo memory pack (notes/memory_artifacts)",
        _py("peer_memory_compress.py", "--compress"),
        pivotal=True,
        tags=("memory",),
    ),
    PeerCommand(
        "memory-compress-verify",
        "agent",
        "Verify lossless memory pack round-trip (deep expand)",
        _py("peer_memory_compress.py", "--verify"),
        pivotal=True,
        tags=("memory", "verify"),
    ),
    PeerCommand(
        "memory-pack-gate",
        "agent",
        "Cheap pack integrity gate (heal/pre-dispatch; soft if no pack)",
        (),
        pivotal=True,
        tags=("memory", "verify", "heal"),
    ),
    PeerCommand(
        "role-state",
        "agent",
        "Thin role state JSON (assignment/blocked/files/verify)",
        _peer("role-state"),
        pivotal=True,
        tags=("memory", "amnesia", "roles"),
    ),
    PeerCommand(
        "niche-domain-classify",
        "agent",
        "Domain classifier — free-local NB checkpoint + keyword fallback",
        _peer("niche-domain-classify"),
        pivotal=True,
        tags=("memory", "niche", "librarian"),
    ),
    PeerCommand(
        "memory-audit",
        "agent",
        "Flag uncited worker claims vs pack/SoT (mechanical grep)",
        _py("peer_memory_auditor.py"),
        pivotal=True,
        tags=("memory", "amnesia"),
    ),
    PeerCommand(
        "memory-quiz",
        "agent",
        "Anti-amnesia SoT needle quiz (fail → heal hint)",
        _py("peer_memory_quiz.py", "--self-check"),
        pivotal=True,
        tags=("memory", "amnesia", "verify"),
    ),
    PeerCommand(
        "memory-health",
        "agent",
        "Pack age / verify / prefer_librarian / Hot vs MEMORY_SPAN",
        _py("peer_memory_health.py"),
        pivotal=True,
        tags=("memory", "amnesia"),
    ),
    PeerCommand(
        "memory-episodic",
        "agent",
        "Episodic jsonl by cycle_id (thin append/get/tail)",
        _py("peer_memory_episodic.py"),
        pivotal=True,
        tags=("memory", "amnesia"),
    ),
    PeerCommand(
        "fact-query",
        "agent",
        "Fact librarian relay (domain SME scoped)",
        _peer("fact-query"),
        pivotal=True,
        tags=("memory", "librarian"),
    ),
    PeerCommand(
        "fact-domains",
        "agent",
        "List repo domain SMEs",
        _peer("fact-domains"),
        pivotal=True,
        tags=("memory", "librarian"),
    ),
    PeerCommand(
        "domain-owners",
        "agent",
        "Regenerate notes/DOMAIN_OWNERS.md from repo_domain_smes.json",
        _peer("domain-owners"),
        pivotal=True,
        tags=("memory", "librarian", "amnesia"),
    ),
    PeerCommand(
        "session-ledger-append",
        "agent",
        "Write-through session ledger (decision/paths/needle before DONE)",
        _peer("session-ledger-append"),
        pivotal=True,
        tags=("memory", "amnesia"),
    ),
    PeerCommand(
        "session-distill",
        "agent",
        "Turn-end cited bullets → PEER_CONVERSATION / last_cycle pins",
        _peer("session-distill"),
        pivotal=True,
        tags=("memory", "amnesia"),
    ),
    PeerCommand(
        "session-claim",
        "agent",
        "Session claim ledger OVERCLAIM-style (session facts)",
        _peer("session-claim"),
        pivotal=True,
        tags=("memory", "amnesia"),
    ),
    PeerCommand(
        "session-sticky-status",
        "agent",
        "Spaced sticky reinject counter (NO-PAY / factory-works / pack≠delete)",
        _peer("session-sticky-status"),
        tags=("memory", "amnesia"),
    ),
    PeerCommand(
        "session-hub-rules",
        "agent",
        "Print hub SoT vs worktree scratch memory rules",
        _peer("session-hub-rules"),
        tags=("memory", "amnesia"),
    ),
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
    PeerCommand(
        "rule-shutdown",
        "health",
        "Rule-change proposals (propose/ack/list/accept/reject) — human closes",
        _py("peer_rule_shutdown.py"),
        pivotal=True,
        tags=("rules", "digest"),
    ),
    PeerCommand(
        "rule-shutdown-digest",
        "health",
        "Refresh notes/RULE_SHUTDOWN_DIGEST.md (daily human review)",
        _py("peer_rule_shutdown.py", "write-digest"),
        pivotal=True,
        tags=("rules", "digest"),
    ),
    PeerCommand(
        "rule-shutdown-expire",
        "health",
        "No-op expire (propose-only — use digest; kept for standup alias)",
        _py("peer_rule_shutdown.py", "write-digest"),
        tags=("rules",),
    ),
    PeerCommand(
        "progress-watch",
        "health",
        "Time+result progress stall → self-heal run_cycle (once)",
        _py("peer_progress_watch.py", "--once"),
        pivotal=True,
        tags=("heal",),
    ),
    PeerCommand(
        "progress-watch-forever",
        "health",
        "Forever progress fingerprint watchdog",
        _py("peer_progress_watch.py", "--forever"),
        tags=("heal",),
    ),
    PeerCommand("playbook", "health", "Ingest errors + show instant fixes from live context", _peer("playbook"), pivotal=True),
    PeerCommand("playbook-lookup", "health", "Match error text to playbook fixes", _peer("playbook-lookup"), pivotal=True),
    PeerCommand("playbook-sync", "health", "Regenerate notes/AGENT_ERROR_PLAYBOOK.md", _peer("playbook-sync")),
    PeerCommand("playbook-add", "health", "Add manual playbook entry", _peer("playbook-add")),
    PeerCommand("watch", "health", "Live peer-loop terminal dashboard", _peer("watch"), pivotal=True),
    PeerCommand("status", "health", "One-shot peer-loop snapshot", _peer("status")),
    PeerCommand("poke", "health", "Wake blocked peer loop (touch signal)", _peer("poke")),
    PeerCommand("check", "verify", "peer_orchestrate self-check (primary verify gate)", _peer("check"), pivotal=True),
    PeerCommand("test", "verify", "Full unittest discover -s tests", ("python3", "-m", "unittest", "discover", "-s", "tests", "-q"), pivotal=True),
    PeerCommand("test-quick", "verify", "Fast automation + worktree/constraints/grid/last_cycle_poison + agent_exit_soft + self_check_fail_ttl_soft tests", ("python3", "-m", "unittest", "tests.test_automation", "tests.test_run_peer_tasks", "tests.test_peer_worktree", "tests.test_peer_pen_test", "tests.test_peer_tasks_constraints", "tests.test_factory_grid", "tests.test_peer_last_cycle_poison", "tests.test_peer_self_heal", "tests.test_agent_exit_soft_land", "tests.test_self_check_fail_ttl_soft", "tests.test_overseer_stag_active_fp", "-q"), pivotal=True),
    PeerCommand("verify-gate", "verify", "Run configured verify_commands from config", _py("run_peer_tasks.py"), pivotal=True),
    PeerCommand("audit", "verify", "Adapt self-audit (script + config + outputs)", _peer("audit"), pivotal=True),
    PeerCommand("audit-json", "verify", "Adapt audit JSON to stdout", _peer("audit-json")),
    PeerCommand("comms-verify", "verify", "Comms kit self-test gate", _peer("comms-verify"), pivotal=True, tags=("comms",)),
    PeerCommand(
        "comms-improve",
        "improve",
        "Comms-kit one-shot: write plan+execute + research (local GLink/bus)",
        _py("automation_comms_improve.py", "--write", "--research"),
        pivotal=True,
        tags=("comms", "improve"),
    ),
    PeerCommand(
        "comms-improve-status",
        "improve",
        "Comms improve daemon + COMMS_HORIZON board",
        _peer("comms-improve-status"),
        pivotal=True,
        tags=("comms", "improve"),
    ),
    PeerCommand(
        "comms-improve-loop",
        "daemon",
        "Comms improve forever loop (foreground)",
        _peer("comms-improve-loop"),
        tags=("comms", "daemon"),
    ),
    PeerCommand(
        "comms-improve-install",
        "daemon",
        "Install comms-improve-loop LaunchAgent",
        _peer("comms-improve-install"),
        pivotal=True,
        tags=("comms", "daemon"),
    ),
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
    PeerCommand("factory-a-plus", "factory", "Factory A+ phase scoreboard", _py("peer_factory_a_plus.py"), pivotal=True, tags=("factory-ai",)),
    PeerCommand("factory-a-plus-install", "factory", "Install A+ queue items + demote theater + shadow test cleanup", _py("peer_factory_a_plus.py", "--phase0", "--write"), tags=("factory-ai",)),
    PeerCommand(
        "a-to-z",
        "factory",
        "Sequencing lock: next open A→Z factory kit phase",
        _py("peer_factory_a_to_z.py"),
        pivotal=True,
        tags=("factory", "factory-ai", "sequencing"),
    ),
    PeerCommand(
        "kit-run",
        "factory",
        "Unsupervised kit compound: adapt → verify → worktree → PR/blocked → writeback",
        _py("factory_kit_run.py"),
        pivotal=True,
        tags=("factory", "factory-ai", "sequencing"),
    ),
    PeerCommand(
        "kit-run-list",
        "factory",
        "List registry targets for kit-run",
        _py("factory_kit_run.py", "--list"),
        tags=("factory", "factory-ai"),
    ),
    PeerCommand(
        "kit-heal-false-green",
        "factory",
        "Force A→Z PROOF Status red when green lacks eligible PR/merge_note",
        _py("factory_kit_run.py", "--heal-false-green"),
        pivotal=True,
        tags=("factory", "factory-ai", "sequencing"),
    ),
    PeerCommand(
        "factory-a-plus-init",
        "compound",
        "Factory A+ scoreboard → install queue items → compact/sync",
        (),
        tags=("factory-ai",),
    ),
    PeerCommand("product", "factory", "External-proof sprint + registry fanout", _peer("product"), tags=("product",)),
    PeerCommand("product-status", "factory", "Product drive cooldown + queue", _peer("product-status")),
    PeerCommand("factory-sprint", "factory", "Launch external-repo cursor-agent lanes", _peer("factory-sprint")),
    PeerCommand("factory-fanout", "factory", "Parallel adapt probe on registry repos", _peer("factory-fanout")),
    PeerCommand("agents", "factory", "8-niche agent board", _peer("agents")),
    PeerCommand(
        "niche-mint",
        "factory",
        "On-demand tiny niche: propose/start when agents find a local speedup (see niche_mint.py)",
        _py("niche_mint.py"),
        pivotal=True,
        tags=("factory-ai", "niche", "mint"),
    ),
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
    PeerCommand("commands-md", "meta", "Regenerate notes/AGENT_COMMANDS.md only", _py("peer_commands.py", "--write-md"), tags=("commands", "dev")),
    PeerCommand("commands-build", "meta", "Command Builder agent prompt (peer CLI recipes only)", _py("peer_command_builder.py", "--prompt"), pivotal=True, tags=("commands", "dev")),
    PeerCommand("commands-digest", "meta", "Refresh notes/COMMAND_BUILDER.md gap probe", _py("peer_command_builder.py", "--digest")),
    PeerCommand(
        "commands-harvest",
        "meta",
        "Harvest repeated shell loops → Command Builder gaps + prompt",
        _py("peer_command_builder.py", "--harvest"),
        pivotal=True,
        tags=("commands", "dev"),
    ),
    PeerCommand(
        "factory-dynamics",
        "factory",
        "Snapshot live niche CPU/GPU balance + assist knobs",
        _py("factory_dynamics.py", "--snapshot"),
        pivotal=True,
        tags=("factory-ai", "niche", "dynamics"),
    ),
    PeerCommand(
        "command-coverage",
        "meta",
        "Regenerate command coverage matrix + optional Backlog enqueue",
        _py("command_ecosystem.py", "--write"),
        pivotal=True,
        tags=("meta", "commands", "dev"),
    ),
    # OVERSEER_COVERAGE_GATE_2026_09_08 — fail-closed gaps; replaces python build_coverage inspect loop
    PeerCommand(
        "coverage-gate",
        "meta",
        "Fail-closed CLI wrap coverage (exit 1 if unwrapped gaps)",
        _py("peer_commands.py", "inner", "coverage-gate"),
        pivotal=True,
        tags=("meta", "commands", "dev", "gate"),
    ),
    PeerCommand(
        "command-coverage-enqueue",
        "meta",
        "Coverage write + enqueue top unwrapped scripts to Backlog",
        _py("command_ecosystem.py", "--write", "--enqueue"),
        tags=("meta", "commands", "dev"),
    ),
    PeerCommand(
        "command-dispatch-audit",
        "meta",
        "Audit pre-dispatch/post-cycle vs raw python3 scripts/ in logs",
        _py("command_ecosystem.py", "--dispatch-audit"),
        pivotal=True,
        tags=("meta", "commands", "dispatch"),
    ),
    PeerCommand(
        "command-ecosystem-finish",
        "meta",
        "Write coverage + dispatch audit + hub verbs + mini-app promote scan",
        _py("command_ecosystem.py", "--finish"),
        pivotal=True,
        tags=("meta", "commands", "dev"),
    ),
    PeerCommand(
        "mini-app-promote",
        "meta",
        "List registered mini-apps that need a peer command wrap",
        _py("command_ecosystem.py", "--mini-app-promote"),
        tags=("meta", "commands", "dev"),
    ),
    PeerCommand(
        "niche-bank-status",
        "factory",
        "Niche bank train status / ready counts",
        _py("niche_bank_train.py", "--status"),
        pivotal=True,
        tags=("factory-ai", "niche"),
    ),
    PeerCommand(
        "niche-bank-eval",
        "factory",
        "Niche bank heldout + live WORK_QUEUE smoke",
        _py("niche_bank_eval.py"),
        pivotal=True,
        tags=("factory-ai", "niche"),
    ),
    PeerCommand(
        "niche-serve",
        "factory",
        "Composer route+serve (pass text after --)",
        _py("niche_composer.py", "--serve"),
        tags=("factory-ai", "niche"),
    ),
    PeerCommand(
        "niche-assist-once",
        "factory",
        "Dynamics + route/serve Active WORK_QUEUE head (fail-soft)",
        _py("niche_assist_once.py"),
        pivotal=True,
        tags=("factory-ai", "niche", "dispatch"),
    ),
    PeerCommand(
        "niche-mint-train",
        "factory",
        "On-demand mint + train (pass --name/--io/--reason after --)",
        _py("niche_mint_train.py"),
        tags=("factory-ai", "niche", "mint"),
    ),
    PeerCommand(
        "top10",
        "factory",
        "Print ranked TOP10_NEXT implement-in-order list",
        _py("peer_top10_next.py", "--list"),
        pivotal=True,
        tags=("factory", "top10", "queue"),
    ),
    PeerCommand(
        "top10-refresh",
        "factory",
        "Mechanical TOP10_NEXT re-rank (open first, renumber, write-back)",
        _py("peer_top10_next.py", "--refresh"),
        pivotal=True,
        tags=("factory", "top10", "queue"),
    ),
    PeerCommand(
        "top10-next",
        "factory",
        "Print highest-rank open TOP10_NEXT item only",
        _py("peer_top10_next.py", "--next"),
        pivotal=True,
        tags=("factory", "top10", "queue"),
    ),
    PeerCommand(
        "production-power",
        "factory",
        "Refresh PRODUCTION_POWER_SCOREBOARD.md (honest bars; NO PAY)",
        _py("production_power_scoreboard.py", "--write"),
        pivotal=True,
        tags=("factory", "top10", "scoreboard"),
    ),
    PeerCommand(
        "scoreboard-write",
        "factory",
        "Alias: refresh PRODUCTION_POWER_SCOREBOARD.md",
        _py("production_power_scoreboard.py", "--write"),
        tags=("factory", "top10", "scoreboard"),
    ),
    PeerCommand(
        "agent-build",
        "factory",
        "Agent Builder: provision role+template+match (pass --dry-run/--write/--spec after --)",
        _py("peer_agent_builder.py"),
        pivotal=True,
        tags=("factory", "agent-builder", "dispatch"),
    ),
    PeerCommand(
        "agent-build-list",
        "factory",
        "List agent_roles with template/match coverage",
        _py("peer_agent_builder.py", "--list"),
        tags=("factory", "agent-builder"),
    ),
    PeerCommand(
        "agent-build-validate",
        "factory",
        "Validate one role id has template + match_rules (pass ID after --)",
        _py("peer_agent_builder.py", "--validate"),
        tags=("factory", "agent-builder"),
    ),
    PeerCommand(
        "agent-who",
        "factory",
        "Task→worker map: which role/template pick_role+match would select",
        _py("peer_agent_builder.py", "--who"),
        pivotal=True,
        tags=("factory", "agent-builder", "dispatch"),
    ),
    # OVERSEER_COMPRESSION_KEEP_ALIVE_2026_09_05 — --check only (never bare forever)
    PeerCommand(
        "compression-keep-alive",
        "factory",
        "Compression keep-alive acceptance JSON (--check; no fanout/forever)",
        _py("compression_keep_alive.py", "--check"),
        pivotal=True,
        tags=("factory", "compression", "keep-alive"),
    ),
    # OVERSEER_COMMAND_BUILDER_HARVEST_WRAP_2026_09_08 — top coverage gaps (safe defaults)
    PeerCommand(
        "compression-ladder",
        "compound",
        "T0–T6 compression probes as JSON (status ladder; no train/forever)",
        (),
        pivotal=True,
        tags=("factory", "compression", "ladder"),
    ),
    PeerCommand(
        "bitnet-fp4-expert-rss-smoke",
        "factory",
        "CLEAN FP4 expert RSS/mmap smoke meters (--json)",
        _py("bitnet_fp4_expert_rss_smoke.py", "--json"),
        pivotal=True,
        tags=("factory", "compression", "bitnet"),
    ),
    PeerCommand(
        "compression-ablation-schedule",
        "factory",
        "OA/Hyperband ablation schedule dry-run (--json; no --write)",
        _py("compression_ablation_schedule.py", "--json"),
        pivotal=True,
        tags=("factory", "compression"),
    ),
    PeerCommand(
        "compression-auto-train",
        "factory",
        "Compression auto-train gate status (--check; no --start/--watch)",
        _py("compression_auto_train.py", "--check"),
        pivotal=True,
        tags=("factory", "compression", "train"),
    ),
    PeerCommand(
        "compression-gpu-worker",
        "factory",
        "Compression GPU worker one cycle (--once; no --forever)",
        _py("compression_gpu_worker.py", "--once"),
        pivotal=True,
        tags=("factory", "compression", "gpu"),
    ),
    PeerCommand(
        "compression-logit-expand",
        "factory",
        "Expand T3 teacher logit bank from peer/factory text",
        _py("compression_logit_expand.py"),
        pivotal=True,
        tags=("factory", "compression", "t3"),
    ),
    PeerCommand(
        "compression-result-watch",
        "factory",
        "Compression result stall watchdog one tick (--once; no --forever)",
        _py("compression_result_watch.py", "--once"),
        pivotal=True,
        tags=("factory", "compression", "watch"),
    ),
    PeerCommand(
        "compression-stress-suite",
        "factory",
        "Post-train stress bars JSON (--json; no --write)",
        _py("compression_stress_suite.py", "--json"),
        pivotal=True,
        tags=("factory", "compression", "stress"),
    ),
    PeerCommand(
        "compression-t0-pack",
        "factory",
        "T0 packing proof (--json)",
        _py("compression_t0_pack.py", "--json"),
        pivotal=True,
        tags=("factory", "compression", "t0"),
    ),
    PeerCommand(
        "compression-t1-share",
        "factory",
        "T1 share-factor ablation (--json)",
        _py("compression_t1_share.py", "--json"),
        pivotal=True,
        tags=("factory", "compression", "t1"),
    ),
    PeerCommand(
        "compression-t2-svd",
        "factory",
        "T2 SVD-TieStack probe (--json)",
        _py("compression_t2_svd.py", "--json"),
        pivotal=True,
        tags=("factory", "compression", "t2"),
    ),
    PeerCommand(
        "compression-t3-bitdistill",
        "factory",
        "T3 BitDistill logit-bank probe (--json)",
        _py("compression_t3_bitdistill.py", "--json"),
        pivotal=True,
        tags=("factory", "compression", "t3"),
    ),
    PeerCommand(
        "compression-t4-scale",
        "factory",
        "T4 scale U/N rung (--json)",
        _py("compression_t4_scale.py", "--json"),
        pivotal=True,
        tags=("factory", "compression", "t4"),
    ),
    PeerCommand(
        "compression-t5-serve",
        "factory",
        "T5 serve/residency smoke (--json)",
        _py("compression_t5_serve.py", "--json"),
        pivotal=True,
        tags=("factory", "compression", "t5"),
    ),
    PeerCommand(
        "compression-t6-quality",
        "factory",
        "T6 heldout quality toy (--json)",
        _py("compression_t6_quality.py", "--json"),
        pivotal=True,
        tags=("factory", "compression", "t6"),
    ),
    PeerCommand(
        "compression-train-profile",
        "factory",
        "DGX/CLEAN train profile-once meters (--json)",
        _py("compression_train_profile.py", "--json"),
        pivotal=True,
        tags=("factory", "compression", "profile"),
    ),
    # OVERSEER_COMMAND_BUILDER_RESIDUAL_WRAP_2026_09_08 — hub verbs + factory gaps
    PeerCommand(
        "github-feedback-fetch",
        "factory",
        "Pull sanitized GitHub feedback inbox (gh CLI)",
        _py("github_feedback.py", "fetch"),
        pivotal=True,
        tags=("factory", "product", "github"),
    ),
    PeerCommand(
        "github-feedback-list",
        "factory",
        "List sanitized GitHub feedback inbox",
        _py("github_feedback.py", "list"),
        pivotal=True,
        tags=("factory", "product", "github"),
    ),
    PeerCommand(
        "github-feedback-render",
        "factory",
        "Render untrusted GitHub feedback markdown for peer review",
        _py("github_feedback.py", "render"),
        pivotal=True,
        tags=("factory", "product", "github"),
    ),
    PeerCommand(
        "production-power",
        "factory",
        "Refresh notes/PRODUCTION_POWER_SCOREBOARD.md (--write)",
        _py("production_power_scoreboard.py", "--write"),
        pivotal=True,
        tags=("factory", "product", "scoreboard"),
    ),
    PeerCommand(
        "scoreboard-write",
        "factory",
        "Alias: refresh PRODUCTION_POWER_SCOREBOARD (--write)",
        _py("production_power_scoreboard.py", "--write"),
        pivotal=True,
        tags=("factory", "product", "scoreboard"),
    ),
    PeerCommand(
        "niche-bank-compress",
        "factory",
        "Compress niche-bank weights to NVFP4-ish packed sidecars",
        _py("niche_bank_compress.py"),
        pivotal=True,
        tags=("factory-ai", "niche", "compress"),
    ),
    PeerCommand(
        "niche-hot-path",
        "factory",
        "Niche hot-path inventory JSON (N01 practice gate status)",
        _py("niche_hot_path.py", "--inventory", "--json"),
        pivotal=True,
        tags=("factory-ai", "niche", "hot-path"),
    ),
    PeerCommand(
        "factory-niche-runtime",
        "factory",
        "Factory niche runtime route+serve snapshot (--json)",
        _py("factory_niche_runtime.py", "--json"),
        pivotal=True,
        tags=("factory-ai", "niche", "runtime"),
    ),
    PeerCommand(
        "factory-lora-train",
        "factory",
        "Factory LoRA scaffold (pass --train/--ask after --; no default train)",
        _py("factory_lora_train.py"),
        tags=("factory-ai", "lora", "train"),
    ),
    PeerCommand(
        "compression-train-rung0",
        "factory",
        "Compression rung0 skeleton once (--once; no --train/--forever)",
        _py("compression_train_rung0.py", "--once"),
        pivotal=True,
        tags=("factory", "compression", "rung0"),
    ),
    PeerCommand(
        "gpu-profile-once",
        "factory",
        "DGX util + CLEAN FP4 profile-once meters (--json)",
        _py("gpu_profile_once.py", "--json"),
        pivotal=True,
        tags=("factory", "gpu", "profile"),
    ),
    PeerCommand(
        "dgx-resource-priority",
        "factory",
        "DGX RAM/GPU priority snapshot (--snapshot --json)",
        _py("dgx_resource_priority.py", "--snapshot", "--json"),
        pivotal=True,
        tags=("factory", "dgx", "ram"),
    ),
    PeerCommand(
        "niche-domain-classifier-train",
        "factory",
        "Domain classifier heldout eval JSON (--eval-only; no --train)",
        _py("niche_domain_classifier_train.py", "--eval-only", "--json"),
        pivotal=True,
        tags=("factory-ai", "niche", "domain"),
    ),
    PeerCommand(
        "agent-survival",
        "agent",
        "Agent survival briefing compact prompt block",
        _py("peer_agent_survival.py", "--compact"),
        pivotal=True,
        tags=("dispatch", "survival"),
    ),
    # OVERSEER_COMMAND_BUILDER_NEXT18_WRAP_2026_09_08 — remaining coverage gaps
    PeerCommand(
        "cursor-self-improve",
        "improve",
        "Cursor self-improve suggestion dry-run (no paste/AX)",
        _py("cursor_self_improve.py", "--dry-run"),
        pivotal=True,
        tags=("dev", "improve"),
    ),
    PeerCommand(
        "dgx-gpu-compute",
        "ram",
        "DGX GPU compute worker status JSON",
        _py("dgx_gpu_compute.py", "--status", "--json"),
        pivotal=True,
        tags=("life", "dgx", "gpu"),
    ),
    PeerCommand(
        "dgx-gpu-events",
        "ram",
        "DGX GPU event mode snapshot JSON",
        _py("dgx_gpu_events.py", "--snapshot", "--json"),
        pivotal=True,
        tags=("life", "dgx", "gpu"),
    ),
    PeerCommand(
        "dgx-local-ram-guard",
        "ram",
        "On-DGX RAM guard once (trim storms; no forever)",
        _py("dgx_local_ram_guard.py", "--once"),
        pivotal=True,
        tags=("life", "dgx", "ram"),
    ),
    PeerCommand(
        "dgx-ram-events",
        "ram",
        "DGX RAM event mode snapshot JSON",
        _py("dgx_ram_events.py", "--snapshot", "--json"),
        pivotal=True,
        tags=("life", "dgx", "ram"),
    ),
    PeerCommand(
        "dgx-ram-priority",
        "ram",
        "DGX RAM priority snapshot JSON",
        _py("dgx_ram_priority.py", "--snapshot", "--json"),
        pivotal=True,
        tags=("life", "dgx", "ram"),
    ),
    PeerCommand(
        "dgx-utilization",
        "ram",
        "DGX utilization snapshot JSON",
        _py("dgx_utilization.py", "--snapshot", "--json"),
        pivotal=True,
        tags=("life", "dgx", "gpu"),
    ),
    PeerCommand(
        "niche-n01-neural-train",
        "factory",
        "N01 neural niche heldout eval JSON (no --train)",
        _py("niche_n01_neural_train.py", "--eval-only", "--json"),
        pivotal=True,
        tags=("factory-ai", "niche"),
    ),
    PeerCommand(
        "niche-n01-practice",
        "factory",
        "N01 practice heldout eval JSON",
        _py("niche_n01_practice.py", "--eval-only", "--json"),
        pivotal=True,
        tags=("factory-ai", "niche"),
    ),
    # OVERSEER_NICHE_PRACTICE_N02_WRAP_2026_09_08 — peer case already wired; register COMMANDS
    PeerCommand(
        "niche-n02-practice",
        "factory",
        "N02 practice heldout eval JSON (--eval-only; no train/corpus prune)",
        _py("niche_n02_practice.py", "--eval-only", "--json"),
        pivotal=True,
        tags=("factory-ai", "niche"),
    ),
    # OVERSEER_NICHE_DISTILL_VALIDATE_WRAP_2026_09_08 — sole COMMAND_COVERAGE gap; --json schema+floors
    PeerCommand(
        "niche-distill-validate",
        "factory",
        "Niche distill schema + anti-prune floor JSON (no row prune/train)",
        _py("niche_distill_validate.py", "--json"),
        pivotal=True,
        tags=("factory-ai", "niche", "dataset"),
    ),
    # OVERSEER_RESEARCH_CLAIM_ARITH_WRAP_2026_09_08 — sole COMMAND_COVERAGE gap; --check-cache --json (no train/write)
    PeerCommand(
        "research-claim-arith",
        "factory",
        "Arith-only research stack prefilter cache check (--check-cache --json; no train/write)",
        _py("research_claim_arith.py", "--check-cache", "--json"),
        pivotal=True,
        tags=("factory-ai", "research", "arith"),
    ),
    PeerCommand(
        "niche-n03-practice",
        "factory",
        "N03 practice heldout eval JSON",
        _py("niche_n03_practice.py", "--eval-only", "--json"),
        pivotal=True,
        tags=("factory-ai", "niche"),
    ),
    PeerCommand(
        "niche-n07-practice",
        "factory",
        "N07 practice heldout eval JSON",
        _py("niche_n07_practice.py", "--eval-only", "--json"),
        pivotal=True,
        tags=("factory-ai", "niche"),
    ),
    PeerCommand(
        "niche-n08-practice",
        "factory",
        "N08 practice heldout eval JSON",
        _py("niche_n08_practice.py", "--eval-only", "--json"),
        pivotal=True,
        tags=("factory-ai", "niche"),
    ),
    PeerCommand(
        "niche-retrieval",
        "factory",
        "Niche retrieval over bank index (query Active)",
        _py("niche_retrieval.py", "Active"),
        pivotal=True,
        tags=("factory-ai", "niche"),
    ),
    PeerCommand(
        "peer-error-adapt",
        "agent",
        "Error adapt from plan-gate (never idle)",
        _py("peer_error_adapt.py", "--from-gate"),
        pivotal=True,
        tags=("dispatch", "heal"),
    ),
    PeerCommand(
        "peer-glink-paste",
        "agent",
        "GLink paste DONE shrink demo JSON (no paste)",
        _py("peer_glink_paste.py", "done", "--demo", "--json"),
        pivotal=True,
        tags=("dispatch", "comms"),
    ),
    PeerCommand(
        "kit-progress",
        "factory",
        "Kit progress JSON snapshot (no --write)",
        _py("peer_kit_progress.py", "--json"),
        pivotal=True,
        tags=("factory-ai", "progress"),
    ),
    PeerCommand(
        "land-hold",
        "ops",
        "Land-hold age/pause status",
        _py("peer_land_hold.py"),
        pivotal=True,
        tags=("meta", "land"),
    ),
    PeerCommand(
        "improve-poll-cache",
        "improve",
        "Improve poll-cache launcher status (CLEAN overlay path)",
        _py("run_improve_poll_cache.py", "--status"),
        pivotal=True,
        tags=("dev", "improve"),
    ),
]

COMPOUND_STEPS: dict[str, list[str]] = {
    "bootstrap": ["install-all", "self-heal", "compact-queue", "check", "digest"],
    # memory-pack-gate = cheap pack integrity (not full expand) — soft-warn if no pack
    "heal-all": [
        "self-heal",
        "compact-queue",
        "sync-queue",
        "memory-pack-gate",
        "verify-gate",
    ],
    "green": ["check", "progress", "self-heal-scan"],
    "install-all": ["install", "improve-install", "oversight-install", "repo-research-install"],
    "pre-dispatch": [
        "compact-queue",
        "memory-pack-gate",
        "plan-gate",
        "check",
        "ensure-pool",
    ],
    "post-cycle": ["verify-gate", "done-gate", "self-heal", "digest"],
    "standup": ["digest", "rule-shutdown-digest", "improve-status", "progress", "self-heal-status"],
    "noop-break": ["compact-queue", "poke", "investigate-force"],
    "stagnation-break": ["heal-all", "noop-break", "progress"],
    # Soft Soft product land without hub proof/WQ = flat queue_fp noop — OVERSEER_SOFT_HUB_WRITEBACK_2026_09_08
    "soft-hub-writeback": ["production-power", "sync-queue", "poke"],
    # Soft Soft Active + proof mtime glance — OVERSEER_SOFT_SOFT_LAND_STATUS_2026_09_08
    "soft-soft-land-status": ["soft-soft-status", "queue-status"],
    "factory-a-plus-init": ["factory-a-plus", "factory-a-plus-install", "compact-queue", "sync-queue"],
    "commands-sync": ["commands-md", "check"],
    "commands-cycle": ["commands-harvest"],
    "dev-fast": ["compact-queue", "test-quick", "check"],
    "dev-heal": ["self-heal", "commands-sync"],
    "idle-gate": ["progress", "compact-queue", "pen-test-digest"],
    "compression-ladder": [
        "compression-t0-pack",
        "compression-t1-share",
        "compression-t2-svd",
        "compression-t3-bitdistill",
        "compression-t4-scale",
        "compression-t5-serve",
        "compression-t6-quality",
    ],
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


def _soft_soft_status_inner() -> tuple[int, str]:
    """Active Soft Soft opens + newest INTEGRATION_PROOF_NEWDROP_*_SOFT.md mtimes.

    Needle: OVERSEER_SOFT_SOFT_LAND_STATUS_2026_09_08 — replaces repeated
    ``rg Soft Soft WORK_QUEUE`` + ``ls notes/INTEGRATION_PROOF_*_SOFT.md`` loops.
    """
    import time

    lines: list[str] = []
    opens: list[str] = []
    wq = ROOT / "notes" / "WORK_QUEUE.md"
    if wq.is_file():
        body = wq.read_text(encoding="utf-8", errors="replace")
        active = body.split("## Backlog", 1)[0]
        opens = [
            ln.strip()
            for ln in active.splitlines()
            if ln.startswith("- [ ]") and ("Soft Soft" in ln or "soft soft" in ln.lower())
        ]
        lines.append(f"soft_soft_active_open={len(opens)}")
        for ln in opens[:6]:
            title = ln.split("—", 1)[0].strip()
            if len(title) > 90:
                title = title[:87] + "…"
            lines.append(f"  {title}")
    else:
        lines.append("soft_soft_active_open=0 (missing WORK_QUEUE.md)")

    notes = ROOT / "notes"
    proofs = sorted(
        notes.glob("INTEGRATION_PROOF_NEWDROP_*_SOFT.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    lines.append(f"soft_soft_proofs={len(proofs)}")
    now = time.time()
    for p in proofs[:5]:
        age_h = (now - p.stat().st_mtime) / 3600.0
        lines.append(f"  {p.name} age_h={age_h:.2f}")
    detail = "\n".join(lines)
    print(detail)
    return 0, f"soft_soft_open={len(opens)} proofs={len(proofs)}"


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


def _memory_pack_gate_inner() -> tuple[int, str]:
    """Cheap pack integrity for heal/pre-dispatch (not full expand).

    Needle: OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07 — wire pack verify into
    compounds without false-red from deep expand or missing pack.

    Hard-fail only when pack exists and header/json_sha integrity fails.
    Soft-warn (rc=0) when no pack / cache-only advice for deep verify.
    """
    try:
        import peer_memory_health as pmh

        ok, why, detail = pmh.resolve_verify_ok(cheap_integrity=True)
        mode = (detail or {}).get("mode") or "cheap"
        if ok is False:
            return 1, f"FAIL mode={mode} {why}"
        if ok is None:
            return 0, f"warn mode={mode} {why} (deep: ./scripts/peer memory-compress-verify)"
        return 0, f"ok mode={mode} {why}"
    except Exception as exc:  # noqa: BLE001
        # Soft — do not block heal/pre-dispatch on import/IO flukes
        return 0, f"warn memory-pack-gate err:{exc}"


def _coverage_gate_inner() -> tuple[int, str]:
    """Fail-closed CLI wrap coverage (n_gaps must be 0).

    Needle: OVERSEER_COVERAGE_GATE_2026_09_08 — agents re-ran
    ``command-coverage`` + ad-hoc ``build_coverage()`` inspect; this gate
    returns rc=1 when unwrapped CLIs remain.
    """
    try:
        import command_ecosystem as ce

        cov = ce.build_coverage()
        n_gaps = int(cov.get("n_gaps") or 0)
        wrapped = int(cov.get("n_wrapped") or 0)
        n_cli = int(cov.get("n_cli_scripts") or 0)
        detail = f"gaps={n_gaps} wrapped={wrapped} cli={n_cli}"
        if n_gaps > 0:
            top = (cov.get("gaps") or [])[:3]
            stems = ",".join(str(g.get("stem") or "?") for g in top)
            return 1, f"BLOCK {detail} top={stems} → ./scripts/peer commands-cycle"
        return 0, detail
    except Exception as exc:  # noqa: BLE001
        return 1, f"BLOCK coverage-gate err:{exc}"


_register_inner("compact-queue", _compact_queue_inner)
_register_inner("sync-queue", _sync_queue_inner)
_register_inner("queue-status", _queue_status_inner)
_register_inner("soft-soft-status", _soft_soft_status_inner)
_register_inner("autonomous-repair", _autonomous_repair_inner)
_register_inner("memory-pack-gate", _memory_pack_gate_inner)
_register_inner("coverage-gate", _coverage_gate_inner)


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
            "| Before spawning cursor-agent | `./scripts/peer pre-dispatch` (includes memory-pack-gate + plan-gate) |",
            "| Before first edit in session | `./scripts/peer plan-gate --role ROLE` |",
            "| Before marking DONE | `./scripts/peer done-gate --expected \"...\" --actual \"...\"` |",
            "| After agent cycle lands diff | `./scripts/peer post-cycle` (includes done-gate) |",
            "| Noop / queue fingerprint stuck | `./scripts/peer noop-break` |",
            "| Overseer stagnation dispatch | `./scripts/peer stagnation-break` |",
            "| Soft Soft CaaS land without hub WQ/proof | `./scripts/peer soft-hub-writeback` |",
            "| Soft Soft Active opens + proof mtimes | `./scripts/peer soft-soft-land-status` |",
            "| Daily standup / human update | `./scripts/peer standup` |",
            "| Verify gate red | `./scripts/peer heal-all` then `./scripts/peer test-quick` |",
            "| Pack integrity (cheap) | `./scripts/peer memory-pack-gate` (deep: `memory-compress-verify`) |",
            "| Role assignment state | `./scripts/peer role-state list` / `set` |",
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
