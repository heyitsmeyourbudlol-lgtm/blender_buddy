"""Mamba student→teacher cascade reranker — 130m → 790m → 2.8b within RAM budget."""

from __future__ import annotations

import gc
import math
import re
import sys
import time
from typing import Any, Callable

import knowledge_index_config as kcfg

_TOKEN = re.compile(r"[a-zA-Z0-9_./-]{2,}")
_MODEL = None
_TOKENIZER = None
_LOADED_MODEL_ID = ""
_LOADED_COMPRESSION = ""
_LAST_USED = 0.0
_LOAD_RSS_MB = 0.0
_LOAD_FAILED_REASON = ""
_LAST_CASCADE: list[str] = []


def available() -> bool:
    return kcfg.mamba_enabled() and (_MODEL is not None or kcfg.mamba_cascade_enabled())


def configured() -> bool:
    return kcfg.mamba_enabled()


def status() -> dict[str, Any]:
    tiers = kcfg.cascade_tiers() if kcfg.mamba_cascade_enabled() else []
    model_id = kcfg.mamba_model()
    carve: dict[str, Any] = {}
    try:
        import knowledge_mamba_backends as backends

        carve = backends.carve_status()
    except Exception as exc:  # noqa: BLE001
        carve = {"error": str(exc)[:120]}
    return {
        "enabled": kcfg.mamba_enabled(),
        "mode": "cascade" if kcfg.mamba_cascade_enabled() else "single",
        "model": model_id,
        "loaded": _MODEL is not None,
        "loaded_model": _LOADED_MODEL_ID or None,
        "loaded_compression": _LOADED_COMPRESSION or None,
        "max_ram_mb": kcfg.mamba_max_ram_mb(),
        "budget_gb": kcfg.knowledge_mamba_budget_gb(),
        "backend": kcfg.mamba_backend(),
        "compression": kcfg.mamba_compression(),
        "teacher_model": kcfg.mamba_teacher_model(),
        "estimated_weight_mb": kcfg.estimated_model_weight_mb(model_id or "", compression=kcfg.mamba_dtype()),
        "dtype": kcfg.mamba_dtype(),
        "device": kcfg.mamba_device(),
        "load_rss_mb": round(_LOAD_RSS_MB, 1),
        "last_used": _LAST_USED,
        "last_cascade": list(_LAST_CASCADE),
        "cascade_tiers": tiers,
        "load_failed": _LOAD_FAILED_REASON or None,
        "carve": carve,
        "paid_api": False,
    }


def _process_rss_mb() -> float:
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return rss / (1024 * 1024)
        return rss / 1024
    except OSError:
        return 0.0


def _touch() -> None:
    global _LAST_USED
    _LAST_USED = time.time()


def _maybe_unload_idle() -> None:
    if _MODEL is None:
        return
    idle_sec = kcfg.mamba_idle_unload_sec()
    if idle_sec <= 0:
        return
    if (time.time() - _LAST_USED) < idle_sec:
        return
    unload()


def unload() -> None:
    global _MODEL, _TOKENIZER, _LOADED_MODEL_ID, _LOADED_COMPRESSION, _LOAD_RSS_MB
    _MODEL = None
    _TOKENIZER = None
    _LOADED_MODEL_ID = ""
    _LOADED_COMPRESSION = ""
    _LOAD_RSS_MB = 0.0
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def _resolve_dtype(name: str):
    import torch

    if name in ("fp16", "float16", "half"):
        return torch.float16
    if name in ("bf16", "bfloat16"):
        return torch.bfloat16
    return torch.float32


def _disable_mamba_cuda_kernels() -> None:
    """GB10/SM121: prebuilt causal-conv1d CUDA ops segfault — force slow_forward."""
    if kcfg.mamba_device() != "cuda":
        return
    try:
        import transformers.models.mamba.modeling_mamba as mm

        mm.causal_conv1d_fn = None
        mm.causal_conv1d_update = None
        mm.selective_scan_fn = None
        mm.mamba_inner_fn = None
        mm.selective_state_update = None
    except ImportError:
        pass


