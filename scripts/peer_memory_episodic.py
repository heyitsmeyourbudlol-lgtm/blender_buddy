#!/usr/bin/env python3
"""Episodic memory by cycle_id — thin append-only jsonl (stretch MVP).

Needle: OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07

Store/retrieve short episode records keyed by cycle_id. Additive only —
never deletes live SoT.

Usage:
  python3 scripts/peer_memory_episodic.py --append --cycle-id C123 --note "…" --path notes/WORK_QUEUE.md
  python3 scripts/peer_memory_episodic.py --get C123
  python3 scripts/peer_memory_episodic.py --tail 5
  ./scripts/peer memory-episodic --tail 5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import peer_memory_compress as pmc  # noqa: E402

NEEDLE = "OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07"
STORE_PATH = pmc.ARTIFACT_DIR / "episodic_by_cycle.jsonl"
NO_PAY = "NO PAY: free desktop/local/CLEAN only — never paid API/Stripe/credits"


def append_episode(
    *,
    cycle_id: str,
    note: str = "",
    paths: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cid = (cycle_id or "").strip()
    if not cid:
        raise ValueError("cycle_id required")
    pmc.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    row: dict[str, Any] = {
        "cycle_id": cid,
        "ts": time.time(),
        "note": (note or "")[:500],
        "paths": [p for p in (paths or []) if p][:24],
        "needle": NEEDLE,
    }
    if extra:
        # Shallow merge — never overwrite cycle_id/ts/needle with secrets dumps
        for k, v in extra.items():
            if k in {"cycle_id", "ts", "needle"}:
                continue
            if k.lower() in {"token", "api_key", "secret", "password"}:
                continue
            row[k] = v
    with STORE_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    return row


def get_by_cycle(cycle_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    cid = (cycle_id or "").strip()
    if not cid or not STORE_PATH.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        lines = STORE_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("cycle_id") or "") == cid:
            out.append(row)
            if len(out) >= limit:
                break
    out.reverse()
    return out


def tail(n: int = 10) -> list[dict[str, Any]]:
    if not STORE_PATH.is_file():
        return []
    try:
        lines = STORE_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-max(1, n) :]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Episodic memory by cycle_id")
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--cycle-id", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--path", action="append", default=[], dest="paths")
    ap.add_argument("--get", metavar="CYCLE_ID", help="Fetch episodes for cycle_id")
    ap.add_argument("--tail", type=int, default=0, help="Show last N episodes")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.append:
        try:
            row = append_episode(
                cycle_id=args.cycle_id,
                note=args.note,
                paths=list(args.paths or []),
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(row, indent=2))
        else:
            print(f"appended cycle_id={row['cycle_id']} → {STORE_PATH.relative_to(ROOT)}")
            print(NO_PAY)
        return 0

    if args.get:
        rows = get_by_cycle(args.get)
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            if not rows:
                print(f"no episodes for cycle_id={args.get}")
            for r in rows:
                print(f"{r.get('cycle_id')} ts={r.get('ts')} note={r.get('note')!r} paths={r.get('paths')}")
        return 0

    n = args.tail or 10
    rows = tail(n)
    if args.json:
        print(json.dumps({"store": str(STORE_PATH), "rows": rows}, indent=2))
    else:
        print(f"## Episodic store ({STORE_PATH.relative_to(ROOT) if STORE_PATH.is_relative_to(ROOT) else STORE_PATH})")
        print(f"- {NO_PAY}")
        if not rows:
            print("- (empty)")
        for r in rows:
            print(f"- {r.get('cycle_id')}: {r.get('note')!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
