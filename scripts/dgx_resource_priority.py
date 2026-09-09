"""Resource priority — RAM/GPU infra fixes before automation development."""

from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import project_automation as auto

STATE_PATH = auto.CONFIG_DIR / "resource-priority-state.json"
# Written by dgx_resource_poll — improve/peer guard reads this instead of CDLL(NVML/CUDA).
# OVERSEER_HUB_POLL_LATEST_2026_09_04 — stop improve crash-loop on peer-N overlay Path races.
POLL_LATEST_PATH = auto.CONFIG_DIR / "resource-poll-latest.json"

MODE_SEVERITY = {
    "hold": 0,
    "boost": 1,
    "trim": 1,
    "pressure": 2,
    "emergency": 3,
}


def _cfg() -> dict[str, Any]:
    raw = auto.CFG.get("resource_priority")
    return raw if isinstance(raw, dict) else {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", True))


def pause_development_when_beeping() -> bool:
    return bool(_cfg().get("pause_development_when_beeping", True))


def kill_dev_agents_on_beep() -> bool:
    return bool(_cfg().get("kill_dev_agents_on_beep", True))


def resource_fix_cooldown_sec() -> float:
    try:
        return max(30.0, float(_cfg().get("resource_fix_cooldown_sec") or 90))
    except (TypeError, ValueError):
        return 90.0


def poll_latest_ttl_sec() -> float:
    """TTL for reusing resource-poll-latest.json (skip NVML/CUDA on guard ticks).

    OVERSEER_HUB_POLL_LATEST_2026_09_04
    """
    try:
        raw = _cfg().get("poll_latest_ttl_sec")
        if raw is None:
            raw = auto.CFG.get("resource_poll_latest_ttl_sec")
        return max(0.0, float(raw if raw is not None else 45))
    except (TypeError, ValueError):
        return 45.0


def _poll_latest_paths() -> list[Path]:
    """Candidate poll-latest paths (CONFIG_DIR first, then hub namespaces).

    Needle: COMPRESSION_POLL_MULTI_PATH_2026_09_04 + OVERSEER_HUB_POLL_LATEST_2026_09_04
    OVERSEER_PATH_LOCAL_IMPORT_2026_09_04 — peer-N overlays loaded via
    ``spec_from_file_location`` can race Mac rsync and leave module-level
    ``Path`` unbound → improve crash-loop ``NameError: Path``. Local import
    survives that race.
    """
    from pathlib import Path as _Path  # OVERSEER_PATH_LOCAL_IMPORT_2026_09_04

    seen: set[str] = set()
    out: list[Path] = []
    for path in (
        POLL_LATEST_PATH,
        _Path.home() / ".config" / "automation-hub" / "resource-poll-latest.json",
        _Path.home() / ".config" / "automation" / "resource-poll-latest.json",
    ):
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out



def _read_poll_latest(*, max_age_sec: float | None = None) -> dict[str, Any] | None:
    """Return poll-latest snapshot when fresh — never spawns NVML/CUDA."""
    ttl = poll_latest_ttl_sec() if max_age_sec is None else max(0.0, float(max_age_sec))
    if ttl <= 0.0:
        return None
    now = time.time()
    for path in _poll_latest_paths():
        try:
            if not path.is_file():
                continue
            age = now - path.stat().st_mtime
            if age > ttl:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and "beeping" in data:
            return data
    return None


def _load_state() -> dict[str, Any]:
    try:
        if STATE_PATH.is_file():
            return json.loads(STATE_PATH.read_text())
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return {}


def _save_state(state: dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, indent=2))
    except OSError:
        pass


def _ram_snapshot() -> dict[str, Any]:
    try:
        import dgx_ram_events as rev

        if rev.enabled():
            return rev.snapshot()
    except ImportError:
        pass
    try:
        import dgx_ram_budget as budget

        stats = budget.mem_stats()
        mode = budget.ram_mode(stats=stats)
        return {"mode": mode, "footprint_gb": stats["footprint_gb"], "enabled": True}
    except ImportError:
        return {"mode": "hold", "enabled": False}


