"""Knowledge index config — 2TB corpus + hybrid retrieval on DGX."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import project_automation as auto

DEFAULT_DATA_ROOT = Path("/data/knowledge-index")
FALLBACK_DATA_ROOT = auto.CONFIG_DIR / "knowledge-index"
DEFAULT_HOT_CACHE = Path("/dev/shm/automation-cache/knowledge")


def _cfg() -> dict[str, Any]:
    raw = auto.CFG.get("knowledge_index")
    return raw if isinstance(raw, dict) else {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", False))


def data_root() -> Path:
    custom = _cfg().get("data_root") or os.environ.get("KNOWLEDGE_INDEX_DATA_ROOT")
    if custom:
        path = Path(str(custom)).expanduser()
    elif DEFAULT_DATA_ROOT.is_dir():
        path = DEFAULT_DATA_ROOT
    else:
        path = DEFAULT_DATA_ROOT
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
        return path
    except OSError:
        pass
    fallback = FALLBACK_DATA_ROOT
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def hot_cache_root() -> Path:
    custom = _cfg().get("hot_cache_root")
    if custom:
        return Path(str(custom)).expanduser()
    return DEFAULT_HOT_CACHE


def db_path() -> Path:
    return data_root() / "index.sqlite3"


def corpus_root() -> Path:
    return data_root() / "corpus"


def index_interval_sec() -> float:
    try:
        return max(30.0, float(_cfg().get("index_interval_sec") or 300))
    except (TypeError, ValueError):
        return 300.0


def retrieve_top_k() -> int:
    try:
        return max(1, int(_cfg().get("retrieve_top_k") or 8))
    except (TypeError, ValueError):
        return 8


def retrieve_candidate_k() -> int:
    try:
        return max(retrieve_top_k(), int(_cfg().get("retrieve_candidate_k") or 48))
    except (TypeError, ValueError):
        return 48


def max_inject_chars() -> int:
    try:
        return max(500, int(_cfg().get("max_inject_chars") or 6000))
    except (TypeError, ValueError):
        return 6000


def max_storage_gb() -> float:
    try:
        return max(1.0, float(_cfg().get("max_storage_gb") or 2048))
    except (TypeError, ValueError):
        return 2048.0


def chunk_chars() -> int:
    try:
        return max(400, int(_cfg().get("chunk_chars") or 1800))
    except (TypeError, ValueError):
        return 1800


def chunk_overlap() -> int:
    try:
        return max(0, int(_cfg().get("chunk_overlap") or 200))
    except (TypeError, ValueError):
        return 200


def sources() -> tuple[str, ...]:
    raw = _cfg().get("sources")
    if isinstance(raw, list) and raw:
        return tuple(str(s) for s in raw)
    return (
        "transcripts",
        "notes",
        "scripts",
        "debrief",
        "glink",
        "work_queue",
        "registry",
        "library",
    )


DEFAULT_MAMBA_MODEL = "state-spaces/mamba-130m-hf"
DEFAULT_BRAIN_BUDGET_GB = 12.0
DEFAULT_BACKEND = "transformers-fp16"


def _mamba_cfg() -> dict[str, Any]:
    raw = _cfg().get("mamba")
    return raw if isinstance(raw, dict) else {}


def mamba_model() -> str | None:
    env = os.environ.get("KNOWLEDGE_MAMBA_MODEL", "").strip()
    if env:
        return env
    raw = _cfg().get("mamba_model")
    if not raw:
        return str(_mamba_cfg().get("default_model") or DEFAULT_MAMBA_MODEL)
    text = str(raw).strip()
    if text.startswith("env:"):
        return os.environ.get(text[4:].strip(), "").strip() or str(
            _mamba_cfg().get("default_model") or DEFAULT_MAMBA_MODEL
        )
    if text.lower() in {"none", "off", "false", "0"}:
        return None
    return text


DEFAULT_STUDENT = "state-spaces/mamba-130m-hf"
DEFAULT_TEACHER_1 = "state-spaces/mamba-790m-hf"
DEFAULT_TEACHER_2 = "state-spaces/mamba-2.8b-hf"


def knowledge_mamba_budget_gb() -> float:
    """Brain RAM carve (GB) — separate from agent ``ram_max_used_gb``.

    Needle: ``OVERSEER_TOP10_NEXT_T10_10_2026_09_07`` · plan: ``notes/MAMBA_SCALE_PLAN.md``.
    """
    env = os.environ.get("KNOWLEDGE_MAMBA_BUDGET_GB", "").strip()
    if env:
        try:
            return max(0.25, float(env))
        except ValueError:
            pass
    for raw in (
        _cfg().get("knowledge_mamba_budget_gb"),
        _mamba_cfg().get("budget_gb"),
        _cfg().get("budget_gb"),
    ):
        if raw is None:
            continue
        try:
            return max(0.25, float(raw))
        except (TypeError, ValueError):
            continue
    return DEFAULT_BRAIN_BUDGET_GB


def mamba_backend() -> str:
    """Pluggable encode backend id (local/NO PAY only)."""
    env = os.environ.get("KNOWLEDGE_MAMBA_BACKEND", "").strip()
    if env:
        return env.lower()
    for raw in (
        _cfg().get("mamba_backend"),
        _mamba_cfg().get("backend"),
        _cfg().get("backend"),
    ):
        if raw:
            return str(raw).strip().lower()
    # Compression stack L4 may name a runtime (transformers / gguf / …).
    stack = _cfg().get("compression_stack")
    if not isinstance(stack, dict):
        stack = _mamba_cfg().get("compression_stack")
    if isinstance(stack, dict):
        runtime = stack.get("l4_runtime") or stack.get("backend")
        if isinstance(runtime, str) and runtime.lower() not in ("true", "false", "off", "0"):
            text = runtime.strip().lower()
            if text in ("transformers", "hf"):
                return "transformers-fp16"
            return text
    return DEFAULT_BACKEND


def mamba_compression() -> str:
    """Default weight compression for the active backend / teacher path."""
    env = os.environ.get("KNOWLEDGE_MAMBA_COMPRESSION", "").strip()
    if env:
        return env.lower()
    for raw in (
        _cfg().get("mamba_compression"),
        _mamba_cfg().get("compression"),
        _mamba_cfg().get("teacher_compression"),
        _cascade_cfg().get("teacher_2_compression"),
    ):
        if raw:
            return str(raw).strip().lower()
    return str(mamba_dtype() or "float16").lower()


def mamba_teacher_model() -> str:
    env = os.environ.get("KNOWLEDGE_MAMBA_TEACHER_MODEL", "").strip()
    if env:
        return env
    for raw in (
        _cfg().get("mamba_teacher_model"),
        _mamba_cfg().get("teacher_model"),
        _cascade_cfg().get("teacher_2"),
    ):
        if raw:
            return str(raw).strip()
    return cascade_teacher_2_model()


def mamba_max_ram_mb() -> int:
    """Per-load RAM ceiling — never exceeds the brain carve (``knowledge_mamba_budget_gb``)."""
    budget_mb = max(128, int(knowledge_mamba_budget_gb() * 1024))
    explicit = None
    try:
        raw = _cfg().get("mamba_max_ram_mb")
        if raw is None:
            raw = _mamba_cfg().get("max_ram_mb")
        if raw is not None:
            explicit = max(128, int(raw))
    except (TypeError, ValueError):
        explicit = None
    if explicit is None:
        return budget_mb
    return min(explicit, budget_mb)


def mamba_cascade_enabled() -> bool:
    mode = str(_cfg().get("mamba_mode") or _mamba_cfg().get("mode") or "cascade").lower()
    return mode == "cascade"


def _cascade_cfg() -> dict[str, Any]:
    raw = _cfg().get("cascade")
    if isinstance(raw, dict):
        return raw
    return _mamba_cfg().get("cascade") if isinstance(_mamba_cfg().get("cascade"), dict) else {}


def cascade_student_model() -> str:
    return str(_cascade_cfg().get("student") or DEFAULT_STUDENT)


def cascade_teacher_1_model() -> str:
    return str(_cascade_cfg().get("teacher_1") or DEFAULT_TEACHER_1)


def cascade_teacher_2_model() -> str:
    return str(_cascade_cfg().get("teacher_2") or DEFAULT_TEACHER_2)


def cascade_compression(role: str) -> str:
    key = f"{role}_compression"
    defaults = {"student": "fp16", "teacher_1": "fp16", "teacher_2": "4bit"}
    return str(_cascade_cfg().get(key) or defaults.get(role, "fp16")).lower()


def cascade_top_k(role: str) -> int:
    key = f"{role}_top_k"
    defaults = {"student": 48, "teacher_1": 16, "teacher_2": 8}
    try:
        return max(1, int(_cascade_cfg().get(key) or defaults.get(role, 8)))
    except (TypeError, ValueError):
        return defaults.get(role, 8)


def cascade_tiers() -> list[dict[str, Any]]:
    return [
        {"role": "student", "model": cascade_student_model(), "compression": cascade_compression("student"), "top_k": cascade_top_k("student")},
        {"role": "teacher_1", "model": cascade_teacher_1_model(), "compression": cascade_compression("teacher_1"), "top_k": cascade_top_k("teacher_1")},
        {"role": "teacher_2", "model": cascade_teacher_2_model(), "compression": cascade_compression("teacher_2"), "top_k": cascade_top_k("teacher_2")},
    ]


def estimated_model_weight_mb(model_id: str, *, compression: str = "fp16") -> int:
    """Rough weight RAM from model name and compression."""
    lower = model_id.lower()
    base = 512
    for token, mb in (
        ("130m", 260),
        ("160m", 320),
        ("370m", 740),
        ("390m", 780),
        ("790m", 1580),
        ("1.4b", 2800),
        ("2.8b", 5600),
        ("2.7b", 5400),
    ):
        if token in lower:
            base = mb
            break
    comp = compression.lower()
    if comp in ("4bit", "q4", "int4", "nvfp4", "fp4"):
        return max(128, base // 4)
    if comp in ("8bit", "q8", "int8"):
        return max(128, base // 2)
    return base


def mamba_dtype() -> str:
    return str(_cfg().get("mamba_dtype") or _mamba_cfg().get("dtype") or "float16").lower()


def mamba_device() -> str:
    """CPU cascade loads one tier at a time inside the RAM budget."""
    return str(_cfg().get("mamba_device") or _mamba_cfg().get("device") or "cpu").lower()


def mamba_max_length() -> int:
    try:
        return max(32, int(_cfg().get("mamba_max_length") or _mamba_cfg().get("max_length") or 128))
    except (TypeError, ValueError):
        return 128


def mamba_batch_size() -> int:
    try:
        return max(1, int(_cfg().get("mamba_batch_size") or _mamba_cfg().get("batch_size") or 16))
    except (TypeError, ValueError):
        return 16


def mamba_idle_unload_sec() -> float:
    try:
        return max(0.0, float(_cfg().get("mamba_idle_unload_sec") or _mamba_cfg().get("idle_unload_sec") or 300))
    except (TypeError, ValueError):
        return 300.0


def mamba_enabled() -> bool:
    if _cfg().get("mamba_enabled") is False:
        return False
    return bool(mamba_model())


def hybrid_sparse_weight() -> float:
    try:
        return float(_cfg().get("hybrid_sparse_weight") or 0.55)
    except (TypeError, ValueError):
        return 0.55


def library_corpus_paths() -> list[Path]:
    raw = _cfg().get("library_corpus_paths")
    if not isinstance(raw, list):
        return []
    out: list[Path] = []
    for item in raw:
        path = Path(str(item)).expanduser()
        if path.is_dir():
            out.append(path)
    return out


def extra_index_roots() -> list[Path]:
    raw = _cfg().get("extra_index_roots")
    if not isinstance(raw, list):
        return []
    out: list[Path] = []
    for item in raw:
        path = Path(str(item)).expanduser()
        if path.is_dir():
            out.append(path)
    return out
