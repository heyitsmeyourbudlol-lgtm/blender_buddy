#!/usr/bin/env python3
"""Factory Dynamics — live serve/routing/resource policy for niche assist.

Needle: OVERSEER_FACTORY_DYNAMICS_2026_09_07

Single brain for:
  - CPU/GPU niche-serve balance (``gpu_share`` ∈ [0,1])
  - Adaptive top_k / worker count from load
  - Adaptive escalate floor from recent niche scores
  - Fail-soft when torch/CUDA missing (never blocks peer_loop)

Honesty: dynamics = serve/routing/resource policy only — not continuous
training, not TE, niches ≠ LLM, deterministic gates stay code.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DISTILL = ROOT / "notes" / "niche_distill"
STATE_PATH = DISTILL / "factory_dynamics_state.json"
BALANCE_PATH = DISTILL / "device_balance.json"
NEEDLE = "OVERSEER_FACTORY_DYNAMICS_2026_09_07"

# Tunables (clamped)
_GPU_SHARE_STEP = 0.10
_GPU_SHARE_MIN = 0.0
_GPU_SHARE_MAX = 1.0
_PICK_TTL_SEC = 3.0
_EMA_ALPHA = 0.35
_ESCALATE_FLOOR_MIN = 0.20
_ESCALATE_FLOOR_MAX = 0.55
_ESCALATE_FLOOR_DEFAULT = 0.35
_TOP_K_BIAS_MIN = -2
_TOP_K_BIAS_MAX = 2
_DEFAULT_VRAM_FLOOR_MB = 512
_DEFAULT_CPU_TARGET = 0.70
_GPU_UTIL_BUSY = 85.0
_VRAM_USED_FRAC_BUSY = 0.85

_lock = threading.RLock()
_pick_cache: tuple[float, str, str] | None = None  # ts, device, reason
_state: dict[str, Any] | None = None


def _cfg() -> dict[str, Any]:
    try:
        import project_automation as auto

        return dict(auto.CFG or {})
    except Exception:  # noqa: BLE001
        return {}


def _truthy(val: Any, default: bool = True) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    s = str(val).strip().lower()
    if s in ("0", "false", "no", "off", ""):
        return False
    if s in ("1", "true", "yes", "on"):
        return True
    return default


def balance_enabled() -> bool:
    env = os.environ.get("FACTORY_NICHE_BALANCE", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    mode = device_mode()
    if mode in ("balance", "auto"):
        return _truthy(_cfg().get("factory_niche_balance"), True)
    if mode in ("cpu", "cuda", "mps"):
        return False
    return _truthy(_cfg().get("factory_niche_balance"), True)


def device_mode() -> str:
    """Resolved preference: auto|balance|cpu|cuda|mps."""
    for key in ("FACTORY_NICHE_DEVICE", "NICHE_SERVE_DEVICE"):
        raw = os.environ.get(key, "").strip().lower()
        if raw in ("auto", "balance", "cpu", "cuda", "mps"):
            return raw
    raw = str(_cfg().get("factory_niche_device") or "auto").strip().lower()
    if raw in ("auto", "balance", "cpu", "cuda", "mps"):
        return raw
    return "auto"


def cpu_target_load() -> float:
    raw = os.environ.get("FACTORY_NICHE_CPU_TARGET") or _cfg().get(
        "factory_niche_cpu_target_load", _DEFAULT_CPU_TARGET
    )
    try:
        return max(0.3, min(0.95, float(raw)))
    except (TypeError, ValueError):
        return _DEFAULT_CPU_TARGET


def gpu_vram_floor_mb() -> float:
    raw = os.environ.get("FACTORY_NICHE_GPU_VRAM_FLOOR_MB") or _cfg().get(
        "factory_niche_gpu_vram_floor_mb", _DEFAULT_VRAM_FLOOR_MB
    )
    try:
        return max(64.0, float(raw))
    except (TypeError, ValueError):
        return float(_DEFAULT_VRAM_FLOOR_MB)


def serve_cache_enabled() -> bool:
    env = os.environ.get("FACTORY_NICHE_SERVE_CACHE", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    return _truthy(_cfg().get("factory_niche_serve_cache"), True)


def _default_state() -> dict[str, Any]:
    init_share = os.environ.get("FACTORY_NICHE_GPU_SHARE", "").strip()
    try:
        gpu_share = float(init_share) if init_share else 0.5
    except ValueError:
        gpu_share = 0.5
    gpu_share = max(_GPU_SHARE_MIN, min(_GPU_SHARE_MAX, gpu_share))
    return {
        "needle": NEEDLE,
        "gpu_share": gpu_share,
        "escalate_floor": _ESCALATE_FLOOR_DEFAULT,
        "top_k_bias": 0,
        "workers_bias": 0,
        "cpu_latency_ema_ms": None,
        "gpu_latency_ema_ms": None,
        "last_reasons": [],
        "last_adjust": None,
        "last_resources": None,
        "batches": 0,
        "cuda_errors": 0,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "honesty": (
            "Live serve/routing/resource policy only — not continuous training, "
            "not TE, niches ≠ LLM."
        ),
    }


def _load_state() -> dict[str, Any]:
    global _state
    with _lock:
        if _state is not None:
            return _state
        st = _default_state()
        for path in (STATE_PATH, BALANCE_PATH):
            if not path.is_file():
                continue
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(blob, dict):
                    if "gpu_share" in blob:
                        st["gpu_share"] = max(
                            _GPU_SHARE_MIN, min(_GPU_SHARE_MAX, float(blob["gpu_share"]))
                        )
                    for k in (
                        "escalate_floor",
                        "top_k_bias",
                        "workers_bias",
                        "cpu_latency_ema_ms",
                        "gpu_latency_ema_ms",
                        "batches",
                        "cuda_errors",
                        "last_reasons",
                        "last_adjust",
                        "last_resources",
                    ):
                        if k in blob:
                            st[k] = blob[k]
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
        _state = st
        return _state


def _persist_state(st: dict[str, Any]) -> None:
    st["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    st["needle"] = NEEDLE
    try:
        DISTILL.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(st, indent=2) + "\n"
        STATE_PATH.write_text(payload, encoding="utf-8")
        # Mirror gpu_share for ops/smoke that look at device_balance.json
        BALANCE_PATH.write_text(
            json.dumps(
                {
                    "needle": NEEDLE,
                    "gpu_share": st.get("gpu_share"),
                    "last_adjust": st.get("last_adjust"),
                    "last_resources": st.get("last_resources"),
                    "ts": st.get("ts"),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def snapshot() -> dict[str, Any]:
    """Public read of dynamics state + live resources (fail-soft)."""
    st = dict(_load_state())
    try:
        st["live_resources"] = probe_resources()
    except Exception as exc:  # noqa: BLE001
        st["live_resources"] = {"error": str(exc)}
    st["device_mode"] = device_mode()
    st["balance_enabled"] = balance_enabled()
    return st


def probe_resources() -> dict[str, Any]:
    """CPU load + GPU util/VRAM + MPS availability. Never raises."""
    out: dict[str, Any] = {
        "cpu_load": None,
        "cpu_count": None,
        "cpu_load_ratio": None,
        "cuda_available": False,
        "gpu_util": None,
        "gpu_free_mb": None,
        "gpu_total_mb": None,
        "mps_available": False,
        "torch": False,
    }
    try:
        ncpu = os.cpu_count() or 1
        out["cpu_count"] = ncpu
        load = os.getloadavg()[0]
        out["cpu_load"] = load
        out["cpu_load_ratio"] = load / max(1, ncpu)
    except (OSError, AttributeError):
        pass

    try:
        import torch

        out["torch"] = True
        if torch.cuda.is_available():
            out["cuda_available"] = True
            try:
                free_b, total_b = torch.cuda.mem_get_info()
                out["gpu_free_mb"] = free_b / (1024 * 1024)
                out["gpu_total_mb"] = total_b / (1024 * 1024)
            except Exception:  # noqa: BLE001
                pass
            util = _nvidia_smi_util()
            if util is not None:
                out["gpu_util"] = util
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            out["mps_available"] = True
    except Exception:  # noqa: BLE001
        pass
    return out


def _nvidia_smi_util() -> float | None:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if proc.returncode != 0:
            return None
        line = (proc.stdout or "").strip().splitlines()[0]
        return float(line.strip())
    except Exception:  # noqa: BLE001
        return None


def _probe_cuda_ok() -> bool:
    try:
        import torch

        if not torch.cuda.is_available():
            return False
        torch.cuda.empty_cache()
        t = torch.zeros(1, device="cuda")
        del t
        torch.cuda.empty_cache()
        return True
    except Exception:  # noqa: BLE001
        return False


def _probe_mps_ok() -> bool:
    try:
        import torch

        mps = getattr(torch.backends, "mps", None)
        if mps is None or not mps.is_available():
            return False
        t = torch.zeros(1024, device="mps")
        del t
        return True
    except Exception:  # noqa: BLE001
        return False


def resolve_torch_device(device_name: str):
    """Map name → torch.device; fail-soft to CPU. Used by serve/train loaders."""
    import torch

    want = (device_name or "cpu").strip().lower()
    if want in ("auto", "balance"):
        want, _ = pick_optimal_device()
    if want == "cuda":
        if _probe_cuda_ok():
            return torch.device("cuda")
        return torch.device("cpu")
    if want == "mps":
        if _probe_mps_ok():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device("cpu")


def pick_optimal_device(override: str | None = None) -> tuple[str, str]:
    """Smart single-device pick with short TTL cache.

    Returns (device_name, reason). Forced cpu|cuda|mps skip heuristics.
    auto/balance use load + VRAM (not naive cuda-first).
    """
    global _pick_cache
    mode = (override or device_mode()).strip().lower()
    if mode in ("cpu", "cuda", "mps"):
        if mode == "cuda" and not _probe_cuda_ok():
            return "cpu", "cuda_unavailable_cpu"
        if mode == "mps" and not _probe_mps_ok():
            return "cpu", "mps_unavailable_cpu"
        return mode, f"forced_{mode}"

    now = time.monotonic()
    with _lock:
        if _pick_cache and (now - _pick_cache[0]) < _PICK_TTL_SEC:
            return _pick_cache[1], _pick_cache[2]

    res = probe_resources()
    cpu_ratio = float(res.get("cpu_load_ratio") or 0.0)
    target = cpu_target_load()
    floor_mb = gpu_vram_floor_mb()
    free_mb = res.get("gpu_free_mb")
    total_mb = res.get("gpu_total_mb")
    util = res.get("gpu_util")
    cuda_ok = bool(res.get("cuda_available")) and _probe_cuda_ok()

    reason = "cpu_default"
    pick = "cpu"

    if cuda_ok:
        vram_ok = free_mb is None or float(free_mb) >= floor_mb
        used_frac = None
        if free_mb is not None and total_mb and float(total_mb) > 0:
            used_frac = 1.0 - (float(free_mb) / float(total_mb))
        util_high = util is not None and float(util) >= _GPU_UTIL_BUSY
        vram_tight = used_frac is not None and used_frac >= _VRAM_USED_FRAC_BUSY
        gpu_busy = util_high or vram_tight or not vram_ok

        if gpu_busy:
            pick, reason = "cpu", "cuda_busy_use_cpu"
        elif cpu_ratio >= target and vram_ok:
            pick, reason = "cuda", "cpu_load_high_use_cuda"
        elif vram_ok:
            pick, reason = "cuda", "cuda_free_vram"
        else:
            pick, reason = "cpu", "cuda_busy_use_cpu"
    elif res.get("mps_available") and _probe_mps_ok():
        # Unified memory: prefer MPS when CPU load is high
        if cpu_ratio >= target * 0.85:
            pick, reason = "mps", "mps"
        else:
            pick, reason = "mps", "mps"
    else:
        pick, reason = "cpu", "cpu_default"

    with _lock:
        _pick_cache = (now, pick, reason)
    return pick, reason


def gpu_share() -> float:
    return float(_load_state().get("gpu_share") or 0.0)


def escalate_floor() -> float:
    return float(_load_state().get("escalate_floor") or _ESCALATE_FLOOR_DEFAULT)


def adaptive_top_k(base: int | None = None) -> int:
    """Base top_k + bias from dynamics; shrink under extreme CPU load."""
    if base is None:
        raw = os.environ.get("FACTORY_NICHE_TOP_K") or _cfg().get("factory_niche_top_k") or 3
        try:
            base = int(raw)
        except (TypeError, ValueError):
            base = 3
    st = _load_state()
    bias = int(st.get("top_k_bias") or 0)
    k = max(1, min(8, int(base) + bias))
    res = probe_resources()
    ratio = float(res.get("cpu_load_ratio") or 0.0)
    if ratio >= 1.2:
        k = max(1, k - 1)
    return k


def adaptive_cpu_workers(base: int | None = None) -> int:
    """CPU-side thread pool size; shrink when CPU load high."""
    if base is None:
        raw = os.environ.get("FACTORY_NICHE_WORKERS") or _cfg().get("factory_niche_workers") or 4
        try:
            base = int(raw)
        except (TypeError, ValueError):
            base = 4
    n = max(1, min(16, int(base)))
    st = _load_state()
    bias = int(st.get("workers_bias") or 0)
    n = max(1, min(16, n + bias))
    res = probe_resources()
    ratio = float(res.get("cpu_load_ratio") or 0.0)
    target = cpu_target_load()
    if ratio >= target + 0.25:
        return 1
    if ratio >= target:
        return max(1, min(2, n))
    return n


def assign_devices(n: int) -> list[str]:
    """Split n serves across GPU/CPU by gpu_share (balance) or single pick.

    GPU device is ``cuda`` or ``mps`` when that backend is the active accelerator.
    """
    if n <= 0:
        return []
    mode = device_mode()
    if mode in ("cpu", "cuda", "mps"):
        return [mode] * n
    if not balance_enabled():
        d, _ = pick_optimal_device()
        return [d] * n

    share = gpu_share()
    accel, _ = pick_optimal_device()
    if accel == "cpu":
        # No usable accelerator → all CPU
        return ["cpu"] * n

    n_gpu = int(round(n * share))
    n_gpu = max(0, min(n, n_gpu))
    # Single niche: probabilistic by share, nudged if one side under target
    if n == 1:
        res = probe_resources()
        cpu_ratio = float(res.get("cpu_load_ratio") or 0.0)
        if cpu_ratio >= cpu_target_load() and share >= 0.35:
            return [accel]
        if share <= 0.0:
            return ["cpu"]
        if share >= 1.0:
            return [accel]
        return [accel if random.random() < share else "cpu"]

    devices = [accel] * n_gpu + ["cpu"] * (n - n_gpu)
    return devices


def _ema(prev: float | None, sample: float) -> float:
    if prev is None:
        return sample
    return (1.0 - _EMA_ALPHA) * float(prev) + _EMA_ALPHA * sample


def pick_device(prefer: str | None = None) -> tuple[str, str]:
    """Public alias: (device_name, reason)."""
    return pick_optimal_device(prefer)


def serve_device(prefer: str | None = None) -> tuple[str, str]:
    """Device pick for niche ``serve_one`` — alias of ``pick_device``."""
    return pick_device(prefer)


def observe_system() -> dict[str, Any]:
    """Public alias for probe_resources with ~3s TTL via pick cache side-effect."""
    return probe_resources()


def adjust_after_batch(
    serves: list[dict[str, Any]],
    errors: list[Any] | None = None,
    *,
    latencies_ms: list[tuple[str, float]] | None = None,
) -> dict[str, Any]:
    """Public alias for observe_batch; merges explicit errors into serves."""
    merged = list(serves or [])
    for err in errors or []:
        if isinstance(err, dict):
            merged.append(err)
        else:
            merged.append({"error": str(err), "ok": False})
    return observe_batch(merged, latencies_ms=latencies_ms)


def plan_serve(pairs: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """Split (nid, text) pairs across devices by gpu_share → (nid, text, device)."""
    if not pairs:
        return []
    devices = assign_devices(len(pairs))
    out: list[tuple[str, str, str]] = []
    for (nid, text), dev in zip(pairs, devices):
        out.append((str(nid), str(text), str(dev)))
    return out


def params_for_assist() -> dict[str, Any]:
    """Assist-time knobs: top_k, workers, escalate_floor, gpu_share, mode, reasons."""
    st = _load_state()
    d, reason = pick_device()
    return {
        "top_k": adaptive_top_k(),
        "workers": adaptive_cpu_workers(),
        "escalate_floor": escalate_floor(),
        "gpu_share": gpu_share(),
        "device_mode": device_mode(),
        "device": d,
        "device_pick_reason": reason,
        "top_k_bias": int(st.get("top_k_bias") or 0),
        "workers_bias": int(st.get("workers_bias") or 0),
        "reasons": list(st.get("last_reasons") or []),
        "needle": NEEDLE,
    }


def observe_batch(
    serves: list[dict[str, Any]],
    *,
    latencies_ms: list[tuple[str, float]] | None = None,
) -> dict[str, Any]:
    """Adjust gpu_share / escalate_floor / top_k_bias after a serve batch.

    Returns balance_adjust dict (delta + why) for payload honesty.
    """
    global _state
    with _lock:
        st = _load_state()
        res = probe_resources()
        st["last_resources"] = res
        reasons: list[str] = []
        delta = 0.0
        share = float(st.get("gpu_share") or 0.5)

        # Latency EMAs
        if latencies_ms:
            for dev, ms in latencies_ms:
                if ms is None or ms < 0:
                    continue
                if str(dev).startswith("cuda") or str(dev) == "mps":
                    st["gpu_latency_ema_ms"] = _ema(st.get("gpu_latency_ema_ms"), float(ms))
                else:
                    st["cpu_latency_ema_ms"] = _ema(st.get("cpu_latency_ema_ms"), float(ms))

        # CUDA / OOM errors in serves
        cuda_err = 0
        scores: list[float] = []
        for s in serves or []:
            err = str(s.get("error") or "").lower()
            if "out of memory" in err or "cuda" in err and s.get("ok") is False:
                cuda_err += 1
            if s.get("score") is not None and not s.get("error"):
                try:
                    scores.append(float(s["score"]))
                except (TypeError, ValueError):
                    pass
        if cuda_err:
            st["cuda_errors"] = int(st.get("cuda_errors") or 0) + cuda_err
            delta -= _GPU_SHARE_STEP
            reasons.append("cuda_error")

        cpu_ratio = float(res.get("cpu_load_ratio") or 0.0)
        target = cpu_target_load()
        free_mb = res.get("gpu_free_mb")
        total_mb = res.get("gpu_total_mb")
        util = res.get("gpu_util")
        floor = gpu_vram_floor_mb()
        vram_ok = free_mb is None or float(free_mb) >= floor
        used_frac = None
        if free_mb is not None and total_mb and float(total_mb) > 0:
            used_frac = 1.0 - (float(free_mb) / float(total_mb))
        util_high = util is not None and float(util) >= _GPU_UTIL_BUSY
        vram_tight = used_frac is not None and used_frac >= _VRAM_USED_FRAC_BUSY

        if res.get("cuda_available") or res.get("mps_available"):
            if cpu_ratio >= target and vram_ok and not util_high and not vram_tight:
                delta += _GPU_SHARE_STEP
                reasons.append("cpu_high_gpu_free")
            if util_high or vram_tight or (free_mb is not None and not vram_ok):
                delta -= _GPU_SHARE_STEP
                reasons.append("gpu_busy")

        cpu_lat = st.get("cpu_latency_ema_ms")
        gpu_lat = st.get("gpu_latency_ema_ms")
        if cpu_lat and gpu_lat and float(gpu_lat) > float(cpu_lat) * 1.35:
            delta -= _GPU_SHARE_STEP * 0.5
            reasons.append("gpu_slower_than_cpu")

        # Clamp step
        delta = max(-_GPU_SHARE_STEP, min(_GPU_SHARE_STEP, delta))
        if not balance_enabled() or device_mode() in ("cpu", "cuda", "mps"):
            delta = 0.0
            reasons = ["forced_mode_no_adjust"]

        new_share = max(_GPU_SHARE_MIN, min(_GPU_SHARE_MAX, share + delta))
        st["gpu_share"] = new_share

        # Escalate floor from score quality
        floor_esc = float(st.get("escalate_floor") or _ESCALATE_FLOOR_DEFAULT)
        if scores:
            mean_s = sum(scores) / len(scores)
            low = sum(1 for s in scores if s < floor_esc) / len(scores)
            if mean_s < floor_esc or low >= 0.5:
                floor_esc = min(_ESCALATE_FLOOR_MAX, floor_esc + 0.03)
                reasons.append("scores_weak_escalate_sooner")
            elif mean_s >= floor_esc + 0.25 and low < 0.15:
                floor_esc = max(_ESCALATE_FLOOR_MIN, floor_esc - 0.02)
                reasons.append("scores_stable_trust_more")
            st["escalate_floor"] = floor_esc

        # top_k_bias / workers_bias: high CPU → fewer niches & workers
        bias = int(st.get("top_k_bias") or 0)
        wbias = int(st.get("workers_bias") or 0)
        if cpu_ratio >= target + 0.2:
            bias = max(_TOP_K_BIAS_MIN, bias - 1)
            wbias = max(-3, wbias - 1)
            reasons.append("cpu_load_cut_topk")
        elif cpu_ratio < target * 0.5 and (vram_ok or not res.get("cuda_available")):
            if bias < 1:
                bias = min(_TOP_K_BIAS_MAX, bias + 1)
            if wbias < 0:
                wbias = min(2, wbias + 1)
        st["top_k_bias"] = bias
        st["workers_bias"] = wbias

        st["batches"] = int(st.get("batches") or 0) + 1
        st["last_reasons"] = reasons[-8:]
        adjust = {
            "delta": round(delta, 3),
            "gpu_share_before": round(share, 3),
            "gpu_share_after": round(new_share, 3),
            "why": reasons,
            "escalate_floor": st["escalate_floor"],
            "top_k_bias": st["top_k_bias"],
            "workers_bias": st["workers_bias"],
        }
        st["last_adjust"] = adjust
        _state = st
        _persist_state(st)
        return adjust


def log_line() -> str:
    st = _load_state()
    res = st.get("last_resources") or probe_resources()
    load = res.get("cpu_load_ratio")
    load_s = f"{load:.2f}" if isinstance(load, (int, float)) else "?"
    return (
        f"factory-dynamics: gpu_share={float(st.get('gpu_share') or 0):.2f} "
        f"escalate={float(st.get('escalate_floor') or 0):.2f} "
        f"load={load_s} mode={device_mode()}"
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--pick", action="store_true")
    ap.add_argument("--assign", type=int, default=0, help="print N device assignments")
    args = ap.parse_args(argv)
    if args.pick:
        d, r = pick_optimal_device()
        print(json.dumps({"device": d, "device_pick_reason": r}, indent=2))
        return 0
    if args.assign:
        print(json.dumps({"devices": assign_devices(args.assign), "gpu_share": gpu_share()}, indent=2))
        return 0
    print(json.dumps(snapshot(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
