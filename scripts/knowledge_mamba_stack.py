"""Compression stack L0–L7 for Mamba cascade (see notes/MAMBA_SCALE_PLAN.md)."""

from __future__ import annotations

from typing import Any

import knowledge_index_config as kcfg

_LAYER_KEYS = (
    "l0_retrieve_less",
    "l1_precompute",
    "l2_weight_format",
    "l3_mmap",
    "l4_runtime",
    "l5_ssm_state",
    "l6_cascade",
    "l7_vector_quant",
)

_DEFAULT_WEIGHTS = {
    "student": "4bit",
    "teacher_1": "4bit",
    "teacher_2": "4bit",
}


def _stack_cfg() -> dict[str, Any]:
    raw = kcfg._cfg().get("compression_stack")
    if isinstance(raw, dict):
        return raw
    nested = kcfg._mamba_cfg().get("compression_stack")
    return nested if isinstance(nested, dict) else {}


def stack_enabled() -> bool:
    if _stack_cfg().get("enabled") is False:
        return False
    return True


def layer_enabled(layer: str) -> bool:
    if not stack_enabled():
        return False
    key = layer if layer.startswith("l") else f"l{layer}"
    raw = _stack_cfg().get(key)
    if raw is None:
        defaults = {
            "l0_retrieve_less": True,
            "l1_precompute": False,
            "l2_weight_format": True,
            "l3_mmap": True,
            "l4_runtime": True,
            "l5_ssm_state": True,
            "l6_cascade": True,
            "l7_vector_quant": True,
        }
        return bool(defaults.get(key, False))
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.lower() not in ("off", "false", "0", "none")
    return bool(raw)


def runtime_backend() -> str:
    if not layer_enabled("l4_runtime"):
        return "transformers"
    raw = _stack_cfg().get("l4_runtime")
    if isinstance(raw, str) and raw not in ("true", "false"):
        return raw.lower()
    return str(_stack_cfg().get("backend") or "transformers").lower()


def vector_quant() -> str:
    if not layer_enabled("l7_vector_quant"):
        return "none"
    raw = _stack_cfg().get("l7_vector_quant")
    if isinstance(raw, str) and raw not in ("true", "false"):
        return raw.lower()
    return "int8"


def tier_compression(role: str) -> str:
    """L2 weight format — per-tier compression from the stack."""
    key = f"{role}_compression"
    cascade = kcfg._cascade_cfg()
    if key in cascade:
        return str(cascade[key]).lower()
    if layer_enabled("l2_weight_format"):
        weights = _stack_cfg().get("weights")
        if isinstance(weights, dict) and role in weights:
            return str(weights[role]).lower()
    if kcfg.mamba_resident():
        return "4bit"
    defaults = {"student": "fp16", "teacher_1": "fp16", "teacher_2": "4bit"}
    return defaults.get(role, "fp16")


def use_mmap() -> bool:
    return layer_enabled("l3_mmap")


def use_cascade() -> bool:
    return layer_enabled("l6_cascade") and kcfg.mamba_cascade_enabled()


def precompute_embeddings() -> bool:
    return layer_enabled("l1_precompute")


def retrieve_candidate_k() -> int:
    """L0 — cap candidates before large-model forwards."""
    if layer_enabled("l0_retrieve_less"):
        try:
            return max(kcfg.retrieve_top_k(), int(_stack_cfg().get("rerank_candidate_k") or kcfg.retrieve_candidate_k()))
        except (TypeError, ValueError):
            pass
    return kcfg.retrieve_candidate_k()


def model_load_kwargs() -> dict[str, Any]:
    """Extra kwargs when loading models (mmap / low CPU mem)."""
    kwargs: dict[str, Any] = {}
    if use_mmap():
        kwargs["low_cpu_mem_usage"] = True
    return kwargs


def status() -> dict[str, Any]:
    layers = {key: layer_enabled(key) for key in _LAYER_KEYS}
    weights = {role: tier_compression(role) for role in ("student", "teacher_1", "teacher_2")}
    return {
        "enabled": stack_enabled(),
        "layers": layers,
        "weights": weights,
        "runtime": runtime_backend(),
        "vector_quant": vector_quant(),
        "mmap": use_mmap(),
        "precompute": precompute_embeddings(),
        "retrieve_candidate_k": retrieve_candidate_k(),
    }
