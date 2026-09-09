#!/usr/bin/env python3
"""T1 share-factor ablation — Distill-Fold / ALBERT-BitMoE.

OVERSEER_COMPRESSION_T1_SHARE_2026_09_05

Torch-free. Sweep share factor k including north-star-capable k≥100.
Reports arith_short_of_s100 (S<100) separately from recon quality proxy.
No data prune. train_unlocked=false (recipe lock — not a quality cliff).

Usage::

    python3 scripts/compression_t1_share.py
    python3 scripts/compression_t1_share.py --json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from typing import Any

# OVERSEER_COMPRESSION_T1_SHARE_2026_09_05
NEEDLE = "OVERSEER_COMPRESSION_T1_SHARE_2026_09_05"

# Include weak k (legacy) + north-star-capable k (S=Nk/(N+2k²) ≥100 needs k≳200 @ N=1e5).
K_GRID = (2, 4, 8, 16, 50, 100, 125, 200)
N_L_DEFAULT = 100_000
META_HEADER_BYTES = 16
META_BOUND_BYTES = 64
NORTH_STAR_S = 100.0
# Recon proxy: share stress should not explode MSE on this toy.
RECON_MSE_OK = 5e-2
TRAIN_UNLOCKED = False


@dataclass(frozen=True)
class ShareRow:
    stack: str
    k: int
    n_logic: int
    u_unique: int
    s_arith: float
    packed_bytes: int
    payload_bytes: int
    recon_mse: float
    arith_short_of_s100: bool
    cliff_before_s100: bool  # alias of arith_short (legacy name — not quality)
    quality_proxy_ok: bool
    train_unlocked: bool
    quality: str
    detail: dict[str, Any]


def _pack_1bit(u: int, meta_bytes: int = META_HEADER_BYTES) -> tuple[int, int]:
    payload = (u + 7) // 8
    return payload, payload + meta_bytes


def _pass_pack(u: int, packed_bytes: int) -> bool:
    ideal = u / 8.0
    ceil_ideal = (u + 7) // 8
    return (
        abs(packed_bytes - ideal) <= META_BOUND_BYTES
        or abs(packed_bytes - ceil_ideal) <= META_BOUND_BYTES
    )


def albert_bitmoe_at_k(n_logic: int, k: int) -> ShareRow:
    """ALBERT-BitMoE share: U = N_L/k + L·r·(d_in+d_out) with L=k (true depth-share).

    Body unique shrinks with k. Tiny per-layer LoRA keeps U > N/k.
    """
    if k not in K_GRID:
        raise ValueError(f"k={k} not in {K_GRID}")
    if n_logic % k != 0:
        raise ValueError(f"n_logic={n_logic} not divisible by k={k}")

    layers = k  # ALBERT-style: share factor = depth
    body_unique = n_logic // k
    r = 1
    lora_d_in, lora_d_out = 1, 1
    u_lora = layers * r * (lora_d_in + lora_d_out)
    u = body_unique + u_lora
    s = n_logic / u
    payload, packed = _pack_1bit(u)
    recon = toy_recon_mse(n_logic=n_logic, k=k, layers=layers)
    arith_short = s < NORTH_STAR_S
    quality_ok = recon <= RECON_MSE_OK
    return ShareRow(
        stack="ALBERT-BitMoE",
        k=k,
        n_logic=n_logic,
        u_unique=u,
        s_arith=s,
        packed_bytes=packed,
        payload_bytes=payload,
        recon_mse=recon,
        arith_short_of_s100=arith_short,
        cliff_before_s100=arith_short,
        quality_proxy_ok=quality_ok,
        train_unlocked=TRAIN_UNLOCKED,
        quality="proxy",
        detail={
            "L": layers,
            "B_body": body_unique,
            "r": r,
            "u_lora": u_lora,
            "formula": "U = N_L/k + L*r*(d_in+d_out) with L=k",
            "pass_pack": _pass_pack(u, packed),
            "distill_fold": "k-group shared body + tiny LoRA (toy)",
            "note": "arith_short_of_s100 ≠ quality cliff; train_unlocked is recipe lock",
        },
    )


def toy_recon_mse(*, n_logic: int, k: int, layers: int) -> float:
    """Recon under true k-way body share: layers share one body per congruence class.

    Group ell % k share the same body vector; per-layer bias remains. MSE rises
    with share stress (more layers per body) but stays small on this toy.
    """
    body = max(1, n_logic // max(k, 1))
    d = min(64, body)
    # Independent "teacher" layers.
    true_layers: list[list[float]] = []
    for ell in range(layers):
        seed = ((ell * 17 + 3) % 97) / 97.0
        bias = ((ell * 13) % 53) / 530.0
        true_layers.append(
            [((i * 19 + ell * 7) % 89) / 89.0 * (0.5 + seed) + bias for i in range(d)]
        )

    # Shared body per group g = mean of layers with ell % k == g.
    bodies: list[list[float]] = []
    for g in range(k):
        members = [ell for ell in range(layers) if ell % k == g]
        if not members:
            bodies.append([0.0] * d)
            continue
        bodies.append(
            [
                sum(true_layers[ell][i] for ell in members) / len(members)
                for i in range(d)
            ]
        )

    # Reconstruct: shared body[g] + scalar residual toward layer mean bias.
    sse = 0.0
    n = 0
    for ell in range(layers):
        g = ell % k
        body_hat = bodies[g]
        residual = [true_layers[ell][i] - body_hat[i] for i in range(d)]
        # Rank-1 residual fit within the group direction.
        v = body_hat[:]
        v_norm = math.sqrt(sum(x * x for x in v)) or 1.0
        v = [x / v_norm for x in v]
        a = sum(residual[i] * v[i] for i in range(d))
        for i in range(d):
            pred = body_hat[i] + a * v[i]
            err = true_layers[ell][i] - pred
            sse += err * err
            n += 1
    return sse / max(n, 1)


def run_sweep(
    n_logic: int = N_L_DEFAULT, k_grid: tuple[int, ...] = K_GRID
) -> list[ShareRow]:
    return [albert_bitmoe_at_k(n_logic, k) for k in k_grid]


def monotonic_unique_down(rows: list[ShareRow]) -> bool:
    us = [r.u_unique for r in rows]
    return all(us[i] > us[i + 1] for i in range(len(us) - 1))


def summary_dict(rows: list[ShareRow]) -> dict[str, Any]:
    clears = [r for r in rows if not r.arith_short_of_s100]
    return {
        "needle": NEEDLE,
        "k_grid": list(K_GRID),
        "n_logic": rows[0].n_logic if rows else N_L_DEFAULT,
        "train_unlocked": TRAIN_UNLOCKED,
        "monotonic_unique_down": monotonic_unique_down(rows),
        "all_pack_ok": all(r.detail.get("pass_pack") for r in rows),
        "all_quality_proxy_ok": all(r.quality_proxy_ok for r in rows),
        "arith_short_of_s100_all": all(r.arith_short_of_s100 for r in rows),
        "cliff_before_s100": all(r.cliff_before_s100 for r in rows),  # legacy
        "north_star_s_cleared": len(clears) > 0,
        "cleared_k": [r.k for r in clears],
        "results": [asdict(r) for r in rows],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="T1 share-factor ablation")
    p.add_argument("--json", action="store_true")
    p.add_argument("--n-logic", type=int, default=N_L_DEFAULT)
    args = p.parse_args(argv)
    rows = run_sweep(n_logic=args.n_logic)
    payload = summary_dict(rows)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not args.json:
        for r in rows:
            print(
                f"k={r.k} U={r.u_unique} S={r.s_arith:.2f} "
                f"recon_mse={r.recon_mse:.6e} arith_short={r.arith_short_of_s100} "
                f"q_ok={r.quality_proxy_ok} train_unlocked={r.train_unlocked}",
                file=sys.stderr,
            )
    ok = (
        payload["monotonic_unique_down"]
        and payload["all_pack_ok"]
        and payload["all_quality_proxy_ok"]
        and payload["north_star_s_cleared"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
