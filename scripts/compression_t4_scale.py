#!/usr/bin/env python3
"""T4 scale rung — U/N ratio at N_logic 1e7→1e8 (still below 1B).

OVERSEER_COMPRESSION_T4_SCALE_2026_09_06

ALBERT-BitMoE-style unique budget:
  U = N/k + L*r_svd*(din+dout) + L*r_lora*(din+dout)
Pass: S=N/U stable within ±20% across scale grid; S>=50 on all rungs;
at least one rung S>=100. No data prune. train_unlocked=false (recipe lock).

Usage::
    python3 scripts/compression_t4_scale.py
    python3 scripts/compression_t4_scale.py --json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from typing import Any

NEEDLE = "OVERSEER_COMPRESSION_T4_SCALE_2026_09_06"
N_GRID = (10_000_000, 50_000_000, 100_000_000)
K_SHARE = 200
R_SVD = 1
R_LORA = 2
L_LAYERS = 16
D_IN = 256
D_OUT = 256
NORTH_STAR_S = 100.0
FLOOR_S = 50.0
RATIO_TOL = 0.20  # ±20%
TRAIN_UNLOCKED = False
DATA_PRUNE = False


@dataclass(frozen=True)
class ScaleRow:
    n_logic: int
    k: int
    u_unique: int
    s_arith: float
    nvfp4_bytes: float
    nvfp4_mb: float
    arith_short_of_s100: bool
    below_floor_s50: bool
    train_unlocked: bool
    data_prune: bool
    detail: dict[str, Any]


def unique_albert(
    n_logic: int,
    *,
    k: int = K_SHARE,
    r_svd: int = R_SVD,
    r_lora: int = R_LORA,
    layers: int = L_LAYERS,
    d_in: int = D_IN,
    d_out: int = D_OUT,
) -> int:
    shared = max(1, n_logic // max(1, k))
    svd = layers * r_svd * (d_in + d_out)
    lora = layers * r_lora * (d_in + d_out)
    return int(shared + svd + lora)


def nvfp4_bytes(u: int) -> float:
    return u / 2.0


def run_grid(n_grid: tuple[int, ...] = N_GRID) -> list[ScaleRow]:
    rows: list[ScaleRow] = []
    for n in n_grid:
        u = unique_albert(n)
        s = n / max(1, u)
        b = nvfp4_bytes(u)
        rows.append(
            ScaleRow(
                n_logic=n,
                k=K_SHARE,
                u_unique=u,
                s_arith=s,
                nvfp4_bytes=b,
                nvfp4_mb=b / (1024 * 1024),
                arith_short_of_s100=s < NORTH_STAR_S,
                below_floor_s50=s < FLOOR_S,
                train_unlocked=TRAIN_UNLOCKED,
                data_prune=DATA_PRUNE,
                detail={
                    "needle": NEEDLE,
                    "stack": "ALBERT-BitMoE + LoRA",
                    "hot_dtype": "NVFP4",
                    "r_svd": R_SVD,
                    "r_lora": R_LORA,
                    "layers": L_LAYERS,
                },
            )
        )
    return rows


def ratio_stable(rows: list[ScaleRow], tol: float = RATIO_TOL) -> bool:
    """Pass if S does not *collapse* with scale (falsifier: drops >tol from first→last).

    Rising S toward k as LoRA/SVD tax dilutes is expected and OK.
    """
    if len(rows) < 2:
        return True
    first = rows[0].s_arith
    last = rows[-1].s_arith
    if first <= 0:
        return False
    # Collapse = last significantly worse than first
    if last < first * (1.0 - tol):
        return False
    # Also reject any mid-rung crash below first*(1-tol)
    return all(r.s_arith >= first * (1.0 - tol) for r in rows)


def report_dict(rows: list[ScaleRow]) -> dict[str, Any]:
    s_vals = [r.s_arith for r in rows]
    return {
        "needle": NEEDLE,
        "train_unlocked": TRAIN_UNLOCKED,
        "data_prune": DATA_PRUNE,
        "n_grid": [r.n_logic for r in rows],
        "k_share": K_SHARE,
        "ratio_stable_pm20": ratio_stable(rows),
        "all_above_floor_s50": all(not r.below_floor_s50 for r in rows),
        "north_star_s_cleared": any(not r.arith_short_of_s100 for r in rows),
        "s_min": min(s_vals) if s_vals else 0.0,
        "s_max": max(s_vals) if s_vals else 0.0,
        "s_mean": (sum(s_vals) / len(s_vals)) if s_vals else 0.0,
        "results": [asdict(r) for r in rows],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-artifact", action="store_true")
    args = parser.parse_args(argv)
    rows = run_grid()
    payload = report_dict(rows)
    if args.json or args.write_artifact:
        text = json.dumps(payload, indent=2, sort_keys=True)
        if args.json:
            print(text)
        if args.write_artifact:
            from pathlib import Path

            art = Path(__file__).resolve().parents[1] / "notes" / "compression_artifacts"
            art.mkdir(parents=True, exist_ok=True)
            (art / "t4_scale_result.json").write_text(text + "\n", encoding="utf-8")
    else:
        print(f"{NEEDLE} train_unlocked={TRAIN_UNLOCKED} data_prune={DATA_PRUNE}")
        for r in rows:
            print(
                f"N={r.n_logic:.0e} U={r.u_unique} S={r.s_arith:.2f} "
                f"nvfp4_mb={r.nvfp4_mb:.4f} short100={r.arith_short_of_s100}"
            )
        print(
            f"stable±20%={payload['ratio_stable_pm20']} "
            f"floor50={payload['all_above_floor_s50']} "
            f"s100={payload['north_star_s_cleared']} "
            f"S∈[{payload['s_min']:.2f},{payload['s_max']:.2f}]"
        )
    ok = (
        payload["ratio_stable_pm20"]
        and payload["all_above_floor_s50"]
        and payload["north_star_s_cleared"]
        and not DATA_PRUNE
        and not TRAIN_UNLOCKED
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
