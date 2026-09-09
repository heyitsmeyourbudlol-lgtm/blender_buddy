#!/usr/bin/env python3
"""Peer work assignment — agents assign each other work with ETA vs cursor-agent deadline.

Any agent can delegate scoped work to another niche via GLink ASN. ETA heuristics
decide help **now** (this cycle), **later** (next slot before session ends), or **miss**
(deadline impossible — escalate BLOCK).

Usage:
  python3 scripts/peer_work_assign.py --write
  python3 scripts/peer_work_assign.py --eta --task "fix verify_runner flake" --role verify_runner
  python3 scripts/peer_work_assign.py --assign --from factory_engineer --to verify_runner --task "..."
  ./scripts/peer assign --from X --to Y --task "..."
  ./scripts/peer eta --task "..." --role verify_runner
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

WORK_ASSIGN_MD = ROOT / "notes" / "WORK_ASSIGN.md"
REGISTRY_PATH = auto.CONFIG_DIR / "work-assignments.json"

MSG_ASN = "ASN"  # re-export; canonical in peer_agent_comms

ASSIGN_MANDATE = """**Peer work assignment** — delegate across niches to ship faster:

Agents may **assign each other** scoped work when parallel product speed beats solo hero work.
Every assignment must include **ETA + deadline check** against the **cursor-agent session limit**.

| Field | Meaning |
|-------|---------|
| **task** | Executable scope (file paths + outcome) |
| **eta_sec** | Estimated seconds for assignee to finish |
| **due** | Hard deadline (ISO) — min(your target, cursor-agent timeout) |
| **when** | `now` = take this cycle · `later` = next slot before due · `miss` = escalate BLOCK |
| **slack_sec** | due − (now + eta) — negative means won't meet deadline |"""

ASSIGN_WORKFLOW = """**Assign workflow:**

```
1. Estimate: ./scripts/peer eta --task "..." --role verify_runner [--deadline ISO]
2. If when=now|later → assign: ./scripts/peer assign --from YOU --to ROLE --task "..."
3. Assignee reads vault todo + GLink ASN; posts ACK then DONE
4. If when=miss → split scope, reassign, or post GLink BLOCK — do not pretend on-time
```"""

WHEN_NOW = "now"
WHEN_LATER = "later"
WHEN_MISS = "miss"

# Base minutes by niche (heuristic — refine with learn-record over time).
ROLE_ETA_BASE_MIN: dict[str, float] = {
    "verify_runner": 8,
    "factory_engineer": 25,
    "adapt_specialist": 20,
    "queue_steward": 12,
    "communications_engineer": 18,
    "integration_architect": 30,
    "compression_engineer": 15,
    "safety_auditor": 12,
    "command_builder": 15,
    "efficiency_researcher": 20,
    "output_researcher": 25,
    "orchestrator": 10,
}

NICHE_ASSIGN: dict[str, tuple[str, ...]] = {
    "orchestrator": (
        "Assign disjoint file scopes — never two peers same path.",
        "Run `./scripts/peer eta` per peer before dispatch; skip when=miss.",
    ),
    "factory_engineer": (
        "Assign verify_runner for test-only runs; adapt_specialist for profile drift.",
    ),
    "verify_runner": (
        "Accept run-only assignments; assign factory_engineer for code fixes.",
    ),
    "queue_steward": (
        "Assign sync pairs to self; escalate drift to orchestrator with ETA.",
    ),
}


@dataclass(frozen=True)
class EtaDecision:
    eta_sec: int
    deadline_ts: float
    finish_ts: float
    slack_sec: int
    when: str
    cursor_limit_ts: float

    @property
    def due_iso(self) -> str:
        return datetime.fromtimestamp(self.deadline_ts, tz=timezone.utc).astimezone().isoformat(
            timespec="seconds"
        )

    def format_summary(self) -> str:
        return (
            f"eta={self.eta_sec}s ({self.eta_sec // 60}m) · "
            f"when={self.when} · slack={self.slack_sec}s · due={self.due_iso}"
        )


def base_role_id(role_id: str) -> str:
    rid = str(role_id or "").strip()
    m = re.match(r"^(.+)_L\d+$", rid)
    return m.group(1) if m else rid


def cursor_agent_timeout_sec() -> float:
    try:
        import peer_terminal as pt

        return float(pt.DEFAULT_AGENT_TIMEOUT_SEC)
    except Exception:  # noqa: BLE001
        return float(auto.CFG.get("cursor_agent_timeout_sec") or 7200)


def eta_buffer_sec() -> int:
    return int(auto.CFG.get("agent_task_eta_buffer_sec") or 120)


def parse_deadline(value: str) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        if raw.isdigit():
            return float(raw)
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (TypeError, ValueError):
        return None


