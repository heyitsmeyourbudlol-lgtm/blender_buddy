#!/usr/bin/env python3
"""T3 BitDistill — teacher logit bank → shared student KD (toy; no real train).

OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05
OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05

Teacher: independent-layer linear heads (dense unique).
Student: SVD-TieStack body + per-layer LoRA under fixed U (T2 spirit).
Logit bank: cache teacher logits on the **full** toy corpus (no example prune).
BitDistill: GD on LoRA factors to match teacher logits (MSE KD proxy).
Durable cache: dump/load JSON bank (Lane U research-speed) — not a train unlock.

Pass: heldout KD ≤ ε AND U_student ≤ U_budget AND KD beats weight-only baseline
      AND prune-control does **not** pass (falsifier check).
Falsifier: gap only closes by raising U or pruning data → stop/redesign.
Quality = proxy (toy logits — not LM). TRAIN-LOCKED.

Torch-free. CPU synthetic.

Usage::

    python3 scripts/compression_t3_bitdistill.py
    python3 scripts/compression_t3_bitdistill.py --json
    python3 scripts/compression_t3_bitdistill.py --write-bank /tmp/t3_bank.json
    python3 scripts/compression_t3_bitdistill.py --read-bank /tmp/t3_bank.json --json
    python3 scripts/compression_t3_bitdistill.py --check-cache
    python3 scripts/compression_t3_bitdistill.py --check-cache notes/compression_artifacts/t3_teacher_logit_bank.json --json
    python3 scripts/compression_t3_bitdistill.py --ensure-default-bank --json

Bare ``--check-cache`` verifies the canonical default bank (T0 ``--check-cache``
parity) — not an in-memory synth roundtrip.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05
NEEDLE = "OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05"
# OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05
CACHE_NEEDLE = "OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05"

_ROOT = Path(__file__).resolve().parents[1]
# Canonical Lane-U bank (repo-relative; TRAIN still LOCKED — not a train unlock)
DEFAULT_BANK_PATH = _ROOT / "notes" / "compression_artifacts" / "t3_teacher_logit_bank.json"

D_IN = 8
D_OUT = 4
LAYERS = 8
LORA_R = 2
SVD_RANK = 2
N_EXAMPLES = 64  # full corpus — never prune for the primary path
HELD_FRAC = 0.5
SEED = 20260905
KD_EPS = 0.15  # absolute heldout MSE on logits (proxy)
KD_STEPS = 100
KD_LR = 0.1
META_HEADER_BYTES = 16
META_BOUND_BYTES = 64
N_L_PACK = 100_000


@dataclass(frozen=True)
class MethodResult:
    method: str
    u_unique: int
    u_teacher: int
    heldout_kd_mse: float
    train_kd_mse: float
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


def u_teacher(layers: int = LAYERS, d_in: int = D_IN, d_out: int = D_OUT) -> int:
    return layers * d_in * d_out


def u_student(
    layers: int = LAYERS,
    d_in: int = D_IN,
    d_out: int = D_OUT,
    svd_r: int = SVD_RANK,
    lora_r: int = LORA_R,
) -> int:
    """SVD-TieStack body + per-layer LoRA."""
    return svd_r * (d_in + d_out) + svd_r + layers * lora_r * (d_in + d_out)


def synth_teacher_and_bank(
    seed: int = SEED,
) -> tuple[list[list[list[float]]], list[list[float]], list[list[list[float]]]]:
    state = seed & 0xFFFFFFFF or 1
    teachers: list[list[list[float]]] = []
    for _ in range(LAYERS):
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


def dump_logit_bank(
    path: str | Path,
    teachers: list[list[list[float]]],
    xs: list[list[float]],
    bank: list[list[list[float]]],
    *,
    seed: int = SEED,
) -> Path:
    """Persist full-corpus teacher logit bank (no prune). TRAIN still LOCKED."""
    out = Path(path)
    payload = {
        "needle": NEEDLE,
        "cache_needle": CACHE_NEEDLE,
        "seed": seed,
        "d_in": D_IN,
        "d_out": D_OUT,
        "layers": LAYERS,
        "n_examples": N_EXAMPLES,
        "teachers": teachers,
        "xs": xs,
        "bank": bank,
        "train_unlocked": False,
        "data_prune": False,
        "quality": "proxy",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return out


# Alias used by CLI / older call sites
write_logit_bank = dump_logit_bank


def load_logit_bank(
    path: str | Path,
) -> tuple[list[list[list[float]]], list[list[float]], list[list[list[float]]]]:
    """Reload durable teacher logit bank; refuse pruned / wrong-geometry caches."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("needle") not in (None, NEEDLE):
        raise ValueError(f"refusing bank with foreign needle: {data.get('needle')!r}")
    if data.get("cache_needle") != CACHE_NEEDLE:
        raise ValueError(
            f"refusing bank missing cache_needle={CACHE_NEEDLE!r} "
            f"(got {data.get('cache_needle')!r})"
        )
    if data.get("data_prune") is True:
        raise ValueError("refusing pruned logit bank cache")
    if data.get("train_unlocked") is True:
        raise ValueError("refusing train-unlocked bank cache (recipe LOCKED)")
    if (
        int(data.get("d_in", -1)) != D_IN
        or int(data.get("d_out", -1)) != D_OUT
        or int(data.get("layers", -1)) != LAYERS
        or int(data.get("n_examples", -1)) != N_EXAMPLES
    ):
        raise ValueError("logit bank geometry mismatch vs probe constants")
    teachers = data["teachers"]
    xs = data["xs"]
    bank = data["bank"]
    if len(teachers) != LAYERS or len(xs) != N_EXAMPLES or len(bank) != LAYERS:
        raise ValueError("logit bank length mismatch")
    if any(len(layer) != N_EXAMPLES for layer in bank):
        raise ValueError("logit bank missing full-corpus rows (possible prune)")
    return teachers, xs, bank