def _load_model(model_id: str, *, compression: str) -> bool:
    """Load one tier; unloads any prior tier first (one model in RAM)."""
    global _MODEL, _TOKENIZER, _LOADED_MODEL_ID, _LOADED_COMPRESSION, _LOAD_RSS_MB, _LOAD_FAILED_REASON
    _maybe_unload_idle()
    if _MODEL is not None and _LOADED_MODEL_ID == model_id and _LOADED_COMPRESSION == compression:
        _touch()
        return True
    unload()
    est = kcfg.estimated_model_weight_mb(model_id, compression=compression)
    budget = kcfg.mamba_max_ram_mb()
    if est > budget:
        _LOAD_FAILED_REASON = f"{model_id} ({compression}) est {est}MB > budget {budget}MB"
        return False
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError:
        _LOAD_FAILED_REASON = "torch/transformers not installed"
        return False
    device = kcfg.mamba_device()
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"
    rss_before = _process_rss_mb()
    comp = compression.lower()
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        if comp in ("4bit", "q4", "int4"):
            try:
                from transformers import BitsAndBytesConfig
            except ImportError:
                _LOAD_FAILED_REASON = "bitsandbytes required for 4bit teacher_2"
                return False
            qconfig = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )
            model = AutoModel.from_pretrained(
                model_id,
                quantization_config=qconfig,
                low_cpu_mem_usage=True,
                trust_remote_code=True,
                device_map="auto" if device == "cuda" else {"": "cpu"},
            )
        else:
            dtype = _resolve_dtype(comp if comp in ("fp16", "bf16") else kcfg.mamba_dtype())
            model = AutoModel.from_pretrained(
                model_id,
                torch_dtype=dtype,
                low_cpu_mem_usage=True,
                trust_remote_code=True,
            )
            if device == "cuda":
                model = model.cuda()
            else:
                model = model.to("cpu")
        model.train(False)
        _disable_mamba_cuda_kernels()
        rss_after = _process_rss_mb()
        delta = max(0.0, rss_after - rss_before)
        if delta > budget and device == "cpu" and comp not in ("4bit", "q4", "int4"):
            del model
            del tokenizer
            gc.collect()
            _LOAD_FAILED_REASON = f"load used {delta:.0f}MB RSS > budget {budget}MB"
            return False
        _TOKENIZER = tokenizer
        _MODEL = model
        _LOADED_MODEL_ID = model_id
        _LOADED_COMPRESSION = compression
        _LOAD_RSS_MB = delta or float(est)
        _LOAD_FAILED_REASON = ""
        _touch()
    except Exception as exc:  # noqa: BLE001
        unload()
        _LOAD_FAILED_REASON = str(exc)[:200]
        return False
    return True


def _lazy_load() -> bool:
    if kcfg.mamba_cascade_enabled():
        return _load_model(kcfg.cascade_student_model(), compression=kcfg.cascade_compression("student"))
    model_id = kcfg.mamba_model()
    if not model_id:
        return False
    return _load_model(model_id, compression=kcfg.mamba_dtype())


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text)]


def hash_embed(text: str, dim: int = 256) -> list[float]:
    vec = [0.0] * dim
    for token in _tokenize(text):
        idx = hash(token) % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def _use_ssm_encode() -> bool:
    """Chunked SSM path — CPU fallback; CUDA uses batched forward for speed/stability."""
    if kcfg.mamba_device() == "cuda":
        return False
    try:
        import knowledge_mamba_ssm as ssm

        return ssm.enabled() and ssm.supports_ssm_cache(_MODEL)
    except Exception:
        return False


