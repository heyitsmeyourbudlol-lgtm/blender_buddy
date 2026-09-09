#!/usr/bin/env python3
"""Rule-change digest — propose-only surface for human accept/reject.

Needle: OVERSEER_RULE_CHANGE_PROPOSE_ONLY_2026_09_06

NEVER mute, delete, or auto-apply rules. This script only maintains
``notes/RULE_SHUTDOWN_DIGEST.md`` proposal rows for human review.

Usage:
  python3 scripts/peer_rule_shutdown.py write-digest
  python3 scripts/peer_rule_shutdown.py list
  python3 scripts/peer_rule_shutdown.py propose --action suspend --rule PATH --why "..."
  python3 scripts/peer_rule_shutdown.py accept --rule PATH
  python3 scripts/peer_rule_shutdown.py reject --rule PATH
  ./scripts/peer rule-shutdown-digest
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
DIGEST = ROOT / "notes" / "RULE_SHUTDOWN_DIGEST.md"
NEEDLE = "OVERSEER_RULE_CHANGE_PROPOSE_ONLY_2026_09_06"
VALID_ACTIONS = ("add", "remove", "modify", "suspend")

_HEADER = """# Rule-change digest — human accept/reject only

_Updated {ts}_ · safety_auditor / peer_rule_shutdown · Needle `{needle}`

**Policy:** propose only — do **not** mute, delete, or auto-apply rules. Human accepts/rejects each row.

## Pending proposals

| Action | Rule / path | Rationale | Status |
|--------|-------------|-----------|--------|
"""

_FOOTER = """
## How to refresh

```bash
./scripts/peer rule-shutdown-digest
# or: python3 scripts/peer_rule_shutdown.py write-digest
# propose: python3 scripts/peer_rule_shutdown.py propose --action suspend --rule PATH --why "..."
```

## Closed this cycle

{closed}
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_table(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    in_pending = False
    for line in text.splitlines():
        if line.strip() == "## Pending proposals":
            in_pending = True
            continue
        if in_pending and line.startswith("## "):
            break
        if not in_pending or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        if cells[0].lower() in ("action", "--------") or cells[0].startswith("-"):
            continue
        if cells[0] in ("_(none)_", "—", "-") and cells[1] in ("—", "-", ""):
            continue
        rows.append(
            {
                "action": cells[0],
                "rule": cells[1],
                "rationale": cells[2],
                "status": cells[3],
            }
        )
    return rows


def _parse_closed(text: str) -> list[str]:
    closed: list[str] = []
    in_closed = False
    for line in text.splitlines():
        if line.strip() == "## Closed this cycle":
            in_closed = True
            continue
        if in_closed and line.startswith("## "):
            break
        if in_closed and line.startswith("- "):
            closed.append(line[2:].strip())
    return closed


def _render(rows: list[dict[str, str]], closed: list[str]) -> str:
    body = _HEADER.format(ts=_utc_now(), needle=NEEDLE)
    if not rows:
        body += "| _(none)_ | — | No pending add/remove/modify/suspend | awaiting human |\n"
    else:
        for r in rows:
            body += (
                f"| {r['action']} | {r['rule']} | {r['rationale']} | {r['status']} |\n"
            )
    closed_block = "\n".join(f"- {c}" for c in closed) if closed else "- _(none)_"
    body += _FOOTER.format(closed=closed_block)
    return body


def _load() -> tuple[list[dict[str, str]], list[str]]:
    if not DIGEST.is_file():
        return [], []
    text = DIGEST.read_text(encoding="utf-8")
    return _parse_table(text), _parse_closed(text)


def write_digest(*, ensure: bool = True) -> Path:
    """Refresh digest timestamp; preserve pending rows. Never mutes rules."""
    rows, closed = _load()
    DIGEST.parent.mkdir(parents=True, exist_ok=True)
    DIGEST.write_text(_render(rows, closed), encoding="utf-8")
    print(f"wrote {DIGEST.relative_to(ROOT)} pending={len(rows)} needle={NEEDLE}")
    return DIGEST


def cmd_list() -> int:
    rows, _ = _load()
    if not rows:
        print("pending: (none) — no add/remove/modify/suspend proposals")
        return 0
    print("pending proposals (human accept/reject — propose-only):")
    for r in rows:
        print(f"  [{r['status']}] {r['action']}: {r['rule']} — {r['rationale']}")
    return 0


def cmd_propose(action: str, rule: str, why: str) -> int:
    action = action.strip().lower()
    if action not in VALID_ACTIONS:
        print(f"action must be one of {VALID_ACTIONS}", file=sys.stderr)
        return 1
    rule = rule.strip()
    why = why.strip() or "unspecified"
    if not rule:
        print("--rule required", file=sys.stderr)
        return 1
    rows, closed = _load()
    for r in rows:
        if r["rule"] == rule and r["action"] == action and r["status"] == "pending":
            print(f"already pending: {action} {rule}")
            return 0
    rows.append(
        {
            "action": action,
            "rule": rule,
            "rationale": why.replace("|", "/"),
            "status": "pending",
        }
    )
    DIGEST.write_text(_render(rows, closed), encoding="utf-8")
    print(f"proposed {action} {rule} (human must accept/reject — no mute applied)")
    return 0


def _set_status(rule: str, status: str) -> int:
    rule = rule.strip()
    rows, closed = _load()
    found = False
    kept: list[dict[str, str]] = []
    for r in rows:
        if r["rule"] == rule:
            found = True
            closed.append(
                f"{status}: {r['action']} `{r['rule']}` — {r['rationale']} "
                f"(digest status only; rules not muted)"
            )
        else:
            kept.append(r)
    if not found:
        print(f"no pending row for rule={rule!r}", file=sys.stderr)
        return 1
    DIGEST.write_text(_render(kept, closed), encoding="utf-8")
    print(
        f"{status} recorded for {rule} in digest only — "
        "no rule files muted/deleted/modified"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Propose-only rule-change digest (never mute rules)"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="list",
        choices=("write-digest", "list", "propose", "accept", "reject", "ack"),
        help="write-digest refreshes notes/RULE_SHUTDOWN_DIGEST.md",
    )
    parser.add_argument(
        "--action",
        choices=VALID_ACTIONS,
        help="propose: add|remove|modify|suspend",
    )
    parser.add_argument("--rule", help="rule id or path")
    parser.add_argument("--why", default="", help="propose rationale")
    args = parser.parse_args(argv)

    cmd = args.command
    if cmd == "write-digest":
        write_digest()
        return 0
    if cmd == "list":
        if not DIGEST.is_file():
            write_digest()
        return cmd_list()
    if cmd == "propose":
        if not args.action or not args.rule:
            print("propose requires --action and --rule", file=sys.stderr)
            return 1
        return cmd_propose(args.action, args.rule, args.why)
    if cmd in ("accept", "ack"):
        if not args.rule:
            print("accept requires --rule", file=sys.stderr)
            return 1
        return _set_status(args.rule, "accepted")
    if cmd == "reject":
        if not args.rule:
            print("reject requires --rule", file=sys.stderr)
            return 1
        return _set_status(args.rule, "rejected")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
