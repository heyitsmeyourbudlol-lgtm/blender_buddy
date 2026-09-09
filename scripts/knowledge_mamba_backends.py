"""Pluggable Mamba encode backends — local / CLEAN only (NO PAY).

See ``notes/MAMBA_SCALE_PLAN.md`` Phase 1. Needle: ``OVERSEER_TOP10_NEXT_T10_10_2026_09_07``.

Backends implement ``encode(texts) -> vectors``. Heavy runtimes (llama.cpp, vLLM)
are stubbed until Phase 3/4; callers fall back to hash / transformers without
paid cloud APIs.
"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from typing import Any

import knowledge_index_config as kcfg

_TOKEN = re.compile(r"[a-zA-Z0-9_./-]{2,}")

# Local-only ids — never map to paid remote inference.
BACKEND_IDS = (
    "transformers-fp16",
    "transformers",
    "gguf-llamacpp",
    "vllm-nvfp4",
    "precomputed",
    "cascade",
    "hash",
)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text)]


def hash_embed(text: str, dim: int = 256) -> list[float]:
    vec = [0.0] * dim
    for token in _tokenize(text):
        idx = hash(token) % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class MambaBackend(ABC):
    """Abstract encode backend — RAM carve enforced by config, not paid APIs."""

    name: str = "abstract"
    local_only: bool = True

    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def encode(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def status(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "available": self.available(),
            "local_only": self.local_only,
            "paid_api": False,
            "budget_gb": kcfg.knowledge_mamba_budget_gb(),
            "max_ram_mb": kcfg.mamba_max_ram_mb(),
            "compression": kcfg.mamba_compression(),
            "teacher_model": kcfg.mamba_teacher_model(),
        }


class HashBackend(MambaBackend):
    """Always-on free fallback (no torch)."""

    name = "hash"

    def available(self) -> bool:
        return True

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [hash_embed(t) for t in texts]


class TransformersFp16Backend(MambaBackend):
    """Current transformers CPU/CUDA path via ``knowledge_mamba``."""

    name = "transformers-fp16"

    def available(self) -> bool:
        try:
            import knowledge_mamba as kmamba

            return bool(kmamba.configured())
        except Exception:
            return False

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            import knowledge_mamba as kmamba

            if kmamba._lazy_load():  # noqa: SLF001 — intentional bridge
                try:
                    return kmamba._encode_batch(texts)  # noqa: SLF001
                finally:
                    kmamba.unload()
        except Exception:
            pass
        return HashBackend().encode(texts)


class CascadeBackend(MambaBackend):
    """Student→teacher cascade id — encode uses student tier only."""

    name = "cascade"

    def available(self) -> bool:
        return kcfg.mamba_cascade_enabled() and TransformersFp16Backend().available()

    def encode(self, texts: list[str]) -> list[list[float]]:
        return TransformersFp16Backend().encode(texts)

    def status(self) -> dict[str, Any]:
        out = super().status()
        out["cascade_tiers"] = kcfg.cascade_tiers()
        return out


class GgufLlamacppBackend(MambaBackend):
    """Phase 3 stub — local llama.cpp only (not implemented yet)."""

    name = "gguf-llamacpp"

    def available(self) -> bool:
        return False

    def encode(self, texts: list[str]) -> list[list[float]]:
        return HashBackend().encode(texts)

    def status(self) -> dict[str, Any]:
        out = super().status()
        out["phase"] = 3
        out["implemented"] = False
        out["note"] = "local llama.cpp mmap path — see MAMBA_SCALE_PLAN Phase 3"
        return out


class VllmNvfp4Backend(MambaBackend):
    """Phase 4 stub — local vLLM Marlin on GB10 (not implemented yet)."""

    name = "vllm-nvfp4"

    def available(self) -> bool:
        return False

    def encode(self, texts: list[str]) -> list[list[float]]:
        return HashBackend().encode(texts)

    def status(self) -> dict[str, Any]:
        out = super().status()
        out["phase"] = 4
        out["implemented"] = False
        out["note"] = "local vLLM NVFP4 Marlin — see MAMBA_SCALE_PLAN Phase 4; NO PAY"
        return out


class PrecomputedBackend(MambaBackend):
    """Phase 2 stub — query encode + stored chunk vectors."""

    name = "precomputed"

    def available(self) -> bool:
        return False

    def encode(self, texts: list[str]) -> list[list[float]]:
        # Until L1 store lands, hash is a safe local stand-in.
        return HashBackend().encode(texts)

    def status(self) -> dict[str, Any]:
        out = super().status()
        out["phase"] = 2
        out["implemented"] = False
        out["note"] = "precomputed chunk vectors — see MAMBA_SCALE_PLAN Phase 2"
        return out


_ALIASES = {
    "transformers": "transformers-fp16",
    "hf": "transformers-fp16",
    "llamacpp": "gguf-llamacpp",
    "llama.cpp": "gguf-llamacpp",
    "gguf": "gguf-llamacpp",
    "vllm": "vllm-nvfp4",
    "nvfp4": "vllm-nvfp4",
}


def normalize_backend_id(name: str | None) -> str:
    raw = (name or kcfg.mamba_backend() or "transformers-fp16").strip().lower()
    return _ALIASES.get(raw, raw)


def get_backend(name: str | None = None) -> MambaBackend:
    bid = normalize_backend_id(name)
    mapping: dict[str, type[MambaBackend]] = {
        "transformers-fp16": TransformersFp16Backend,
        "cascade": CascadeBackend,
        "gguf-llamacpp": GgufLlamacppBackend,
        "vllm-nvfp4": VllmNvfp4Backend,
        "precomputed": PrecomputedBackend,
        "hash": HashBackend,
    }
    cls = mapping.get(bid, HashBackend)
    return cls()


def encode(texts: list[str], *, backend: str | None = None) -> list[list[float]]:
    """Public encode entry — respects configured backend, never paid APIs."""
    return get_backend(backend).encode(texts)


def carve_status() -> dict[str, Any]:
    """Brain carve + backend snapshot for ``peer mamba-status``."""
    backend = get_backend()
    agent_cap = None
    try:
        import dgx_ram_budget as budget

        agent_cap = budget.ram_max_used_gb()
    except Exception:
        agent_cap = None
    return {
        "knowledge_mamba_budget_gb": kcfg.knowledge_mamba_budget_gb(),
        "max_ram_mb": kcfg.mamba_max_ram_mb(),
        "backend": backend.name,
        "backend_available": backend.available(),
        "compression": kcfg.mamba_compression(),
        "teacher_model": kcfg.mamba_teacher_model(),
        "agent_ram_max_used_gb": agent_cap,
        "separate_from_agent_cap": True,
        "paid_api": False,
        "backend_status": backend.status(),
    }
