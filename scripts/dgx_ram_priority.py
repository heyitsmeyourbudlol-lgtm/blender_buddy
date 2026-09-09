"""Priority-ranked RAM governor — stable ~100GB via tiered evict + high-tier fill."""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import dgx_ram_budget as budget
import dgx_ram_efficiency as eff
import dgx_ram_fill as fill
import project_automation as auto

# Held by dgx_ram_events --forever (primary) or dgx_utilization --forever (fallback)
# when /dev/shm tmpfs is capped — anonymous resident pages toward ~100GB footprint.
_ANON_RESERVE: list[bytearray] = []
BALLAST_ROOT = Path("/dev/shm/automation-ballast")


def _swap_free_gb() -> float:
    try:
        total = free = 0
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("SwapTotal:"):
                total = int(line.split()[1])
            elif line.startswith("SwapFree:"):
                free = int(line.split()[1])
        return free / 1024 / 1024 if total else 99.0
    except (OSError, ValueError, IndexError):
        return 99.0


def fill_avail_floor_gb(*, gap: float | None = None) -> float:
    """Adaptive MemAvailable floor for under-target fill (not mass-allocate).

    Needle: CUDA allocator reserved ~24GB while student only needed ~250MB —
    MemAvailable sat ~8GB and mid-climb floors of 10–12GB froze footprint ~83GB.
    Last ~25GB of climb: allow down to critical (~6.5GB) with small chunks.

    Counter-needle: swap 100% full + floor 5.25 allowed anon grow into OOM-kill
    of ram_events (81GB peak → SIGKILL). When swap is exhausted, keep ≥10GB
    MemAvailable before growing footprint.
    """
    if gap is None:
        gap = target_used_gb() - budget.footprint_gb()
    try:
        configured = float(_cfg().get("min_fill_avail_gb") or 0)
    except (TypeError, ValueError):
        configured = 0.0
    base = configured if configured > 0 else 8.0
    crit = float(budget.ram_critical_avail_floor_gb())
    hard_min = 3.25
    swap_free = _swap_free_gb()
    # Exhausted swap + CUDA unified cache often parks MemAvailable at 5.5–6.5GB
    # while footprint sits ~88GB (/dev/shm full — only anon crumbs can finish).
    # Floor ≥7.0 froze the last climb forever (needle 2026-09-06). Allow down to
    # ~3.25–4.5 with 256–512MB crumbs; free_headroom must raise avail first when lower.
    if swap_free < 0.5:
        # CUDA unified cache parks MemAvailable at ~3.5–6.5GB while gap is still
        # 15–25GB (needle 2026-09-06: floor 7.0 → needs_fill False at fp~78 forever).
        # Allow crumbs from 3.25GB avail; free_headroom raises floor first when lower.
        if gap <= 30.0:
            return max(3.0, min(base if base > 0 else 3.75, 4.0))
        return max(3.5, min(base if base > 0 else 4.5, 5.0))
    # Last climb must be allowed below cfg critical=10 (that stall sat at ~89GB).
    # Final ~15GB: /dev/shm full leaves avail ~4.5–7GB — still allow 256MB crumbs.
    # hard_min was 5.0 with min(..., 4.75) → always 5.0 (blocked 4.5–5.0 windows).
    if gap <= 15.0:
        return max(hard_min, min(base if base > 0 else 4.5, 4.75))
    if gap <= 25.0:
        return max(hard_min, min(base if base > 0 else 5.5, 5.5))
    if gap <= 40.0:
        return max(4.0, min(base, max(crit, 8.0)))
    return max(base, 8.0)


def _fill_pressure_blocked(*, stats: dict[str, float] | None = None) -> bool:
    """True when MemAvailable/swap are too tight to grow footprint safely.

    Adaptive avail floor: far from target keep ≥8GB; last ~25GB of climb
    allows down to critical (~6.5GB) so we can actually reach ~100GB without
    permanent stall (needle: fixed 12GB floor left footprint stuck ~83GB while
    CUDA reserved 24GB of unused allocator cache).

    Needle: swap 100% full while MemAvailable ≈40GB permanently set needs_fill
    False — new resident anon uses free RAM and must not wait on swap reclaim.

    Needle: mid-climb (~83GB fp, ~8GB avail, CUDA cache bloat) also blocked —
    the old ≥10–12GB mid-climb gates froze the last ~15–20GB forever. Under-target
    with avail ≥ min_avail ignores exhausted swap.
    """
    if stats is None:
        stats = budget.mem_stats()
    gap = target_used_gb() - budget.footprint_gb()
    min_avail = fill_avail_floor_gb(gap=gap)
    try:
        min_swap = float(_cfg().get("min_fill_swap_free_gb") or 2.0)
    except (TypeError, ValueError):
        min_swap = 2.0
    if stats["avail_gb"] < min_avail:
        return True
    # Under footprint target with healthy MemAvailable: allocate from free/cache —
    # ignore exhausted swap (new anon does not need swap reclaim).
    if gap > hold_band_gb() and stats["avail_gb"] >= min_avail:
        return False
    # Ample MemAvailable: allocate from free/cache — ignore exhausted swap.
    if stats["avail_gb"] >= max(18.0, min_avail + 6.0):
        return False
    if gap > 20.0 and stats["avail_gb"] >= 15.0:
        return False
    if _swap_free_gb() < min_swap:
        return True
    return False


def anon_fill_blocked(*, stats: dict[str, float] | None = None) -> bool:
    """AnonPages growth needs free swap or healthy MemAvailable under target.

    When swap is exhausted but MemAvailable is above the adaptive fill floor,
    still allow anon — new resident pages come from free RAM, not swap reclaim.
    (Old ≥18GB floor left footprint stuck ~83GB with 8GB avail + CUDA cache bloat.)
    """
    if stats is None:
        stats = budget.mem_stats()
    gap = target_used_gb() - budget.footprint_gb()
    floor = fill_avail_floor_gb(gap=gap)
    if stats["avail_gb"] >= floor:
        return False
    if stats["avail_gb"] >= 18.0:
        return False
    try:
        min_swap = float(_cfg().get("min_fill_swap_free_gb") or 2.0)
    except (TypeError, ValueError):
        min_swap = 2.0
    if _swap_free_gb() < min_swap:
        return True
    return _fill_pressure_blocked(stats=stats)


