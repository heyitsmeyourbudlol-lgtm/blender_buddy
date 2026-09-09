#!/usr/bin/env python3
"""Automation engine — match events to rules and yield actions (Cursor Automations-style)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import automation_actions as actions  # noqa: E402
import automation_rules_config as arc  # noqa: E402


@dataclass
class EngineResult:
    event: str
    matched_rules: list[str] = field(default_factory=list)
    action_results: list[str] = field(default_factory=list)
    skipped_cooldown: list[str] = field(default_factory=list)


def _now() -> float:
    return time.time()


def _audit(line: str) -> None:
    if not arc.audit_enabled():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    arc.log_path().parent.mkdir(parents=True, exist_ok=True)
    with arc.log_path().open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp}  {line}\n")


def load_state() -> dict[str, Any]:
    path = arc.state_path()
    if not path.is_file():
        return {"cooldowns": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"cooldowns": {}}


def save_state(state: dict[str, Any]) -> None:
    arc.state_path().parent.mkdir(parents=True, exist_ok=True)
    arc.state_path().write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def load_rules() -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for path in reversed(arc.rules_paths()):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        raw_rules = data.get("rules") if isinstance(data, dict) else None
        if not isinstance(raw_rules, list):
            continue
        for rule in raw_rules:
            if not isinstance(rule, dict):
                continue
            rule_id = str(rule.get("id") or "")
            if rule_id:
                merged[rule_id] = rule
            else:
                merged[f"anon-{len(merged)}"] = rule
    return list(merged.values())


def _payload_text(payload: dict[str, Any]) -> str:
    bits: list[str] = []
    for key in ("note", "title", "detail", "message", "branch", "status"):
        val = payload.get(key)
        if val:
            bits.append(str(val))
    return " ".join(bits).lower()


def _when_matches(when: dict[str, Any], payload: dict[str, Any]) -> bool:
    if not when:
        return True
    for key, expected in when.items():
        if key == "any":
            text = _payload_text(payload)
            terms = expected if isinstance(expected, list) else [expected]
            if not any(str(t).lower() in text for t in terms):
                return False
            continue
        if key == "all":
            text = _payload_text(payload)
            terms = expected if isinstance(expected, list) else [expected]
            if not all(str(t).lower() in text for t in terms):
                return False
            continue
        if key.endswith("_contains"):
            field = key[: -len("_contains")]
            hay = str(payload.get(field) or "").lower()
            if str(expected).lower() not in hay:
                return False
            continue
        actual = payload.get(key)
        if isinstance(expected, bool):
            if bool(actual) is not expected:
                return False
        elif actual != expected:
            return False
    return True


def match_rules(event: str, payload: dict[str, Any], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for rule in rules:
        if rule.get("enabled") is False:
            continue
        if str(rule.get("on") or "") != event:
            continue
        when = rule.get("when")
        if isinstance(when, dict) and not _when_matches(when, payload):
            continue
        matched.append(rule)
    return matched


def _on_cooldown(state: dict[str, Any], rule_id: str, cooldown_sec: float) -> bool:
    if cooldown_sec <= 0:
        return False
    cooldowns = state.setdefault("cooldowns", {})
    if not isinstance(cooldowns, dict):
        return False
    last = float(cooldowns.get(rule_id) or 0)
    return (_now() - last) < cooldown_sec


def _set_cooldown(state: dict[str, Any], rule_id: str) -> None:
    cooldowns = state.setdefault("cooldowns", {})
    if isinstance(cooldowns, dict):
        cooldowns[rule_id] = _now()


def emit(event: str, payload: dict[str, Any] | None = None, *, dry_run: bool = False) -> EngineResult:
    """Match rules for an event and execute actions."""
    if not arc.enabled():
        return EngineResult(event=event)
    payload = dict(payload or {})
    payload.setdefault("event", event)
    payload.setdefault("ts", _now())
    rules = load_rules()
    matched = match_rules(event, payload, rules)
    state = load_state()
    result = EngineResult(event=event)
    for rule in matched:
        rule_id = str(rule.get("id") or "anonymous")
        try:
            cooldown_sec = float(rule.get("cooldown_sec") or 0)
        except (TypeError, ValueError):
            cooldown_sec = 0.0
        if _on_cooldown(state, rule_id, cooldown_sec):
            result.skipped_cooldown.append(rule_id)
            continue
        result.matched_rules.append(rule_id)
        raw_actions = rule.get("actions")
        if not isinstance(raw_actions, list):
            continue
        for action in raw_actions:
            if not isinstance(action, dict):
                continue
            if dry_run:
                result.action_results.append(f"dry_run:{action.get('type')}")
                continue
            outcome = actions.execute(action, payload)
            result.action_results.append(f"{rule_id}:{outcome}")
        if not dry_run:
            _set_cooldown(state, rule_id)
    if not dry_run:
        save_state(state)
    _audit(
        f"event={event} matched={','.join(result.matched_rules) or '-'} "
        f"actions={len(result.action_results)} skipped={','.join(result.skipped_cooldown) or '-'}"
    )
    return result


def emit_peer_cycle(state: dict[str, Any], **extra: Any) -> EngineResult:
    """Emit peer.cycle.end + verify ok/fail from peer-loop-state last_cycle."""
    lc = state.get("last_cycle")
    payload: dict[str, Any] = {}
    if isinstance(lc, dict):
        payload = {
            "verify_ok": bool(lc.get("verify_ok")),
            "rc": lc.get("rc"),
            "noop": bool(lc.get("noop")),
            "note": str(lc.get("note") or ""),
            "queue_fp": lc.get("queue_fp"),
            "queue_fp_before": lc.get("queue_fp_before"),
            "failure_type": lc.get("failure_type"),
        }
    payload.update(extra)
    result = emit("peer.cycle.end", payload)
    if payload.get("verify_ok"):
        emit("peer.verify.ok", payload)
    else:
        emit("peer.verify.fail", payload)
    return result


def handle_webhook(body: dict[str, Any]) -> EngineResult:
    event = str(body.get("event") or "webhook.received")
    payload = body.get("payload")
    if not isinstance(payload, dict):
        payload = {k: v for k, v in body.items() if k != "event"}
    return emit(event, payload)


def list_rules() -> list[dict[str, Any]]:
    return load_rules()


def main() -> int:
    parser = argparse.ArgumentParser(description="Automation engine — event rules")
    parser.add_argument("--emit", default="", help="Event name to emit")
    parser.add_argument("--payload", default="{}", help="JSON payload")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true", help="List loaded rules")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.list:
        rules = list_rules()
        if args.json:
            print(json.dumps(rules, indent=2))
        else:
            for rule in rules:
                print(f"{rule.get('id')}: on={rule.get('on')} enabled={rule.get('enabled', True)}")
        return 0
    if not args.emit:
        parser.print_help()
        return 1
    try:
        payload = json.loads(args.payload)
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"invalid payload: {exc}", file=sys.stderr)
        return 1
    result = emit(args.emit, payload, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result.__dict__, indent=2))
    else:
        print(f"event={result.event} matched={result.matched_rules} actions={result.action_results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
