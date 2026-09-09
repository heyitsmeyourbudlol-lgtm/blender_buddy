#!/usr/bin/env python3
"""Stall pivot — when blocked >N seconds, ask what else can I do?

While primary progress waits (dirty tree, noop backoff, verify cooldown, git wait),
switch focus to small disjoint kit improvements, then resume main queue when unblocked.

Usage:
  python3 scripts/peer_stall_pivot.py --preview
  python3 scripts/peer_stall_pivot.py --preview --reason noop_backoff
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import automation_config as cfg_mod  # noqa: E402
import peer_transcript as transcript  # noqa: E402
import project_automation as auto  # noqa: E402

# Same-tick skip: continuous already ran emit/close/prepare; stall must not
# re-enter all three within ~wake TTL (probed stall no-audit ~396ms).
# OVERSEER_SAME_TICK_STALL_2026_09_03
KIT_REFRESH_TTL_SEC = 60.0
CONTINUUM_KIT_TS = auto.CONFIG_DIR / "continuum-kit-refresh.ts"

REASON_LABELS: dict[str, str] = {
    "git_clean_wait": "waiting for clean git tree",
    "dirty_tree": "dirty tree (continue_on_dirty off)",
    "noop_backoff": "noop backoff (same queue fingerprint)",
    "verify_cooldown": "local verify cooldown",
    "event_wait": "event wait with open queue",
    "verify_fail_hold": "verify failed — holding primary dispatch",
    "plan_gate_blocked": "plan-gate hard fail — adapting / pivoting",
    "agent_error": "cursor-agent non-zero exit",
    "auth_failed": "cursor-agent auth failed",
}

# Skip queue lines that match the blocker (pivot should work on something else).
_BLOCKER_SKIP: dict[str, tuple[str, ...]] = {
    "git_clean_wait": ("dirty tree", "dirty-tree", "commit", "stash", "git not clean", "unblock dirty"),
    "dirty_tree": ("dirty tree", "dirty-tree", "commit", "stash", "unblock dirty"),
    "noop_backoff": (),
    "verify_cooldown": (),
    "event_wait": (),
    "verify_fail_hold": (),
    "plan_gate_blocked": ("plan-gate", "plan gate"),
    "agent_error": (),
    "auth_failed": ("auth", "login", "cursor-agent"),
}

_PIVOT_PREFER: tuple[str, ...] = (
    "adapt",
    "audit",
    "playbook",
    "self-heal",
    "heal",
    "test",
    "worktree",
    "verify",
    "self-check",
    "noop",
    "daemon",
    "factory",
    "shorten",
    "cache",
    "mcp",
    "orchestr",
    "improve",
    "research",
    "external proof",
    "forge",
    "product",
)


def stall_pivot_enabled() -> bool:
    return bool(cfg_mod.CFG.get("stall_pivot_enabled", True))


def stall_pivot_sec() -> float:
    try:
        return max(0.5, float(cfg_mod.CFG.get("stall_pivot_sec", 3)))
    except (TypeError, ValueError):
        return 3.0


def stall_pivot_agent_cooldown_sec() -> float:
    try:
        return max(stall_pivot_sec(), float(cfg_mod.CFG.get("stall_pivot_agent_cooldown_sec", 90)))
    except (TypeError, ValueError):
        return 90.0


def note_stall(state: dict[str, Any], reason: str) -> dict[str, Any]:
    """Mark stall start time when reason unchanged; reset timer on reason change."""
    if state.get("stall_reason") != reason:
        state["stall_reason"] = reason
        state["stall_since_ts"] = time.time()
    elif "stall_since_ts" not in state:
        state["stall_since_ts"] = time.time()
    return state


def clear_stall(state: dict[str, Any]) -> dict[str, Any]:
    state.pop("stall_reason", None)
    state.pop("stall_since_ts", None)
    state.pop("stall_pivot_active", None)
    return state


def stall_elapsed(state: dict[str, Any]) -> float:
    since = float(state.get("stall_since_ts") or 0)
    if not since:
        return 0.0
    return max(0.0, time.time() - since)


def ready_to_pivot(state: dict[str, Any]) -> bool:
    if not stall_pivot_enabled():
        return False
    reason = str(state.get("stall_reason") or "")
    if not reason:
        return False
    return stall_elapsed(state) >= stall_pivot_sec()


def _item_blocked(item: str, reason: str) -> bool:
    low = item.lower()
    for token in _BLOCKER_SKIP.get(reason, ()):
        if token in low:
            return True
    return False


def _item_score(item: str, reason: str) -> int:
    if _item_blocked(item, reason):
        return -100
    low = item.lower()
    return sum(1 for p in _PIVOT_PREFER if p in low)


def alternate_items(reason: str, *, limit: int = 3) -> list[str]:
    """Pick disjoint improvements while primary progress is blocked."""
    queue = auto.open_work_items()
    items = list(queue.open_items)
    ranked = sorted(items, key=lambda i: _item_score(i, reason), reverse=True)
    alts = [i for i in ranked if _item_score(i, reason) >= 0][:limit]
    if len(alts) < limit:
        try:
            creative = auto.creative_backlog_items(auto.load_context_md())
        except Exception:  # noqa: BLE001
            creative = []
        for c in creative:
            if c not in alts and not _item_blocked(c, reason):
                alts.append(c)
            if len(alts) >= limit:
                break
    if not alts:
        alts = [
            "Run ./scripts/peer adapt — heal profiles after git churn",
            "Add or extend tests for peer_loop / stall_pivot / verify hot paths",
            "Shrink queue: demote strategy theater; keep factory-shaped items only",
        ][:limit]
    return alts[:limit]


def pivot_prompt_prefix(reason: str, alternates: list[str], elapsed: float) -> str:
    """Inject at top of agent prompt during stall pivot."""
    label = REASON_LABELS.get(reason, reason.replace("_", " "))
    alt_lines = "\n".join(f"- {a}" for a in alternates)
    return (
        "## Stall pivot — what else can I do?\n\n"
        f"Primary progress is **waiting** ({label}, {elapsed:.0f}s). "
        "The harness will resume the main queue automatically when unblocked.\n\n"
        "**This pivot:** pick **one** small, disjoint improvement from the list below. "
        "Land a real diff (tests pass). Then stop — do not re-plan the blocked primary work.\n\n"
        f"Alternates:\n{alt_lines}\n"
    )


def build_pivot_prompt(*, quick: bool, reason: str) -> str:
    """Focused pivot prompt for cursor-agent during stall."""
    state = transcript.load_state()
    elapsed = stall_elapsed(state)
    alternates = alternate_items(reason)
    prefix = pivot_prompt_prefix(reason, alternates, elapsed)
    rules = auto.extract_rules(auto.load_context_md())
    rules_short = "; ".join(rules[:3]) if rules else "minimal diff; tests must pass"
    alt_body = "\n".join(f"1. {a}" for a in alternates[:2])
    return (
        f"{prefix}\n"
        f"Constraints: {rules_short}.\n\n"
        f"Implement exactly one alternate now:\n{alt_body}\n"
    ).strip()


def agent_pivot_cooldown_remaining(state: dict[str, Any]) -> float:
    last = float(state.get("last_pivot_agent_ts") or 0)
    if not last:
        return 0.0
    return max(0.0, stall_pivot_agent_cooldown_sec() - (time.time() - last))


def mark_agent_pivot(state: dict[str, Any]) -> dict[str, Any]:
    state["last_pivot_agent_ts"] = time.time()
    state["stall_pivot_active"] = True
    return state


STALL_ADAPT_AUDIT_TTL_SEC = 60.0


def _adapt_audit_age_sec(root: Path | None = None) -> float:
    """Seconds since adapt-audit.json mtime; inf if missing."""
    try:
        import automation_adapt as adapt

        path = adapt.adapt_state_path(root or ROOT).parent / "adapt-audit.json"
        if not path.is_file():
            return float("inf")
        return max(0.0, time.time() - path.stat().st_mtime)
    except Exception:  # noqa: BLE001
        return float("inf")


def _maybe_stall_adapt_audit(*, log_fn: Callable[[str], None]) -> None:
    """TTL-skip expensive ``adapt --audit`` subprocess on stall pivot.

    Fresh audit (< TTL): in-process ``detect_signals(quick)`` only.
    Stale/missing: shell ``automation_adapt.py --audit`` (90s timeout).
    """
    import subprocess

    import automation_adapt as adapt

    if adapt.should_re_adapt(ROOT):
        return
    age = _adapt_audit_age_sec(ROOT)
    if age < STALL_ADAPT_AUDIT_TTL_SEC:
        adapt.detect_signals(ROOT, quick=True)
        log_fn(
            f"stall pivot: adapt audit TTL-skip (age={age:.0f}s < "
            f"{STALL_ADAPT_AUDIT_TTL_SEC:.0f}s) — in-process quick signals"
        )
        return
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "automation_adapt.py"), "--audit"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=90.0,
        check=False,
    )
    if proc.returncode != 0:
        log_fn("stall pivot: adapt audit found issues (see output)")
    else:
        log_fn("stall pivot: adapt audit ok")


def mark_continuum_kit_refresh() -> None:
    """Stamp after continuous emit/close/prepare so stall can same-tick skip."""
    try:
        CONTINUUM_KIT_TS.parent.mkdir(parents=True, exist_ok=True)
        CONTINUUM_KIT_TS.write_text(f"{time.time():.3f}\n", encoding="utf-8")
    except OSError:
        pass


def continuum_kit_fresh(*, ttl_sec: float | None = None) -> bool:
    """True when continuum kit refresh ran within TTL (skip stall re-entry)."""
    ttl = KIT_REFRESH_TTL_SEC if ttl_sec is None else float(ttl_sec)
    if not CONTINUUM_KIT_TS.is_file():
        return False
    try:
        age = time.time() - float(CONTINUUM_KIT_TS.read_text(encoding="utf-8").strip())
        return 0.0 <= age < ttl
    except (OSError, ValueError, TypeError):
        return False


def run_local_pivot_work(*, quick: bool, log_fn: Callable[[str], None]) -> bool:
    """Refresh prompts / adapt / close ASI plans — no LLM required."""
    import peer_loop as pl  # noqa: E402 — runtime only (avoid import cycle at load)

    log_fn("stall pivot: what else can I do — local kit improvements")
    if continuum_kit_fresh():
        log_fn("stall pivot: skip emit/close/prepare — continuum kit fresh")
    else:
        pl._emit_worktree_inventory(log_fn)
        pl._close_completed_asi_phase_plans(log_fn)
        pl._prepare_continuous_prompts(quick=quick, log_fn=log_fn)
        mark_continuum_kit_refresh()
    pl._maybe_adapt(log_fn)
    try:
        _maybe_stall_adapt_audit(log_fn=log_fn)
    except Exception as exc:  # noqa: BLE001
        log_fn(f"stall pivot: audit skipped ({exc})")
    return True


def maybe_pivot(
    *,
    state: dict[str, Any],
    reason: str,
    quick: bool,
    log_fn: Callable[[str], None],
    live: auto.LiveState | None = None,
    use_agent: bool = False,
    paid_api: bool = False,
) -> bool:
    """If stalled long enough, pivot to alternate improvements. Returns True if work ran."""
    state = note_stall(state, reason)
    if not ready_to_pivot(state):
        transcript.save_state(state)
        return False

    elapsed = stall_elapsed(state)
    alternates = alternate_items(reason)
    log_fn(
        f"stall pivot: blocked {elapsed:.0f}s on {reason} — "
        f"what else can I do? ({len(alternates)} alternate(s))"
    )
    for alt in alternates[:2]:
        log_fn(f"stall pivot: alt — {alt[:100]}")

    run_local_pivot_work(quick=quick, log_fn=log_fn)

    agent_left = agent_pivot_cooldown_remaining(state)
    if use_agent and agent_left <= 0:
        import peer_loop as pl
        import peer_worktree as pwt

        live = live or auto.measure_live_state(quick=True)
        work_cwd, isolated = pl._resolve_coding_cwd(live, log_fn)
        text = build_pivot_prompt(quick=quick, reason=reason)
        log_fn(
            "stall pivot: cursor-agent on alternate work"
            + (f" · cwd={work_cwd}" if isolated else "")
        )
        rc, auth_failed = pl.dispatch_prompt_text(
            text,
            mode="background",
            clipboard_only=False,
            press_enter=False,
            log_fn=log_fn,
            cwd=work_cwd,
            paid_api=paid_api,
        )
        mark_agent_pivot(state)
        if rc != 0 and auth_failed:
            log_fn("stall pivot: agent auth failed — local pivot only")
        elif rc != 0:
            log_fn(f"stall pivot: agent exit {rc} — local pivot only")
        else:
            log_fn("stall pivot: agent cycle finished — resume primary when unblocked")
    elif use_agent and agent_left > 0:
        log_fn(f"stall pivot: agent cooldown {agent_left:.0f}s — local pivot only")

    transcript.save_state(state)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview stall-pivot alternates")
    parser.add_argument("--reason", default="noop_backoff", help="Stall reason key")
    parser.add_argument("--preview", action="store_true", help="Print pivot prompt preview")
    args = parser.parse_args()
    reason = args.reason
    if args.preview:
        print(build_pivot_prompt(quick=True, reason=reason))
        return 0
    alts = alternate_items(reason)
    print(f"reason={reason} enabled={stall_pivot_enabled()} threshold={stall_pivot_sec()}s")
    for a in alts:
        print(f"- {a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