def _ram_events_holder_alive() -> bool:
    for pid, cmd in budget.iter_proc_cmdlines():
        if "dgx_ram_events.py" in cmd and "--forever" in cmd and pid != os.getpid():
            return True
    return False


def _is_anon_holder() -> bool:
    """Primary holder: ram_events --forever. Fallback: utilization when events is down."""
    env = os.environ.get("DGX_RAM_ANON_HOLDER", "").strip().lower()
    if env in ("1", "true", "yes"):
        return True
    cmd = ""
    try:
        with open(f"/proc/{os.getpid()}/cmdline", "rb") as fh:
            cmd = fh.read().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        cmd = " ".join(sys.argv)
    if "dgx_ram_events.py" in cmd and "--forever" in cmd:
        return True
    if "dgx_utilization.py" in cmd and "--forever" in cmd:
        # Avoid dual holders thrashing swap (needle: events 24GB + util 12GB).
        return not _ram_events_holder_alive()
    return False

# Lower tier = evicted first. 10 = protected core daemons.
TIER_SELF_CHECK = 1
TIER_ADAPT_ORPHAN = 1
TIER_UNITTEST = 2
TIER_LINT_PROBE = 2
TIER_AGENT_EXCESS = 3
TIER_BALLAST = 4
TIER_DEPS_MIRROR = 5
TIER_WORKTREE_SHM = 6
TIER_REPO_MIRROR = 7
TIER_HUB_AGENT = 8
TIER_GPU_COMPUTE = 9
TIER_CORE_DAEMON = 10

CORE_DAEMON_MARKERS = (
    "peer_loop.py --forever",
    "automation_improve.py --forever",
    "automation_comms_improve.py --forever",
    "factory_sprint.py --forever",
    "knowledge_index.py --forever",
    "dgx_utilization.py --forever",
    "dgx_ram_accel.py --forever",
    "dgx_gpu_compute.py --forever",
    "dgx_local_ram_guard.py",
    "dashboard/server.py",
)

LOW_ORPHAN_MARKERS = (
    "automation_adapt.py",
    "peer_orchestrate.py --self-check",
    "factory_fanout.py",
)

LINT_MARKERS = (" -m ruff", " -m mypy", " -m pytest", " -m py_compile")

_AGENT_SKIP_MARKERS = ("cursor-agent", "worker-server")


def _is_real_python_worker(cmd: str) -> bool:
    if not cmd or any(m in cmd for m in _AGENT_SKIP_MARKERS):
        return False
    return "python" in cmd.lower() or "Python" in cmd


def _is_real_self_check(cmd: str) -> bool:
    return _is_real_python_worker(cmd) and "peer_orchestrate.py" in cmd and "--self-check" in cmd


def _self_check_cap() -> int:
    try:
        return max(1, int(auto.CFG.get("dgx_self_check_cap") or 2))
    except (TypeError, ValueError):
        return 2


def _unittest_cap() -> int:
    try:
        return max(1, int(auto.CFG.get("dgx_unittest_cap") or 12))
    except (TypeError, ValueError):
        return 12


def trim_worker_storms(
    *,
    log_fn: Callable[[str], None] = print,
    self_check_cap: int | None = None,
    unittest_cap: int | None = None,
    procs: list[tuple[int, str]] | None = None,
) -> dict[str, int]:
    """Kill real self-check/unittest workers above cap — ignore cursor-agent prompt matches."""
    if procs is None:
        procs = _list_processes()
    self_check_pids: list[int] = []
    unittest_pids: list[int] = []
    for pid, cmd in procs:
        if _is_real_self_check(cmd):
            self_check_pids.append(pid)
        elif budget.is_unittest_worker_cmdline(cmd):
            unittest_pids.append(pid)
    sc_cap = _self_check_cap() if self_check_cap is None else max(0, self_check_cap)
    ut_cap = _unittest_cap() if unittest_cap is None else max(0, unittest_cap)
    killed_sc = 0
    killed_ut = 0
    if len(self_check_pids) > sc_cap:
        killed_sc = _kill_pids(sorted(self_check_pids)[sc_cap:])
        if killed_sc:
            log_fn(f"priority storms: trimmed {killed_sc} self-check worker(s) (cap {sc_cap})")
    if len(unittest_pids) > ut_cap:
        killed_ut = _kill_pids(sorted(unittest_pids)[ut_cap:])
        if killed_ut:
            log_fn(f"priority storms: trimmed {killed_ut} unittest worker(s) (cap {ut_cap})")
    return {"self_check_killed": killed_sc, "unittest_killed": killed_ut}


def _cfg() -> dict[str, Any]:
    raw = auto.CFG.get("ram_priority")
    return raw if isinstance(raw, dict) else {}


def enabled() -> bool:
    if _cfg().get("enabled") is False:
        return False
    if _cfg().get("require_stable_mode") is False:
        return True
    return eff.stable_mode()


def target_used_gb() -> float:
    """Fill target from ram_priority — never use ram_max_used_gb as the aim point.

    Needle: targeting the hard cap (110) overshoots events.trim_gb (100) → perpetual trim beep.
    """
    try:
        target = float(_cfg().get("target_used_gb") or 100)
    except (TypeError, ValueError):
        target = 100.0
    cap = budget.ram_max_used_gb()
    if cap is not None:
        return min(target, float(cap))
    return target


def hold_band_gb() -> float:
    try:
        return max(1.0, float(_cfg().get("hold_band_gb") or 3))
    except (TypeError, ValueError):
        return 3.0


