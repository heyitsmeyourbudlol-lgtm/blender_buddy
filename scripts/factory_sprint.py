#!/usr/bin/env python3
"""External-proof agent lanes — fill spare DGX RAM with registry repo work."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import factory_fanout as fanout  # noqa: E402
import factory_grid as grid  # noqa: E402
import peer_parallel_dispatch as ppd  # noqa: E402
import peer_terminal as terminal  # noqa: E402
import project_automation as auto  # noqa: E402


def _log(msg: str) -> None:
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}", flush=True)


def _lane_agents(lane: dict[str, Any]) -> int:
    try:
        return max(1, int(lane.get("agents") or 4))
    except (TypeError, ValueError):
        return 4


def _build_external_prompt(*, name: str, repo_path: Path) -> str:
    return f"""# External proof sprint — {name}

You are a **factory lane agent** on the DGX Spark. Work **only** in this repo.

**Repo:** `{repo_path}`
**Mission:** adapt → native verify → minimal irreversible artifact (PR-shaped diff).

## Steps (execute now — no plan-only output)
1. Run `python3 {ROOT}/scripts/automation_adapt.py --target {repo_path} --heal --write --quick` if kit not installed; else `--audit`.
2. Use the repo's **native** verify command (npm test, pytest, etc.) — not the hub unittest suite unless this IS the hub.
3. Land **one** scoped improvement: fix a failing test, wire verify gate, or install automation kit profile.
4. Prefer worktree/branch isolation if git is dirty on main.
5. Stop when verify passes or you have a concrete blocker with log excerpt.

**North star:** OSS monster factory — external proof that adapt→verify→artifact works without babysitting.
Implement now.
"""


def _dispatch_lane(
    lane: dict[str, Any],
    *,
    log_fn: Callable[[str], None],
    paid_api: bool,
) -> tuple[int, bool]:
    raw_path = str(lane.get("path") or lane.get("name") or "")
    repo = fanout.resolve_repo_path(raw_path)
    if repo is None:
        log_fn(f"factory_sprint: skip {lane.get('name')} — path missing on DGX")
        return 0, False
    prompt = _build_external_prompt(name=str(lane.get("name") or repo.name), repo_path=repo)
    log_fn(f"factory_sprint: launch {lane.get('name')} · cwd={repo}")
    return terminal.run_cursor_agent(
        prompt, log_fn=log_fn, paid_api=paid_api, cwd=repo, sync=False
    )


def run_sprint_cycle(*, log_fn: Callable[[str], None] = _log) -> dict[str, Any]:
    try:
        import dgx_resource_priority as rp

        if rp.guard_development(log_fn=log_fn):
            return {"launched": 0, "reason": "infra_beep"}
    except ImportError:
        pass
    if not grid.grid_enabled() or grid.external_agent_cap() <= 0:
        return {"launched": 0, "reason": "automation_only"}

    paid_api = os.environ.get("PEER_LOOP_PAID_API") == "1"
    global_cap = grid.global_agent_cap()
    external_cap = grid.external_agent_cap()
    global_running = len(ppd.find_agent_procs())
    external_running = ppd.count_agents_outside(hub_worktree_root=grid.hub_worktree_root())

    if global_running >= global_cap:
        log_fn(f"factory_sprint: global cap ({global_running}/{global_cap})")
        return {"launched": 0, "reason": "global_cap"}

    if external_running >= external_cap:
        log_fn(f"factory_sprint: external cap ({external_running}/{external_cap})")
        return {"launched": 0, "reason": "external_cap"}

    slots = min(external_cap - external_running, global_cap - global_running)
    launched = 0
    lanes = grid.external_lanes()

    for lane in lanes:
        if slots <= 0:
            break
        raw_path = str(lane.get("path") or "")
        repo = fanout.resolve_repo_path(raw_path)
        if repo is None:
            continue
        lane_cap = _lane_agents(lane)
        lane_running = ppd.count_agents_under(repo)
        need = lane_cap - lane_running
        if need <= 0:
            continue
        take = min(need, slots)
        for _ in range(take):
            rc, auth_failed = _dispatch_lane(lane, log_fn=log_fn, paid_api=paid_api)
            launched += 1
            slots -= 1
            if auth_failed:
                return {"launched": launched, "auth_failed": True}
            if rc != 0:
                log_fn(f"factory_sprint: agent rc={rc}")
        log_fn(f"factory_sprint: {lane.get('name')} +{take} (lane {lane_running + take}/{lane_cap})")

    return {"launched": launched}


def run_forever() -> None:
    _log("factory_sprint: forever loop started")
    while True:
        try:
            run_sprint_cycle()
        except Exception as exc:  # noqa: BLE001
            _log(f"factory_sprint: error — {exc}")
        time.sleep(grid.sprint_interval_sec())


def main() -> int:
    parser = argparse.ArgumentParser(description="External-proof agent lanes on DGX")
    parser.add_argument("--forever", action="store_true")
    args = parser.parse_args()
    if args.forever:
        run_forever()
        return 0
    report = run_sprint_cycle()
    return 0 if report.get("launched", 0) >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
