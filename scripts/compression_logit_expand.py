#!/usr/bin/env python3
"""Expand T3 teacher logit bank from peer/factory text (no data prune).

Needle: OVERSEER_COMPRESSION_LOGIT_EXPAND_2026_09_07

Appends synthetic teacher logit rows derived from peer-loop / debrief snippets
into an extended bank beside the canonical T3 cache.

Lane-U sibling to T3 ``--ensure-default-bank`` / T0 ``--ensure-default-pack``.
``--check`` / ``--ensure`` are fail-closed (not a train unlock).

Usage::

    python3 scripts/compression_logit_expand.py
    python3 scripts/compression_logit_expand.py --ensure --json
    python3 scripts/compression_logit_expand.py --check --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "notes" / "compression_artifacts"
DEFAULT_BANK = ART / "t3_teacher_logit_bank.json"
EXPANDED = ART / "t3_teacher_logit_bank_expanded.json"
NEEDLE = "OVERSEER_COMPRESSION_LOGIT_EXPAND_2026_09_07"
# Lane-U ensure floor — unittest snip_limit=16 must not pass durable --check.
DEFAULT_EXPAND_SNIPS = 200
# Parent must be the durable T3 BitDistill / logit-cache SoT.
PARENT_NEEDLES = (
    "OVERSEER_COMPRESSION_T3_BITDISTILL_2026_09_05",
    "OVERSEER_COMPRESSION_T3_LOGIT_CACHE_2026_09_05",
)

_SOURCES = (
    ROOT / "notes" / "DEBRIEF_LOG.md",
    ROOT / "notes" / "AGENT_ERROR_PLAYBOOK.md",
    ROOT / "notes" / "niche_distill" / "sidequest_knowledge.json",
)


def _hash_vec(text: str, dim: int = 32) -> list[float]:
    h = hashlib.sha256(text.encode("utf-8", errors="ignore")).digest()
    out = []
    for i in range(dim):
        b = h[i % len(h)]
        out.append((b / 127.5) - 1.0)
    # L2 normalize-ish
    n = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / n for x in out]


def _snippets(*, limit: int = 200) -> list[str]:
    snips: list[str] = []
    for path in _SOURCES:
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if path.suffix == ".json":
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    for row in data:
                        if isinstance(row, dict):
                            snips.append(str(row.get("input") or row.get("output") or "")[:240])
            except json.JSONDecodeError:
                pass
            continue
        for line in raw.splitlines():
            line = line.strip()
            if len(line) > 40:
                snips.append(line[:240])
            if len(snips) >= limit:
                return snips
    return snips


def _parent_n_examples(base: dict[str, Any]) -> int:
    """Corpus size from T3 schema (n_examples / xs) or legacy rows/logits."""
    if "n_examples" in base:
        try:
            return int(base["n_examples"])
        except (TypeError, ValueError):
            pass
    xs = base.get("xs")
    if isinstance(xs, list):
        return len(xs)
    for key in ("rows", "logits"):
        block = base.get(key)
        if isinstance(block, list):
            return len(block)
    return 0


def _parent_dim(base: dict[str, Any], *, fallback: int = 32) -> int:
    """Logit width = teacher output dim (d_out), never input xs (d_in)."""
    if "d_out" in base:
        try:
            return int(base["d_out"])
        except (TypeError, ValueError):
            pass
    bank = base.get("bank")
    # T3 bank: layers × examples × d_out
    if (
        isinstance(bank, list)
        and bank
        and isinstance(bank[0], list)
        and bank[0]
        and isinstance(bank[0][0], list)
        and bank[0][0]
    ):
        return len(bank[0][0])
    logits = base.get("logits")
    if isinstance(logits, list) and logits and isinstance(logits[0], list) and logits[0]:
        return len(logits[0])
    # Legacy only — prefer not to use d_in / xs (inputs ≠ logits).
    if "d_in" in base:
        try:
            return int(base["d_in"])
        except (TypeError, ValueError):
            pass
    return fallback


def _mean_pool_bank_logits(bank: list[Any]) -> list[list[float]]:
    """Mean-pool T3 bank[layer][example] → one logit vec per example (no prune)."""
    if not isinstance(bank, list) or not bank:
        return []
    layers = [layer for layer in bank if isinstance(layer, list)]
    if not layers:
        return []
    n = len(layers[0])
    if n < 1 or any(len(layer) != n for layer in layers):
        return []
    out: list[list[float]] = []
    for i in range(n):
        vecs = [layer[i] for layer in layers if isinstance(layer[i], list)]
        if not vecs:
            return []
        dim = len(vecs[0])
        if dim < 1 or any(len(v) != dim for v in vecs):
            return []
        pooled = [sum(v[j] for v in vecs) / float(len(vecs)) for j in range(dim)]
        out.append(pooled)
    return out


def _seed_rows_from_parent(base: dict[str, Any]) -> list[dict[str, Any]]:
    """Mirror parent teacher logits so expand preserves corpus, no prune.

    Prefer T3 ``bank`` (layers×examples×d_out). Never treat ``xs`` (d_in inputs)
    as teacher_logits when a real bank exists — that fakes dim=d_in.
    """
    prior = base.get("rows")
    if isinstance(prior, list) and prior:
        return [r for r in prior if isinstance(r, dict)]
    bank = base.get("bank")
    if isinstance(bank, list) and bank:
        pooled = _mean_pool_bank_logits(bank)
        if pooled:
            return [
                {
                    "source": "parent_bank",
                    "text": f"parent_bank_{i}",
                    "teacher_logits": list(vec),
                }
                for i, vec in enumerate(pooled)
            ]
    logits = base.get("logits")
    if isinstance(logits, list) and logits:
        return [
            {
                "source": "parent_logits",
                "text": f"parent_logit_{i}",
                "teacher_logits": list(vec),
            }
            for i, vec in enumerate(logits)
            if isinstance(vec, list)
        ]
    # Last-resort legacy only (pre-bank caches). Prefer bank/logits above.
    xs = base.get("xs")
    if isinstance(xs, list) and xs:
        return [
            {
                "source": "parent_xs_legacy",
                "text": f"parent_x_{i}",
                "teacher_logits": list(x),
            }
            for i, x in enumerate(xs)
            if isinstance(x, list)
        ]
    return []


def expand(
    *,
    dim: int | None = None,
    snip_limit: int = DEFAULT_EXPAND_SNIPS,
    out_path: Path | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Build expanded bank. Default writes durable ``EXPANDED``.

    Pass ``out_path`` / ``path`` (e.g. tempfile) for probes/tests so a reduced
    ``snip_limit`` cannot shrink the Lane-U SoT on disk.
    """
    if out_path is not None and path is not None and Path(out_path) != Path(path):
        raise ValueError("out_path and path disagree")
    dest = out_path if out_path is not None else path
    base: dict[str, Any] = {}
    if DEFAULT_BANK.is_file():
        try:
            base = json.loads(DEFAULT_BANK.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            base = {}
    if base.get("data_prune") is True:
        raise ValueError("refusing expand from pruned parent logit bank")
    if base.get("train_unlocked") is True:
        raise ValueError("refusing expand from train-unlocked parent bank")

    # Canonical T3 bank uses teachers/xs/n_examples — not rows/logits.
    before = _parent_n_examples(base)
    use_dim = int(dim) if dim is not None else _parent_dim(base)
    rows = _seed_rows_from_parent(base)
    for s in _snippets(limit=snip_limit):
        rows.append(
            {
                "source": "peer_factory_expand",
                "text": s,
                "teacher_logits": _hash_vec(s, dim=use_dim),
            }
        )
    n_new = len([r for r in rows if r.get("source") == "peer_factory_expand"])
    parent = base.get("needle") or base.get("cache_needle")
    payload = {
        "needle": NEEDLE,
        "parent_needle": parent,
        "parent_cache_needle": base.get("cache_needle"),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_before": before,
        # Advance = parent corpus + new factory snippets (sidecar; canonical untouched)
        "n_after": (before + n_new) if before > 0 else len(rows),
        "n_rows": len(rows),
        "dim": use_dim,
        "d_in": base.get("d_in"),
        "d_out": base.get("d_out"),
        "layers": base.get("layers"),
        "snip_limit": int(snip_limit),
        "data_prune": False,
        "train_unlocked": False,  # expand ≠ TRAIN unlock
        "canonical_untouched": True,
        "quality": "proxy",
        "rows": rows,
        "local_only": True,
    }
    target = Path(dest) if dest is not None else EXPANDED
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    summary = {k: payload[k] for k in payload if k != "rows"}
    summary["path"] = str(target)
    return summary


def check_expanded(path: Path | None = None) -> dict[str, Any]:
    """Fail-closed verify durable expanded bank. Does **not** unlock train."""
    target = Path(path) if path is not None else EXPANDED
    out: dict[str, Any] = {
        "needle": NEEDLE,
        "path": str(target),
        "expand_ok": False,
        "train_unlocked": False,
        "data_prune": False,
    }
    if not target.is_file():
        out["error"] = "missing_expanded_bank"
        return out
    try:
        meta = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        out["error"] = str(exc)
        return out

    out["parent_needle"] = meta.get("parent_needle")
    out["n_before"] = meta.get("n_before")
    out["n_after"] = meta.get("n_after")
    out["dim"] = meta.get("dim")

    if meta.get("needle") != NEEDLE:
        out["error"] = "needle_mismatch"
        return out
    if meta.get("data_prune") is True:
        out["error"] = "data_prune_refused"
        out["data_prune"] = True
        return out
    if meta.get("train_unlocked") is True:
        out["error"] = "train_unlocked_refused"
        out["train_unlocked"] = True
        return out
    parent = meta.get("parent_needle")
    if parent not in PARENT_NEEDLES:
        out["error"] = "parent_needle_mismatch"
        return out
    rows = meta.get("rows")
    if not isinstance(rows, list) or len(rows) < 1:
        out["error"] = "empty_rows"
        return out
    n_after = meta.get("n_after")
    if not isinstance(n_after, int) or n_after < 1 or n_after != len(rows):
        out["error"] = "n_after_mismatch"
        return out
    # Must advance past parent corpus (n_after > n_before) with expand-sourced rows.
    n_before = meta.get("n_before")
    if not isinstance(n_before, int) or n_before < 0:
        out["error"] = "n_before_invalid"
        return out
    if n_after <= n_before:
        out["error"] = "no_growth"
        return out
    # When canonical T3 parent exists, n_before must match n_examples (schema-aware).
    parent_meta: dict[str, Any] = {}
    if DEFAULT_BANK.is_file():
        try:
            parent_meta = json.loads(DEFAULT_BANK.read_text(encoding="utf-8"))
            parent_n = _parent_n_examples(parent_meta)
            out["parent_n_examples"] = parent_n
            if parent_n > 0 and n_before != parent_n:
                out["error"] = "n_before_ne_parent_n_examples"
                return out
            parent_dim = _parent_dim(parent_meta)
            out["parent_d_out"] = parent_dim
            if parent_dim > 0 and isinstance(meta.get("dim"), int) and meta["dim"] != parent_dim:
                out["error"] = "dim_ne_parent_d_out"
                return out
        except (OSError, json.JSONDecodeError):
            parent_meta = {}
    expand_rows = [r for r in rows if isinstance(r, dict) and r.get("source") == "peer_factory_expand"]
    if len(expand_rows) < 1:
        out["error"] = "missing_expand_rows"
        return out
    dim = meta.get("dim")
    if not isinstance(dim, int) or dim < 1:
        out["error"] = "dim_invalid"
        return out
    sample = expand_rows[0].get("teacher_logits")
    if not isinstance(sample, list) or len(sample) != dim:
        out["error"] = "logit_dim_mismatch"
        return out
    # When parent has a real bank, refuse xs-as-logits theater seed.
    if isinstance(parent_meta.get("bank"), list) and parent_meta["bank"]:
        bank_seed = [
            r
            for r in rows
            if isinstance(r, dict) and r.get("source") == "parent_bank"
        ]
        if len(bank_seed) < 1:
            out["error"] = "missing_parent_bank_seed"
            return out
        if any(
            isinstance(r, dict) and str(r.get("source", "")).startswith("parent_xs")
            for r in rows
        ):
            out["error"] = "xs_as_logits_refused"
            return out
        out["parent_bank_rows"] = len(bank_seed)

    # Durable Lane-U SoT must meet ensure floor; toy probes may be smaller.
    out["expand_rows"] = len(expand_rows)
    if target.resolve() == EXPANDED.resolve():
        snip_meta = meta.get("snip_limit")
        if isinstance(snip_meta, int) and snip_meta < DEFAULT_EXPAND_SNIPS:
            out["error"] = "expand_rows_below_ensure_floor"
            out["snip_limit"] = snip_meta
            out["ensure_floor"] = DEFAULT_EXPAND_SNIPS
            out["expand_ok"] = False
            return out
        if len(expand_rows) < DEFAULT_EXPAND_SNIPS:
            out["error"] = "expand_rows_below_ensure_floor"
            out["ensure_floor"] = DEFAULT_EXPAND_SNIPS
            out["expand_ok"] = False
            return out

    out["expand_ok"] = True
    out["snip_limit"] = meta.get("snip_limit", DEFAULT_EXPAND_SNIPS)
    out["canonical_untouched"] = bool(meta.get("canonical_untouched", True))
    return out


def ensure_expanded(*, dim: int | None = None, path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    """Dump expanded bank then fail-closed check. TRAIN still LOCKED."""
    target = Path(path) if path is not None else EXPANDED
    summary = expand(dim=dim, out_path=target)
    checked = check_expanded(target)
    checked["ensure"] = True
    checked["n_before"] = summary.get("n_before")
    checked["n_after"] = summary.get("n_after")
    return target, checked


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dim",
        type=int,
        default=None,
        help="logit dim (default: parent d_out / bank width)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="print JSON summary only",
    )
    ap.add_argument(
        "--check",
        nargs="?",
        const="",
        metavar="PATH",
        help=(
            f"fail-closed verify expanded bank (PATH or {EXPANDED.name}); "
            "not a train unlock"
        ),
    )
    ap.add_argument(
        "--ensure",
        action="store_true",
        help=(
            f"dump+verify canonical expanded bank at {EXPANDED.name} "
            "(not a train unlock)"
        ),
    )
    args = ap.parse_args(argv)

    if args.ensure:
        _path, checked = ensure_expanded(dim=args.dim)
        payload = {
            **checked,
            "expand_path": str(_path),
            "expand_source": "ensure",
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if checked.get("expand_ok") else 1

    if args.check is not None:
        check_path = Path(args.check) if args.check else EXPANDED
        payload = check_expanded(check_path)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("expand_ok") else 1

    out = expand(dim=args.dim)
    print(json.dumps(out, indent=2, sort_keys=True) if args.json else json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