def check_bank_at_path(path: str | Path, *, atol: float = 1e-12) -> bool:
    """Verify durable bank at PATH: load→KD pass + reload KD match. TRAIN LOCKED."""
    teachers, xs, bank = load_logit_bank(path)
    fresh = run_compare(teachers=teachers, xs=xs, bank=bank)
    t2, x2, b2 = load_logit_bank(path)
    cached = run_compare(teachers=t2, xs=x2, bank=b2)
    return (
        abs(fresh[0].heldout_kd_mse - cached[0].heldout_kd_mse) <= atol
        and abs(fresh[0].train_kd_mse - cached[0].train_kd_mse) <= atol
        and fresh[0].passed
        and cached[0].passed
        and (not fresh[1].passed)
        and (not cached[1].passed)
        and (not fresh[0].data_prune)
    )


def bank_cache_roundtrip_ok(*, atol: float = 1e-12) -> bool:
    """Fresh synth → dump → load → KD must match (Lane U teacher-logit cache)."""
    import tempfile

    teachers, xs, bank = synth_teacher_and_bank()
    fresh = run_compare(teachers=teachers, xs=xs, bank=bank)
    with tempfile.TemporaryDirectory(prefix="t3_logit_bank_") as td:
        path = Path(td) / "bank.json"
        dump_logit_bank(path, teachers, xs, bank)
        t2, x2, b2 = load_logit_bank(path)
        cached = run_compare(teachers=t2, xs=x2, bank=b2)
    return (
        abs(fresh[0].heldout_kd_mse - cached[0].heldout_kd_mse) <= atol
        and abs(fresh[0].train_kd_mse - cached[0].train_kd_mse) <= atol
        and fresh[0].passed
        and cached[0].passed
        and (not fresh[1].passed)
        and (not cached[1].passed)
    )