def fill_chunk_gb() -> float:
    """Prefer 2GB steps when far below target — 1GB crawl never closes a 20GB gap.

    Counter-needle: swap 100% full + 2GB×16 steps/tick OOM-kills ram_events
    (43–81GB peak → SIGKILL → footprint collapses to ~50–70GB forever).
    """
    try:
        configured = float(_cfg().get("fill_chunk_gb") or 0)
    except (TypeError, ValueError):
        configured = 0.0
    swap_dead = _swap_free_gb() < 0.5
    if configured > 0:
        chunk = max(0.25, configured)
    else:
        gap = target_used_gb() - budget.footprint_gb()
        if gap > 20:
            chunk = 2.0
        elif gap > 8:
            chunk = 1.5
        else:
            chunk = 1.0
    # Exhausted swap: crumb climb only — large steps OOM the forever holder.
    if swap_dead:
        return min(chunk, 0.5)
    return chunk


def evict_until_used_gb() -> float:
    return target_used_gb()


def fill_until_used_gb() -> float:
    return max(0.0, target_used_gb() - hold_band_gb())


def fill_steps_for_gap() -> int:
    """How many incremental fill steps to close the gap toward hold band."""
    gap = target_used_gb() - budget.footprint_gb()
    if gap <= hold_band_gb():
        return 1
    # Swap exhausted: never spray 16–64 allocates in one tick (OOM thrash).
    if _swap_free_gb() < 0.5:
        return min(4, max(1, int(gap / max(0.5, fill_chunk_gb()))))
    # Large hold gaps need many ballast/anon steps per tick (1GB chunks).
    if gap > 40:
        return min(64, max(24, int(gap / max(0.5, fill_chunk_gb()))))
    if gap > 15:
        return min(48, max(16, int(gap / max(0.5, fill_chunk_gb()))))
    return min(24, max(8, int(gap / max(0.5, fill_chunk_gb()))))


def _shm_near_full(*, min_free_mb: int = 512) -> bool:
    try:
        usage = shutil.disk_usage("/dev/shm")
        return usage.free < min_free_mb * 1024 * 1024
    except OSError:
        return False


def _trim_one_ballast_chunk(*, log_fn: Callable[[str], None] = print) -> int:
    """Tiered replace — drop one ballast chunk to free tmpfs for productive mirrors."""
    if not BALLAST_ROOT.is_dir():
        return 0
    files = sorted(BALLAST_ROOT.glob("ballast_*.bin"), reverse=True)
    for path in files:
        try:
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            log_fn(f"priority replace: freed {size // (1024 * 1024)}MB ballast for productive fill")
            return size
        except OSError:
            continue
    return 0


def _grow_anon_footprint(*, chunk_mb: int | None = None, log_fn: Callable[[str], None] = print) -> int:
    """Grow AnonPages when tmpfs ballast is capped — held in ram_events forever.

    Primary holder: ``dgx_ram_events.py --forever`` (DGX_RAM_ANON_HOLDER=1).
    Fallback: ``dgx_utilization.py --forever`` only when events holder is absent.
    One-shot CLI ``--govern`` must not allocate ephemeral anon (frees on exit).
    """
    global _ANON_RESERVE
    if not _is_anon_holder():
        log_fn("priority anon: skip — not forever holder (use ram_events / utilization)")
        return 0
    stats = budget.mem_stats()
    if anon_fill_blocked(stats=stats):
        log_fn(
            f"priority anon: skip — fill pressure "
            f"(avail {stats['avail_gb']:.1f}GB swap_free {_swap_free_gb():.1f}GB)"
        )
        return 0
    if chunk_mb is None:
        chunk_mb = max(256, int(fill_chunk_gb() * 1024))
    # Under tight MemAvailable, use small crumbs — large anon steps OOM-kill
    # the forever holder (restart counter climbs, footprint oscillates 60↔97).
    if _swap_free_gb() < 0.5:
        chunk_mb = min(chunk_mb, 512)
    if stats["avail_gb"] < 10.0:
        chunk_mb = min(chunk_mb, 256)
    elif stats["avail_gb"] < 14.0:
        chunk_mb = min(chunk_mb, 512)
    elif stats["avail_gb"] < 18.0:
        chunk_mb = min(chunk_mb, 1024)
    # Cap single step so we never eat the last fill-floor band in one allocate.
    # Use adaptive fill floor (not cfg critical=10) — last-mile avail ~5–7GB must
    # still grow anon toward ~100GB when /dev/shm is ENOSPC. Prefer 256MB crumbs
    # over stalling when headroom is thin.
    gap = target_used_gb() - budget.footprint_gb()
    floor = fill_avail_floor_gb(gap=gap)
    headroom_mb = max(0.0, (stats["avail_gb"] - floor) * 1024)
    max_mb = int(max(256.0, headroom_mb * 0.7)) if headroom_mb >= 256 else int(headroom_mb)
    if gap <= 8.0 and stats["avail_gb"] >= floor and max_mb < 256:
        max_mb = 256 if stats["avail_gb"] - floor >= 0.2 else max_mb
    chunk_mb = min(chunk_mb, max_mb) if max_mb > 0 else 0
    if chunk_mb < 128:
        return 0
    chunk = chunk_mb * 1024 * 1024
    try:
        buf = bytearray(chunk)
        for i in range(0, chunk, 4096):
            buf[i] = 1
        _ANON_RESERVE.append(buf)
        log_fn(f"priority anon: +{chunk_mb}MB resident ({len(_ANON_RESERVE)} chunks)")
        return chunk
    except MemoryError:
        log_fn("priority anon: stop — MemoryError")
        return 0


def keep_mirror_names() -> set[str]:
    raw = _cfg().get("keep_mirrors")
    if isinstance(raw, list) and raw:
        return {str(x) for x in raw}
    accel = auto.CFG.get("ram_accel")
    if isinstance(accel, dict):
        names = accel.get("mirror_names")
        if isinstance(names, list):
            return {str(x) for x in names}
    return {"Automation", "Automation Hub", "CPT", "CaaS", "ram", "Doc2Api"}


def max_worktree_shm_dirs() -> int:
    try:
        return max(8, int(_cfg().get("max_worktree_shm_dirs") or 48))
    except (TypeError, ValueError):
        return 48


