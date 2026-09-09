#!/usr/bin/env python3
"""Parallel factory fanout — probe/adapt external repos from registry.json.

Runs on DGX to burn idle RAM/CPU on unaudited repos while peer-loop grinds the hub.
"""

from __future__ import annotations

import argparse
import json
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


def _path_roots() -> tuple[Path, Path]:
    """Return (local_root, remote_root).

    Needle: OVERSEER_REGISTRY_MAC_MIRROR_2026_09_04 — never ``resolve()`` the
    remote root: macOS firmlinks rewrite ``/home/...`` →
    ``/System/Volumes/Data/home/...`` and break prefix match against registry
    DGX paths (``/home/arnavrastogi/...``).
    """
    home = Path.home()
    remote = auto.CFG.get("agent_remote")
    if isinstance(remote, dict):
        local = Path(str(remote.get("local_root") or home)).expanduser()
        rem = Path(str(remote.get("remote_root") or "/home/arnavrastogi")).expanduser()
        try:
            local = local.resolve()
        except OSError:
            pass
        return local, rem
    dgx = auto.CFG.get("dgx_host")
    if isinstance(dgx, dict):
        rem = Path(str(dgx.get("remote_root") or "/home/arnavrastogi")).expanduser()
        try:
            home = home.resolve()
        except OSError:
            pass
        return home, rem
    try:
        home = home.resolve()
    except OSError:
        pass
    return home, home


def _mirror_under(src_root: Path, dst_root: Path, path: Path) -> Path | None:
    """If ``path`` is under ``src_root``, return ``dst_root / rel`` when that dir exists."""
    src_s = str(src_root).rstrip("/")
    text = str(path)
    if text == src_s or text.startswith(src_s + "/"):
        rel = text[len(src_s) :].lstrip("/")
        alt = dst_root / rel if rel else dst_root
        if alt.is_dir():
            try:
                return alt.resolve()
            except OSError:
                return alt
    try:
        rel_p = path.relative_to(src_root)
    except ValueError:
        return None
    alt = dst_root / rel_p
    if alt.is_dir():
        try:
            return alt.resolve()
        except OSError:
            return alt
    return None


def resolve_repo_path(raw_path: str) -> Path | None:
    """Resolve a registry path on this host; map Mac↔DGX home mirrors when missing.

    Needle: OVERSEER_REGISTRY_MAC_MIRROR_2026_09_04
    """
    p = Path(raw_path).expanduser()
    if p.is_dir():
        try:
            return p.resolve()
        except OSError:
            return p
    local_root, remote_root = _path_roots()
    # Mac path missing → try DGX remote
    got = _mirror_under(local_root, remote_root, p)
    if got is not None:
        return got
    # DGX / remote path missing → try Mac (local) mirror
    remote_aliases = {remote_root, Path("/home/arnavrastogi")}
    try:
        remote_aliases.add(remote_root.resolve())
    except OSError:
        pass
    for rem in remote_aliases:
        got = _mirror_under(rem, local_root, p)
        if got is not None:
            return got
    return None


def actionable_on_disk() -> list[dict[str, Any]]:
    """Registry rows whose SoT path is absent but a Mac/local mirror exists.

    Used by ``--registry-status`` so offline-mac / DGX-SoT gaps stay visible
    without reopening Active under ``factory_meter_mode=self_sufficient``.
    Needle: OVERSEER_REGISTRY_MAC_MIRROR_2026_09_04
    """
    if not REGISTRY.is_file():
        return []
    try:
        data = json.loads(REGISTRY.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    repos = data.get("repos") if isinstance(data, dict) else []
    if not isinstance(repos, list):
        return []
    hub = str(ROOT.resolve())
    out: list[dict[str, Any]] = []
    for entry in repos:
        if not isinstance(entry, dict):
            continue
        raw = str(entry.get("path") or "")
        if not raw:
            continue
        sot = Path(raw).expanduser()
        sot_here = sot.is_dir()
        mirrored = resolve_repo_path(raw)
        if mirrored is None or str(mirrored) == hub:
            continue
        # Actionable when SoT missing on this host but mirror resolved elsewhere,
        # or offline-mac with a real on-disk tree.
        status = str(entry.get("status") or "").lower()
        if sot_here and status not in ("offline-mac", "git", "unaudited", "needs-kit-install"):
            continue
        if sot_here and str(mirrored) == str(sot.resolve()):
            if status != "offline-mac":
                continue
        out.append(
            {
                "name": entry.get("name"),
                "status": entry.get("status"),
                "path": raw,
                "resolved_path": str(mirrored),
                "sot_present": sot_here,
            }
        )
    return out


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


def run_fanout(*, quick: bool = True, limit: int | None = None, log_fn=print) -> dict[str, Any]:
    candidates = load_candidates()
    if limit is not None:
        candidates = candidates[: max(0, limit)]
    if not candidates:
        log_fn("factory_fanout: no registry candidates")
        return {"candidates": 0, "results": []}

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
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "candidates": len(candidates),
        "ok": ok,
        "fail": len(results) - ok,
        "results": results,
    }


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
        "--registry-status",
        action="store_true",
        help="List Mac/local mirrors for DGX-SoT / offline-mac gaps (no probe)",
    )
    args = parser.parse_args()
    if args.registry_status:
        rows = actionable_on_disk()
        payload = {"actionable_on_disk": len(rows), "rows": rows}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"registry-status: actionable_on_disk={len(rows)}")
            for row in rows:
                print(
                    f"  - {row.get('name')} [{row.get('status')}] "
                    f"sot_present={row.get('sot_present')} → {row.get('resolved_path')}"
                )
        return 0
    quick = not args.deep
    if args.forever:
        run_forever(quick=quick)
        return 0
    report = run_fanout(quick=quick, limit=args.limit, log_fn=lambda m: None if args.json else print(m))
    if args.json:
        print(json.dumps(report, indent=2))
    return 0 if report.get("fail", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
