#!/usr/bin/env python3
"""TOP10_NEXT list printer + mechanical rank refresh.

Usage:
  python3 scripts/peer_top10_next.py            # print ranked table
  python3 scripts/peer_top10_next.py --list
  python3 scripts/peer_top10_next.py --refresh  # open first, renumber, write-back
  python3 scripts/peer_top10_next.py --next     # print #1 open item only
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP10_PATH = ROOT / "notes" / "TOP10_NEXT.md"

_ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$"
)


@dataclass
class Top10Item:
    rank: int
    id: str
    title: str
    why: str
    acceptance: str
    status: str

    @property
    def open(self) -> bool:
        return self.status.strip().lower() in {"open", "todo", "wip", "in_progress"}


def _parse(text: str) -> tuple[list[str], list[Top10Item], list[str]]:
    lines = text.splitlines(keepends=True)
    items: list[Top10Item] = []
    head: list[str] = []
    tail: list[str] = []
    in_table = False
    for line in lines:
        stripped = line.rstrip("\n")
        if re.match(r"^\|\s*Rank\s*\|", stripped, flags=re.I):
            in_table = True
            continue
        if in_table and stripped.startswith("|-----"):
            continue
        m = _ROW_RE.match(stripped)
        if in_table and m:
            rank_s, iid, title, why, acceptance, status = m.groups()
            items.append(
                Top10Item(
                    rank=int(rank_s),
                    id=iid.strip(),
                    title=title.strip(),
                    why=why.strip(),
                    acceptance=acceptance.strip(),
                    status=status.strip(),
                )
            )
            continue
        if in_table and items and stripped and not stripped.startswith("|"):
            in_table = False
            tail.append(line)
            continue
        if in_table and not stripped:
            # blank line after table ends table
            in_table = False
            tail.append(line)
            continue
        if not items:
            head.append(line)
        else:
            tail.append(line)
    return head, items, tail


def _table_lines(items: list[Top10Item]) -> list[str]:
    out = [
        "| Rank | Id | Title | Why | Acceptance | Status |\n",
        "|-----:|----|-------|-----|------------|--------|\n",
    ]
    for i, it in enumerate(items, start=1):
        out.append(
            f"| {i} | {it.id} | {it.title} | {it.why} | {it.acceptance} | {it.status} |\n"
        )
    return out


def load_items(path: Path = TOP10_PATH) -> list[Top10Item]:
    _head, items, _tail = _parse(path.read_text(encoding="utf-8"))
    return items


def print_list(items: list[Top10Item]) -> None:
    print("TOP10_NEXT — implement open items in rank order (NO PAY)\n")
    for it in items:
        mark = "OPEN" if it.open else it.status.upper()
        print(f"  #{it.rank:02d}  [{mark:4}]  {it.id}  {it.title}")
    open_n = sum(1 for it in items if it.open)
    print(f"\nopen={open_n} / total={len(items)}  ·  SoT: notes/TOP10_NEXT.md")


def next_open(items: list[Top10Item]) -> Top10Item | None:
    for it in items:
        if it.open:
            return it
    return None


def refresh(path: Path = TOP10_PATH) -> list[Top10Item]:
    text = path.read_text(encoding="utf-8")
    head, items, tail = _parse(text)
    if not items:
        raise SystemExit(f"no TOP10 rows parsed from {path}")
    open_items = [it for it in items if it.open]
    done_items = [it for it in items if not it.open]
    # Stable within buckets by previous rank
    open_items.sort(key=lambda x: x.rank)
    done_items.sort(key=lambda x: x.rank)
    ordered = open_items + done_items
    for i, it in enumerate(ordered, start=1):
        it.rank = i
    # Rebuild: keep head until table header; replace table; keep tail after table
    # Drop trailing blank lines from head that were part of old table intro
    new_head: list[str] = []
    for line in head:
        if line.startswith("| Rank") or line.startswith("|-----"):
            continue
        new_head.append(line)
    while new_head and new_head[-1].strip() == "":
        new_head.pop()
    if new_head and not new_head[-1].endswith("\n"):
        new_head[-1] = new_head[-1] + "\n"
    new_head.append("\n")
    body = "".join(new_head) + "".join(_table_lines(ordered))
    if tail:
        if not body.endswith("\n"):
            body += "\n"
        body += "".join(tail)
    path.write_text(body, encoding="utf-8")
    return ordered


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="Print ranked list (default)")
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="Mechanical re-rank: open first, renumber 1..N, write TOP10_NEXT.md",
    )
    ap.add_argument("--next", action="store_true", help="Print highest-rank open item only")
    ap.add_argument("--path", type=Path, default=TOP10_PATH)
    args = ap.parse_args(argv)

    if args.refresh:
        items = refresh(args.path)
        print_list(items)
        print(f"\nrefreshed {args.path.relative_to(ROOT)}")
        return 0

    items = load_items(args.path)
    if args.next:
        nxt = next_open(items)
        if not nxt:
            print("no open TOP10_NEXT items")
            return 1
        print(f"#{nxt.rank} {nxt.id} {nxt.title} — {nxt.acceptance}")
        return 0

    print_list(items)
    return 0


if __name__ == "__main__":
    sys.exit(main())
