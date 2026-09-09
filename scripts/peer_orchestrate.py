#!/usr/bin/env python3
"""Peer orchestrator — decompose {auto.PROJECT_NAME} work into parallel agent tasks.

Usage:
  python3 scripts/peer_orchestrate.py --dry-run
  python3 scripts/peer_orchestrate.py --json
  python3 scripts/peer_orchestrate.py --self-check
  python3 scripts/peer_orchestrate.py --quick --clipboard
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import peer_roles as roles  # noqa: E402
import plan_drift_cache as drift_cache  # noqa: E402
import project_automation as auto  # noqa: E402
import template_match as tm  # noqa: E402

try:
    import github_feedback as gh_feedback  # noqa: E402
except ImportError:
    gh_feedback = None  # type: ignore[assignment,misc]


@dataclass
class PeerTask:
    peer: str
    subagent_type: str
    safety_tier: str
    title: str
    scope: list[str]
    prompt: str
    reads: list[str] = field(default_factory=list)
    mitigations: list[str] = field(default_factory=list)
    queue_items: list[str] = field(default_factory=list)
    item_guides: list[str] = field(default_factory=list)
    role_id: str = ""
    job_title: str = ""
    model: str = ""
    responsibilities: str = ""


@dataclass
class PeerPlan:
    orchestrator_brief: str
    tasks: list[PeerTask]
    live: dict
    stop: bool
    stop_reason: str | None
    warnings: list[str] = field(default_factory=list)
    role_assignments: list[roles.RoleAssignment] = field(default_factory=list)


def _scope_hints_from_item(item: str) -> list[str]:
    return tm.scope_hints_from_item(item, auto.module_scope_map())


def _match_template(item: str, templates: dict, cfg: dict) -> tuple[str, dict]:
    rules = list(cfg.get("match_rules") or [])
    return tm.match_template(item, templates, rules)


def _mitigations_for_tier(tier: str) -> list[str]:
    if tier == "green":
        return []
    if tier == "yellow":
        return [
            "Confirm only_background + experience.should_protect_workload on target loop",
            "Browsers/media/Cursor never auto-quit or E-core demoted (AGENTS.md)",
            "Game session defer unchanged for heavy passes",
            "Safety peer must PASS before merge",
        ]
    return ["RED tier — do not implement until user consent + explicit mitigation design"]


def _guide_block(title: str, scope: list[str], prompt: str) -> str:
    scope_s = ", ".join(scope) if scope else "(infer from item — do not default to electron/chrome)"
    return f"### {title}\nScope: `{scope_s}`\n{prompt}"


def _merge_implementation_tasks(raw: list[PeerTask]) -> list[PeerTask]:
    """Merge same-peer tasks when scopes are disjoint — keep per-item guidance."""
    by_peer: dict[str, PeerTask] = {}
    for task in raw:
        key = task.peer
        guide = _guide_block(task.title, task.scope, task.prompt)
        if key not in by_peer:
            by_peer[key] = PeerTask(
                peer=task.peer,
                subagent_type=task.subagent_type,
                safety_tier=task.safety_tier,
                title=task.title,
                scope=list(task.scope),
                prompt=task.prompt,
                reads=list(task.reads),
                mitigations=list(task.mitigations),
                queue_items=[task.title],
                item_guides=[guide],
            )
            continue
        existing = by_peer[key]
        existing.queue_items.append(task.title)
        existing.item_guides.append(guide)
        for s in task.scope:
            if s not in existing.scope:
                existing.scope.append(s)
        tier_rank = {"green": 0, "yellow": 1, "red": 2}
        if tier_rank.get(task.safety_tier, 1) > tier_rank.get(existing.safety_tier, 0):
            existing.safety_tier = task.safety_tier
            existing.mitigations = list(task.mitigations)
        existing.title = f"{existing.peer} work ({len(existing.queue_items)} items)"
        existing.prompt = (
            "Complete these queue items in one pass (disjoint scopes):\n"
            + "\n".join(f"  - {t}" for t in existing.queue_items)
            + "\n\nPer-item guidance (do not drop or swap scopes):\n"
            + "\n\n".join(existing.item_guides)
        )
    return list(by_peer.values())


def _peer_task_from_role(
    *,
    assignment: roles.RoleAssignment,
    peer_key: str,
    safety_tier: str,
    title: str,
    scope: list[str],
    prompt: str,
    reads: list[str],
    mitigations: list[str],
) -> PeerTask:
    role = assignment.role
    merged_reads = list(dict.fromkeys([*reads, *list(role.reads)]))
    try:
        import peer_team_context as tc

        merged_reads = list(dict.fromkeys([*tc.shared_read_paths(), *merged_reads]))
    except Exception:  # noqa: BLE001
        pass
    try:
        import peer_agent_comms as comms

        if comms.comms_enabled():
            merged_reads = list(
                dict.fromkeys([*merged_reads, *comms.comms_read_paths(role.id)])
            )
    except Exception:  # noqa: BLE001
        pass
    try:
        import peer_persona_rules as pr

        persona_block = pr.format_persona_rules_block(
            role.id, fallback_job_title=role.job_title
        )
    except Exception:  # noqa: BLE001
        persona_block = ""
    duty = (
        f"**Your job title:** {role.job_title}. "
        f"**Model:** {role.model}. "
        f"**Own this scope only** — {role.responsibilities}\n\n"
        f"{persona_block}\n\n"
        f"{prompt}"
    )
    return PeerTask(
        peer=peer_key,
        subagent_type=role.subagent_type,
        safety_tier=safety_tier,
        title=title,
        scope=scope,
        prompt=duty,
        reads=merged_reads,
        mitigations=mitigations,
        queue_items=[title],
        item_guides=[_guide_block(title, scope, duty)],
        role_id=role.id,
        job_title=role.job_title,
        model=role.model,
        responsibilities=role.responsibilities,
    )


def _build_implementation_tasks(open_items: list[str], cfg: dict) -> tuple[list[PeerTask], list[roles.RoleAssignment]]:
    templates = cfg.get("task_templates") or {}
    peers_meta = cfg.get("peers") or {}
    tasks: list[PeerTask] = []
    used_scopes: set[str] = set()
    cap = roles.worker_pool_size(cfg)
    template_peers: list[str] = []
    for item in open_items:
        _key, tmpl = _match_template(item, templates, cfg)
        template_peers.append(str(tmpl.get("peer") or "implement"))
    assignments = roles.hub_pool_assignments(
        roles.assign_worker_pool(
            open_items,
            cfg,
            template_peers=template_peers,
            worker_count=cap,
        ),
        cfg,
    )

    for idx, asn in enumerate(assignments, start=1):
        item = asn.item
        _key, tmpl = _match_template(item, templates, cfg)
        base_peer = tmpl.get("peer", "implement")
        peer_name = base_peer if auto.merge_same_peer_tasks() else f"{asn.role.id}-{idx}"
        meta = peers_meta.get(base_peer, {})
        hinted = _scope_hints_from_item(item)
        tmpl_scope = list(tmpl.get("scope") or [])
        merged_scope: list[str] = []
        for s in hinted + tmpl_scope:
            if s in used_scopes or s in merged_scope:
                continue
            merged_scope.append(s)
            used_scopes.add(s)
        tier = tmpl.get("safety_tier", "yellow")
        prompt = tmpl.get("prompt", f"Implement: {item}")
        tasks.append(
            _peer_task_from_role(
                assignment=asn,
                peer_key=peer_name,
                safety_tier=tier,
                title=item,
                scope=merged_scope,
                prompt=prompt,
                reads=list(meta.get("reads") or []),
                mitigations=_mitigations_for_tier(tier),
            )
        )

    impl = (
        _merge_implementation_tasks(tasks)
        if auto.merge_same_peer_tasks()
        else tasks
    )

    if not impl:
        return [], assignments

    safety_role = roles.role_for_legacy(cfg, "safety")
    if safety_role:
        safety_meta = peers_meta.get("safety", {})
        scopes = ", ".join(s for t in impl for s in t.scope) or "(see implementation peers)"
        impl.append(
            PeerTask(
                peer="safety",
                subagent_type=safety_role.subagent_type,
                safety_tier="green",
                title="Safety review",
                scope=[],
                prompt=(
                    f"**Your job title:** {safety_role.job_title}. "
                    f"Review changes in: {scopes}. "
                    "Apply notes/SAFETY_GATES.md checklist. Output PASS or BLOCK with file:line."
                ),
                reads=list(dict.fromkeys([*(safety_meta.get("reads") or []), *safety_role.reads])),
                role_id=safety_role.id,
                job_title=safety_role.job_title,
                model=safety_role.model,
                responsibilities=safety_role.responsibilities,
            )
        )
    else:
        safety_meta = peers_meta.get("safety", {})
        scopes = ", ".join(s for t in impl for s in t.scope) or "(see implementation peers)"
        impl.append(
            PeerTask(
                peer="safety",
                subagent_type=safety_meta.get("subagent_type", "generalPurpose"),
                safety_tier="green",
                title="Safety review",
                scope=[],
                prompt=(
                    f"Review changes in: {scopes}. "
                    "Apply notes/SAFETY_GATES.md checklist. Output PASS or BLOCK with file:line."
                ),
                reads=list(safety_meta.get("reads") or ["notes/SAFETY_GATES.md"]),
            )
        )

    verify_role = roles.role_for_legacy(cfg, "verify")
    verify_meta = peers_meta.get("verify", {})
    vcmds = cfg.get("verify_commands") or []
    if verify_role:
        impl.append(
            PeerTask(
                peer="verify",
                subagent_type=verify_role.subagent_type,
                safety_tier="green",
                title="Verify",
                scope=[],
                prompt=(
                    f"**Your job title:** {verify_role.job_title}. "
                    "Run:\n" + "\n".join(f"  {c}" for c in vcmds)
                ),
                reads=list(dict.fromkeys([*(verify_meta.get("reads") or []), *verify_role.reads])),
                role_id=verify_role.id,
                job_title=verify_role.job_title,
                model=verify_role.model,
                responsibilities=verify_role.responsibilities,
            )
        )
    else:
        impl.append(
            PeerTask(
                peer="verify",
                subagent_type=verify_meta.get("subagent_type", "shell"),
                safety_tier="green",
                title="Verify",
                scope=[],
                prompt="Run:\n" + "\n".join(f"  {c}" for c in vcmds),
            )
        )
    return impl, assignments


def build_plan(*, force: bool = False, quick: bool = False, include_creative: bool = False, loop: bool = False) -> PeerPlan:
    cfg = auto.load_tasks_config()
    context_md = auto.load_context_md()
    work_md = auto.load_work_queue_md()
    use_loop = loop or include_creative
    live = auto.measure_live_state(quick=quick)
    queue = (
        auto.loop_work_items(context_md, work_md, live=live)
        if use_loop
        else auto.open_work_items(context_md, work_md)
    )
    reason = auto.stop_reason(
        context_md,
        live,
        auto.open_work_items(context_md, work_md) if use_loop else queue,
        loop=use_loop,
    )
    if quick and drift_cache.should_skip_drift_sync(context_md=context_md, work_md=work_md):
        warnings: list[str] = []
    else:
        warnings = auto.sync_queue_drift(context_md, work_md)
        if quick:
            drift_cache.record_drift_sync(context_md=context_md, work_md=work_md)

    open_items = list(queue.open_items)
    if not open_items and include_creative and not use_loop:
        open_items = auto.creative_backlog_items(context_md)[:3]
        if open_items:
            queue = auto.QueueState(open_items=open_items, source="creative")
    if not live.git_clean and not any("git" in i.lower() or "commit" in i.lower() for i in open_items):
        open_items.insert(0, "Commit or stash pending changes (git not clean)")

    if not open_items and not force and not use_loop:
        open_items = auto.blocker_items(context_md, live, loop=False)[:2]
        queue = auto.QueueState(open_items=open_items, source="blockers")

    git_items = [i for i in open_items if "git" in i.lower() or "commit" in i.lower()]
    work_items = [i for i in open_items if i not in git_items]
    if use_loop and len(work_items) > 3:
        import peer_transcript as transcript

        state = transcript.load_state()
        cursor = int(state.get("orchestrate_cursor") or 0)
        n = len(work_items)
        picked = [work_items[(cursor + i) % n] for i in range(3)]
        state["orchestrate_cursor"] = (cursor + 3) % n
        transcript.save_state(state)
        work_items = picked
    open_items = git_items + work_items
    queue = auto.QueueState(open_items=open_items, source=queue.source if open_items else "empty")

    stop = bool(reason) and not force and not open_items
    if use_loop and open_items:
        stop = False

    rules = auto.extract_rules(context_md)
    cfg_rules = cfg.get("product_constraints") or []
    # Prefer product rules; include enough to keep TIME BOMB + ladder + meta-exit in every brief
    rules_short = "; ".join((rules or cfg_rules)[:6]) if (rules or cfg_rules) else "consent + compress + Cursor protected"

    priority_note = ""
    if queue.source == "launch":
        priority_note = (
            " Priority: LAUNCH.md phases in order (0 ship → 1 GitHub → 2 soft → 3 Setapp → 4 spikes); "
            "Phase 6 paid newsletters human-only after Setapp gate."
        )
    elif queue.source in ("creative", "experiments", "mine"):
        priority_note = " Priority: clever/non-obvious reclaim before obvious queue items."
    elif queue.source == "metrics":
        priority_note = " Priority: fix metrics before next clever pass."

    brief = (
        f"Orchestrate {auto.PROJECT_NAME} peers (speed × intelligence). "
        f"**TIME BOMB:** crown-era custom loop ends early–mid 2027 (top 5–15% parity). "
        f"**Also stress:** ladder speed→distribution→ecosystem (hub gravity); "
        f"keep queue/verify/constraints, drop daemon when native ~80%; "
        f"meta = exit each loop when it becomes the floor; "
        f"bank users+primitives now — not kit polish. Full frame: notes/LOOP_STRATEGY.md. "
        f"Live: {live.git_detail} · {live.tests_detail} · {live.footprint_detail}. "
        f"Queue source: {queue.source}.{priority_note} "
        f"Constraints: {rules_short}. "
        f"Read notes/PEER_ORCHESTRATION.md + notes/SELF_IMPROVE_RUBRIC.md + notes/AUTOMATION.md"
        f" + notes/AGENT_SURVIVAL.md (hazard map — stalls/chicken-eggs you will hit)"
        f"{(' + LAUNCH.md + MONETIZATION.md' if queue.source == 'launch' else '')}. "
        f"Phase gates: Plan/Orchestrate → Parallel Implement → Safety → Verify → Merge. "
        f"Maximize parallel Task peers — target **{roles.worker_pool_size(cfg)}** hub workers "
        f"(one niche each) in ONE message; hub launch ≤{roles.worker_pool_size(cfg)}; "
        f"max_parallel_peers {auto.max_parallel_peers()}; split scopes aggressively; "
        f"never collapse independent scopes into one hero agent."
    )

    tasks, role_assignments = [] if stop else _build_implementation_tasks(open_items, cfg)
    return PeerPlan(
        orchestrator_brief=brief,
        tasks=tasks,
        live=auto.live_snapshot(live, queue),
        stop=stop,
        stop_reason=reason,
        warnings=warnings,
        role_assignments=role_assignments,
    )


def _task_launch_hint(task: PeerTask, index: int) -> str:
    label = task.job_title or task.peer
    model_bit = f', model="{task.model}"' if task.model else ""
    return (
        f'Task(subagent_type="{task.subagent_type}"{model_bit}, description="{label} #{index}", '
        f'prompt="""{task.prompt} Scope: {", ".join(task.scope) or "see queue"}. '
        f'Read: {", ".join(task.reads) or "notes/"}.""")'
    )


