"""DGX utilization orchestrator — near-full CPU/GPU/RAM with compressed productive pins."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import dgx_ram_budget as budget  # noqa: E402
import dgx_ram_efficiency as eff  # noqa: E402
import dgx_ram_fill as fill  # noqa: E402
import factory_grid as grid  # noqa: E402
import factory_sprint as sprint  # noqa: E402
import peer_parallel_dispatch as ppd  # noqa: E402
import peer_roles as roles  # noqa: E402
import peer_worktree as wt  # noqa: E402
import project_automation as auto  # noqa: E402


def _cfg() -> dict[str, Any]:
    raw = auto.CFG.get("dgx_utilization")
    return raw if isinstance(raw, dict) else {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", True))


def interval_sec() -> float:
    try:
        return max(10.0, float(_cfg().get("interval_sec") or 30))
    except (TypeError, ValueError):
        return 30.0


def target_used_ram_pct() -> float:
    try:
        return min(0.95, max(0.5, float(_cfg().get("target_used_ram_pct") or 0.88)))
    except (TypeError, ValueError):
        return 0.88


def max_productive_shm_gb() -> float:
    try:
        return max(4.0, float(_cfg().get("max_productive_shm_gb") or 24))
    except (TypeError, ValueError):
        return 24.0


def target_agent_fill() -> int:
    """Desired agent count — never above ``max_parallel_peers`` (worktree pool).

    Local/dgx_speed overlays can leave ``target_agent_fill: 48`` after peers
    drop to 8; ``_nudge_agents`` must not chase 48 hub slots (flaw-research).
    """
    peers = auto.max_parallel_peers()
    try:
        raw = int(_cfg().get("target_agent_fill") or grid.global_agent_cap())
    except (TypeError, ValueError):
        raw = grid.global_agent_cap()
    return max(1, min(raw, peers))


def unittest_cap() -> int:
    try:
        return max(2, int(_cfg().get("unittest_cap") or auto.CFG.get("dgx_unittest_cap") or 12))
    except (TypeError, ValueError):
        return 12


def self_check_cap() -> int:
    try:
        return max(1, int(_cfg().get("self_check_cap") or auto.CFG.get("dgx_self_check_cap") or 2))
    except (TypeError, ValueError):
        return 2


def hub_dispatch_enabled() -> bool:
    return bool(_cfg().get("hub_dispatch", True))


def worktree_pool_size() -> int:
    """Hub worktree pool target — clamped to ``max_parallel_peers``.

    Stale ``worktree_pool: 48`` after peers=8 must not re-inflate peer-0..47.
    """
    peers = auto.max_parallel_peers()
    try:
        raw = int(_cfg().get("worktree_pool") or grid.hub_agent_cap())
    except (TypeError, ValueError):
        raw = grid.hub_agent_cap()
    # Floor at 1 (not 8): when peers < 8, max(8, raw) would ignore the peer cap.
    return max(1, min(raw, peers))


def noop_poke_enabled() -> bool:
    return bool(_cfg().get("noop_poke", True))


def ram_fill_enabled() -> bool:
    raw = _cfg().get("ram_fill")
    if raw is not None:
        return bool(raw)
    return not eff.stable_mode()


def _log(msg: str, log_fn: Callable[[str], None] = print) -> None:
    log_fn(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  util: {msg}")


_last_cycle_after: dict[str, Any] | None = None


def _gpu_snapshot() -> dict[str, Any]:
    try:
        import dgx_gpu_events as gev

        return gev.gpu_snapshot()
    except ImportError:
        pass
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,power.draw,memory.used,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8.0,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return {}
        parts = [p.strip() for p in proc.stdout.strip().split(",")]
        return {
            "gpu_util_pct": float(parts[0]) if parts else 0.0,
            "gpu_power_w": float(parts[1]) if len(parts) > 1 else 0.0,
            "gpu_mem_mib": parts[2] if len(parts) > 2 else "0",
            "gpu_temp_c": float(parts[3]) if len(parts) > 3 else 0.0,
        }
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}


def _python_worker_count() -> int:
    proc_root = Path("/proc")
    if proc_root.is_dir():
        count = 0
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                comm = (entry / "comm").read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            if comm in ("python3", "python", "Python"):
                count += 1
        return count
    try:
        proc = subprocess.run(
            ["pgrep", "-c", "python3"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
        return int((proc.stdout or "0").strip() or 0)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0


def snapshot() -> dict[str, Any]:
    mem = budget.mem_stats()
    agents = eff.agent_count()
    agent_cap = grid.global_agent_cap()
    productive = fill.productive_shm_gb()
    pinned = fill.pinned_shm_gb()
    total = mem["total_gb"] or 121.0
    target_used = min(
        budget.ram_max_used_gb() or total * target_used_ram_pct(),
        total * target_used_ram_pct(),
    )
    return {
        "mem_total_gb": mem["total_gb"],
        "mem_used_gb": mem["used_gb"],
        "mem_avail_gb": mem["avail_gb"],
        "target_used_gb": round(target_used, 1),
        "productive_shm_gb": round(productive, 2),
        "max_productive_shm_gb": max_productive_shm_gb(),
        "pinned_shm_gb": round(pinned, 2),
        "agents": agents,
        "agent_cap": agent_cap,
        "target_agents": target_agent_fill(),
        "python_workers": _python_worker_count(),
        "unittest_workers": budget.unittest_worker_count(),
        **_gpu_snapshot(),
    }


def _trim_storm(*, log_fn: Callable[[str], None]) -> int:
    killed = 0
    if auto.CFG.get("trim_agents_over_cap", True):
        trimmed_agents = ppd.trim_agents_over_cap(log_fn=lambda m: _log(m.replace("parallel:", "agents:"), log_fn))
        if trimmed_agents:
            killed += trimmed_agents
    sc_cap = self_check_cap()
    cap = unittest_cap()
    # OVERSEER_TRIM_ONE_CENSUS_2026_09_06 — one /proc walk for sc+ut (was 2×).
    sc_pids, ut_pids = budget.classify_storm_worker_pids()
    sc_count = len(sc_pids)
    if sc_count > sc_cap:
        trimmed = budget.trim_self_check_storm(cap=sc_cap, pids=sc_pids)
        if trimmed:
            killed += trimmed
            _log(f"trimmed {trimmed} self-check workers ({sc_count} > {sc_cap})", log_fn)
    count = len(ut_pids)
    if count > cap:
        trimmed_ut = budget.trim_unittest_storm(cap=cap, pids=ut_pids)
        if trimmed_ut:
            killed += trimmed_ut
            _log(f"trimmed {trimmed_ut} unittest workers ({count} > {cap})", log_fn)
    # OVERSEER_STORM_BRAKE_2026_09_03 — never pkill automation_adapt.py.
    # Self-check + unittest trims above are the budget-safe path; SIGKILL on
    # adapt wiped live heal/adapt mid-verify and caused factory stalls.
    py_count = _python_worker_count()
    if py_count > cap * 8:
        _log(f"storm brake observe-only — python workers {py_count} (no adapt pkill)", log_fn)
    return killed


def _fill_toward_target(*, log_fn: Callable[[str], None]) -> dict[str, Any]:
    if not ram_fill_enabled():
        return {"fill": "disabled"}
    try:
        import dgx_ram_priority as priority

        if priority.enabled():
            report = priority.govern(log_fn=lambda m: _log(m.replace("govern:", "priority:"), log_fn))
            return report
    except ImportError:
        pass
    if eff.stable_mode():
        if not fill.fill_pressure_ok():
            mem = budget.mem_stats()
            return {
                "fill": "pressure_hold",
                "avail_gb": mem["avail_gb"],
                "headroom_gb": eff.fill_headroom_gb(),
            }
        if fill.productive_shm_gb() >= eff.effective_productive_target_gb():
            return {"fill": "productive_at_target"}
        report = fill.maintain_ram_stable(log_fn=lambda m: _log(m, log_fn))
        report["productive_target_gb"] = round(eff.effective_productive_target_gb(), 1)
        return report
    mem = budget.mem_stats()
    target_used = min(
        budget.ram_max_used_gb() or mem["total_gb"] * target_used_ram_pct(),
        mem["total_gb"] * target_used_ram_pct(),
    )
    gap = target_used - mem["used_gb"]
    if gap < 2.0:
        return {"fill": "at_target"}
    if not fill.fill_pressure_ok():
        return {"fill": "pressure_hold", "avail_gb": mem["avail_gb"]}
    report = fill.rebalance_ram(log_fn=lambda m: _log(m, log_fn))
    report["used_gap_gb"] = round(gap, 1)
    report["productive_target_gb"] = round(eff.effective_productive_target_gb(), 1)
    return report


def _nudge_agents(*, log_fn: Callable[[str], None]) -> dict[str, Any]:
    agents = eff.agent_count()
    target = target_agent_fill()
    try:
        mode = budget.ram_mode()
        cap = budget.ram_agent_cap()
        if not budget.dispatch_allowed():
            return {
                "agents": agents,
                "nudged": False,
                "target": target,
                "ram_mode": mode,
                "agent_cap": cap,
                "skipped": "ram_event_block",
            }
        target = min(target, cap)
    except Exception:  # noqa: BLE001
        mode = "hold"
        cap = target
    if agents >= target:
        return {"agents": agents, "nudged": False, "target": target, "at_cap": True, "ram_mode": mode}
    reports: dict[str, Any] = {"agents": agents, "target": target}
    hub_report = _dispatch_hub_parallel(log_fn=log_fn)
    reports["hub"] = hub_report
    sprint_report = sprint.run_sprint_cycle(log_fn=lambda m: _log(m.replace("factory_sprint:", "sprint:"), log_fn))
    reports["external"] = sprint_report
    reports["nudged"] = bool((hub_report.get("launched") or 0) > 0 or sprint_report.get("launched"))
    return reports


def _ensure_worktree_pool(*, log_fn: Callable[[str], None]) -> dict[str, Any]:
    # OVERSEER_READY_PRUNE_2026_09_03 — hub-protect needle: never skip prune on floor-ready
    """Ensure floor slots exist and always prune excess + ensure_parallel_pool.

    Must not short-circuit on peer-0..N-1 dirs alone — that skips
    ``prune_excess`` / nested prune, so inflated pools (peer-8..47) stick
    forever (flaw-research: ready-short-circuit skips prune_excess).
    Call ``prune_excess_parallel_pool`` even when floor dirs already exist;
    ``ensure_parallel_pool`` also prunes, but an old in-memory daemon or a
    future ensure skip must not leave excess slots.
    """
    want = min(worktree_pool_size(), auto.max_parallel_peers())
    rel_base, prefix = wt.parallel_pool_config()
    pool_root = (ROOT / rel_base).resolve()
    floor_ready = all((pool_root / f"{prefix}-{i}").is_dir() for i in range(want))
    try:
        # OVERSEER_READY_PRUNE_2026_09_03 — always prune first; floor-ready ≠ skip.
        excess = wt.prune_excess_parallel_pool(
            cap=auto.max_parallel_peers(),
            log_fn=lambda m: _log(m.replace("worktree pool:", "worktrees:"), log_fn),
        )
        paths = wt.ensure_parallel_pool(
            count=want,
            log_fn=lambda m: _log(m.replace("worktree pool:", "worktrees:"), log_fn),
        )
        return {
            "pool": len(paths),
            "target": want,
            "ready": floor_ready or len(paths) >= want,
            "excess_found": int(excess.get("found") or 0),
            "excess_removed": len(excess.get("removed") or []),
        }
    except Exception as exc:  # noqa: BLE001
        _log(f"worktree pool error — {exc}", log_fn)
        return {"pool": 0, "error": str(exc), "ready": False}


def _dispatch_hub_parallel(*, log_fn: Callable[[str], None]) -> dict[str, Any]:
    if not hub_dispatch_enabled() or not grid.grid_enabled():
        return {"skipped": True}
    hub_cap = grid.hub_agent_cap()
    global_running = len(ppd.find_agent_procs())
    hub_running = global_running - ppd.count_agents_outside(hub_worktree_root=grid.hub_worktree_root())
    if hub_running >= hub_cap:
        return {"hub_running": hub_running, "hub_cap": hub_cap, "launched": 0}
    import peer_orchestrate as po

    plan = po.build_plan(quick=True, loop=True)
    items = list(plan.live.get("open_items") or [])
    slots = min(hub_cap - hub_running, hub_cap)
    assignments = roles.assign_worker_pool(items, auto.load_tasks_config(), worker_count=slots)
    if not assignments:
        return {"launched": 0, "reason": "no_assignments"}
    slots = min(hub_cap - hub_running, hub_cap, len(assignments))
    batch = assignments[:slots]
    paid = os.environ.get("PEER_LOOP_PAID_API") == "1"
    rc, auth_failed = ppd.run_parallel_niche_cycle(
        batch,
        log_fn=log_fn,
        paid_api=paid,
        max_workers=slots,
    )
    return {"launched": len(batch), "slots": slots, "rc": rc, "auth_failed": auth_failed}


def _poke_noop_loop(*, log_fn: Callable[[str], None]) -> bool:
    if not noop_poke_enabled():
        return False
    state_path = auto.CONFIG_DIR / "peer-loop-state.json"
    if not state_path.is_file():
        return False
    try:
        data = json.loads(state_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    lc = data.get("last_cycle") or {}
    if not lc.get("verify_ok"):
        return False
    fp_before = lc.get("queue_fp_before")
    fp_after = lc.get("queue_fp_after")
    if not fp_before or fp_before != fp_after:
        return False
    signal = auto.CONFIG_DIR / "peer-turn.signal"
    try:
        signal.write_text(f"{time.time()}\nnoop-poke\n")
        _log("noop poke — queue fingerprint unchanged after ok cycle", log_fn)
        return True
    except OSError:
        return False


def run_cycle(*, log_fn: Callable[[str], None] = print) -> dict[str, Any]:
    if not enabled():
        return {"enabled": False}
    ram_event_report: dict[str, Any] = {}
    gpu_event_report: dict[str, Any] = {}
    try:
        import dgx_ram_events as events

        ram_event_report = events.handle_events(
            log_fn=lambda m: _log(m.replace("ram event:", "ram:"), log_fn)
        )
    except ImportError:
        pass
    try:
        import dgx_gpu_events as gev

        gpu_event_report = gev.handle_events(
            log_fn=lambda m: _log(m.replace("gpu event:", "gpu:"), log_fn)
        )
    except ImportError:
        pass
    global _last_cycle_after
    before = _last_cycle_after if _last_cycle_after is not None else snapshot()
    _trim_storm(log_fn=log_fn)
    worktree_report = _ensure_worktree_pool(log_fn=log_fn)
    fill_report = _fill_toward_target(log_fn=log_fn)
    agent_report = _nudge_agents(log_fn=log_fn)
    noop_poked = _poke_noop_loop(log_fn=log_fn)
    after = snapshot()
    _last_cycle_after = after
    report = {
        "before": before,
        "after": after,
        "ram_events": ram_event_report,
        "gpu_events": gpu_event_report,
        "worktrees": worktree_report,
        "fill": fill_report,
        "agents": agent_report,
        "noop_poked": noop_poked,
    }
    _log(
        f"used {after['mem_used_gb']}/{after['mem_total_gb']}GB "
        f"productive {after['productive_shm_gb']}/{after['max_productive_shm_gb']}GB "
        f"agents {after['agents']}/{after['target_agents']} "
        f"gpu {after.get('gpu_util_pct', 0):.0f}% "
        f"py {after['python_workers']}",
        log_fn,
    )
    return report


def run_forever() -> None:
    _log("forever loop started")
    while True:
        try:
            run_cycle()
        except Exception as exc:  # noqa: BLE001
            _log(f"cycle error — {exc}")
        time.sleep(interval_sec())


def main() -> int:
    parser = argparse.ArgumentParser(description="DGX utilization orchestrator")
    parser.add_argument("--forever", action="store_true")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.snapshot or (args.json and not args.forever):
        payload = snapshot()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(json.dumps(payload, indent=2))
        return 0
    if args.forever:
        run_forever()
        return 0
    report = run_cycle(log_fn=lambda m: None if args.json else print(m))
    if args.json:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
