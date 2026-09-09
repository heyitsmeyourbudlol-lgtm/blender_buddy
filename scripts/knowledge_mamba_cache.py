"""Per-tier KV / SSM state cache — generous defaults, scales with repo growth."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import knowledge_index_config as kcfg
import project_automation as auto

TEXT_SUFFIXES = {".md", ".py", ".json", ".jsonl", ".txt", ".ts", ".tsx", ".js", ".sh", ".yaml", ".yml"}
_SKIP_PARTS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache"}
_WALK_FILE_CAP = 200_000


@dataclass
class _TierCache:
    role: str
    max_tokens: int
    peak_tokens: int = 0
    forward_passes: int = 0
    state_slots: dict[str, Any] = field(default_factory=dict)


def _kv_cfg() -> dict[str, Any]:
    raw = kcfg._cfg().get("kv_cache")
    if isinstance(raw, dict):
        return raw
    nested = kcfg._mamba_cfg().get("kv_cache")
    return nested if isinstance(nested, dict) else {}


def enabled() -> bool:
    if _kv_cfg().get("enabled") is False:
        return False
    return bool(_kv_cfg().get("enabled", True))


def dynamic() -> bool:
    if _kv_cfg().get("dynamic") is False:
        return False
    return bool(_kv_cfg().get("dynamic", True))


def reuse_state() -> bool:
    return bool(_kv_cfg().get("reuse_state", True))


def _base_tokens(role: str) -> int:
    defaults = {"student": 16384, "teacher_1": 32768, "teacher_2": 65536}
    bases = _kv_cfg().get("base_tokens")
    if isinstance(bases, dict) and role in bases:
        try:
            return max(512, int(bases[role]))
        except (TypeError, ValueError):
            pass
    return defaults.get(role, 8192)


def _max_tokens(role: str) -> int:
    defaults = {"student": 262144, "teacher_1": 524288, "teacher_2": 1048576}
    caps = _kv_cfg().get("max_tokens")
    if isinstance(caps, dict) and role in caps:
        try:
            return max(1024, int(caps[role]))
        except (TypeError, ValueError):
            pass
    return defaults.get(role, 131072)


def _min_tokens() -> int:
    try:
        return max(512, int(_kv_cfg().get("min_tokens") or 4096))
    except (TypeError, ValueError):
        return 4096


def _growth_cfg() -> tuple[int, int, int]:
    try:
        per_1k = max(0, int(_kv_cfg().get("tokens_per_1k_chunks") or 256))
    except (TypeError, ValueError):
        per_1k = 256
    try:
        per_gb_index = max(0, int(_kv_cfg().get("tokens_per_gb_index") or 512))
    except (TypeError, ValueError):
        per_gb_index = 512
    try:
        per_gb_repo = max(0, int(_kv_cfg().get("tokens_per_gb_repo") or 384))
    except (TypeError, ValueError):
        per_gb_repo = 384
    return per_1k, per_gb_index, per_gb_repo


def _index_stats() -> tuple[int, float]:
    db = kcfg.db_path()
    if not db.is_file():
        return 0, 0.0
    try:
        conn = sqlite3.connect(db, timeout=5.0)
        row = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
        chunk_count = int(row[0]) if row else 0
        row = conn.execute("SELECT COALESCE(SUM(bytes), 0) FROM chunks").fetchone()
        storage_gb = float(row[0] or 0) / (1024**3)
        conn.close()
        return chunk_count, storage_gb
    except (sqlite3.Error, OSError):
        return 0, 0.0


def _walk_repo_scale(roots: list[Path]) -> tuple[int, float]:
    files = 0
    total_bytes = 0
    seen: set[Path] = set()
    for root in roots:
        root = root.expanduser().resolve()
        if not root.is_dir() or root in seen:
            continue
        seen.add(root)
        try:
            for dirpath, dirnames, filenames in os.walk(root, topdown=True):
                dirnames[:] = [d for d in dirnames if d not in _SKIP_PARTS and not d.startswith(".")]
                for name in filenames:
                    path = Path(dirpath) / name
                    if path.suffix.lower() not in TEXT_SUFFIXES:
                        continue
                    try:
                        total_bytes += path.stat().st_size
                    except OSError:
                        continue
                    files += 1
                    if files >= _WALK_FILE_CAP:
                        return files, total_bytes / (1024**2)
        except OSError:
            continue
    return files, total_bytes / (1024**2)


def measure_repo_scale() -> dict[str, float]:
    chunk_count, storage_gb = _index_stats()
    roots = [auto.ROOT, *kcfg.extra_index_roots()]
    repo_files, repo_mb = _walk_repo_scale(roots)
    return {
        "chunk_count": float(chunk_count),
        "storage_gb": storage_gb,
        "repo_files": float(repo_files),
        "repo_mb": repo_mb,
        "repo_gb": repo_mb / 1024.0,
    }


def compute_max_tokens(role: str, scale: dict[str, float] | None = None) -> int:
    base = _base_tokens(role)
    if not dynamic():
        return min(base, _max_tokens(role))
    stats = scale if scale is not None else measure_repo_scale()
    per_1k, per_gb_index, per_gb_repo = _growth_cfg()
    growth = 0
    growth += int(stats.get("chunk_count", 0) // 1000) * per_1k
    growth += int(stats.get("storage_gb", 0)) * per_gb_index
    growth += int(stats.get("repo_gb", 0)) * per_gb_repo
    total = base + growth
    floor = _min_tokens()
    cap = _max_tokens(role)
    return max(floor, min(total, cap))


class MambaKVCacheManager:
    def __init__(self) -> None:
        self._tiers: dict[str, _TierCache] = {}
        self._scale_signature: tuple[float, ...] = ()

    def _signature(self, scale: dict[str, float]) -> tuple[float, ...]:
        return (
            scale.get("chunk_count", 0),
            scale.get("storage_gb", 0),
            scale.get("repo_files", 0),
            scale.get("repo_mb", 0),
        )

    def reconcile(self, scale: dict[str, float] | None = None) -> None:
        stats = scale if scale is not None else measure_repo_scale()
        sig = self._signature(stats)
        if sig == self._scale_signature and self._tiers:
            return
        self._scale_signature = sig
        for role in ("student", "teacher_1", "teacher_2"):
            tokens = compute_max_tokens(role, stats)
            if role in self._tiers:
                self._tiers[role].max_tokens = tokens
            else:
                self._tiers[role] = _TierCache(role=role, max_tokens=tokens)

    def max_tokens_for(self, role: str) -> int:
        if not enabled():
            return kcfg.mamba_max_length()
        tier = self._tiers.get(role)
        if tier is None:
            self.reconcile()
            tier = self._tiers.get(role)
        if tier is None:
            return compute_max_tokens(role)
        return tier.max_tokens

    def note_forward(self, role: str, token_count: int, *, state_key: str | None = None, state: Any = None) -> None:
        if not enabled():
            return
        self.reconcile()
        tier = self._tiers.setdefault(role, _TierCache(role=role, max_tokens=compute_max_tokens(role)))
        tier.forward_passes += 1
        tier.peak_tokens = max(tier.peak_tokens, token_count)
        if reuse_state() and state_key and state is not None:
            tier.state_slots[state_key] = state
            cap = max(8, int(_kv_cfg().get("state_slot_cap") or 64))
            if len(tier.state_slots) > cap:
                oldest = next(iter(tier.state_slots))
                del tier.state_slots[oldest]

    def get_state(self, role: str, state_key: str) -> Any | None:
        tier = self._tiers.get(role)
        if tier is None:
            return None
        return tier.state_slots.get(state_key)

    def clear(self) -> None:
        self._tiers.clear()
        self._scale_signature = ()

    def status(self) -> dict[str, Any]:
        self.reconcile()
        scale = measure_repo_scale()
        tiers = {
            role: {
                "max_tokens": cache.max_tokens,
                "peak_tokens": cache.peak_tokens,
                "forward_passes": cache.forward_passes,
                "state_slots": len(cache.state_slots),
            }
            for role, cache in self._tiers.items()
        }
        return {
            "enabled": enabled(),
            "dynamic": dynamic(),
            "reuse_state": reuse_state(),
            "repo_scale": scale,
            "tiers": tiers,
        }


_MANAGER = MambaKVCacheManager()


def manager() -> MambaKVCacheManager:
    return _MANAGER


def max_tokens_for(role: str) -> int:
    return _MANAGER.max_tokens_for(role)


def note_forward(role: str, token_count: int, *, state_key: str | None = None, state: Any = None) -> None:
    _MANAGER.note_forward(role, token_count, state_key=state_key, state=state)


def status() -> dict[str, Any]:
    return _MANAGER.status()
