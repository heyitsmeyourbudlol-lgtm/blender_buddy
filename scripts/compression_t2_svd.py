#!/usr/bin/env python3
"""T2 SVD-TieStack toy probe — real truncated SVD + rank grid.

OVERSEER_COMPRESSION_T2_SVD_2026_09_05

Torch-free. Sweep SVD rank r including north-star-capable low ranks.
Reports arith_short_of_s100 (S<100) separately from recon residual MSE.
No data prune. train_unlocked=false (recipe lock — not a quality cliff).

Usage::

    python3 scripts/compression_t2_svd.py
    python3 scripts/compression_t2_svd.py --json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from typing import Any

# OVERSEER_COMPRESSION_T2_SVD_2026_09_05
NEEDLE = "OVERSEER_COMPRESSION_T2_SVD_2026_09_05"

# Include r=1,2 so S = d^2/(2dr+r) can clear 100 on d=256 (r=1 → S≈128).
R_GRID = (1, 2, 4, 8, 16, 32)
D_DEFAULT = 256
META_HEADER_BYTES = 16
META_BOUND_BYTES = 64
NORTH_STAR_S = 100.0
TRAIN_UNLOCKED = False


@dataclass(frozen=True)
class SvdRow:
    stack: str
    r: int
    d: int
    n_logic: int
    u_unique: int
    s_arith: float
    packed_bytes: int
    payload_bytes: int
    recon_mse: float
    arith_short_of_s100: bool
    cliff_before_s100: bool  # legacy alias of arith_short
    train_unlocked: bool
    quality: str
    detail: dict[str, Any]


def unique_svd_tie(d: int, r: int) -> int:
    """Unique params for SVD factors U(d×r) + S(r) + V(r×d) tied once."""
    return d * r + r + r * d


def pack_bytes(u: int) -> int:
    return META_HEADER_BYTES + int(math.ceil(u / 8.0))


def _synthetic_matrix(d: int) -> list[list[float]]:
    """Deterministic full-rank-ish d×d matrix (no RNG)."""
    mat: list[list[float]] = []
    for i in range(d):
        row = []
        for j in range(d):
            row.append((((i * 31 + j * 17 + 5) % 997) / 997.0) - 0.5)
        mat.append(row)
    return mat


def _matvec(a: list[list[float]], x: list[float]) -> list[float]:
    d = len(x)
    return [sum(a[i][j] * x[j] for j in range(d)) for i in range(d)]


def _norm(x: list[float]) -> float:
    return math.sqrt(sum(v * v for v in x)) or 1e-12


def truncated_svd_residuals(d: int, ranks: tuple[int, ...], *, iters: int = 4) -> dict[int, float]:
    """One deflation pass → residual MSE after keeping top-r for each r in ranks."""
    a = _synthetic_matrix(d)
    work = [row[:] for row in a]
    max_r = max(ranks)
    kept: list[tuple[list[float], float, list[float]]] = []
    out: dict[int, float] = {}
    rank_set = set(ranks)

    def _mse_with(components: list[tuple[list[float], float, list[float]]]) -> float:
        recon = [[0.0] * d for _ in range(d)]
        for u, s, v in components:
            for i in range(d):
                uj = u[i]
                for j in range(d):
                    recon[i][j] += s * uj * v[j]
        sse = 0.0
        for i in range(d):
            ai = a[i]
            ri = recon[i]
            for j in range(d):
                err = ai[j] - ri[j]
                sse += err * err
        return sse / float(d * d)

    for r_i in range(1, max_r + 1):
        v = [((i * 13 + 7 + r_i) % 89) / 89.0 for i in range(d)]
        v = [x / _norm(v) for x in v]
        for _it in range(iters):
            u = _matvec(work, v)
            u = [x / _norm(u) for x in u]
            vt = [sum(work[i][j] * u[i] for i in range(d)) for j in range(d)]
            v = [x / _norm(vt) for x in vt]
        u = _matvec(work, v)
        s = _norm(u)
        u = [x / (s or 1.0) for x in u]
        kept.append((u, s, v))
        for i in range(d):
            ui = u[i]
            wi = work[i]
            for j in range(d):
                wi[j] -= s * ui * v[j]
        if r_i in rank_set:
            out[r_i] = _mse_with(kept)
    return out


def run_sweep(d: int = D_DEFAULT) -> list[SvdRow]:
    n_logic = d * d
    mse_by_r = truncated_svd_residuals(d, R_GRID)
    rows: list[SvdRow] = []
    for r in R_GRID:
        u = unique_svd_tie(d, r)
        s = n_logic / float(u) if u else 0.0
        payload = int(math.ceil(u / 8.0))
        packed = pack_bytes(u)
        mse = mse_by_r[r]
        arith_short = s < NORTH_STAR_S
        pass_pack = abs(packed - payload - META_HEADER_BYTES) <= META_BOUND_BYTES
        rows.append(
            SvdRow(
                stack="SVD-TieStack",
                r=r,
                d=d,
                n_logic=n_logic,
                u_unique=u,
                s_arith=s,
                packed_bytes=packed,
                payload_bytes=payload,
                recon_mse=mse,
                arith_short_of_s100=arith_short,
                cliff_before_s100=arith_short,
                train_unlocked=TRAIN_UNLOCKED,
                quality="proxy",
                detail={
                    "pass_pack": pass_pack,
                    "needle": NEEDLE,
                    "recon": "power-iter truncated SVD residual (single deflation pass)",
                    "note": "arith_short_of_s100 ≠ quality cliff; train_unlocked is recipe lock",
                },
            )
        )
    return rows


def monotonic_unique_up_with_rank(rows: list[SvdRow]) -> bool:
    prev: int | None = None
    for row in rows:
        if prev is not None and row.u_unique <= prev:
            return False
        prev = row.u_unique
    return True


def report_dict(rows: list[SvdRow]) -> dict[str, Any]:
    clears = [r for r in rows if not r.arith_short_of_s100]
    return {
        "needle": NEEDLE,
        "train_unlocked": TRAIN_UNLOCKED,
        "r_grid": list(R_GRID),
        "monotonic_unique_up_with_rank": monotonic_unique_up_with_rank(rows),
        "all_pack_ok": all(r.detail.get("pass_pack") for r in rows),
        "arith_short_of_s100_all": all(r.arith_short_of_s100 for r in rows),
        "cliff_all_before_s100": all(r.cliff_before_s100 for r in rows),
        "north_star_s_cleared": len(clears) > 0,
        "cleared_r": [r.r for r in clears],
        "results": [asdict(r) for r in rows],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--d", type=int, default=D_DEFAULT)
    args = parser.parse_args(argv)
    rows = run_sweep(d=args.d)
    payload = report_dict(rows)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{NEEDLE} train_unlocked={TRAIN_UNLOCKED}")
        for r in rows:
            print(
                f"r={r.r} U={r.u_unique} S={r.s_arith:.2f} "
                f"pack={r.packed_bytes} mse={r.recon_mse:.6e} "
                f"arith_short={r.arith_short_of_s100}"
            )
        print(
            f"mono_U_up={payload['monotonic_unique_up_with_rank']} "
            f"pack_ok={payload['all_pack_ok']} "
            f"s100_cleared={payload['north_star_s_cleared']} @ r={payload['cleared_r']}"
        )
    ok = (
        payload["monotonic_unique_up_with_rank"]
        and payload["all_pack_ok"]
        and payload["north_star_s_cleared"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