def format_prompt(plan: PeerPlan) -> str:
    if plan.stop:
        return f"Nothing to orchestrate — {plan.stop_reason}\n{json.dumps(plan.live, indent=2)}"

    lines = [plan.orchestrator_brief, ""]
    if plan.warnings:
        lines.append("## Queue drift (fix notes sync)")
        for w in plan.warnings:
            lines.append(f"- {w}")
        lines.append("")

    if gh_feedback is not None:
        fb = gh_feedback.render_for_peers()
        if fb.strip():
            lines.append(fb.rstrip())
            lines.append("")

    try:
        import peer_dual_research as dr

        sync = dr.load_sync_brief(max_chars=2000)
        if sync.strip():
            lines.extend([
                "## Research sync (efficiency + output — read before Plan)",
                "",
                "Dual research agents feed the team + improve loop each cycle.",
                "Implement findings: Factory Engineer (speed) · OSS Architect (monster output).",
                "",
                sync.strip(),
                "",
            ])
    except Exception:  # noqa: BLE001
        pass

    try:
        import peer_team_context as tc

        block = tc.format_prompt_block(max_chars=5000)
        if block.strip():
            lines.extend([block, ""])
    except Exception:  # noqa: BLE001
        pass

    impl_tasks = [t for t in plan.tasks if t.peer not in ("safety", "verify")]
    safety_tasks = [t for t in plan.tasks if t.peer == "safety"]
    verify_tasks = [t for t in plan.tasks if t.peer == "verify"]
    needs_safety = bool(safety_tasks) or any(t.safety_tier in ("yellow", "red") for t in impl_tasks)

    cfg = auto.load_tasks_config()
    hub_workers = roles.worker_pool_size(cfg)
    lines.extend([
        "## Phase gates (run in order — do not skip)",
        "1. **Plan / Orchestrate** — `./scripts/peer plan-gate --role orchestrator`; read TEAM_CONTEXT; "
        "each peer drafts a **numbered step plan** (≥3 steps: action · paths · expected · verify) "
        "before any edit; answer Plan self-check; `./scripts/peer eta` per peer; assign by job title",
        "2. **Parallel Implement** — launch implementation Task peers (see below); "
        "**execute only drafted steps**",
        "3. **Safety** — required when any impl peer is yellow/red (or Safety peer listed)",
        "4. **Verify** — run verify commands; gate merge on PASS",
        "5. **Merge** — apply merge rules; sync WORK_QUEUE ↔ self_improve_context",
        "",
        "**Maximize parallel Task peers:** launch **"
        f"{hub_workers}** implementation Task tool calls in **ONE** message — "
        f"**one worker per niche** (hub launch ≤{hub_workers}; "
        f"max_parallel_peers {auto.max_parallel_peers()}); "
        "split scopes aggressively; never collapse independent scopes into one hero agent. "
        "Company org: `./scripts/peer company-org` — staff all teams/roles.",
        "",
    ])

    try:
        import command_ecosystem as ceco

        lines.extend([ceco.orchestrator_command_block(), ""])
    except Exception:  # noqa: BLE001
        lines.extend(
            [
                "## Command ecosystem (mandatory)",
                "- Prefer `./scripts/peer <id>` — `commands-list --pivotal`.",
                "- pre-dispatch before spawn; post-cycle after land.",
                "",
            ]
        )

    if plan.role_assignments:
        lines.append(roles.format_orchestrator_assignment_block(plan.role_assignments))
        try:
            import peer_agent_comms as comms

            block = comms.format_prompt_block()
            if block.strip():
                lines.append(block)
        except Exception:  # noqa: BLE001
            pass
        lines.append("## Phase 2 — Parallel Implement (launch together)")
        lines.append("")
    else:
        lines.extend([
            "## Phase 2 — Parallel Implement (launch together)",
            "",
        ])

    floor = hub_workers
    cap = auto.max_parallel_peers()
    pool_slots = roles.worker_pool_size(cfg)

    for i, t in enumerate(impl_tasks, 1):
        title = t.job_title or t.peer.upper()
        glink_role = getattr(t, "role_id", None) or ""
        glink_hint = ""
        if glink_role:
            try:
                import peer_agent_comms as comms

                if comms.comms_enabled():
                    glink_hint = (
                        f"\n- **GLink:** after work, append one line to "
                        f"`{comms._try_rel(comms.BUS_PATH)}` as `{glink_role}` "
                        f"(STAT/DONE/DIFF/REQ — not English; see GLink section above)"
                    )
            except Exception:  # noqa: BLE001
                pass
        lines.append(f"### Peer {i}: {title} ({t.subagent_type}, model `{t.model or 'inherit'}`) — {t.title}")
        lines.append(f"- Safety tier: **{t.safety_tier}**")
        if t.scope:
            lines.append(f"- Scope: `{', '.join(t.scope)}`")
        if t.reads:
            lines.append(f"- Read: {', '.join(t.reads)}")
        if t.mitigations:
            lines.append("- Mitigations required:")
            for m in t.mitigations:
                lines.append(f"  - {m}")
        lines.append(f"- Task: {t.prompt}{glink_hint}")
        lines.append("")

    if impl_tasks:
        lines.append("### Cursor Task launch (copy pattern — ONE message)")
        need = max(0, floor - len(impl_tasks))
        if need > 0:
            lines.append(
                f"- Only {len(impl_tasks)} impl peer(s) — **fill niche backlogs** until you launch "
                f"**{floor}** parallel Task peers (one per job title; cap {cap})."
            )
        lines.append(
            f"- Launch all {len(impl_tasks)} implementation peers in a single parallel Task batch "
            f"(target **{floor}** workers — one niche each; hub launch ≤{floor}; "
            f"max_parallel_peers {cap}; maximize parallel Task peers — "
            "not merely ≥2; prefer the full impl set in ONE message; split scopes aggressively; "
            "never collapse independent scopes into one hero agent)."
        )
        lines.append(
            "- **One worktree per Implement peer** when scopes are disjoint — "
            f"`.worktrees/peer-0` … `.worktrees/peer-{pool_slots - 1}` (peer_loop ensures pool)."
        )
        for i, t in enumerate(impl_tasks, 1):
            lines.append(f"- {_task_launch_hint(t, i)}")
        lines.append("")

    if needs_safety and safety_tasks:
        lines.extend(["## Phase 3 — Safety (after implement; before merge)", ""])
        for i, t in enumerate(safety_tasks, len(impl_tasks) + 1):
            lines.append(f"### Peer {i}: {t.peer.upper()} ({t.subagent_type}) — {t.title}")
            lines.append(f"- Task: {t.prompt}")
            lines.append("")
    elif needs_safety:
        lines.extend([
            "## Phase 3 — Safety (after implement; before merge)",
            "- No Safety peer in plan — still apply notes/SAFETY_GATES.md before merge for yellow/red.",
            "",
        ])

    if verify_tasks:
        lines.extend(["## Phase 4 — Verify (gate merge)", ""])
        base = len(impl_tasks) + len(safety_tasks) + 1
        for i, t in enumerate(verify_tasks, base):
            lines.append(f"### Peer {i}: {t.peer.upper()} ({t.subagent_type}) — {t.title}")
            lines.append(f"- Task: {t.prompt}")
            lines.append("")

    lines.extend([
        "## Phase 5 — Merge rules",
        "1. Safety BLOCK → fix before keeping implementation changes",
        "2. Verify fail → fix and re-run Verify only",
        "3. Update notes/WORK_QUEUE.md + scripts/self_improve_context.md when done (sync Phase checkboxes)",
        "4. Run `python3 scripts/peer_orchestrate.py --self-check` after editing automation",
        "5. Keep cold import <28 MB",
        "6. Re-run `python3 scripts/peer_loop.py --once` (or `--forever` daemon) after merge",
        "7. Set `## Loop` → `exhausted` in self_improve_context.md only when audit finds zero non-obvious wins left",
        "8. Update `notes/PEER_CONVERSATION.md` — canonical entire-conversation summary for next loop input",
        "9. Launch track: read LAUNCH.md — Phase 0 before Phase 4; Phase 6 paid ads = human only, never automate",
        "10. User-facing ship: CHANGELOG.md → Newdrop Publish",
        "11. **TIME BOMB + full strategy:** early–mid 2027 crown ends — bank product/users; ladder speed→distribution→ecosystem; exit loops when table stakes; keep queue/verify not daemon — notes/LOOP_STRATEGY.md (stress all of it)",
        "",
        "Implement now — follow phase gates; do not plan only.",
    ])
    return "\n".join(lines)