def estimate_eta_sec(task: str, *, role_id: str = "") -> int:
    """Heuristic ETA in seconds for assignment planning."""
    base_min = ROLE_ETA_BASE_MIN.get(base_role_id(role_id), 15.0)
    sec = int(base_min * 60)
    paths = len(re.findall(r"[\w./-]+\.(?:py|md|json|sh)", task))
    sec += paths * 120
    lower = task.lower()
    if any(w in lower for w in ("refactor", "rewrite", "migrate", "all repos")):
        sec += 600
    if any(w in lower for w in ("verify", "unittest", "self-check", "test")):
        sec += 180
    if any(w in lower for w in ("one line", "one file", "minimal")):
        sec = max(sec - 300, 300)
    return sec + eta_buffer_sec()


def scheduling_decision(
    *,
    eta_sec: int,
    deadline_ts: float | None = None,
    now: float | None = None,
) -> EtaDecision:
    """Compare ETA vs cursor-agent session limit and optional target deadline."""
    t0 = now if now is not None else time.time()
    cursor_limit_ts = t0 + cursor_agent_timeout_sec()
    if deadline_ts is None:
        effective_deadline = cursor_limit_ts
    else:
        effective_deadline = min(deadline_ts, cursor_limit_ts)
    finish_ts = t0 + max(0, eta_sec)
    slack_sec = int(effective_deadline - finish_ts)
    if slack_sec >= 0:
        when = WHEN_NOW
    elif deadline_ts is None and finish_ts <= cursor_limit_ts - 60:
        # Deadline miss is solely cursor-session-caused; task fits session → defer
        when = WHEN_LATER
    else:
        when = WHEN_MISS
    return EtaDecision(
        eta_sec=eta_sec,
        deadline_ts=effective_deadline,
        finish_ts=finish_ts,
        slack_sec=slack_sec,
        when=when,
        cursor_limit_ts=cursor_limit_ts,
    )


