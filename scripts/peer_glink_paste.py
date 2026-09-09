#!/usr/bin/env python3
"""Lean GLink paste — hub-compatible compact DONE/DIFF/BLOCK without peer_agent_comms.

# OVERSEER_LEAN_GLINK_PASTE_2026_09_04 — lean dig4 paste cuts English DONE wire
# without hub bus (peer-2 stand-in; hub also registers ./scripts/peer glink-paste).

peer-2 has no bus/vault kit. Niches were pasting English metric/recommend blobs into
notes (KPI_DIGEST / RELEASE_HEALTH). This module emits orchestrator-paste lines with
``ph`` (blake2b dig4) + ``eva`` / ``rh`` — same wire shape as hub ``compact_*_payload``.

Usage:
  python3 scripts/peer_glink_paste.py done --role communications_engineer \\
    --cycle 2026-09-04T20:30 --path scripts/peer_glink_paste.py --eva match --out ok
  python3 scripts/peer_glink_paste.py done --demo   # fat→compact byte report
  ./scripts/peer glink-paste done --demo
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from typing import Any

PATH_HASH_HEX_LEN = 8  # blake2b digest_size=4 → 8 hex (hub PROTOCOL dig4)
_CODE_KEY_MAX = 32
_PAYLOAD_WIRE_MAX = 320
_REASON_KEEP_MAX = 32
_DONE_DROP = frozenset(
    {"recommendation", "metric", "needle", "expected_vs_actual", "detail", "summary", "note"}
)
_ENGLISH_STOP_RE = re.compile(
    r"\b(the|should|please|draft|numbered|implementation|elegant)\b",
    re.I,
)


def path_hash(path: str) -> str:
    return hashlib.blake2b(
        str(path).encode("utf-8"), digest_size=PATH_HASH_HEX_LEN // 2
    ).hexdigest()


def reason_hash(text: str) -> str:
    return hashlib.blake2b(
        str(text).encode("utf-8"), digest_size=PATH_HASH_HEX_LEN // 2
    ).hexdigest()


def _normalize_eva(val: Any) -> str:
    s = str(val or "").strip().lower()
    if s.startswith("match") or s == "ok":
        return "match"
    if "discrep" in s or s.startswith("fail") or s.startswith("mismatch"):
        return "disc"
    return re.sub(r"[^a-z0-9_|+-]", "", s.replace(" ", "_"))[:16] or "unk"


def _is_english_heavy(text: str) -> bool:
    return bool(_ENGLISH_STOP_RE.search(text)) or text.count(" ") >= 3


def compact_done_payload(
    *,
    cycle: str | None = None,
    paths: list[str] | None = None,
    bref: str | list[str] | None = None,
    eva: str | None = None,
    expected_vs_actual: str | None = None,
    out: str | None = None,
    ref: str | None = None,
    keep_paths: bool = False,
) -> dict[str, Any]:
    """Build DONE ``p`` preferring ``ph`` + ``eva`` (hub-compatible)."""
    payload: dict[str, Any] = {}
    if cycle is not None:
        payload["cycle"] = str(cycle)[:32]
    if paths:
        clean = [str(p) for p in paths]
        payload["ph"] = [path_hash(p) for p in clean]
        if keep_paths:
            payload["paths"] = clean
    if bref is not None:
        payload["bref"] = bref
    raw_eva = eva if eva is not None else expected_vs_actual
    if raw_eva is not None:
        payload["eva"] = _normalize_eva(raw_eva)
    if out is not None:
        payload["out"] = str(out).strip()[:_CODE_KEY_MAX]
    if ref is not None:
        payload["ref"] = str(ref).strip()[:64]
    for drop in _DONE_DROP:
        payload.pop(drop, None)
    return payload


def compact_diff_payload(
    *,
    cycle: str | None = None,
    paths: list[str] | None = None,
    schema: str | None = None,
    bref: str | list[str] | None = None,
    keep_paths: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if cycle is not None:
        payload["cycle"] = str(cycle)[:32]
    if schema is not None:
        payload["schema"] = str(schema).strip()[:_CODE_KEY_MAX]
    if paths:
        clean = [str(p) for p in paths]
        payload["ph"] = [path_hash(p) for p in clean]
        if keep_paths:
            payload["paths"] = clean
    if bref is not None:
        payload["bref"] = bref
    return payload


def compact_block_payload(
    *,
    reason: str | None = None,
    wait: str | None = None,
    paths: list[str] | None = None,
    bref: str | list[str] | None = None,
    keep_reason: bool = False,
    keep_paths: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if isinstance(reason, str) and reason.strip():
        payload["rh"] = reason_hash(reason)
        if keep_reason and (
            len(reason) <= _REASON_KEEP_MAX
            and reason.count(" ") <= 2
            and not _is_english_heavy(reason)
        ):
            payload["reason"] = reason.strip()[:_CODE_KEY_MAX]
    if wait is not None:
        payload["wait"] = str(wait).strip()[:_CODE_KEY_MAX]
    if paths:
        clean = [str(p) for p in paths]
        payload["ph"] = [path_hash(p) for p in clean]
        if keep_paths:
            payload["paths"] = clean
    if bref is not None:
        payload["bref"] = bref
    return payload


def wire_bytes(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, separators=(",", ":")))


def format_paste(msg_type: str, role: str, payload: dict[str, Any]) -> str:
    return f"{msg_type} {role}: {json.dumps(payload, separators=(',', ':'))}"


def demo_done_shrink() -> tuple[dict[str, Any], dict[str, Any], int, int]:
    """KPI_DIGEST-style fat DONE → compact; returns fat, compact, fat_n, compact_n."""
    fat = {
        "cycle": "2026-09-04T17:16",
        "paths": ["notes/KPI_DIGEST.md"],
        "expected_vs_actual": "match — Digest numbers = LiveState",
        "metric": "success_metrics_ok=False git_clean=False paths=18 tests_ok=True",
        "recommendation": "adapt_specialist heal fingerprint; flag creative-before-Active",
        "detail": "long english narrative for operators reading the digest",
    }
    compact = compact_done_payload(
        cycle=str(fat["cycle"]),
        paths=list(fat["paths"]),  # type: ignore[arg-type]
        expected_vs_actual=str(fat["expected_vs_actual"]),
        out="ok",
    )
    return fat, compact, wire_bytes(fat), wire_bytes(compact)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lean GLink paste (hub-compatible compact)")
    parser.add_argument(
        "msg",
        choices=("done", "diff", "block", "DONE", "DIFF", "BLOCK"),
        help="Message type",
    )
    parser.add_argument("--role", default="communications_engineer")
    parser.add_argument("--cycle", default="", help="ISO cycle id (default: now)")
    parser.add_argument("--path", action="append", default=[], dest="paths")
    parser.add_argument("--eva", default="", help="match|disc|code")
    parser.add_argument("--expected-vs-actual", default="", dest="eva_prose")
    parser.add_argument("--out", default="")
    parser.add_argument("--ref", default="")
    parser.add_argument("--schema", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--wait", default="")
    parser.add_argument("--bref", default="")
    parser.add_argument("--keep-paths", action="store_true")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Print fat→compact DONE shrink report (no paste line)",
    )
    parser.add_argument("--json", action="store_true", help="Payload JSON only")
    args = parser.parse_args(argv)

    msg = args.msg.upper()
    cycle = args.cycle or datetime.now().isoformat(timespec="minutes")

    if args.demo and msg == "DONE":
        fat, compact, fat_n, compact_n = demo_done_shrink()
        pct = round(100.0 * (1.0 - compact_n / max(fat_n, 1)), 1)
        report = {
            "fat_b": fat_n,
            "compact_b": compact_n,
            "saved_pct": pct,
            "wire_ok": compact_n <= _PAYLOAD_WIRE_MAX,
            "compact": compact,
            "drop": sorted(_DONE_DROP & set(fat)),
        }
        print(json.dumps(report, indent=2))
        return 0 if report["wire_ok"] and compact_n < fat_n else 1

    paths = list(args.paths) or None
    bref = args.bref or None
    if msg == "DONE":
        payload = compact_done_payload(
            cycle=cycle,
            paths=paths,
            bref=bref,
            eva=args.eva or None,
            expected_vs_actual=args.eva_prose or None,
            out=args.out or None,
            ref=args.ref or None,
            keep_paths=args.keep_paths,
        )
    elif msg == "DIFF":
        payload = compact_diff_payload(
            cycle=cycle,
            paths=paths,
            schema=args.schema or None,
            bref=bref,
            keep_paths=args.keep_paths,
        )
    else:
        payload = compact_block_payload(
            reason=args.reason or None,
            wait=args.wait or None,
            paths=paths,
            bref=bref,
            keep_paths=args.keep_paths,
        )

    n = wire_bytes(payload)
    if n > _PAYLOAD_WIRE_MAX:
        print(f"refuse:wire>{_PAYLOAD_WIRE_MAX} got={n}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, separators=(",", ":")))
    else:
        print(format_paste(msg, args.role, payload))
        print(f"# wire={n}B ≤{_PAYLOAD_WIRE_MAX}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