SELF_CHECK_LOCK_PATH = auto.CONFIG_DIR / "self-check.lock"
SELF_CHECK_LOCK_STALE_SEC = 180.0


def _try_acquire_self_check_lock() -> bool:
    SELF_CHECK_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    try:
        if SELF_CHECK_LOCK_PATH.is_file():
            age = now - SELF_CHECK_LOCK_PATH.stat().st_mtime
            if age < SELF_CHECK_LOCK_STALE_SEC:
                try:
                    pid = int(SELF_CHECK_LOCK_PATH.read_text().strip().splitlines()[0])
                except (OSError, ValueError, IndexError):
                    pid = None
                if pid and pid != os.getpid():
                    try:
                        os.kill(pid, 0)
                        return False
                    except OSError:
                        pass
        SELF_CHECK_LOCK_PATH.write_text(f"{os.getpid()}\n{now}\n")
        return True
    except OSError:
        return True


def _release_self_check_lock() -> None:
    try:
        if SELF_CHECK_LOCK_PATH.is_file():
            text = SELF_CHECK_LOCK_PATH.read_text()
            if text.startswith(str(os.getpid())):
                SELF_CHECK_LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


# Fail-closed: lock contention must not look like verify PASS (rc=0).
SELF_CHECK_LOCK_BUSY_RC = 75


