#!/usr/bin/env python3
"""DGX RAM acceleration — tmpfs build caches + parallel native verify pool.

Uses spare RAM (not agent slots) to make every dev cycle faster:
- pip/npm/ccache/pytest caches on /dev/shm (61GB tmpfs on Spark)
- parallel native verify across synced registry repos
- page-cache warm for hot repo paths
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import dgx_ram_accel_config as rac  # noqa: E402
import dgx_ram_fill as ram_fill  # noqa: E402
import dgx_shm_hydrate as hydrate  # noqa: E402
import factory_fanout as fanout  # noqa: E402
import project_automation as auto  # noqa: E402

ADAPT = SCRIPTS / "automation_adapt.py"
REGISTRY = ROOT / "repos" / "registry.json"


def _log(msg: str, log_fn: Callable[[str], None] = print) -> None:
    log_fn(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ram_accel: {msg}")


def ensure_shm_caches(*, log_fn: Callable[[str], None] = print) -> list[str]:
    """Create tmpfs cache dirs and wire env vars for child processes."""
    if not rac.enabled():
        return []
    root = rac.cache_root()
    actions: list[str] = []
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _log(f"cache root unavailable ({exc})", log_fn)
        return actions

    for name in rac.cache_subdirs():
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        actions.append(str(path))

    # Wire standard cache env (child daemons inherit via systemd EnvironmentFile or shell profile)
    env_map = {
        "PIP_CACHE_DIR": str(root / "pip"),
        "npm_config_cache": str(root / "npm"),
        "CCACHE_DIR": str(root / "ccache"),
        "PYTEST_CACHE_DIR": str(root / "pytest"),
        "UV_CACHE_DIR": str(root / "uv"),
        "PNPM_HOME": str(root / "pnpm-store"),
    }
    for key, val in env_map.items():
        os.environ[key] = val

    _log(f"shm caches ready under {root} ({len(actions)} dirs)", log_fn)
    return actions


def _repo_test_command(repo: Path) -> list[str] | None:
    cfg_path = repo / "automation.config.json"
    if cfg_path.is_file():
        try:
            data = json.loads(cfg_path.read_text())
            cmd = data.get("test_command")
            if isinstance(cmd, list) and cmd:
                return [str(x) for x in cmd]
        except (json.JSONDecodeError, OSError):
            pass
    if (repo / "package.json").is_file():
        return ["npm", "test", "--if-present"]
    if (repo / "pyproject.toml").is_file() or (repo / "setup.py").is_file():
        return ["python3", "-m", "pytest", "-q", "--tb=no"]
    if (repo / "tests").is_dir():
        return ["python3", "-m", "unittest", "discover", "-s", "tests", "-q"]
    return None


def _run_verify(repo: Path, name: str) -> dict[str, Any]:
    cmd = _repo_test_command(repo)
    if not cmd:
        return {"name": name, "path": str(repo), "skipped": True}
    if cmd[0] == "npm":
        if shutil.which("npm") is None:
            return {"name": name, "path": str(repo), "skipped": True, "reason": "npm missing"}
    started = time.time()
    env = dict(os.environ)
    proc = subprocess.run(
        cmd,
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
        check=False,
    )
    return {
        "name": name,
        "path": str(repo),
        "cmd": cmd,
        "rc": proc.returncode,
        "elapsed_sec": round(time.time() - started, 1),
        "tail": (proc.stderr or proc.stdout or "")[-300:],
    }


def warm_repo_paths(*, log_fn: Callable[[str], None] = print) -> int:
    """Read hot files into page cache (cheap when RAM is free)."""
    import dgx_ram_efficiency as eff

    if eff.stable_mode() or not eff.page_warm_enabled():
        return 0
    warmed = 0
    for entry in fanout.load_candidates():
        repo = Path(str(entry.get("resolved_path") or ""))
        if not repo.is_dir():
            continue
        for pattern in ("*.py", "*.ts", "*.tsx", "*.json", "*.md"):
            for path in list(repo.rglob(pattern))[:200]:
                try:
                    if path.stat().st_size < 512_000:
                        path.read_bytes()
                        warmed += 1
                except OSError:
                    continue
    hub = ROOT
    for pattern in ("scripts/*.py", "tests/*.py", "notes/*.md"):
        for path in hub.glob(pattern):
            try:
                path.read_bytes()
                warmed += 1
            except OSError:
                continue
    _log(f"warmed {warmed} files into page cache", log_fn)
    return warmed


def run_verify_pool(*, log_fn: Callable[[str], None] = print) -> dict[str, Any]:
    """Parallel native verify on all registry repos present on DGX."""
    candidates = fanout.load_candidates()
    hub = [{"name": "Automation Hub", "resolved_path": str(ROOT)}]
    repos = hub + candidates
    if not repos:
        _log("no repos for verify pool", log_fn)
        return {"results": []}

    parallel = min(rac.verify_parallel(), len(repos))
    _log(f"verify pool — {len(repos)} repo(s), parallel={parallel}", log_fn)

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = {}
        for entry in repos:
            repo = Path(str(entry["resolved_path"]))
            if not repo.is_dir():
                continue
            fut = pool.submit(_run_verify, repo, str(entry.get("name") or repo.name))
            futures[fut] = entry

        for fut in as_completed(futures):
            row = fut.result()
            results.append(row)
            if row.get("skipped"):
                continue
            tag = "ok" if row.get("rc") == 0 else "fail"
            _log(f"[{tag}] {row.get('name')} ({row.get('elapsed_sec')}s)", log_fn)

    ok = sum(1 for r in results if r.get("rc") == 0)
    return {"ok": ok, "fail": sum(1 for r in results if r.get("rc") not in (0, None) and not r.get("skipped")), "results": results}


def run_cycle(*, log_fn: Callable[[str], None] = print) -> dict[str, Any]:
    ensure_shm_caches(log_fn=log_fn)
    report: dict[str, Any] = {"caches": True}
    if rac.hydrate_on_start():
        report["mirrors"] = hydrate.hydrate_mirrors(log_fn=lambda m: _log(m, log_fn))
        report["venvs"] = hydrate.warm_python_venvs(log_fn=lambda m: _log(m, log_fn))
    if ram_fill.fill_enabled():
        import dgx_ram_efficiency as eff

        if eff.stable_mode():
            report["fill"] = ram_fill.maintain_ram_stable(log_fn=lambda m: _log(m, log_fn))
        else:
            report["fill"] = ram_fill.run_fill_cycle(log_fn=lambda m: _log(m, log_fn))
    if rac.warm_on_start():
        report["warmed"] = warm_repo_paths(log_fn=log_fn)
    report["verify"] = run_verify_pool(log_fn=log_fn)
    report["hydration"] = hydrate.hydration_report()
    return report


def run_forever() -> None:
    _log("forever loop started")
    if rac.hydrate_on_start():
        hydrate.hydrate_mirrors(log_fn=lambda m: _log(m))
        hydrate.warm_python_venvs(log_fn=lambda m: _log(m))
    if ram_fill.fill_enabled():
        import dgx_ram_efficiency as eff

        if eff.stable_mode():
            ram_fill.maintain_ram_stable(log_fn=lambda m: _log(m))
        else:
            ram_fill.run_fill_cycle(log_fn=lambda m: _log(m))
    if rac.warm_on_start():
        warm_repo_paths()
    last_maintain = 0.0
    last_verify = 0.0
    while True:
        if not rac.enabled():
            time.sleep(60)
            continue
        now = time.time()
        try:
            if ram_fill.fill_enabled() and now - last_maintain >= ram_fill.maintain_interval_sec():
                report = ram_fill.maintain_ram(log_fn=lambda m: _log(m))
                pinned = report.get("pinned_shm_gb_after") or report.get("pinned_shm_gb_before")
                _log(f"maintain — pinned {pinned}GB shm, avail {report.get('avail_gb_after', report.get('avail_gb'))}GB")
                last_maintain = now
            if now - last_verify >= rac.verify_interval_sec():
                run_verify_pool(log_fn=lambda m: _log(m))
                last_verify = now
        except Exception as exc:  # noqa: BLE001
            _log(f"cycle error — {exc}")
        time.sleep(15)


def main() -> int:
    parser = argparse.ArgumentParser(description="DGX RAM acceleration — caches + verify pool")
    parser.add_argument("--forever", action="store_true")
    parser.add_argument("--caches-only", action="store_true")
    parser.add_argument("--warm-only", action="store_true")
    parser.add_argument("--hydrate-only", action="store_true")
    parser.add_argument("--fill-only", action="store_true")
    parser.add_argument("--maintain-only", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--report", action="store_true", help="Show shm hydration stats")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.report:
        print(json.dumps(hydrate.hydration_report(), indent=2))
        return 0

    if args.forever:
        run_forever()
        return 0

    report: dict[str, Any] = {}
    if args.caches_only:
        report["caches"] = ensure_shm_caches()
    elif args.warm_only:
        report["warmed"] = warm_repo_paths()
    elif args.hydrate_only:
        report["mirrors"] = hydrate.hydrate_mirrors()
        report["venvs"] = hydrate.warm_python_venvs()
        report["hydration"] = hydrate.hydration_report()
    elif args.fill_only:
        report["fill"] = ram_fill.run_fill_cycle()
    elif args.maintain_only:
        report["maintain"] = ram_fill.maintain_ram()
    elif args.verify_only:
        report["verify"] = run_verify_pool()
    else:
        report = run_cycle(log_fn=lambda m: None if args.json else print(m))

    if args.json:
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
