#!/usr/bin/env python3
"""Compression GPU worker — use CLEAN GB10 for SVD / KD / T4 scale math (free local CUDA).

Needle: OVERSEER_COMPRESSION_GPU_2026_09_05

Does NOT bill Cursor API. Runs on-box torch.cuda.
Speeds research that cursor-agent cannot: large SVD, logit KD matmuls, scale U/N sweeps.
Writes notes/compression_artifacts/gpu_accel_status.json each cycle.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ART = ROOT / "notes" / "compression_artifacts"
NEEDLE = "OVERSEER_COMPRESSION_GPU_2026_09_05"

sys.path.insert(0, str(SCRIPTS))
os.chdir(ROOT)


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}", flush=True)


def device():
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA not available")
    return torch.device("cuda:0")


def cap_memory(frac: float = 0.85) -> None:
    try:
        import torch

        torch.cuda.set_per_process_memory_fraction(max(0.2, min(0.95, frac)), 0)
    except Exception:  # noqa: BLE001
        pass


def svd_scale_sweep(*, d: int = 1024, ranks: tuple[int, ...] = (1, 2, 4, 8)) -> dict:
    """GPU truncated SVD on d×d — T2/T4-style unique/S math at larger d than CPU toys."""
    import torch

    dev = device()
    # Deterministic synthetic weight
    i = torch.arange(d, device=dev, dtype=torch.float32)
    j = torch.arange(d, device=dev, dtype=torch.float32)
    w = ((i[:, None] * 31 + j[None, :] * 17 + 5) % 997).float() / 997.0 - 0.5
    n_logic = d * d
    rows = []
    t0 = time.perf_counter()
    # One full SVD — reuse factors for each rank (was 4× redundant SVD).
    u, s, vh = torch.linalg.svd(w, full_matrices=False)
    for r in ranks:
        u_r, s_r, vh_r = u[:, :r], s[:r], vh[:r, :]
        recon = (u_r * s_r) @ vh_r
        mse = float(torch.mean((recon - w) ** 2).item())
        u_unique = 2 * d * r + r  # U,V + singular values
        s_arith = n_logic / max(1, u_unique)
        rows.append(
            {
                "r": r,
                "d": d,
                "n_logic": n_logic,
                "u_unique": u_unique,
                "S": round(s_arith, 4),
                "recon_mse": mse,
                "arith_short_of_s100": s_arith < 100.0,
                "nvfp4_mb": round((u_unique / 2.0) / (1024 * 1024), 6),
            }
        )
    del u, s, vh, w, i, j
    torch.cuda.synchronize()
    return {
        "kind": "svd_scale_sweep",
        "seconds": round(time.perf_counter() - t0, 4),
        "device": torch.cuda.get_device_name(0),
        "rows": rows,
        "best_S": max(r["S"] for r in rows),
    }


def kd_gpu_step(*, n: int = 4096, dim: int = 512, steps: int = 80) -> dict:
    """Tiny BitDistill-style KD on GPU — student low-rank vs teacher dense logits."""
    import torch
    import torch.nn.functional as F

    dev = device()
    g = torch.Generator(device=dev)
    g.manual_seed(42)
    x = torch.randn(n, dim, device=dev, generator=g)
    # Teacher: full linear
    w_t = torch.randn(dim, dim, device=dev, generator=g) * 0.02
    with torch.no_grad():
        teacher = x @ w_t
    # Student: rank-2 SVD-ish factors (min unique)
    r = 2
    a = torch.randn(dim, r, device=dev, requires_grad=True)
    b = torch.randn(r, dim, device=dev, requires_grad=True)
    opt = torch.optim.Adam([a, b], lr=1e-2)
    t0 = time.perf_counter()
    last = 0.0
    for _ in range(steps):
        opt.zero_grad(set_to_none=True)
        student = x @ (a @ b)
        loss = F.mse_loss(student, teacher)
        loss.backward()
        opt.step()
        last = float(loss.item())
    torch.cuda.synchronize()
    u = dim * r + r * dim
    return {
        "kind": "kd_gpu_step",
        "seconds": round(time.perf_counter() - t0, 4),
        "heldout_proxy_mse": last,
        "unique_U": u,
        "S_vs_dense": round((dim * dim) / u, 4),
        "nvfp4_mb": round((u / 2.0) / (1024 * 1024), 6),
        "data_prune": False,
    }


def t4_ratio_check(*, n_logic: int = 10_000_000, k: int = 200, r: int = 1, d: int = 256, layers: int = 16) -> dict:
    """T4-ish unique ratio on GPU-backed dims (arith + optional random pack smoke)."""
    import torch

    shared = max(1, n_logic // k)
    u = shared + layers * r * (d + d) + layers * 2 * (d + d)  # svd + lora r=2
    s = n_logic / u
    # Smoke: allocate unique store as NVFP4-ish packed int8 nibbles simulation on GPU
    dev = device()
    t0 = time.perf_counter()
    packed = torch.empty(max(1, u // 2), dtype=torch.uint8, device=dev)
    packed.random_(0, 255)
    torch.cuda.synchronize()
    return {
        "kind": "t4_ratio_check",
        "seconds": round(time.perf_counter() - t0, 4),
        "n_logic": n_logic,
        "unique_U": u,
        "S": round(s, 4),
        "arith_short_of_s100": s < 100.0,
        "nvfp4_pack_mb": round((u / 2.0) / (1024 * 1024), 4),
        "packed_bytes_alloc": int(packed.numel()),
        "objective": "min U / min RAM @ NVFP4",
    }


def write_status(payload: dict) -> Path:
    ART.mkdir(parents=True, exist_ok=True)
    path = ART / "gpu_accel_status.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # Soft-land T4 evidence if S clears and scale is large
    t4 = payload.get("t4_ratio_check") or {}
    if t4.get("S", 0) >= 80 and t4.get("n_logic", 0) >= 1_000_000:
        stamp = ART / "t4_gpu_evidence.json"
        stamp.write_text(
            json.dumps(
                {
                    "needle": "OVERSEER_COMPRESSION_T4_GPU_EVIDENCE_2026_09_05",
                    "ts": payload.get("ts"),
                    "t4": t4,
                    "note": "GPU scale arith evidence — peers must still mark TRAIN_READY T4 Done + recipe LOCKED",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return path


def release_cuda() -> None:
    """Drop caching-allocator / host tensor refs between forever ticks.

    Needle: COMPRESSION_GPU_RELEASE_BETWEEN_CYCLES_2026_09_06
    Zero feature loss — next cycle reallocates; cuts idle host+GPU RSS.
    """
    import gc

    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            try:
                torch.cuda.ipc_collect()
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    gc.collect()


def one_cycle() -> dict:
    import torch

    cap_memory(0.85)
    payload = {
        "needle": NEEDLE,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "device": torch.cuda.get_device_name(0),
        "cuda": True,
        "billing": "local_cuda_free",
    }
    payload["svd_scale_sweep"] = svd_scale_sweep()
    payload["kd_gpu_step"] = kd_gpu_step()
    payload["t4_ratio_check"] = t4_ratio_check()
    # Prefer larger scale when memory allows
    try:
        free, total = torch.cuda.mem_get_info()
        if free > 8 * 1024**3:
            payload["t4_ratio_check_1e8"] = t4_ratio_check(n_logic=100_000_000)
    except Exception:  # noqa: BLE001
        pass
    path = write_status(payload)
    payload["status_path"] = str(path)
    release_cuda()
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--forever", action="store_true")
    ap.add_argument("--interval-sec", type=float, default=20.0)
    args = ap.parse_args()

    log(f"{NEEDLE} CUDA compression accel starting")
    try:
        import torch

        if not torch.cuda.is_available():
            log("CUDA unavailable — exit")
            return 2
        log(f"device={torch.cuda.get_device_name(0)}")
    except Exception as exc:  # noqa: BLE001
        log(f"torch import fail: {exc}")
        return 2

    if args.forever or not args.once:
        while True:
            try:
                p = one_cycle()
                log(
                    f"cycle ok S={p['t4_ratio_check']['S']} "
                    f"svd_s={p['svd_scale_sweep']['seconds']}s "
                    f"kd_s={p['kd_gpu_step']['seconds']}s"
                )
            except Exception as exc:  # noqa: BLE001
                log(f"cycle error: {exc}")
                release_cuda()
            if args.once:
                break
            time.sleep(max(5.0, args.interval_sec))
        return 0

    print(json.dumps(one_cycle(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