def _hub_parallel_pool_on_disk(hub_pool: int) -> int:
    """Count ``peer-0..hub_pool-1`` dirs under the *hub* ``.worktrees`` pool.

    Self-check often runs from a linked ``.worktrees/peer-N`` ROOT. Counting
    ``auto.ROOT / .worktrees / peer-i`` always yields 0/N there and falsely tips
    ``ensure-pool`` while the hub floor is already ready. Mirror
    ``peer_agent_gates._worktree_pool_ok`` / ``ensure_parallel_pool`` — anchor
    via ``primary_worktree_root``.
    Needle: OVERSEER_SELF_CHECK_HUB_POOL_ISDIR_2026_09_07
    """
    import peer_worktree as wt

    rel, prefix = wt.parallel_pool_config()
    try:
        pool_root = wt.primary_worktree_root()
    except Exception:  # noqa: BLE001
        pool_root = auto.ROOT
    pool_dir = pool_root / rel
    n = max(0, int(hub_pool or 0))
    return sum(1 for i in range(n) if (pool_dir / f"{prefix}-{i}").is_dir())

def _tests_detail_inconclusive(detail: str | None) -> bool:
    """True when tests_detail is tip/soft, not a confirmed red suite.

    OVERSEER_SELF_CHECK_FAIL_TTL_SOFT_2026_09_04 — fail-ttl/lock/deferred tip-only.
    OVERSEER_PROBE_SKIP_BARE_FAIL_2026_09_04 — empty epilog "FAIL — failed" ≠ confirmed.
    OVERSEER_INCONCLUSIVE_WORKTREE_EPILOG_SELF_CHECK_2026_09_04 — peer_worktree
    OVERSEER_INCONCLUSIVE_WORKTREE_EPILOG_2026_09_04 — shared with project_automation measure soft-pass.
    dry-run stderr ``(pass --execute…)`` after SIGKILL/race must not trip ISSUES.
    """
    d = (detail or "").strip().lower()
    if not d:
        return True
    if "fail-ttl" in d:
        return True
    # Confirmed red suite — keep hard fail
    if "failures=" in d or "errors=" in d:
        return False
    soft_toks = (
        "in flight",
        "lock held",
        "deferred",
        "skipped",
        "stale cache",
        "timeout",
        "inconclusive",
        "storm trim",
        "pass --execute",
        "never uses --force",
    )
    if any(tok in d for tok in soft_toks):
        return True
    if d in {"tests: fail — failed", "tests: fail - failed", "failed"}:
        return True
    if re.search(r"fail\s*[—\-]\s*failed\s*$", d):
        return True
    return False

