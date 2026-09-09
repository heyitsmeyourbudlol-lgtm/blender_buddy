"""Hydrate /dev/shm with repo mirrors and Python venvs — burns spare RAM for speed."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import dgx_ram_accel_config as rac  # noqa: E402
import factory_fanout as fanout  # noqa: E402

MIRROR_ROOT = Path("/dev/shm/automation-mirror")
VENV_ROOT = Path("/dev/shm/automation-cache/venvs")

EXCLUDE = {".git", "node_modules", ".next", "dist", "build", "__pycache__", ".worktrees"}


def _cfg() -> dict[str, Any]:
    return rac._cfg()


def mirror_enabled() -> bool:
    return bool(_cfg().get("mirror_repos", True))


def venv_enabled() -> bool:
    return bool(_cfg().get("warm_python_venvs", True))


def mirror_names() -> list[str]:
    raw = _cfg().get("mirror_names")
    if isinstance(raw, list) and raw:
        return [str(x) for x in raw]
    return ["Automation", "CPT", "CaaS", "ram", "Doc2Api"]


def _rsync(src: Path, dst: Path, *, include_node_modules: bool = False) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    excludes = set(EXCLUDE)
    if include_node_modules:
        excludes.discard("node_modules")
    cmd = [
        "rsync",
        "-a",
        "--delete",
        *[f"--exclude={x}" for x in excludes],
        f"{src}/",
        f"{dst}/",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return proc.returncode == 0


def hydrate_mirrors(*, log_fn: Callable[[str], None] = print, all_candidates: bool = False) -> list[str]:
    """Copy hot repos into /dev/shm for RAM-speed reads/writes."""
    if not mirror_enabled():
        return []
    MIRROR_ROOT.mkdir(parents=True, exist_ok=True)
    done: list[str] = []
    candidates = {str(e.get("name")): e for e in fanout.load_candidates()}
    candidates["Automation Hub"] = {"name": "Automation Hub", "resolved_path": str(ROOT)}

    names = list(candidates.keys()) if all_candidates else mirror_names()
    for name in names:
        entry = candidates.get(name)
        if not entry:
            # try path suffix match
            for e in candidates.values():
                if name.lower() in str(e.get("resolved_path", "")).lower():
                    entry = e
                    break
        if not entry:
            continue
        src = Path(str(entry.get("resolved_path") or ""))
        if not src.is_dir():
            continue
        slug = name.replace(" ", "_").replace("(", "").replace(")", "")
        dst = MIRROR_ROOT / slug
        if _rsync(src, dst):
            done.append(str(dst))
            log_fn(f"mirror: {name} → {dst}")
        else:
            log_fn(f"mirror: {name} failed")
    return done


def _python_warm_targets() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = [( "Automation", ROOT)]
    for entry in fanout.load_candidates():
        repo = Path(str(entry.get("resolved_path") or ""))
        if not repo.is_dir():
            continue
        if (repo / "pyproject.toml").is_file() or (repo / "requirements.txt").is_file():
            out.append((str(entry.get("name") or repo.name), repo))
    return out


def warm_python_venvs(*, log_fn: Callable[[str], None] = print) -> list[str]:
    """Create per-repo venvs in shm and pip-install deps."""
    if not venv_enabled():
        return []
    VENV_ROOT.mkdir(parents=True, exist_ok=True)
    ready: list[str] = []
    for name, repo in _python_warm_targets():
        slug = "".join(c if c.isalnum() else "_" for c in name)[:40]
        venv = VENV_ROOT / slug
        if not venv.is_dir():
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=False)
        pip = venv / "bin" / "pip"
        if not pip.is_file():
            continue
        reqs: list[str] = []
        req_file = repo / "requirements.txt"
        if req_file.is_file():
            reqs.extend(["-r", str(req_file)])
        if (repo / "pyproject.toml").is_file():
            subprocess.run(
                [str(pip), "install", "-q", "-e", str(repo)],
                capture_output=True,
                check=False,
                env={**os.environ, "PIP_CACHE_DIR": str(rac.cache_root() / "pip")},
            )
        elif reqs:
            subprocess.run(
                [str(pip), "install", "-q", *reqs],
                capture_output=True,
                check=False,
                env={**os.environ, "PIP_CACHE_DIR": str(rac.cache_root() / "pip")},
            )
        ready.append(str(venv))
        log_fn(f"venv: {name} → {venv}")
    return ready


def mirror_path_for_repo(repo: Path) -> Path | None:
    """Return shm mirror if hydrated."""
    if not MIRROR_ROOT.is_dir():
        return None
    name = repo.name
    for child in MIRROR_ROOT.iterdir():
        if child.is_dir() and name.lower() in child.name.lower():
            return child
    return None


def hydration_report() -> dict[str, Any]:
    mirrors = list(MIRROR_ROOT.iterdir()) if MIRROR_ROOT.is_dir() else []
    venvs = list(VENV_ROOT.iterdir()) if VENV_ROOT.is_dir() else []
    def du(p: Path) -> int:
        try:
            out = subprocess.run(
                ["du", "-sb", str(p)], capture_output=True, text=True, check=False
            )
            return int(out.stdout.split()[0]) if out.returncode == 0 else 0
        except (ValueError, IndexError, OSError):
            return 0

    return {
        "mirror_root": str(MIRROR_ROOT),
        "mirror_count": len(mirrors),
        "mirror_bytes": sum(du(p) for p in mirrors if p.is_dir()),
        "venv_count": len(venvs),
        "venv_bytes": sum(du(p) for p in venvs if p.is_dir()),
        "shm_cache_bytes": du(rac.cache_root()),
        "ballast_bytes": du(Path("/dev/shm/automation-ballast")),
    }
