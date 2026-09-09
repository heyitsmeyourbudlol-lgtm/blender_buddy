#!/usr/bin/env python3
"""Factory A→Z status — next open phase from FACTORY_A_TO_Z_TASKS.md.

Usage:
  python3 scripts/peer_factory_a_to_z.py
  python3 scripts/peer_factory_a_to_z.py --next
  ./scripts/peer a-to-z
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "notes" / "FACTORY_A_TO_Z_TASKS.md"
PROOF = ROOT / "notes" / "FACTORY_A_TO_Z_PROOF.md"
PLAN = ROOT / "notes" / "FACTORY_A_TO_Z_PLAN.md"
NEEDLE = "OVERSEER_NO_JUMP_UNTIL_A_TO_Z_2026_09_07"

_OPEN_RE = re.compile(r"^- \[ \] \*\*(\[[^\]]+\].*?)\*\*")


def open_items(path: Path = TASKS) -> list[str]:
    if not path.is_file():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _OPEN_RE.match(line.strip())
        if m:
            out.append(m.group(1).strip())
    return out


def proof_status(path: Path = PROOF) -> str:
    if not path.is_file():
        return "missing"
    text = path.read_text(encoding="utf-8")
    m = re.search(r"\|\s*Status\s*\|\s*\*\*([^*]+)\*\*", text)
    return m.group(1).strip() if m else "unknown"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Factory A→Z status")
    ap.add_argument("--next", action="store_true", help="Print only next open item")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    items = open_items()
    status = proof_status()
    nxt = items[0] if items else None

    if args.json:
        print(
            json.dumps(
                {
                    "needle": NEEDLE,
                    "proof_status": status,
                    "open_count": len(items),
                    "next": nxt,
                    "plan": str(PLAN),
                    "tasks": str(TASKS),
                },
                indent=2,
            )
        )
        return 0

    if args.next:
        if nxt:
            print(nxt)
            return 0
        print("(no open a-to-z items — check green lock)")
        return 0

    print(f"Factory A→Z — {NEEDLE}")
    print(f"  proof_status: {status}")
    print(f"  open: {len(items)}")
    print(f"  plan: {PLAN.relative_to(ROOT)}")
    print(f"  tasks: {TASKS.relative_to(ROOT)}")
    print(f"  role: kit_a_to_z · wake: ./scripts/peer kit-run --repo CPT --dry-run")
    print()
    if nxt:
        print(f"NEXT:\n  {nxt}")
    else:
        print("NEXT: (none open)")
    if items[1:]:
        print("\nThen:")
        for it in items[1:6]:
            print(f"  - {it}")
        if len(items) > 6:
            print(f"  … +{len(items) - 6} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
