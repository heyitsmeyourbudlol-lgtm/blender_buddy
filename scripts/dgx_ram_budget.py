#!/usr/bin/env python3
"""DGX RAM budget — cap resident footprint (AnonPages+Shmem), not volatile page cache."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

# Real python unittest workers only — never match cursor-agent prompts that quote this string.
_UNITTEST_WORKER_RE = re.compile(
    r"(?:^|[\s/])(?:python3?|Python)\s+-m\s+unittest\b",
    re.IGNORECASE,
)
_AGENT_SKIP_RE = re.compile(r"cursor-agent|worker-server", re.IGNORECASE)
# Match shell parents only — not ``/bin/sh -c`` wrappers double-count with python child.
_SHELL_WRAPPER_RE = re.compile(
    r"(?:^|[\s/])(?:ba)?sh(?:\s+\S+)*?\s+-c\b|(?:^|[\s/])(?:ba)?sh\s+-\w*c\b",
    re.IGNORECASE,
)  # OVERSEER_SELF_CHECK_ARGV0_2026_09_03
    # OVERSEER_SELF_CHECK_COMM — land-proof alias (python argv0 only)


SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

MEMINFO = Path("/proc/meminfo")


_DGX_UNITTEST_CAP_CEILING = 24
_DGX_AGENTS_CAP_CEILING = 96


def _dgx_cfg() -> dict[str, Any]:
    """Prefer top-level overlay caps — never prefer stale 96/20 nested landmines.

    Stale ``dgx_host.dgx_unittest_cap=96`` / ``dgx_max_cursor_agents=48`` must not
    beat overlay top-level ``2`` / peers ``8`` (rsync/overlay landmine).
    """
    raw = auto.CFG.get("dgx_host")
    cfg = dict(raw) if isinstance(raw, dict) else {}
    for key in (
        "ram_max_used_gb",
        "ram_hard_max_used_gb",
        "ram_min_avail_gb",
        "ram_critical_avail_gb",
    ):
        if key in auto.CFG and key not in cfg:
            cfg[key] = auto.CFG[key]
    # Prefer top-level overlay caps when stricter than nested.
    top_ut = auto.CFG.get("dgx_unittest_cap")
    if top_ut is not None:
        try:
            nested_ut = cfg.get("dgx_unittest_cap")
            if nested_ut is None or int(nested_ut) > int(top_ut):
                cfg["dgx_unittest_cap"] = int(top_ut)
        except (TypeError, ValueError):
            try:
                cfg["dgx_unittest_cap"] = int(top_ut)
            except (TypeError, ValueError):
                pass
    top_ag = auto.CFG.get("dgx_max_cursor_agents")
    if top_ag is None:
        top_ag = auto.CFG.get("max_parallel_agent_procs")
    if top_ag is not None:
        try:
            nested_ag = cfg.get("dgx_max_cursor_agents")
            if nested_ag is None or int(nested_ag) > int(top_ag):
                cfg["dgx_max_cursor_agents"] = int(top_ag)
        except (TypeError, ValueError):
            try:
                cfg["dgx_max_cursor_agents"] = int(top_ag)
            except (TypeError, ValueError):
                pass
    try:
        peers = int(auto.max_parallel_peers())
        nested_ag = cfg.get("dgx_max_cursor_agents")
        if nested_ag is not None and int(nested_ag) > peers:
            cfg["dgx_max_cursor_agents"] = peers
    except (TypeError, ValueError):
        pass
    return cap_dgx_install_limits(cfg)


def cap_dgx_install_limits(cfg: dict[str, Any]) -> dict[str, Any]:
    """Clamp nested caps so stale high values (e.g. 96/48) can never survive overlay."""
    out = dict(cfg)
    try:
        v = out.get("dgx_unittest_cap")
        if v is not None and int(v) > _DGX_UNITTEST_CAP_CEILING:
            out["dgx_unittest_cap"] = _DGX_UNITTEST_CAP_CEILING
    except (TypeError, ValueError):
        pass
    try:
        v = out.get("dgx_max_cursor_agents")
        if v is not None and int(v) > _DGX_AGENTS_CAP_CEILING:
            out["dgx_max_cursor_agents"] = _DGX_AGENTS_CAP_CEILING
    except (TypeError, ValueError):
        pass
    return out


def _float_cfg(key: str, default: float) -> float:
    try:
        return float(_dgx_cfg().get(key) or default)
    except (TypeError, ValueError):
        return default


def ram_max_used_gb() -> float | None:
    try:
        raw = _dgx_cfg().get("ram_max_used_gb")
        if raw is None:
            return None
        return max(1.0, float(raw))
    except (TypeError, ValueError):
        return None


def knowledge_mamba_budget_gb() -> float:
    """Knowledge-brain RAM carve — separate from agent ``ram_max_used_gb``.

    Delegates to ``knowledge_index_config`` (default 12GB). Needle:
    ``OVERSEER_TOP10_NEXT_T10_10_2026_09_07``.
    """
    try:
        import knowledge_index_config as kcfg

        return float(kcfg.knowledge_mamba_budget_gb())
    except Exception:
        return 12.0


def ram_hard_max_used_gb() -> float | None:
    try:
        raw = _dgx_cfg().get("ram_hard_max_used_gb")
        if raw is not None:
            return max(1.0, float(raw))
    except (TypeError, ValueError):
        pass
    soft = ram_max_used_gb()
    return soft + 2.0 if soft is not None else None


def _meminfo_field_kb(field: str) -> int:
    try:
        for line in MEMINFO.read_text().splitlines():
            if line.startswith(f"{field}:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return 0


def footprint_kb() -> int:
    """Resident footprint — anonymous + shared memory (excludes reclaimable page cache)."""
    return _meminfo_field_kb("AnonPages") + _meminfo_field_kb("Shmem")


def footprint_gb(*, stats: dict[str, float] | None = None) -> float:
    if stats is not None and "footprint_gb" in stats:
        return float(stats["footprint_gb"])
    kb = footprint_kb()
    return round(kb / 1024 / 1024, 1) if kb else 0.0


def ram_min_avail_floor_gb() -> float:
    return _float_cfg("ram_min_avail_gb", 12.0)


def ram_critical_avail_floor_gb() -> float:
    return _float_cfg("ram_critical_avail_gb", 6.0)


def read_meminfo_kb() -> tuple[int, int]:
    total_kb = avail_kb = 0
    try:
        text = MEMINFO.read_text()
    except OSError:
        return 0, 0
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            try:
                total_kb = int(line.split()[1])
            except (ValueError, IndexError):
                pass
        elif line.startswith("MemAvailable:"):
            try:
                avail_kb = int(line.split()[1])
            except (ValueError, IndexError):
                pass
    return total_kb, avail_kb


def mem_stats() -> dict[str, float]:
    total_kb, avail_kb = read_meminfo_kb()
    total_gb = total_kb / 1024 / 1024 if total_kb else 0.0
    avail_gb = avail_kb / 1024 / 1024 if avail_kb else 0.0
    used_avail_gb = max(0.0, total_gb - avail_gb) if total_gb else 0.0
    fp_gb = footprint_gb()
    return {
        "total_kb": float(total_kb),
        "avail_kb": float(avail_kb),
        "total_gb": round(total_gb, 1),
        "avail_gb": round(avail_gb, 1),
        "used_gb": round(fp_gb, 1),
        "used_avail_gb": round(used_avail_gb, 1),
        "footprint_gb": fp_gb,
    }


def effective_ram_thresholds(total_gb: float) -> tuple[float, float]:
    """Return (min_avail_gb, critical_avail_gb) honoring the RAM budget cap."""
    min_avail = ram_min_avail_floor_gb()
    crit_avail = ram_critical_avail_floor_gb()
    cap = ram_max_used_gb()
    if cap is not None and total_gb > 0:
        budget_min = max(0.0, total_gb - cap)
        min_avail = max(min_avail, budget_min)
    crit_avail = max(crit_avail, min(min_avail, max(1.0, min_avail - 6.0)))
    return round(min_avail, 1), round(crit_avail, 1)


def pressure_level(*, avail_gb: float, total_gb: float, stats: dict[str, float] | None = None) -> str:
    min_avail, crit_avail = effective_ram_thresholds(total_gb)
    soft = ram_max_used_gb()
    hard = ram_hard_max_used_gb()
    used_gb = footprint_gb(stats=stats)
    if hard is not None and used_gb >= hard:
        return "critical"
    if avail_gb < crit_avail:
        return "critical"
    if soft is not None and used_gb >= soft:
        return "critical"
    if avail_gb < min_avail:
        return "warn"
    return "ok"


def fill_stop_avail_gb() -> float:
    """Stop cache/page warm when available RAM drops below this."""
    stats = mem_stats()
    min_avail, _ = effective_ram_thresholds(stats["total_gb"])
    fill_cfg = auto.CFG.get("ram_accel")
    reserve = 25.0
    if isinstance(fill_cfg, dict):
        raw_fill = fill_cfg.get("ram_fill")
        if isinstance(raw_fill, dict) and raw_fill.get("target_reserve_gb") is not None:
            try:
                reserve = max(10.0, float(raw_fill["target_reserve_gb"]))
            except (TypeError, ValueError):
                pass
    return max(reserve, min_avail + 1.0)


def enforced_used_gb(*, stats: dict[str, float] | None = None) -> float:
    return footprint_gb(stats=stats)


def ram_mode(*, stats: dict[str, float] | None = None) -> str:
    import dgx_ram_events as events

    return events.ram_mode(stats=stats)


def ram_agent_cap(*, stats: dict[str, float] | None = None) -> int:
    import dgx_ram_events as events

    return events.ram_agent_cap(stats=stats)


def dispatch_allowed(*, stats: dict[str, float] | None = None) -> bool:
    import dgx_ram_events as events

    return events.dispatch_allowed(stats=stats)


def is_unittest_worker_cmdline(cmdline: str) -> bool:
    """True for actual ``python -m unittest`` processes, not agent prompt text."""
    if not cmdline or _AGENT_SKIP_RE.search(cmdline):
        return False
    return bool(_UNITTEST_WORKER_RE.search(cmdline))


def _proc_cwd(pid: int) -> Path | None:
    """Linux ``/proc/<pid>/cwd``; None when unreadable (macOS / permission)."""
    link = Path(f"/proc/{pid}/cwd")
    try:
        return link.resolve()
    except OSError:
        return None


def _unittest_cwd_in_hub(pid: int, hub: Path | None = None) -> bool:
    """True when unittest cwd is under Automation hub (or cwd unknown).

    OVERSEER_UNITTEST_CENSUS_HUB_CWD_2026_09_07 — foreign repos (e.g. Doc2Api
    hung ``unittest discover``) must not inflate hub quiet-wait / storm-trim
    census or get SIGKILL'd by hub trim.
    """
    root = (hub or auto.ROOT).resolve()
    cwd = _proc_cwd(pid)
    if cwd is None:
        # Fail-open when /proc cwd unavailable (ps fallback / macOS).
        return True
    try:
        cwd.relative_to(root)
        return True
    except ValueError:
        return False


def _iter_proc_cmdlines_ps() -> list[tuple[int, str]]:
    try:
        proc = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=8.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0 or not proc.stdout:
        return []
    out: list[tuple[int, str]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        try:
            out.append((int(parts[0]), parts[1]))
        except ValueError:
            continue
    return out


def iter_proc_cmdlines() -> list[tuple[int, str]]:
    """Linux ``/proc`` scan — cheaper than ps/pgrep on daemon hot paths."""
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return _iter_proc_cmdlines_ps()
    out: list[tuple[int, str]] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            pid = int(entry.name)
        except ValueError:
            continue
        cmdline_path = entry / "cmdline"
        try:
            raw = cmdline_path.read_bytes()
        except OSError:
            continue
        if not raw:
            continue
        cmd = raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
        if cmd:
            out.append((pid, cmd))
    if out:
        return out
    return _iter_proc_cmdlines_ps()


def list_unittest_worker_pids() -> list[int]:
    """PIDs of hub-scoped unittest workers (excludes cursor-agent argv + foreign cwd)."""
    return [
        pid
        for pid, cmd in iter_proc_cmdlines()
        if is_unittest_worker_cmdline(cmd) and _unittest_cwd_in_hub(pid)
    ]


def unittest_worker_count() -> int:
    return len(list_unittest_worker_pids())


def classify_storm_worker_pids() -> tuple[list[int], list[int]]:
    """One ``/proc`` walk → (self_check_pids, unittest_pids).

    OVERSEER_TRIM_ONE_CENSUS_2026_09_06 — ``_trim_storm`` + ``poll_once`` used to
    call ``list_self_check_pids`` then ``list_unittest_worker_pids`` (2× census).
    Timed hub: double mean ~15.8ms vs single ~8.8ms (~1.8×).
    OVERSEER_UNITTEST_CENSUS_HUB_CWD_2026_09_07 — unittest side hub-scoped.
    """
    sc: list[int] = []
    ut: list[int] = []
    for pid, cmd in iter_proc_cmdlines():
        if _is_self_check_cmdline(cmd):
            sc.append(pid)
        elif is_unittest_worker_cmdline(cmd) and _unittest_cwd_in_hub(pid):
            ut.append(pid)
    return sc, ut


def _is_self_check_cmdline(cmdline: str) -> bool:
    """Count real python self-check workers — not shell wrappers / prompt text.

    Cap/quiet-wait use this count. Matching ``bash -c`` / Cursor
    ``bash -O extglob -c`` with peer_orchestrate/--self-check in prompt text
    double-counts and starves verify under ``dgx_self_check_cap=1``.
    Require argv0 basename to start with ``python``.
    # OVERSEER_SELF_CHECK_ARGV0_2026_09_03
    """
    if not cmdline or _AGENT_SKIP_RE.search(cmdline):
        return False
    if _SHELL_WRAPPER_RE.search(cmdline):
        return False
    first = cmdline.split(None, 1)[0]
    base = Path(first).name.lower()
    if not base.startswith("python"):
        return False
    return "peer_orchestrate.py" in cmdline and "--self-check" in cmdline


def list_self_check_pids() -> list[int]:
    return [pid for pid, cmd in iter_proc_cmdlines() if _is_self_check_cmdline(cmd)]


def self_check_worker_count() -> int:
    return len(list_self_check_pids())


def trim_self_check_storm(*, cap: int | None = None, pids: list[int] | None = None) -> int:
    cfg = _dgx_cfg()
    try:
        limit = cap if cap is not None else max(1, int(cfg.get("dgx_self_check_cap") or 2))
    except (TypeError, ValueError):
        limit = 2
    if pids is None:
        pids = list_self_check_pids()
    if len(pids) <= limit:
        return 0
    killed = 0
    for pid in pids[limit:]:
        try:
            os.kill(pid, signal.SIGKILL)
            killed += 1
        except OSError:
            pass
    return killed


def verify_protect_path() -> Path:
    """Session-leader PIDs that storm trims must never SIGKILL."""
    return auto.CONFIG_DIR / "verify-protect.pids"


def register_verify_protect(pid: int) -> None:
    """Protect a verify/audit session leader (and its process group)."""
    try:
        path = verify_protect_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{int(pid)}\n")
    except OSError:
        pass


def unregister_verify_protect(pid: int) -> None:
    try:
        path = verify_protect_path()
        if not path.is_file():
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        kept = [ln for ln in lines if ln.strip() and ln.strip() != str(int(pid))]
        if kept:
            path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
    except OSError:
        pass


def _verify_protect_leaders() -> set[int]:
    path = verify_protect_path()
    out: set[int] = set()
    try:
        if not path.is_file():
            return out
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.add(int(line))
            except ValueError:
                continue
    except OSError:
        return out
    return out

def _pid_pgid(pid: int) -> int | None:
    try:
        return os.getpgid(pid)
    except OSError:
        return None


def _is_verify_protected(pid: int, leaders: set[int]) -> bool:
    if not leaders:
        return False
    if pid in leaders:
        return True
    pgid = _pid_pgid(pid)
    return pgid is not None and pgid in leaders


def trim_unittest_storm(*, cap: int | None = None, pids: list[int] | None = None) -> int:
    """SIGKILL unittest workers above cap. Protect verify-gate session leaders."""
    # OVERSEER_SCRUB_ORPHAN_FORGE_BUDGET_2026_09_04 — inactive forge orphans
    # keep agents>quiet_cap → deferred verify; scrub on every verify-lane trim.
    try:
        import peer_product_forge as forge

        if not forge.forge_active():
            forge.scrub_orphan_forge_agents()
    except Exception:  # noqa: BLE001
        pass
    limit = cap if cap is not None else guard_shell_vars()["unittest_cap"]
    if pids is None:
        pids = list_unittest_worker_pids()
    leaders = _verify_protect_leaders()
    protected = [p for p in pids if _is_verify_protected(p, leaders)]
    rest = [p for p in pids if p not in protected]
    keep_rest = max(0, int(limit) - len(protected))
    to_kill = rest[keep_rest:]
    killed = 0
    for pid in to_kill:
        try:
            os.kill(pid, signal.SIGKILL)
            killed += 1
        except OSError:
            pass
    # OVERSEER_FAIL_TTL_STORM_2026_09_04 — storm FAIL must not pin fail-ttl poison.
    if killed > 0:
        try:
            cache = auto._load_cache()
            if cache.get("tests_ok") is False and "FAIL" in str(cache.get("tests_detail") or ""):
                cache["tests_ts"] = 0.0
                cache["tests_detail"] = "tests: cleared after unittest storm trim"
                auto._save_cache(cache)
        except Exception:  # noqa: BLE001
            pass
    return killed


def guard_shell_vars() -> dict[str, Any]:
    stats = mem_stats()
    min_avail, crit_avail = effective_ram_thresholds(stats["total_gb"])
    cfg = _dgx_cfg()
    try:
        unittest_cap = max(1, int(cfg.get("dgx_unittest_cap") or auto.CFG.get("dgx_unittest_cap") or 8))
    except (TypeError, ValueError):
        unittest_cap = 8
    # Prefer top-level overlay caps (belt-and-suspenders vs nested).
    try:
        top_ut = auto.CFG.get("dgx_unittest_cap")
        if top_ut is not None:
            unittest_cap = min(unittest_cap, max(1, int(top_ut)))
    except (TypeError, ValueError):
        pass
    try:
        max_agents = max(
            1,
            int(
                cfg.get("dgx_max_cursor_agents")
                or auto.CFG.get("max_parallel_agent_procs")
                or 24
            ),
        )
    except (TypeError, ValueError):
        max_agents = 24
    try:
        max_agents = min(max_agents, max(1, int(auto.max_parallel_peers())))
    except (TypeError, ValueError):
        pass
    cap = ram_max_used_gb()
    stats = mem_stats()
    return {
        "unittest_cap": unittest_cap,
        "max_agents": max_agents,
        "min_avail_gb": min_avail,
        "crit_avail_gb": crit_avail,
        "max_used_gb": cap if cap is not None else 0,
        "used_gb": stats["used_gb"],
        "footprint_gb": stats["footprint_gb"],
        "used_avail_gb": stats["used_avail_gb"],
        "total_gb": stats["total_gb"],
        "avail_gb": stats["avail_gb"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="DGX RAM budget helpers")
    parser.add_argument("--shell-vars", action="store_true", help="Print guard thresholds for bash")
    parser.add_argument("--json", action="store_true", help="Print full budget report as JSON")
    parser.add_argument("--unittest-count", action="store_true", help="Print unittest worker count")
    parser.add_argument("--trim-unittest-storm", action="store_true", help="Kill excess unittest workers")
    parser.add_argument("--self-check-count", action="store_true", help="Print peer_orchestrate self-check count")
    parser.add_argument("--trim-self-check-storm", action="store_true", help="Kill excess self-check workers")
    parser.add_argument("--govern", action="store_true", help="Priority governor — evict low tier or fill high tier")
    parser.add_argument("--priority-snapshot", action="store_true", help="Print priority tier inventory JSON")
    parser.add_argument("--stable-maintain", action="store_true", help="Stable pinned-shm top-up only (no page warm)")
    parser.add_argument("--rebalance", action="store_true", help="Purge waste + fill productive shm only")
    parser.add_argument("--ram-events", action="store_true", help="Evaluate RAM event triggers (100/110/120GB)")
    parser.add_argument("--ram-snapshot", action="store_true", help="Print RAM mode snapshot JSON")
    args = parser.parse_args()
    if args.unittest_count:
        print(unittest_worker_count())
        return 0
    if args.trim_unittest_storm:
        killed = trim_unittest_storm()
        if killed:
            print(f"trimmed {killed} unittest worker(s)")
        return 0
    if args.self_check_count:
        print(self_check_worker_count())
        return 0
    if args.trim_self_check_storm:
        killed = trim_self_check_storm()
        if killed:
            print(f"trimmed {killed} self-check worker(s)")
        return 0
    if args.govern:
        import dgx_ram_events as events

        events.handle_events(log_fn=lambda m: None if args.json else print(m))
        import dgx_ram_priority as priority

        report = priority.govern()
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            after = report.get("after") or {}
            print(
                f"govern: {report.get('action')} used {after.get('used_gb')}GB "
                f"/ target {report.get('target_used_gb')}GB [{report.get('pressure')}]"
            )
        return 0
    if args.priority_snapshot:
        import dgx_ram_priority as priority

        print(json.dumps(priority.tier_snapshot(), indent=2))
        return 0
    if args.ram_events:
        import dgx_ram_events as events

        report = events.handle_events(log_fn=lambda m: None if args.json else print(m))
        if args.json:
            print(json.dumps(report, indent=2))
        return 0
    if args.ram_snapshot:
        import dgx_ram_events as events

        print(json.dumps(events.snapshot(), indent=2))
        return 0
    if args.stable_maintain:
        import dgx_ram_fill as fill

        trim_self_check_storm()
        trim_unittest_storm()
        report = fill.maintain_ram_stable()
        if args.json:
            print(json.dumps(report))
        else:
            print(
                f"stable: productive={report.get('productive_shm_gb_after')}GB "
                f"avail={report.get('avail_gb_after')}GB pressure={report.get('pressure')}"
            )
        return 0
    if args.rebalance:
        import dgx_ram_fill as fill

        trim_self_check_storm()
        trim_unittest_storm()
        report = fill.rebalance_ram()
        if args.json:
            print(json.dumps(report))
        else:
            print(
                f"rebalance: productive={report.get('productive_shm_gb_after')}GB "
                f"avail={report.get('avail_gb_after')}GB agents={report.get('agents')}"
            )
        return 0
    report = guard_shell_vars()
    report["level"] = pressure_level(avail_gb=report["avail_gb"], total_gb=report["total_gb"])
    if args.shell_vars:
        print(
            f"{report['unittest_cap']} {report['max_agents']} "
            f"{report['min_avail_gb']} {report['crit_avail_gb']} {report['max_used_gb']} "
            f"{report['footprint_gb']}"
        )
        return 0
    if args.json:
        print(json.dumps(report))
        return 0
    print(
        f"RAM budget: footprint {report['footprint_gb']:.1f}GB / cap {report['max_used_gb'] or 'none'}GB "
        f"(avail-based {report['used_avail_gb']:.1f}GB) — avail {report['avail_gb']:.1f}GB "
        f"(min {report['min_avail_gb']}, crit {report['crit_avail_gb']}) "
        f"[{report['level']}]"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
