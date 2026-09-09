"""RAM acceleration config — tmpfs caches + parallel verify on DGX."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import project_automation as auto

SHM_ROOT = Path("/dev/shm/automation-cache")


def _cfg() -> dict[str, Any]:
    raw = auto.CFG.get("ram_accel")
    return raw if isinstance(raw, dict) else {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


def verify_parallel() -> int:
    try:
        return max(1, int(_cfg().get("verify_parallel") or 6))
    except (TypeError, ValueError):
        return 6


def verify_interval_sec() -> float:
    try:
        return max(30.0, float(_cfg().get("verify_interval_sec") or 120))
    except (TypeError, ValueError):
        return 120.0


def cache_root() -> Path:
    custom = _cfg().get("cache_root")
    if custom:
        return Path(str(custom))
    return SHM_ROOT


def cache_subdirs() -> tuple[str, ...]:
    raw = _cfg().get("cache_dirs")
    if isinstance(raw, list) and raw:
        return tuple(str(x) for x in raw)
    return ("pip", "npm", "ccache", "pytest", "uv", "pnpm-store")


def warm_on_start() -> bool:
    return bool(_cfg().get("warm_repos_on_start", True))


def hydrate_on_start() -> bool:
    return bool(_cfg().get("hydrate_on_start", True))
