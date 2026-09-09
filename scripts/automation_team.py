#!/usr/bin/env python3
"""Improve loop ↔ automation team integration (8 niches + operating system).

Bridges ``automation_improve`` (forever driver) with:
- 8-worker roster (`peer_roles`, `peer_agent_board`)
- Daily flaw scan (`peer_flaw_scan`)
- Debriefs / SOPs / KPIs (`peer_debrief`, `factory_progress`)
- Canonical map: ``notes/OPERATING_SYSTEM.md``
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

SCRIPTS = __import__("pathlib").Path(__file__).resolve().parent
ROOT = SCRIPTS.parent

# TEAM_STATUS_GENERATION_CACHE_2026_09_05 — gather→rank remissed team_status
# on every WQ mtime MISS even when flaw/debrief/board/roles unchanged.
# RANK_TEAM_STATUS_CACHE_2026_09_05 — rank path used uncached team_status_for_rank
# every gather MISS while full team_status already HIT.
# RANK_TEAM_STATUS_LITE_2026_09_05 — rank paid debrief.status_dict (~52ms) + factory.
_TEAM_STATUS_CACHE: dict[str, Any] | None = None
_TEAM_STATUS_STAMP_KEY: tuple[Any, ...] | None = None
_TEAM_STATUS_RANK_CACHE: dict[str, Any] | None = None
_TEAM_STATUS_RANK_STAMP_KEY: tuple[Any, ...] | None = None


def clear_team_status_cache() -> None:
    """Drop in-memory team_status + for_rank stamps (tests + forced remiss)."""
    global _TEAM_STATUS_CACHE, _TEAM_STATUS_STAMP_KEY
    global _TEAM_STATUS_RANK_CACHE, _TEAM_STATUS_RANK_STAMP_KEY
    _TEAM_STATUS_CACHE = None
    _TEAM_STATUS_STAMP_KEY = None
    _TEAM_STATUS_RANK_CACHE = None
    _TEAM_STATUS_RANK_STAMP_KEY = None


def _mtime_ns(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns) if path.is_file() else 0
    except OSError:
        return 0


def _team_status_input_key(*, quick: bool) -> tuple[Any, ...]:
    """Flaw/debrief/board/roles mtimes + calendar day — team_status generation token."""
    import peer_agent_board as board
    import peer_debrief as debrief
    import peer_flaw_scan as flaw

    # Include today so should_dispatch / past_daily_time remiss across day boundary.
    # DEBRIEF_COUNT_PATH: for_rank reads count_entries() (sidecar), not only DEBRIEF_LOG_MD.
    return (
        1 if quick else 0,
        date.today().isoformat(),
        _mtime_ns(flaw.STATE_PATH),
        _mtime_ns(flaw.ROUND_PATH),
        _mtime_ns(debrief.DEBRIEF_LOG_MD),
        _mtime_ns(debrief.SOP_INDEX_MD),
        _mtime_ns(debrief.DEBRIEF_COUNT_PATH),
        _mtime_ns(board.ROSTER_PATH),
        _mtime_ns(board.STATUS_PATH),
        _mtime_ns(SCRIPTS / "peer_tasks.json"),
    )


@dataclass(frozen=True)
class TeamOpportunity:
    category: str
    title: str
    detail: str
    priority: int = 50


def team_status(*, quick: bool = True) -> dict[str, Any]:
    """Single snapshot for improve prompts + horizon board."""
    global _TEAM_STATUS_CACHE, _TEAM_STATUS_STAMP_KEY
    key = _team_status_input_key(quick=quick)
    if _TEAM_STATUS_STAMP_KEY == key and _TEAM_STATUS_CACHE is not None:
        return _TEAM_STATUS_CACHE

    out: dict[str, Any] = {
        "operating_system": "notes/OPERATING_SYSTEM.md",
        "worker_target": 8,
        "roles": 0,
        "flaw_scan": {},
        "debrief": {},
        "agents_board": {},
        "factory_pct": None,
    }
    try:
        import peer_roles as roles

        out["roles"] = len(roles.load_roles())
        out["worker_target"] = roles.worker_pool_size()
    except Exception:  # noqa: BLE001
        pass

    try:
        import peer_flaw_scan as flaw

        out["flaw_scan"] = flaw.status_dict()
    except Exception as exc:  # noqa: BLE001
        out["flaw_scan"] = {"error": str(exc)}

    try:
        import peer_debrief as debrief

        out["debrief"] = debrief.status_dict()
    except Exception as exc:  # noqa: BLE001
        out["debrief"] = {"error": str(exc)}

    try:
        import peer_agent_board as board

        # TEAM_STATUS_SKIP_PORCELAIN — slice skips list_worktrees / porcelain
        out["agents_board"] = board.agents_board_slice()
    except Exception as exc:  # noqa: BLE001
        out["agents_board"] = {"error": str(exc)}

    try:
        import factory_progress as fp

        block = fp.compute_factory_progress(quick=quick).to_dict()
        out["factory_pct"] = block.get("pct")
        out["factory_blockers"] = list(block.get("blockers") or [])[:4]
    except Exception:  # noqa: BLE001
        pass

    _TEAM_STATUS_CACHE = out
    _TEAM_STATUS_STAMP_KEY = key
    return out


def team_status_for_rank() -> dict[str, Any]:
    """Rank-path snapshot — no debrief.recent / kpi / factory (unused by rank).

    Needle: RANK_TEAM_STATUS_LITE_2026_09_05 — ``rank_team_opportunities`` only reads
    flaw_scan, debrief.entries, roles/worker_target, agents_board.summary.phase.
    Full ``team_status`` paid ``status_dict`` (~52ms) + factory on every rank MISS.

    Needle: RANK_TEAM_STATUS_CACHE_2026_09_05 — generation stamp; gather→rank remiss.
    """
    global _TEAM_STATUS_RANK_CACHE, _TEAM_STATUS_RANK_STAMP_KEY
    key = _team_status_input_key(quick=True)
    if _TEAM_STATUS_RANK_STAMP_KEY == key and _TEAM_STATUS_RANK_CACHE is not None:
        return _TEAM_STATUS_RANK_CACHE

    out: dict[str, Any] = {
        "operating_system": "notes/OPERATING_SYSTEM.md",
        "worker_target": 8,
        "roles": 0,
        "flaw_scan": {},
        "debrief": {"entries": 0},
        "agents_board": {},
        "factory_pct": None,
    }
    try:
        import peer_roles as roles

        out["roles"] = len(roles.load_roles())
        out["worker_target"] = roles.worker_pool_size()
    except Exception:  # noqa: BLE001
        pass

    try:
        import peer_flaw_scan as flaw

        out["flaw_scan"] = flaw.status_dict()
    except Exception as exc:  # noqa: BLE001
        out["flaw_scan"] = {"error": str(exc)}

    try:
        import peer_debrief as debrief

        out["debrief"] = {"entries": int(debrief.count_entries())}
    except Exception as exc:  # noqa: BLE001
        out["debrief"] = {"entries": 0, "error": str(exc)}

    try:
        import peer_agent_board as board

        out["agents_board"] = board.agents_board_slice()
    except Exception as exc:  # noqa: BLE001
        out["agents_board"] = {"error": str(exc)}

    _TEAM_STATUS_RANK_CACHE = out
    _TEAM_STATUS_RANK_STAMP_KEY = key
    return out


def _known_has(known: set[str], *needles: str) -> bool:
    import project_automation as auto

    for n in needles:
        key = auto._normalize_queue_key(n)
        if not key:
            continue
        for k in known:
            if key in k or k in key:
                return True
    return False


def rank_team_opportunities(known: set[str]) -> list[TeamOpportunity]:
    """Executable queue items derived from the automation team setup."""
    opps: list[TeamOpportunity] = []
    st = team_status_for_rank()
    fs = st.get("flaw_scan") or {}
    rnd = fs.get("round") or {}
    deb = st.get("debrief") or {}

    if fs.get("should_dispatch"):
        opps.append(
            TeamOpportunity(
                category="smooth",
                title="Daily flaw scan — 8 scanners cross-review 7 niches each",
                detail=(
                    "Peer loop should run flaw-scan orchestration (Flaw Detection Scanner + role). "
                    "56 reviews → 8 self-triages. `./scripts/peer flaw-scan-preview`"
                ),
                priority=13,
            )
        )
    elif rnd.get("phase") == "scanning":
        done = int(rnd.get("reviews_done") or 0)
        total = int(rnd.get("reviews_total") or 56)
        if done < total:
            opps.append(
                TeamOpportunity(
                    category="efficiency",
                    title=f"Complete flaw scan reviews ({done}/{total})",
                    detail=(
                        "Record reviews via `peer flaw-scan --record-review` or flaw-scan-reviews/*.md "
                        "then `--compile`. Advance to triage when complete."
                    ),
                    priority=14,
                )
            )
    elif rnd.get("phase") == "triage":
        tri = int(rnd.get("triage_done") or 0)
        if tri < 8:
            opps.append(
                TeamOpportunity(
                    category="smooth",
                    title=f"Flaw scan self-triage ({tri}/8 niches)",
                    detail=(
                        "Each niche reads 7 reviews; record via `peer flaw-scan --record-triage`. "
                        "Queue Steward promotes accepted upgrades to WORK_QUEUE."
                    ),
                    priority=15,
                )
            )

    if not _known_has(known, "debrief", "DEBRIEF_LOG", "Queue Steward: promote"):
        if int(deb.get("entries") or 0) == 0:
            opps.append(
                TeamOpportunity(
                    category="ease",
                    title="Optimization Unit debrief — capture cycle AAR/post-mortem",
                    detail=(
                        "Run `./scripts/peer debrief --capture-cycle`; blameless process focus. "
                        "See notes/OPERATING_SYSTEM.md pillar 1."
                    ),
                    priority=22,
                )
            )
        else:
            opps.append(
                TeamOpportunity(
                    category="smooth",
                    title="Queue Steward: promote debrief upgrades to WORK_QUEUE",
                    detail=(
                        "Read notes/DEBRIEF_LOG.md + flaw-scan triage; sync executable items to "
                        "notes/WORK_QUEUE.md ↔ scripts/self_improve_context.md. notes/SOP_INDEX.md"
                    ),
                    priority=23,
                )
            )

    roles_n = int(st.get("roles") or 0)
    target = int(st.get("worker_target") or 8)
    if roles_n < target:
        opps.append(
            TeamOpportunity(
                category="smooth",
                title=f"Agent roster — need {target} niches in peer_tasks.json agent_roles",
                detail=f"Only {roles_n} roles defined; parallel_peer_floor={target}. notes/AGENT_ROLES.md",
                priority=19,
            )
        )

    if not _known_has(known, "ensure-pool", "peer-0", "worktree pool"):
        opps.append(
            TeamOpportunity(
                category="speed",
                title="Ensure 8-worker worktree pool for parallel niches",
                detail="./scripts/peer ensure-pool — .worktrees/peer-0..7 for disjoint Implement peers",
                priority=25,
            )
        )

    ab = st.get("agents_board") or {}
    summary = ab.get("summary") if isinstance(ab.get("summary"), dict) else {}
    if summary.get("phase") == "STOPPED":
        opps.append(
            TeamOpportunity(
                category="smooth",
                title="Peer loop stopped — automation team idle",
                detail="`python3 scripts/peer_loop.py --install` or kickstart com.togi.automation-hub-peer-loop",
                priority=6,
            )
        )

    return opps


def format_team_block(*, quick: bool = True) -> str:
    """Markdown section injected into improve plan/execute/horizon."""
    st = team_status(quick=quick)
    fs = st.get("flaw_scan") or {}
    rnd = fs.get("round") or {}
    deb = st.get("debrief") or {}
    ab_summary = (st.get("agents_board") or {}).get("summary") or {}

    lines = [
        "## Automation team (improve ↔ peer orchestration)",
        "",
        "Improve forever **must** drive this setup — not kit polish in isolation.",
        "",
        f"| Pillar | Kit | Status |",
        f"|--------|-----|--------|",
        f"| 8 niches | `notes/AGENT_ROLES.md`, `peer_tasks.json` | {st.get('roles', '?')}/{st.get('worker_target', 8)} roles |",
        f"| Agent board | `/agents`, `peer_agent_board.py` | phase `{ab_summary.get('phase', '?')}` |",
        f"| GLink comms | `peer_agent_comms.py`, `/api/comms` | shared bus + per-agent vaults |",
        f"| Flaw scan | `peer_flaw_scan.py`, `/flaw-scan` | `{rnd.get('phase') or '—'}` · reviews {rnd.get('reviews_done', 0)}/{rnd.get('reviews_total', 56)} |",
        f"| Debriefs / KPIs | `peer_debrief.py`, `/progress` | factory {st.get('factory_pct', '?')}% · {deb.get('entries', 0)} debrief(s) |",
        f"| Operating system | `notes/OPERATING_SYSTEM.md` | SOP index + DEBRIEF_LOG |",
        "",
        "**Peer dispatch rules for improve cycles:**",
        "",
        "1. **Every improve cycle** calls `hand_out_worker_pool` — all 8 niches get assignments on the board + GLink.",
        "2. Launch **8 Task peers** — one niche each (`parallel_peer_floor`).",
        "3. Respect daily **flaw scan** when `should_dispatch` (priority over normal queue).",
        "4. **Queue Steward** syncs debrief + flaw-scan upgrades → WORK_QUEUE.",
        "5. **Optimization Unit** (`./scripts/peer debrief --preview`) after flaw round or verify fail.",
        "6. Never solo — orchestrate parallel peers in ONE message.",
        "",
        "```bash",
        "./scripts/peer agents          # birds-eye",
        "./scripts/peer flaw-scan --status",
        "./scripts/peer debrief --status",
        "./scripts/peer progress",
        "./scripts/peer ensure-pool",
        "```",
        "",
    ]
    if fs.get("should_dispatch"):
        lines.append("> **NOW:** Daily flaw scan is due — peer loop should run flaw-scan orchestration first.")
        lines.append("")
    blockers = st.get("factory_blockers") or []
    if blockers:
        lines.append("**Factory blockers (KPI):**")
        for b in blockers[:3]:
            lines.append(f"- {b}")
        lines.append("")

    return "\n".join(lines)


def team_wake_hint() -> str | None:
    """Short log line for improve wake_peer."""
    fs = team_status(quick=True).get("flaw_scan") or {}
    if fs.get("should_dispatch"):
        return "team: flaw scan due — peer should prioritize flaw-scan prompt"
    rnd = fs.get("round") or {}
    if rnd.get("phase") in ("scanning", "triage"):
        return f"team: flaw scan in progress ({rnd.get('phase')})"
    return None


def _gather_handout_items(*, signals: Any | None = None) -> list[str]:
    """Queue lines + NOW opportunities for role matching."""
    import project_automation as auto

    items: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        text = str(raw or "").strip()
        if not text:
            return
        key = auto._normalize_queue_key(text)
        if key in seen:
            return
        seen.add(key)
        items.append(text)

    try:
        for line in auto.open_work_items().open_items:
            add(line)
    except Exception:  # noqa: BLE001
        pass

    if signals is not None:
        try:
            import automation_improve as improve

            for opp in getattr(signals, "opportunities", None) or []:
                if not improve.is_work_kit_target(opp):
                    continue
                if improve._horizon_tier(opp.priority) not in ("NOW", "NEXT"):
                    continue
                add(f"{opp.title} — {opp.detail}")
        except Exception:  # noqa: BLE001
            pass

    return items[: auto.max_parallel_peers() * 2]


def hand_out_worker_pool(
    *,
    log_fn: Callable[[str], None],
    signals: Any | None = None,
    items: list[str] | None = None,
    worker_count: int | None = None,
) -> list[str]:
    """Assign every niche a task; refresh agent board + GLink vaults (improve forever)."""
    import project_automation as auto

    if not auto.improve_hand_out_roles_enabled():
        return []

    import peer_agent_board as board
    import peer_agent_comms as comms
    import peer_roles as pr

    pool_items = items if items is not None else _gather_handout_items(signals=signals)
    cfg = auto.load_tasks_config()
    count = worker_count if worker_count is not None else pr.worker_pool_size(cfg)
    assignments = pr.assign_worker_pool(pool_items, cfg, worker_count=count)
    if not assignments:
        log_fn("hand_out: no agent_roles in peer_tasks.json")
        return []

    board.record_role_assignments(assignments, source="automation_improve")

    all_roles = pr.load_roles(cfg)
    if comms.comms_enabled():
        comms.ensure_all_agents(all_roles)

    handed: list[str] = []
    standby: list[str] = []
    floor = auto.parallel_peer_floor()
    for asn in assignments:
        role = asn.role
        plain = board.plain_item(asn.item)
        if getattr(asn, "standby", False):
            standby.append(role.id)
            if comms.comms_enabled():
                comms.ensure_agent(role.id)
                comms.update_tasks(role.id, todo=[plain])
            continue
        if comms.comms_enabled():
            comms.update_tasks(role.id, todo=[plain])
            comms.post_glink(
                msg_type=comms.MSG_STAT,
                from_role="orchestrator",
                to_role=role.id,
                payload={
                    "st": "ASN",
                    "role": role.id,
                    "job": role.job_title[:48],
                    "score": round(float(asn.score), 2),
                },
            )
        handed.append(role.id)
        log_fn(f"hand_out: {role.job_title} ← {plain[:76]}")

    for sid in standby:
        role = next((r for r in all_roles if r.id == sid), None)
        if role:
            log_fn(f"hand_out: {role.job_title} (standby — niche backlog, rotates in)")

    log_fn(
        f"hand_out: {len(handed)}/{count} active · {len(standby)} standby · "
        f"{len(all_roles)} total roster"
    )
    if len(handed) < floor:
        log_fn(
            f"hand_out: WARN — only {len(handed)}/{floor} niches; "
            "raise max_parallel_peers / parallel_peer_floor in automation.config"
        )

    try:
        import peer_team_context as tc

        tc.write_team_context(signals=signals)
        n = tc.sync_agent_vaults(assignments, signals=signals)
        if n:
            log_fn(f"hand_out: team context synced to {n} vault(s)")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"hand_out: team context sync skipped ({exc})")

    return handed
