#!/usr/bin/env python3
"""Error adapt — recover from gate/agent failures so the loop never idles.

When plan-gate blocks or cursor-agent exits non-zero, mechanically heal what we
can, consult the playbook, pivot to alternate work, and wake peer/improve.
Hard safety fails (secrets) stay blocking; soft/recoverable fails become warn.
# OVERSEER_LAND_2026_09_03 — hub-protect needle: soften clears only still_hard
# OVERSEER_AUTH_HOLD_2026_09_03 — hub-protect needle: auth-hold skips clear_autonomy

Usage:
  python3 scripts/peer_error_adapt.py --from-gate
  python3 scripts/peer_error_adapt.py --agent-exit 1 --note "cursor-agent non-zero"
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

# Gaps we can usually clear without human; stay soft after heal attempt.
# Self-correction softens after heal so verify_ok=false never forever-blocks primary.
_RECOVERABLE_GAPS = frozenset(
    {
        "Institutional memory",
        "Parallel cognition",
        "Time awareness",
        "Long-term memory",
        "Episodic recall",
        "Self-correction",
    }
)

_HARD_GAPS = frozenset(
    {
        "Secret hygiene",
    }
)


def never_delay_on_error() -> bool:
    """Errors must accelerate recovery — never pause peer/improve/oversight."""
    if "autonomy_never_delay_on_error" in auto.CFG:
        return bool(auto.CFG.get("autonomy_never_delay_on_error"))
    return True


def _is_auth_hold_text(text: str) -> bool:
    """Human-only auth stalls — clearing delays only spam-wakes the loop."""
    blob = (text or "").lower()
    needles = (
        "auth not ready",
        "auth_failed",
        "cursor-agent auth",
        "cursor auth not ready",
        "cursor_agent_auth",
        "run cursor-agent login",
    )
    return any(n in blob for n in needles)


def _load_loop_state_lite() -> dict[str, Any]:
    """Read peer-loop-state.json without importing peer_transcript.

    Needle: CLEAR_DELAYS_LITE_STATE_NO_TX_IMPORT_2026_09_08 — clear_autonomy_delays
    was cold-importing transcript (~13ms) solely to JSON-load state; save still
    goes through transcript.save_state when mutations occur (flock + scrub).
    """
    path = auto.CONFIG_DIR / "peer-loop-state.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def clear_autonomy_delays(
    *,
    log_fn: Callable[[str], None] | None = None,
    reason: str = "error",
) -> list[str]:
    """Clear verify cooldown / stalls so hard errors never idle the factory.

    OVERSEER_CLEAR_DELAYS_KEEP_NOOP_2026_09_07 — do **not** clear ``last_cycle.noop``
    unless reason is ``noop-mislabel`` (queue_fp advanced). Clearing noop on every
    verify-fail-bypass / live-log hit defeated stall_pivot_noop_backoff and caused
    continuous re-dispatch on a flat fingerprint.

    Needle: CLEAR_DELAYS_LITE_STATE_NO_TX_IMPORT_2026_09_08 — lite JSON load; import
    peer_transcript only when save_state is required.
    """
    if not never_delay_on_error():
        return []
    # Auth is human-only (playbook). Clearing delays on auth hits creates the
    # "auth not ready — cleared autonomy delays" wake thrash that stalls factory %.
    if _is_auth_hold_text(reason):
        _log(log_fn, f"error-adapt: auth-hold — skip clear delays ({reason[:60]})")
        return ["auth-hold"]
    actions: list[str] = []
    try:
        state = _load_loop_state_lite()
        changed = False
        lc = state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else None
        reason_l = (reason or "").lower()
        allow_noop_clear = reason_l.startswith("noop-mislabel") or reason_l == "noop-mislabel"
        if isinstance(lc, dict) and lc.get("noop") and allow_noop_clear:
            lc["noop"] = False
            lc["noop_cleared_for_error"] = True
            lc["delay_clear_reason"] = reason[:80]
            state["last_cycle"] = lc
            changed = True
            actions.append("noop-cleared")
        # Age out local verify cooldown immediately.
        if float(state.get("last_local_verify_ts") or 0) > 0:
            state["last_local_verify_ts"] = 0.0
            changed = True
            actions.append("verify-cooldown-cleared")
        # Clear stall timers that hold primary dispatch.
        for key in ("stall_reason", "stall_since_ts", "stall_pivot_active"):
            if key in state:
                state.pop(key, None)
                changed = True
        if changed:
            import peer_transcript as transcript

            transcript.save_state(state)
            _log(log_fn, f"error-adapt: cleared autonomy delays ({reason[:60]})")
    except Exception as exc:  # noqa: BLE001
        _log(log_fn, f"error-adapt: clear delays ({exc})")
    _wake_loops(log_fn=log_fn)
    if actions:
        actions.append("woken")
    return actions


def _log(log_fn: Callable[[str], None] | None, msg: str) -> None:
    if log_fn:
        log_fn(msg)


def heal_recoverable_gate_fails(
    report: Any,
    *,
    log_fn: Callable[[str], None] | None = None,
) -> list[str]:
    """Run mechanical heals for known plan-gate fail rows. Returns action labels."""
    actions: list[str] = []
    fails = [r for r in getattr(report, "results", []) if getattr(r, "status", "") == "fail"]
    if not fails:
        return actions

    gaps = {str(getattr(r, "gap", "") or "") for r in fails}

    if "Institutional memory" in gaps:
        try:
            import automation_adapt as adapt

            healed, _warns = adapt.heal_queue_drift(root=ROOT, write=True)
            actions.append(f"sync-queue:{len(healed)}")
            _log(log_fn, f"error-adapt: sync-queue healed={len(healed)}")
        except Exception as exc:  # noqa: BLE001
            _log(log_fn, f"error-adapt: sync-queue ({exc})")

    if "Long-term memory" in gaps:
        try:
            import peer_team_context as tc

            tc.write_team_context()
            actions.append("team-context")
            _log(log_fn, "error-adapt: team-context refreshed")
        except Exception as exc:  # noqa: BLE001
            _log(log_fn, f"error-adapt: team-context ({exc})")

    if "Parallel cognition" in gaps:
        try:
            import peer_worktree as wt

            ensure = getattr(wt, "ensure_parallel_pool", None)
            if callable(ensure):
                ensure(log_fn=log_fn or (lambda _m: None))
                actions.append("worktree-pool")
                _log(log_fn, "error-adapt: worktree pool ensured")
        except Exception as exc:  # noqa: BLE001
            _log(log_fn, f"error-adapt: worktree pool ({exc})")

    if "Time awareness" in gaps or "Episodic recall" in gaps or "Self-correction" in gaps:
        try:
            import automation_adapt as adapt

            if adapt.should_re_adapt(ROOT):
                adapt.run_heal_fresh(write=True, quick=True)
                adapt.sync_git_fingerprint(ROOT)
                actions.append("adapt-heal")
                _log(log_fn, "error-adapt: adapt heal for stale fingerprint")
        except Exception as exc:  # noqa: BLE001
            _log(log_fn, f"error-adapt: adapt heal ({exc})")
        try:
            import peer_self_heal as sh

            if sh.self_heal_enabled():
                report_h = sh.run_cycle(write=True, log_fn=log_fn or (lambda _m: None))
                actions.append(f"self-heal:{len(report_h.actions)}")
        except Exception as exc:  # noqa: BLE001
            _log(log_fn, f"error-adapt: self-heal ({exc})")

    # Playbook instant fixes for each fail detail.
    try:
        import peer_playbook as playbook

        for r in fails:
            detail = f"{getattr(r, 'gap', '')}: {getattr(r, 'detail', '')}"
            playbook.record_observation(
                detail[:200],
                source="error-adapt-gate",
                severity="high" if str(getattr(r, "gap", "")) in _HARD_GAPS else "medium",
            )
            hits = playbook.match_many([detail], limit=2)
            if hits:
                actions.append(f"playbook:{getattr(hits[0], 'id', 'hit')}")
                _log(log_fn, f"error-adapt: playbook → {getattr(hits[0], 'id', '?')}")
                cmds = list(getattr(hits[0], "mechanical_fix", None) or [])[:2]
                for cmd in cmds:
                    _try_playbook_command(str(cmd), log_fn=log_fn, actions=actions)
    except Exception as exc:  # noqa: BLE001
        _log(log_fn, f"error-adapt: playbook ({exc})")

    return actions


# OVERSEER_ERROR_ADAPT_NO_NESTED_VERIFY_2026_09_07 — heal-all includes
# verify-gate; nesting it under error-adapt (plan-gate / agent-fail recovery)
# hits the old flat 120s TimeoutExpired and stamps stagnation
# "peer heal-all timed out after 120" forever. Expand to mechanical heal
# without verify (verify runs on its own gate path).
_NEST_SAFE_EXPAND: dict[str, tuple[str, ...]] = {
    "heal-all": ("self-heal", "compact-queue", "sync-queue"),
    "stagnation-break": ("self-heal", "compact-queue", "sync-queue", "noop-break"),
}
_PEER_CMD_TIMEOUT_SEC: dict[str, float] = {
    "verify-gate": 480.0,
    "autonomous-repair": 300.0,
    "pre-dispatch": 180.0,
    "adapt": 180.0,
}
_DEFAULT_PEER_CMD_TIMEOUT_SEC = 120.0


def _playbook_verbs(verb: str) -> tuple[str, ...]:
    """Map heavy compounds to nest-safe verbs (no nested verify-gate)."""
    return _NEST_SAFE_EXPAND.get(verb, (verb,))


def _try_playbook_command(
    cmd: str,
    *,
    log_fn: Callable[[str], None] | None,
    actions: list[str],
) -> None:
    """Run safe peer compound commands from playbook (no shell metachar spam)."""
    raw = cmd.strip()
    if not raw.startswith("./scripts/peer"):
        return
    # Only allow known heal/dispatch compounds — never arbitrary shell.
    allow = (
        "sync-queue",
        "compact-queue",
        "self-heal",
        "noop-break",
        "poke",
        "heal-all",
        "stagnation-break",
        "pre-dispatch",
        "verify-gate",
        "adapt",
        "autonomous-repair",
    )
    parts = raw.split()
    if len(parts) < 2:
        return
    verb = parts[1]
    if verb not in allow:
        return
    peer_bin = SCRIPTS / "peer"
    extra = parts[2:]
    for run_verb in _playbook_verbs(verb):
        timeout = float(
            _PEER_CMD_TIMEOUT_SEC.get(run_verb, _DEFAULT_PEER_CMD_TIMEOUT_SEC)
        )
        try:
            proc = subprocess.run(
                [str(peer_bin), run_verb, *extra],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            label = f"cmd:{run_verb}:{proc.returncode}"
            if run_verb != verb:
                label = f"cmd:{verb}->{run_verb}:{proc.returncode}"
            actions.append(label)
            _log(log_fn, f"error-adapt: ran peer {run_verb} rc={proc.returncode}")
        except Exception as exc:  # noqa: BLE001
            _log(log_fn, f"error-adapt: cmd failed ({exc})")


def soften_recoverable_fails(report: Any) -> int:
    """Downgrade recoverable fail → warn after heal attempt (keep secrets hard)."""
    softened = 0
    for r in getattr(report, "results", []):
        if getattr(r, "status", "") != "fail":
            continue
        gap = str(getattr(r, "gap", "") or "")
        if gap in _HARD_GAPS:
            continue
        if gap in _RECOVERABLE_GAPS:
            r.status = "warn"
            detail = str(getattr(r, "detail", "") or "")
            r.detail = f"adapted: {detail}"[:160]
            softened += 1
    return softened


def adapt_plan_gate(
    report: Any,
    *,
    log_fn: Callable[[str], None] | None = None,
    state: dict[str, Any] | None = None,
    use_agent: bool = True,
    paid_api: bool = False,
    quick: bool = True,
) -> tuple[bool, list[str]]:
    """Heal + soft recoverable fails + stall-pivot. Returns (still_blocked, actions)."""
    actions = heal_recoverable_gate_fails(report, log_fn=log_fn)

    # Re-run gate after heals.
    try:
        import peer_agent_gates as gates

        report2 = gates.run_plan_gate(role_id=getattr(report, "role_id", "") or "orchestrator", refresh=True, quick=quick)
    except Exception as exc:  # noqa: BLE001
        _log(log_fn, f"error-adapt: re-gate ({exc})")
        report2 = report

    # Soften after re-gate; still = remaining hard fails only (still_hard).
    # Never clear_autonomy on stale report.blocked when soften unblocked.
    # OVERSEER_GATE_SOFTENED_2026_09_03
    n = 0
    if getattr(report2, "blocked", False):
        n = soften_recoverable_fails(report2)
        if n:
            actions.append(f"soften:{n}")
            _log(log_fn, f"error-adapt: softened {n} recoverable fail(s) → warn")

    results2 = getattr(report2, "results", None)
    if isinstance(results2, (list, tuple)):
        still_hard = any(getattr(r, "status", "") == "fail" for r in results2)
    else:
        still_hard = bool(getattr(report2, "blocked", False))
    still = still_hard
    if still:
        actions.extend(clear_autonomy_delays(log_fn=log_fn, reason="plan-gate"))
        hard = [
            r
            for r in getattr(report2, "results", [])
            if getattr(r, "status", "") == "fail"
        ]
        _log(
            log_fn,
            "error-adapt: hard block remains — "
            + "; ".join(f"{getattr(r, 'gap', '?')}" for r in hard[:3]),
        )
        # Never idle: pivot to alternate work while hard fails are fixed.
        try:
            import peer_stall_pivot as stall
            import peer_transcript as transcript

            st = state if state is not None else transcript.load_state()
            stall.maybe_pivot(
                state=st,
                reason="plan_gate_blocked",
                quick=quick,
                log_fn=log_fn or (lambda _m: None),
                use_agent=use_agent,
                paid_api=paid_api,
            )
            transcript.save_state(st)
            actions.append("stall-pivot")
        except Exception as exc:  # noqa: BLE001
            _log(log_fn, f"error-adapt: pivot ({exc})")
        _wake_loops(log_fn=log_fn)
    elif n:
        actions.append("gate-softened")
        _log(
            log_fn,
            "error-adapt: recoverable fails softened — dispatch may proceed; skip delay-clear",
        )
    else:
        actions.append("gate-clear")
        _log(log_fn, "error-adapt: plan-gate clear after adapt")

    return still, actions


def adapt_agent_failure(
    *,
    rc: int,
    note: str = "",
    log_fn: Callable[[str], None] | None = None,
    state: dict[str, Any] | None = None,
    auth_failed: bool = False,
    use_agent: bool = True,
    paid_api: bool = False,
    quick: bool = True,
) -> list[str]:
    """Respond to cursor-agent non-zero / auth fail — playbook + heal + pivot."""
    actions: list[str] = []
    blob = f"cursor-agent exit {rc}: {note or 'non-zero'}".strip()
    if auth_failed:
        blob = f"cursor-agent auth failed: {note or 'auth'}"
    # OVERSEER_AUTH_HOLD_2026_09_03 — never clear_autonomy on auth_failed.
    if not auth_failed:
        actions.extend(clear_autonomy_delays(log_fn=log_fn, reason=blob[:80]))

    try:
        import peer_playbook as playbook

        playbook.record_observation(
            blob[:200],
            source="error-adapt-agent",
            severity="high" if auth_failed or rc not in (0, None) else "medium",
        )
        hits = playbook.match_many([blob], limit=2)
        if hits:
            actions.append(f"playbook:{getattr(hits[0], 'id', 'hit')}")
            if not auth_failed:
                for cmd in list(getattr(hits[0], "mechanical_fix", None) or [])[:2]:
                    _try_playbook_command(str(cmd), log_fn=log_fn, actions=actions)
    except Exception as exc:  # noqa: BLE001
        _log(log_fn, f"error-adapt: agent playbook ({exc})")

    if auth_failed:
        actions.append("auth-hold")
        _log(log_fn, "error-adapt: auth-hold — human must run cursor-agent login")
        return actions

    try:
        import peer_self_heal as sh

        if sh.self_heal_enabled():
            report = sh.run_cycle(write=True, log_fn=log_fn or (lambda _m: None))
            actions.append(f"self-heal:{len(report.actions)}")
    except Exception as exc:  # noqa: BLE001
        _log(log_fn, f"error-adapt: agent self-heal ({exc})")

    reason = "agent_error"
    try:
        import peer_stall_pivot as stall
        import peer_transcript as transcript

        st = state if state is not None else transcript.load_state()
        stall.maybe_pivot(
            state=st,
            reason=reason,
            quick=quick,
            log_fn=log_fn or (lambda _m: None),
            use_agent=use_agent,
            paid_api=paid_api,
        )
        transcript.save_state(st)
        actions.append("stall-pivot")
    except Exception as exc:  # noqa: BLE001
        _log(log_fn, f"error-adapt: agent pivot ({exc})")

    _wake_loops(log_fn=log_fn)
    _log(log_fn, f"error-adapt: agent failure handled ({', '.join(actions[:4])})")
    return actions


def _wake_loops(*, log_fn: Callable[[str], None] | None) -> None:
    """Touch peer/improve wake signals without cold-importing automation_improve.

    Needle: CLEAR_DELAYS_WAKE_NO_COLD_IMPROVE_IMPORT_2026_09_08 — stacks with
    WAKE_PEER_NO_COLD_TEAM_TX_IMPORT; clear_autonomy_delays was still paying
    improve compile (~30ms) solely to touch peer-turn.signal.
    """
    _ = log_fn
    now = str(time.time())
    for name in ("peer-turn.signal", "improve-wake.signal"):
        try:
            sig = auto.CONFIG_DIR / name
            sig.parent.mkdir(parents=True, exist_ok=True)
            sig.write_text(now, encoding="utf-8")
        except OSError:
            pass


def ensure_driving(
    *,
    log_fn: Callable[[str], None] | None = None,
    quick: bool = True,
) -> dict[str, Any]:
    """Improve/peer heartbeat: if open work + idle/block signals, adapt and wake."""
    out: dict[str, Any] = {"actions": []}
    try:
        import peer_agent_gates as gates

        report = gates.run_plan_gate(role_id="orchestrator", refresh=False, quick=quick)
        if report.blocked:
            still, acts = adapt_plan_gate(report, log_fn=log_fn, quick=quick)
            out["actions"].extend(acts)
            out["still_blocked"] = still
            # Only clear delays when still hard-blocked after soften.
            if still:
                out["actions"].extend(
                    clear_autonomy_delays(log_fn=log_fn, reason="gate-blocked")
                )
            else:
                out["gate"] = "ok"
        else:
            out["gate"] = "ok"
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)[:120]
        _log(log_fn, f"error-adapt: ensure_driving ({exc})")
        out["actions"].extend(clear_autonomy_delays(log_fn=log_fn, reason=f"ensure:{exc}"))

    # Live log errors → clear delays immediately (never idle on ERROR lines).
    # Skip auth-only hits — playbook: human login; clear+wake thrash stalls factory.
    auth_hold = False
    try:
        import peer_oversight_events as oevents

        hits = oevents.scan_live_error_hits(max_age_sec=90.0)
        if hits:
            out["live_errors"] = hits[:3]
            if all(_is_auth_hold_text(h) for h in hits):
                auth_hold = True
                out["actions"].append("auth-hold")
                _log(log_fn, f"error-adapt: auth-hold live — {hits[0][:60]}")
            else:
                non_auth = next((h for h in hits if not _is_auth_hold_text(h)), hits[0])
                out["actions"].extend(
                    clear_autonomy_delays(log_fn=log_fn, reason=non_auth[:80])
                )
    except Exception:  # noqa: BLE001
        pass

    # Probe cursor-agent auth once — if not ready, do not thrash on verify_ok=False.
    if not auth_hold:
        try:
            import peer_terminal as terminal

            ready, detail = terminal.cursor_agent_auth_ready()
            if not ready:
                auth_hold = True
                out["actions"].append("auth-hold")
                _log(log_fn, f"error-adapt: auth-hold probe — {detail[:60]}")
        except Exception:  # noqa: BLE001
            pass

    # False-noop recovery — clear only when last_cycle.noop but queue fp
    # advanced (mislabel). Real fp-flat noop keeps backoff; clearing every
    # improve tick on noop/verify_ok=False defeats stall_pivot_noop_backoff.
    if not auth_hold:
        try:
            state_path = auto.CONFIG_DIR / "peer-loop-state.json"
            if state_path.is_file():
                data = json.loads(state_path.read_text(encoding="utf-8"))
                lc = data.get("last_cycle") if isinstance(data, dict) else None
                if isinstance(lc, dict) and lc.get("noop"):
                    fp_before = str(lc.get("queue_fp_before") or "")
                    fp_after = str(lc.get("queue_fp_after") or lc.get("queue_fp") or "")
                    if fp_before and fp_after and fp_before != fp_after:
                        cleared = clear_autonomy_delays(
                            log_fn=log_fn,
                            reason="noop-mislabel",
                        )
                        out["actions"].extend(cleared)
        except Exception:  # noqa: BLE001
            pass

    if not out.get("actions") and out.get("gate") == "ok":
        # Do not wake on every healthy tick — that feedback-loops oversight log watches.
        out["actions"].append("healthy")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Adapt to errors — never idle")
    parser.add_argument("--from-gate", action="store_true", help="Run plan-gate adapt")
    parser.add_argument("--agent-exit", type=int, default=None)
    parser.add_argument("--note", default="")
    parser.add_argument("--auth-failed", action="store_true")
    parser.add_argument("--ensure-driving", action="store_true")
    args = parser.parse_args()

    def log(msg: str) -> None:
        print(msg)

    if args.ensure_driving:
        print(json.dumps(ensure_driving(log_fn=log), indent=2))
        return 0
    if args.from_gate:
        import peer_agent_gates as gates

        report = gates.run_plan_gate(role_id="orchestrator", refresh=True, quick=True)
        still, acts = adapt_plan_gate(report, log_fn=log)
        print(json.dumps({"still_blocked": still, "actions": acts}, indent=2))
        return 1 if still else 0
    if args.agent_exit is not None:
        acts = adapt_agent_failure(
            rc=args.agent_exit,
            note=args.note,
            log_fn=log,
            auth_failed=args.auth_failed,
        )
        print(json.dumps({"actions": acts}, indent=2))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