@dataclass(frozen=True)
class EvictionStep:
    tier: int
    name: str
    freed_estimate: int
    detail: str


def _list_processes() -> list[tuple[int, str]]:
    return budget.iter_proc_cmdlines()


def _kill_pids(pids: list[int]) -> int:
    killed = 0
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
            killed += 1
        except OSError:
            pass
    return killed


def _evict_tier_1(*, log_fn: Callable[[str], None]) -> EvictionStep:
    procs = _list_processes()
    storms = trim_worker_storms(log_fn=log_fn, procs=procs)
    killed = storms["self_check_killed"]
    orphans: list[int] = []
    for pid, cmd in procs:
        if not _is_real_python_worker(cmd):
            continue
        if any(m in cmd for m in LOW_ORPHAN_MARKERS):
            if not any(c in cmd for c in CORE_DAEMON_MARKERS):
                orphans.append(pid)
    killed += _kill_pids(orphans)
    if killed:
        log_fn(f"priority T1: evicted {killed} self-check/adapt orphan(s)")
    return EvictionStep(TIER_SELF_CHECK, "self_check_adapt", killed, f"killed={killed}")


def _evict_tier_2(*, log_fn: Callable[[str], None]) -> EvictionStep:
    procs = _list_processes()
    storms = trim_worker_storms(log_fn=log_fn, procs=procs)
    killed = storms["unittest_killed"]
    lint_pids: list[int] = []
    for pid, cmd in procs:
        if _is_real_python_worker(cmd) and any(m in cmd for m in LINT_MARKERS):
            lint_pids.append(pid)
    killed += _kill_pids(lint_pids)
    if killed:
        log_fn(f"priority T2: evicted {killed} unittest/lint worker(s)")
    return EvictionStep(TIER_UNITTEST, "unittest_lint", killed, f"killed={killed}")


def _evict_tier_3(*, log_fn: Callable[[str], None]) -> EvictionStep:
    """Trim only agents *above* ``max_parallel_agent_procs``.

    Needle: OVERSEER_SATURATE_KEEP_FLOOR_2026_09_07 — footprint>target used to
    SIGKILL the first 2 PIDs even when under the free-desktop floor (cap 8).
    That slaughtered CLEAN niches for ballast while ``/dev/shm`` held 56GB pins
    and blocked ≥6 productive cycles/h. Excess-only trim; ballast is T4.
    """
    import peer_parallel_dispatch as ppd

    fp = budget.footprint_gb()
    target = target_used_gb()
    killed = int(ppd.trim_agents_over_cap(log_fn=log_fn) or 0)
    if killed:
        if fp > target:
            log_fn(
                f"priority T3: trimmed {killed} excess agent(s) "
                f"(footprint {fp:.1f}GB > {target}GB; floor kept)"
            )
        else:
            log_fn(f"priority T3: trimmed {killed} excess agent(s)")
    elif fp > target:
        log_fn(
            f"priority T3: skip under-floor agent kill "
            f"(footprint {fp:.1f}GB > {target}GB; peel ballast T4)"
        )
    return EvictionStep(TIER_AGENT_EXCESS, "agent_excess", killed, f"killed={killed}")


def _evict_tier_4(*, log_fn: Callable[[str], None]) -> EvictionStep:
    # Never mass-purge ballast while under the ~100GB footprint target —
    # ram_accel/fill maintain was oscillating 50↔85GB (needle: T4 purge fight).
    if budget.footprint_gb() < fill_until_used_gb():
        return EvictionStep(TIER_BALLAST, "ballast", 0, "skip_under_target")
    freed = fill.purge_ballast(log_fn=log_fn)
    if freed:
        log_fn(f"priority T4: purged {freed // (1024 * 1024)}MB ballast")
    return EvictionStep(TIER_BALLAST, "ballast", freed, f"bytes={freed}")


def _evict_tier_5(*, log_fn: Callable[[str], None]) -> EvictionStep:
    deps_root = Path("/dev/shm/automation-deps")
    freed = 0
    if deps_root.is_dir():
        for child in sorted(deps_root.iterdir()):
            if not child.is_dir():
                continue
            try:
                size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
            except OSError:
                size = 0
            subprocess.run(["rm", "-rf", str(child)], check=False)
            freed += size
            log_fn(f"priority T5: dropped deps mirror {child.name}")
            break
    return EvictionStep(TIER_DEPS_MIRROR, "deps_mirror", freed, f"bytes={freed}")


def _evict_tier_6(*, log_fn: Callable[[str], None]) -> EvictionStep:
    root = Path("/dev/shm/automation-worktrees")
    freed = 0
    if not root.is_dir():
        return EvictionStep(TIER_WORKTREE_SHM, "worktree_shm", 0, "none")
    dirs = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime)
    keep = max_worktree_shm_dirs()
    if len(dirs) <= keep:
        return EvictionStep(TIER_WORKTREE_SHM, "worktree_shm", 0, "at_cap")
    drop = dirs[: max(1, len(dirs) - keep)]
    for path in drop:
        try:
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        except OSError:
            size = 0
        subprocess.run(["rm", "-rf", str(path)], check=False)
        freed += size
        log_fn(f"priority T6: dropped worktree shm {path.name}")
    return EvictionStep(TIER_WORKTREE_SHM, "worktree_shm", freed, f"bytes={freed}")


def _evict_tier_7(*, log_fn: Callable[[str], None]) -> EvictionStep:
    mirror_root = Path("/dev/shm/automation-mirror")
    keep = keep_mirror_names()
    freed = 0
    if not mirror_root.is_dir():
        return EvictionStep(TIER_REPO_MIRROR, "repo_mirror", 0, "none")
    for child in sorted(mirror_root.iterdir(), key=lambda p: p.stat().st_mtime):
        if not child.is_dir():
            continue
        name = child.name.replace("_", " ")
        if any(k.replace(" ", "_") in child.name or k in name for k in keep):
            continue
        try:
            size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
        except OSError:
            size = 0
        subprocess.run(["rm", "-rf", str(child)], check=False)
        freed += size
        log_fn(f"priority T7: dropped repo mirror {child.name}")
        break
    return EvictionStep(TIER_REPO_MIRROR, "repo_mirror", freed, f"bytes={freed}")