def _gpu_snapshot() -> dict[str, Any]:
    try:
        import dgx_gpu_events as gev

        if gev.enabled():
            return gev.snapshot()
    except ImportError:
        return {"mode": "hold", "enabled": False}


def ram_beeping(*, ram: dict[str, Any] | None = None) -> bool:
    snap = ram if ram is not None else _ram_snapshot()
    if not snap.get("enabled", True):
        return False
    return str(snap.get("mode") or "hold") != "hold"


def gpu_beeping(*, gpu: dict[str, Any] | None = None) -> bool:
    snap = gpu if gpu is not None else _gpu_snapshot()
    if not snap.get("enabled", True):
        return False
    return str(snap.get("mode") or "hold") != "hold"


def beeping(*, ram: dict[str, Any] | None = None, gpu: dict[str, Any] | None = None) -> bool:
    if not enabled():
        return False
    # Compression: prefer poll-latest when caller did not pass snaps (guard hot path).
    # OVERSEER_HUB_POLL_LATEST_2026_09_04
    if ram is None and gpu is None:
        cached = _read_poll_latest()
        if cached is not None:
            return bool(cached.get("beeping"))
    return ram_beeping(ram=ram) or gpu_beeping(gpu=gpu)


def development_allowed(*, ram: dict[str, Any] | None = None, gpu: dict[str, Any] | None = None) -> bool:
    if not enabled() or not pause_development_when_beeping():
        return True
    return not beeping(ram=ram, gpu=gpu)


def worst_mode(*, ram: dict[str, Any] | None = None, gpu: dict[str, Any] | None = None) -> str:
    ram_mode = str((ram or _ram_snapshot()).get("mode") or "hold")
    gpu_mode = str((gpu or _gpu_snapshot()).get("mode") or "hold")
    if MODE_SEVERITY.get(ram_mode, 0) >= MODE_SEVERITY.get(gpu_mode, 0):
        return ram_mode
    return gpu_mode


def snapshot(
    *,
    ram: dict[str, Any] | None = None,
    gpu: dict[str, Any] | None = None,
    force_live: bool = False,
) -> dict[str, Any]:
    """Combined RAM+GPU priority snap.

    ``force_live=True`` — always probe (resource-poll writer). Default prefers
    fresh ``resource-poll-latest.json`` so improve ``guard_development`` does not
    CDLL libnvidia-ml/libcuda every tick.
    Needle: COMPRESSION_POLL_LATEST_GUARD_2026_09_04 + OVERSEER_HUB_POLL_LATEST_2026_09_04
    """
    if not force_live and ram is None and gpu is None:
        cached = _read_poll_latest()
        if cached is not None:
            return dict(cached)
    ram_snap = ram if ram is not None else _ram_snapshot()
    gpu_snap = gpu if gpu is not None else _gpu_snapshot()
    bp = beeping(ram=ram_snap, gpu=gpu_snap)
    return {
        "beeping": bp,
        "development_allowed": development_allowed(ram=ram_snap, gpu=gpu_snap),
        "worst_mode": worst_mode(ram=ram_snap, gpu=gpu_snap),
        "ram": ram_snap,
        "gpu": gpu_snap,
    }


def _build_resource_fix_prompt(*, snap: dict[str, Any]) -> str:
    ram = snap.get("ram") or {}
    gpu = snap.get("gpu") or {}
    return f"""# INFRA PRIORITY — drop all development work

**RAM and GPU management come before automation development.** Fix resource usage now.

## Status
- **BEEPING:** {snap.get('beeping')} · worst mode: `{snap.get('worst_mode')}`
- **RAM:** mode `{ram.get('mode')}` · footprint **{ram.get('footprint_gb', '?')}GB** / target **{ram.get('target_gb', 100)}GB**
- **GPU:** mode `{gpu.get('mode')}` · util **{gpu.get('gpu_util_pct', '?')}%** / target **{gpu.get('target_util_pct', 80)}%**

## Do this now (nothing else)
1. **Stop** automation_improve, peer dev dispatch, factory sprint, and kit polish until resources are green.
2. Run and read:
   - `python3 scripts/dgx_ram_budget.py --priority-snapshot --json`
   - `python3 scripts/dgx_gpu_events.py --snapshot --json`
   - `python3 scripts/dgx_resource_priority.py --snapshot --json`
3. Fix **resident RAM footprint** toward ~100GB (tiered replace — never mass-kill to empty).
4. Fix **GPU utilization** with productive Mamba embed (126k chunks) — not synthetic GEMM.
5. Tune only: `dgx_ram_events.py`, `dgx_ram_priority.py`, `dgx_gpu_events.py`, `dgx_gpu_compute.py`, `automation.config.local.json`.
6. Verify green, then exit — peer-loop will resume development.

**Do not** enqueue features, refactor unrelated code, or run automation_improve cycles until `development_allowed` is true.
"""