def _encode_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if _MODEL is None or _TOKENIZER is None:
        return [hash_embed(t) for t in texts]
    try:
        import knowledge_mamba_ssm as ssm

        if _use_ssm_encode():
            pool = ssm.manager()
            role = "student"
            if kcfg.mamba_cascade_enabled():
                role = "student"
            vectors: list[list[float]] = []
            for text in texts:
                vec = ssm.stream_encode_text(
                    _MODEL,
                    _TOKENIZER,
                    text,
                    role=role,
                    cache_key=f"{role}:{hash(text) & 0xFFFFFFFF:08x}",
                    pool=pool,
                )
                if vec:
                    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
                    vectors.append([v / norm for v in vec])
                else:
                    vectors.append(hash_embed(text))
            if vectors:
                _touch()
                return vectors
    except Exception:
        pass
    try:
        import torch

        max_len = kcfg.mamba_max_length()
        batch_size = kcfg.mamba_batch_size()
        vectors: list[list[float]] = []
        device = next(_MODEL.parameters()).device
        with torch.inference_mode():
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                encoded = _TOKENIZER(
                    batch,
                    return_tensors="pt",
                    truncation=True,
                    max_length=max_len,
                    padding=True,
                )
                encoded = {k: v.to(device) for k, v in encoded.items()}
                out = _MODEL(**encoded)
                hidden = out.last_hidden_state
                mask = encoded["attention_mask"].unsqueeze(-1)
                pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
                for row in pooled:
                    vec = row.detach().float().cpu().tolist()
                    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
                    vectors.append([v / norm for v in vec])
        _touch()
        return vectors
    except Exception:
        return [hash_embed(t) for t in texts]


def _hybrid_score(sparse: float, dense: float) -> float:
    sparse_w = kcfg.hybrid_sparse_weight()
    return sparse_w * sparse + (1.0 - sparse_w) * dense