EVICTORS: list[tuple[int, str, Callable[..., EvictionStep]]] = [
    (TIER_SELF_CHECK, "self_check_adapt", _evict_tier_1),
    (TIER_UNITTEST, "unittest_lint", _evict_tier_2),
    (TIER_AGENT_EXCESS, "agent_excess", _evict_tier_3),
    (TIER_BALLAST, "ballast", _evict_tier_4),
    (TIER_DEPS_MIRROR, "deps_mirror", _evict_tier_5),
    (TIER_WORKTREE_SHM, "worktree_shm", _evict_tier_6),
    (TIER_REPO_MIRROR, "repo_mirror", _evict_tier_7),
]


def needs_eviction() -> bool:
    fp = budget.footprint_gb()
    if fp > target_used_gb():
        return True
    stats = budget.mem_stats()
    if stats["total_gb"] <= 0:
        return False
    if fp >= target_used_gb() - hold_band_gb():
        if stats["avail_gb"] < budget.ram_critical_avail_floor_gb():
            return True
        return budget.pressure_level(
            avail_gb=stats["avail_gb"],
            total_gb=stats["total_gb"],
            stats=stats,
        ) == "critical"
    return False


def needs_fill() -> bool:
    fp = budget.footprint_gb()
    if fp >= fill_until_used_gb():
        return False
    stats = budget.mem_stats()
    if stats["total_gb"] <= 0:
        return False
    gap = target_used_gb() - fp
    # Large under-target gaps: fill whenever we have a few GB free — do not wait
    # for full fill_headroom (needle: trim@20GB avail ↔ fill thrash forever ~60GB).
    # Ignore pressure-blocked here when avail clears the adaptive crumb floor —
    # otherwise needs_fill stays False at fp~87 with avail 6.5 while CUDA cache
    # holds MemAvailable under the old 7.5GB gate.
    floor = fill_avail_floor_gb(gap=gap)
    if gap > hold_band_gb() * 2:
        # Large under-target gaps: fill whenever avail clears the adaptive floor
        # (often ~3.5–5GB with swap dead + CUDA resident). Old min(8.0, …) gate
        # froze climb at ~78GB while 20GB+ gap remained (needle 2026-09-06).
        # Unified GB10 teacher reserved parks avail ~3.5–4.0 — allow crumbs from 3.25.
        min_headroom = max(3.0, min(floor, 4.0))
        if stats["avail_gb"] >= min_headroom:
            return True
        return False
    if _fill_pressure_blocked(stats=stats):
        return stats["avail_gb"] >= floor
    # Last-mile needle: fill_pressure_ok wants ~18GB headroom and froze footprint
    # ~94–97GB forever while /dev/shm was full and avail sat ~7–9GB. Use the
    # adaptive fill floor so anon holder can finish the climb to ~100GB.
    return stats["avail_gb"] >= floor


def release_anon_pressure(*, log_fn: Callable[[str], None] = print, keep_chunks: int = 4) -> int:
    """Drop anon holder chunks when MemAvailable is critical — prevent OOM-kill.

    Tiered replace: shrink low-importance anon ballast before the kernel SIGKILLs
    the forever holder (needle: 81GB peak → oom-kill → fp collapses to ~50GB).

    Counter-needle: swap 100% full alone must NOT dump anon — free_headroom runs
    every hold tick and was releasing to keep_chunks=4 whenever SwapFree≈0 even
    with avail 20–40GB (fp climbed to ~90GB then collapsed to ~65GB forever).
    Only release when MemAvailable is actually under the critical floor.

    Counter-needle-2: under-target + brief CUDA spike (avail 2GB for seconds)
    must not dump the whole climb — release at most 2 chunks per call so
    the forever holder can re-absorb once MemAvailable recovers.
    """
    global _ANON_RESERVE
    if not _ANON_RESERVE:
        return 0
    if not _is_anon_holder():
        return 0
    stats = budget.mem_stats()
    crit = float(budget.ram_critical_avail_floor_gb())
    under_target = budget.footprint_gb() < fill_until_used_gb()
    # Under-target: only peel on true OOM path. crit*0.55 with crit=5.5 still
    # released at avail~3GB and undid 90→100 climbs (needle 2026-09-06).
    # Hard floor 2.0 — brief CUDA dips to 4–6GB must not dump anon crumbs.
    hard_oom = 2.0 if under_target else crit
    if stats["avail_gb"] >= hard_oom:
        return 0
    # Under ~100GB: only peel 1 crumb — mass release undoes hours of climb.
    max_release = 1 if under_target else max(1, len(_ANON_RESERVE) - max(0, keep_chunks))
    floor_keep = max(0, keep_chunks) if not under_target else max(keep_chunks, len(_ANON_RESERVE) - max_release)
    freed = 0
    released_n = 0
    while (
        len(_ANON_RESERVE) > floor_keep
        and released_n < max_release
        and budget.mem_stats()["avail_gb"] < hard_oom
    ):
        buf = _ANON_RESERVE.pop()
        freed += len(buf)
        del buf
        released_n += 1
    if freed:
        log_fn(
            f"priority anon: released {freed // (1024 * 1024)}MB "
            f"(keep {len(_ANON_RESERVE)} chunks, avail {budget.mem_stats()['avail_gb']:.1f}GB)"
        )
    return freed


