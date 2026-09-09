#!/usr/bin/env python3
"""Autonomous repair — detect factory breakage and fix without human in the loop."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

REPAIR_STATE_PATH = auto.CONFIG_DIR / "autonomous-repair-state.json"
DEFAULT_COOLDOWN_SEC = 45.0


def _cfg() -> dict[str, Any]:
    raw = auto.CFG.get("autonomous_repair")
    return raw if isinstance(raw, dict) else {}


def enabled() -> bool:
    if "enabled" in _cfg():
        return bool(_cfg().get("enabled"))
    return bool(auto.CFG.get("autonomous_repair_enabled", True))


def cooldown_sec() -> float:
    try:
        return max(10.0, float(_cfg().get("cooldown_sec") or DEFAULT_COOLDOWN_SEC))
    except (TypeError, ValueError):
        return DEFAULT_COOLDOWN_SEC


def _load_state() -> dict[str, Any]:
    try:
        if REPAIR_STATE_PATH.is_file():
            data = json.loads(REPAIR_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_state(state: dict[str, Any]) -> None:
    REPAIR_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPAIR_STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _on_cooldown(key: str) -> bool:
    state = _load_state()
    last = float((state.get("cooldowns") or {}).get(key) or 0)
    return (time.time() - last) < cooldown_sec()


def _mark(key: str) -> None:
    state = _load_state()
    cooldowns = state.setdefault("cooldowns", {})
    cooldowns[key] = time.time()
    _save_state(state)


def clear_test_cache() -> str:
    path = auto.cache_path()
    if not path.is_file():
        return "clear_test_cache: no cache"
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
        for key in ("tests_ok", "tests_detail", "tests_ts"):
            cache.pop(key, None)
        path.write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")
        return "clear_test_cache: ok"
    except (OSError, json.JSONDecodeError) as exc:
        return f"clear_test_cache: {exc}"


def dedupe_queue() -> str:
    removed = auto.dedupe_work_queue_files(write=True)
    return f"dedupe_queue: removed {removed}" if removed else "dedupe_queue: clean"


def heal_git_identity() -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(auto.ROOT), "config", "user.email"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
        if proc.returncode == 0 and (proc.stdout or "").strip():
            return "heal_git_identity: already set"
    except (OSError, subprocess.TimeoutExpired):
        pass

    name = str(_cfg().get("git_user_name") or os.environ.get("AUTOMATION_GIT_NAME") or "Automation Hub")
    email = str(_cfg().get("git_user_email") or os.environ.get("AUTOMATION_GIT_EMAIL") or "")
    if email.startswith("env:"):
        email = os.environ.get(email[4:].strip(), "")
    if not email:
        return "heal_git_identity: skipped (set AUTOMATION_GIT_EMAIL or autonomous_repair.git_user_email)"

    for scope_args, key, val in (
        (["git", "-C", str(auto.ROOT), "config"], "user.name", name),
        (["git", "-C", str(auto.ROOT), "config"], "user.email", email),
    ):
        try:
            subprocess.run(
                [*scope_args, key, val],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=True,
            )
        except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            return f"heal_git_identity: FAIL ({exc})"
    return f"heal_git_identity: set {name} <{email[:3]}…>"


def dispatch_role(
    role_id: str,
    *,
    item: str,
    log_fn: Callable[[str], None],
    paid_api: bool = False,
    sync: bool = False,
) -> str:
    import peer_parallel_dispatch as ppd
    import peer_roles as roles
    import peer_terminal as terminal

    role_list = roles.load_roles()
    role = next((r for r in role_list if r.id == role_id), None)
    if role is None:
        return f"dispatch_role: unknown role {role_id}"

    asn = roles.RoleAssignment(role=role, score=1.0, item=item)
    prompt = ppd.build_niche_prompt(asn, cwd=auto.ROOT)
    log_fn(f"autonomous repair: dispatch {role.job_title} ({role_id})")
    rc, auth_failed = terminal.run_cursor_agent(
        prompt,
        log_fn=log_fn,
        paid_api=paid_api,
        cwd=auto.ROOT,
        sync=sync,
    )
    if auth_failed:
        return f"dispatch_role: auth failed ({role_id})"
    if rc != 0 and sync:
        return f"dispatch_role: rc={rc} ({role_id})"
    return f"dispatch_role: launched {role_id}" if not sync else f"dispatch_role: ok ({role_id})"


def run_mechanical_repairs(*, log_fn: Callable[[str], None]) -> list[str]:
    """Cheap fixes before agent dispatch."""
    results: list[str] = []
    if bool(_cfg().get("dedupe_queue_on_fail", True)):
        line = dedupe_queue()
        results.append(line)
        if "removed" in line:
            log_fn(f"autonomous repair: {line}")
    if bool(_cfg().get("clear_test_cache_on_fail", True)):
        line = clear_test_cache()
        results.append(line)
        log_fn(f"autonomous repair: {line}")
    if bool(_cfg().get("heal_git_identity", True)):
        line = heal_git_identity()
        results.append(line)
        if "set" in line or "FAIL" in line:
            log_fn(f"autonomous repair: {line}")
    return results


def repair_verify_failure(
    *,
    log_fn: Callable[[str], None],
    state: dict[str, Any] | None = None,
    paid_api: bool = False,
    failure_type: str | None = None,
    evidence: str | None = None,
) -> bool:
    """Mechanical repair + optional Verify Runner dispatch. Returns True if repair attempted."""
    if not enabled():
        return False
    if _on_cooldown("verify_fail"):
        log_fn("autonomous repair: verify_fail on cooldown")
        return False

    _mark("verify_fail")
    log_fn("autonomous repair: verify gate failed — self-fixing (no human)")

    run_mechanical_repairs(log_fn=log_fn)

    try:
        import run_peer_tasks as rpt

        failures, ft, retries = rpt.run_verify_gate(log_fn=log_fn)
        if failures == 0:
            log_fn("autonomous repair: verify green after mechanical repair")
            if state is not None:
                lc = state.get("last_cycle")
                if isinstance(lc, dict):
                    lc["verify_ok"] = True
                    lc["failure_type"] = None
                    lc["note"] = (str(lc.get("note") or "") + "; autonomous_repair").strip("; ")
                import peer_transcript as transcript

                transcript.save_state(state)
            try:
                import peer_transcript as pt

                pt.poke_turn_signal()
            except Exception:  # noqa: BLE001
                pass
            return True
        log_fn(
            f"autonomous repair: verify still failing ({failures}, {ft or failure_type}, retries={retries})"
        )
    except Exception as exc:  # noqa: BLE001
        log_fn(f"autonomous repair: verify retry failed ({exc})")

    if not bool(_cfg().get("dispatch_on_verify_fail", True)):
        return True

    detail = evidence or failure_type or "verify_ok=false"
    item = (
        f"**[auto-repair] Fix verify gate** — {detail[:160]}. "
        "Run self-check + quick tests; minimal diff; do not wait for human."
    )
    result = dispatch_role(
        "verify_runner",
        item=item,
        log_fn=log_fn,
        paid_api=paid_api,
        sync=False,
    )
    log_fn(f"autonomous repair: {result}")
    try:
        import peer_transcript as pt

        pt.poke_turn_signal()
    except Exception:  # noqa: BLE001
        pass
    return True


def repair_queue_spam(*, log_fn: Callable[[str], None]) -> bool:
    if not enabled():
        return False
    removed = auto.dedupe_work_queue_files(write=True)
    if removed:
        log_fn(f"autonomous repair: deduped {removed} queue line(s)")
        return True
    return False
