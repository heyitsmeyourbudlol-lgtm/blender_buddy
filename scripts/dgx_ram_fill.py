"""Aggressively use spare DGX RAM for caches — shm ballast, mirrors, pip prefetch, page warm."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import dgx_ram_accel_config as rac  # noqa: E402
import dgx_ram_budget as budget  # noqa: E402
import dgx_ram_efficiency as eff  # noqa: E402
import dgx_shm_hydrate as hydrate  # noqa: E402
import factory_fanout as fanout  # noqa: E402
import project_automation as auto  # noqa: E402

WORKTREE_SHM = Path("/dev/shm/automation-worktrees")
BALLAST_ROOT = Path("/dev/shm/automation-ballast")
READ_LOG = Path("/dev/shm/automation-cache/fill-state.txt")
FILL_LOCK_PATH = auto.CONFIG_DIR / "ram-fill.lock"
FILL_LOCK_STALE_SEC = 600.0
FILL_STEP_STATE = auto.CONFIG_DIR / "ram-fill-step.json"


def _try_acquire_fill_lock() -> bool:
    FILL_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    try:
        if FILL_LOCK_PATH.is_file():
            age = now - FILL_LOCK_PATH.stat().st_mtime
            if age < FILL_LOCK_STALE_SEC:
                try:
                    pid = int(FILL_LOCK_PATH.read_text().strip().splitlines()[0])
                except (OSError, ValueError, IndexError):
                    pid = None
                if pid and pid != os.getpid():
                    try:
                        os.kill(pid, 0)
                        return False
                    except OSError:
                        pass
        FILL_LOCK_PATH.write_text(f"{os.getpid()}\n{now}\n")
        return True
    except OSError:
        return True


def _release_fill_lock() -> None:
    try:
        if FILL_LOCK_PATH.is_file():
            text = FILL_LOCK_PATH.read_text()
            if text.startswith(str(os.getpid())):
                FILL_LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def page_warm_enabled() -> bool:
    raw = _fill_cfg().get("page_warm_enabled")
    if raw is not None:
        return bool(raw)
    return eff.page_warm_enabled()


def fill_pressure_ok() -> bool:
    return eff.fill_pressure_ok()


def should_page_warm() -> bool:
    if not page_warm_enabled() or eff.stable_mode():
        return False
    if not fill_pressure_ok():
        return False
    stats = budget.mem_stats()
    cap = budget.ram_max_used_gb()
    if cap is not None and stats["used_gb"] >= cap - 2.0:
        return False
    return True


def _fill_cfg() -> dict[str, Any]:
    raw = rac._cfg().get("ram_fill")
    return raw if isinstance(raw, dict) else {}


def fill_enabled() -> bool:
    return bool(_fill_cfg().get("enabled", False))


def target_reserve_gb() -> float:
    return budget.fill_stop_avail_gb()


def max_warm_passes() -> int:
    if not page_warm_enabled():
        return 0
    try:
        return max(0, int(_fill_cfg().get("max_passes") if _fill_cfg().get("max_passes") is not None else 3))
    except (TypeError, ValueError):
        return 3


def maintain_interval_sec() -> float:
    try:
        return max(30.0, float(_fill_cfg().get("maintain_interval_sec") or 90))
    except (TypeError, ValueError):
        return 90.0


def ballast_enabled() -> bool:
    if eff.enabled() and _fill_cfg().get("ballast_enabled") is False:
        return False
    return bool(_fill_cfg().get("ballast_enabled", False))


def target_productive_gb() -> float:
    raw = _fill_cfg().get("target_productive_shm_gb")
    if raw is not None:
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass
    return eff.target_productive_shm_gb()


def _shm_capacity_gb() -> float:
    """Total /dev/shm size in GiB — ballast must not target past this."""
    try:
        import shutil

        return shutil.disk_usage("/dev/shm").total / (1024**3)
    except OSError:
        return 0.0


def _shm_free_gb() -> float:
    try:
        import shutil

        return shutil.disk_usage("/dev/shm").free / (1024**3)
    except OSError:
        return 0.0


def min_pinned_shm_gb() -> float:
    """Configured pin target, clamped to shm capacity − headroom.

    Needle: OVERSEER_SHM_BALLAST_CAP_2026_09_04 — min_pinned=92 with 61G shm
    filled tmpfs to ENOSPC, truncated automation_cache.json, poisoned fail-ttl.
    """
    try:
        raw = max(0.0, float(_fill_cfg().get("min_pinned_shm_gb") or 0))
    except (TypeError, ValueError):
        raw = 0.0
    cap = _shm_capacity_gb()
    if cap <= 0.0:
        return raw
    # Leave room for automation-cache / mirrors / worktree shm.
    headroom = 2.0
    return min(raw, max(0.0, cap - headroom))


def ballast_chunk_bytes() -> int:
    try:
        mb = max(64, int(_fill_cfg().get("ballast_chunk_mb") or 512))
    except (TypeError, ValueError):
        mb = 512
    return mb * 1024 * 1024


def mirror_all_repos() -> bool:
    return bool(_fill_cfg().get("mirror_all_repos", False))


def avail_gb() -> float:
    return budget.mem_stats()["avail_gb"]


_SHARED_SHM_ROOTS = (
    rac.cache_root(),
    Path("/dev/shm/automation-mirror"),
    Path("/dev/shm/automation-hub-full"),
    Path("/dev/shm/automation-deps"),
    WORKTREE_SHM,
)
_SHM_ALLOC_CACHE: tuple[tuple[int, int], tuple[int, int]] | None = None
_SHM_CACHE_TS = 0.0
_SHM_CACHE_TTL_SEC = 2.0


def _shm_witness() -> tuple[int, int]:
    latest = 0
    total_size = 0
    for root in (*_SHARED_SHM_ROOTS, BALLAST_ROOT):
        try:
            st = root.stat()
            latest = max(latest, st.st_mtime_ns)
            total_size += st.st_size
        except OSError:
            pass
    return (latest, total_size)


def _allocated_bytes_scandir(path: Path) -> int:
    """Bytes resident under path — os.scandir walk (faster than Path.rglob)."""
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_blocks * 512
        except OSError:
            return 0
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_blocks * 512
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _shared_shm_alloc_bytes() -> tuple[int, int]:
    """Single walk of shared roots — productive + pinned (pinned adds ballast)."""
    global _SHM_ALLOC_CACHE, _SHM_CACHE_TS
    now = time.time()
    witness = _shm_witness()
    if (
        _SHM_ALLOC_CACHE
        and _SHM_ALLOC_CACHE[0] == witness
        and now - _SHM_CACHE_TS < _SHM_CACHE_TTL_SEC
    ):
        return _SHM_ALLOC_CACHE[1]
    shared = sum(_allocated_bytes_scandir(p) for p in _SHARED_SHM_ROOTS)
    ballast = _allocated_bytes_scandir(BALLAST_ROOT) if BALLAST_ROOT.exists() else 0
    result = (shared, shared + ballast)
    _SHM_ALLOC_CACHE = (witness, result)
    _SHM_CACHE_TS = now
    return result


def _allocated_bytes(path: Path) -> int:
    """Bytes actually resident (not sparse apparent size)."""
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_blocks * 512
        except OSError:
            return 0
    return _allocated_bytes_scandir(path)


def productive_shm_bytes() -> int:
    return _shared_shm_alloc_bytes()[0]


def productive_shm_gb() -> float:
    return productive_shm_bytes() / (1024**3)


def pinned_shm_bytes() -> int:
    """RAM pinned in /dev/shm (tmpfs) — not reclaimable like page cache."""
    return _shared_shm_alloc_bytes()[1]


def pinned_shm_gb() -> float:
    return pinned_shm_bytes() / (1024**3)


def mirror_hub_with_worktrees(*, log_fn: Callable[[str], None] = print) -> str | None:
    """Full hub + worktree pool in shm (largest automation footprint)."""
    dst = Path("/dev/shm/automation-hub-full")
    excludes_backup = set(hydrate.EXCLUDE)
    hydrate.EXCLUDE.discard(".worktrees")
    try:
        ok = hydrate._rsync(ROOT, dst, include_node_modules=False)
    finally:
        hydrate.EXCLUDE.clear()
        hydrate.EXCLUDE.update(excludes_backup)
    if ok:
        log_fn(f"hub full mirror → {dst}")
        return str(dst)
    return None


def mirror_worktrees_to_shm(*, log_fn: Callable[[str], None] = print) -> int:
    """Copy parallel worktree pool into /dev/shm for fast agent I/O."""
    wt_dir = ROOT / str(auto.CFG.get("parallel_worktree_dir") or ".worktrees")
    if not wt_dir.is_dir():
        return 0
    WORKTREE_SHM.mkdir(parents=True, exist_ok=True)
    n = 0
    for child in sorted(wt_dir.iterdir()):
        if not child.is_dir() or not child.name.startswith("peer"):
            continue
        dst = WORKTREE_SHM / child.name
        if hydrate._rsync(child, dst):
            n += 1
    log_fn(f"worktree shm mirrors: {n}")
    return n


def mirror_deps_to_shm(*, log_fn: Callable[[str], None] = print) -> list[str]:
    """Mirror repos that have node_modules into shm (heavy RAM use)."""
    done: list[str] = []
    for entry in fanout.load_candidates():
        repo = Path(str(entry.get("resolved_path") or ""))
        nm = repo / "node_modules"
        if not nm.is_dir():
            continue
        slug = "".join(c if c.isalnum() else "_" for c in str(entry.get("name") or repo.name))[:40]
        dst = Path("/dev/shm/automation-deps") / slug
        if hydrate._rsync(repo, dst, include_node_modules=True):
            done.append(str(dst))
            log_fn(f"deps mirror: {entry.get('name')} → {dst}")
    return done


def _read_tree(root: Path, *, max_file_bytes: int = 2_000_000) -> int:
    """Read files into Linux page cache; return bytes read."""
    total = 0
    if not root.is_dir():
        return 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(x in path.parts for x in (".git", "__pycache__")):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > max_file_bytes:
            continue
        try:
            total += len(path.read_bytes())
        except OSError:
            continue
    return total


def warm_paths_into_cache(*, log_fn: Callable[[str], None] = print) -> int:
    """Walk hub + synced repos and read files until reserve target approached."""
    if not should_page_warm():
        return 0
    roots = [ROOT, WORKTREE_SHM, Path("/dev/shm/automation-hub-full"), Path("/dev/shm/automation-deps")]
    for entry in fanout.load_candidates():
        p = Path(str(entry.get("resolved_path") or ""))
        if p.is_dir():
            roots.append(p)
    if hydrate.MIRROR_ROOT.is_dir():
        roots.extend(p for p in hydrate.MIRROR_ROOT.iterdir() if p.is_dir())

    total = 0
    reserve = target_reserve_gb()
    for root in roots:
        if avail_gb() <= reserve + 2:
            log_fn(f"page warm: stop at {avail_gb():.1f}GB avail (reserve {reserve}GB)")
            break
        got = _read_tree(root)
        total += got
        log_fn(f"page warm: {root.name} +{got // (1024 * 1024)}MB")
    return total


def pip_prefetch_hub(*, log_fn: Callable[[str], None] = print) -> bool:
    """Download common Python deps into shm pip cache (no install)."""
    cache = rac.cache_root() / "pip"
    cache.mkdir(parents=True, exist_ok=True)
    packages = _fill_cfg().get("pip_prefetch_packages")
    if not isinstance(packages, list) or not packages:
        packages = ["pytest", "unittest-xml-reporting", "requests", "pyyaml", "jsonschema"]
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "-q",
        "-d",
        str(cache / "wheels"),
        *[str(p) for p in packages],
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PIP_CACHE_DIR": str(cache)},
    )
    ok = proc.returncode == 0
    log_fn(f"pip prefetch: {'ok' if ok else 'partial'} ({len(packages)} packages)")
    return ok


def grow_ballast(
    *,
    log_fn: Callable[[str], None] = print,
    force: bool = False,
    target_gb: float | None = None,
) -> int:
    """Allocate tmpfs ballast chunks — pinned RAM that won't fall out of cache.

    ``force=True`` — ignore ballast_enabled/min_pinned config clobber (INFRA hold fill).
    """
    if not force and not ballast_enabled():
        return 0
    if target_gb is None:
        target_gb = min_pinned_shm_gb()
        if force and target_gb <= 0:
            # Hold-mode fill toward ~100GB when local.json flipped ballast off.
            try:
                import dgx_ram_priority as pri

                gap = max(0.0, pri.target_used_gb() - budget.footprint_gb())
                target_gb = min(32.0, max(8.0, pinned_shm_gb() + gap))
            except Exception:  # noqa: BLE001
                target_gb = max(8.0, pinned_shm_gb() + 8.0)
    if target_gb <= 0:
        return 0
    BALLAST_ROOT.mkdir(parents=True, exist_ok=True)
    # Drop sparse/hollow ballast from older runs.
    for path in BALLAST_ROOT.glob("ballast_*.bin"):
        try:
            if path.stat().st_blocks * 512 < path.stat().st_size // 2:
                path.unlink(missing_ok=True)
        except OSError:
            continue
    reserve = target_reserve_gb()
    chunk = ballast_chunk_bytes()
    if force:
        chunk = max(chunk, 512 * 1024 * 1024)
    added = 0
    idx = 0
    while pinned_shm_gb() < target_gb:
        if avail_gb() <= reserve + 2:
            log_fn(f"ballast: stop — avail {avail_gb():.1f}GB (reserve {reserve}GB)")
            break
        # System MemAvailable ≠ shm free — pin target can exceed tmpfs (ENOSPC).
        shm_free = _shm_free_gb()
        if shm_free <= 2.0:
            log_fn(f"ballast: stop — shm free {shm_free:.1f}GB")
            break
        path = BALLAST_ROOT / f"ballast_{idx:05d}.bin"
        idx += 1
        if path.is_file() and path.stat().st_size >= chunk:
            continue
        try:
            block = 64 * 1024 * 1024
            # Non-zero pages — some tmpfs paths can hollow pure zeros.
            page = b"\xff" * block
            with path.open("wb") as fh:
                written = 0
                while written < chunk:
                    step = min(block, chunk - written)
                    fh.write(page if step == block else page[:step])
                    written += step
            added += chunk
            log_fn(f"ballast: +{chunk // (1024 * 1024)}MB → {pinned_shm_gb():.1f}GB pinned shm")
        except OSError as exc:
            log_fn(f"ballast: stop — {exc}")
            break
    return added


def purge_ballast(*, log_fn: Callable[[str], None] = print) -> int:
    if not BALLAST_ROOT.is_dir():
        return 0
    freed = 0
    for path in BALLAST_ROOT.glob("ballast_*.bin"):
        try:
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            freed += size
        except OSError:
            continue
    if freed:
        log_fn(f"ballast: purged {freed // (1024 * 1024)}MB non-productive shm")
    return freed


def trim_ballast(*, log_fn: Callable[[str], None] = print) -> int:
    """Drop ballast when agents need headroom."""
    avail = avail_gb()
    if not ballast_enabled() or eff.should_trim_ballast(avail):
        return purge_ballast(log_fn=log_fn)
    reserve = target_reserve_gb()
    if avail_gb() > reserve + 4:
        return 0
    if not BALLAST_ROOT.is_dir():
        return 0
    freed = 0
    files = sorted(BALLAST_ROOT.glob("ballast_*.bin"), reverse=True)
    for path in files:
        if avail_gb() > reserve + 8:
            break
        try:
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            freed += size
            log_fn(f"ballast: freed {size // (1024 * 1024)}MB (avail {avail_gb():.1f}GB)")
        except OSError:
            continue
    return freed


def _load_fill_step_state() -> dict[str, Any]:
    try:
        if FILL_STEP_STATE.is_file():
            return json.loads(FILL_STEP_STATE.read_text())
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return {"idx": 0}


def _save_fill_step_state(state: dict[str, Any]) -> None:
    try:
        FILL_STEP_STATE.parent.mkdir(parents=True, exist_ok=True)
        FILL_STEP_STATE.write_text(json.dumps(state))
    except OSError:
        pass


def fill_one_step(*, log_fn: Callable[[str], None] = print) -> dict[str, Any]:
    """Single incremental pinned-shm step — one repo mirror OR one worktree (no bulk rsync)."""
    state = _load_fill_step_state()
    idx = int(state.get("idx") or 0)
    steps = ["mirror", "worktree", "pip"]
    phase = steps[idx % len(steps)]
    state["idx"] = idx + 1
    _save_fill_step_state(state)
    report: dict[str, Any] = {"phase": phase, "ok": False}
    if phase == "mirror":
        names = hydrate.mirror_names()
        name = names[idx % len(names)] if names else "Automation"
        for entry in fanout.load_candidates():
            if str(entry.get("name") or "") == name or name in str(entry.get("name") or ""):
                repo = Path(str(entry.get("resolved_path") or ""))
                if repo.is_dir():
                    slug = "".join(c if c.isalnum() else "_" for c in name)[:40]
                    dst = hydrate.MIRROR_ROOT / slug
                    ok = hydrate._rsync(repo, dst)
                    report["ok"] = ok
                    report["detail"] = f"mirror {name} → {dst}"
                    log_fn(f"fill step: mirror {name} → {dst}")
                    return report
        if name == "Automation" or "Automation" in name:
            dst = hydrate.MIRROR_ROOT / "Automation_Hub"
            ok = hydrate._rsync(ROOT, dst)
            report["ok"] = ok
            report["detail"] = f"mirror Automation → {dst}"
            log_fn(f"fill step: mirror Automation Hub → {dst}")
            return report
    elif phase == "worktree":
        wt_dir = ROOT / str(auto.CFG.get("parallel_worktree_dir") or ".worktrees")
        peers = sorted(p for p in wt_dir.glob("peer-*") if p.is_dir()) if wt_dir.is_dir() else []
        if peers:
            src = peers[idx % len(peers)]
            WORKTREE_SHM.mkdir(parents=True, exist_ok=True)
            dst = WORKTREE_SHM / src.name
            ok = hydrate._rsync(src, dst)
            report["ok"] = ok
            report["detail"] = f"worktree {src.name}"
            log_fn(f"fill step: worktree shm {src.name}")
            return report
    elif phase == "pip":
        report["ok"] = pip_prefetch_hub(log_fn=log_fn)
        report["detail"] = "pip prefetch"
        return report
    report["detail"] = "noop"
    return report


def _productive_top_up(*, log_fn: Callable[[str], None], light: bool = False) -> bool:
    """Grow pinned shm mirrors/caches only — no page cache, no ballast."""
    try:
        import dgx_ram_priority as priority

        if priority.enabled():
            step = fill_one_step(log_fn=log_fn)
            return bool(step.get("ok"))
    except ImportError:
        pass
    if not fill_pressure_ok():
        log_fn(f"productive: skip — avail {avail_gb():.1f}GB (need {eff.fill_headroom_gb():.0f}GB headroom)")
        return False
    productive_target = eff.effective_productive_target_gb()
    if productive_shm_gb() >= productive_target:
        return False
    if not light:
        if mirror_all_repos():
            hydrate.hydrate_mirrors(log_fn=log_fn, all_candidates=True)
        else:
            hydrate.hydrate_mirrors(log_fn=log_fn)
    if not light:
        mirror_hub_with_worktrees(log_fn=log_fn)
        if bool(_fill_cfg().get("mirror_worktrees", True)):
            mirror_worktrees_to_shm(log_fn=log_fn)
        mirror_deps_to_shm(log_fn=log_fn)
        pip_prefetch_hub(log_fn=log_fn)
    else:
        # light legacy path — one step only, never bulk hub+49 worktrees
        return bool(fill_one_step(log_fn=log_fn).get("ok"))
    return True


def maintain_ram_stable(*, log_fn: Callable[[str], None] = print) -> dict[str, Any]:
    """Stable RAM — pinned productive shm only; never page-warm or ballast."""
    if not fill_enabled():
        return {"enabled": False, "mode": "stable"}
    if not _try_acquire_fill_lock():
        return {"skipped": "fill lock held", "mode": "stable"}
    try:
        report: dict[str, Any] = {
            "mode": "stable",
            "avail_gb": round(avail_gb(), 1),
            "productive_shm_gb": round(productive_shm_gb(), 2),
            "pinned_shm_gb_before": round(pinned_shm_gb(), 2),
        }
        report["ballast_trimmed_bytes"] = purge_ballast(log_fn=log_fn)
        if fill_pressure_ok() and productive_shm_gb() < eff.effective_productive_target_gb():
            report["productive_fill"] = _productive_top_up(log_fn=log_fn, light=True)
        report["productive_shm_gb_after"] = round(productive_shm_gb(), 2)
        report["pinned_shm_gb_after"] = round(pinned_shm_gb(), 2)
        report["avail_gb_after"] = round(avail_gb(), 1)
        report["agents"] = eff.agent_count()
        report["pressure"] = budget.pressure_level(
            avail_gb=report["avail_gb_after"], total_gb=budget.mem_stats()["total_gb"]
        )
        return report
    finally:
        _release_fill_lock()


def maintain_ram(*, log_fn: Callable[[str], None] = print) -> dict[str, Any]:
    """Top-up productive shm only; purge non-productive ballast under load."""
    if eff.stable_mode():
        return maintain_ram_stable(log_fn=log_fn)
    if not _try_acquire_fill_lock():
        return {"skipped": "fill lock held"}
    try:
        return _maintain_ram_volatile(log_fn=log_fn)
    finally:
        _release_fill_lock()


def _maintain_ram_volatile(*, log_fn: Callable[[str], None] = print) -> dict[str, Any]:
    if not fill_enabled():
        return {"enabled": False}
    report: dict[str, Any] = {
        "avail_gb": round(avail_gb(), 1),
        "productive_shm_gb": round(productive_shm_gb(), 2),
        "pinned_shm_gb_before": round(pinned_shm_gb(), 2),
    }
    report["ballast_trimmed_bytes"] = trim_ballast(log_fn=log_fn)

    reserve = target_reserve_gb()
    headroom = avail_gb() - reserve
    productive_target = eff.effective_productive_target_gb()

    if productive_target > 0 and productive_shm_gb() < productive_target and headroom > 4:
        if mirror_all_repos():
            hydrate.hydrate_mirrors(log_fn=log_fn, all_candidates=True)
        else:
            hydrate.hydrate_mirrors(log_fn=log_fn)
        mirror_hub_with_worktrees(log_fn=log_fn)
        if bool(_fill_cfg().get("mirror_worktrees", True)):
            mirror_worktrees_to_shm(log_fn=log_fn)
        mirror_deps_to_shm(log_fn=log_fn)
        pip_prefetch_hub(log_fn=log_fn)
        report["productive_fill"] = True

    if ballast_enabled():
        target = min_pinned_shm_gb()
        if target > 0 and pinned_shm_gb() < target and headroom > 4:
            report["ballast_added_bytes"] = grow_ballast(log_fn=log_fn)
    elif headroom > 8:
        warmed = 0
        target_used = eff.target_used_gb()
        passes = 4 if budget.mem_stats()["used_gb"] < target_used - 4 else 2
        for _ in range(min(passes, max_warm_passes())):
            if avail_gb() <= reserve + 2:
                break
            warmed += warm_paths_into_cache(log_fn=log_fn)
        report["bytes_warmed"] = warmed

    report["productive_shm_gb_after"] = round(productive_shm_gb(), 2)
    report["pinned_shm_gb_after"] = round(pinned_shm_gb(), 2)
    report["avail_gb_after"] = round(avail_gb(), 1)
    report["agents"] = eff.agent_count()
    try:
        READ_LOG.write_text(
            f"maintain productive={report['productive_shm_gb_after']}GB "
            f"pinned={report['pinned_shm_gb_after']}GB avail={report['avail_gb_after']}GB "
            f"agents={report['agents']}\n"
        )
    except OSError:
        pass
    return report


def rebalance_ram(*, log_fn: Callable[[str], None] = print) -> dict[str, Any]:
    return maintain_ram(log_fn=log_fn)


def run_fill_cycle(*, log_fn: Callable[[str], None] = print) -> dict[str, Any]:
    if not fill_enabled():
        return {"enabled": False}
    if eff.stable_mode():
        return maintain_ram_stable(log_fn=log_fn)
    if not _try_acquire_fill_lock():
        return {"skipped": "fill lock held"}
    try:
        return _run_fill_cycle_volatile(log_fn=log_fn)
    finally:
        _release_fill_lock()


def _run_fill_cycle_volatile(*, log_fn: Callable[[str], None] = print) -> dict[str, Any]:
    report: dict[str, Any] = {
        "avail_gb_before": round(avail_gb(), 1),
        "pinned_shm_gb_before": round(pinned_shm_gb(), 2),
    }
    report["ballast_trimmed_bytes"] = trim_ballast(log_fn=log_fn)
    if mirror_all_repos():
        hydrate.hydrate_mirrors(log_fn=log_fn, all_candidates=True)
    else:
        hydrate.hydrate_mirrors(log_fn=log_fn)
    hydrate.warm_python_venvs(log_fn=log_fn)
    report["hub_full"] = mirror_hub_with_worktrees(log_fn=log_fn)
    if bool(_fill_cfg().get("mirror_worktrees", True)):
        report["worktrees"] = mirror_worktrees_to_shm(log_fn=log_fn)
    else:
        report["worktrees"] = 0
    report["deps_mirrors"] = mirror_deps_to_shm(log_fn=log_fn)
    report["pip_prefetch"] = pip_prefetch_hub(log_fn=log_fn)

    warmed = 0
    for _ in range(max_warm_passes()):
        if avail_gb() <= target_reserve_gb() + 2:
            break
        warmed += warm_paths_into_cache(log_fn=log_fn)
    report["bytes_warmed"] = warmed
    if ballast_enabled() and min_pinned_shm_gb() > 0:
        report["ballast_added_bytes"] = grow_ballast(log_fn=log_fn)
    report["pinned_shm_gb_after"] = round(pinned_shm_gb(), 2)
    report["avail_gb_after"] = round(avail_gb(), 1)
    report.update(hydrate.hydration_report())
    if WORKTREE_SHM.is_dir():
        try:
            out = subprocess.run(
                ["du", "-sb", str(WORKTREE_SHM)],
                capture_output=True,
                text=True,
                check=False,
            )
            report["worktree_shm_bytes"] = int(out.stdout.split()[0]) if out.returncode == 0 else 0
        except (ValueError, IndexError):
            report["worktree_shm_bytes"] = 0

    try:
        READ_LOG.write_text(
            f"fill pinned={report['pinned_shm_gb_after']}GB warmed={warmed} avail={report['avail_gb_after']}GB\n"
        )
    except OSError:
        pass
    return report