def run_self_check(*, quick: bool = False) -> int:
    """Teacher mode: audit automation health and suggest script improvements."""
    if not _try_acquire_self_check_lock():
        print("=== automation self-check ===\nSKIP: another self-check already running")
        # Fail-closed: rc=0 made verify treat SKIP as PASS while self-check never ran.
        return SELF_CHECK_LOCK_BUSY_RC
    try:
        return _run_self_check_body(quick=quick)
    finally:
        _release_self_check_lock()


def _run_self_check_body(*, quick: bool = False) -> int:
    cfg = auto.load_tasks_config()
    context_md = auto.load_context_md()
    work_md = auto.load_work_queue_md()
    issues: list[str] = []
    tips: list[str] = []

    issues.extend(auto.validate_tasks_config(cfg))
    issues.extend(auto.sync_queue_drift(context_md, work_md))

    try:
        import peer_team_context as tc

        for rel in tc.TEAM_SHARED_READS:
            path = auto.ROOT / rel
            if not path.is_file():
                issues.append(f"missing shared read: {rel}")
    except Exception as exc:  # noqa: BLE001
        issues.append(f"team shared reads check failed: {exc}")

    for path in (
        auto.CONTEXT_PATH,
        auto.WORK_QUEUE_PATH,
        auto.TASKS_PATH,
        auto.LAUNCH_PATH,
        SCRIPTS / "project_automation.py",
        SCRIPTS / "cursor_self_improve.py",
    ):
        if not path.is_file():
            issues.append(f"missing file: {path.relative_to(auto.ROOT)}")

    if auto.launch_track_active(work_md):
        open_launch = auto._parse_phased_work_items(work_md)
        tips.append(
            f"Launch track active: {len(open_launch)} open phase item(s) — read LAUNCH.md; "
            f"next: {open_launch[0][:70]}…"
        )

    # OVERSEER_SELF_CHECK_REUSE_PLAN_LIVE_2026_09_04 — OVERSEER_LAND_2026_09_04
    # one build_plan (owns measure_live); reuse plan.live (no orphan measure / dual format_prompt).
    # OVERSEER_SELF_CHECK_DEDUP_2026_09_04 — hot verify path must not double-pay measure.
    plan = build_plan(quick=quick)
    live = auto.LiveState(
        git_clean=bool(plan.live.get("git_clean")),
        git_detail=str(plan.live.get("git") or ""),
        tests_ok=bool(plan.live.get("tests_ok")),
        tests_detail=str(plan.live.get("tests") or ""),
        import_rss_mb=plan.live.get("import_rss_mb"),
        footprint_detail=str(plan.live.get("footprint") or ""),
    )
    loop_queue = auto.loop_work_items(context_md, work_md, live=live)
    if plan.stop and not plan.live.get("open_items"):
        if loop_queue.open_items:
            tips.append(
                f"Blocking queue empty but peer loop has {len(loop_queue.open_items)} "
                f"item(s) ({loop_queue.source}) — `cursor_self_improve.py --peer` continues."
            )
        else:
            tips.append("Queue empty and metrics green — automation should stop (expected).")
    elif not plan.tasks:
        issues.append("plan has open items but zero peer tasks — check task_templates matching")
    elif len([t for t in plan.tasks if t.peer not in ("safety", "verify")]) > 3:
        tips.append("Many implementation peers — merge logic may need tuning.")

    if loop_queue.open_items:
        tips.append(f"Loop preview source: {loop_queue.source}")

    role_list = roles.load_roles(cfg)
    hub_pool = roles.worker_pool_size(cfg)
    role_floor = min(hub_pool, auto.parallel_peer_floor())
    if len(role_list) < role_floor:
        issues.append(
            f"agent_roles has {len(role_list)} roles — need ≥{role_floor} "
            "(job titles for strength-based assignment)"
        )
    elif len(role_list) < auto.parallel_peer_floor():
        tips.append(
            f"agent_roles: {len(role_list)} niches — hub launches {hub_pool} "
            f"(worker_pool_size); dispatch lanes up to {auto.parallel_peer_floor()} "
            "when role_pool_expand"
        )
    elif len(role_list) < hub_pool:
        tips.append(
            f"agent_roles: {len(role_list)} niches — target {hub_pool} hub workers "
            "(one role each)"
        )
    if plan.role_assignments:
        titles = {a.role.job_title for a in plan.role_assignments}
        tips.append(f"Role roster: {len(titles)} job title(s) assigned this cycle")
        got = len(roles.hub_pool_assignments(plan.role_assignments, cfg))
        if got < hub_pool:
            issues.append(
                f"plan assigns {got}/{hub_pool} workers — "
                f"{hub_pool}-worker pool incomplete (check agent_roles + assign_worker_pool)"
            )
        else:
            tips.append(f"Worker pool: {hub_pool}/{hub_pool} niches (full hub pool)")
    try:
        on_disk = _hub_parallel_pool_on_disk(hub_pool)
        if on_disk < hub_pool:
            tips.append(
                f"Hub worktrees on disk: {on_disk}/{hub_pool} — ./scripts/peer ensure-pool"
            )
        else:
            tips.append(f"Hub worktrees on disk: {on_disk}/{hub_pool} (ready)")
    except Exception:  # noqa: BLE001
        pass

    try:
        import command_ecosystem as ceco

        for tip in ceco.self_check_tips()[:3]:
            tips.append(tip)
    except Exception:  # noqa: BLE001
        tips.append(
            "Command ecosystem: prefer ./scripts/peer — notes/COMMAND_ECOSYSTEM_PLAN.md"
        )

    if not live.tests_ok:
        # OVERSEER_SELF_CHECK_FAIL_TTL_SOFT_2026_09_04 — soft tip, not ISSUES.
        if _tests_detail_inconclusive(live.tests_detail or ""):
            tips.append(f"tests tip (inconclusive): {live.tests_detail}")
        else:
            issues.append(f"tests not ok: {live.tests_detail}")
    if auto.RSS_BUDGET_MB is not None and live.import_rss_mb is not None and live.import_rss_mb >= auto.RSS_BUDGET_MB:
        issues.append(f"import RSS over budget: {live.import_rss_mb:.1f} MB")

    if gh_feedback is not None and gh_feedback.INBOX_PATH.is_file():
        inbox = gh_feedback._load_json(gh_feedback.INBOX_PATH, {"items": []})
        new_count = sum(
            1
            for i in inbox.get("items") or []
            if i.get("local_status", "new") == "new"
        )
        if new_count:
            tips.append(
                f"{new_count} new GitHub feedback item(s) — "
                "python3 scripts/github_feedback.py fetch && render"
            )

    try:
        import automation_adapt as adapt

        signals = adapt.detect_signals(auto.ROOT, quick=True)
        config_profile = auto.CFG.get("task_profile")
        if config_profile and config_profile != signals.profile:
            tips.append(
                f"task_profile={config_profile!r} but detected stack={signals.stack!r} "
                f"(expected profile {signals.profile!r}) — run ./scripts/peer adapt-deep"
            )
        audit_path = adapt.adapt_state_path(auto.ROOT).parent / "adapt-audit.json"
        if audit_path.is_file():
            try:
                saved = json.loads(audit_path.read_text())
                for item in saved.get("findings") or []:
                    if item.get("level") == "warn":
                        tips.append(f"adapt audit [{item.get('category')}]: {item.get('message')}")
                if not saved.get("ok"):
                    for item in saved.get("findings") or []:
                        if item.get("level") == "error":
                            issues.append(f"adapt audit [{item.get('category')}]: {item.get('message')}")
            except (json.JSONDecodeError, OSError):
                tips.append("stale adapt-audit.json — run ./scripts/peer audit")
        else:
            tips.append("no adapt-audit.json yet — run ./scripts/peer audit after adapt/heal")
    except Exception as exc:  # noqa: BLE001 — self-check must not crash on adapt import
        tips.append(f"adapt check skipped ({exc})")

    print("=== automation self-check ===")
    if issues:
        print("\nISSUES:")
        for i in issues:
            print(f"  ✗ {i}")
    else:
        print("\nISSUES: none")

    if tips:
        print("\nTIPS:")
        for t in tips:
            print(f"  → {t}")

    print("\nPLAN PREVIEW:")
    preview = format_prompt(plan)
    print(preview[:800] + ("…" if len(preview) > 800 else ""))
    return 1 if issues else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Peer orchestrator for {auto.PROJECT_NAME}")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt to stdout")
    parser.add_argument("--json", action="store_true", help="Print JSON plan")
    parser.add_argument("--clipboard", action="store_true", help="Copy prompt to clipboard")
    parser.add_argument("--force", action="store_true", help="Plan even if stop heuristics say done")
    parser.add_argument("--loop", action="store_true", help="Include creative backlog + CREATIVE_RECLAIM experiments")
    parser.add_argument("--quick", action="store_true", help="Reuse cached tests/RSS when fresh (daemon hot paths)")
    parser.add_argument("--self-check", action="store_true", help="Audit automation health (teacher mode)")
    parser.add_argument(
        "--fetch-feedback",
        action="store_true",
        help="Fetch GitHub Issues into sanitized inbox before planning",
    )
    args = parser.parse_args()

    if args.fetch_feedback:
        if gh_feedback is None:
            print("github_feedback module unavailable", file=sys.stderr)
            return 1
        if gh_feedback.cmd_fetch(argparse.Namespace()) != 0:
            return 1

    if args.self_check:
        return run_self_check(quick=args.quick or True)

    plan = build_plan(force=args.force, quick=args.quick, loop=args.loop or args.force)
    prompt = format_prompt(plan)

    if args.json:
        payload = {
            "stop": plan.stop,
            "stop_reason": plan.stop_reason,
            "warnings": plan.warnings,
            "live": plan.live,
            "orchestrator_brief": plan.orchestrator_brief,
            "tasks": [asdict(t) for t in plan.tasks],
            "prompt": prompt,
        }
        print(json.dumps(payload, indent=2))
        return 0

    if plan.stop and not args.force:
        print(prompt)
        return 0

    if args.clipboard:
        if not auto.copy_to_clipboard(prompt):
            print("clipboard failed", file=sys.stderr)
            return 1
        print("copied peer prompt to clipboard")
        return 0

    print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