def _gpu_compute_forever_running() -> bool:
    """True when productive CUDA embed daemon is alive (needs MemAvailable headroom)."""
    try:
        proc = subprocess.run(
            ["pgrep", "-f", r"dgx_gpu_compute\.py --forever"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
        return proc.returncode == 0 and bool(proc.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def free_headroom_for_fill(*, log_fn: Callable[[str], None] = print) -> dict[str, int]:
    """Tiered replace — evict low tiers when footprint is below target but avail is tight.

    Also runs near target when MemAvailable is critical — INFRA agent storms
    leave fp≈100GB with avail≈8–10GB (pressure) and stall durable ballast.
    """
    stats = budget.mem_stats()
    gap = target_used_gb() - budget.footprint_gb()
    crit = float(budget.ram_critical_avail_floor_gb())
    avail_critical = stats["avail_gb"] < crit
    # Near-target still trim when avail is critical (don't wait for a gap).
    # GPU teacher embeds need ≥8GB MemAvailable — below that forever worker
    # enters folio_wait (needle: 9.6/s embeds + permanent emergency beep).
    gpu_floor = max(crit, 8.0)
    try:
        if _gpu_compute_forever_running():
            avail_critical = stats["avail_gb"] < gpu_floor or avail_critical
    except Exception:  # noqa: BLE001
        if stats["avail_gb"] < gpu_floor:
            avail_critical = True
    if gap <= hold_band_gb() and not avail_critical:
        return {"self_check_killed": 0, "unittest_killed": 0, "agents_killed": 0}
    # Under-target: prefer ballast trim over anon release — free_headroom was
    # peeling anon every tick at avail 4–6GB and freezing footprint ~87–91GB.
    # Only release anon on true OOM (<2GB); otherwise tiered-replace shm ballast.
    # Counter-needle: under-target + shm room must NOT trim ballast we are about
    # to re-pin (grow→trim→grow thrash froze footprint ~78GB with 20GB+ gap).
    anon_freed = 0
    if stats["avail_gb"] < 2.0:
        anon_freed = release_anon_pressure(log_fn=log_fn)
    elif (
        gap > hold_band_gb()
        and avail_critical
        and _shm_near_full(min_free_mb=1024)
    ):
        # Only trim when tmpfs is actually full AND avail is critical — then
        # anon holder can absorb. Never trim ballast just because avail is tight
        # while /dev/shm still has room (that undoes fill_with_replace).
        for _ in range(2):
            if budget.mem_stats()["avail_gb"] >= max(crit, fill_avail_floor_gb(gap=gap)):
                break
            if _trim_one_ballast_chunk(log_fn=log_fn) <= 0:
                break
    # Large gaps / tight avail: trim agent storms — INFRA agents free tens of GB
    # of AnonPages that must become durable ballast, not respawn churn.
    min_headroom = max(4.0, eff.fill_headroom_gb() * 0.4)
    force_trim = gap > 15.0 or stats["avail_gb"] < min_headroom or avail_critical
    if not force_trim:
        return {
            "self_check_killed": 0,
            "unittest_killed": 0,
            "agents_killed": 0,
            "anon_released_mb": anon_freed // (1024 * 1024),
        }
    report = trim_worker_storms(log_fn=log_fn, self_check_cap=0, unittest_cap=1)
    agents_killed = 0
    # Under-target + tight avail: trim only agents *above* the free-desktop floor.
    # Needle: OVERSEER_SATURATE_KEEP_FLOOR_2026_09_07 — keep=2/4 slaughtered the
    # factory cap-8 pool for ballast headroom (56GB /dev/shm pins) and held
    # productive cycles/h at ~4. Prefer ballast peel; never go below procs cap.
    try:
        import peer_parallel_dispatch as ppd

        procs = sorted(ppd.find_agent_procs(), key=lambda p: p.pid)
        try:
            factory_floor = max(1, int(ppd.max_parallel_agent_procs()))
        except (TypeError, ValueError):
            factory_floor = 8
        # Soft keep above floor when not critical — still never below factory floor.
        if avail_critical or gap > 25:
            keep = factory_floor
        elif stats["avail_gb"] < budget.ram_critical_avail_floor_gb() or gap > 15:
            keep = max(factory_floor, 4)
        else:
            keep = max(factory_floor, 12)
        for proc in procs[keep:]:
            if proc.pid <= 0:
                continue
            try:
                os.kill(proc.pid, signal.SIGKILL)
                agents_killed += 1
            except OSError:
                pass
        if agents_killed:
            log_fn(
                f"priority fill: trimmed {agents_killed} agent(s) for headroom "
                f"(keep {keep}, floor {factory_floor})"
            )
    except ImportError:
        pass
    # Near/over target + critical avail: drop one ballast chunk for headroom.
    # Under-target + shm-full + avail under fill floor: tiered replace — peel
    # 1–2 ballast GB so MemAvailable clears the crumb floor, then anon re-pins
    # toward 100GB (needle: 59GB ballast @99% shm + avail 6.3 froze fp~88GB).
    ballast_trimmed = 0
    if avail_critical and gap <= hold_band_gb():
        freed = _trim_one_ballast_chunk(log_fn=log_fn)
        if freed:
            ballast_trimmed = freed
    elif gap > hold_band_gb() and _shm_near_full(min_free_mb=1024):
        floor = fill_avail_floor_gb(gap=gap)
        if stats["avail_gb"] < floor:
            for _ in range(2):
                if budget.mem_stats()["avail_gb"] >= floor:
                    break
                freed = _trim_one_ballast_chunk(log_fn=log_fn)
                if not freed:
                    break
                ballast_trimmed += freed
    if ballast_trimmed:
        report["ballast_trimmed_mb"] = ballast_trimmed // (1024 * 1024)
    report["agents_killed"] = agents_killed
    report["anon_released_mb"] = anon_freed // (1024 * 1024)
    return report


def ensure_headroom(*, log_fn: Callable[[str], None]) -> bool:
    """Evict lowest tier before high-tier allocate — replace, don't spike."""
    fp = budget.footprint_gb()
    target = target_used_gb()
    chunk = fill_chunk_gb()
    if fp + chunk <= target + 0.5:
        return True
    for _tier, _name, fn in EVICTORS:
        step = fn(log_fn=log_fn)
        if step.freed_estimate > 0:
            log_fn(f"priority replace: freed {step.name} before fill")
            return budget.footprint_gb() <= target + chunk
    return budget.footprint_gb() <= target


def evict_to_target(*, log_fn: Callable[[str], None] = print) -> list[EvictionStep]:
    """Evict low tiers until footprint ≤ target — hold band, no crash to empty."""
    steps: list[EvictionStep] = []
    target = target_used_gb()
    for _ in range(len(EVICTORS) * 3):
        if budget.footprint_gb() <= target:
            break
        evicted_any = False
        for _tier, _name, fn in EVICTORS:
            if budget.footprint_gb() <= target:
                break
            step = fn(log_fn=log_fn)
            steps.append(step)
            if step.freed_estimate > 0:
                evicted_any = True
                time.sleep(0.4)
                break
        if not evicted_any:
            break
    return steps


def _grow_ballast_toward_target(*, log_fn: Callable[[str], None] = print) -> int:
    """Pin ballast past fill.target_reserve when under ~100GB footprint.

    Needle: grow_ballast stops at avail<=reserve+2 (often 19–21GB) while /dev/shm
    has tens of GB free — permanent ~80GB hole and INFRA hold beep.
    Never grow into swap thrash (avail/swap floors from ram_priority config).
    """
    gap = target_used_gb() - budget.footprint_gb()
    if gap <= hold_band_gb():
        return 0
    stats = budget.mem_stats()
    avail_floor = fill_avail_floor_gb(gap=gap)
    # Ballast is tmpfs — allow when avail is healthy even if swap is full.
    if stats["avail_gb"] < avail_floor:
        return 0
    if anon_fill_blocked(stats=stats) and stats["avail_gb"] < max(avail_floor, 12.0):
        return 0
    if stats["avail_gb"] < avail_floor:
        return 0
    try:
        if shutil.disk_usage("/dev/shm").free < 1 * 1024 * 1024 * 1024:
            return 0
    except OSError:
        return 0
    # Stop before the last chunk would push avail under the floor.
    chunk_mb = max(1024, int(fill_chunk_gb() * 1024))
    max_mb = int(min(chunk_mb, max(1024.0, gap * 1024 * 0.5)))
    if stats["avail_gb"] - (max_mb / 1024.0) < avail_floor:
        max_mb = int(max(512, (stats["avail_gb"] - avail_floor) * 1024))
        if max_mb < 512:
            return 0
    path = BALLAST_ROOT / f"ballast_{int(time.time() * 1000)}_{os.getpid()}.bin"
    try:
        # Non-zero pages — pure zeros can hollow on tmpfs (du≠allocated).
        block = 64 * 1024 * 1024
        page = b"\xff" * block
        nbytes = max_mb * 1024 * 1024
        with open(path, "wb") as fh:
            written = 0
            while written < nbytes:
                step = min(block, nbytes - written)
                fh.write(page if step == block else page[:step])
                written += step
            fh.flush()
            os.fsync(fh.fileno())
        log_fn(
            f"priority ballast: +{max_mb}MB pinned "
            f"(gap {gap:.1f}GB avail {stats['avail_gb']:.1f}GB)"
        )
        return nbytes
    except OSError as exc:
        path.unlink(missing_ok=True)
        log_fn(f"priority ballast: stop — {exc}")
        return 0


def fill_with_replace(
    *,
    log_fn: Callable[[str], None] = print,
    force: bool = False,
) -> dict[str, Any]:
    """One incremental high-tier pin — evict lower tier first if at cap.

    ``force=True``: under-target hold path may retry one step after headroom
    trim even when ``needs_fill`` is False due to a lagging pressure gate.
    """
    fp = budget.footprint_gb()
    under = fp < fill_until_used_gb()
    if not needs_fill() and not (force and under and not _fill_pressure_blocked()):
        return {
            "filled": False,
            "footprint_gb": fp,
            "target_used_gb": target_used_gb(),
            "productive_shm_gb": fill.productive_shm_gb(),
        }
    if not ensure_headroom(log_fn=log_fn):
        return {
            "filled": False,
            "reason": "headroom",
            "footprint_gb": budget.footprint_gb(),
            "target_used_gb": target_used_gb(),
        }
    gap = target_used_gb() - fp
    step: dict[str, Any] = {"phase": "none", "ok": False}
    filled = False
    # Large gap: direct ballast pin (bypasses inflate target_reserve stall).
    if gap > hold_band_gb():
        ballast_added = 0
        attempts = min(16, max(4, int(gap / fill_chunk_gb()) + 2))
        for i in range(attempts):
            if budget.footprint_gb() >= fill_until_used_gb():
                break
            added = _grow_ballast_toward_target(log_fn=log_fn)
            if added <= 0:
                if i == 0 and budget.mem_stats()["avail_gb"] < 10.0:
                    free_headroom_for_fill(log_fn=log_fn)
                    time.sleep(0.3)
                    continue
                break
            ballast_added += added
            filled = True
        if ballast_added > 0:
            step = {
                "phase": "ballast",
                "ok": True,
                "detail": f"+{ballast_added // (1024 * 1024)}MB pinned",
            }
    # tmpfs capped (~50% RAM): grow AnonPages in ram_events forever holder.
    # Prefer anon when shm is tight — never because avail is already critical
    # (that path dual-filled holders into swap thrash).
    # Last-mile needle: gap 3–6GB with /dev/shm full left footprint stuck ~94–97GB
    # because need_anon required gap > 2*hold_band (6GB).
    stats_now = budget.mem_stats()
    shm_tight = _shm_near_full(min_free_mb=1536)
    need_anon = (
        under
        and not anon_fill_blocked(stats=stats_now)
        and (
            (gap > hold_band_gb() * 2 and (not filled or shm_tight))
            or (shm_tight and gap > 0.5 and not filled)
            or (shm_tight and gap > hold_band_gb() * 0.5)
        )
    )
    if need_anon:
        added = _grow_anon_footprint(log_fn=log_fn)
        if added > 0:
            step = {"phase": "anon", "ok": True, "detail": f"+{added // (1024 * 1024)}MB resident"}
            filled = True
    # Ballast/anon already closed this tick — do NOT call fill_one_step (pip/mirror
    # can race ram_accel trim_ballast and undo a 90GB climb back to ~60GB).
    if filled:
        return {
            "filled": True,
            "step": step,
            "footprint_gb": budget.footprint_gb(),
            "target_used_gb": target_used_gb(),
            "productive_shm_gb": fill.productive_shm_gb(),
        }
    # Under footprint target, ballast IS the productive pin — do not trim it to
    # make room for fill_one_step (mirror/pip) that immediately loses the climb.
    if _shm_near_full() and budget.footprint_gb() >= fill_until_used_gb():
        # Free one ballast file so a productive pin can land — never mass-trim.
        _trim_one_ballast_chunk(log_fn=log_fn)
    # Skip fill.fill_one_step while under footprint target — maintain/trim_ballast
    # inside that path undoes priority pins when avail < old 20GB floor.
    if budget.footprint_gb() < fill_until_used_gb():
        added = _grow_anon_footprint(log_fn=log_fn)
        if added > 0:
            return {
                "filled": True,
                "step": {"phase": "anon", "ok": True, "detail": f"+{added // (1024 * 1024)}MB resident"},
                "footprint_gb": budget.footprint_gb(),
                "target_used_gb": target_used_gb(),
                "productive_shm_gb": fill.productive_shm_gb(),
            }
        return {
            "filled": filled,
            "step": step,
            "footprint_gb": budget.footprint_gb(),
            "target_used_gb": target_used_gb(),
            "productive_shm_gb": fill.productive_shm_gb(),
        }
    step = fill.fill_one_step(log_fn=log_fn)
    filled = bool(step.get("ok"))
    if not filled and (fill.ballast_enabled() or gap > hold_band_gb()):
        added = fill.grow_ballast(log_fn=log_fn, force=True)
        if added > 0:
            step = {"phase": "ballast", "ok": True, "detail": f"+{added // (1024 * 1024)}MB pinned"}
            filled = True
    if not filled and budget.footprint_gb() < fill_until_used_gb():
        added = _grow_anon_footprint(log_fn=log_fn)
        if added > 0:
            step = {"phase": "anon", "ok": True, "detail": f"+{added // (1024 * 1024)}MB resident"}
            filled = True
    return {
        "filled": filled,
        "step": step,
        "footprint_gb": budget.footprint_gb(),
        "target_used_gb": target_used_gb(),
        "productive_shm_gb": fill.productive_shm_gb(),
    }


def govern(*, log_fn: Callable[[str], None] = print) -> dict[str, Any]:
    """One governor tick — evict low tiers over cap, else one high-tier pin toward ~100GB."""
    storms = trim_worker_storms(log_fn=log_fn)
    before = budget.mem_stats()
    report: dict[str, Any] = {
        "worker_storms": storms,
        "before": before,
        "target_used_gb": target_used_gb(),
        "hold_band_gb": hold_band_gb(),
        "fill_until_gb": fill_until_used_gb(),
        "footprint_gb_before": before["footprint_gb"],
    }
    if needs_eviction():
        report["evictions"] = [
            {"tier": s.tier, "name": s.name, "detail": s.detail} for s in evict_to_target(log_fn=log_fn)
        ]
        report["action"] = "evict"
    elif needs_fill():
        free_headroom_for_fill(log_fn=log_fn)
        fills: list[dict[str, Any]] = []
        for _ in range(fill_steps_for_gap()):
            if not needs_fill():
                break
            one = fill_with_replace(log_fn=log_fn)
            fills.append(one)
            if not one.get("filled"):
                break
        report["fill"] = fills[-1] if fills else fill_with_replace(log_fn=log_fn)
        report["fill_steps"] = len(fills)
        report["action"] = "fill"
    else:
        report["action"] = "hold"
    after = budget.mem_stats()
    report["after"] = after
    report["footprint_gb"] = after["footprint_gb"]
    report["pressure"] = budget.pressure_level(
        avail_gb=after["avail_gb"],
        total_gb=after["total_gb"],
        stats=after,
    )
    log_fn(
        f"govern {report['action']}: footprint {after['footprint_gb']}/{report['target_used_gb']}GB "
        f"(avail-based {after['used_avail_gb']}GB) productive {fill.productive_shm_gb():.1f}GB "
        f"[{report['pressure']}]"
    )
    return report


def tier_snapshot() -> dict[str, Any]:
    """Inventory for dashboard / debugging."""
    stats = budget.mem_stats()
    procs = _list_processes()
    return {
        "target_used_gb": target_used_gb(),
        "hold_band_gb": hold_band_gb(),
        "footprint_gb": stats["footprint_gb"],
        "used_avail_gb": stats["used_avail_gb"],
        "avail_gb": stats["avail_gb"],
        "productive_shm_gb": round(fill.productive_shm_gb(), 2),
        "agents": eff.agent_count(),
        "self_check_workers": sum(1 for _pid, cmd in procs if _is_real_self_check(cmd)),
        "unittest_workers": sum(1 for _pid, cmd in procs if budget.is_unittest_worker_cmdline(cmd)),
        "needs_eviction": needs_eviction(),
        "needs_fill": needs_fill(),
        "ram_mode": budget.ram_mode(stats=stats),
        "agent_cap": budget.ram_agent_cap(stats=stats),
        "dispatch_allowed": budget.dispatch_allowed(stats=stats),
        "pressure": budget.pressure_level(
            avail_gb=stats["avail_gb"],
            total_gb=stats["total_gb"],
            stats=stats,
        ),
        "tiers": [{"tier": t, "name": n} for t, n, _ in EVICTORS],
    }


def main() -> int:
    import argparse
    import json as json_mod

    parser = argparse.ArgumentParser(description="DGX RAM priority governor")
    parser.add_argument("--govern", action="store_true")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.snapshot:
        payload = tier_snapshot()
        print(json_mod.dumps(payload, indent=2))
        return 0
    if args.govern or not args.snapshot:
        report = govern(log_fn=lambda m: None if args.json else print(m))
        if args.json:
            print(json_mod.dumps(report, indent=2))
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
