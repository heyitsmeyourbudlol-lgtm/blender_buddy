"""SSM state pool — fixed-size Mamba cache slots, chunked carry-forward encode."""

from __future__ import annotations

import copy
import os
import sqlite3
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import knowledge_index_config as kcfg
import knowledge_mamba_stack as kstack
import project_automation as auto

TEXT_SUFFIXES = {".md", ".py", ".json", ".jsonl", ".txt", ".ts", ".tsx", ".js", ".sh", ".yaml", ".yml"}
_SKIP_PARTS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache"}
_WALK_FILE_CAP = 200_000


@dataclass
class _TierPool:
    role: str
    max_slots: int
    slots: OrderedDict[str, Any] = field(default_factory=OrderedDict)
    slot_mb: OrderedDict[str, float] = field(default_factory=OrderedDict)
    stream_peak_tokens: int = 0
    forwards: int = 0


def _ssm_cfg() -> dict[str, Any]:
    raw = kcfg._cfg().get("ssm_state_pool")
    if isinstance(raw, dict):
        return raw
    legacy = kcfg._cfg().get("kv_cache")
    if isinstance(legacy, dict):
        return legacy
    nested = kcfg._mamba_cfg().get("ssm_state_pool")
    return nested if isinstance(nested, dict) else {}


def enabled() -> bool:
    if _ssm_cfg().get("enabled") is False:
        return False
    if not kstack.layer_enabled("l5_ssm_state"):
        return bool(_ssm_cfg().get("enabled"))
    return bool(_ssm_cfg().get("enabled", True))


def pair_encode_teachers() -> bool:
    return bool(_ssm_cfg().get("pair_encode_teachers", True))


def chunk_step_tokens(role: str) -> int:
    steps = _ssm_cfg().get("chunk_step_tokens")
    if isinstance(steps, dict) and role in steps:
        try:
            return max(8, int(steps[role]))
        except (TypeError, ValueError):
            pass
    defaults = {"student": 256, "teacher_1": 384, "teacher_2": 512}
    try:
        return max(32, int(_ssm_cfg().get("chunk_step") or defaults.get(role, 256)))
    except (TypeError, ValueError):
        return defaults.get(role, 256)


def _model_max_tokens(model: Any) -> int:
    config = getattr(model, "config", None)
    if config is None:
        return 2048
    for key in ("max_position_embeddings", "n_positions", "max_seq_len"):
        val = getattr(config, key, None)
        if val is not None:
            try:
                return max(512, int(val))
            except (TypeError, ValueError):
                continue
    return 2048


def _stream_multiplier() -> float:
    try:
        return max(1.0, float(_ssm_cfg().get("stream_multiplier") or 4.0))
    except (TypeError, ValueError):
        return 4.0