def ensure_default_bank(
    path: Path | None = None, *, atol: float = 1e-12
) -> tuple[Path, bool]:
    """Dump canonical repo bank + prove load→KD match. TRAIN still LOCKED."""
    out = Path(path) if path is not None else DEFAULT_BANK_PATH
    teachers, xs, bank = synth_teacher_and_bank()
    fresh = run_compare(teachers=teachers, xs=xs, bank=bank)
    dump_logit_bank(out, teachers, xs, bank)
    meta = json.loads(out.read_text(encoding="utf-8"))
    if meta.get("train_unlocked") is True or meta.get("data_prune") is True:
        return out, False
    if meta.get("cache_needle") != CACHE_NEEDLE:
        return out, False
    t2, x2, b2 = load_logit_bank(out)
    cached = run_compare(teachers=t2, xs=x2, bank=b2)
    ok = (
        abs(fresh[0].heldout_kd_mse - cached[0].heldout_kd_mse) <= atol
        and abs(fresh[0].train_kd_mse - cached[0].train_kd_mse) <= atol
        and fresh[0].passed
        and cached[0].passed
        and (not fresh[1].passed)
        and (not cached[1].passed)
        and (not fresh[0].data_prune)
    )
    return out, ok


def build_shared_body(teachers: list[list[list[float]]]) -> list[list[float]]:
    mean = _mean_mat(teachers)
    u, s, vt = truncated_svd(mean, rank=SVD_RANK, iters=48)
    return reconstruct_svd(u, s, vt)


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
    body: list[list[float]],
    xs_train: list[list[float]],
    teacher_logits_train: list[list[float]],
    rank: int = LORA_R,
    steps: int = KD_STEPS,
    lr: float = KD_LR,
) -> list[list[float]]:
    """BitDistill: GD on LoRA factors vs teacher logit bank (train split)."""
    n = len(xs_train)
    if n == 0:
        return _zeros(D_OUT, D_IN)
    acc = _zeros(D_OUT, D_IN)
    for x, t_logit in zip(xs_train, teacher_logits_train):
        body_logit = _matvec(body, x)
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
            pred = _matvec(_add_mat(body, lora), x)
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


