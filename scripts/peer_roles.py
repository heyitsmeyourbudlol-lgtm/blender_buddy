#!/usr/bin/env python3
"""Job-title roles + strength-based assignment for parallel Task peers.

The main orchestrator assigns queue work to subagents by matching each item to
the role whose strengths fit best, then launches Task(subagent_type=…, model=…).

Roles load from ``agent_roles`` in ``scripts/peer_tasks.json``.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentRole:
    id: str
    job_title: str
    subagent_type: str
    model: str
    strengths: tuple[str, ...]
    responsibilities: str
    reads: tuple[str, ...] = ()
    legacy_peer: str = ""  # maps old template peer keys (implement, verify, …)
    niche_task: str = ""  # default improvement task when queue has no fit
    prefer_remote: bool = False  # per-role DGX / SSH dispatch preference
    host: str = ""  # optional SSH host override hint for prefer_remote roles


def _coerce_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on")
    return bool(val)


@dataclass
class RoleAssignment:
    role: AgentRole
    score: float
    item: str
    standby: bool = False


def _as_role(raw: dict[str, Any]) -> AgentRole | None:
    rid = str(raw.get("id") or "").strip()
    title = str(raw.get("job_title") or raw.get("title") or "").strip()
    if not rid or not title:
        return None
    strengths = raw.get("strengths") or []
    if isinstance(strengths, str):
        strengths = [s.strip() for s in strengths.split(",") if s.strip()]
    reads = raw.get("reads") or []
    if isinstance(reads, str):
        reads = [reads]
    return AgentRole(
        id=rid,
        job_title=title,
        subagent_type=str(raw.get("subagent_type") or "generalPurpose"),
        model=str(raw.get("model") or "inherit"),
        strengths=tuple(str(s) for s in strengths if s),
        responsibilities=str(raw.get("responsibilities") or "").strip(),
        reads=tuple(str(r) for r in reads if r),
        legacy_peer=str(raw.get("legacy_peer") or "").strip(),
        niche_task=str(raw.get("niche_task") or "").strip(),
        prefer_remote=_coerce_bool(raw.get("prefer_remote", False)),
        host=str(raw.get("host") or "").strip(),
    )


def load_roles(cfg: dict[str, Any] | None = None) -> list[AgentRole]:
    """Load ``agent_roles`` from peer_tasks config."""
    if cfg is None:
        import project_automation as auto

        cfg = auto.load_tasks_config()
    roles: list[AgentRole] = []
    for raw in cfg.get("agent_roles") or []:
        if not isinstance(raw, dict):
            continue
        role = _as_role(raw)
        if role:
            roles.append(role)
    return roles


def _role_shard(role: AgentRole, shard: int) -> AgentRole:
    if shard <= 0:
        return role
    return AgentRole(
        id=f"{role.id}_L{shard + 1}",
        job_title=f"{role.job_title} · L{shard + 1}",
        subagent_type=role.subagent_type,
        model=role.model,
        strengths=role.strengths,
        responsibilities=role.responsibilities,
        reads=role.reads,
        legacy_peer=role.legacy_peer,
        niche_task=role.niche_task,
        prefer_remote=role.prefer_remote,
        host=role.host,
    )


def load_roles_expanded(cfg: dict[str, Any] | None = None, *, target: int | None = None) -> list[AgentRole]:
    """Repeat base niches until ``target`` parallel lanes exist (48 workers / 8 bases → 6 lanes each)."""
    import project_automation as auto

    base = load_roles(cfg)
    if not base:
        return []
    if cfg is None:
        cfg = auto.load_tasks_config()
    util = auto.CFG.get("dgx_utilization")
    if isinstance(util, dict) and util.get("role_pool_expand") is False:
        return base
    try:
        want = target if target is not None else int(auto.max_parallel_peers())
    except (TypeError, ValueError):
        want = auto.parallel_peer_floor()
    want = max(len(base), min(want, auto.max_parallel_peers()))
    if len(base) >= want:
        return base[:want]
    out: list[AgentRole] = []
    shard = 0
    while len(out) < want:
        for role in base:
            if len(out) >= want:
                break
            out.append(_role_shard(role, shard))
        shard += 1
    return out


def score_item_for_role(
    item: str,
    role: AgentRole,
    *,
    template_peer: str = "",
) -> float:
    """Higher = better fit for this queue line."""
    low = item.lower()
    score = 0.0
    for kw in role.strengths:
        k = kw.lower()
        if k in low:
            score += 1.0
        elif "`" in kw and kw.strip("`") in item:
            score += 1.5
    if template_peer and role.legacy_peer and template_peer == role.legacy_peer:
        score += 2.0
    # Whole-word bonus for short tokens
    for kw in role.strengths:
        k = kw.lower().strip("`")
        if len(k) >= 4 and re.search(rf"\b{re.escape(k)}\b", low):
            score += 0.25
    return score


def pick_role(
    item: str,
    roles: list[AgentRole],
    *,
    template_peer: str = "",
    used_role_ids: set[str] | None = None,
) -> RoleAssignment:
    """Pick the best role for one queue item (spread load on ties)."""
    used = used_role_ids or set()
    best: AgentRole | None = None
    best_score = -1.0
    for role in roles:
        s = score_item_for_role(item, role, template_peer=template_peer)
        if role.id in used:
            s -= 0.35  # prefer fresh roles when scores are close
        if s > best_score:
            best_score = s
            best = role
    if best is None:
        best = roles[0] if roles else AgentRole(
            id="generalist",
            job_title="Generalist Engineer",
            subagent_type="generalPurpose",
            model="inherit",
            strengths=(),
            responsibilities="Implement scoped queue work.",
        )
    return RoleAssignment(role=best, score=best_score, item=item)


def assign_items(
    items: list[str],
    cfg: dict[str, Any],
    *,
    template_peers: list[str] | None = None,
) -> list[RoleAssignment]:
    """Assign a dedicated job title + model to each queue item."""
    roles = load_roles(cfg)
    if not roles:
        return []
    peers = template_peers or [""] * len(items)
    used: set[str] = set()
    out: list[RoleAssignment] = []
    for item, tmpl_peer in zip(items, peers):
        asn = pick_role(item, roles, template_peer=tmpl_peer, used_role_ids=used)
        used.add(asn.role.id)
        out.append(asn)
    return out


def pool_guaranteed_role_ids(cfg: dict[str, Any] | None = None) -> list[str]:
    """Roles always in the active dispatch pool when rotation trims slots."""
    import project_automation as auto

    raw: Any = None
    if cfg is not None:
        raw = cfg.get("pool_guaranteed_roles")
    if not raw:
        raw = auto.CFG.get("pool_guaranteed_roles")
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return []


def role_importance_order(cfg: dict[str, Any] | None = None) -> list[str]:
    """Highest-importance first — used for rotation tie-breaks and replacement policy."""
    import project_automation as auto

    raw: Any = None
    if cfg is not None:
        raw = cfg.get("role_importance_order")
    if not raw:
        raw = auto.CFG.get("role_importance_order")
    if not isinstance(raw, list):
        raw = [
            "verify_runner",
            "queue_steward",
            "product_manager",
            "factory_engineer",
            "command_builder",
            "efficiency_researcher",
            "fact_checker",
            "bitnet_researcher",
            "compression_trainer",
            "output_researcher",
            "research_speed_engineer",
            "niche_distiller",
            "architecture_researcher",
            "train_eval_runner",
            "dgx_ops",
            "backend_engineer",
            "frontend_engineer",
            "adapt_specialist",
            "safety_auditor",
            "pen_test_researcher",
            "gpu_profiler",
            "recipe_lock_steward",
            "hallucination_auditor",
            "qa_engineer",
            "sre_release",
            "integration_architect",
            "design_ux",
            "compression_engineer",
            "communications_engineer",
            "model_serve_engineer",
            "dataset_curator",
            "idea_synthesis",
            "flaw_researcher",
            "creative_miner",
            "debrief_optimizer",
            "lessons_curator",
            "worktree_manager",
            "claim_ledger_scribe",
            "parallel_dispatch_coach",
            "growth_marketer",
            "customer_success",
            "finance_billing",
            "data_analyst",
            "tech_writer",
            "legal_compliance",
        ]
    return [str(x).strip() for x in raw if str(x).strip()]


def pool_rotation_enabled(cfg: dict[str, Any] | None = None) -> bool:
    import project_automation as auto

    block = auto.CFG.get("pool_rotation")
    if isinstance(block, dict) and "enabled" in block:
        return bool(block["enabled"])
    if cfg and isinstance(cfg.get("pool_rotation"), dict):
        return bool(cfg["pool_rotation"].get("enabled", True))
    return True


def _participation_path() -> Path:
    import project_automation as auto

    return auto.CONFIG_DIR / "role-participation-state.json"


def _load_participation() -> dict[str, Any]:
    path = _participation_path()
    if not path.is_file():
        return {"roles": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"roles": {}}
    except (OSError, json.JSONDecodeError):
        return {"roles": {}}


def record_pool_participation(active_role_ids: list[str]) -> None:
    """Track last active-pool cycle per role (rotation fairness)."""
    state = _load_participation()
    roles_map: dict[str, Any] = state.setdefault("roles", {})
    now = time.time()
    for rid in active_role_ids:
        entry = roles_map.setdefault(rid, {})
        entry["last_active_ts"] = now
        entry["cycles"] = int(entry.get("cycles") or 0) + 1
    state["last_hand_out_ts"] = now
    state["active_role_ids"] = list(active_role_ids)
    path = _participation_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def participation_snapshot() -> dict[str, Any]:
    """Last hand-out + per-role cycle counts for dashboard / kit-progress."""
    state = _load_participation()
    roster = load_roles()
    active = set(state.get("active_role_ids") or [])
    roles_map = state.get("roles") if isinstance(state.get("roles"), dict) else {}
    rows: list[dict[str, Any]] = []
    for role in roster:
        entry = roles_map.get(role.id) if isinstance(roles_map.get(role.id), dict) else {}
        rows.append(
            {
                "role_id": role.id,
                "job_title": role.job_title,
                "active_last_cycle": role.id in active,
                "cycles": int(entry.get("cycles") or 0),
                "last_active_ts": entry.get("last_active_ts"),
            }
        )
    return {
        "roster_size": len(roster),
        "active_last_cycle": len(active),
        "roles": rows,
        "last_hand_out_ts": state.get("last_hand_out_ts"),
    }


def select_pool_roles(
    pool_roles: list[AgentRole],
    count: int,
    cfg: dict[str, Any],
) -> list[AgentRole]:
    """Pick ``count`` active dispatch roles — guaranteed first, then rotation/fairness."""
    count = max(1, min(count, len(pool_roles)))
    if count >= len(pool_roles):
        return list(pool_roles)

    by_id = {r.id: r for r in pool_roles}
    selected: list[AgentRole] = []
    seen: set[str] = set()

    for gid in pool_guaranteed_role_ids(cfg):
        role = by_id.get(gid)
        if role is None or gid in seen:
            continue
        selected.append(role)
        seen.add(gid)
        if len(selected) >= count:
            return selected[:count]

    remaining = [r for r in pool_roles if r.id not in seen]
    slots_left = count - len(selected)
    if slots_left <= 0:
        return selected[:count]
    if len(remaining) <= slots_left:
        selected.extend(remaining)
        return selected[:count]

    importance = role_importance_order(cfg)
    rank = {rid: i for i, rid in enumerate(importance)}
    participation = _load_participation().get("roles") or {}

    def sort_key(role: AgentRole) -> tuple[float, int]:
        entry = participation.get(role.id) if isinstance(participation.get(role.id), dict) else {}
        last_ts = float(entry.get("last_active_ts") or 0)
        imp = rank.get(role.id, len(importance) + 1)
        return (last_ts, imp)

    if pool_rotation_enabled(cfg):
        remaining.sort(key=sort_key)
    else:
        remaining.sort(key=lambda r: rank.get(r.id, len(importance) + 1))

    selected.extend(remaining[:slots_left])
    return selected[:count]


# Hub niche lanes (peer-0..7). Expanded dispatch may use parallel_peer_floor —
# never confuse the two when floor grows under DGX.
DEFAULT_HUB_WORKER_POOL = 8


def worker_pool_size(cfg: dict[str, Any] | None = None) -> int:
    """Hub worker pool — one lane per base niche (typically 8).

    Honors ``hub_worker_pool`` / ``DEFAULT_HUB_WORKER_POOL``. Never follows
    ``parallel_peer_floor`` alone (may be 48 under DGX expand).
    """
    import project_automation as auto

    if cfg is None:
        cfg = auto.load_tasks_config()
    base = load_roles(cfg)
    hub_default = DEFAULT_HUB_WORKER_POOL
    try:
        raw = auto.CFG.get("hub_worker_pool")
        if raw is not None:
            hub_default = max(1, int(raw))
    except (TypeError, ValueError):
        hub_default = DEFAULT_HUB_WORKER_POOL
    cap = min(hub_default, auto.max_parallel_peers())
    if not base:
        return cap
    staff_all = bool(auto.CFG.get("staff_all_niches", True))
    if staff_all:
        return max(1, min(len(base), cap))
    # Non-staffed: still never inflate hub above hub_worker_pool.
    return max(1, min(cap, len(base)))


def hub_pool_assignments(
    assignments: list[RoleAssignment],
    cfg: dict[str, Any] | None = None,
) -> list[RoleAssignment]:
    """Unique 8-worker hub pool — drop rotation standbys, clamp to worker_pool_size."""
    n = worker_pool_size(cfg)
    active = [a for a in assignments if not getattr(a, "standby", False)]
    return active[:n]


def _default_niche_task(role: AgentRole) -> str:
    if role.niche_task:
        task = role.niche_task
    else:
        task = f"**{role.job_title} niche** — {role.responsibilities}"
    try:
        import command_ecosystem as ceco

        return ceco.ensure_niche_task_prefix(task)
    except Exception:  # noqa: BLE001
        return task


def assign_worker_pool(
    items: list[str],
    cfg: dict[str, Any],
    *,
    template_peers: list[str] | None = None,
    worker_count: int | None = None,
) -> list[RoleAssignment]:
    """Assign exactly ``worker_count`` peers — each a distinct automation niche.

    Queue items are matched greedily to the best unused role. Unfilled niches
    get each role's ``niche_task`` backlog line so the orchestrator always
    targets a full worker pool (default 8).
    """
    pool_roles = load_roles(cfg)
    if not pool_roles:
        return []
    count = worker_count if worker_count is not None else worker_pool_size(cfg)
    count = max(1, min(count, len(pool_roles)))
    active_roles = select_pool_roles(pool_roles, count, cfg)
    record_pool_participation([r.id for r in active_roles])
    roles = active_roles
    peers = template_peers or [""] * len(items)

    edges: list[tuple[float, int, str, AgentRole, str]] = []
    for item_idx, item in enumerate(items):
        tmpl = peers[item_idx] if item_idx < len(peers) else ""
        for role in roles:
            s = score_item_for_role(item, role, template_peer=tmpl)
            edges.append((s, item_idx, item, role, tmpl))
    edges.sort(key=lambda x: (-x[0], x[1]))

    used_roles: set[str] = set()
    used_items: set[int] = set()
    by_role: dict[str, RoleAssignment] = {}

    for score, item_idx, item, role, _tmpl in edges:
        if role.id in used_roles or item_idx in used_items:
            continue
        used_roles.add(role.id)
        used_items.add(item_idx)
        by_role[role.id] = RoleAssignment(role=role, score=score, item=item)
        if len(by_role) >= count:
            break

    out: list[RoleAssignment] = []
    active_ids = {r.id for r in active_roles}
    for role in roles:
        if role.id in by_role:
            out.append(by_role[role.id])
        else:
            out.append(RoleAssignment(role=role, score=0.0, item=_default_niche_task(role)))
    for role in pool_roles:
        if role.id in active_ids:
            continue
        out.append(
            RoleAssignment(
                role=role,
                score=0.0,
                item=_default_niche_task(role),
                standby=True,
            )
        )
    return out


def role_for_legacy(cfg: dict[str, Any], legacy_peer: str) -> AgentRole | None:
    for role in load_roles(cfg):
        if role.legacy_peer == legacy_peer or role.id == legacy_peer:
            return role
    return None


def format_roster_table(assignments: list[RoleAssignment]) -> str:
    if not assignments:
        return "(no role assignments)"
    lines = [
        "| # | Job title | Model | Subagent | Fit | Queue item |",
        "|---|-----------|-------|----------|-----|------------|",
    ]
    for i, asn in enumerate(assignments, 1):
        item = asn.item.replace("|", "\\|")[:72]
        if len(asn.item) > 72:
            item += "…"
        lines.append(
            f"| {i} | **{asn.role.job_title}** | `{asn.role.model}` | "
            f"`{asn.role.subagent_type}` | {asn.score:.1f} | {item} |"
        )
    return "\n".join(lines)


def format_orchestrator_assignment_block(assignments: list[RoleAssignment]) -> str:
    """Instructions for the main orchestrator agent."""
    if not assignments:
        return ""
    lines = [
        "## Orchestrator — assign by job title (main agent)",
        "",
        "You are the **Orchestrator**. Do **not** implement the full queue solo.",
        "Launch parallel **Task** subagents below — each has a **job title**, **model**, and **dedicated niche**.",
        "Assign work only to the matching role; one worker per niche; swap only if a peer reports true out-of-scope.",
        "",
        format_roster_table(assignments),
        "",
        "### Role responsibilities",
        "",
    ]
    seen: set[str] = set()
    for asn in assignments:
        if asn.role.id in seen:
            continue
        seen.add(asn.role.id)
        resp = asn.role.responsibilities or "(see queue item)"
        lines.append(f"- **{asn.role.job_title}** (`{asn.role.model}` / {asn.role.subagent_type}): {resp}")
    lines.append("")
    return "\n".join(lines)