def _score_hits(query: str, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    texts = [str(hit.get("text") or "") for hit in hits]
    encoded = _encode_batch([query, *texts])
    query_vec = encoded[0]
    doc_vecs = encoded[1:]
    scored: list[dict[str, Any]] = []
    for hit, doc_vec in zip(hits, doc_vecs):
        sparse = float(hit.get("sparse_score") or 0.0)
        dense = cosine(query_vec, doc_vec)
        enriched = dict(hit)
        enriched["dense_score"] = round(dense, 4)
        enriched["hybrid_score"] = round(_hybrid_score(sparse, dense), 4)
        scored.append(enriched)
    scored.sort(key=lambda h: float(h.get("hybrid_score") or 0.0), reverse=True)
    return scored


def _cascade_rerank(query: str, hits: list[dict[str, Any]], *, top_k: int) -> list[dict[str, Any]]:
    global _LAST_CASCADE
    trail: list[str] = []
    pool = list(hits)
    final_top = top_k
    for tier in kcfg.cascade_tiers():
        role = str(tier["role"])
        model_id = str(tier["model"])
        compression = str(tier["compression"])
        keep = int(tier["top_k"])
        if role == "teacher_2":
            keep = min(keep, final_top)
        if not pool:
            break
        if not _load_model(model_id, compression=compression):
            trail.append(f"{role}:skip({(_LOAD_FAILED_REASON or 'load failed')[:40]})")
            continue
        pool = _score_hits(query, pool)[:keep]
        for item in pool:
            item["cascade_stage"] = role
        trail.append(f"{role}:{len(pool)}")
        unload()
    _LAST_CASCADE = trail
    return pool[:final_top]


def dense_score(query: str, text: str) -> float:
    if not query or not text:
        return 0.0
    if not _lazy_load():
        qv, tv = hash_embed(query), hash_embed(text)
        return cosine(qv, tv)
    qv, tv = _encode_batch([query, text])
    return cosine(qv[0], tv[0])


def rerank(query: str, hits: list[dict[str, Any]], *, top_k: int) -> list[dict[str, Any]]:
    """Rerank hits; single-model path always unloads after (cascade already does)."""
    if not hits:
        return []
    if kcfg.mamba_cascade_enabled():
        return _cascade_rerank(query, hits, top_k=top_k)
    try:
        if not _lazy_load():
            sparse_w = kcfg.hybrid_sparse_weight()
            dense_w = 1.0 - sparse_w
            scored: list[tuple[float, dict[str, Any]]] = []
            for hit in hits:
                sparse = float(hit.get("sparse_score") or 0.0)
                dense = cosine(hash_embed(query), hash_embed(str(hit.get("text") or "")))
                hybrid = sparse_w * sparse + dense_w * dense
                enriched = dict(hit)
                enriched["dense_score"] = round(dense, 4)
                enriched["hybrid_score"] = round(hybrid, 4)
                scored.append((hybrid, enriched))
            scored.sort(key=lambda pair: pair[0], reverse=True)
            return [item for _, item in scored[:top_k]]
        return _score_hits(query, hits)[:top_k]
    finally:
        # peer_loop / improve must not retain GB-scale weights between calls.
        unload()


def warmup_cascade(*, log_fn: Callable[[str], None] = print) -> dict[str, Any]:
    """Load each cascade tier, smoke-encode, unload — verify all three work."""
    probe = "mamba cascade warmup — fast GPU encode probe for knowledge index"
    tiers_out: list[dict[str, Any]] = []
    for tier in kcfg.cascade_tiers():
        role = str(tier["role"])
        model_id = str(tier["model"])
        compression = str(tier["compression"])
        entry: dict[str, Any] = {"role": role, "model": model_id, "compression": compression}
        ok = _load_model(model_id, compression=compression)
        entry["loaded"] = ok
        if not ok:
            entry["encode_ok"] = False
            entry["error"] = _LOAD_FAILED_REASON or "load failed"
            tiers_out.append(entry)
            log_fn(f"warmup {role}: load failed — {entry['error']}")
            continue
        vecs = _encode_batch([probe])
        enc_ok = bool(vecs and len(vecs[0]) > 8)
        entry["encode_ok"] = enc_ok
        entry["dim"] = len(vecs[0]) if vecs else 0
        entry["device"] = kcfg.mamba_device()
        entry["rss_mb"] = round(_LOAD_RSS_MB, 1)
        tiers_out.append(entry)
        log_fn(f"warmup {role}: loaded encode={enc_ok} dim={entry['dim']} rss={entry['rss_mb']}MB")
        unload()
    all_ok = all(t.get("loaded") and t.get("encode_ok") for t in tiers_out)
    return {"all_ok": all_ok, "device": kcfg.mamba_device(), "tiers": tiers_out}


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Mamba cascade reranker status")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--unload", action="store_true")
    parser.add_argument("--warmup", action="store_true", help="Load+encode smoke test for all cascade tiers")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.unload:
        unload()
    if args.warmup:
        report = warmup_cascade(log_fn=lambda m: None if args.json else print(m))
        if args.json:
            print(json.dumps(report, indent=2))
        return 0 if report.get("all_ok") else 1
    if not args.status and not args.unload:
        parser.print_help()
        return 1
    report = status()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"mamba: mode={report['mode']} backend={report.get('backend')} "
            f"budget={report.get('budget_gb')}GB cap={report['max_ram_mb']}MB "
            f"compression={report.get('compression')} "
            f"loaded={report['loaded']} rss={report['load_rss_mb']}MB"
        )
        teacher = report.get("teacher_model")
        if teacher:
            print(f"  teacher: {teacher}")
        carve = report.get("carve") or {}
        if carve.get("agent_ram_max_used_gb") is not None:
            print(
                f"  carve: brain={carve.get('knowledge_mamba_budget_gb')}GB "
                f"(separate from agent_cap={carve.get('agent_ram_max_used_gb')}GB) NO PAY"
            )
        if report.get("cascade_tiers"):
            for tier in report["cascade_tiers"]:
                est = kcfg.estimated_model_weight_mb(tier["model"], compression=tier["compression"])
                print(f"  {tier['role']}: {tier['model']} ({tier['compression']}, ~{est}MB, top {tier['top_k']})")
        if report.get("last_cascade"):
            print(f"  last cascade: {' → '.join(report['last_cascade'])}")
        if report.get("load_failed"):
            print(f"  last error: {report['load_failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
