#!/usr/bin/env python3
"""CLEAN FP4 expert RSS/mmap smoke — T0 toy (no nvidia-fs/GDS).

OVERSEER_CLEAN_FP4_EXPERT_RSS_MMAP_SMOKE_2026_09_04

Toy MoE expert weights packed as FP4 (0.5 B/param) and served via ``mmap`` —
the Spark-safe host/UMA path. Never loads ``nvidia-fs`` / cuFile / GDS.

Meters **prompt tok/s** (prefill-shaped) and **accepted Writing tok/s**
separately (C13 / L8). Brochure 10k+ is *not* a success bar.

Usage::

    python3 scripts/bitnet_fp4_expert_rss_smoke.py
    python3 scripts/bitnet_fp4_expert_rss_smoke.py --json
"""

from __future__ import annotations

import argparse
import json
import mmap
import os
import resource
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

# OVERSEER_CLEAN_FP4_EXPERT_RSS_MMAP_SMOKE_2026_09_04
FORBIDDEN_MODULES = frozenset(
    {
        "nvidia_fs",
        "nvidia-fs",
        "cufile",
        "cupy",  # optional GPU path — smoke stays CPU/mmap
    }
)

# Toy T0 caps — never R0-39B (L8 smoke inflation FAIL).
TOY_N_EXPERTS = 4
TOY_EXPERT_PARAMS = 4096  # ~2 KiB FP4 each
FP4_BYTES_PER_PARAM = 0.5
BYTES_PER_EXPERT = int(TOY_EXPERT_PARAMS * FP4_BYTES_PER_PARAM)


@dataclass(frozen=True)
class SmokeMeters:
    """Separate prompt vs accepted Writing meters (never conflate)."""

    prompt_tok_s: float
    accepted_writing_tok_s: float
    accept_rate: float
    rss_before_mb: float
    rss_after_mb: float
    rss_delta_mb: float
    expert_bytes_mmap: int
    n_experts: int
    gds_forbidden_ok: bool
    path: str


def _rss_mb() -> float:
    """Current process RSS in MiB (portable ru_maxrss units)."""
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux: KiB; macOS: bytes.
    if sys.platform == "darwin":
        return usage / (1024.0 * 1024.0)
    return usage / 1024.0


def assert_no_gds_imports() -> bool:
    """Fail closed if nvidia-fs / cuFile already imported (CLEAN hygiene)."""
    for name in FORBIDDEN_MODULES:
        if name in sys.modules:
            raise RuntimeError(f"GDS/forbidden module already loaded: {name}")
    return True


def pack_fp4_expert(n_params: int = TOY_EXPERT_PARAMS) -> bytes:
    """Pack toy params as FP4 nibbles (2 params / byte). Deterministic pattern."""
    n_bytes = int(n_params * FP4_BYTES_PER_PARAM)
    # Alternate nibble pattern — not real NVFP4 scales; accounting smoke only.
    return bytes((i * 17) & 0xFF for i in range(n_bytes))


def write_expert_bank(dir_path: Path, n_experts: int = TOY_N_EXPERTS) -> list[Path]:
    """Write mmap-backed FP4 expert files under *dir_path*."""
    paths: list[Path] = []
    blob = pack_fp4_expert()
    for i in range(n_experts):
        p = dir_path / f"expert_{i:02d}.fp4"
        p.write_bytes(blob)
        paths.append(p)
    return paths


def mmap_experts(paths: list[Path]) -> tuple[list[mmap.mmap], int]:
    """Open experts read-only via mmap (NVMe→page-cache→UMA stand-in)."""
    maps: list[mmap.mmap] = []
    total = 0
    for p in paths:
        fd = os.open(p, os.O_RDONLY)
        try:
            mm = mmap.mmap(fd, 0, access=mmap.ACCESS_READ)
        finally:
            os.close(fd)
        maps.append(mm)
        total += len(mm)
    return maps, total


def _touch_mmap(maps: list[mmap.mmap], stride: int = 64) -> int:
    """Force page faults so RSS reflects resident expert pages."""
    touched = 0
    for mm in maps:
        view = memoryview(mm)
        for off in range(0, len(view), stride):
            touched += view[off]
        del view
    return touched


