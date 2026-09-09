#!/usr/bin/env python3
"""T5 serve/residency smoke — NVFP4 unique pack-bytes + L2 fit sketches.

OVERSEER_COMPRESSION_T5_SERVE_2026_09_06

Reads notes/compression_artifacts/rung0_model_skeleton.json (if present) and
prints residency estimates for:
  - north-star U=10M @ NVFP4 (same grain as L5 far-map 10M)
  - T4 toy U at N=1e7 (arith only)
  - rung0 skeleton unique_U / nvfp4_pack_bytes

Honesty: arith byte fit ≠ quality / KD / native MoE serve maturity.
Does not train. Does not rewrite LOCKED recipe.

Usage::
    python3 scripts/compression_t5_serve.py
    python3 scripts/compression_t5_serve.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

NEEDLE = "OVERSEER_COMPRESSION_T5_SERVE_2026_09_06"
ROOT = Path(__file__).resolve().parents[1]
SKELETON_PATH = ROOT / "notes" / "compression_artifacts" / "rung0_model_skeleton.json"

# Plan-assumed banks (L5) — pending hardware lane; sketches only. Decimal MB.
L2_MB = 24.0
L3_MB = 24.0
NORTH_STAR_U = 10_000_000
T4_N1E7_U = 74_576  # from t4_scale_result.json N=1e7 row
BITS_PER_PARAM_RAW = 4.0  # NVFP4 raw = 0.5 B/param
BITS_PER_PARAM_PACKED_SKETCH = 4.5  # applicability note; scales extra UNKNOWN


@dataclass(frozen=True)
class ResidencyRow:
    label: str
    unique_u: int
    raw_nvfp4_bytes: float
    raw_nvfp4_mb: float
    packed_sketch_mb: float
    fit_l2_24mb: bool
    fit_l3_24mb: bool
    note: str


def nvfp4_raw_bytes(u: int) -> float:
    return float(u) * (BITS_PER_PARAM_RAW / 8.0)


def nvfp4_packed_sketch_bytes(u: int) -> float:
    return float(u) * (BITS_PER_PARAM_PACKED_SKETCH / 8.0)


def decimal_mb(nbytes: float) -> float:
    """L5-style decimal MB (1e6 B), not MiB — matches far-map 10M → 5.00 MB."""
    return nbytes / 1_000_000.0


def row(label: str, u: int, note: str) -> ResidencyRow:
    raw_b = nvfp4_raw_bytes(u)
    pack_b = nvfp4_packed_sketch_bytes(u)
    raw_mb = decimal_mb(raw_b)
    pack_mb = decimal_mb(pack_b)
    return ResidencyRow(
        label=label,
        unique_u=u,
        raw_nvfp4_bytes=raw_b,
        raw_nvfp4_mb=raw_mb,
        packed_sketch_mb=pack_mb,
        fit_l2_24mb=raw_mb <= L2_MB,
        fit_l3_24mb=raw_mb <= L3_MB,
        note=note,
    )


def load_skeleton(path: Path = SKELETON_PATH) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    return data


def build_rows(skeleton: dict[str, Any] | None = None) -> list[ResidencyRow]:
    rows = [
        row(
            "north_star_10M_unique",
            NORTH_STAR_U,
            "1B→10M unique @ NVFP4; same grain as L5 far-map 10M; arith≠quality",
        ),
        row(
            "logical_1B_all_unique",
            1_000_000_000,
            "before share/rank — must stream; motivates S≈100 fold",
        ),
        row(
            "t4_n1e7_unique",
            T4_N1E7_U,
            "T4 toy N=1e7 U; S_arith≈134; train stamp only",
        ),
    ]
    sk = skeleton if skeleton is not None else load_skeleton()
    if sk is not None:
        u = int(sk.get("unique_U") or sk.get("unique_u") or 0)
        if u > 0:
            pack = sk.get("nvfp4_pack_bytes")
            note = "rung0_model_skeleton.json toy; not north-star"
            if pack is not None:
                note += f"; skeleton pack_bytes={pack}"
            rows.append(row("rung0_skeleton", u, note))
    return rows


def report_dict(rows: list[ResidencyRow], skeleton: dict[str, Any] | None) -> dict[str, Any]:
    north = next(r for r in rows if r.label == "north_star_10M_unique")
    return {
        "needle": NEEDLE,
        "arith_not_quality": True,
        "hot_dtype": "NVFP4",
        "l2_mb_assumed": L2_MB,
        "l3_mb_assumed": L3_MB,
        "north_star_fits_l2": north.fit_l2_24mb,
        "north_star_raw_mb": north.raw_nvfp4_mb,
        "skeleton_path": str(SKELETON_PATH.relative_to(ROOT)),
        "skeleton_present": skeleton is not None,
        "skeleton_unique_U": (
            int(skeleton["unique_U"]) if skeleton and "unique_U" in skeleton else None
        ),
        "rows": [asdict(r) for r in rows],
        "honesty": (
            "Byte fit of NVFP4 unique store ≠ KD/task quality; "
            "sm121 native NVFP4 MoE immature (C27); no 1B train started."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--skeleton",
        type=Path,
        default=SKELETON_PATH,
        help="path to rung0_model_skeleton.json",
    )
    args = parser.parse_args(argv)
    skeleton = load_skeleton(args.skeleton)
    rows = build_rows(skeleton)
    payload = report_dict(rows, skeleton)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{NEEDLE} hot_dtype=NVFP4 arith_not_quality=true")
        print(f"L2/L3 assumed {L2_MB:.0f} MB decimal (L5 plan banks)")
        for r in rows:
            print(
                f"{r.label}: U={r.unique_u} raw_mb={r.raw_nvfp4_mb:.4f} "
                f"pack_sketch_mb={r.packed_sketch_mb:.4f} "
                f"fit_L2={r.fit_l2_24mb} — {r.note}"
            )
        print(f"north_star_fits_l2={payload['north_star_fits_l2']}")
        print(payload["honesty"])
    return 0 if payload["north_star_fits_l2"] and payload["arith_not_quality"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