def run_compare(
    teachers: list[list[list[float]]] | None = None,
    xs: list[list[float]] | None = None,
    bank: list[list[list[float]]] | None = None,
) -> list[MethodResult]:
    """Primary BitDistill student + prune-control (must fail)."""
    if teachers is None or xs is None or bank is None:
        teachers, xs, bank = synth_teacher_and_bank()
    body = build_shared_body(teachers)
    u_t = u_teacher()
    u_s = u_student()
    u_budget = u_s  # held fixed — never raise for pass
    n_hold = int(N_EXAMPLES * HELD_FRAC)
    xs_train, xs_hold = xs[: N_EXAMPLES - n_hold], xs[N_EXAMPLES - n_hold :]

    base_h: list[float] = []
    base_tr: list[float] = []
    kd_h: list[float] = []
    kd_tr: list[float] = []
    # Prune cheat: train+eval only on first quarter of corpus
    prune_n = max(1, N_EXAMPLES // 4)
    xs_prune = xs[:prune_n]
    prune_h: list[float] = []

    for li, w_t in enumerate(teachers):
        residual = _sub_mat(w_t, body)
        w_base = _add_mat(body, fit_lora_weight(residual))
        t_train = bank[li][: N_EXAMPLES - n_hold]
        t_hold = bank[li][N_EXAMPLES - n_hold :]
        base_tr.append(kd_mse(w_base, xs_train, t_train))
        base_h.append(kd_mse(w_base, xs_hold, t_hold))

        lora_kd = fit_lora_kd(body, xs_train, t_train)
        w_kd = _add_mat(body, lora_kd)
        kd_tr.append(kd_mse(w_kd, xs_train, t_train))
        kd_h.append(kd_mse(w_kd, xs_hold, t_hold))

        # Prune control: fit KD only on pruned slice, eval on same pruned slice
        t_prune = bank[li][:prune_n]
        lora_p = fit_lora_kd(body, xs_prune, t_prune, steps=40)
        w_p = _add_mat(body, lora_p)
        prune_h.append(kd_mse(w_p, xs_prune, t_prune))

    base_held = sum(base_h) / len(base_h)
    kd_held = sum(kd_h) / len(kd_h)
    kd_train = sum(kd_tr) / len(kd_tr)
    prune_mse = sum(prune_h) / len(prune_h)

    payload_b, packed_b = _pack_1bit(u_s)
    pass_pack = _pass_pack(u_s, packed_b)
    pass_u = u_s <= u_budget
    pass_kd = kd_held <= KD_EPS
    pass_vs = kd_held < base_held - 1e-12

    student = MethodResult(
        method="BitDistill-logit-bank+LoRA",
        u_unique=u_s,
        u_teacher=u_t,
        heldout_kd_mse=kd_held,
        train_kd_mse=kd_train,
        packed_bytes=packed_b,
        payload_bytes=payload_b,
        pass_u_budget=pass_u,
        pass_kd=pass_kd,
        pass_vs_baseline=pass_vs,
        pass_pack=pass_pack,
        data_prune=False,
        passed=pass_pack and pass_u and pass_kd and pass_vs,
        quality="proxy",
        detail={
            "role": "bitdistill_student",
            "kd_eps": KD_EPS,
            "n_examples_full": N_EXAMPLES,
            "held_frac": HELD_FRAC,
            "svd_rank": SVD_RANK,
            "lora_r": LORA_R,
            "u_budget": u_budget,
            "baseline_heldout_kd": base_held,
            "falsifier_raise_u": False,
            "falsifier_data_prune": False,
        },
    )
    # Prune control must NOT count as a valid pass path even if MSE looks good
    prune_looks_ok = prune_mse <= KD_EPS
    prune = MethodResult(
        method="prune-cheat-control",
        u_unique=u_s,
        u_teacher=u_t,
        heldout_kd_mse=prune_mse,  # evaluated on pruned slice only
        train_kd_mse=prune_mse,
        packed_bytes=packed_b,
        payload_bytes=payload_b,
        pass_u_budget=pass_u,
        pass_kd=prune_looks_ok,
        pass_vs_baseline=False,
        pass_pack=pass_pack,
        data_prune=True,
        passed=False,  # always fail — data prune forbidden
        quality="proxy",
        detail={
            "role": "prune_control",
            "n_examples_used": prune_n,
            "n_examples_full": N_EXAMPLES,
            "note": "forbidden path — KD on pruned slice only",
        },
    )
    return [student, prune]


def summary_dict(
    rows: list[MethodResult] | None = None,
    *,
    bank_source: str = "synth",
    bank_cache_ok: bool | None = None,
) -> dict[str, Any]:
    if rows is None:
        rows = run_compare()
    student, prune = rows[0], rows[1]
    return {
        "needle": NEEDLE,
        "cache_needle": CACHE_NEEDLE,
        "geometry": {
            "d_in": D_IN,
            "d_out": D_OUT,
            "layers": LAYERS,
            "svd_rank": SVD_RANK,
            "lora_r": LORA_R,
            "n_examples": N_EXAMPLES,
            "held_frac": HELD_FRAC,
            "kd_eps": KD_EPS,
            "n_l_pack": N_L_PACK,
        },
        "u_teacher": student.u_teacher,
        "u_student": student.u_unique,
        "u_budget": student.detail["u_budget"],
        "compression_vs_teacher": student.u_teacher / float(student.u_unique),
        "heldout_kd_bitdistill": student.heldout_kd_mse,
        "heldout_kd_baseline": student.detail["baseline_heldout_kd"],
        "pass_kd": student.pass_kd,
        "u_within_budget": student.pass_u_budget,
        "kd_improved": student.pass_vs_baseline,
        "quality": "proxy",
        "train_unlocked": False,
        "data_prune": False,
        "prune_control_passed": prune.passed,
        "bank_source": bank_source,
        "bank_cache_ok": bank_cache_ok,
        "all_passed": student.passed and (not prune.passed),
        "results": [asdict(r) for r in rows],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="T3 BitDistill logit-bank toy probe")
    p.add_argument("--json", action="store_true", help="print JSON summary only")
    p.add_argument(
        "--write-bank",
        metavar="PATH",
        help="dump durable teacher logit bank JSON (full corpus; TRAIN-LOCKED)",
    )
    p.add_argument(
        "--read-bank",
        metavar="PATH",
        help="load durable teacher logit bank JSON instead of synth",
    )
    p.add_argument(
        "--check-cache",
        metavar="PATH",
        nargs="?",
        const="",
        help=(
            "verify durable bank at PATH (Lane U); bare flag → "
            f"{DEFAULT_BANK_PATH.name} (parity with T0 --check-cache → default pack)"
        ),
    )
    p.add_argument(
        "--ensure-default-bank",
        action="store_true",
        help=(
            f"dump+verify canonical bank at {DEFAULT_BANK_PATH.name} "
            "(notes/compression_artifacts/; TRAIN-LOCKED)"
        ),
    )
    args = p.parse_args(argv)

    bank_source = "synth"
    teachers: list[list[list[float]]] | None = None
    xs: list[list[float]] | None = None
    bank: list[list[list[float]]] | None = None
    default_bank_ok: bool | None = None
    check_path: str | None = None
    bank_cache_error: str | None = None
    if args.ensure_default_bank:
        _path, default_bank_ok = ensure_default_bank()
        teachers, xs, bank = load_logit_bank(_path)
        bank_source = "default_bank"
        # T0 --ensure-default-pack emits pack_path; keep Lane-U JSON parity
        check_path = str(_path)
    elif args.read_bank:
        teachers, xs, bank = load_logit_bank(args.read_bank)
        bank_source = "cache"
    elif args.check_cache is not None:
        # T0 parity: bare --check-cache → DEFAULT_BANK_PATH (not in-memory synth)
        check_path = args.check_cache or args.write_bank or str(DEFAULT_BANK_PATH)
        if not check_path:
            print(
                "error: --check-cache needs PATH or --write-bank/--ensure",
                file=sys.stderr,
            )
            return 2
        try:
            teachers, xs, bank = load_logit_bank(check_path)
            bank_source = "cache"
        except (OSError, ValueError, KeyError, TypeError):
            # Fall through to synth so JSON still emits; cache_ok set False below
            teachers, xs, bank = synth_teacher_and_bank()
            bank_source = "cache_load_failed"
    elif args.write_bank:
        teachers, xs, bank = synth_teacher_and_bank()

    if args.write_bank:
        assert teachers is not None and xs is not None and bank is not None
        dump_logit_bank(args.write_bank, teachers, xs, bank)
        if check_path is None:
            check_path = str(Path(args.write_bank))

    rows = run_compare(teachers=teachers, xs=xs, bank=bank)
    cache_ok: bool | None = None
    if args.check_cache is not None:
        check_path = args.check_cache or args.write_bank or str(DEFAULT_BANK_PATH)
        try:
            cache_ok = check_bank_at_path(check_path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            cache_ok = False
            bank_cache_error = str(exc)
    if default_bank_ok is not None:
        cache_ok = default_bank_ok if cache_ok is None else (cache_ok and default_bank_ok)
    payload = summary_dict(rows, bank_source=bank_source, bank_cache_ok=cache_ok)
    if check_path:
        payload["bank_path"] = str(check_path)
    if bank_cache_error:
        payload["bank_cache_error"] = bank_cache_error
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not args.json:
        s = rows[0]
        print(
            f"bitdistill_kd={s.heldout_kd_mse:.6f} baseline={s.detail['baseline_heldout_kd']:.6f} "
            f"eps={KD_EPS} improved={s.pass_vs_baseline} "
            f"U_s={s.u_unique} U_t={s.u_teacher} bank={bank_source} "
            f"cache_ok={cache_ok} all_passed={payload['all_passed']} train_unlocked=False",
            file=sys.stderr,
        )
    ok = bool(payload["all_passed"])
    if cache_ok is False:
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