def meter_prompt_tok_s(
    maps: list[mmap.mmap],
    *,
    tokens: int = 2048,
    active_experts: int = 2,
) -> float:
    """Prefill-shaped meter: scan expert tiles per prompt token (GEMM-ish)."""
    if tokens <= 0:
        return 0.0
    t0 = time.perf_counter()
    n = len(maps)
    for tok in range(tokens):
        for e in range(active_experts):
            mm = maps[(tok + e) % n]
            # Cheap checksum over a tile — stands in for FP4 GEMM read.
            _ = mm[0] ^ mm[min(63, len(mm) - 1)]
    elapsed = max(time.perf_counter() - t0, 1e-9)
    return tokens / elapsed


def meter_accepted_writing_tok_s(
    maps: list[mmap.mmap],
    *,
    draft_tokens: int = 512,
    accept_rate: float = 0.75,
    active_experts: int = 2,
) -> tuple[float, float]:
    """Accepted Writing meter — only accepted draft tokens count (C13).

    Returns ``(accepted_tok_s, accept_rate)``. Prompt/prefill must not be
    folded into this number.
    """
    rate = min(1.0, max(0.0, accept_rate))
    accepted = max(1, int(draft_tokens * rate))
    if draft_tokens <= 0:
        return 0.0, rate
    t0 = time.perf_counter()
    n = len(maps)
    # Draft pass (rejected work still burns BW) + accepted verify tiles.
    for tok in range(draft_tokens):
        mm = maps[tok % n]
        _ = mm[0]
    for tok in range(accepted):
        for e in range(active_experts):
            mm = maps[(tok + e) % n]
            _ = mm[0] ^ mm[min(31, len(mm) - 1)]
    elapsed = max(time.perf_counter() - t0, 1e-9)
    return accepted / elapsed, rate


def run_smoke(work_dir: Path | None = None) -> SmokeMeters:
    """Run T0 CLEAN FP4 RSS/mmap smoke; returns separated meters."""
    assert_no_gds_imports()
    rss_before = _rss_mb()
    own_tmp = work_dir is None
    root = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="fp4_smoke_"))
    try:
        paths = write_expert_bank(root)
        maps, total_bytes = mmap_experts(paths)
        try:
            _touch_mmap(maps)
            prompt_tps = meter_prompt_tok_s(maps)
            writing_tps, accept_rate = meter_accepted_writing_tok_s(maps)
            rss_after = _rss_mb()
            return SmokeMeters(
                prompt_tok_s=round(prompt_tps, 3),
                accepted_writing_tok_s=round(writing_tps, 3),
                accept_rate=accept_rate,
                rss_before_mb=round(rss_before, 3),
                rss_after_mb=round(rss_after, 3),
                rss_delta_mb=round(rss_after - rss_before, 3),
                expert_bytes_mmap=total_bytes,
                n_experts=len(paths),
                gds_forbidden_ok=True,
                path=str(root),
            )
        finally:
            for mm in maps:
                mm.close()
    finally:
        if own_tmp:
            for p in root.glob("*.fp4"):
                try:
                    p.unlink()
                except OSError:
                    pass
            try:
                root.rmdir()
            except OSError:
                pass


def iter_meter_keys() -> Iterator[str]:
    """Documented meter keys — prompt vs accepted Writing stay distinct."""
    yield "prompt_tok_s"
    yield "accepted_writing_tok_s"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print meters as JSON")
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="Reuse expert bank directory (default: temp)",
    )
    args = parser.parse_args(argv)
    meters = run_smoke(args.dir)
    if args.json:
        print(json.dumps(asdict(meters), indent=2, sort_keys=True))
    else:
        print("CLEAN FP4 expert RSS/mmap smoke (no nvidia-fs/GDS)")
        print(f"  experts={meters.n_experts} mmap_bytes={meters.expert_bytes_mmap}")
        print(f"  prompt_tok_s={meters.prompt_tok_s}")
        print(f"  accepted_writing_tok_s={meters.accepted_writing_tok_s} (accept={meters.accept_rate})")
        print(
            f"  rss_before_mb={meters.rss_before_mb} "
            f"rss_after_mb={meters.rss_after_mb} "
            f"delta_mb={meters.rss_delta_mb}"
        )
        print(f"  gds_forbidden_ok={meters.gds_forbidden_ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
