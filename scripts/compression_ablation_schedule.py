#!/usr/bin/env python3
"""Share×rank ablation schedule — OA screen → successive halving / Hyperband.

OVERSEER_COMPRESSION_ABLATION_SCHEDULE_2026_09_06

Research-speed S03 / S16 / S32 (notes/RESEARCH_SPEED_TRAINING.md).
Torch-free. Emits dry-run brackets for future T1–T2-style (k, r) screens.
Does **not** change the LOCKED recipe, unlock train, or block rung0.

Usage::

    python3 scripts/compression_ablation_schedule.py
    python3 scripts/compression_ablation_schedule.py --json
    python3 scripts/compression_ablation_schedule.py --mode oa --write
    python3 scripts/compression_ablation_schedule.py --mode hyperband --eta 3 --json
    python3 scripts/compression_ablation_schedule.py --mode oa-then-hb --write
    python3 scripts/compression_ablation_schedule.py --ensure-default-schedule --json
    python3 scripts/compression_ablation_schedule.py --check-cache --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

# OVERSEER_COMPRESSION_ABLATION_SCHEDULE_2026_09_06
NEEDLE = "OVERSEER_COMPRESSION_ABLATION_SCHEDULE_2026_09_06"
# Lane-U probe-once cache (research-speed S03) — not a train unlock.
CACHE_NEEDLE = "OVERSEER_COMPRESSION_ABLATION_SCHEDULE_CACHE_2026_09_08"

# Default grids aligned with T1/T2 toys (schedule only — not a recipe rewrite).
K_LEVELS_DEFAULT = (2, 4, 8, 16, 50, 100, 125, 200)
R_LEVELS_DEFAULT = (1, 2, 4, 8, 16, 32)
# Early resource / epoch proxy levels for 3-factor OA (S32 OATM).
E_LEVELS_DEFAULT = (1, 3, 9)

ETA_DEFAULT = 3
MAX_RESOURCE_DEFAULT = 81  # 3^4 — Hyperband R
ARTIFACT_REL = Path("notes/compression_artifacts/ablation_schedule.json")
BLOCKS_RUNG0 = False
TRAIN_UNLOCKED = False
RECIPE_LOCKED = True
DATA_PRUNE = False


@dataclass(frozen=True)
class ConfigPoint:
    """One (k, r[, E]) candidate in a schedule."""

    k: int
    r: int
    e: int | None = None
    config_id: str = ""

    def label(self) -> str:
        if self.e is None:
            return f"k={self.k},r={self.r}"
        return f"k={self.k},r={self.r},E={self.e}"


@dataclass(frozen=True)
class BracketRound:
    round_idx: int
    resource: int
    n_configs: int
    configs: tuple[str, ...]


@dataclass(frozen=True)
class Bracket:
    bracket_id: int
    n0: int
    r0: int
    s: int
    eta: int
    rounds: tuple[BracketRound, ...]
    total_resource_units: int


def _pick_levels(values: Sequence[int], n: int) -> tuple[int, ...]:
    """Evenly subsample ``values`` down to ``n`` levels (inclusive endpoints)."""
    if n <= 0:
        raise ValueError("n must be positive")
    vals = tuple(int(v) for v in values)
    if n >= len(vals):
        return vals
    if n == 1:
        return (vals[len(vals) // 2],)
    out: list[int] = []
    for i in range(n):
        idx = round(i * (len(vals) - 1) / (n - 1))
        out.append(vals[idx])
    # Dedupe while preserving order (grids can collapse when short).
    seen: set[int] = set()
    uniq: list[int] = []
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    while len(uniq) < n:
        for v in vals:
            if v not in seen:
                seen.add(v)
                uniq.append(v)
            if len(uniq) >= n:
                break
    return tuple(uniq[:n])


def taguchi_l9() -> tuple[tuple[int, int, int], ...]:
    """Classic Taguchi L9 (3^4 reduced) — first three columns for (k, r, E).

    Levels are 0..2. Nine runs vs 27 full factorial (S32 OATM screen).
    """
    return (
        (0, 0, 0),
        (0, 1, 1),
        (0, 2, 2),
        (1, 0, 1),
        (1, 1, 2),
        (1, 2, 0),
        (2, 0, 2),
        (2, 1, 0),
        (2, 2, 1),
    )


def orthogonal_array_screen(
    k_levels: Sequence[int] = K_LEVELS_DEFAULT,
    r_levels: Sequence[int] = R_LEVELS_DEFAULT,
    e_levels: Sequence[int] = E_LEVELS_DEFAULT,
    *,
    n_levels: int = 3,
) -> list[ConfigPoint]:
    """OATM / Taguchi L9 screen over share×rank×resource (S03/S32).

    Subsamples each factor to ``n_levels`` (default 3), maps L9 indices, and
    returns balanced (k, r, E) points — far fewer than a full k×r×E grid.
    """
    if n_levels != 3:
        raise ValueError("only L9 (n_levels=3) is implemented")
    ks = _pick_levels(k_levels, n_levels)
    rs = _pick_levels(r_levels, n_levels)
    es = _pick_levels(e_levels, n_levels)
    points: list[ConfigPoint] = []
    for i, (ik, ir, ie) in enumerate(taguchi_l9()):
        pt = ConfigPoint(
            k=ks[ik],
            r=rs[ir],
            e=es[ie],
            config_id=f"oa{i}",
        )
        points.append(pt)
    return points


def full_grid(
    k_levels: Sequence[int] = K_LEVELS_DEFAULT,
    r_levels: Sequence[int] = R_LEVELS_DEFAULT,
) -> list[ConfigPoint]:
    """Full factorial share×rank grid (baseline cost reference)."""
    out: list[ConfigPoint] = []
    i = 0
    for k in k_levels:
        for r in r_levels:
            out.append(ConfigPoint(k=int(k), r=int(r), e=None, config_id=f"g{i}"))
            i += 1
    return out


def successive_halving_bracket(
    configs: Sequence[ConfigPoint],
    *,
    max_resource: int,
    eta: int = ETA_DEFAULT,
    bracket_id: int = 0,
    s: int = 0,
) -> Bracket:
    """One successive-halving bracket (Jamieson & Talwalkar; Hyperband inner loop).

    Starts with ``len(configs)`` arms at resource r0 = max_resource / eta^s,
    keeps top 1/eta each round until one (or few) remain.
    Dry-run: no metrics — cull order is schedule order (deterministic placeholder).
    """
    if eta < 2:
        raise ValueError("eta must be >= 2")
    if max_resource < 1:
        raise ValueError("max_resource must be >= 1")
    n = len(configs)
    if n < 1:
        raise ValueError("configs must be non-empty")

    r0 = max(1, int(max_resource / (eta**s)))
    alive: list[ConfigPoint] = list(configs)
    rounds: list[BracketRound] = []
    total = 0
    round_idx = 0
    # Number of SH rounds ≈ floor(log_eta n) + 1, capped by s+1 in Hyperband.
    max_rounds = max(1, s + 1)
    while alive and round_idx < max_rounds:
        resource = int(r0 * (eta**round_idx))
        resource = min(resource, max_resource)
        n_i = len(alive)
        total += n_i * resource
        rounds.append(
            BracketRound(
                round_idx=round_idx,
                resource=resource,
                n_configs=n_i,
                configs=tuple(c.config_id for c in alive),
            )
        )
        keep = max(1, int(math.floor(n_i / eta)))
        if keep >= n_i and round_idx > 0:
            break
        # Dry-run cull: keep first ``keep`` (stable schedule; real runs rank by loss).
        alive = alive[:keep]
        round_idx += 1
        if keep == 1 and round_idx >= max_rounds:
            break

    return Bracket(
        bracket_id=bracket_id,
        n0=n,
        r0=r0,
        s=s,
        eta=eta,
        rounds=tuple(rounds),
        total_resource_units=total,
    )


def hyperband_brackets(
    configs: Sequence[ConfigPoint],
    *,
    max_resource: int = MAX_RESOURCE_DEFAULT,
    eta: int = ETA_DEFAULT,
) -> list[Bracket]:
    """Hyperband outer loop: s = s_max .. 0 brackets with η cull (S16).

    Each bracket takes up to ``n_i`` arms from ``configs`` (deterministic prefix).
    Cap ``n_i`` at ``len(pool)`` — do **not** cycle-clone arms. Clone inflation
    made ``oa-then-hb`` cost identical to full-grid Hyperband (OA screen noop).
    Needle: ``OVERSEER_COMPRESSION_HB_NO_CLONE_2026_09_08``.
    """
    if eta < 2:
        raise ValueError("eta must be >= 2")
    s_max = int(math.floor(math.log(max_resource) / math.log(eta)))
    brackets: list[Bracket] = []
    pool = list(configs)
    if not pool:
        raise ValueError("configs must be non-empty")

    for bracket_id, s in enumerate(range(s_max, -1, -1)):
        n = int(math.ceil((s_max + 1) / (s + 1) * (eta**s)))
        # Cap to unique pool size so OA→HB realizes the OA cull in resource units.
        n_eff = min(n, len(pool))
        taken: list[ConfigPoint] = []
        for i in range(n_eff):
            base = pool[i]
            taken.append(
                ConfigPoint(
                    k=base.k,
                    r=base.r,
                    e=base.e,
                    config_id=f"hb{bracket_id}_{i}_{base.config_id}",
                )
            )
        brackets.append(
            successive_halving_bracket(
                taken,
                max_resource=max_resource,
                eta=eta,
                bracket_id=bracket_id,
                s=s,
            )
        )
    return brackets


def schedule_cost_units(brackets: Iterable[Bracket]) -> int:
    return sum(b.total_resource_units for b in brackets)


def build_schedule(
    *,
    mode: str = "oa-then-hb",
    k_levels: Sequence[int] = K_LEVELS_DEFAULT,
    r_levels: Sequence[int] = R_LEVELS_DEFAULT,
    e_levels: Sequence[int] = E_LEVELS_DEFAULT,
    eta: int = ETA_DEFAULT,
    max_resource: int = MAX_RESOURCE_DEFAULT,
) -> dict[str, Any]:
    """Build dry-run ablation schedule JSON payload."""
    mode_key = mode.strip().lower().replace("_", "-")
    grid = full_grid(k_levels, r_levels)
    full_n = len(grid)
    full_cost_proxy = full_n * max_resource  # naive: every cell at R

    oa_points = orthogonal_array_screen(k_levels, r_levels, e_levels)
    brackets: list[Bracket] = []
    screen: list[ConfigPoint] = []

    if mode_key == "oa":
        screen = oa_points
        # Single cheap SH on OA set (optional structure for consumers).
        brackets = [
            successive_halving_bracket(
                oa_points,
                max_resource=max_resource,
                eta=eta,
                bracket_id=0,
                s=int(math.floor(math.log(max(len(oa_points), 1)) / math.log(eta))),
            )
        ]
    elif mode_key in ("sh", "successive-halving"):
        screen = list(grid)
        s = int(math.floor(math.log(max(len(grid), 1)) / math.log(eta)))
        brackets = [
            successive_halving_bracket(
                grid,
                max_resource=max_resource,
                eta=eta,
                bracket_id=0,
                s=s,
            )
        ]
    elif mode_key in ("hyperband", "hb"):
        screen = list(grid)
        brackets = hyperband_brackets(grid, max_resource=max_resource, eta=eta)
    elif mode_key in ("oa-then-hb", "oa-hb", "oatm"):
        screen = oa_points
        # Promote OA (k,r) unique pairs into Hyperband arms (drop E for HB resource).
        seen: set[tuple[int, int]] = set()
        arms: list[ConfigPoint] = []
        for p in oa_points:
            key = (p.k, p.r)
            if key in seen:
                continue
            seen.add(key)
            arms.append(ConfigPoint(k=p.k, r=p.r, e=None, config_id=p.config_id))
        brackets = hyperband_brackets(arms, max_resource=max_resource, eta=eta)
    else:
        raise ValueError(
            f"unknown mode={mode!r}; use oa|sh|hyperband|oa-then-hb"
        )

    sched_cost = schedule_cost_units(brackets)
    speedup = (full_cost_proxy / sched_cost) if sched_cost else None

    return {
        "needle": NEEDLE,
        "mode": mode_key,
        "dry_run": True,
        "blocks_rung0": BLOCKS_RUNG0,
        "train_unlocked": TRAIN_UNLOCKED,
        "recipe_locked": RECIPE_LOCKED,
        "refs": {
            "S03": "orthogonal array / successive halving for (k,r)",
            "S16": "Hyperband-style brackets eta cull after OA",
            "S32": "OATM / Taguchi L9 multi-factor k,r,E screen",
        },
        "eta": eta,
        "max_resource": max_resource,
        "k_levels": list(k_levels),
        "r_levels": list(r_levels),
        "e_levels": list(e_levels),
        "full_grid_n": full_n,
        "full_grid_cost_proxy": full_cost_proxy,
        "screen": [asdict(p) for p in screen],
        "screen_n": len(screen),
        "brackets": [_bracket_dict(b) for b in brackets],
        "schedule_resource_units": sched_cost,
        "approx_speedup_vs_full_grid": speedup,
        "note": (
            "Dry-run schedule only — cull order is deterministic placeholder; "
            "does not rewrite LOCKED recipe or gate rung0."
        ),
    }


def _bracket_dict(b: Bracket) -> dict[str, Any]:
    return {
        "bracket_id": b.bracket_id,
        "n0": b.n0,
        "r0": b.r0,
        "s": b.s,
        "eta": b.eta,
        "total_resource_units": b.total_resource_units,
        "rounds": [asdict(r) for r in b.rounds],
    }


def write_artifact(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def schedule_fingerprint(
    *,
    mode: str,
    k_levels: Sequence[int],
    r_levels: Sequence[int],
    e_levels: Sequence[int],
    eta: int,
    max_resource: int,
) -> str:
    """Stable key for probe-once cache (grids + Hyperband knobs)."""
    blob = json.dumps(
        {
            "mode": mode.strip().lower().replace("_", "-"),
            "k": list(k_levels),
            "r": list(r_levels),
            "e": list(e_levels),
            "eta": int(eta),
            "max_resource": int(max_resource),
            "needle": NEEDLE,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def default_artifact_path(root: Path | None = None) -> Path:
    base = root if root is not None else Path(__file__).resolve().parents[1]
    return base / ARTIFACT_REL


def check_schedule_cache(
    path: Path,
    *,
    mode: str = "oa-then-hb",
    k_levels: Sequence[int] = K_LEVELS_DEFAULT,
    r_levels: Sequence[int] = R_LEVELS_DEFAULT,
    e_levels: Sequence[int] = E_LEVELS_DEFAULT,
    eta: int = ETA_DEFAULT,
    max_resource: int = MAX_RESOURCE_DEFAULT,
) -> dict[str, Any]:
    """Validate durable OA→HB schedule cache (Lane U / research-speed S03)."""
    fp = schedule_fingerprint(
        mode=mode,
        k_levels=k_levels,
        r_levels=r_levels,
        e_levels=e_levels,
        eta=eta,
        max_resource=max_resource,
    )
    out: dict[str, Any] = {
        "cache_needle": CACHE_NEEDLE,
        "needle": NEEDLE,
        "path": str(path),
        "fingerprint": fp,
        "cache_ok": False,
        "cache_hit": False,
        "train_unlocked": TRAIN_UNLOCKED,
        "data_prune": DATA_PRUNE,
        "blocks_rung0": BLOCKS_RUNG0,
    }
    if not path.is_file():
        out["error"] = "missing_artifact"
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        out["error"] = f"read_fail:{exc}"
        return out
    if data.get("needle") != NEEDLE:
        out["error"] = "needle_mismatch"
        return out
    if data.get("cache_needle") != CACHE_NEEDLE:
        out["error"] = "cache_needle_mismatch"
        return out
    if bool(data.get("train_unlocked")):
        out["error"] = "refusing_train_unlocked_cache"
        return out
    if bool(data.get("data_prune")):
        out["error"] = "refusing_pruned_cache"
        return out
    if data.get("fingerprint") != fp:
        out["error"] = "fingerprint_mismatch"
        return out
    speedup = data.get("approx_speedup_vs_full_grid")
    if not isinstance(speedup, (int, float)) or speedup <= 1.0:
        out["error"] = "speedup_not_gt_1"
        return out
    out["cache_ok"] = True
    out["cache_hit"] = True
    out["mode"] = data.get("mode")
    out["approx_speedup_vs_full_grid"] = speedup
    out["schedule_resource_units"] = data.get("schedule_resource_units")
    out["full_grid_cost_proxy"] = data.get("full_grid_cost_proxy")
    out["screen_n"] = data.get("screen_n")
    return out


def ensure_default_schedule(
    *,
    root: Path | None = None,
    path: Path | None = None,
    mode: str = "oa-then-hb",
    k_levels: Sequence[int] = K_LEVELS_DEFAULT,
    r_levels: Sequence[int] = R_LEVELS_DEFAULT,
    e_levels: Sequence[int] = E_LEVELS_DEFAULT,
    eta: int = ETA_DEFAULT,
    max_resource: int = MAX_RESOURCE_DEFAULT,
    force: bool = False,
) -> dict[str, Any]:
    """Probe-once: reuse disk schedule when fingerprint matches; else rebuild.

    Speeds research-speed S03 consumers (no recompute of OA→HB brackets).
    Does **not** unlock train or rewrite the LOCKED recipe.
    """
    base = root if root is not None else Path(__file__).resolve().parents[1]
    art = path if path is not None else default_artifact_path(base)
    if not art.is_absolute():
        art = base / art
    check = check_schedule_cache(
        art,
        mode=mode,
        k_levels=k_levels,
        r_levels=r_levels,
        e_levels=e_levels,
        eta=eta,
        max_resource=max_resource,
    )
    if check.get("cache_ok") and not force:
        try:
            payload = json.loads(art.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            check = {**check, "cache_ok": False, "cache_hit": False, "error": f"reread:{exc}"}
        else:
            return {
                **payload,
                "cache_ok": True,
                "cache_hit": True,
                "cache_needle": CACHE_NEEDLE,
                "ensured": False,
                "artifact": str(art),
            }

    payload = build_schedule(
        mode=mode,
        k_levels=k_levels,
        r_levels=r_levels,
        e_levels=e_levels,
        eta=eta,
        max_resource=max_resource,
    )
    fp = schedule_fingerprint(
        mode=mode,
        k_levels=k_levels,
        r_levels=r_levels,
        e_levels=e_levels,
        eta=eta,
        max_resource=max_resource,
    )
    payload = {
        **payload,
        "cache_needle": CACHE_NEEDLE,
        "fingerprint": fp,
        "data_prune": DATA_PRUNE,
    }
    write_artifact(payload, art)
    return {
        **payload,
        "cache_ok": True,
        "cache_hit": False,
        "ensured": True,
        "artifact": str(art),
        "prior_check_error": check.get("error"),
    }


def _parse_int_list(raw: str | None, default: Sequence[int]) -> tuple[int, ...]:
    if raw is None or not raw.strip():
        return tuple(default)
    parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    return tuple(int(p) for p in parts)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run OA / successive-halving / Hyperband schedule for "
            "share×rank (k,r) ablations (S03/S16/S32)."
        )
    )
    parser.add_argument(
        "--mode",
        default="oa-then-hb",
        choices=("oa", "sh", "hyperband", "oa-then-hb"),
        help="Schedule builder (default: oa-then-hb)",
    )
    parser.add_argument("--eta", type=int, default=ETA_DEFAULT, help="Cull factor η")
    parser.add_argument(
        "--max-resource",
        type=int,
        default=MAX_RESOURCE_DEFAULT,
        help="Hyperband R (max resource units)",
    )
    parser.add_argument(
        "--k-levels",
        default=None,
        help="Comma-separated share factors (default: T1-aligned grid)",
    )
    parser.add_argument(
        "--r-levels",
        default=None,
        help="Comma-separated SVD/LoRA ranks (default: T2-aligned grid)",
    )
    parser.add_argument(
        "--e-levels",
        default=None,
        help="Comma-separated early resource levels for OA (default: 1,3,9)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full schedule JSON to stdout",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help=f"Write schedule under {ARTIFACT_REL}",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Override artifact path (implies --write)",
    )
    parser.add_argument(
        "--ensure-default-schedule",
        action="store_true",
        help="Probe-once: write/reuse default ablation_schedule.json cache",
    )
    parser.add_argument(
        "--check-cache",
        action="store_true",
        help="Validate durable schedule cache (exit 1 on miss/mismatch)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --ensure-default-schedule, rebuild even on cache hit",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    k_levels = _parse_int_list(args.k_levels, K_LEVELS_DEFAULT)
    r_levels = _parse_int_list(args.r_levels, R_LEVELS_DEFAULT)
    e_levels = _parse_int_list(args.e_levels, E_LEVELS_DEFAULT)

    root = Path(__file__).resolve().parents[1]
    out_path: Path | None = None
    if args.out is not None:
        out_path = args.out if args.out.is_absolute() else root / args.out
    elif args.write or args.ensure_default_schedule or args.check_cache:
        out_path = root / ARTIFACT_REL

    if args.check_cache and not args.ensure_default_schedule:
        assert out_path is not None
        check = check_schedule_cache(
            out_path,
            mode=args.mode,
            k_levels=k_levels,
            r_levels=r_levels,
            e_levels=e_levels,
            eta=args.eta,
            max_resource=args.max_resource,
        )
        if args.json:
            print(json.dumps(check, indent=2))
        else:
            print(
                f"cache_needle={CACHE_NEEDLE} cache_ok={check.get('cache_ok')} "
                f"hit={check.get('cache_hit')} err={check.get('error')}"
            )
        return 0 if check.get("cache_ok") else 1

    if args.ensure_default_schedule:
        payload = ensure_default_schedule(
            root=root,
            path=out_path,
            mode=args.mode,
            k_levels=k_levels,
            r_levels=r_levels,
            e_levels=e_levels,
            eta=args.eta,
            max_resource=args.max_resource,
            force=args.force,
        )
    else:
        payload = build_schedule(
            mode=args.mode,
            k_levels=k_levels,
            r_levels=r_levels,
            e_levels=e_levels,
            eta=args.eta,
            max_resource=args.max_resource,
        )
        if args.write or args.out is not None:
            assert out_path is not None
            fp = schedule_fingerprint(
                mode=args.mode,
                k_levels=k_levels,
                r_levels=r_levels,
                e_levels=e_levels,
                eta=args.eta,
                max_resource=args.max_resource,
            )
            payload = {
                **payload,
                "cache_needle": CACHE_NEEDLE,
                "fingerprint": fp,
                "data_prune": DATA_PRUNE,
            }
            write_artifact(payload, out_path)
            try:
                artifact_s = str(out_path.relative_to(root))
            except ValueError:
                artifact_s = str(out_path)
            payload = {**payload, "artifact": artifact_s}

    if args.check_cache and args.ensure_default_schedule:
        assert out_path is not None
        check = check_schedule_cache(
            out_path,
            mode=args.mode,
            k_levels=k_levels,
            r_levels=r_levels,
            e_levels=e_levels,
            eta=args.eta,
            max_resource=args.max_resource,
        )
        payload = {
            **payload,
            "cache_ok": check.get("cache_ok"),
            "check_error": check.get("error"),
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"needle={NEEDLE} cache_needle={CACHE_NEEDLE} "
                f"cache_ok={check.get('cache_ok')} hit={payload.get('cache_hit')} "
                f"ensured={payload.get('ensured')}"
            )
        return 0 if check.get("cache_ok") else 1

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"needle={NEEDLE}")
        if payload.get("cache_needle"):
            print(
                f"cache_needle={payload.get('cache_needle')} "
                f"cache_hit={payload.get('cache_hit')} ensured={payload.get('ensured')}"
            )
        print(f"mode={payload['mode']} dry_run=true blocks_rung0=false")
        speedup = payload["approx_speedup_vs_full_grid"]
        speedup_s = f"{speedup:.2f}x" if speedup else "n/a"
        print(
            f"screen_n={payload['screen_n']} full_grid_n={payload['full_grid_n']} "
            f"brackets={len(payload['brackets'])} "
            f"units={payload['schedule_resource_units']} "
            f"approx_speedup={speedup_s}"
        )
        if payload.get("artifact"):
            print(f"wrote={payload['artifact']}")
        for b in payload["brackets"]:
            rounds = b["rounds"]
            rsrc = ",".join(str(r["resource"]) for r in rounds)
            ns = ",".join(str(r["n_configs"]) for r in rounds)
            print(
                f"  bracket s={b['s']} n0={b['n0']} r0={b['r0']} "
                f"n_path=[{ns}] R_path=[{rsrc}] units={b['total_resource_units']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
