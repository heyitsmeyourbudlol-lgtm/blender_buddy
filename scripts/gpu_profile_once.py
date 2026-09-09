#!/usr/bin/env python3
"""Profile-once DGX util + CLEAN FP4 / TE meters — append, never thrash.

OVERSEER_GPU_PROFILE_ONCE_2026_09_05

GPU Profiler niche: snapshot GB10 util once per *code change* of the profile
scope, run CLEAN FP4 expert RSS/mmap smoke (TE stand-in when Transformer Engine
is unavailable), append one JSONL meter line, then skip until scope changes.

Usage::

    python3 scripts/gpu_profile_once.py
    python3 scripts/gpu_profile_once.py --json
    python3 scripts/gpu_profile_once.py --force   # ignore fingerprint skip
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import bitnet_fp4_expert_rss_smoke as fp4  # noqa: E402
import project_automation as auto  # noqa: E402

# OVERSEER_GPU_PROFILE_ONCE_2026_09_05
NEEDLE = "OVERSEER_GPU_PROFILE_ONCE_2026_09_05"

# Scripts whose content gates re-profile (do not re-profile without a code change).
SCOPE_FILES = (
    "scripts/gpu_profile_once.py",
    "scripts/bitnet_fp4_expert_rss_smoke.py",
    "scripts/dgx_gpu_events.py",
)

METERS_NAME = "gpu-profile-meters.jsonl"
STATE_NAME = "gpu-profile-once-state.json"


@dataclass
class ProfileMeters:
    """One profile-once row — DGX util + CLEAN FP4 / TE probe."""

    ts: str
    skipped: bool
    scope_fp: str
    gpu_util_pct: float | None = None
    gpu_temp_c: float | None = None
    gpu_power_w: float | None = None
    gpu_mem_mib: str | None = None
    gpu_name: str | None = None
    te_fp4_available: bool = False
    te_import_error: str | None = None
    prompt_tok_s: float | None = None
    accepted_writing_tok_s: float | None = None
    accept_rate: float | None = None
    rss_delta_mb: float | None = None
    expert_bytes_mmap: int | None = None
    gds_forbidden_ok: bool | None = None
    bottlenecks: list[str] = field(default_factory=list)
    path: str = ""
    note: str = ""


def meters_path() -> Path:
    return auto.CONFIG_DIR / METERS_NAME


def state_path() -> Path:
    return auto.CONFIG_DIR / STATE_NAME


def scope_fingerprint(*, root: Path | None = None) -> str:
    """Stable hash of profile-scope file bytes — change ⇒ allow re-profile."""
    base = root or ROOT
    h = hashlib.sha256()
    for rel in SCOPE_FILES:
        p = base / rel
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        if p.is_file():
            h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:16]


def load_state() -> dict[str, Any]:
    p = state_path()
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    auto.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    state_path().write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def should_skip(*, force: bool = False, root: Path | None = None) -> tuple[bool, str]:
    """True when last profile used the same scope fingerprint (no code change)."""
    fp = scope_fingerprint(root=root)
    if force:
        return False, fp
    st = load_state()
    # Accept legacy code_fp (pre-scope_fp meters) so we do not thrash after schema rename.
    prev = str(st.get("scope_fp") or st.get("code_fp") or "").strip()
    if prev and prev == fp:
        return True, fp
    return False, fp


def _probe_te_fp4() -> tuple[bool, str | None]:
    """Transformer Engine NVFP4 path — honest availability (often absent on Spark)."""
    try:
        import transformer_engine  # noqa: F401

        return True, None
    except Exception as exc:  # noqa: BLE001 — surface any import/runtime miss
        return False, f"{type(exc).__name__}: {exc}"


def _gpu_snap() -> dict[str, Any]:
    try:
        import dgx_gpu_events as gev

        return gev.gpu_snapshot()
    except Exception:  # noqa: BLE001
        return {}


def _bottlenecks(
    *,
    util: float | None,
    te_ok: bool,
    writing_tps: float | None,
    prompt_tps: float | None,
) -> list[str]:
    out: list[str] = []
    if util is not None and util < 5.0:
        out.append("gpu_util_near_idle")
    if not te_ok:
        out.append("transformer_engine_unavailable_use_clean_fp4_mmap")
    if (
        writing_tps is not None
        and prompt_tps is not None
        and prompt_tps > 0
        and writing_tps < prompt_tps * 0.5
    ):
        # CLEAN toy is CPU/mmap — documents C96 posture (Writing ≠ identical TFLOPS).
        out.append("accepted_writing_slower_than_prompt_shape")
    if not out:
        out.append("none_flagged")
    return out


def run_profile(*, force: bool = False, root: Path | None = None) -> ProfileMeters:
    """Profile once (or skip); always returns a meter row."""
    skip, fp = should_skip(force=force, root=root)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if skip:
        return ProfileMeters(
            ts=ts,
            skipped=True,
            scope_fp=fp,
            note="skip — scope fingerprint unchanged (no code change)",
            bottlenecks=["skipped_no_code_change"],
            path=str(meters_path()),
        )

    snap = _gpu_snap()
    util = snap.get("gpu_util_pct")
    try:
        util_f = float(util) if util is not None else None
    except (TypeError, ValueError):
        util_f = None

    te_ok, te_err = _probe_te_fp4()
    smoke = fp4.run_smoke()
    bots = _bottlenecks(
        util=util_f,
        te_ok=te_ok,
        writing_tps=smoke.accepted_writing_tok_s,
        prompt_tps=smoke.prompt_tok_s,
    )
    row = ProfileMeters(
        ts=ts,
        skipped=False,
        scope_fp=fp,
        gpu_util_pct=util_f,
        gpu_temp_c=_float_or_none(snap.get("gpu_temp_c")),
        gpu_power_w=_float_or_none(snap.get("gpu_power_w")),
        gpu_mem_mib=str(snap.get("gpu_mem_mib")) if snap.get("gpu_mem_mib") is not None else None,
        gpu_name=str(snap.get("gpu_name") or snap.get("name") or "NVIDIA GB10"),
        te_fp4_available=te_ok,
        te_import_error=te_err,
        prompt_tok_s=smoke.prompt_tok_s,
        accepted_writing_tok_s=smoke.accepted_writing_tok_s,
        accept_rate=smoke.accept_rate,
        rss_delta_mb=smoke.rss_delta_mb,
        expert_bytes_mmap=smoke.expert_bytes_mmap,
        gds_forbidden_ok=smoke.gds_forbidden_ok,
        bottlenecks=bots,
        path=str(meters_path()),
        note="profile-once DGX util + CLEAN FP4 (TE probe)",
    )
    append_meter(row)
    save_state({"scope_fp": fp, "code_fp": fp, "ts": ts, "meters": str(meters_path())})
    return row


def _float_or_none(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def append_meter(row: ProfileMeters) -> Path:
    """Append one JSON object line to gpu-profile-meters.jsonl."""
    auto.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    p = meters_path()
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(row), sort_keys=True) + "\n")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print meter row as JSON")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-profile even when scope fingerprint unchanged",
    )
    args = parser.parse_args(argv)
    row = run_profile(force=args.force)
    if args.json:
        print(json.dumps(asdict(row), indent=2, sort_keys=True))
    else:
        print(f"GPU profile-once ({NEEDLE})")
        print(f"  skipped={row.skipped} scope_fp={row.scope_fp}")
        if not row.skipped:
            print(f"  gpu_util_pct={row.gpu_util_pct} te_fp4={row.te_fp4_available}")
            print(
                f"  prompt_tok_s={row.prompt_tok_s} "
                f"accepted_writing_tok_s={row.accepted_writing_tok_s}"
            )
            print(f"  bottlenecks={row.bottlenecks}")
            print(f"  meters={row.path}")
        else:
            print(f"  note={row.note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
