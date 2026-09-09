#!/usr/bin/env python3
"""Arith-only stack prefilter before any quality/GPU research run.

OVERSEER_RESEARCH_CLAIM_ARITH_2026_09_08

Research-speed S06 / S11 / S12 / S14 (notes/RESEARCH_SPEED_TRAINING.md).
Torch-free. Closed-form U, S=N/U, bytes@1-bit for ALBERT-BitMoE / LoRA-Hive /
raw symbols. Optional ledger scaffold + claim-ID range split for peer fanout.
Fail-closed on arith contradiction. Does **not** unlock train or prune data.

Usage::

    python3 scripts/research_claim_arith.py --stack albert --n 100000
    python3 scripts/research_claim_arith.py --stack hive --n 1000000 --json
    python3 scripts/research_claim_arith.py --raw --n 1e6 --u 10200 --json
    python3 scripts/research_claim_arith.py --probe --write
    python3 scripts/research_claim_arith.py --scaffold --claim-range 200 203
    python3 scripts/research_claim_arith.py --ensure-default --json
    python3 scripts/research_claim_arith.py --check-cache --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

# OVERSEER_RESEARCH_CLAIM_ARITH_2026_09_08
NEEDLE = "OVERSEER_RESEARCH_CLAIM_ARITH_2026_09_08"
# Lane-U durable probe report (before/after wall) — not a train unlock.
PROBE_NEEDLE = "OVERSEER_RESEARCH_CLAIM_ARITH_PROBE_2026_09_08"

MIN_ARITH = 50.0
META_HEADER_BYTES = 16
META_BOUND_BYTES = 64
TRAIN_UNLOCKED = False
BLOCKS_RUNG0 = False
RECIPE_LOCKED = True

ARTIFACT_REL = Path("notes/compression_artifacts/claim_arith_report.json")
PROBE_REL = Path("notes/compression_artifacts/claim_arith_probe.json")

# Default T1-ish share×rank screen for --probe (prefilter vs full quality proxy).
PROBE_K_LEVELS = (2, 4, 8, 16, 50, 100, 125, 200)
PROBE_R_LEVELS = (1, 2, 4, 8, 16, 32)
# Synthetic body size for share-factor arith (matches T0 body share intuition).
PROBE_N_LOGIC = 100_000
PROBE_LAYERS = 100


@dataclass(frozen=True)
class ArithResult:
    stack: str
    n_logic: float
    u_unique: float
    s_arith: float
    payload_bytes: int
    packed_bytes: int
    pass_arith: bool
    pass_pack: bool
    passed: bool
    quality: str  # always UNKNOWN until ledger upgrade
    detail: dict[str, Any]
    contradiction: str | None = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _pack_1bit(u: int, meta_bytes: int = META_HEADER_BYTES) -> tuple[int, int]:
    payload = (int(u) + 7) // 8
    return payload, payload + meta_bytes


def _pass_pack(u: float, packed_bytes: int) -> bool:
    ideal = float(u) / 8.0
    ceil_ideal = (int(u) + 7) // 8
    return (
        abs(packed_bytes - ideal) <= META_BOUND_BYTES
        or abs(packed_bytes - ceil_ideal) <= META_BOUND_BYTES
    )


def albert_closed_form(
    n_logic: float,
    *,
    layers: int = 100,
    r: int = 1,
    lora_d_in: int = 1,
    lora_d_out: int = 1,
) -> ArithResult:
    """U = B_body + L*r*(d_in+d_out); N_L = L*B_body (matches compression_t0_pack)."""
    n = int(n_logic)
    if layers < 1:
        return _fail("albert", n, "layers must be >= 1")
    if n % layers != 0:
        return _fail("ALBERT-BitMoE", n, f"n_logic={n} not divisible by L={layers}")
    body = n // layers
    u_lora = layers * r * (lora_d_in + lora_d_out)
    u = body + u_lora
    return _finish(
        stack="ALBERT-BitMoE",
        n=n,
        u=u,
        detail={
            "L": layers,
            "B_body": body,
            "r": r,
            "lora_d_in": lora_d_in,
            "lora_d_out": lora_d_out,
            "u_lora": u_lora,
            "formula": "U = B_body + L*r*(d_in+d_out); N_L = L*B_body",
        },
    )


def hive_closed_form(
    n_logic: float,
    *,
    experts: int = 100,
    r: int = 1,
    lora_d_in: int = 1,
    lora_d_out: int = 1,
) -> ArithResult:
    """U_e = B_hive/E + r*(d_in+d_out); N_L = B_hive."""
    n = int(n_logic)
    if experts < 1:
        return _fail("LoRA-Hive", n, "experts must be >= 1")
    if n % experts != 0:
        return _fail("LoRA-Hive", n, f"n_logic={n} not divisible by E={experts}")
    u_lora = r * (lora_d_in + lora_d_out)
    u = n // experts + u_lora
    return _finish(
        stack="LoRA-Hive",
        n=n,
        u=u,
        detail={
            "E": experts,
            "B_hive": n,
            "r": r,
            "lora_d_in": lora_d_in,
            "lora_d_out": lora_d_out,
            "u_hive_amortized": n // experts,
            "u_lora_amortized": u_lora,
            "formula": "U_e = B_hive/E + r*(d_in+d_out); N_L = B_hive",
        },
    )


def raw_closed_form(n_logic: float, u_unique: float) -> ArithResult:
    """Given N and U directly — fail-closed if U<=0 or S gate fails."""
    n = float(n_logic)
    u = float(u_unique)
    if u <= 0:
        return _fail("raw", n, "u_unique must be > 0")
    if n <= 0:
        return _fail("raw", n, "n_logic must be > 0")
    return _finish(stack="raw", n=n, u=u, detail={"formula": "S=N/U; bytes=ceil(U/8)+meta"})


def share_rank_closed_form(
    n_logic: float,
    *,
    k: int,
    r: int,
    layers: int = PROBE_LAYERS,
) -> ArithResult:
    """Toy share×rank: B = N/L, U = B/k + L*r*2 — cull when S < MIN_ARITH."""
    n = int(n_logic)
    if k < 1 or r < 0 or layers < 1:
        return _fail("share-rank", n, "k>=1, r>=0, layers>=1 required")
    if n % layers != 0:
        return _fail("share-rank", n, f"n_logic={n} not divisible by L={layers}")
    body = n // layers
    # k = share factor: unique body shrinks as body/k (integer floor).
    u_body = max(1, body // k)
    u_lora = layers * r * 2
    u = u_body + u_lora
    return _finish(
        stack="share-rank",
        n=n,
        u=u,
        detail={
            "k": k,
            "r": r,
            "L": layers,
            "B_body": body,
            "u_body": u_body,
            "u_lora": u_lora,
            "formula": "U = (B_body/k) + L*r*2; N_L = L*B_body",
        },
    )


def _fail(stack: str, n: float, msg: str) -> ArithResult:
    return ArithResult(
        stack=stack,
        n_logic=float(n),
        u_unique=0.0,
        s_arith=0.0,
        payload_bytes=0,
        packed_bytes=0,
        pass_arith=False,
        pass_pack=False,
        passed=False,
        quality="UNKNOWN",
        detail={},
        contradiction=msg,
    )


def _finish(*, stack: str, n: float, u: float, detail: dict[str, Any]) -> ArithResult:
    s = float(n) / float(u)
    payload, packed = _pack_1bit(int(u))
    pass_arith = s >= MIN_ARITH
    pass_pack = _pass_pack(u, packed)
    contradiction = None
    if not pass_arith:
        contradiction = f"S={s:.4f} < MIN_ARITH={MIN_ARITH} (refuse quality/GPU)"
    elif not pass_pack:
        contradiction = f"packed_bytes={packed} outside U/8±{META_BOUND_BYTES}"
    return ArithResult(
        stack=stack,
        n_logic=float(n),
        u_unique=float(u),
        s_arith=s,
        payload_bytes=payload,
        packed_bytes=packed,
        pass_arith=pass_arith,
        pass_pack=pass_pack,
        passed=pass_arith and pass_pack,
        quality="UNKNOWN",
        detail=detail,
        contradiction=contradiction,
    )


def scaffold_rows(
    start_id: int,
    end_id: int,
    *,
    stacks: Sequence[ArithResult] | None = None,
) -> list[dict[str, Any]]:
    """Template falsifier stubs (PASS/SPLIT/FAIL/UNKNOWN) for claim-ID fanout."""
    if end_id < start_id:
        raise ValueError("claim-range end must be >= start")
    rows: list[dict[str, Any]] = []
    stack_cycle = list(stacks or [])
    for i, cid in enumerate(range(start_id, end_id + 1)):
        base = stack_cycle[i % len(stack_cycle)] if stack_cycle else None
        rows.append(
            {
                "id": f"C{cid}",
                "claim": (
                    f"Stack arith prefilter {base.stack} N={base.n_logic} U={base.u_unique}"
                    if base
                    else f"Claim C{cid} arith/quality stub (fill after scrape)"
                ),
                "verdict": "UNKNOWN",
                "quality": "UNKNOWN",
                "arith_passed": bool(base.passed) if base else None,
                "s_arith": base.s_arith if base else None,
                "falsifier_stub": "PASS|SPLIT|FAIL|UNKNOWN — fill after primary URL",
                "peer_range": f"C{start_id}-C{end_id}",
            }
        )
    return rows


def probe_prefilter_vs_full(
    *,
    k_levels: Sequence[int] = PROBE_K_LEVELS,
    r_levels: Sequence[int] = PROBE_R_LEVELS,
    n_logic: int = PROBE_N_LOGIC,
    quality_proxy_ms: float = 0.05,
    wall: bool = True,
) -> dict[str, Any]:
    """Measure before/after: full k×r quality-proxy cost vs arith-prefilter cull.

    Primary metric is **logical cost units** (deterministic): before = grid_n,
    after = after_pass (rejects pay 0 quality). Optional wall sleep mirrors the
    same accounting for a live wall-clock check when ``wall=True``.
    """
    grid = [(k, r) for k in k_levels for r in r_levels]
    sleep_s = max(0.0, float(quality_proxy_ms) / 1000.0)

    t0 = time.perf_counter()
    before_results: list[ArithResult] = []
    for k, r in grid:
        # Simulate "would run quality" — still compute arith for labeling, but
        # before-path charges quality for *every* cell.
        before_results.append(share_rank_closed_form(n_logic, k=k, r=r))
        if wall and sleep_s:
            time.sleep(sleep_s)
    before_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    after_pass = 0
    after_reject = 0
    after_results: list[ArithResult] = []
    for k, r in grid:
        row = share_rank_closed_form(n_logic, k=k, r=r)
        after_results.append(row)
        if row.passed:
            after_pass += 1
            if wall and sleep_s:
                time.sleep(sleep_s)
        else:
            after_reject += 1
    after_s = time.perf_counter() - t1

    before_units = float(len(grid))
    after_units = float(after_pass)  # rejects skip quality
    unit_speedup = (before_units / after_units) if after_units > 0 else None
    wall_speedup = (before_s / after_s) if after_s > 0 else None
    # Prefer deterministic unit speedup as approx_speedup (anti-flake).
    speedup = unit_speedup
    return {
        "needle": PROBE_NEEDLE,
        "parent_needle": NEEDLE,
        "refs": {"S06": "arith prefilter", "S14": "closed-form U/S/bytes"},
        "grid_n": len(grid),
        "n_logic": n_logic,
        "quality_proxy_ms": quality_proxy_ms,
        "before_cost_units": before_units,
        "after_cost_units": after_units,
        "unit_speedup": round(unit_speedup, 3) if unit_speedup else None,
        "before_wall_sec": round(before_s, 6),
        "after_wall_sec": round(after_s, 6),
        "wall_speedup": round(wall_speedup, 3) if wall_speedup else None,
        "approx_speedup": round(speedup, 3) if speedup else None,
        "after_pass": after_pass,
        "after_reject": after_reject,
        "reject_fraction": round(after_reject / len(grid), 4) if grid else None,
        "train_unlocked": TRAIN_UNLOCKED,
        "blocks_rung0": BLOCKS_RUNG0,
        "recipe_locked": RECIPE_LOCKED,
        "note": (
            "Primary speedup = cost units (grid_n / after_pass). Optional wall "
            "sleep mirrors quality proxy — not GPU. Rejects fail-closed "
            "(S<MIN_ARITH); no data prune."
        ),
        "sample_rejects": [
            {"k": r.detail.get("k"), "r": r.detail.get("r"), "S": round(r.s_arith, 4)}
            for r in after_results
            if not r.passed
        ][:8],
    }


def fingerprint_payload(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def build_default_report() -> dict[str, Any]:
    rows = [
        albert_closed_form(100_000),
        albert_closed_form(1_000_000),
        hive_closed_form(100_000),
        hive_closed_form(1_000_000),
    ]
    body = {
        "needle": NEEDLE,
        "train_unlocked": TRAIN_UNLOCKED,
        "blocks_rung0": BLOCKS_RUNG0,
        "recipe_locked": RECIPE_LOCKED,
        "min_arith": MIN_ARITH,
        "rows": [asdict(r) for r in rows],
        "all_passed": all(r.passed for r in rows),
        "refs": {
            "S06": "arith-only prefilter before quality",
            "S14": "U, N/U, bytes@1-bit closed-form",
            "S11": "claim-range peer fanout",
            "S12": "--scaffold falsifier stubs",
        },
    }
    body["fp"] = fingerprint_payload(
        {"rows": body["rows"], "min_arith": MIN_ARITH, "needle": NEEDLE}
    )
    return body


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def check_cache(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "reason": "missing", "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "reason": f"read_error:{exc}", "path": str(path)}
    if data.get("needle") != NEEDLE:
        return {"ok": False, "reason": "needle_mismatch", "path": str(path)}
    if data.get("train_unlocked") is True:
        return {"ok": False, "reason": "refuse_train_unlock", "path": str(path)}
    fresh = build_default_report()
    hit = data.get("fp") == fresh["fp"] and bool(data.get("all_passed"))
    return {
        "ok": hit,
        "hit": hit,
        "path": str(path),
        "fp": data.get("fp"),
        "expected_fp": fresh["fp"],
        "all_passed": data.get("all_passed"),
    }


def _parse_float(raw: str) -> float:
    return float(raw.replace("_", ""))


def main(argv: Sequence[str] | None = None) -> int:
    root = _repo_root()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stack", choices=("albert", "hive", "share-rank"), default=None)
    p.add_argument("--raw", action="store_true", help="Use --n + --u directly")
    p.add_argument("--n", type=str, default=None, help="N_L logical params")
    p.add_argument("--u", type=str, default=None, help="U unique (raw mode)")
    p.add_argument("--k", type=int, default=None, help="share factor (share-rank)")
    p.add_argument("--r", type=int, default=1, help="LoRA rank / share-rank r")
    p.add_argument("--layers", type=int, default=100)
    p.add_argument("--experts", type=int, default=100)
    p.add_argument("--json", action="store_true")
    p.add_argument("--scaffold", action="store_true")
    p.add_argument(
        "--claim-range",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        help="Inclusive claim-ID range for peer fanout (S11)",
    )
    p.add_argument("--probe", action="store_true", help="Before/after prefilter wall probe")
    p.add_argument(
        "--quality-proxy-ms",
        type=float,
        default=0.05,
        help="Sleep ms charged as quality proxy in --probe",
    )
    p.add_argument("--write", action="store_true", help="Write default/probe artifacts")
    p.add_argument("--ensure-default", action="store_true")
    p.add_argument("--check-cache", action="store_true")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Override artifact path",
    )
    args = p.parse_args(list(argv) if argv is not None else None)

    default_path = root / ARTIFACT_REL
    probe_path = root / PROBE_REL

    if args.check_cache:
        report = check_cache(Path(args.out) if args.out else default_path)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print("HIT" if report.get("hit") else "MISS", report)
        return 0 if report.get("ok") else 1

    if args.ensure_default or (args.write and not args.probe and not args.scaffold):
        payload = build_default_report()
        out = Path(args.out) if args.out else default_path
        write_json(out, payload)
        if args.json:
            print(json.dumps({"ok": True, "path": str(out), **payload}, indent=2))
        else:
            print(f"WROTE {out} all_passed={payload['all_passed']} fp={payload['fp']}")
        return 0 if payload["all_passed"] else 1

    if args.probe:
        wall = float(args.quality_proxy_ms) > 0
        probe = probe_prefilter_vs_full(
            quality_proxy_ms=args.quality_proxy_ms, wall=wall
        )
        if args.write or args.ensure_default:
            write_json(Path(args.out) if args.out else probe_path, probe)
            probe["path"] = str(Path(args.out) if args.out else probe_path)
        if args.json:
            print(json.dumps(probe, indent=2))
        else:
            print(
                f"PROBE units {probe['before_cost_units']}→{probe['after_cost_units']} "
                f"speedup≈{probe['approx_speedup']}× "
                f"pass={probe['after_pass']} reject={probe['after_reject']}"
            )
        # Fail-closed if no measured win (speedup < 1.2) — theater probe.
        sp = probe.get("approx_speedup") or 0
        return 0 if sp >= 1.2 and probe["after_reject"] > 0 else 1

    row: ArithResult | None = None
    if args.raw:
        if args.n is None or args.u is None:
            print("--raw requires --n and --u", file=sys.stderr)
            return 2
        row = raw_closed_form(_parse_float(args.n), _parse_float(args.u))
    elif args.stack == "albert":
        if args.n is None:
            print("--stack albert requires --n", file=sys.stderr)
            return 2
        row = albert_closed_form(
            _parse_float(args.n), layers=args.layers, r=args.r
        )
    elif args.stack == "hive":
        if args.n is None:
            print("--stack hive requires --n", file=sys.stderr)
            return 2
        row = hive_closed_form(
            _parse_float(args.n), experts=args.experts, r=args.r
        )
    elif args.stack == "share-rank":
        if args.n is None or args.k is None:
            print("--stack share-rank requires --n and --k", file=sys.stderr)
            return 2
        row = share_rank_closed_form(
            _parse_float(args.n), k=args.k, r=args.r, layers=args.layers
        )
    elif args.scaffold and args.claim_range:
        # scaffold-only path below
        pass
    else:
        # Default: print default stacks (same as ensure body rows).
        payload = build_default_report()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for r in payload["rows"]:
                status = "PASS" if r["passed"] else "FAIL"
                print(
                    f"{status} {r['stack']} N={r['n_logic']} U={r['u_unique']} "
                    f"S={r['s_arith']:.4f} bytes={r['packed_bytes']} "
                    f"quality={r['quality']}"
                )
            print(f"all_passed={payload['all_passed']} needle={NEEDLE}")
        return 0 if payload["all_passed"] else 1

    rows_for_scaffold = [row] if row is not None else []
    if args.scaffold:
        if not args.claim_range:
            print("--scaffold requires --claim-range START END", file=sys.stderr)
            return 2
        start, end = args.claim_range
        stubs = scaffold_rows(start, end, stacks=rows_for_scaffold or None)
        out = {"needle": NEEDLE, "scaffold": stubs, "train_unlocked": False}
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            for s in stubs:
                print(f"{s['id']}\t{s['verdict']}\t{s['claim'][:80]}")
        return 0

    assert row is not None
    payload = asdict(row)
    payload["needle"] = NEEDLE
    payload["train_unlocked"] = TRAIN_UNLOCKED
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        status = "PASS" if row.passed else "FAIL"
        print(
            f"{status} {row.stack} N={row.n_logic} U={row.u_unique} "
            f"S={row.s_arith:.4f} bytes={row.packed_bytes}"
        )
        if row.contradiction:
            print(f"contradiction: {row.contradiction}", file=sys.stderr)
    # Fail-closed: non-zero when arith/pack fails.
    return 0 if row.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