def _kill_development_agents(*, log_fn: Callable[[str], None]) -> int:
    try:
        import peer_parallel_dispatch as ppd
    except ImportError:
        return 0
    killed = 0
    for proc in ppd.find_agent_procs():
        if proc.pid <= 0:
            continue
        try:
            os.kill(proc.pid, signal.SIGKILL)
            killed += 1
        except OSError:
            pass
    if killed:
        log_fn(f"resource priority: dropped {killed} cursor-agent dev worker(s)")
    return killed


def _dispatch_resource_fix_agent(*, snap: dict[str, Any], log_fn: Callable[[str], None]) -> bool:
    state = _load_state()
    now = time.time()
    # Hard mute — parallel INFRA agents thrash-restart dgx-gpu-compute mid-load
    # (needle 2026-09-07: NRestarts storm, permanent emergency). Mechanical
    # governors (ram_events / gpu_compute) fix resources; do not spawn more agents.
    try:
        disabled_until = float(state.get("dispatch_disabled_until") or 0)
    except (TypeError, ValueError):
        disabled_until = 0.0
    if disabled_until > now:
        log_fn("resource priority: fix dispatch muted (dispatch_disabled_until)")
        return False
    # Default mute while GPU forever is warming/embedding — agents only fight it.
    try:
        import dgx_gpu_events as gev

        if gev._gpu_compute_process_active():
            log_fn("resource priority: fix dispatch skipped — gpu_compute active")
            return False
    except Exception:  # noqa: BLE001
        pass
    last = float(state.get("last_fix_dispatch_ts") or 0)
    if now - last < resource_fix_cooldown_sec():
        return False
    try:
        import peer_terminal as terminal

        ready, detail = terminal.desktop_auth_ready()
        if not ready:
            log_fn(f"resource priority: cursor-agent skip — {detail}")
            return False
        prompt = _build_resource_fix_prompt(snap=snap)
        rc, _auth_fail = terminal.run_cursor_agent(
            prompt,
            log_fn=log_fn,
            sync=False,
            paid_api=False,
        )
        if rc == 0:
            state["last_fix_dispatch_ts"] = now
            _save_state(state)
            return True
    except Exception as exc:  # noqa: BLE001
        log_fn(f"resource priority: fix dispatch failed — {exc}")
    return False


def _emit_beep_event(*, snap: dict[str, Any], transition: bool) -> None:
    try:
        import automation_engine as engine

        ram = snap.get("ram") or {}
        gpu = snap.get("gpu") or {}
        engine.emit(
            "resource.beep",
            {
                "beeping": snap.get("beeping"),
                "development_blocked": not snap.get("development_allowed"),
                "worst_mode": snap.get("worst_mode"),
                "ram_mode": ram.get("mode"),
                "gpu_mode": gpu.get("mode"),
                "footprint_gb": ram.get("footprint_gb"),
                "gpu_util_pct": gpu.get("gpu_util_pct"),
                "transition": transition,
                "note": "RAM/GPU infra priority — pause automation development",
            },
        )
    except Exception:  # noqa: BLE001
        pass


