#!/usr/bin/env python3
"""Birds-eye + per-niche agent board for the 8-worker automation pool.

Persists the last dispatched roster to ``peer-agent-roster.json`` and merges
live peer-loop phase, worktrees, and cycle memory for the dashboard.

Usage:
  python3 scripts/peer_agent_board.py --json
  python3 scripts/peer_agent_board.py --watch
  ./scripts/peer agents
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import peer_roles as roles  # noqa: E402
import project_automation as auto  # noqa: E402

ROSTER_PATH = auto.CONFIG_DIR / "peer-agent-roster.json"
STATUS_PATH = auto.CONFIG_DIR / "peer-loop-status.json"
STATE_PATH = auto.CONFIG_DIR / "peer-loop-state.json"

ORCHESTRATOR_ID = "orchestrator"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _plain_item(text: str, *, limit: int = 220) -> str:
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", str(text or ""))
    s = re.sub(r"`([^`]+)`", r"\1", s).strip()
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def plain_item(text: str, *, limit: int = 220) -> str:
    """Public helper for assignment summaries."""
    return _plain_item(text, limit=limit)


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _worktree_slots() -> list[dict[str, str]]:
    try:
        import peer_worktree as wt

        entries = wt.list_worktrees(ROOT)
        extras = wt.parallel_entries(entries, root=ROOT)
    except Exception:  # noqa: BLE001
        return []
    out: list[dict[str, str]] = []
    for ent in extras:
        name = Path(ent.path).name
        slot = name if name.startswith("peer-") else name
        out.append(
            {
                "slot": slot,
                "path": ent.path,
                "branch": ent.branch or "",
                "head": (ent.head or "")[:12],
            }
        )
    return out


def _assignments_to_rows(assignments: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    slot = 0
    for asn in assignments:
        if getattr(asn, "standby", False):
            continue
        slot += 1
        role = asn.role
        rows.append(
            {
                "slot": slot,
                "role_id": role.id,
                "job_title": role.job_title,
                "model": role.model,
                "subagent_type": role.subagent_type,
                "item": asn.item,
                "item_plain": _plain_item(asn.item),
                "score": float(asn.score),
                "responsibilities": role.responsibilities,
                "reads": list(role.reads),
                "status": "dispatched",
                "detail": "Assigned for this orchestration cycle",
                "updated_at": _now_iso(),
                "pool": "active",
            }
        )
    for asn in assignments:
        if not getattr(asn, "standby", False):
            continue
        role = asn.role
        rows.append(
            {
                "slot": None,
                "role_id": role.id,
                "job_title": role.job_title,
                "model": role.model,
                "subagent_type": role.subagent_type,
                "item": asn.item,
                "item_plain": _plain_item(asn.item),
                "score": float(asn.score),
                "responsibilities": role.responsibilities,
                "reads": list(role.reads),
                "status": "standby",
                "detail": "Rotation standby — niche backlog until next active slot",
                "updated_at": _now_iso(),
                "pool": "standby",
            }
        )
    return rows


def roster_assignments(roster: dict[str, Any] | None = None) -> list[Any]:
    """Rebuild RoleAssignment list from improve/orchestrate roster JSON."""
    data = roster if roster is not None else (_safe_read_json(ROSTER_PATH) or {})
    agents = data.get("agents") or []
    if not agents:
        return []
    cfg = auto.load_tasks_config()
    by_id = {r.id: r for r in roles.load_roles_expanded(cfg)}
    for base in roles.load_roles(cfg):
        by_id.setdefault(base.id, base)
    out: list[Any] = []
    for row in agents:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("role_id") or "").strip()
        role = by_id.get(rid)
        if role is None:
            m = re.match(r"^(.+)_L\d+$", rid)
            if m:
                role = by_id.get(m.group(1))
        if role is None:
            continue
        item = str(row.get("item") or row.get("item_plain") or role.niche_task or "")
        out.append(roles.RoleAssignment(role=role, score=float(row.get("score") or 0.0), item=item))
    return out


def _assignment_rows(plan: Any) -> list[dict[str, Any]]:
    return _assignments_to_rows(getattr(plan, "role_assignments", None) or [])


def record_role_assignments(
    assignments: list[Any],
    *,
    source: str = "peer_orchestrate",
) -> dict[str, Any]:
    """Persist an 8-niche roster from improve or orchestrate (no PeerPlan required)."""
    agents = _assignments_to_rows(assignments)
    payload: dict[str, Any] = {
        "version": 1,
        "dispatch_ts": time.time(),
        "dispatch_iso": _now_iso(),
        "source": source,
        "stop": False,
        "stop_reason": None,
        "orchestrator": {
            "role_id": ORCHESTRATOR_ID,
            "job_title": "Orchestrator",
            "model": "inherit",
            "subagent_type": "agent",
            "status": "dispatched",
            "detail": f"Role handout ({source}) — {len(agents)} niches",
            "updated_at": _now_iso(),
        },
        "agents": agents,
        "worktrees": _worktree_slots(),
        "worker_target": roles.worker_pool_size(),
    }
    _write_json(ROSTER_PATH, payload)
    try:
        import peer_agent_comms as comms

        if comms.comms_enabled():
            comms.ensure_all_agents()
            comms.post_glink(
                msg_type=comms.MSG_STAT,
                from_role="orchestrator",
                payload={"st": "WIP", "op": "hand_out", "n": len(agents), "src": source[:24]},
            )
    except Exception:  # noqa: BLE001
        pass
    return payload


def record_dispatch(plan: Any) -> dict[str, Any]:
    """Persist roster from a ``PeerPlan`` (called before Cursor dispatch)."""
    agents = _assignment_rows(plan)
    payload: dict[str, Any] = {
        "version": 1,
        "dispatch_ts": time.time(),
        "dispatch_iso": _now_iso(),
        "stop": bool(getattr(plan, "stop", False)),
        "stop_reason": getattr(plan, "stop_reason", None),
        "orchestrator": {
            "role_id": ORCHESTRATOR_ID,
            "job_title": "Orchestrator",
            "model": "inherit",
            "subagent_type": "agent",
            "status": "dispatched" if not getattr(plan, "stop", False) else "idle",
            "detail": "Peer plan built — dispatching to Cursor",
            "updated_at": _now_iso(),
        },
        "agents": agents,
        "worktrees": _worktree_slots(),
        "worker_target": roles.worker_pool_size(),
    }
    _write_json(ROSTER_PATH, payload)
    try:
        import peer_agent_comms as comms

        if comms.comms_enabled():
            comms.ensure_all_agents()
            comms.post_glink(
                msg_type=comms.MSG_STAT,
                from_role="orchestrator",
                payload={"st": "WIP", "op": "dispatch", "n": len(agents)},
            )
    except Exception:  # noqa: BLE001
        pass
    return payload


def ensure_roster(*, max_age_sec: float = 7200.0) -> dict[str, Any]:
    """Load roster file or rebuild from current plan when missing/stale."""
    data = _safe_read_json(ROSTER_PATH)
    if data and data.get("agents"):
        age = time.time() - float(data.get("dispatch_ts") or 0)
        if age <= max_age_sec:
            return data
    try:
        import peer_orchestrate as po

        plan = po.build_plan(quick=True, loop=True)
        if plan.role_assignments:
            return record_dispatch(plan)
        if data:
            return data
        if not plan.stop:
            return record_dispatch(plan)
    except Exception:  # noqa: BLE001
        pass
    return data or {}


def update_agent_note(role_id: str, status: str, detail: str) -> bool:
    """Manual heartbeat — orchestrator or steward can update one niche."""
    data = _safe_read_json(ROSTER_PATH)
    if not data:
        data = ensure_roster()
    if role_id == ORCHESTRATOR_ID:
        orch = data.setdefault("orchestrator", {})
        orch["status"] = status
        orch["detail"] = detail
        orch["updated_at"] = _now_iso()
        _write_json(ROSTER_PATH, data)
        return True
    for agent in data.get("agents") or []:
        if isinstance(agent, dict) and agent.get("role_id") == role_id:
            agent["status"] = status
            agent["detail"] = detail
            agent["updated_at"] = _now_iso()
            _write_json(ROSTER_PATH, data)
            return True
    return False


def _peer_runtime() -> dict[str, Any]:
    snap = _safe_read_json(STATUS_PATH) or {}
    state = _safe_read_json(STATE_PATH) or {}
    lc = state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else {}
    return {
        "phase": str(snap.get("phase") or "UNKNOWN").upper(),
        "phase_detail": str(snap.get("phase_detail") or ""),
        "daemon_running": snap.get("daemon_running"),
        "queue_count": int(snap.get("queue_count") or 0),
        "queue_preview": list(snap.get("queue_preview") or [])[:4],
        "last_cycle_summary": str(snap.get("last_cycle_summary") or ""),
        "noop_backoff_sec": float(snap.get("noop_backoff_sec") or 0),
        "agent_pid": (snap.get("agent") or {}).get("pid") if isinstance(snap.get("agent"), dict) else None,
        "last_cycle": lc,
    }


def agents_board_slice() -> dict[str, Any]:
    """Phase + dispatch for improve ``team_status`` — no ``list_worktrees``.

    Needle: TEAM_STATUS_SKIP_PORCELAIN_2026_09_05 — ``team_status`` only keeps
    ``summary`` + ``dispatch_iso`` but called ``build_board`` which shells
    porcelain (~2–3ms) on every ``gather_signals`` → ``rank_opportunities``
    prepare-miss path. Runtime JSON + roster are enough for STOPPED/phase.
    """
    roster = _safe_read_json(ROSTER_PATH) or {}
    runtime = _peer_runtime()
    agents = roster.get("agents") or []
    if not isinstance(agents, list):
        agents = []
    active = sum(
        1
        for a in agents
        if isinstance(a, dict) and a.get("status") in ("in_flight", "running", "verifying")
    )
    return {
        "summary": {
            "phase": runtime["phase"],
            "phase_detail": runtime["phase_detail"],
            "active_agents": active,
            "total_agents": len(agents),
            "daemon_running": runtime.get("daemon_running"),
            "queue_count": runtime["queue_count"],
        },
        "dispatch_iso": roster.get("dispatch_iso"),
    }


def agents_board_lite() -> dict[str, Any]:
    """Alias for ``agents_board_slice`` (TEAM_STATUS_SKIP_PORCELAIN)."""
    return agents_board_slice()


def _status_for_role(role_id: str, phase: str, base_status: str, base_detail: str) -> tuple[str, str]:
    """Map daemon phase → per-niche status (honest — subagents live inside Cursor)."""
    phase = phase.upper()
    if base_status in ("running", "blocked", "done", "verifying"):
        return base_status, base_detail

    if role_id == ORCHESTRATOR_ID:
        if phase == "WORKING":
            return "running", "Orchestrating parallel Task peers in Cursor"
        if phase == "VERIFYING":
            return "verifying", "Gate on verify before next dispatch"
        if phase == "WAITING":
            return "waiting", "Between dispatches — peer loop will wake cursor-agent"
        if phase == "STOPPED":
            return "offline", "Peer LaunchAgent not running"
        if phase == "IDLE":
            return "idle", "Between cycles — watching transcript / queue"
        return "unknown", base_detail or phase

    if phase == "WORKING":
        return "in_flight", "Orchestrator active — launch or monitor your Task scope"
    if phase == "VERIFYING":
        if role_id == "verify_runner":
            return "verifying", "Verify Runner niche — tests / self-check gate"
        return "waiting_verify", "Waiting on verify gate before merge"
    if phase == "WAITING":
        return "queued", "Queued — next cursor-agent cycle launches 8 Task peers"
    if phase == "STOPPED":
        return "offline", "Peer loop stopped"
    if phase == "IDLE":
        return "idle", "Standing by — last assignment below"
    return "idle", base_detail or "Standing by"


def build_board(*, refresh_roster: bool = True) -> dict[str, Any]:
    """Birds-eye board: orchestrator + 8 niches + worktrees + peer runtime."""
    roster = ensure_roster() if refresh_roster else (_safe_read_json(ROSTER_PATH) or {})
    runtime = _peer_runtime()
    phase = runtime["phase"]

    orch = dict(roster.get("orchestrator") or {})
    orch.setdefault("role_id", ORCHESTRATOR_ID)
    orch.setdefault("job_title", "Orchestrator")
    o_status, o_detail = _status_for_role(
        ORCHESTRATOR_ID,
        phase,
        str(orch.get("status") or "idle"),
        str(orch.get("detail") or ""),
    )
    orch["status"] = o_status
    orch["detail"] = o_detail
    orch["phase"] = phase

    agents_out: list[dict[str, Any]] = []
    roster_agents = roster.get("agents") or []
    if not roster_agents:
        cfg = auto.load_tasks_config()
        pool = roles.assign_worker_pool([], cfg)
        for i, asn in enumerate(pool, start=1):
            roster_agents.append(
                {
                    "slot": i,
                    "role_id": asn.role.id,
                    "job_title": asn.role.job_title,
                    "model": asn.role.model,
                    "subagent_type": asn.role.subagent_type,
                    "item": asn.item,
                    "item_plain": _plain_item(asn.item),
                    "score": asn.score,
                    "responsibilities": asn.role.responsibilities,
                    "reads": list(asn.role.reads),
                    "status": "planned",
                    "detail": "Niche backlog — awaiting dispatch",
                }
            )

    worktrees = _worktree_slots() or list(roster.get("worktrees") or [])
    wt_by_slot = {w.get("slot", ""): w for w in worktrees if isinstance(w, dict)}

    for agent in roster_agents:
        if not isinstance(agent, dict):
            continue
        row = dict(agent)
        rid = str(row.get("role_id") or "")
        st, det = _status_for_role(
            rid,
            phase,
            str(row.get("status") or "idle"),
            str(row.get("detail") or ""),
        )
        row["status"] = st
        row["detail"] = det
        slot_key = f"peer-{int(row.get('slot', 0)) - 1}" if row.get("slot") else ""
        wt = wt_by_slot.get(slot_key) or wt_by_slot.get(f"peer-{row.get('slot')}")
        if wt:
            row["worktree"] = wt
        agents_out.append(row)

    active = sum(1 for a in agents_out if a.get("status") in ("in_flight", "running", "verifying"))
    return {
        "updated_at": _now_iso(),
        "dispatch_iso": roster.get("dispatch_iso"),
        "dispatch_age_sec": (
            max(0.0, time.time() - float(roster.get("dispatch_ts") or 0))
            if roster.get("dispatch_ts")
            else None
        ),
        "worker_target": int(roster.get("worker_target") or roles.worker_pool_size()),
        "orchestrator": orch,
        "agents": agents_out,
        "summary": {
            "phase": phase,
            "phase_detail": runtime["phase_detail"],
            "active_agents": active,
            "total_agents": len(agents_out),
            "daemon_running": runtime.get("daemon_running"),
            "queue_count": runtime["queue_count"],
        },
        "peer": runtime,
        "worktrees": worktrees,
    }


def format_terminal(board: dict[str, Any]) -> str:
    lines: list[str] = []
    sm = board.get("summary") or {}
    lines.append(f"AGENT BOARD · phase {sm.get('phase')} · {sm.get('active_agents')}/{sm.get('total_agents')} active")
    if sm.get("phase_detail"):
        lines.append(f"  {sm['phase_detail']}")
    lines.append("")
    orch = board.get("orchestrator") or {}
    lines.append(f"▸ {orch.get('job_title')} [{orch.get('status')}] — {orch.get('detail')}")
    lines.append("")
    for a in board.get("agents") or []:
        title = a.get("job_title", "?")
        st = a.get("status", "?")
        item = a.get("item_plain") or _plain_item(str(a.get("item") or ""), limit=56)
        lines.append(f"  {a.get('slot', '?')}. {title} [{st}]")
        lines.append(f"     {item}")
        if a.get("detail"):
            lines.append(f"     → {a['detail']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Automation hub agent board")
    parser.add_argument("--json", action="store_true", help="Print board JSON")
    parser.add_argument("--watch", action="store_true", help="Live terminal refresh")
    parser.add_argument("--note", nargs=3, metavar=("ROLE_ID", "STATUS", "DETAIL"), help="Update one agent note")
    parser.add_argument("--refresh-plan", action="store_true", help="Rebuild roster from current plan")
    args = parser.parse_args(argv)

    if args.note:
        ok = update_agent_note(args.note[0], args.note[1], args.note[2])
        return 0 if ok else 1

    if args.refresh_plan:
        import peer_orchestrate as po

        record_dispatch(po.build_plan(quick=True, loop=True))

    if args.watch:
        import os

        try:
            while True:
                board = build_board()
                os.system("clear" if os.name != "nt" else "cls")
                print(format_terminal(board))
                print(f"\n(refresh 3s · {board.get('updated_at')})")
                time.sleep(3.0)
        except KeyboardInterrupt:
            return 0

    board = build_board()
    if args.json:
        print(json.dumps(board, indent=2))
    else:
        print(format_terminal(board))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
