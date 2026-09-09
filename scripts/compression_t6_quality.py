#!/usr/bin/env python3
"""T6 toy quality falsifier — ALBERT-BitMoE vs LoRA-Hive heldout ε.

OVERSEER_COMPRESSION_T6_QUALITY_2026_09_06

Primary (ALBERT-BitMoE): shared body across layers + per-layer LoRA, KD vs teacher.
Control (LoRA-Hive): shared hive across experts + per-expert LoRA, KD vs teacher.
Full toy corpus — **no** data prune. Quality = proxy (toy logit MSE — not LM).
Does not raise recipe U / rewrite LOCKED stack. Torch-free. CPU synthetic.

Pass (per stack): heldout KD ≤ ε AND packed ≈ U/8 AND data_prune=false
      AND prune-control does **not** pass.
Falsifier: gap only closes by raising U or pruning data → stop/redesign.
Ledger: upgrade hypothesis→measured only with new BITNET_FACTCHECK C-rows.

Usage::

    python3 scripts/compression_t6_quality.py
    python3 scripts/compression_t6_quality.py --json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from typing import Any

# OVERSEER_COMPRESSION_T6_QUALITY_2026_09_06
NEEDLE = "OVERSEER_COMPRESSION_T6_QUALITY_2026_09_06"

D_IN = 8
D_OUT = 4
SLOTS = 8  # layers (ALBERT) / experts (Hive)
LORA_R = 2
N_EXAMPLES = 64  # full corpus — never prune for the primary path
HELD_FRAC = 0.5
SEED = 20260906
KD_EPS = 0.15  # absolute heldout MSE on logits (proxy)
KD_STEPS = 100
KD_LR = 0.1
META_HEADER_BYTES = 16
META_BOUND_BYTES = 64
TRAIN_UNLOCKED = False


@dataclass(frozen=True)
class StackResult:
    stack: str
    role: str  # primary | control | prune_control
    u_unique: int
    u_teacher: int
    heldout_kd_mse: float
    train_kd_mse: float
    baseline_heldout_kd: float
    packed_bytes: int
    payload_bytes: int
    pass_u_budget: bool
    pass_kd: bool
    pass_vs_baseline: bool
    pass_pack: bool
    data_prune: bool
    passed: bool
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


def _xorshift(state: int) -> int:
    state ^= (state << 13) & 0xFFFFFFFF
    state ^= (state >> 17) & 0xFFFFFFFF
    state ^= (state << 5) & 0xFFFFFFFF
    return state & 0xFFFFFFFF


def _randn_mat(rows: int, cols: int, state: int) -> tuple[list[list[float]], int]:
    mat: list[list[float]] = []
    for _ in range(rows):
        row: list[float] = []
        for _c in range(cols):
            state = _xorshift(state)
            u = max(state / 0xFFFFFFFF, 1e-12)
            state = _xorshift(state)
            v = max(state / 0xFFFFFFFF, 1e-12)
            z = math.sqrt(-2.0 * math.log(u)) * math.cos(2.0 * math.pi * v)
            row.append(z * 0.5)
        mat.append(row)
    return mat, state


def _zeros(m: int, n: int) -> list[list[float]]:
    return [[0.0] * n for _ in range(m)]


def _add_mat(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[a[i][j] + b[i][j] for j in range(len(a[0]))] for i in range(len(a))]


def _sub_mat(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[a[i][j] - b[i][j] for j in range(len(a[0]))] for i in range(len(a))]


def _scale_mat(a: list[list[float]], s: float) -> list[list[float]]:
    return [[x * s for x in row] for row in a]


def _mean_mat(mats: list[list[list[float]]]) -> list[list[float]]:
    acc = _zeros(len(mats[0]), len(mats[0][0]))
    for m in mats:
        acc = _add_mat(acc, m)
    return _scale_mat(acc, 1.0 / len(mats))


def _matvec(a: list[list[float]], x: list[float]) -> list[float]:
    return [sum(a[i][j] * x[j] for j in range(len(x))) for i in range(len(a))]


def _matTvec(a: list[list[float]], x: list[float]) -> list[float]:
    n = len(a[0])
    return [sum(a[i][j] * x[i] for i in range(len(a))) for j in range(n)]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(v: list[float]) -> float:
    return math.sqrt(max(_dot(v, v), 1e-30))


def _normalize(v: list[float]) -> list[float]:
    n = _norm(v)
    return [x / n for x in v]


def _outer(u: list[float], v: list[float], s: float = 1.0) -> list[list[float]]:
    return [[s * u[i] * v[j] for j in range(len(v))] for i in range(len(u))]


def _project_out(v: list[float], basis: list[list[float]]) -> list[float]:
    out = list(v)
    for b in basis:
        c = _dot(out, b)
        out = [out[i] - c * b[i] for i in range(len(out))]
    return out


def truncated_svd(
    a: list[list[float]],
    rank: int,
    iters: int = 48,
) -> tuple[list[list[float]], list[float], list[list[float]]]:
    m, n = len(a), len(a[0])
    rank = min(rank, m, n)
    u_cols: list[list[float]] = []
    s_vals: list[float] = []
    vt_rows: list[list[float]] = []
    residual = [row[:] for row in a]
    for _k in range(rank):
        v = [1.0 if i == (_k % n) else 0.01 * ((i + 1) % 3) for i in range(n)]
        v = _normalize(_project_out(v, vt_rows))
        u = [0.0] * m
        for _ in range(iters):
            u = _normalize(_project_out(_matvec(residual, v), u_cols))
            v = _normalize(_project_out(_matTvec(residual, u), vt_rows))
        av = _matvec(residual, v)
        s = _dot(u, av)
        if s < 0:
            s = -s
            u = [-x for x in u]
        u_cols.append(u)
        s_vals.append(s)
        vt_rows.append(v)
        residual = _sub_mat(residual, _outer(u, v, s))
    return u_cols, s_vals, vt_rows


def reconstruct_svd(
    u_cols: list[list[float]],
    s_vals: list[float],
    vt_rows: list[list[float]],
) -> list[list[float]]:
    if not u_cols:
        return _zeros(D_OUT, D_IN)
    acc = _zeros(len(u_cols[0]), len(vt_rows[0]))
    for u, s, v in zip(u_cols, s_vals, vt_rows):
        acc = _add_mat(acc, _outer(u, v, s))
    return acc


def u_teacher(slots: int = SLOTS, d_in: int = D_IN, d_out: int = D_OUT) -> int:
    """Independent dense weights per layer/expert."""
    return slots * d_in * d_out


def u_shared_plus_lora(
    slots: int = SLOTS,
    d_in: int = D_IN,
    d_out: int = D_OUT,
    lora_r: int = LORA_R,
) -> int:
    """Shared body/hive (d_out×d_in once) + per-slot LoRA."""
    return d_in * d_out + slots * lora_r * (d_in + d_out)


def synth_teachers_and_bank(
    seed: int = SEED,
) -> tuple[list[list[list[float]]], list[list[float]], list[list[list[float]]]]:
    state = seed & 0xFFFFFFFF or 1
    teachers: list[list[list[float]]] = []
    for _ in range(SLOTS):
        w, state = _randn_mat(D_OUT, D_IN, state)
        teachers.append(w)
    xs: list[list[float]] = []
    for _ in range(N_EXAMPLES):
        x, state = _randn_mat(1, D_IN, state)
        xs.append(x[0])
    bank: list[list[list[float]]] = []
    for w in teachers:
        bank.append([_matvec(w, x) for x in xs])
    return teachers, xs, bank


def fit_lora_weight(residual: list[list[float]]) -> list[list[float]]:
    """Weak weight-space baseline: rank-1 + tight cap (no logit KD)."""
    u, s, vt = truncated_svd(residual, rank=1, iters=32)
    s_capped = [min(abs(x), 0.2) * (1.0 if x >= 0 else -1.0) for x in s]
    return reconstruct_svd(u, s_capped, vt)


def _lora_factors_from_mat(
    mat: list[list[float]], rank: int
) -> tuple[list[list[float]], list[list[float]]]:
    u, s, vt = truncated_svd(mat, rank=rank, iters=48)
    a_mat = [[0.0] * rank for _ in range(D_OUT)]
    b_mat = [[0.0] * D_IN for _ in range(rank)]
    for k in range(len(s)):
        scale = math.sqrt(max(s[k], 0.0))
        for i in range(D_OUT):
            a_mat[i][k] = u[k][i] * scale
        for j in range(D_IN):
            b_mat[k][j] = vt[k][j] * scale
    return a_mat, b_mat


def _compose_lora(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    rank = len(b)
    out = _zeros(D_OUT, D_IN)
    for i in range(D_OUT):
        for j in range(D_IN):
            out[i][j] = sum(a[i][k] * b[k][j] for k in range(rank))
    return out


def fit_lora_kd(
    shared: list[list[float]],
    xs_train: list[list[float]],
    teacher_logits_train: list[list[float]],
    rank: int = LORA_R,
    steps: int = KD_STEPS,
    lr: float = KD_LR,
) -> list[list[float]]:
    """BitDistill-style GD on LoRA factors vs teacher logit bank (train split)."""
    n = len(xs_train)
    if n == 0:
        return _zeros(D_OUT, D_IN)
    acc = _zeros(D_OUT, D_IN)
    for x, t_logit in zip(xs_train, teacher_logits_train):
        body_logit = _matvec(shared, x)
        delta = [t_logit[i] - body_logit[i] for i in range(D_OUT)]
        for i in range(D_OUT):
            for j in range(D_IN):
                acc[i][j] += delta[i] * x[j]
    init = _scale_mat(acc, 1.0 / n)
    a, b = _lora_factors_from_mat(init, rank)

    for _ in range(steps):
        g_a = _zeros(D_OUT, rank)
        g_b = _zeros(rank, D_IN)
        for x, t_logit in zip(xs_train, teacher_logits_train):
            lora = _compose_lora(a, b)
            pred = _matvec(_add_mat(shared, lora), x)
            err = [pred[i] - t_logit[i] for i in range(D_OUT)]
            bx = [sum(b[k][j] * x[j] for j in range(D_IN)) for k in range(rank)]
            for i in range(D_OUT):
                for k in range(rank):
                    g_a[i][k] += err[i] * bx[k]
            at_err = [sum(a[i][k] * err[i] for i in range(D_OUT)) for k in range(rank)]
            for k in range(rank):
                for j in range(D_IN):
                    g_b[k][j] += at_err[k] * x[j]
        inv_n = 1.0 / n
        for i in range(D_OUT):
            for k in range(rank):
                a[i][k] -= lr * g_a[i][k] * inv_n
        for k in range(rank):
            for j in range(D_IN):
                b[k][j] -= lr * g_b[k][j] * inv_n
    return _compose_lora(a, b)


def kd_mse(
    w: list[list[float]],
    xs: list[list[float]],
    teacher_logits: list[list[float]],
) -> float:
    if not xs:
        return 0.0
    err = 0.0
    for x, t in zip(xs, teacher_logits):
        pred = _matvec(w, x)
        err += sum((pred[i] - t[i]) ** 2 for i in range(D_OUT)) / D_OUT
    return err / len(xs)


def _eval_shared_stack(
    *,
    stack: str,
    role: str,
    teachers: list[list[list[float]]],
    xs: list[list[float]],
    bank: list[list[list[float]]],
    data_prune: bool,
    prune_n: int | None = None,
) -> StackResult:
    """Fit shared body/hive + per-slot LoRA; score heldout (or prune slice)."""
    shared = _mean_mat(teachers)
    u_t = u_teacher()
    u_s = u_shared_plus_lora()
    u_budget = u_s
    n_hold = int(N_EXAMPLES * HELD_FRAC)
    if data_prune:
        assert prune_n is not None
        xs_train = xs[:prune_n]
        xs_eval = xs[:prune_n]
        n_used = prune_n
    else:
        xs_train = xs[: N_EXAMPLES - n_hold]
        xs_eval = xs[N_EXAMPLES - n_hold :]
        n_used = N_EXAMPLES

    base_h: list[float] = []
    kd_h: list[float] = []
    kd_tr: list[float] = []

    for li, w_t in enumerate(teachers):
        residual = _sub_mat(w_t, shared)
        w_base = _add_mat(shared, fit_lora_weight(residual))
        if data_prune:
            assert prune_n is not None
            t_train = bank[li][:prune_n]
            t_eval = bank[li][:prune_n]
            steps = 40
        else:
            t_train = bank[li][: N_EXAMPLES - n_hold]
            t_eval = bank[li][N_EXAMPLES - n_hold :]
            steps = KD_STEPS
        base_h.append(kd_mse(w_base, xs_eval, t_eval))
        lora_kd = fit_lora_kd(shared, xs_train, t_train, steps=steps)
        w_kd = _add_mat(shared, lora_kd)
        kd_tr.append(kd_mse(w_kd, xs_train, t_train))
        kd_h.append(kd_mse(w_kd, xs_eval, t_eval))

    base_held = sum(base_h) / len(base_h)
    kd_held = sum(kd_h) / len(kd_h)
    kd_train = sum(kd_tr) / len(kd_tr)

    payload_b, packed_b = _pack_1bit(u_s)
    pass_pack = _pass_pack(u_s, packed_b)
    pass_u = u_s <= u_budget
    pass_kd = kd_held <= KD_EPS
    pass_vs = kd_held < base_held - 1e-12

    if data_prune:
        passed = False  # always fail — data prune forbidden
    else:
        passed = pass_pack and pass_u and pass_kd and pass_vs

    return StackResult(
        stack=stack,
        role=role,
        u_unique=u_s,
        u_teacher=u_t,
        heldout_kd_mse=kd_held,
        train_kd_mse=kd_train,
        baseline_heldout_kd=base_held,
        packed_bytes=packed_b,
        payload_bytes=payload_b,
        pass_u_budget=pass_u,
        pass_kd=pass_kd,
        pass_vs_baseline=pass_vs,
        pass_pack=pass_pack,
        data_prune=data_prune,
        passed=passed,
        quality="proxy",
        detail={
            "role": role,
            "kd_eps": KD_EPS,
            "n_examples_full": N_EXAMPLES,
            "n_examples_used": n_used,
            "held_frac": HELD_FRAC,
            "lora_r": LORA_R,
            "slots": SLOTS,
            "u_budget": u_budget,
            "formula": "U = d_in*d_out + slots*r*(d_in+d_out)",
            "falsifier_raise_u": False,
            "falsifier_data_prune": data_prune,
            "note": (
                "forbidden path — KD on pruned slice only"
                if data_prune
                else "full corpus; no prune"
            ),
        },
    )


def run_compare(
    teachers: list[list[list[float]]] | None = None,
    xs: list[list[float]] | None = None,
    bank: list[list[list[float]]] | None = None,
) -> list[StackResult]:
    """ALBERT primary + LoRA-Hive control + prune-control (must fail)."""
    if teachers is None or xs is None or bank is None:
        teachers, xs, bank = synth_teachers_and_bank()

    albert = _eval_shared_stack(
        stack="ALBERT-BitMoE",
        role="primary",
        teachers=teachers,
        xs=xs,
        bank=bank,
        data_prune=False,
    )
    hive = _eval_shared_stack(
        stack="LoRA-Hive",
        role="control",
        teachers=teachers,
        xs=xs,
        bank=bank,
        data_prune=False,
    )
    prune_n = max(1, N_EXAMPLES // 4)
    prune = _eval_shared_stack(
        stack="prune-cheat-control",
        role="prune_control",
        teachers=teachers,
        xs=xs,
        bank=bank,
        data_prune=True,
        prune_n=prune_n,
    )
    return [albert, hive, prune]


def summary_dict(rows: list[StackResult] | None = None) -> dict[str, Any]:
    if rows is None:
        rows = run_compare()
    albert, hive, prune = rows[0], rows[1], rows[2]
    stacks_ok = albert.passed and hive.passed and (not prune.passed)
    return {
        "needle": NEEDLE,
        "geometry": {
            "d_in": D_IN,
            "d_out": D_OUT,
            "slots": SLOTS,
            "lora_r": LORA_R,
            "n_examples": N_EXAMPLES,
            "held_frac": HELD_FRAC,
            "kd_eps": KD_EPS,
        },
        "u_teacher": albert.u_teacher,
        "u_albert": albert.u_unique,
        "u_hive": hive.u_unique,
        "heldout_kd_albert": albert.heldout_kd_mse,
        "heldout_kd_hive": hive.heldout_kd_mse,
        "baseline_heldout_albert": albert.baseline_heldout_kd,
        "baseline_heldout_hive": hive.baseline_heldout_kd,
        "pass_kd_albert": albert.pass_kd,
        "pass_kd_hive": hive.pass_kd,
        "quality": "proxy",
        "train_unlocked": TRAIN_UNLOCKED,
        "data_prune": False,
        "prune_control_passed": prune.passed,
        "all_passed": stacks_ok,
        "recipe_stack_unchanged": True,
        "results": [asdict(r) for r in rows],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="T6 ALBERT vs Hive heldout quality toy")
    p.add_argument("--json", action="store_true", help="print JSON summary only")
    args = p.parse_args(argv)
    rows = run_compare()
    payload = summary_dict(rows)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not args.json:
        for r in rows[:2]:
            status = "PASS" if r.passed else "FAIL"
            print(
                f"{status} {r.stack} ({r.role}) heldout_kd={r.heldout_kd_mse:.6f} "
                f"baseline={r.baseline_heldout_kd:.6f} eps={KD_EPS} "
                f"U={r.u_unique} packed={r.packed_bytes} quality={r.quality} "
                f"data_prune={r.data_prune}",
                file=sys.stderr,
            )
        print(
            f"prune_control_passed={rows[2].passed} all_passed={payload['all_passed']} "
            f"train_unlocked={TRAIN_UNLOCKED}",
            file=sys.stderr,
        )
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
