"""Factory grid — split agent pool between hub worktrees and external repos."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import project_automation as auto

ROOT = auto.ROOT


def _grid() -> dict[str, Any]:
    raw = auto.CFG.get("factory_grid")
    return raw if isinstance(raw, dict) else {}


def grid_enabled() -> bool:
    return bool(_grid().get("enabled", False))


def automation_only() -> bool:
    return bool(_grid().get("automation_only", False))


def hub_agent_cap() -> int:
    """Hub niches to launch — never above ``max_parallel_peers`` (pool size).

    Config ``hub_agents`` (local=32, dgx_speed=48) can exceed the worktree pool.
    Uncapped ``_dispatch_hub_parallel`` then launches extras with cwd=ROOT.
    Always ``min(raw, max_parallel_peers())``.
    """
    try:
        raw = int(_grid().get("hub_agents") or auto.max_parallel_agent_procs())
    except (TypeError, ValueError):
        raw = auto.max_parallel_agent_procs()
    return max(1, min(raw, auto.max_parallel_peers()))


def external_agent_cap() -> int:
    try:
        return max(0, int(_grid().get("external_agents") or 0))
    except (TypeError, ValueError):
        return 0


def global_agent_cap() -> int:
    """Total agents to launch — never above ``max_parallel_peers``.

    Raw ``global_agents`` (local/dgx_speed often 48) filled the swarm while the
    worktree pool stayed at 8 — starve verify. Always ``min(raw, peers)``.
    OVERSEER_GLOBAL_CAP_CLAMP_2026_09_04
    """
    peers = auto.max_parallel_peers()
    try:
        cap = int(_grid().get("global_agents") or 0)
        if cap > 0:
            return max(1, min(cap, peers))
    except (TypeError, ValueError):
        pass
    return max(1, min(hub_agent_cap() + external_agent_cap(), peers))


def sprint_interval_sec() -> float:
    """Factory sprint heartbeat — floor at wake hard-min (15s).

    DGX overlays used interval_sec=8 (max(5,8)=8), ~3.75× churn vs peer
    continuous_wake floor. K8s sub-10s RequeueAfter is waste; Claude/Temporal
    empty floors are 60s — 15–30s is the healthy not-ready band.
    """
    hard_min = 15.0
    try:
        return max(hard_min, float(_grid().get("interval_sec") or 30))
    except (TypeError, ValueError):
        return 30.0


def external_lanes() -> list[dict[str, Any]]:
    raw = _grid().get("external_repos")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, str):
            out.append({"name": entry, "path": entry, "agents": 4})
        elif isinstance(entry, dict):
            out.append(dict(entry))
    return out


def hub_worktree_root() -> Path:
    rel = str(auto.CFG.get("parallel_worktree_dir") or ".worktrees")
    return (ROOT / rel).resolve()