def load_registry() -> list[dict]:
    if not REGISTRY_PATH.is_file():
        return []
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        return list(data.get("assignments") or []) if isinstance(data, dict) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_registry(rows: list[dict]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated": time.time(), "assignments": rows[-200:]}
    REGISTRY_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def list_open_assignments(*, for_role: str | None = None) -> list[dict]:
    rows = load_registry()
    out: list[dict] = []
    for row in rows:
        if row.get("status") not in (None, "open", "ack"):
            continue
        if for_role and row.get("to") != for_role:
            continue
        out.append(row)
    return out


def assign_work(
    from_role: str,
    to_role: str,
    task: str,
    *,
    deadline_ts: float | None = None,
    paths: list[str] | None = None,
    force_when: str = "",
) -> dict:
    """Post GLink ASN + vault todo for assignee."""
    import peer_agent_comms as comms

    if not comms.comms_enabled():
        raise RuntimeError("agent comms disabled — enable agent_comms_enabled in config")

    eta_sec = estimate_eta_sec(task, role_id=to_role)
    decision = scheduling_decision(eta_sec=eta_sec, deadline_ts=deadline_ts)
    when = force_when or decision.when
    if when == WHEN_MISS and not force_when:
        return {
            "ok": False,
            "reason": "deadline_miss",
            "eta_sec": eta_sec,
            "when": when,
            "slack_sec": decision.slack_sec,
            "summary": decision.format_summary(),
        }

    assign_id = f"asn-{int(time.time())}-{base_role_id(to_role)[:8]}"
    payload = {
        "id": assign_id,
        "task": task.strip()[:500],
        "eta_sec": eta_sec,
        "when": when,
        "due": decision.due_iso,
        "slack_sec": decision.slack_sec,
        "paths": paths or [],
        "from": from_role,
    }
    comms.post_glink(
        msg_type=comms.MSG_ASN,
        from_role=from_role,
        to_role=to_role,
        payload=payload,
    )
    todo_line = f"[{assign_id} when={when} eta={eta_sec // 60}m] {task.strip()[:180]}"
    comms.update_tasks(to_role, append_todo=todo_line)
    row = {
        "id": assign_id,
        "from": from_role,
        "to": to_role,
        "task": task.strip()[:500],
        "eta_sec": eta_sec,
        "when": when,
        "due": decision.due_iso,
        "slack_sec": decision.slack_sec,
        "status": "open",
        "ts": time.time(),
        "paths": paths or [],
    }
    rows = load_registry()
    rows.append(row)
    save_registry(rows)
    return {"ok": True, **row}


def format_assignments_block(*, for_role: str | None = None, max_entries: int = 8) -> str:
    open_rows = list_open_assignments(for_role=for_role)
    if not open_rows:
        label = f" for `{for_role}`" if for_role else ""
        return f"- No open peer assignments{label}."
    lines: list[str] = []
    for row in open_rows[-max_entries:]:
        lines.append(
            f"- **{row.get('id')}** {row.get('from')}→{row.get('to')} "
            f"when={row.get('when')} eta={int(row.get('eta_sec', 0)) // 60}m · "
            f"{str(row.get('task', ''))[:70]}"
        )
    return "\n".join(lines)


def format_niche_assign(role_id: str) -> str:
    base = base_role_id(role_id)
    tips = NICHE_ASSIGN.get(base, ())
    if not tips:
        return "- Use `./scripts/peer eta` before assigning; `./scripts/peer assign` to delegate."
    return "\n".join(f"- {t}" for t in tips)


def format_work_assign_block(*, role_id: str | None = None) -> str:
    lines = [
        "## Peer work assignment (ETA vs cursor-agent deadline)",
        "",
        ASSIGN_MANDATE,
        "",
        ASSIGN_WORKFLOW,
        "",
        f"- cursor-agent session limit: **{int(cursor_agent_timeout_sec() // 60)} min** "
        f"(hard ceiling for when=now/later)",
        "",
        "**Open assignments:**",
        format_assignments_block(for_role=role_id),
        "",
    ]
    if role_id:
        lines.extend(["**Your niche:**", format_niche_assign(role_id), ""])
    lines.append(
        "_CLI:_ `./scripts/peer eta --task \"...\" --role ROLE` · "
        "`./scripts/peer assign --from YOU --to ROLE --task \"...\"`"
    )
    return "\n".join(lines).strip()


def write_work_assign_md() -> Path:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines = [
        "# Peer work assignment — ETA + deadline",
        "",
        f"_Updated {now}_ · assign across niches · respect cursor-agent timeout",
        "",
        ASSIGN_MANDATE,
        "",
        ASSIGN_WORKFLOW,
        "",
        f"## Session limit\n\n- cursor-agent timeout: **{int(cursor_agent_timeout_sec() // 60)}** minutes\n",
        "## Open assignments\n",
        format_assignments_block(max_entries=20),
        "",
        "## Niche guidance",
        "",
    ]
    for rid in sorted(NICHE_ASSIGN):
        title = rid.replace("_", " ").title()
        lines.append(f"### {title}")
        lines.append(format_niche_assign(rid))
        lines.append("")
    WORK_ASSIGN_MD.parent.mkdir(parents=True, exist_ok=True)
    WORK_ASSIGN_MD.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return WORK_ASSIGN_MD


def suggest_assignee(task: str) -> dict:
    """Pick role + template for a task (Agent Builder / factory routing)."""
    import peer_agent_builder as ab

    return ab.who_for_task(task)


def main() -> int:
    parser = argparse.ArgumentParser(description="Peer work assignment with ETA")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--block", action="store_true")
    parser.add_argument("--role", default="", help="Role for block/list context")
    parser.add_argument("--eta", action="store_true")
    parser.add_argument("--assign", action="store_true")
    parser.add_argument("--suggest", action="store_true", help="Print pick_role + match_template for --task")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--from", dest="from_role", default="")
    parser.add_argument("--to", dest="to_role", default="")
    parser.add_argument("--task", default="")
    parser.add_argument("--deadline", default="", help="ISO timestamp or unix seconds")
    parser.add_argument("--paths", default="", help="Comma-separated paths")
    parser.add_argument("--force-when", choices=[WHEN_NOW, WHEN_LATER, WHEN_MISS], default="")
    args = parser.parse_args()

    if args.suggest:
        if not args.task:
            print("suggest requires --task", file=sys.stderr)
            return 1
        report = suggest_assignee(args.task)
        print(json.dumps(report, indent=2))
        return 0

    if args.list:
        for row in list_open_assignments(for_role=args.role or None):
            print(
                f"{row.get('id')}: {row.get('from')}→{row.get('to')} "
                f"when={row.get('when')} {str(row.get('task', ''))[:60]}"
            )
        return 0

    if args.eta:
        if not args.task:
            print("eta requires --task", file=sys.stderr)
            return 1
        eta_sec = estimate_eta_sec(args.task, role_id=args.role or args.to_role)
        decision = scheduling_decision(
            eta_sec=eta_sec,
            deadline_ts=parse_deadline(args.deadline),
        )
        print(decision.format_summary())
        print(f"cursor_limit={datetime.fromtimestamp(decision.cursor_limit_ts).isoformat(timespec='seconds')}")
        return 0 if decision.when != WHEN_MISS else 2

    if args.assign:
        if not args.from_role or not args.task:
            print("assign requires --from --task (and --to, or omit --to to auto-pick)", file=sys.stderr)
            return 1
        to_role = args.to_role
        if not to_role:
            suggestion = suggest_assignee(args.task)
            to_role = str(suggestion.get("role_id") or "")
            if not to_role:
                print("assign: could not auto-pick --to from task", file=sys.stderr)
                return 1
            print(
                f"auto-to: {to_role} (template={suggestion.get('template')} "
                f"score={suggestion.get('score')})",
                file=sys.stderr,
            )
        paths = [p.strip() for p in args.paths.split(",") if p.strip()] if args.paths else None
        try:
            result = assign_work(
                args.from_role,
                to_role,
                args.task,
                deadline_ts=parse_deadline(args.deadline),
                paths=paths,
                force_when=args.force_when,
            )
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            return 1
        if not result.get("ok"):
            print(f"ASSIGN BLOCKED: {result.get('reason')} — {result.get('summary')}", file=sys.stderr)
            return 2
        print(f"assigned {result.get('id')} when={result.get('when')} eta={result.get('eta_sec')}s")
        return 0

    if args.block:
        print(format_work_assign_block(role_id=args.role or None))
        return 0

    path = write_work_assign_md()
    print(f"work-assign: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