def max_stream_tokens(role: str, model: Any | None = None, scale: dict[str, float] | None = None) -> int:
    """Max tokens streamed via SSM carry — scales with repo, capped at model native max × multiplier."""
    model_cap = int(_model_max_tokens(model) * _stream_multiplier()) if model is not None else 8192
    base = int(_ssm_cfg().get("base_stream_tokens") or model_cap)
    if not bool(_ssm_cfg().get("dynamic", True)):
        return min(base, model_cap)
    stats = scale if scale is not None else measure_repo_scale()
    per_1k = int(_ssm_cfg().get("tokens_per_1k_chunks") or 128)
    per_gb = int(_ssm_cfg().get("tokens_per_gb_repo") or 256)
    growth = int(stats.get("chunk_count", 0) // 1000) * per_1k
    growth += int(stats.get("repo_gb", 0)) * per_gb
    cap = int(_ssm_cfg().get("max_stream_tokens") or model_cap)
    return max(chunk_step_tokens(role), min(base + growth, cap, model_cap))


def _base_slots(role: str) -> int:
    slots = _ssm_cfg().get("base_slots")
    if isinstance(slots, dict) and role in slots:
        try:
            return max(4, int(slots[role]))
        except (TypeError, ValueError):
            pass
    defaults = {"student": 256, "teacher_1": 192, "teacher_2": 128}
    return defaults.get(role, 128)


def _max_slots(role: str) -> int:
    caps = _ssm_cfg().get("max_slots")
    if isinstance(caps, dict) and role in caps:
        try:
            return max(8, int(caps[role]))
        except (TypeError, ValueError):
            pass
    defaults = {"student": 2048, "teacher_1": 1536, "teacher_2": 1024}
    return defaults.get(role, 1024)


def _slot_mb_estimate(role: str) -> float:
    estimates = _ssm_cfg().get("slot_mb_estimate")
    if isinstance(estimates, dict) and role in estimates:
        try:
            return max(0.5, float(estimates[role]))
        except (TypeError, ValueError):
            pass
    defaults = {"student": 6.0, "teacher_1": 28.0, "teacher_2": 72.0}
    return defaults.get(role, 16.0)


def max_pool_mb() -> float:
    raw = _ssm_cfg().get("ssm_max_pool_mb")
    if raw is None:
        return 4096.0
    try:
        return max(8.0, float(raw))
    except (TypeError, ValueError):
        return 4096.0


def compute_slot_budget(role: str, scale: dict[str, float] | None = None) -> int:
    base = _base_slots(role)
    if not bool(_ssm_cfg().get("dynamic", True)):
        return min(base, _max_slots(role))
    stats = scale if scale is not None else measure_repo_scale()
    per_1k = int(_ssm_cfg().get("slots_per_1k_chunks") or 16)
    per_gb = int(_ssm_cfg().get("slots_per_gb_repo") or 32)
    growth = int(stats.get("chunk_count", 0) // 1000) * per_1k
    growth += int(stats.get("repo_gb", 0)) * per_gb
    return max(8, min(base + growth, _max_slots(role)))


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


def supports_ssm_cache(model: Any) -> bool:
    if not enabled():
        return False
    config = getattr(model, "config", None)
    model_type = str(getattr(config, "model_type", "") or "").lower()
    return "mamba" in model_type or hasattr(model, "layers")


def clone_cache(cache: Any) -> Any:
    if cache is None:
        return None
    try:
        return copy.deepcopy(cache)
    except Exception:
        pass
    cloned = copy.copy(cache)
    for name in ("ssm_states", "conv_states", "state", "cache_params"):
        if hasattr(cache, name):
            val = getattr(cache, name)
            if val is None:
                continue
            try:
                import torch

                if isinstance(val, torch.Tensor):
                    setattr(cloned, name, val.clone())
                elif isinstance(val, (list, tuple)):
                    setattr(cloned, name, type(val)(t.clone() if hasattr(t, "clone") else t for t in val))
            except Exception:
                continue
    return cloned


def _new_cache(model: Any, *, batch_size: int = 1) -> Any:
    import torch

    device = next(model.parameters()).device
    dtype = next(model.parameters()).dtype
    config = model.config
    try:
        from transformers.cache_utils import MambaCache

        return MambaCache(config, batch_size, device=device, dtype=dtype)
    except Exception:
        return None


def _pool_hidden(hidden: Any, mask: Any) -> list[float]:
    import torch

    if hidden is None:
        return []
    if mask is not None:
        pooled = (hidden * mask.unsqueeze(-1)).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
    else:
        pooled = hidden.mean(dim=1)
    row = pooled[0].detach().float().cpu()
    vec = row.tolist()
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def _forward_chunk(
    model: Any,
    input_ids: Any,
    attention_mask: Any,
    *,
    cache_params: Any,
) -> tuple[Any, Any, Any]:
    kwargs: dict[str, Any] = {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "use_cache": True,
        "return_dict": True,
    }
    if cache_params is not None:
        kwargs["cache_params"] = cache_params
    out = model(**kwargs)
    hidden = getattr(out, "last_hidden_state", None)
    if hidden is None and hasattr(out, "hidden_states") and out.hidden_states:
        hidden = out.hidden_states[-1]
    new_cache = getattr(out, "cache_params", cache_params)
    return hidden, new_cache, out


def stream_encode_ids(
    model: Any,
    token_ids: list[int],
    *,
    role: str,
    initial_cache: Any = None,
) -> tuple[list[float], Any, int]:
    if not token_ids:
        return [], initial_cache, 0
    step = chunk_step_tokens(role)
    limit = max_stream_tokens(role, model)
    ids = token_ids[:limit]
    cache_params = initial_cache
    hidden = None
    mask = None
    seen = 0
    pos = 0
    while pos < len(ids):
        chunk = ids[pos : pos + step]
        pos += len(chunk)
        seen += len(chunk)
        try:
            import torch

            device = next(model.parameters()).device
            input_ids = torch.tensor([chunk], device=device, dtype=torch.long)
            attention_mask = torch.ones_like(input_ids)
        except (ImportError, StopIteration):
            input_ids = [chunk]
            attention_mask = [1] * len(chunk)
        hidden, cache_params, _ = _forward_chunk(
            model,
            input_ids,
            attention_mask,
            cache_params=cache_params,
        )
        mask = attention_mask
    vec = _pool_hidden(hidden, mask)
    return vec, cache_params, seen


def stream_encode_text(
    model: Any,
    tokenizer: Any,
    text: str,
    *,
    role: str,
    initial_cache: Any = None,
    cache_key: str | None = None,
    pool: SSMStatePool | None = None,
) -> list[float]:
    if not text.strip():
        return []
    if not supports_ssm_cache(model):
        return []
    if cache_key and pool is not None:
        cached = pool.get_vector(cache_key)
        if cached is not None:
            return cached
    token_ids = tokenizer.encode(text, add_special_tokens=True)
    vec, final_cache, _ = stream_encode_ids(
        model,
        token_ids,
        role=role,
        initial_cache=initial_cache,
    )
    if cache_key and pool is not None and vec:
        pool.put_vector(cache_key, vec)
        if final_cache is not None:
            pool.put_state(cache_key, final_cache)
    return vec


def stream_encode_pair(
    model: Any,
    tokenizer: Any,
    query: str,
    doc: str,
    *,
    role: str,
    pool: SSMStatePool | None = None,
) -> list[float]:
    """Query-prefix SSM stream: carry state from query into doc tokens."""
    if not supports_ssm_cache(model):
        return []
    prefix_key = f"{role}:prefix:{hash(query) & 0xFFFFFFFF:08x}"
    prefix_cache = pool.get_state(prefix_key) if pool is not None else None
    if prefix_cache is None and query.strip():
        _, prefix_cache, _ = stream_encode_ids(
            model,
            tokenizer.encode(query, add_special_tokens=True),
            role=role,
            initial_cache=None,
        )
        if pool is not None and prefix_cache is not None:
            pool.put_state(prefix_key, prefix_cache)
    doc_ids = tokenizer.encode(doc, add_special_tokens=False)
    vec, _, _ = stream_encode_ids(
        model,
        doc_ids,
        role=role,
        initial_cache=clone_cache(prefix_cache) if prefix_cache is not None else None,
    )
    return vec


class SSMStatePool:
    def __init__(self) -> None:
        self._tiers: dict[str, _TierPool] = {}
        self._scale_signature: tuple[float, ...] = ()

    def _signature(self, scale: dict[str, float]) -> tuple[float, ...]:
        return (
            scale.get("chunk_count", 0),
            scale.get("storage_gb", 0),
            scale.get("repo_files", 0),
            scale.get("repo_gb", 0),
        )

    def reconcile(self, scale: dict[str, float] | None = None) -> None:
        stats = scale if scale is not None else measure_repo_scale()
        sig = self._signature(stats)
        if sig == self._scale_signature and self._tiers:
            return
        self._scale_signature = sig
        for role in ("student", "teacher_1", "teacher_2"):
            budget = compute_slot_budget(role, stats)
            if role in self._tiers:
                self._tiers[role].max_slots = budget
            else:
                self._tiers[role] = _TierPool(role=role, max_slots=budget)

    def _tier(self, role: str) -> _TierPool:
        self.reconcile()
        return self._tiers.setdefault(role, _TierPool(role=role, max_slots=compute_slot_budget(role)))

    def _total_pool_mb(self) -> float:
        return sum(
            sum(tier.slot_mb.values())
            for tier in self._tiers.values()
        )

    def _evict_lru_until(self, *, need_mb: float) -> None:
        cap = max_pool_mb()
        while self._tiers and self._total_pool_mb() + need_mb > cap:
            evicted = False
            for tier in self._tiers.values():
                if not tier.slots:
                    continue
                old_key, _ = tier.slots.popitem(last=False)
                tier.slot_mb.pop(old_key, None)
                evicted = True
                break
            if not evicted:
                break

    def put_state(self, key: str, state: Any, *, role: str = "student") -> None:
        tier = self._tier(role)
        est_mb = _slot_mb_estimate(role)
        if key in tier.slots:
            tier.slots.pop(key, None)
            tier.slot_mb.pop(key, None)
        self._evict_lru_until(need_mb=est_mb)
        while len(tier.slots) >= tier.max_slots:
            old_key, _ = tier.slots.popitem(last=False)
            tier.slot_mb.pop(old_key, None)
        tier.slots[key] = state
        tier.slot_mb[key] = est_mb
        tier.slots.move_to_end(key)

    def get_state(self, key: str, *, role: str = "student") -> Any | None:
        tier = self._tier(role)
        state = tier.slots.get(key)
        if state is not None:
            tier.slots.move_to_end(key)
        return clone_cache(state)

    def put_vector(self, key: str, vector: list[float], *, role: str = "student") -> None:
        self.put_state(f"vec:{key}", vector, role=role)

    def get_vector(self, key: str, *, role: str = "student") -> list[float] | None:
        val = self.get_state(f"vec:{key}", role=role)
        return val if isinstance(val, list) else None

    def note_forward(self, role: str, tokens: int) -> None:
        tier = self._tier(role)
        tier.forwards += 1
        tier.stream_peak_tokens = max(tier.stream_peak_tokens, tokens)

    def clear(self) -> None:
        self._tiers.clear()
        self._scale_signature = ()

    def status(self) -> dict[str, Any]:
        self.reconcile()
        scale = measure_repo_scale()
        tiers = {
            role: {
                "max_slots": pool.max_slots,
                "used_slots": len(pool.slots),
                "pool_mb": round(sum(pool.slot_mb.values()), 1),
                "forwards": pool.forwards,
                "stream_peak_tokens": pool.stream_peak_tokens,
                "chunk_step": chunk_step_tokens(role),
                "slot_mb_estimate": _slot_mb_estimate(role),
            }
            for role, pool in self._tiers.items()
        }
        return {
            "enabled": enabled(),
            "dynamic": bool(_ssm_cfg().get("dynamic", True)),
            "pair_encode_teachers": pair_encode_teachers(),
            "ssm_max_pool_mb": max_pool_mb(),
            "pool_mb_used": round(self._total_pool_mb(), 1),
            "repo_scale": scale,
            "tiers": tiers,
        }


_MANAGER = SSMStatePool()


def manager() -> SSMStatePool:
    return _MANAGER


def status() -> dict[str, Any]:
    return _MANAGER.status()
