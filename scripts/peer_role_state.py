#!/usr/bin/env python3
"""Thin role-state schema — assignment / blocked / files / verify.

Needle: OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07 (#16 Role state schema)

JSON helper for peer roles so orchestrators can persist who owns what without
stuffing chat. Additive under notes/role_state/ — never deletes live SoT.

Usage:
  python3 scripts/peer_role_state.py get factory_engineer
  python3 scripts/peer_role_state.py set factory_engineer --assignment "…" --files a,b --verify-cmd "…"
  python3 scripts/peer_role_state.py block factory_engineer --reason "…"
  python3 scripts/peer_role_state.py unblock factory_engineer
  python3 scripts/peer_role_state.py list
  ./scripts/peer role-state list
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent

NEEDLE = "OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07"
STATE_DIR = ROOT / "notes" / "role_state"
SCHEMA_VERSION = 1

REQUIRED_KEYS = ("role_id", "assignment", "blocked", "files", "verify_cmd")


def _utc_ts() -> float:
    return time.time()


def state_path(role_id: str, *, root: Path | None = None) -> Path:
    rid = str(role_id or "").strip()
    if not rid or "/" in rid or ".." in rid:
        raise ValueError(f"invalid role_id: {role_id!r}")
    base = (root or ROOT) / "notes" / "role_state"
    return base / f"{rid}.json"


def empty_state(role_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "needle": NEEDLE,
        "role_id": str(role_id).strip(),
        "assignment": "",
        "blocked": False,
        "blocked_reason": "",
        "files": [],
        "verify_cmd": "",
        "updated_ts": 0.0,
    }


def validate_state(data: dict[str, Any]) -> list[str]:
    """Return list of schema problems (empty = ok)."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return ["not an object"]
    for key in REQUIRED_KEYS:
        if key not in data:
            errs.append(f"missing:{key}")
    if "role_id" in data and not str(data.get("role_id") or "").strip():
        errs.append("empty:role_id")
    if "blocked" in data and not isinstance(data.get("blocked"), bool):
        errs.append("blocked must be bool")
    if "files" in data and not isinstance(data.get("files"), list):
        errs.append("files must be list")
    return errs


def load_state(role_id: str, *, root: Path | None = None) -> dict[str, Any]:
    path = state_path(role_id, root=root)
    if not path.is_file():
        return empty_state(role_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_state(role_id)
    if not isinstance(data, dict):
        return empty_state(role_id)
    out = empty_state(role_id)
    out.update({k: data[k] for k in data if k in out or k in ("blocked_reason", "schema_version", "needle")})
    out["role_id"] = str(role_id).strip()
    files = out.get("files") or []
    if not isinstance(files, list):
        files = []
    out["files"] = [str(f) for f in files if str(f).strip()]
    out["blocked"] = bool(out.get("blocked"))
    out["assignment"] = str(out.get("assignment") or "")
    out["verify_cmd"] = str(out.get("verify_cmd") or "")
    out["blocked_reason"] = str(out.get("blocked_reason") or "")
    return out


def save_state(state: dict[str, Any], *, root: Path | None = None) -> Path:
    rid = str(state.get("role_id") or "").strip()
    if not rid:
        raise ValueError("role_id required")
    errs = validate_state(state)
    if errs:
        raise ValueError("invalid state: " + ", ".join(errs))
    path = state_path(rid, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state)
    payload["schema_version"] = SCHEMA_VERSION
    payload["needle"] = NEEDLE
    payload["updated_ts"] = _utc_ts()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def set_assignment(
    role_id: str,
    *,
    assignment: str | None = None,
    files: list[str] | None = None,
    verify_cmd: str | None = None,
    blocked: bool | None = None,
    blocked_reason: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    state = load_state(role_id, root=root)
    if assignment is not None:
        state["assignment"] = str(assignment)
    if files is not None:
        state["files"] = [str(f).strip() for f in files if str(f).strip()]
    if verify_cmd is not None:
        state["verify_cmd"] = str(verify_cmd)
    if blocked is not None:
        state["blocked"] = bool(blocked)
        if not blocked:
            state["blocked_reason"] = ""
    if blocked_reason is not None:
        state["blocked_reason"] = str(blocked_reason)
        if blocked_reason:
            state["blocked"] = True
    save_state(state, root=root)
    return state


def list_states(*, root: Path | None = None) -> list[dict[str, Any]]:
    base = (root or ROOT) / "notes" / "role_state"
    if not base.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        rid = path.stem
        out.append(load_state(rid, root=root))
    return out


def format_state(state: dict[str, Any]) -> str:
    rid = state.get("role_id") or "?"
    blocked = "BLOCKED" if state.get("blocked") else "open"
    files = ", ".join(state.get("files") or []) or "—"
    assign = (state.get("assignment") or "").strip() or "—"
    verify = (state.get("verify_cmd") or "").strip() or "—"
    reason = (state.get("blocked_reason") or "").strip()
    lines = [
        f"role={rid} status={blocked}",
        f"assignment={assign}",
        f"files={files}",
        f"verify_cmd={verify}",
    ]
    if reason:
        lines.append(f"blocked_reason={reason}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Thin peer role state (assignment/blocked/files/verify)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_get = sub.add_parser("get", help="Print one role state")
    p_get.add_argument("role_id")
    p_get.add_argument("--json", action="store_true")

    p_set = sub.add_parser("set", help="Update assignment / files / verify")
    p_set.add_argument("role_id")
    p_set.add_argument("--assignment", default=None)
    p_set.add_argument("--files", default=None, help="comma-separated paths")
    p_set.add_argument("--verify-cmd", default=None)
    p_set.add_argument("--json", action="store_true")

    p_block = sub.add_parser("block", help="Mark role blocked")
    p_block.add_argument("role_id")
    p_block.add_argument("--reason", default="")
    p_block.add_argument("--json", action="store_true")

    p_un = sub.add_parser("unblock", help="Clear blocked flag")
    p_un.add_argument("role_id")
    p_un.add_argument("--json", action="store_true")

    p_list = sub.add_parser("list", help="List all role states")
    p_list.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)

    if args.cmd == "get":
        state = load_state(args.role_id)
        if args.json:
            print(json.dumps(state, indent=2))
        else:
            print(format_state(state))
        return 0

    if args.cmd == "set":
        files = None
        if args.files is not None:
            files = [p.strip() for p in str(args.files).split(",") if p.strip()]
        state = set_assignment(
            args.role_id,
            assignment=args.assignment,
            files=files,
            verify_cmd=args.verify_cmd,
        )
        if args.json:
            print(json.dumps(state, indent=2))
        else:
            print(format_state(state))
        return 0

    if args.cmd == "block":
        state = set_assignment(
            args.role_id,
            blocked=True,
            blocked_reason=args.reason or "blocked",
        )
        if args.json:
            print(json.dumps(state, indent=2))
        else:
            print(format_state(state))
        return 0

    if args.cmd == "unblock":
        state = set_assignment(args.role_id, blocked=False, blocked_reason="")
        if args.json:
            print(json.dumps(state, indent=2))
        else:
            print(format_state(state))
        return 0

    if args.cmd == "list":
        rows = list_states()
        if args.json:
            print(json.dumps(rows, indent=2))
        elif not rows:
            print("(no role states yet)")
        else:
            for s in rows:
                print(format_state(s))
                print("---")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
