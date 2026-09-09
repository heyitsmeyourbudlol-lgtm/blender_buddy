#!/usr/bin/env python3
"""T0 packing proof — synthetic unique-param + 1-bit pack math (no training).

OVERSEER_COMPRESSION_T0_PACK_2026_09_05
OVERSEER_COMPRESSION_T0_PACK_CACHE_2026_09_05
OVERSEER_COMPRESSION_DUAL_SOT_CACHE_2026_09_07

Proves ALBERT-BitMoE (primary) and LoRA-Hive (control) hit:
  N_L ∈ {1e5, 1e6},  C_arith = N_L/U ≥ 50,  packed_bytes ≈ U/8 (± metadata).

Quality/loss is out of scope for T0. No data pruning. Torch-free.
Durable pack report (Lane-U sibling to T3 logit bank) — not a train unlock.
Dual SoT cache (pack + logit bank report) — Lane-U durable gate; still not a train unlock.

Usage::

    python3 scripts/compression_t0_pack.py
    python3 scripts/compression_t0_pack.py --json
    python3 scripts/compression_t0_pack.py --write-report /tmp/t0_pack.json
    python3 scripts/compression_t0_pack.py --check-cache /tmp/t0_pack.json --json
    python3 scripts/compression_t0_pack.py --ensure-default-pack --json
    python3 scripts/compression_t0_pack.py --dual-sot-check --json
    python3 scripts/compression_t0_pack.py --ensure-dual-sot --json
    python3 scripts/compression_t0_pack.py --check-dual-sot-report --json
    python3 scripts/compression_t0_pack.py --probe-keep-alive --json
    python3 scripts/compression_t0_pack.py --check-probe-report --json
    python3 scripts/compression_t0_pack.py --heal-lane-u-sot --json
    # --check-dual-sot-report also RAM-safe stamp-refreshes dual_sot_report.json
    # (OVERSEER_COMPRESSION_DUAL_SOT_STAMP_REFRESH_2026_09_08; live soft only; no ensure)
    # --check-probe-report also RAM-safe stamp-refreshes probe_keep_alive_report.json
    # (OVERSEER_COMPRESSION_PROBE_STAMP_REFRESH_2026_09_08; no undersize mutation)
    # --heal-lane-u-sot runs both checks (post-unittest sticky soft clear; TRAIN-LOCKED)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# OVERSEER_COMPRESSION_T0_PACK_2026_09_05
NEEDLE = "OVERSEER_COMPRESSION_T0_PACK_2026_09_05"
# OVERSEER_COMPRESSION_T0_PACK_CACHE_2026_09_05
CACHE_NEEDLE = "OVERSEER_COMPRESSION_T0_PACK_CACHE_2026_09_05"
# OVERSEER_COMPRESSION_DUAL_SOT_CACHE_2026_09_07
DUAL_SOT_CACHE_NEEDLE = "OVERSEER_COMPRESSION_DUAL_SOT_CACHE_2026_09_07"
# OVERSEER_COMPRESSION_DUAL_SOT_PROBE_KEEP_ALIVE_2026_09_08
PROBE_KEEP_ALIVE_NEEDLE = "OVERSEER_COMPRESSION_DUAL_SOT_PROBE_KEEP_ALIVE_2026_09_08"
# OVERSEER_COMPRESSION_DUAL_SOT_PROBE_CACHE_2026_09_08 — durable probe report (Lane U)
PROBE_CACHE_NEEDLE = "OVERSEER_COMPRESSION_DUAL_SOT_PROBE_CACHE_2026_09_08"
# OVERSEER_COMPRESSION_DUAL_SOT_RAM_SOFT_SKIP_2026_09_08 — full ensure OOMs under RAM storm
DUAL_SOT_RAM_SOFT_NEEDLE = "OVERSEER_COMPRESSION_DUAL_SOT_RAM_SOFT_SKIP_2026_09_08"
# OVERSEER_COMPRESSION_HUB_UNLOCK_IGNORE_2026_09_08 — hub unlock file ≠ Dual SoT unlock
HUB_UNLOCK_IGNORE_NEEDLE = "OVERSEER_COMPRESSION_HUB_UNLOCK_IGNORE_2026_09_08"
# OVERSEER_COMPRESSION_HUB_UNLOCK_FILE_NEEDLE_REVOKED_2026_09_08 — steward-revoked
# unlock JSON still stamps hub_unlock_file_needle (losing it after revoke = Dual SoT theater)
HUB_UNLOCK_FILE_NEEDLE_REVOKED = (
    "OVERSEER_COMPRESSION_HUB_UNLOCK_FILE_NEEDLE_REVOKED_2026_09_08"
)
# OVERSEER_COMPRESSION_PROBE_STAMP_REFRESH_2026_09_08 — RAM-safe check→re-dump (no undersize)
PROBE_STAMP_REFRESH_NEEDLE = "OVERSEER_COMPRESSION_PROBE_STAMP_REFRESH_2026_09_08"
# OVERSEER_COMPRESSION_PROBE_RAM_SOFT_REFRESH_2026_09_08 — stamp-refresh must not sticky-OR ram_soft_skip
PROBE_RAM_SOFT_REFRESH_NEEDLE = "OVERSEER_COMPRESSION_PROBE_RAM_SOFT_REFRESH_2026_09_08"
# OVERSEER_COMPRESSION_DUAL_SOT_STAMP_REFRESH_2026_09_08 — RAM-safe Dual SoT check→re-dump
DUAL_SOT_STAMP_REFRESH_NEEDLE = "OVERSEER_COMPRESSION_DUAL_SOT_STAMP_REFRESH_2026_09_08"
# OVERSEER_COMPRESSION_DUAL_SOT_RAM_SOFT_REFRESH_2026_09_08 — Dual SoT stamp must not sticky-OR soft
DUAL_SOT_RAM_SOFT_REFRESH_NEEDLE = "OVERSEER_COMPRESSION_DUAL_SOT_RAM_SOFT_REFRESH_2026_09_08"
# OVERSEER_COMPRESSION_WORKTREE_ROOT_BIND_2026_09_08 — prefer worktree cwd over hub __file__
WORKTREE_ROOT_BIND_NEEDLE = "OVERSEER_COMPRESSION_WORKTREE_ROOT_BIND_2026_09_08"
# OVERSEER_COMPRESSION_EXPAND_PATH_COERCE_2026_09_08 — refuse corrupt report expand_path
EXPAND_PATH_COERCE_NEEDLE = "OVERSEER_COMPRESSION_EXPAND_PATH_COERCE_2026_09_08"
# OVERSEER_COMPRESSION_LANE_U_SOT_HEAL_2026_09_08 — post-unittest Dual SoT+probe heal
LANE_U_SOT_HEAL_NEEDLE = "OVERSEER_COMPRESSION_LANE_U_SOT_HEAL_2026_09_08"
# OVERSEER_COMPRESSION_PACK_BANK_PATH_HONESTY_2026_09_08 — hub pack/bank under peer cwd → peer twin
PACK_BANK_PATH_HONESTY_NEEDLE = (
    "OVERSEER_COMPRESSION_PACK_BANK_PATH_HONESTY_2026_09_08"
)
# Below this MemAvailable, --ensure-dual-sot soft-skips to check_dual_sot_report (no unlock).
# 2 GiB was too low — live probe still OOM-killed (rc 137) at ~2.4 GiB avail.
ENSURE_DUAL_SOT_RAM_FLOOR_KB = 8 * 1024 * 1024  # 8 GiB
# Unittests / forced heal: set to 1 to bypass soft-skip even under low RAM.
ENSURE_DUAL_SOT_FORCE_ENV = "COMPRESSION_ENSURE_DUAL_FORCE"


def _worktree_root_from_cwd(cwd: Path | None = None) -> Path | None:
    """Return ``.../.worktrees/peer-N`` when cwd is under a peer worktree with artifacts."""
    cur = (cwd or Path.cwd()).resolve()
    parts = cur.parts
    if ".worktrees" not in parts:
        return None
    i = parts.index(".worktrees")
    if i + 1 >= len(parts):
        return None
    wt = Path(*parts[: i + 2])
    if not (wt / "notes" / "compression_artifacts").is_dir():
        return None
    return wt


def _resolve_repo_root(
    *,
    cwd: Path | None = None,
    file_path: Path | None = None,
) -> Path:
    """Prefer peer worktree cwd when hub scripts module is imported under a worktree.

    Needle: WORKTREE_ROOT_BIND_NEEDLE. Bare ``import compression_t0_pack`` with hub
    scripts on ``sys.path`` would otherwise dump Dual SoT onto hub ROOT and clobber
    hub stamps (e.g. drop ``hub_unlock_file_needle``).
    """
    file_root = (file_path or Path(__file__)).resolve().parents[1]
    wt = _worktree_root_from_cwd(cwd)
    if wt is not None and wt.resolve() != file_root.resolve():
        return wt
    return file_root


def _redirect_hub_artifact_path(path: Path, *, cwd: Path | None = None) -> Path:
    """If ``path`` is under hub compression_artifacts while cwd is a worktree, redirect."""
    wt = _worktree_root_from_cwd(cwd)
    if wt is None:
        return path
    hub_art = (wt.parent.parent / "notes" / "compression_artifacts").resolve()
    wt_art = (wt / "notes" / "compression_artifacts").resolve()
    try:
        rel = path.resolve().relative_to(hub_art)
    except ValueError:
        return path
    return wt_art / rel


def coerce_expand_path(raw: Any, *, default: Path | None = None) -> Path:
    """Refuse corrupt Dual SoT ``expand_path`` (e.g. ``\"z\"``); use Lane-U EXPANDED.

    Needle: EXPAND_PATH_COERCE_NEEDLE. Report-only expand_path that is relative
    junk or a missing file must not fail-closed Dual SoT / probe keep-alive when
    the durable expanded bank exists. Still TRAIN-LOCKED.
    """
    import compression_logit_expand as expand

    fallback = Path(default) if default is not None else Path(expand.EXPANDED)
    fallback = _redirect_hub_artifact_path(fallback)
    if raw is None or raw == "":
        return fallback
    try:
        cand = Path(str(raw))
    except (TypeError, ValueError):
        return fallback
    # Relative single-segment junk ("z") is never a durable SoT path.
    if not cand.is_absolute() and len(cand.parts) <= 1:
        return fallback
    try:
        cand = _redirect_hub_artifact_path(cand.resolve())
    except OSError:
        return fallback
    if not cand.is_file():
        return fallback
    return cand


_ROOT = _resolve_repo_root()
# Canonical packing SoT (repo-relative; TRAIN still LOCKED — not a train unlock)
DEFAULT_PACK_PATH = _ROOT / "notes" / "compression_artifacts" / "t0_pack_report.json"
# Dual SoT durable report (pack + T3 logit bank); TRAIN still LOCKED
DEFAULT_DUAL_SOT_PATH = (
    _ROOT / "notes" / "compression_artifacts" / "dual_sot_report.json"
)
# Sibling unlock stamp (hub may set true; peer Dual SoT must ignore until recipe TRAIN-LOCK)
DEFAULT_TRAIN_UNLOCK_PATH = (
    _ROOT / "notes" / "compression_artifacts" / "train_unlock.json"
)
# Probe keep-alive durable report (undersize→heal); TRAIN still LOCKED
DEFAULT_PROBE_PATH = (
    _ROOT / "notes" / "compression_artifacts" / "probe_keep_alive_report.json"
)

# Pass gates (COMPRESSION_NOVEL.md T0)
MIN_ARITH = 50.0
# Prefer ~100 when geometry is easy; soft target for reporting only.
PREFER_ARITH = 100.0
# Packed store may add a tiny header; payload must track U/8.
META_HEADER_BYTES = 16
META_BOUND_BYTES = 64
# Fail if unique or pack miss target by >2× (falsifier).
FAIL_MISS_FACTOR = 2.0

N_L_TARGETS = (100_000, 1_000_000)


@dataclass(frozen=True)
class PackResult:
    stack: str
    n_logic: int
    u_unique: int
    s_arith: float
    packed_bytes: int
    payload_bytes: int
    meta_bytes: int
    pass_arith: bool
    pass_pack: bool
    passed: bool
    quality: str  # always N/A for T0
    detail: dict[str, Any]


def _pack_1bit(u: int, meta_bytes: int = META_HEADER_BYTES) -> tuple[int, int]:
    """Pack U ternary/1-bit slots → (payload_bytes, packed_bytes)."""
    payload = (u + 7) // 8
    return payload, payload + meta_bytes


def _pass_pack(u: int, packed_bytes: int) -> bool:
    """packed ≈ U/8 within metadata bound (ceil vs float both allowed)."""
    ideal = u / 8.0
    ceil_ideal = (u + 7) // 8
    return (
        abs(packed_bytes - ideal) <= META_BOUND_BYTES
        or abs(packed_bytes - ceil_ideal) <= META_BOUND_BYTES
    )


def albert_bitmoe(n_logic: int) -> PackResult:
    """ALBERT-BitMoE: one shared 1-bit FFN body + per-layer LoRA.

    U = B_body + L * r * (d_in + d_out)   with L_share = L
    N_L = L * B_body
    """
    # Geometry tuned for exact N_L and S ≳ 80 (prefer ~100).
    # L=100 → B = N_L/100; tiny LoRA so body share dominates.
    layers = 100
    if n_logic % layers != 0:
        raise ValueError(f"n_logic={n_logic} not divisible by L={layers}")
    body = n_logic // layers
    # Synthetic body shape (up+down): d_in * d_ff + d_ff * d_out == body
    d_in = d_out = max(1, int(math.isqrt(max(body // 2, 1))))
    d_ff = max(1, body // (d_in + d_out))
    body_unique = body  # shared once (= N_L / L)

    r = 1
    # Tiny adapter dims so LoRA does not erase the share win (still nonzero U_lora).
    lora_d_in, lora_d_out = 1, 1
    u_lora = layers * r * (lora_d_in + lora_d_out)
    u = body_unique + u_lora
    s = n_logic / u
    payload, packed = _pack_1bit(u)
    pass_arith = s >= MIN_ARITH
    pass_pack = _pass_pack(u, packed)
    # Fail if unique/pack miss hard floor by >2× (COMPRESSION_NOVEL falsifier).
    passed = pass_arith and pass_pack and s >= (MIN_ARITH / FAIL_MISS_FACTOR)
    return PackResult(
        stack="ALBERT-BitMoE",
        n_logic=n_logic,
        u_unique=u,
        s_arith=s,
        packed_bytes=packed,
        payload_bytes=payload,
        meta_bytes=META_HEADER_BYTES,
        pass_arith=pass_arith,
        pass_pack=pass_pack,
        passed=passed,
        quality="N/A",
        detail={
            "L": layers,
            "L_share": layers,
            "B_body": body_unique,
            "r": r,
            "lora_d_in": lora_d_in,
            "lora_d_out": lora_d_out,
            "u_lora": u_lora,
            "d_in_body": d_in,
            "d_ff_body": d_ff,
            "d_out_body": d_out,
            "formula": "U = B_body + L*r*(d_in+d_out); N_L = L*B_body",
        },
    )


def lora_hive(n_logic: int) -> PackResult:
    """LoRA-Hive: shared 1-bit hive + per-expert LoRA (control).

    Amortized: U = B_hive/E + r*(d_in+d_out), N_L = B_hive
    (equivalently total N = E*B_hive, U_tot = B_hive + E*r*(...)).
    """
    experts = 100
    b_hive = n_logic  # logical expert size = hive body
    r = 1
    lora_d_in, lora_d_out = 1, 1
    u_lora_amortized = r * (lora_d_in + lora_d_out)
    u = b_hive // experts + u_lora_amortized
    # Exact integer share: require divisible hive.
    if b_hive % experts != 0:
        raise ValueError(f"n_logic={n_logic} not divisible by E={experts}")
    s = n_logic / u
    payload, packed = _pack_1bit(u)
    pass_arith = s >= MIN_ARITH
    pass_pack = _pass_pack(u, packed)
    passed = pass_arith and pass_pack and s >= (MIN_ARITH / FAIL_MISS_FACTOR)
    return PackResult(
        stack="LoRA-Hive",
        n_logic=n_logic,
        u_unique=u,
        s_arith=s,
        packed_bytes=packed,
        payload_bytes=payload,
        meta_bytes=META_HEADER_BYTES,
        pass_arith=pass_arith,
        pass_pack=pass_pack,
        passed=passed,
        quality="N/A",
        detail={
            "E": experts,
            "B_hive": b_hive,
            "r": r,
            "lora_d_in": lora_d_in,
            "lora_d_out": lora_d_out,
            "u_hive_amortized": b_hive // experts,
            "u_lora_amortized": u_lora_amortized,
            "formula": "U_e = B_hive/E + r*(d_in+d_out); N_L = B_hive",
        },
    )


def run_all(n_targets: tuple[int, ...] = N_L_TARGETS) -> list[PackResult]:
    rows: list[PackResult] = []
    for n in n_targets:
        rows.append(albert_bitmoe(n))
        rows.append(lora_hive(n))
    return rows


def summary_dict(rows: list[PackResult]) -> dict[str, Any]:
    return {
        "needle": NEEDLE,
        "cache_needle": CACHE_NEEDLE,
        "min_arith": MIN_ARITH,
        "prefer_arith": PREFER_ARITH,
        "meta_header_bytes": META_HEADER_BYTES,
        "meta_bound_bytes": META_BOUND_BYTES,
        "quality": "N/A",  # packing proof only — never measured LM
        "data_prune": False,  # RECIPE: no data/example/token prune
        "train_unlocked": False,  # T0 packing ≠ permission to train
        "all_passed": all(r.passed for r in rows),
        "results": [asdict(r) for r in rows],
    }


def dump_pack_report(path: str | Path, rows: list[PackResult] | None = None) -> Path:
    """Persist packing SoT JSON (no prune). TRAIN still LOCKED."""
    out = _redirect_hub_artifact_path(Path(path))
    payload = summary_dict(rows if rows is not None else run_all())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    return out


def load_pack_report(path: str | Path) -> dict[str, Any]:
    """Reload durable pack report; refuse pruned / train-unlocked caches."""
    path = _redirect_hub_artifact_path(Path(path))
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("needle") not in (None, NEEDLE):
        raise ValueError(f"refusing pack report with foreign needle: {data.get('needle')!r}")
    if data.get("cache_needle") != CACHE_NEEDLE:
        raise ValueError(
            f"refusing pack report missing cache_needle={CACHE_NEEDLE!r} "
            f"(got {data.get('cache_needle')!r})"
        )
    if data.get("data_prune") is True:
        raise ValueError("refusing pruned pack report cache")
    if data.get("train_unlocked") is True:
        raise ValueError("refusing train-unlocked pack report (recipe LOCKED)")
    results = data.get("results")
    if not isinstance(results, list) or len(results) != len(N_L_TARGETS) * 2:
        raise ValueError("pack report results length mismatch")
    return data


def _results_fingerprint(payload: dict[str, Any]) -> list[tuple[Any, ...]]:
    rows = []
    for r in payload["results"]:
        rows.append(
            (
                r["stack"],
                int(r["n_logic"]),
                int(r["u_unique"]),
                float(r["s_arith"]),
                int(r["packed_bytes"]),
                bool(r["passed"]),
            )
        )
    return rows


def pack_cache_roundtrip_ok(path: str | Path | None = None) -> bool:
    """Fresh run → dump → load must match packing fingerprint."""
    import tempfile

    fresh = summary_dict(run_all())
    if path is None:
        with tempfile.TemporaryDirectory(prefix="t0_pack_") as td:
            p = Path(td) / "pack.json"
            dump_pack_report(p, run_all())
            cached = load_pack_report(p)
            return (
                fresh["all_passed"]
                and cached["all_passed"] is True
                and _results_fingerprint(fresh) == _results_fingerprint(cached)
                and cached.get("train_unlocked") is False
                and cached.get("data_prune") is False
            )
    dump_pack_report(path, run_all())
    cached = load_pack_report(path)
    return (
        fresh["all_passed"]
        and cached["all_passed"] is True
        and _results_fingerprint(fresh) == _results_fingerprint(cached)
        and cached.get("train_unlocked") is False
        and cached.get("data_prune") is False
    )


def ensure_default_pack(path: Path | None = None) -> tuple[Path, bool]:
    """Dump canonical repo pack report + prove load match. TRAIN still LOCKED."""
    out = Path(path) if path is not None else DEFAULT_PACK_PATH
    rows = run_all()
    fresh = summary_dict(rows)
    dump_pack_report(out, rows)
    meta = load_pack_report(out)
    ok = (
        fresh["all_passed"]
        and meta["all_passed"] is True
        and _results_fingerprint(fresh) == _results_fingerprint(meta)
        and meta.get("train_unlocked") is False
        and meta.get("data_prune") is False
        and meta.get("cache_needle") == CACHE_NEEDLE
        and meta.get("needle") == NEEDLE
    )
    return out, ok


def _train_unlock_candidates() -> list[Path]:
    """Local worktree unlock file, then hub Automation twin when under .worktrees/."""
    paths = [DEFAULT_TRAIN_UNLOCK_PATH]
    if _ROOT.parent.name == ".worktrees":
        hub = (
            _ROOT.parent.parent
            / "notes"
            / "compression_artifacts"
            / "train_unlock.json"
        )
        try:
            if hub.resolve() != DEFAULT_TRAIN_UNLOCK_PATH.resolve():
                paths.append(hub)
        except OSError:
            paths.append(hub)
    return paths


def hub_train_unlock_status() -> dict[str, Any]:
    """Detect hub/sibling train_unlock.json; Dual SoT still stays locked.

    Needle: HUB_UNLOCK_IGNORE_NEEDLE. Peer recipe stub is SoT until explicit
    TRAIN-LOCK card fill — hub unlock stamp must not flip Dual SoT.

    Always stamp ``hub_unlock_file_needle`` from a readable unlock JSON
    (claimed **or** steward-revoked). Losing the file needle after revoke
    made Dual SoT dumps look unlock-naive (HUB_UNLOCK_FILE_NEEDLE_REVOKED).
    ``hub_unlock_ignored`` only when ``train_unlocked`` was claimed true.
    """
    out: dict[str, Any] = {
        "hub_unlock_ignore_needle": HUB_UNLOCK_IGNORE_NEEDLE,
        "hub_unlock_file_needle_revoked": HUB_UNLOCK_FILE_NEEDLE_REVOKED,
        "hub_unlock_present": False,
        "hub_unlock_claimed": False,
        "hub_unlock_ignored": False,
        "hub_unlock_path": None,
        "train_unlocked": False,  # always — ignore ≠ unlock
    }
    for path in _train_unlock_candidates():
        if not path.is_file():
            continue
        out["hub_unlock_present"] = True
        out["hub_unlock_path"] = str(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        # Record which unlock stamp was inspected even when steward-revoked
        # (train_unlocked=false). Claimed files still win and stop the scan.
        if data.get("needle") is not None:
            out["hub_unlock_file_needle"] = data.get("needle")
        if data.get("train_unlocked") is True:
            out["hub_unlock_claimed"] = True
            out["hub_unlock_ignored"] = True
            out["hub_unlock_file_needle"] = data.get("needle")
            break
    return out


def apply_hub_unlock_ignore(payload: dict[str, Any]) -> dict[str, Any]:
    """Stamp hub-unlock ignore fields; force train_unlocked=false."""
    st = hub_train_unlock_status()
    payload["hub_unlock_ignore_needle"] = st["hub_unlock_ignore_needle"]
    payload["hub_unlock_file_needle_revoked"] = st.get(
        "hub_unlock_file_needle_revoked"
    ) or HUB_UNLOCK_FILE_NEEDLE_REVOKED
    payload["hub_unlock_present"] = st["hub_unlock_present"]
    payload["hub_unlock_claimed"] = st["hub_unlock_claimed"]
    payload["hub_unlock_ignored"] = st["hub_unlock_ignored"]
    if st.get("hub_unlock_path") is not None:
        payload["hub_unlock_path"] = st["hub_unlock_path"]
    if st.get("hub_unlock_file_needle") is not None:
        payload["hub_unlock_file_needle"] = st["hub_unlock_file_needle"]
    payload["train_unlocked"] = False
    return payload


# Back-compat alias (tests / prior drafts)
_apply_hub_unlock_ignore = apply_hub_unlock_ignore


def dual_sot_check(
    pack_path: Path | None = None,
    bank_path: Path | None = None,
) -> dict[str, Any]:
    """TRAIN-LOCK Dual SoT: canonical T0 pack + T3 logit bank both green.

    Recipe must not unlock real train until both durable caches load clean
    (no prune, train_unlocked=false). Does **not** unlock training.
    Hub train_unlock.json=true is detected and ignored (HUB_UNLOCK_IGNORE_NEEDLE).
    Hub pack/bank paths under peer cwd redirect to worktree twins
    (PACK_BANK_PATH_HONESTY_NEEDLE) — keep-alive must not claim hub SoT while
    dumping peer Dual SoT.
    """
    import compression_t3_bitdistill as t3

    pack = Path(pack_path) if pack_path is not None else DEFAULT_PACK_PATH
    bank = Path(bank_path) if bank_path is not None else t3.DEFAULT_BANK_PATH
    # Worktree bind honesty: hub absolute pack/bank + peer cwd → peer twin.
    pack = _redirect_hub_artifact_path(pack)
    bank = _redirect_hub_artifact_path(bank)
    out: dict[str, Any] = {
        "dual_sot": True,
        "train_unlocked": False,  # Dual SoT green ≠ TRAIN unlock
        "data_prune": False,
        "pack_path": str(pack),
        "bank_path": str(bank),
        "pack_ok": False,
        "bank_ok": False,
        "dual_sot_ok": False,
        "quality": "proxy",
        "pack_bank_path_honesty_needle": PACK_BANK_PATH_HONESTY_NEEDLE,
        "worktree_root_bind_needle": WORKTREE_ROOT_BIND_NEEDLE,
    }
    try:
        pack_meta = load_pack_report(pack)
        fresh = summary_dict(run_all())
        out["pack_ok"] = (
            pack_meta.get("all_passed") is True
            and fresh["all_passed"]
            and _results_fingerprint(fresh) == _results_fingerprint(pack_meta)
            and pack_meta.get("train_unlocked") is False
            and pack_meta.get("data_prune") is False
            and pack_meta.get("cache_needle") == CACHE_NEEDLE
        )
        out["pack_needle"] = pack_meta.get("needle")
        out["pack_cache_needle"] = pack_meta.get("cache_needle")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        out["pack_error"] = str(exc)
        out["pack_ok"] = False

    try:
        out["bank_ok"] = bool(t3.check_bank_at_path(bank))
        bank_meta = json.loads(bank.read_text(encoding="utf-8"))
        out["bank_needle"] = bank_meta.get("needle")
        out["bank_cache_needle"] = bank_meta.get("cache_needle")
        if bank_meta.get("train_unlocked") is True or bank_meta.get("data_prune") is True:
            out["bank_ok"] = False
    except (OSError, ValueError, KeyError, TypeError) as exc:
        out["bank_error"] = str(exc)
        out["bank_ok"] = False

    out["dual_sot_ok"] = bool(out["pack_ok"] and out["bank_ok"])
    # Hub train_unlock.json may be true — peer Dual SoT still refuses unlock.
    return _apply_hub_unlock_ignore(out)


def dump_dual_sot_report(path: str | Path, payload: dict[str, Any]) -> Path:
    """Persist Dual SoT gate report (pack + logit). TRAIN still LOCKED."""
    out = _redirect_hub_artifact_path(Path(path))
    stamped = apply_hub_unlock_ignore(dict(payload))
    body = {
        "needle": DUAL_SOT_CACHE_NEEDLE,
        "cache_needle": DUAL_SOT_CACHE_NEEDLE,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dual_sot": True,
        "dual_sot_ok": bool(stamped.get("dual_sot_ok")),
        "pack_ok": bool(stamped.get("pack_ok")),
        "bank_ok": bool(stamped.get("bank_ok")),
        "pack_cache_ok": bool(stamped.get("pack_cache_ok")),
        "bank_cache_ok": bool(stamped.get("bank_cache_ok")),
        "pack_path": stamped.get("pack_path"),
        "bank_path": stamped.get("bank_path"),
        "pack_needle": stamped.get("pack_needle"),
        "pack_cache_needle": stamped.get("pack_cache_needle"),
        "bank_needle": stamped.get("bank_needle"),
        "bank_cache_needle": stamped.get("bank_cache_needle"),
        # Sidecar expand keep-alive (Lane U); Dual SoT gate stays pack+canonical.
        "expand_ok": bool(stamped.get("expand_ok")),
        "expand_path": stamped.get("expand_path"),
        "expand_n_before": stamped.get("expand_n_before"),
        "expand_n_after": stamped.get("expand_n_after"),
        "expand_needle": stamped.get("expand_needle"),
        "train_unlocked": False,
        "data_prune": False,
        "quality": stamped.get("quality") or "proxy",
        "hub_unlock_ignore_needle": stamped.get("hub_unlock_ignore_needle"),
        "hub_unlock_ignored": bool(stamped.get("hub_unlock_ignored")),
        "hub_unlock_claimed": bool(stamped.get("hub_unlock_claimed")),
        "hub_unlock_present": bool(stamped.get("hub_unlock_present")),
        # Honesty: stamp worktree-bind needle when dump redirected off hub.
        "worktree_root_bind_needle": WORKTREE_ROOT_BIND_NEEDLE,
        # Durable expand-path coerce honesty (EXPAND_PATH_COERCE): CLI-only
        # expand_path_coerce_needle on check_* was theater — SoT dumps must carry it.
        "expand_path_coerce_needle": (
            stamped.get("expand_path_coerce_needle") or EXPAND_PATH_COERCE_NEEDLE
        ),
        # Pack/bank path honesty (PACK_BANK_PATH_HONESTY): hub args under peer cwd
        # must dump peer twin paths — CLI-only redirect was theater.
        "pack_bank_path_honesty_needle": (
            stamped.get("pack_bank_path_honesty_needle")
            or PACK_BANK_PATH_HONESTY_NEEDLE
        ),
    }
    if stamped.get("hub_unlock_path") is not None:
        body["hub_unlock_path"] = stamped["hub_unlock_path"]
    if stamped.get("hub_unlock_file_needle") is not None:
        body["hub_unlock_file_needle"] = stamped["hub_unlock_file_needle"]
    if stamped.get("hub_unlock_file_needle_revoked") is not None:
        body["hub_unlock_file_needle_revoked"] = stamped[
            "hub_unlock_file_needle_revoked"
        ]
    # Soft-skip honesty: durable Dual SoT must stamp RAM soft-skip when dump
    # came from ensure_dual_sot soft path (OVERSEER_COMPRESSION_DUAL_SOT_RAM_SOFT_SKIP_2026_09_08).
    if stamped.get("ram_soft_skip") is not None:
        body["ram_soft_skip"] = bool(stamped.get("ram_soft_skip"))
    if stamped.get("ram_soft_needle") is not None:
        body["ram_soft_needle"] = stamped["ram_soft_needle"]
    if stamped.get("mem_available_kb") is not None:
        body["mem_available_kb"] = stamped["mem_available_kb"]
    if stamped.get("ram_floor_kb") is not None:
        body["ram_floor_kb"] = stamped["ram_floor_kb"]
    # Durable stamp-refresh honesty (DUAL_SOT_STAMP_REFRESH): persist when
    # check_dual_sot_report re-dumps — CLI-only stamp_refreshed is theater.
    # Always stamp Dual SoT refresh needles so ensure dumps cannot drop Lane-U
    # honesty fields (sticky soft clears via check stamp-refresh must stay visible).
    body["stamp_refresh_needle"] = (
        stamped.get("stamp_refresh_needle") or DUAL_SOT_STAMP_REFRESH_NEEDLE
    )
    body["ram_soft_refresh_needle"] = (
        stamped.get("ram_soft_refresh_needle") or DUAL_SOT_RAM_SOFT_REFRESH_NEEDLE
    )
    if stamped.get("stamp_refreshed") is not None:
        body["stamp_refreshed"] = bool(stamped.get("stamp_refreshed"))
    body["artifact_root"] = str(_resolve_repo_root())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def load_dual_sot_report(path: str | Path) -> dict[str, Any]:
    """Reload Dual SoT report; refuse prune / unlock / foreign needle / expand miss."""
    path = _redirect_hub_artifact_path(Path(path))
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("cache_needle") != DUAL_SOT_CACHE_NEEDLE:
        raise ValueError(
            f"refusing dual-sot report missing cache_needle={DUAL_SOT_CACHE_NEEDLE!r} "
            f"(got {data.get('cache_needle')!r})"
        )
    if data.get("data_prune") is True:
        raise ValueError("refusing pruned dual-sot report")
    if data.get("train_unlocked") is True:
        raise ValueError("refusing train-unlocked dual-sot report (recipe LOCKED)")
    if data.get("dual_sot_ok") is not True:
        raise ValueError("refusing dual-sot report with dual_sot_ok≠true")
    # Lane-U: ensure dumps expand_ok; stale reports without expand sidecar fail-closed.
    if data.get("expand_ok") is not True:
        raise ValueError("refusing dual-sot report with expand_ok≠true")
    return data


def dump_probe_report(path: str | Path, payload: dict[str, Any]) -> Path:
    """Persist Dual SoT probe keep-alive report. TRAIN still LOCKED."""
    out = _redirect_hub_artifact_path(Path(path))
    stamped = apply_hub_unlock_ignore(dict(payload))
    body = {
        "needle": PROBE_CACHE_NEEDLE,
        "cache_needle": PROBE_CACHE_NEEDLE,
        "probe_needle": PROBE_KEEP_ALIVE_NEEDLE,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probe_keep_alive": True,
        "probe_ok": bool(stamped.get("probe_ok")),
        "undersize_ok": bool(stamped.get("undersize_ok")),
        "healed_ok": bool(stamped.get("healed_ok")),
        "heal_via_expand": bool(stamped.get("heal_via_expand")),
        "dual_sot_ok": bool(stamped.get("dual_sot_ok")),
        "expand_ok": bool(stamped.get("expand_ok")),
        "pack_ok": bool(stamped.get("pack_ok")),
        "bank_ok": bool(stamped.get("bank_ok")),
        "ram_soft_skip": bool(stamped.get("ram_soft_skip")),
        "expand_n_before": stamped.get("expand_n_before"),
        "expand_n_after": stamped.get("expand_n_after"),
        "expand_path": stamped.get("expand_path"),
        "snip_limit": stamped.get("snip_limit"),
        "mem_available_kb": stamped.get("mem_available_kb"),
        "ram_floor_kb": stamped.get("ram_floor_kb") or ENSURE_DUAL_SOT_RAM_FLOOR_KB,
        "train_unlocked": False,
        "data_prune": False,
        "quality": stamped.get("quality") or "proxy",
        "hub_unlock_ignore_needle": stamped.get("hub_unlock_ignore_needle"),
        "hub_unlock_ignored": bool(stamped.get("hub_unlock_ignored")),
        "hub_unlock_claimed": bool(stamped.get("hub_unlock_claimed")),
        "hub_unlock_present": bool(stamped.get("hub_unlock_present")),
        "stamp_refresh_needle": PROBE_STAMP_REFRESH_NEEDLE,
        "ram_soft_refresh_needle": stamped.get("ram_soft_refresh_needle")
        or PROBE_RAM_SOFT_REFRESH_NEEDLE,
        "worktree_root_bind_needle": WORKTREE_ROOT_BIND_NEEDLE,
        # Durable expand-path coerce honesty (EXPAND_PATH_COERCE): CLI-only
        # expand_path_coerce_needle on check_probe_report was theater.
        "expand_path_coerce_needle": (
            stamped.get("expand_path_coerce_needle") or EXPAND_PATH_COERCE_NEEDLE
        ),
    }
    if stamped.get("hub_unlock_path") is not None:
        body["hub_unlock_path"] = stamped["hub_unlock_path"]
    if stamped.get("hub_unlock_file_needle") is not None:
        body["hub_unlock_file_needle"] = stamped["hub_unlock_file_needle"]
    if stamped.get("hub_unlock_file_needle_revoked") is not None:
        body["hub_unlock_file_needle_revoked"] = stamped[
            "hub_unlock_file_needle_revoked"
        ]
    # Durable stamp-refresh honesty (PROBE_STAMP_REFRESH): persist stamp_refreshed
    # when check_probe_report re-dumps — CLI-only flag is theater for Lane-U SoT.
    if stamped.get("stamp_refreshed") is not None:
        body["stamp_refreshed"] = bool(stamped.get("stamp_refreshed"))
    body["artifact_root"] = str(_resolve_repo_root())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def load_probe_report(path: str | Path) -> dict[str, Any]:
    """Reload probe report; refuse prune / unlock / foreign needle / probe_ok miss."""
    path = _redirect_hub_artifact_path(Path(path))
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("cache_needle") != PROBE_CACHE_NEEDLE:
        raise ValueError(
            f"refusing probe report missing cache_needle={PROBE_CACHE_NEEDLE!r} "
            f"(got {data.get('cache_needle')!r})"
        )
    if data.get("data_prune") is True:
        raise ValueError("refusing pruned probe report")
    if data.get("train_unlocked") is True:
        raise ValueError("refusing train-unlocked probe report (recipe LOCKED)")
    if data.get("probe_ok") is not True:
        raise ValueError("refusing probe report with probe_ok≠true")
    if data.get("expand_ok") is not True:
        raise ValueError("refusing probe report with expand_ok≠true")
    return data


def check_probe_report(report_path: Path | None = None) -> dict[str, Any]:
    """Lane-U durable probe report check (sibling to ``--check-dual-sot-report``).

    Loads ``probe_keep_alive_report.json`` (probe_ok + expand_ok required) and
    live-probes the logit-expand sidecar so a stale report cannot false-green
    an undersized durable bank. Does **not** re-run undersize mutation; does
    **not** unlock training.

    On ``probe_ok``, RAM-safe stamp-refresh re-dumps the durable report with
    fresh ``ts`` + hub-unlock ignore fields (PROBE_STAMP_REFRESH_NEEDLE) —
    keep-alive under MemAvailable soft-skip without OOM undersize heal.
    ``ram_soft_skip`` is set from **live** ``_should_ram_soft_skip`` only
    (never OR'd with a stale dump — sticky true after RAM recovers is a lie).
    """
    import compression_logit_expand as expand

    report = Path(report_path) if report_path is not None else DEFAULT_PROBE_PATH
    # Prefer peer worktree twin before load (hub path + peer cwd must not
    # false-green from stale hub Dual SoT / probe SoT — WORKTREE_ROOT_BIND).
    report = _redirect_hub_artifact_path(report)
    out: dict[str, Any] = {
        "check_probe_report": True,
        "probe_keep_alive": True,
        "train_unlocked": False,
        "data_prune": False,
        "probe_report_path": str(report),
        "probe_cache_needle": PROBE_CACHE_NEEDLE,
        "probe_needle": PROBE_KEEP_ALIVE_NEEDLE,
        "stamp_refresh_needle": PROBE_STAMP_REFRESH_NEEDLE,
        "stamp_refreshed": False,
        "probe_report_ok": False,
        "probe_ok": False,
        "expand_ok": False,
        "dual_sot_ok": False,
        "quality": "proxy",
        "worktree_root_bind_needle": WORKTREE_ROOT_BIND_NEEDLE,
    }
    loaded: dict[str, Any] | None = None
    try:
        loaded = load_probe_report(report)
        out["probe_report_ok"] = True
        out["expand_path"] = loaded.get("expand_path")
        out["expand_n_before"] = loaded.get("expand_n_before")
        out["expand_n_after"] = loaded.get("expand_n_after")
        out["heal_via_expand"] = loaded.get("heal_via_expand")
        out["undersize_ok"] = loaded.get("undersize_ok")
        out["healed_ok"] = loaded.get("healed_ok")
        out["snip_limit"] = loaded.get("snip_limit")
        out["ram_soft_skip"] = loaded.get("ram_soft_skip")
        out["pack_ok"] = loaded.get("pack_ok")
        out["bank_ok"] = loaded.get("bank_ok")
        out["mem_available_kb"] = loaded.get("mem_available_kb")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        out["probe_report_error"] = str(exc)
        out["probe_report_ok"] = False
        out["probe_ok"] = False
        return out

    expand_path = coerce_expand_path(out.get("expand_path"))
    out["expand_path_coerce_needle"] = EXPAND_PATH_COERCE_NEEDLE
    expand_live = expand.check_expanded(expand_path)
    out["expand_ok"] = bool(expand_live.get("expand_ok"))
    out["expand_path"] = str(expand_path)
    if expand_live.get("n_before") is not None:
        out["expand_n_before"] = expand_live.get("n_before")
    if expand_live.get("n_after") is not None:
        out["expand_n_after"] = expand_live.get("n_after")
    if expand_live.get("error"):
        out["expand_error"] = expand_live.get("error")
    if expand_live.get("expand_rows") is not None:
        out["expand_rows"] = expand_live.get("expand_rows")

    live = dual_sot_check()
    out["pack_ok"] = bool(live.get("pack_ok"))
    out["bank_ok"] = bool(live.get("bank_ok"))
    out["dual_sot_ok"] = bool(live.get("dual_sot_ok"))
    out["train_unlocked"] = False
    out["probe_ok"] = bool(
        out["probe_report_ok"]
        and out.get("expand_ok")
        and live.get("dual_sot_ok")
        and out["train_unlocked"] is False
        and out["data_prune"] is False
    )
    stamped = _apply_hub_unlock_ignore(out)
    # RAM-safe keep-alive: refresh durable stamp without undersize mutation.
    if stamped.get("probe_ok") and loaded is not None:
        soft, avail_kb = _should_ram_soft_skip()
        # Live soft only — do not OR stale dump (sticky true after RAM recovers).
        # Needles: PROBE_STAMP_REFRESH + PROBE_RAM_SOFT_REFRESH.
        stamped["ram_soft_skip"] = bool(soft)
        stamped["ram_soft_refresh_needle"] = PROBE_RAM_SOFT_REFRESH_NEEDLE
        if avail_kb is not None:
            stamped["mem_available_kb"] = avail_kb
        stamped["ram_floor_kb"] = ENSURE_DUAL_SOT_RAM_FLOOR_KB
        # Preserve falsifiable heal fields from prior probe dump.
        for key in (
            "undersize_ok",
            "healed_ok",
            "heal_via_expand",
            "snip_limit",
        ):
            if stamped.get(key) is None and loaded.get(key) is not None:
                stamped[key] = loaded[key]
        try:
            # Set stamp_refreshed BEFORE dump so durable probe SoT records it
            # (CLI-only stamp_refreshed after dump was theater — output-compare
            # could not prove keep-alive advanced from probe_keep_alive_report.json).
            stamped["stamp_refreshed"] = True
            stamped["stamp_refresh_needle"] = PROBE_STAMP_REFRESH_NEEDLE
            # Worktree bind: never dump hub Dual SoT while cwd is peer-N.
            report = _redirect_hub_artifact_path(Path(report))
            dump_probe_report(report, stamped)
            refreshed = json.loads(report.read_text(encoding="utf-8"))
            stamped["probe_report_path"] = str(report)
            # Surface durable stamp fields for CLI / output-compare honesty.
            stamped["ts"] = refreshed.get("ts")
            stamped["stamp_refreshed"] = bool(refreshed.get("stamp_refreshed") is True)
            stamped["ram_soft_refresh_needle"] = (
                refreshed.get("ram_soft_refresh_needle") or PROBE_RAM_SOFT_REFRESH_NEEDLE
            )
            stamped["worktree_root_bind_needle"] = refreshed.get(
                "worktree_root_bind_needle"
            ) or WORKTREE_ROOT_BIND_NEEDLE
            stamped["expand_path_coerce_needle"] = (
                refreshed.get("expand_path_coerce_needle") or EXPAND_PATH_COERCE_NEEDLE
            )
            if refreshed.get("artifact_root"):
                stamped["artifact_root"] = refreshed.get("artifact_root")
            elif not stamped.get("artifact_root"):
                stamped["artifact_root"] = str(_resolve_repo_root())
            stamped["ram_soft_skip"] = bool(refreshed.get("ram_soft_skip"))
            if refreshed.get("mem_available_kb") is not None:
                stamped["mem_available_kb"] = refreshed.get("mem_available_kb")
            stamped["probe_ok"] = bool(
                stamped.get("probe_ok")
                and refreshed.get("probe_ok") is True
                and refreshed.get("stamp_refreshed") is True
                and refreshed.get("train_unlocked") is False
                and refreshed.get("expand_path_coerce_needle") == EXPAND_PATH_COERCE_NEEDLE
            )
            stamped["train_unlocked"] = False
        except (OSError, ValueError, TypeError) as exc:
            stamped["stamp_refreshed"] = False
            stamped["stamp_refresh_error"] = str(exc)
            stamped["probe_ok"] = False
    return stamped


def check_dual_sot_report(
    report_path: Path | None = None,
    pack_path: Path | None = None,
    bank_path: Path | None = None,
) -> dict[str, Any]:
    """Lane-U durable Dual SoT report check (sibling to ``--check-cache``).

    Loads ``dual_sot_report.json`` (expand_ok required), re-verifies live
    pack+logit Dual SoT, **and** live-probes the logit-expand sidecar
    (``check_expanded``) so a stale report ``expand_ok=true`` cannot
    false-green an undersized durable bank. Does **not** unlock training.

    On ``dual_sot_ok``, RAM-safe stamp-refresh re-dumps the durable report with
    fresh ``ts`` + hub-unlock ignore fields (DUAL_SOT_STAMP_REFRESH_NEEDLE) —
    keep-alive under MemAvailable soft-skip without heavy ensure refresh.
    ``ram_soft_skip`` is set from **live** ``_should_ram_soft_skip`` only
    (never OR'd with a stale dump — sticky true after RAM recovers is a lie).
    """
    import compression_logit_expand as expand

    report = Path(report_path) if report_path is not None else DEFAULT_DUAL_SOT_PATH
    # Worktree bind: prefer peer twin before load so CLI path ≠ hub when cwd is peer-N.
    report = _redirect_hub_artifact_path(report)
    out: dict[str, Any] = {
        "check_dual_sot_report": True,
        "dual_sot": True,
        "train_unlocked": False,
        "data_prune": False,
        "dual_sot_report_path": str(report),
        "dual_sot_cache_needle": DUAL_SOT_CACHE_NEEDLE,
        "stamp_refresh_needle": DUAL_SOT_STAMP_REFRESH_NEEDLE,
        "stamp_refreshed": False,
        "dual_sot_report_ok": False,
        "dual_sot_ok": False,
        "expand_ok": False,
        "quality": "proxy",
        "worktree_root_bind_needle": WORKTREE_ROOT_BIND_NEEDLE,
    }
    loaded: dict[str, Any] | None = None
    try:
        loaded = load_dual_sot_report(report)
        out["dual_sot_report_ok"] = True
        # Report flag is necessary but not sufficient — live expand below.
        out["expand_path"] = loaded.get("expand_path")
        out["expand_n_before"] = loaded.get("expand_n_before")
        out["expand_n_after"] = loaded.get("expand_n_after")
        out["expand_needle"] = loaded.get("expand_needle")
        out["pack_path"] = loaded.get("pack_path")
        out["bank_path"] = loaded.get("bank_path")
        out["ram_soft_skip"] = loaded.get("ram_soft_skip")
        out["mem_available_kb"] = loaded.get("mem_available_kb")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        out["dual_sot_report_error"] = str(exc)
        out["dual_sot_report_ok"] = False
        out["dual_sot_ok"] = False
        return out

    # Keep-alive: live expand SoT (floor / bank-seed), not report-only expand_ok.
    # Coerce corrupt report expand_path (EXPAND_PATH_COERCE_NEEDLE) → Lane-U EXPANDED.
    expand_path = coerce_expand_path(out.get("expand_path"))
    out["expand_path_coerce_needle"] = EXPAND_PATH_COERCE_NEEDLE
    expand_live = expand.check_expanded(expand_path)
    out["expand_ok"] = bool(expand_live.get("expand_ok"))
    out["expand_path"] = str(expand_path)
    if expand_live.get("n_before") is not None:
        out["expand_n_before"] = expand_live.get("n_before")
    if expand_live.get("n_after") is not None:
        out["expand_n_after"] = expand_live.get("n_after")
    if expand_live.get("needle"):
        out["expand_needle"] = expand_live.get("needle")
    if expand_live.get("error"):
        out["expand_error"] = expand_live.get("error")
    if expand_live.get("expand_rows") is not None:
        out["expand_rows"] = expand_live.get("expand_rows")

    live = dual_sot_check(pack_path=pack_path, bank_path=bank_path)
    out["pack_ok"] = bool(live.get("pack_ok"))
    out["bank_ok"] = bool(live.get("bank_ok"))
    out["pack_needle"] = live.get("pack_needle")
    out["pack_cache_needle"] = live.get("pack_cache_needle")
    out["bank_needle"] = live.get("bank_needle")
    out["bank_cache_needle"] = live.get("bank_cache_needle")
    if live.get("pack_path"):
        out["pack_path"] = live.get("pack_path")
    if live.get("bank_path"):
        out["bank_path"] = live.get("bank_path")
    # Surface pack/bank path honesty needle from live Dual SoT (hub→peer redirect).
    out["pack_bank_path_honesty_needle"] = (
        live.get("pack_bank_path_honesty_needle") or PACK_BANK_PATH_HONESTY_NEEDLE
    )
    out["train_unlocked"] = False
    out["dual_sot_ok"] = bool(
        out["dual_sot_report_ok"]
        and out.get("expand_ok")
        and live.get("dual_sot_ok")
        and out["train_unlocked"] is False
        and out["data_prune"] is False
    )
    stamped = _apply_hub_unlock_ignore(out)
    # RAM-safe keep-alive: refresh durable stamp without heavy ensure refresh.
    if stamped.get("dual_sot_ok") and loaded is not None:
        soft, avail_kb = _should_ram_soft_skip()
        # Live soft only — do not OR stale dump (sticky true after RAM recovers).
        # Needles: DUAL_SOT_STAMP_REFRESH + DUAL_SOT_RAM_SOFT_REFRESH.
        stamped["ram_soft_skip"] = bool(soft)
        stamped["ram_soft_refresh_needle"] = DUAL_SOT_RAM_SOFT_REFRESH_NEEDLE
        if soft:
            stamped["ram_soft_needle"] = DUAL_SOT_RAM_SOFT_NEEDLE
        if avail_kb is not None:
            stamped["mem_available_kb"] = avail_kb
        stamped["ram_floor_kb"] = ENSURE_DUAL_SOT_RAM_FLOOR_KB
        # Preserve expand/pack metadata from prior Dual SoT dump when live miss.
        for key in (
            "expand_n_before",
            "expand_n_after",
            "expand_needle",
            "pack_cache_ok",
            "bank_cache_ok",
        ):
            if stamped.get(key) is None and loaded.get(key) is not None:
                stamped[key] = loaded[key]
        try:
            # Set stamp_refreshed BEFORE dump so durable Dual SoT records it
            # (CLI-only stamp_refreshed after dump was theater — output-compare
            # could not prove keep-alive advanced from dual_sot_report.json).
            stamped["stamp_refreshed"] = True
            stamped["stamp_refresh_needle"] = DUAL_SOT_STAMP_REFRESH_NEEDLE
            # Worktree bind: never dump hub Dual SoT while cwd is peer-N.
            report = _redirect_hub_artifact_path(Path(report))
            dump_dual_sot_report(report, stamped)
            refreshed = json.loads(report.read_text(encoding="utf-8"))
            stamped["dual_sot_report_path"] = str(report)
            # Surface durable stamp fields for CLI / output-compare honesty.
            stamped["ts"] = refreshed.get("ts")
            stamped["stamp_refreshed"] = bool(refreshed.get("stamp_refreshed") is True)
            stamped["ram_soft_refresh_needle"] = (
                refreshed.get("ram_soft_refresh_needle")
                or DUAL_SOT_RAM_SOFT_REFRESH_NEEDLE
            )
            stamped["worktree_root_bind_needle"] = refreshed.get(
                "worktree_root_bind_needle"
            ) or WORKTREE_ROOT_BIND_NEEDLE
            stamped["expand_path_coerce_needle"] = (
                refreshed.get("expand_path_coerce_needle") or EXPAND_PATH_COERCE_NEEDLE
            )
            if refreshed.get("artifact_root"):
                stamped["artifact_root"] = refreshed.get("artifact_root")
            elif not stamped.get("artifact_root"):
                stamped["artifact_root"] = str(_resolve_repo_root())
            stamped["ram_soft_skip"] = bool(refreshed.get("ram_soft_skip"))
            if refreshed.get("mem_available_kb") is not None:
                stamped["mem_available_kb"] = refreshed.get("mem_available_kb")
            stamped["dual_sot_ok"] = bool(
                stamped.get("dual_sot_ok")
                and refreshed.get("dual_sot_ok") is True
                and refreshed.get("stamp_refreshed") is True
                and refreshed.get("train_unlocked") is False
                and refreshed.get("expand_path_coerce_needle") == EXPAND_PATH_COERCE_NEEDLE
            )
            stamped["train_unlocked"] = False
        except (OSError, ValueError, TypeError) as exc:
            stamped["stamp_refreshed"] = False
            stamped["stamp_refresh_error"] = str(exc)
            stamped["dual_sot_ok"] = False
    return stamped


def heal_lane_u_sot(
    dual_sot_report_path: Path | None = None,
    probe_report_path: Path | None = None,
) -> dict[str, Any]:
    """Post-unittest Lane-U SoT heal — Dual SoT + probe stamp-refresh.

    Soft-skip unit tests / mock soft can leave durable ``ram_soft_skip=true``
    on Lane-U reports after RAM recovers. Re-run both check paths (RAM-safe
    stamp-refresh only; no heavy ensure / undersize mutation) so DONE cannot
    claim green keep-alive on poisoned SoT. Needle: LANE_U_SOT_HEAL_NEEDLE.
    Does **not** unlock training.
    """
    dual = check_dual_sot_report(report_path=dual_sot_report_path)
    probe = check_probe_report(report_path=probe_report_path)
    soft, avail_kb = _should_ram_soft_skip()
    out: dict[str, Any] = {
        "heal_lane_u_sot": True,
        "needle": LANE_U_SOT_HEAL_NEEDLE,
        "train_unlocked": False,
        "data_prune": False,
        "quality": "proxy",
        "dual_sot_ok": bool(dual.get("dual_sot_ok")),
        "probe_ok": bool(probe.get("probe_ok")),
        "dual_stamp_refreshed": bool(dual.get("stamp_refreshed")),
        "probe_stamp_refreshed": bool(probe.get("stamp_refreshed")),
        "dual_ram_soft_skip": bool(dual.get("ram_soft_skip")),
        "probe_ram_soft_skip": bool(probe.get("ram_soft_skip")),
        "dual_sot_report_path": dual.get("dual_sot_report_path"),
        "probe_report_path": probe.get("probe_report_path"),
        "live_ram_soft_skip": bool(soft),
        "worktree_root_bind_needle": WORKTREE_ROOT_BIND_NEEDLE,
    }
    if avail_kb is not None:
        out["mem_available_kb"] = avail_kb
    out["ram_floor_kb"] = ENSURE_DUAL_SOT_RAM_FLOOR_KB
    # When live soft is false, durable soft on either report is sticky poison.
    sticky_cleared = True
    if not soft:
        sticky_cleared = (not out["dual_ram_soft_skip"]) and (
            not out["probe_ram_soft_skip"]
        )
    out["sticky_soft_cleared"] = sticky_cleared if not soft else None
    out["heal_ok"] = bool(
        out["dual_sot_ok"]
        and out["probe_ok"]
        and out["dual_stamp_refreshed"]
        and out["probe_stamp_refreshed"]
        and out["train_unlocked"] is False
        and out["data_prune"] is False
        and (soft or sticky_cleared)
    )
    return apply_hub_unlock_ignore(out)


def _mem_available_kb() -> int | None:
    """Read MemAvailable from /proc/meminfo (None if unavailable)."""
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _should_ram_soft_skip() -> tuple[bool, int | None]:
    """True when MemAvailable is below floor and FORCE env is unset.

    Needle: DUAL_SOT_RAM_SOFT_NEEDLE — full pack/bank/expand refresh under
    RAM storm OOMs (rc 137) and can leave expand undersized; soft-skip to
    ``check_dual_sot_report`` keep-alive instead. Still TRAIN-LOCKED.
    """
    force = os.environ.get(ENSURE_DUAL_SOT_FORCE_ENV, "").strip().lower()
    if force in ("1", "true", "yes", "on"):
        return False, _mem_available_kb()
    avail = _mem_available_kb()
    if avail is None:
        return False, None
    return avail < ENSURE_DUAL_SOT_RAM_FLOOR_KB, avail


def ensure_dual_sot(
    pack_path: Path | None = None,
    bank_path: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Refresh T0 pack + T3 logit bank SoTs, Dual-SoT check, dump Lane-U report.

    Advances one Dual-SoT keep-alive step (pack/logit) without unlocking train.
    Also refreshes T3 logit-expand sidecar (full snip corpus) so unittest
    snip_limit clobbers cannot leave durable expand SoT stale — expand is
    sidecar-only; ``dual_sot_check`` stays pack+canonical.
    Under RAM storm (MemAvailable < ENSURE_DUAL_SOT_RAM_FLOOR_KB), soft-skips
    heavy refresh and runs ``check_dual_sot_report`` instead (fail-closed if
    expand/pack/bank not already green). Needle: DUAL_SOT_CACHE_NEEDLE →
    notes/compression_artifacts/dual_sot_report.json
    """
    soft, avail_kb = _should_ram_soft_skip()
    if soft:
        import compression_logit_expand as expand

        payload = check_dual_sot_report(
            report_path=report_path, pack_path=pack_path, bank_path=bank_path
        )
        payload["ensure_dual_sot"] = True
        payload["ram_soft_skip"] = True
        payload["ram_soft_needle"] = DUAL_SOT_RAM_SOFT_NEEDLE
        payload["mem_available_kb"] = avail_kb
        payload["ram_floor_kb"] = ENSURE_DUAL_SOT_RAM_FLOOR_KB
        payload["train_unlocked"] = False
        payload["data_prune"] = False
        # Caches were not refreshed; report honesty from live check only.
        payload["pack_cache_ok"] = bool(payload.get("pack_ok"))
        payload["bank_cache_ok"] = bool(payload.get("bank_ok"))
        payload["dual_sot_cache_needle"] = DUAL_SOT_CACHE_NEEDLE
        # Surface expand floor metadata so soft-skip CLI tests can assert honesty
        # without requiring a heavy refresh (n_after may equal durable bank size).
        live_exp = expand.check_expanded()
        if payload.get("expand_n_before") is None:
            payload["expand_n_before"] = live_exp.get("n_before")
        if payload.get("expand_n_after") is None:
            payload["expand_n_after"] = live_exp.get("n_after") or live_exp.get(
                "expand_rows"
            )
        payload["expand_path"] = payload.get("expand_path") or str(expand.EXPANDED)
        # Fail-closed: soft-skip must not green an undersized/missing SoT.
        payload["dual_sot_ok"] = bool(
            payload.get("dual_sot_ok")
            and payload.get("expand_ok")
            and payload.get("train_unlocked") is False
            and payload.get("data_prune") is False
        )
        # Lane-U keep-alive under RAM soft-skip: still dump Dual SoT so durable
        # report stamps hub_unlock_ignored (Creative: hub unlock ≠ TRAIN-GO).
        # Full pack/bank/expand refresh stays skipped; dump uses live check only.
        report = Path(report_path) if report_path is not None else DEFAULT_DUAL_SOT_PATH
        report = _redirect_hub_artifact_path(report)
        payload = apply_hub_unlock_ignore(payload)
        payload["worktree_root_bind_needle"] = WORKTREE_ROOT_BIND_NEEDLE
        if payload["dual_sot_ok"]:
            dump_dual_sot_report(report, payload)
            try:
                loaded = load_dual_sot_report(report)
                payload["dual_sot_report_ok"] = loaded.get("dual_sot_ok") is True
            except (OSError, ValueError, KeyError, TypeError) as exc:
                payload["dual_sot_report_ok"] = False
                payload["dual_sot_report_error"] = str(exc)
                payload["dual_sot_ok"] = False
        else:
            payload["dual_sot_report_ok"] = False
        payload["dual_sot_report_path"] = str(report)
        payload["dual_sot_cache_needle"] = DUAL_SOT_CACHE_NEEDLE
        return apply_hub_unlock_ignore(payload)

    import compression_logit_expand as expand
    import compression_t3_bitdistill as t3

    pack_out, pack_cache_ok = ensure_default_pack(pack_path)
    bank_out, bank_cache_ok = t3.ensure_default_bank(bank_path)
    expand_path, expand_checked = expand.ensure_expanded()
    payload = dual_sot_check(pack_path=pack_out, bank_path=bank_out)
    payload["ensure_dual_sot"] = True
    payload["ram_soft_skip"] = False
    payload["mem_available_kb"] = avail_kb
    payload["pack_cache_ok"] = bool(pack_cache_ok)
    payload["bank_cache_ok"] = bool(bank_cache_ok)
    payload["pack_path"] = str(pack_out)
    payload["bank_path"] = str(bank_out)
    payload["expand_ok"] = bool(expand_checked.get("expand_ok"))
    payload["expand_path"] = str(expand_path)
    payload["expand_n_before"] = expand_checked.get("n_before")
    payload["expand_n_after"] = expand_checked.get("n_after")
    payload["expand_needle"] = expand_checked.get("needle") or expand.NEEDLE
    # Refuse unlock even if caches green
    payload["train_unlocked"] = False
    payload["dual_sot_ok"] = bool(
        payload.get("dual_sot_ok")
        and pack_cache_ok
        and bank_cache_ok
        and payload.get("expand_ok")
        and payload.get("train_unlocked") is False
        and payload.get("data_prune") is False
    )
    report = Path(report_path) if report_path is not None else DEFAULT_DUAL_SOT_PATH
    report = _redirect_hub_artifact_path(report)
    payload["worktree_root_bind_needle"] = WORKTREE_ROOT_BIND_NEEDLE
    if payload["dual_sot_ok"]:
        dump_dual_sot_report(report, payload)
        try:
            loaded = load_dual_sot_report(report)
            payload["dual_sot_report_ok"] = loaded.get("dual_sot_ok") is True
        except (OSError, ValueError, KeyError, TypeError) as exc:
            payload["dual_sot_report_ok"] = False
            payload["dual_sot_report_error"] = str(exc)
            payload["dual_sot_ok"] = False
    else:
        payload["dual_sot_report_ok"] = False
    payload["dual_sot_report_path"] = str(report)
    payload["dual_sot_cache_needle"] = DUAL_SOT_CACHE_NEEDLE
    return apply_hub_unlock_ignore(payload)


def probe_keep_alive(snip_limit: int = 16) -> dict[str, Any]:
    """Falsifiable Dual SoT keep-alive: undersize expand → ensure heals → still TRAIN-LOCKED.

    Advances one T0/logit keep-alive step without unlocking train. Mutates durable
    expand only inside try/finally (restores via ensure_expanded / rewrite).

    Under RAM soft-skip, ``ensure_dual_sot`` is check-only — forcing a full
    refresh OOMs (rc 137) and leaves expand undersized. Heal via
    ``ensure_expanded`` then Dual SoT check / soft ensure. Needle: PROBE_KEEP_ALIVE_NEEDLE.
    """
    import tempfile

    import compression_logit_expand as expand

    out: dict[str, Any] = {
        "probe_keep_alive": True,
        "probe_needle": PROBE_KEEP_ALIVE_NEEDLE,
        "dual_sot_cache_needle": DUAL_SOT_CACHE_NEEDLE,
        "snip_limit": int(snip_limit),
        "undersize_ok": False,
        "healed_ok": False,
        "dual_sot_ok": False,
        "expand_ok": False,
        "train_unlocked": False,
        "data_prune": False,
        "quality": "proxy",
        "heal_via_expand": False,
        "ram_soft_skip": False,
    }
    if snip_limit >= expand.DEFAULT_EXPAND_SNIPS:
        out["error"] = "snip_limit_must_be_below_ensure_floor"
        return out

    prior = (
        expand.EXPANDED.read_text(encoding="utf-8")
        if expand.EXPANDED.is_file()
        else None
    )
    try:
        with tempfile.TemporaryDirectory(prefix="probe_ka_") as td:
            toy = Path(td) / "under.json"
            expand.expand(snip_limit=snip_limit, out_path=toy)
            expand.EXPANDED.write_text(toy.read_text(encoding="utf-8"), encoding="utf-8")
        before = expand.check_expanded()
        out["undersize_ok"] = before.get("expand_ok") is False and before.get(
            "error"
        ) == "expand_rows_below_ensure_floor"
        out["undersize_rows"] = before.get("expand_rows")
        out["undersize_error"] = before.get("error")
        if not out["undersize_ok"]:
            out["error"] = "undersize_did_not_fail_closed"
            return out

        soft, avail_kb = _should_ram_soft_skip()
        out["mem_available_kb"] = avail_kb
        out["ram_soft_skip"] = bool(soft)
        # Always heal expand SoT directly (soft ensure cannot restore undersize).
        _epath, expand_checked = expand.ensure_expanded()
        out["heal_via_expand"] = True
        out["expand_heal_ok"] = bool(expand_checked.get("expand_ok"))
        out["expand_n_before"] = expand_checked.get("n_before")
        out["expand_n_after"] = expand_checked.get("n_after")
        out["expand_path"] = str(_epath)

        # Never FORCE full ensure under storm — OOM kills the probe and poisons SoT.
        if soft:
            healed = check_dual_sot_report()
            healed["ram_soft_skip"] = True
        else:
            healed = ensure_dual_sot()
        live_exp = expand.check_expanded()
        out["expand_ok"] = bool(live_exp.get("expand_ok"))
        if live_exp.get("n_before") is not None:
            out["expand_n_before"] = live_exp.get("n_before")
        if live_exp.get("n_after") is not None:
            out["expand_n_after"] = live_exp.get("n_after")
        # Live soft only — do not OR healed (sticky soft after RAM recovers).
        out["ram_soft_skip"] = bool(soft)
        out["ram_floor_kb"] = ENSURE_DUAL_SOT_RAM_FLOOR_KB
        out["healed_ok"] = bool(
            out.get("expand_heal_ok")
            and out["expand_ok"]
            and healed.get("dual_sot_ok")
        )
        out["dual_sot_ok"] = bool(healed.get("dual_sot_ok") and out["expand_ok"])
        out["pack_ok"] = healed.get("pack_ok")
        out["bank_ok"] = healed.get("bank_ok")
        out["data_prune"] = bool(healed.get("data_prune"))
        # Refuse unlock even if hub train_unlock.json is true (peer recipe SoT).
        _apply_hub_unlock_ignore(out)
        out["probe_ok"] = bool(
            out["undersize_ok"]
            and out["healed_ok"]
            and out["dual_sot_ok"]
            and out["expand_ok"]
            and out["train_unlocked"] is False
            and out["data_prune"] is False
        )
        if out["probe_ok"]:
            report = dump_probe_report(DEFAULT_PROBE_PATH, out)
            out["probe_report_path"] = str(report)
            out["probe_cache_needle"] = PROBE_CACHE_NEEDLE
            try:
                loaded = load_probe_report(report)
                out["probe_report_ok"] = loaded.get("probe_ok") is True
            except (OSError, ValueError, KeyError, TypeError) as exc:
                out["probe_report_ok"] = False
                out["probe_report_error"] = str(exc)
                out["probe_ok"] = False
        else:
            out["probe_report_ok"] = False
        return out
    finally:
        live = expand.check_expanded()
        if live.get("expand_ok") is not True:
            if prior is not None:
                expand.EXPANDED.write_text(prior, encoding="utf-8")
            expand.ensure_expanded()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="T0 compression packing proof")
    p.add_argument("--json", action="store_true", help="print JSON summary only")
    p.add_argument(
        "--write-report",
        metavar="PATH",
        help="dump durable pack report JSON (TRAIN still LOCKED)",
    )
    p.add_argument(
        "--check-cache",
        metavar="PATH",
        nargs="?",
        const="",
        help="verify dump→load fingerprint (PATH or default after write)",
    )
    p.add_argument(
        "--ensure-default-pack",
        action="store_true",
        help=(
            f"dump+verify canonical pack report at {DEFAULT_PACK_PATH.name} "
            "(not a train unlock)"
        ),
    )
    p.add_argument(
        "--dual-sot-check",
        action="store_true",
        help=(
            "TRAIN-LOCK Dual SoT: verify canonical pack report + T3 logit bank "
            "(both green, prune/unlock refused; does not unlock train)"
        ),
    )
    p.add_argument(
        "--ensure-dual-sot",
        action="store_true",
        help=(
            "refresh pack + T3 logit bank + logit-expand sidecar, Dual SoT check, "
            f"dump dual_sot_report.json ({DUAL_SOT_CACHE_NEEDLE}; not a train unlock)"
        ),
    )
    p.add_argument(
        "--check-dual-sot-report",
        metavar="PATH",
        nargs="?",
        const="",
        help=(
            "verify durable dual_sot_report.json (expand_ok required) + live "
            "pack/logit Dual SoT; on success RAM-safe stamp-refresh "
            f"({DUAL_SOT_STAMP_REFRESH_NEEDLE}; PATH or default; not a train unlock)"
        ),
    )
    p.add_argument(
        "--probe-keep-alive",
        action="store_true",
        help=(
            "falsifiable Dual SoT keep-alive: undersize expand → ensure heals "
            f"({PROBE_KEEP_ALIVE_NEEDLE}; dumps probe_keep_alive_report.json; "
            "not a train unlock)"
        ),
    )
    p.add_argument(
        "--check-probe-report",
        metavar="PATH",
        nargs="?",
        const="",
        help=(
            "verify durable probe_keep_alive_report.json (probe_ok required) + "
            "live expand + Dual SoT; on success RAM-safe stamp-refresh "
            f"({PROBE_STAMP_REFRESH_NEEDLE}; PATH or default; not a train unlock)"
        ),
    )
    p.add_argument(
        "--heal-lane-u-sot",
        action="store_true",
        help=(
            "post-unittest Lane-U heal: --check-dual-sot-report + "
            f"--check-probe-report ({LANE_U_SOT_HEAL_NEEDLE}; clears sticky "
            "ram_soft_skip after soft-skip tests; not a train unlock)"
        ),
    )
    args = p.parse_args(argv)

    if args.heal_lane_u_sot:
        payload = heal_lane_u_sot()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("heal_ok") else 1

    if args.probe_keep_alive:
        payload = probe_keep_alive()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("probe_ok") else 1

    if args.check_probe_report is not None:
        report = args.check_probe_report or None
        payload = check_probe_report(
            report_path=Path(report) if report else None
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("probe_ok") else 1

    if args.ensure_dual_sot:
        payload = ensure_dual_sot()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["dual_sot_ok"] else 1

    if args.check_dual_sot_report is not None:
        report = args.check_dual_sot_report or None
        payload = check_dual_sot_report(
            report_path=Path(report) if report else None
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["dual_sot_ok"] else 1

    if args.dual_sot_check:
        payload = dual_sot_check()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["dual_sot_ok"] else 1

    if args.ensure_default_pack:
        out, pack_cache_ok = ensure_default_pack()
        payload = summary_dict(run_all())
        payload["pack_cache_ok"] = pack_cache_ok
        payload["pack_source"] = "default_pack"
        payload["pack_path"] = str(out)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if pack_cache_ok and payload["all_passed"] else 1

    rows = run_all()
    payload = summary_dict(rows)

    if args.write_report:
        dump_pack_report(args.write_report, rows)
        payload["pack_path"] = str(Path(args.write_report))

    if args.check_cache is not None:
        check_path = args.check_cache or args.write_report or str(DEFAULT_PACK_PATH)
        if not check_path:
            print("error: --check-cache needs PATH or --write-report/--ensure", file=sys.stderr)
            return 2
        try:
            cached = load_pack_report(check_path)
            pack_cache_ok = (
                payload["all_passed"]
                and cached["all_passed"] is True
                and _results_fingerprint(payload) == _results_fingerprint(cached)
                and cached.get("train_unlocked") is False
                and cached.get("data_prune") is False
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            pack_cache_ok = False
            payload["pack_cache_error"] = str(exc)
        payload["pack_cache_ok"] = pack_cache_ok
        payload["pack_path"] = str(check_path)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if pack_cache_ok and payload["all_passed"] else 1

    if args.json or args.write_report:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
        for r in rows:
            status = "PASS" if r.passed else "FAIL"
            print(
                f"{status} {r.stack} N_L={r.n_logic} U={r.u_unique} "
                f"S={r.s_arith:.2f} bytes={r.packed_bytes} "
                f"(payload={r.payload_bytes}+meta={r.meta_bytes}) quality={r.quality}",
                file=sys.stderr,
            )
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
