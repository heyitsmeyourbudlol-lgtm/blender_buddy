"""Automation action registry — execute yielded actions from rules."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable

import automation_rules_config as arc
import project_automation as auto

ROOT = auto.ROOT


def _noop(_payload: dict[str, Any], action: dict[str, Any]) -> str:
    return "noop"


def wake_peer(_payload: dict[str, Any], _action: dict[str, Any]) -> str:
    import peer_transcript as pt

    pt.poke_turn_signal()
    return "wake_peer: touched peer-turn.signal"


def enqueue(_payload: dict[str, Any], action: dict[str, Any]) -> str:
    title = str(action.get("title") or "Automation task")
    detail = str(action.get("detail") or action.get("body") or "")
    prefix = str(action.get("prefix") or "auto")
    marker = f"[{prefix}] {title}"
    work_path = auto.WORK_QUEUE_PATH
    ctx_path = auto.CONTEXT_PATH
    try:
        work_md = work_path.read_text(encoding="utf-8") if work_path.is_file() else ""
        known = {
            auto._normalize_queue_key(x)
            for x in auto.open_work_items(work_md=work_md).open_items
        }
        if auto._normalize_queue_key(marker) in known:
            return f"enqueue: already queued ({title})"
        line = f"- [ ] **{marker}** — {detail}"
        if "## Active" in work_md:
            work_md = work_md.replace("## Active\n", f"## Active\n{line}\n", 1)
        else:
            work_md = work_md.rstrip() + f"\n\n## Active\n{line}\n"
        work_path.write_text(work_md, encoding="utf-8")
        if ctx_path.is_file():
            ctx_md = ctx_path.read_text(encoding="utf-8")
            if marker not in ctx_md:
                ctx_md = auto.insert_remaining_work_bullet(ctx_md, line)
                ctx_path.write_text(ctx_md, encoding="utf-8")
        return f"enqueue: {title}"
    except OSError as exc:
        return f"enqueue failed: {exc}"


def post_cycle_hook(_payload: dict[str, Any], _action: dict[str, Any]) -> str:
    hook = auto.POST_CYCLE_HOOK
    if not hook:
        return "post_cycle_hook: not configured"
    cmd = [str(x) for x in hook] if isinstance(hook, list) else [str(hook)]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=120.0, check=False)
    if proc.returncode == 0:
        return f"post_cycle_hook: ok ({' '.join(cmd)})"
    err = (proc.stderr or proc.stdout or "failed").strip().splitlines()
    return f"post_cycle_hook: FAIL — {err[-1] if err else proc.returncode}"


def hook(_payload: dict[str, Any], action: dict[str, Any]) -> str:
    raw = action.get("cmd") or action.get("command")
    if not raw:
        return "hook: missing cmd"
    cmd = [str(x) for x in raw] if isinstance(raw, list) else [str(raw)]
    cwd = Path(str(action.get("cwd") or ROOT)).expanduser()
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=120.0, check=False)
    if proc.returncode == 0:
        return f"hook: ok ({' '.join(cmd)})"
    err = (proc.stderr or proc.stdout or "failed").strip().splitlines()
    return f"hook: FAIL — {err[-1] if err else proc.returncode}"


def log_action(payload: dict[str, Any], action: dict[str, Any]) -> str:
    msg = str(action.get("message") or action.get("msg") or payload.get("note") or "automation event")
    return f"log: {msg[:200]}"


def debrief(_payload: dict[str, Any], action: dict[str, Any]) -> str:
    import peer_debrief as deb

    title = str(action.get("title") or "Automation debrief")
    body = str(action.get("body") or action.get("detail") or "")
    kind = str(action.get("kind") or "knowledge")
    try:
        deb.append_entry(deb.DebriefEntry(kind=kind, title=title, body=body))
        return f"debrief: {title}"
    except Exception as exc:  # noqa: BLE001
        return f"debrief failed: {exc}"


def glink_post(_payload: dict[str, Any], action: dict[str, Any]) -> str:
    import peer_agent_comms as comms

    role = str(action.get("from") or action.get("role") or "automation_engine")
    msg_type = str(action.get("type") or "STAT")
    payload_obj = action.get("payload")
    if not isinstance(payload_obj, dict):
        payload_obj = {"st": "EVT", "op": str(action.get("op") or "automation")}
    try:
        comms.post_message(from_role=role, msg_type=msg_type, payload=payload_obj)
        return f"glink_post: {msg_type}"
    except Exception as exc:  # noqa: BLE001
        return f"glink_post failed: {exc}"


def run_verify(_payload: dict[str, Any], _action: dict[str, Any]) -> str:
    import run_peer_tasks as rpt

    failures, failure_type, retries = rpt.run_verify_gate(log_fn=lambda _m: None)
    if failures == 0:
        return f"run_verify: ok (retries={retries})"
    return f"run_verify: FAIL ({failures}, {failure_type}, retries={retries})"


def adapt_heal(_payload: dict[str, Any], _action: dict[str, Any]) -> str:
    proc = subprocess.run(
        ["python3", str(ROOT / "scripts" / "automation_adapt.py"), "--heal", "--write", "--quick"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180.0,
        check=False,
    )
    if proc.returncode == 0:
        return "adapt_heal: ok"
    err = (proc.stderr or proc.stdout or "failed").strip().splitlines()
    return f"adapt_heal: FAIL — {err[-1] if err else proc.returncode}"


def dedupe_queue(_payload: dict[str, Any], _action: dict[str, Any]) -> str:
    import autonomous_repair as ar

    return ar.dedupe_queue()


def clear_test_cache(_payload: dict[str, Any], _action: dict[str, Any]) -> str:
    import autonomous_repair as ar

    return ar.clear_test_cache()


def heal_git_identity(_payload: dict[str, Any], _action: dict[str, Any]) -> str:
    import autonomous_repair as ar

    return ar.heal_git_identity()


def dispatch_niche(_payload: dict[str, Any], action: dict[str, Any]) -> str:
    import autonomous_repair as ar

    role_id = str(action.get("role_id") or action.get("role") or "verify_runner")
    item = str(
        action.get("item")
        or _payload.get("detail")
        or "**[auto-repair]** Fix the failure reported in peer.verify.fail — minimal diff."
    )
    paid_api = os.environ.get("PEER_LOOP_PAID_API") == "1"
    lines: list[str] = []

    def log_fn(msg: str) -> None:
        lines.append(msg)

    result = ar.dispatch_role(role_id, item=item, log_fn=log_fn, paid_api=paid_api, sync=False)
    return result


def auto_repair_verify(_payload: dict[str, Any], _action: dict[str, Any]) -> str:
    import autonomous_repair as ar

    lines: list[str] = []

    def log_fn(msg: str) -> None:
        lines.append(msg)

    ok = ar.repair_verify_failure(
        log_fn=log_fn,
        paid_api=os.environ.get("PEER_LOOP_PAID_API") == "1",
        failure_type=str(_payload.get("failure_type") or ""),
        evidence=str(_payload.get("note") or _payload.get("detail") or ""),
    )
    tail = lines[-1] if lines else ("ok" if ok else "skipped")
    return f"auto_repair_verify: {tail}"


ACTIONS: dict[str, Callable[[dict[str, Any], dict[str, Any]], str]] = {
    "noop": _noop,
    "wake_peer": wake_peer,
    "enqueue": enqueue,
    "post_cycle_hook": post_cycle_hook,
    "hook": hook,
    "log": log_action,
    "debrief": debrief,
    "glink_post": glink_post,
    "run_verify": run_verify,
    "adapt_heal": adapt_heal,
    "dedupe_queue": dedupe_queue,
    "clear_test_cache": clear_test_cache,
    "heal_git_identity": heal_git_identity,
    "dispatch_niche": dispatch_niche,
    "auto_repair_verify": auto_repair_verify,
}


def execute(action: dict[str, Any], payload: dict[str, Any]) -> str:
    action_type = str(action.get("type") or "").strip()
    if not action_type:
        return "action: missing type"
    fn = ACTIONS.get(action_type)
    if fn is None:
        return f"action: unknown type {action_type}"
    return fn(payload, action)