def _run_mechanical_fixes(
    *,
    log_fn: Callable[[str], None],
    snap: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply RAM/GPU mode actions. Prefer poll-latest gpu snap to skip NVML CDLL.

    Needle: COMPRESSION_POLL_GUARD_SKIP_NVML_2026_09_05 — improve ``guard_development``
    while beeping previously called ``dgx_gpu_events.handle_events`` → ``gpu_snapshot``
    → ``ctypes.CDLL(libnvidia-ml)`` every tick (~+20 MB sticky + libcuda) even when
    ``resource-poll-latest.json`` was fresh. Pass ``snap["gpu"]`` when present.
    """
    report: dict[str, Any] = {}
    try:
        import dgx_ram_events as rev

        if rev.enabled():
            report["ram"] = rev.handle_events(log_fn=log_fn, skip_cursor_agent=True)
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        report["ram_error"] = str(exc)
    try:
        import dgx_gpu_events as gev

        if gev.enabled():
            gpu_snap = None
            if isinstance(snap, dict):
                raw_gpu = snap.get("gpu")
                if isinstance(raw_gpu, dict) and (
                    "gpu_util_pct" in raw_gpu or "mode" in raw_gpu or "effective_util_pct" in raw_gpu
                ):
                    gpu_snap = raw_gpu
            report["gpu"] = gev.handle_events(
                log_fn=log_fn,
                skip_cursor_agent=True,
                snap=gpu_snap,
            )
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        report["gpu_error"] = str(exc)
    return report


def handle_beep(*, log_fn: Callable[[str], None] = print, force_agent: bool = False) -> dict[str, Any]:
    """Mechanical RAM/GPU fix + optional cursor-agent — blocks development while beeping."""
    snap = snapshot()
    state = _load_state()
    was_beeping = bool(state.get("beeping"))
    now_beeping = bool(snap["beeping"])
    transition = was_beeping != now_beeping
    report: dict[str, Any] = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **snap,
        "transition": transition,
    }

    if now_beeping:
        if transition:
            log_fn(
                f"BEEP: infra priority — RAM `{snap['ram'].get('mode')}` GPU `{snap['gpu'].get('mode')}` "
                f"— development paused"
            )
        if transition and kill_dev_agents_on_beep():
            report["agents_killed"] = _kill_development_agents(log_fn=log_fn)
        # Pass poll-backed snap so GPU mechanical path skips NVML CDLL.
        report["mechanical"] = _run_mechanical_fixes(log_fn=log_fn, snap=snap)
        if transition or force_agent:
            _emit_beep_event(snap=snap, transition=transition)
        want_agent = force_agent or transition or (
            now_beeping and time.time() - float(state.get("last_fix_dispatch_ts") or 0) >= resource_fix_cooldown_sec()
        )
        if want_agent:
            if _dispatch_resource_fix_agent(snap=snap, log_fn=log_fn):
                report["resource_fix_dispatched"] = True
                log_fn("resource priority: dispatched cursor-agent — fix RAM/GPU now")
    elif transition:
        log_fn("resource priority: green — development may resume")
        _emit_beep_event(snap=snap, transition=True)

    state["beeping"] = now_beeping
    state["last_ts"] = time.time()
    state["worst_mode"] = snap.get("worst_mode")
    if transition:
        state["last_transition_ts"] = time.time()
    _save_state(state)
    return report


def guard_development(*, log_fn: Callable[[str], None] = print) -> bool:
    """If beeping, optionally handle infra and return True to skip dev work.

    When ``pause_development_when_beeping`` is False, return False immediately
    (do not call ``handle_beep``) so improve→peer wake is not blocked and
    mechanical RAM/GPU ticks do not SIGKILL free-desktop agents every cycle.
    Needle: OVERSEER_GUARD_RESPECT_PAUSE_2026_09_07
    """
    if not enabled() or not beeping():
        return False
    if not pause_development_when_beeping():
        return False
    handle_beep(log_fn=log_fn)
    return True


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="DGX resource priority — RAM/GPU before development")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--handle", action="store_true")
    parser.add_argument("--guard", action="store_true", help="Handle beep if active; exit 1 when dev blocked")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.snapshot or not (args.handle or args.guard):
        print(json.dumps(snapshot(), indent=2))
        return 0
    report = handle_beep(log_fn=lambda m: None if args.json else print(m))
    if args.json:
        print(json.dumps(report, indent=2))
    if args.guard and report.get("beeping"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
