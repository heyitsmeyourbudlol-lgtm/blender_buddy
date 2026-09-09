"""Skip expensive drift sync when queue/context unchanged (DGX fast path)."""

from __future__ import annotations

import zlib
import json
import time
from pathlib import Path

import automation_config as cfg_mod

DEFAULT_STATE = Path("/dev/shm/automation-cache/state")


def _state_dir() -> Path:
    custom = cfg_mod.CFG.get("automation_cache_dir")
    if custom:
        return Path(str(custom)).expanduser()
    return DEFAULT_STATE


def _fp_path() -> Path:
    return _state_dir() / "plan_fingerprint.json"


def drift_skip_ttl_sec() -> float:
    try:
        return max(15.0, float(cfg_mod.CFG.get("drift_sync_skip_ttl_sec") or 90))
    except (TypeError, ValueError):
        return 90.0


def _fingerprint(context_md: str, work_md: str) -> str:
    # COMPRESSION_ZLIB_PLAN_DRIFT_FP_2026_09_04 — zlib adler+crc (16 hex)
    # keeps peer_orchestrate import path libcrypto-free (~5.7MB r-xp).
    blob = f"{len(context_md)}:{hash(context_md)}:{len(work_md)}:{hash(work_md)}"
    raw = blob.encode()
    return f"{zlib.adler32(raw) & 0xffffffff:08x}{zlib.crc32(raw) & 0xffffffff:08x}"


def should_skip_drift_sync(*, context_md: str, work_md: str) -> bool:
    fp = _fingerprint(context_md, work_md)
    now = time.time()
    try:
        path = _fp_path()
        if path.is_file():
            data = json.loads(path.read_text())
            if (
                data.get("fp") == fp
                and now - float(data.get("drift_ts") or 0) < drift_skip_ttl_sec()
            ):
                return True
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        pass
    return False


def record_drift_sync(*, context_md: str, work_md: str) -> None:
    try:
        state = _state_dir()
        state.mkdir(parents=True, exist_ok=True)
        _fp_path().write_text(
            json.dumps(
                {
                    "fp": _fingerprint(context_md, work_md),
                    "drift_ts": time.time(),
                }
            )
        )
    except OSError:
        pass
