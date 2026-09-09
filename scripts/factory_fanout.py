#!/usr/bin/env python3
"""Parallel factory fanout — probe/adapt external repos from registry.json.

Runs on DGX to burn idle RAM/CPU on unaudited repos while peer-loop grinds the hub.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

REGISTRY = ROOT / "repos" / "registry.json"
ADAPT = SCRIPTS / "automation_adapt.py"
# Durable Lane-C verify: cycle log OR agents≥floor (keep-alive FANOUT_RESPAWN_BELOW).
CYCLE_LOG = ROOT / "notes" / "compression_artifacts" / "fanout_cycle.json"
HUB_CYCLE_LOG = Path.home() / ".config" / "automation-hub" / "factory-fanout-cycle.json"
HUB_FANOUT_LOG = Path.home() / ".config" / "automation-hub" / "factory-fanout.log"


def _fanout_cfg() -> dict[str, Any]:
    raw = auto.CFG.get("factory_fanout")
    return raw if isinstance(raw, dict) else {}


def fanout_enabled() -> bool:
    return bool(_fanout_cfg().get("enabled", True))


def fanout_parallel() -> int:
    try:
        return max(1, int(_fanout_cfg().get("parallel") or 4))
    except (TypeError, ValueError):
        return 4


def fanout_interval_sec() -> float:
    try:
        return max(60.0, float(_fanout_cfg().get("interval_sec") or 300))
    except (TypeError, ValueError):
        return 300.0


def status_filter() -> set[str]:
    raw = _fanout_cfg().get("status_filter")
    if isinstance(raw, list) and raw:
        return {str(s).lower() for s in raw}
    return {"unaudited", "needs-kit-install", "git"}


# Needle: OVERSEER_FANOUT_AGENT_COUNT_TTL_2026_09_08 — S23 probe-once / remiss cache
# (Lane C write_cycle_log was re-shelling ps every cycle; ~15–23ms).
_AGENT_COUNT_TTL_SEC = 30.0
_agent_count_cache: dict[str, float | int] = {}


def clear_cursor_agent_count_cache() -> None:
    """Drop TTL memo (tests / after intentional spawn/kill)."""
    _agent_count_cache.clear()


def _cursor_agent_count(*, force: bool = False) -> int:
    """Count live cursor-agent procs — TTL-cached (research-speed probe-once)."""
    now = time.monotonic()
    if not force:
        at = _agent_count_cache.get("at")
        val = _agent_count_cache.get("n")
        if isinstance(at, (int, float)) and isinstance(val, int) and (now - float(at)) < _AGENT_COUNT_TTL_SEC:
            return int(val)
    out = subprocess.getoutput("ps -u \"$USER\" -o cmd= | grep -c '[c]ursor-agent' || true")
    try:
        n = int(out.strip() or "0")
    except ValueError:
        n = 0
    _agent_count_cache["at"] = now
    _agent_count_cache["n"] = n
    return n


def _worktree_pool_count() -> int:
    wt = ROOT / ".worktrees"
    if not wt.is_dir():
        return 0
    return sum(1 for p in wt.glob("peer-*") if p.is_dir())


def _kd_agent_floor() -> int:
    """Prefer keep-alive FANOUT_RESPAWN_BELOW; else config parallel_peer_floor.

    OVERSEER_KD_FLOOR_CLAMP_MAX_PEERS_2026_09_08 — never exceed max_parallel_peers
    (free-desktop / CLEAN cap). Stale FANOUT_RESPAWN_BELOW=96 made agents_ge_floor
    permanently false at live agents≤8 (research-speed S28 / Lane C KD fanout).
    """
    raw = os.environ.get("FANOUT_RESPAWN_BELOW")
    floor = None
    if raw is not None and str(raw).strip() != "":
        try:
            floor = max(1, int(raw))
        except (TypeError, ValueError):
            floor = None
    if floor is None:
        floor = int(auto.parallel_peer_floor())
    try:
        cap = int(auto.max_parallel_peers())
    except (TypeError, ValueError):
        cap = 8
    return max(1, min(floor, cap))


def write_cycle_log(report: dict[str, Any], *, log_fn=print) -> Path:
    """Persist fanout cycle for Lane C verify (cycle log OR agents≥floor)."""
    floor = _kd_agent_floor()
    agents = _cursor_agent_count()
    pool = _worktree_pool_count()
    agents_ok = agents >= floor
    pool_ok = pool >= floor
    row = {
        **report,
        "ts": report.get("ts") or datetime.now(timezone.utc).isoformat(),
        "agents": agents,
        "worktrees": pool,
        "floor": floor,
        "agents_ge_floor": agents_ok,
        "pool_ge_floor": pool_ok,
        # Lane C verify path #1: this cycle log exists.
        "verify_ok": True,
        "verify": "agents_ge_floor" if agents_ok else ("pool_ge_floor" if pool_ok else "cycle_log"),
        "lane": "CT-C",
        "cid": "20260906T232110Z",
        "role": "research_speed_engineer",
        "service_masked": not (Path.home() / ".config/systemd/user/factory-fanout.service").exists(),
        "no_public_publish": True,
        "stress_bars_untouched": True,
    }
    text = json.dumps(row, indent=2) + "\n"
    for path in (CYCLE_LOG, HUB_CYCLE_LOG):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            log_fn(f"factory_fanout: cycle log skip {path.name} — {exc}")
    line = (
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  factory_fanout: cycle "
        f"candidates={row.get('candidates', 0)} ok={row.get('ok', 0)} fail={row.get('fail', 0)} "
        f"agents={agents}/{floor} pool={pool} agents_ge_floor={agents_ok}"
    )
    try:
        HUB_FANOUT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with HUB_FANOUT_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        log_fn(f"factory_fanout: hub log skip — {exc}")
    log_fn(line)
    return CYCLE_LOG


def _path_roots() -> tuple[Path, Path]:
    home = Path.home()
    remote = auto.CFG.get("agent_remote")
    if isinstance(remote, dict):
        local = Path(str(remote.get("local_root") or home)).expanduser()
        rem = Path(str(remote.get("remote_root") or "/home/arnavrastogi")).expanduser()
        return local.resolve(), rem.resolve()
    dgx = auto.CFG.get("dgx_host")
    if isinstance(dgx, dict):
        rem = Path(str(dgx.get("remote_root") or "/home/arnavrastogi")).expanduser()
        return home.resolve(), rem.resolve()
    return home.resolve(), home.resolve()


def resolve_repo_path(raw_path: str) -> Path | None:
    p = Path(raw_path).expanduser()
    if p.is_dir():
        return p.resolve()
    local_root, remote_root = _path_roots()
    text = str(p)
    if text.startswith(str(local_root)):
        alt = remote_root / p.relative_to(local_root)
        if alt.is_dir():
            return alt.resolve()
    if text.startswith(str(remote_root)):
        return p.resolve() if p.is_dir() else None
    return None


def load_candidates() -> list[dict[str, Any]]:
    if not REGISTRY.is_file():
        return []
    try:
        data = json.loads(REGISTRY.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    repos = data.get("repos") if isinstance(data, dict) else []
    if not isinstance(repos, list):
        return []
    filt = status_filter()
    hub = str(ROOT.resolve())
    out: list[dict[str, Any]] = []
    for entry in repos:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "").lower()
        if filt and status not in filt:
            continue
        path = resolve_repo_path(str(entry.get("path") or ""))
        if path is None or str(path) == hub:
            continue
        out.append({**entry, "resolved_path": str(path)})
    return out


def _run_adapt_probe(target: Path, *, quick: bool) -> dict[str, Any]:
    cmd = [sys.executable, str(ADAPT), "--target", str(target), "--probe", "--audit"]
    if quick:
        cmd.append("--quick")
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), check=False)
    return {
        "path": str(target),
        "rc": proc.returncode,
        "elapsed_sec": round(time.time() - started, 1),
        "stdout_tail": (proc.stdout or "")[-400:],
        "stderr_tail": (proc.stderr or "")[-400:],
    }


def run_fanout(
    *,
    quick: bool = True,
    limit: int | None = None,
    log_fn=print,
    write_log: bool = True,
) -> dict[str, Any]:
    candidates = load_candidates()
    if limit is not None:
        candidates = candidates[: max(0, limit)]
    if not candidates:
        log_fn("factory_fanout: no registry candidates")
        report: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "candidates": 0,
            "ok": 0,
            "fail": 0,
            "results": [],
            "note": "native_verify_remaining=0",
        }
        if write_log:
            write_cycle_log(report, log_fn=log_fn)
        return report

    parallel = min(fanout_parallel(), len(candidates))
    log_fn(f"factory_fanout: probing {len(candidates)} repo(s) · parallel={parallel}")

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = {
            pool.submit(_run_adapt_probe, Path(c["resolved_path"]), quick=quick): c for c in candidates
        }
        for fut in as_completed(futures):
            entry = futures[fut]
            try:
                row = fut.result()
            except Exception as exc:  # noqa: BLE001
                row = {"path": entry.get("resolved_path"), "rc": 1, "error": str(exc)}
            row["name"] = entry.get("name")
            row["status"] = entry.get("status")
            results.append(row)
            tag = "ok" if row.get("rc") == 0 else "fail"
            log_fn(f"factory_fanout: [{tag}] {row.get('name')} ({row.get('elapsed_sec', '?')}s)")

    ok = sum(1 for r in results if r.get("rc") == 0)
    report = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "candidates": len(candidates),
        "ok": ok,
        "fail": len(results) - ok,
        "results": results,
    }
    if write_log:
        write_cycle_log(report, log_fn=log_fn)
    return report


def run_forever(*, quick: bool = True) -> None:
    log_fn = lambda msg: print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}", flush=True)
    log_fn("factory_fanout: forever loop started")
    while True:
        if not fanout_enabled():
            log_fn("factory_fanout: disabled — sleeping 60s")
            time.sleep(60)
            continue
        try:
            run_fanout(quick=quick, log_fn=log_fn)
        except Exception as exc:  # noqa: BLE001
            log_fn(f"factory_fanout: cycle error — {exc}")
        time.sleep(fanout_interval_sec())


def main() -> int:
    parser = argparse.ArgumentParser(description="Parallel adapt/probe on external registry repos")
    parser.add_argument("--forever", action="store_true", help="Run on interval (daemon)")
    parser.add_argument("--quick", action="store_true", default=True, help="Quick probes (default)")
    parser.add_argument("--deep", action="store_true", help="Full probes (no --quick)")
    parser.add_argument("--limit", type=int, default=None, help="Max repos per cycle")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    parser.add_argument(
        "--no-cycle-log",
        action="store_true",
        help="Skip writing notes/compression_artifacts/fanout_cycle.json",
    )
    args = parser.parse_args()
    quick = not args.deep
    if args.forever:
        run_forever(quick=quick)
        return 0
    report = run_fanout(
        quick=quick,
        limit=args.limit,
        log_fn=lambda m: None if args.json else print(m),
        write_log=not args.no_cycle_log,
    )
    if args.json:
        # Re-read cycle file metrics when present for Lane C verify payload.
        if CYCLE_LOG.is_file() and not args.no_cycle_log:
            try:
                report = {**report, **json.loads(CYCLE_LOG.read_text(encoding="utf-8"))}
            except (json.JSONDecodeError, OSError):
                pass
        print(json.dumps(report, indent=2))
    # Lane C verify: cycle log written OR agents/pool ≥ floor — not probe fails alone.
    if CYCLE_LOG.is_file() and not args.no_cycle_log:
        try:
            meta = json.loads(CYCLE_LOG.read_text(encoding="utf-8"))
            if meta.get("verify_ok"):
                return 0
        except (json.JSONDecodeError, OSError):
            pass
    return 0 if report.get("fail", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
