#!/usr/bin/env python3
"""Event-based stagnation detection for Cursor oversight dispatch."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import automation_config as cfg_mod
import project_automation as auto



@dataclass
class StagnationReport:
    stagnant: bool
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    should_dispatch: bool = False
    critical: bool = False


def _cfg() -> dict[str, Any]:
    raw = cfg_mod.CFG.get("oversight") or {}
    return raw if isinstance(raw, dict) else {}


def agent_dispatch_mode() -> str:
    raw = str(
        _cfg().get("agent_dispatch_mode")
        or cfg_mod.CFG.get("oversight_agent_dispatch_mode")
        or "event"
    ).strip().lower()
    return raw if raw in ("event", "interval") else "event"


def agent_min_interval_sec() -> float:
    try:
        val = _cfg().get("agent_min_interval_sec") or cfg_mod.CFG.get("oversight_agent_min_interval_sec") or 60
        floor = 15.0 if bool(_cfg().get("instant_react", cfg_mod.CFG.get("oversight_instant_react", True))) else 60.0
        return max(floor, float(val))
    except (TypeError, ValueError):
        return 60.0


def critical_agent_min_interval_sec() -> float:
    """Critical errors may re-dispatch overseer this often (instant react).

    When ``autonomy_never_delay_on_error`` is on, callers skip this gap entirely.
    """
    try:
        val = _cfg().get("critical_agent_min_interval_sec") or cfg_mod.CFG.get(
            "oversight_critical_agent_min_interval_sec"
        )
        if val is None:
            return 5.0
        return max(0.0, float(val))
    except (TypeError, ValueError):
        return 5.0


def agent_max_interval_sec() -> float:
    try:
        val = _cfg().get("agent_max_interval_sec")
        if val is None:
            val = cfg_mod.CFG.get("oversight_agent_max_interval_sec", 0)
        return max(0.0, float(val))
    except (TypeError, ValueError):
        return 0.0


def agent_interval_sec() -> float:
    try:
        val = _cfg().get("agent_interval_sec") or cfg_mod.CFG.get("oversight_agent_interval_sec") or 900
        return max(120.0, float(val))
    except (TypeError, ValueError):
        return 900.0


def stagnation_cycles_threshold() -> int:
    try:
        val = _cfg().get("stagnation_cycles") or cfg_mod.CFG.get("oversight_stagnation_cycles") or 2
        return max(1, int(val))
    except (TypeError, ValueError):
        return 2


def high_expectations_enabled() -> bool:
    if "high_expectations" in _cfg():
        return bool(_cfg()["high_expectations"])
    return bool(cfg_mod.CFG.get("oversight_high_expectations", True))




# OVERSEER_HEALTHY_IDLE_NO_DISPATCH_2026_09_04 — hub-protect timer/pause HIGH
# thrash must not score stagnation theater (same as factory meter skip).
_HUB_PROTECT_STAG_SKIP = frozenset(
    {"hub_protect_timer_stopped", "hub_protect_restore_paused"}
)


def _comparable_git_head(value: str | None) -> str:
    """OVERSEER_GIT_HEAD_SENTINEL_STAG_2026_09_04 — real SHA only.

    Overseer hand-out / soft-exit re-pins stamp ``git_head='overseer'`` (or
    truncated ``continue_on_dirty``). Those sentinels freeze
    "git HEAD unchanged while WORKING" forever under continue_on_dirty.
    """
    s = str(value or "").strip()
    if not s or s.startswith("("):
        return ""
    # Inline match — avoid fragile module-level regex constants under Mac clobber.
    m = re.match(r"^[0-9a-f]{7,40}", s, re.I)
    return (m.group(0) if m else "").lower()


def _coerce_factory_pct(raw: Any) -> float | None:
    """OVERSEER_HEALTHY_IDLE_LIVE_FACTORY_2026_09_04 — None/blank → None."""
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _live_factory_pct() -> float | None:
    """Best-effort live factory % when kit snapshot omitted it.

    OVERSEER_HEALTHY_IDLE_LIVE_FACTORY_2026_09_04 — thin kit (no factory_pct)
    used to leave healthy_idle False forever (flat/HEAD theater re-dispatch).
    Call compute_factory_progress (not missing compute_progress).
    """
    try:
        import factory_progress as fp

        prog = None
        # Prefer compute_report when patched in tests; else factory progress.
        if hasattr(fp, "compute_report"):
            try:
                prog = fp.compute_report()
            except Exception:
                prog = None
        if prog is None and hasattr(fp, "compute_factory_progress"):
            prog = fp.compute_factory_progress()
        pct = getattr(prog, "pct", None) if prog is not None else None
        if pct is None and isinstance(prog, dict):
            pct = prog.get("pct")
        if pct is not None:
            return float(pct)
    except Exception:  # noqa: BLE001
        return None
    return None


def _resolve_factory_pct(kit: dict[str, Any], snap: dict[str, Any] | None = None) -> float:
    """kit → snap → live factory_progress. Missing → -1 (not idle-green)."""
    raw = _coerce_factory_pct(kit.get("factory_pct"))
    if raw is None and snap is not None:
        raw = _coerce_factory_pct(snap.get("factory_pct"))
    if raw is None:
        raw = _live_factory_pct()
    return float(raw) if raw is not None else -1.0


def _verify_ok_for_idle(last: dict[str, Any]) -> bool:
    """True when last_cycle is green OR soft Episodic (not red verify).

    OVERSEER_HEALTHY_IDLE_SOFT_DEFERRED_2026_09_07 — soft deferred stamps
    verify_ok=False with failure_type=deferred (swarm/lock). Requiring
    verify_ok is True vetoed healthy_idle forever → flat-at-100% + cycles
    theater (score ~78) while Active was already empty. Matches ASI
    OVERSEER_ASI_DEFERRED_SOFT_VERIFY_2026_09_07 (deferred = not red).

    Poison pair (verify_ok=True + failure_type=deferred) is NOT idle-green.
    """
    if not isinstance(last, dict):
        return False
    ft = str(last.get("failure_type") or "").strip().lower()
    if last.get("verify_ok") is True:
        return ft != "deferred"
    if last.get("verify_ok") is False and _soft_cycle_failure(last):
        return True
    return False


def _healthy_idle_factory(ctx: dict[str, Any], snap: dict[str, Any], last: dict[str, Any]) -> bool:
    """OVERSEER_HEALTHY_IDLE_NO_FLAT_STAG_2026_09_04 — Active cleared + green.

    Flat factory/ASI + sentinel HEAD must not re-dispatch overseers when the
    factory is already idle-healthy (no Active work, verify ok).

    OVERSEER_HEALTHY_IDLE_SNAP_FACTORY_2026_09_04 — prefer kit.factory_pct but
    fall back to snap.factory_pct so a thin ctx (or mid-clobber kit) cannot
    leave healthy_idle False forever and rack stagnation_cycles into the 100s.

    OVERSEER_VAULT_HEALTHY_IDLE_2026_09_04 — vault_ok must require live resolve.
    OVERSEER_HEALTHY_IDLE_LIVE_FACTORY_2026_09_04 — when both kit+snap omit %,
    resolve via live factory_progress (thin-kit dispatch was score 64+ forever).

    OVERSEER_HEALTHY_IDLE_IGNORE_STALE_NOOP_2026_09_04 — last_cycle.noop must
    not veto idle (stale noop + empty Active was critical-dispatch forever).

    OVERSEER_CLEARED_ACTIVE_NO_FACTORY_GATE_2026_09_04 — do NOT require
    factory≥90. research_stale itself tanks self-sufficiency (88%) which then
    blocked idle demote → research_stale + flat + HEAD + cycles = score 144
    soft-dispatch storm while Active was already empty + verify_ok. Heal owns
    the research daemon; soft theater must not chicken-egg on the meter dip.

    OVERSEER_HEALTHY_IDLE_SOFT_DEFERRED_2026_09_07 — soft deferred verify_ok=False
    is idle-green (see _verify_ok_for_idle).
    """
    _ = ctx  # kit resolve retained for callers/tests; gate is Active+verify only
    return int(snap.get("queue_count") or 0) == 0 and _verify_ok_for_idle(last)


def _idle_green_pre_snap(ctx: dict[str, Any], last: dict[str, Any], *, active_n: int) -> bool:
    """Active cleared + verify ok — before metric_snapshot.

    OVERSEER_HEALTHY_IDLE_DEMOTE_NOOP_2026_09_04 — early noop / noop_backoff
    criticals must not fire when Active is already empty.

    OVERSEER_HEALTHY_IDLE_LIVE_FACTORY_2026_09_04 — thin kit must not skip demote.

    OVERSEER_CLEARED_ACTIVE_NO_FACTORY_GATE_2026_09_04 — no factory≥90 gate
    (research_stale → 88% must not re-arm noop/research critical theater).

    OVERSEER_HEALTHY_IDLE_SOFT_DEFERRED_2026_09_07 — soft deferred counts green.
    """
    _ = ctx  # kept for signature compatibility with callers/tests
    return active_n == 0 and _verify_ok_for_idle(last)


def _active_queue_metrics() -> tuple[str, int]:
    """Active/Phase fingerprint only — never context Remaining or Creative.

    OVERSEER_ACTIVE_ONLY_QUEUE_FP_2026_09_04 — when Active is cleared, loop_work_items
    falls through to perpetual Creative opens (Newdrop / registry / discover). That
    stable creative fingerprint fired "queue fingerprint unchanged N snapshots" and
    dispatched overseers on healthy idle. Stagnation metrics use Active-only.

    OVERSEER_PHASED_ONLY_STAG_FP_2026_09_04 — ``open_work_items`` also falls through
    to context Remaining (deferred Newdrop/registry theater) and froze queue_fp the
    same way. Parse ## Active / ## Phase only after close/promote Done orphans.
    """
    import peer_transcript as transcript

    work_md = auto.load_work_queue_md()
    if not work_md:
        return "", 0
    work_md, _ = auto.close_landed_done_orphans(work_md)
    promoted, _ = auto.promote_open_done_orphans(work_md)
    items = list(auto._parse_phased_work_items(promoted) or [])
    if not items:
        return "", 0
    return transcript.queue_fingerprint(items), len(items)


def metric_snapshot(ctx: dict[str, Any], flaws: dict[str, Any]) -> dict[str, Any]:
    kit = ctx.get("kit") or {}
    last = ctx.get("last_cycle") or {}
    ram = ctx.get("ram") or {}
    try:
        import peer_transcript as transcript

        fp, active_n = _active_queue_metrics()
        tstate = transcript.load_state()
        last_advance = float(tstate.get("last_queue_advance_ts") or 0)
    except Exception:  # noqa: BLE001
        fp = ""
        active_n = 0
        last_advance = 0.0
        if str(ctx.get("queue_source") or "") not in ("creative", "empty"):
            active_n = int(ctx.get("queue_count") or 0)
            fp = str(last.get("queue_fp") or "") if active_n else ""
    # OVERSEER_HEALTHY_IDLE_LIVE_FACTORY_2026_09_04 — persist resolved % so history
    # snapshots are not thin-None forever (flat-at theater + healthy_idle miss).
    factory_pct = _coerce_factory_pct(kit.get("factory_pct"))
    if factory_pct is None:
        factory_pct = _live_factory_pct()
    # OVERSEER_METRIC_SNAP_LIVE_GIT_HEAD_2026_09_08 — self-heal rehydrate / thin
    # last_cycle often omits git_head → empty snap history forever (HEAD-stall
    # signal blind + "unchanged while WORKING" false negatives). Prefer live
    # oneline when last lacks a comparable SHA.
    git_head = str(last.get("git_head") or "")
    if not _comparable_git_head(git_head):
        try:
            import peer_transcript as transcript

            live_head = str(transcript.git_head_oneline() or "")
            if _comparable_git_head(live_head):
                git_head = live_head
        except Exception:  # noqa: BLE001
            pass
    return {
        "ts": time.time(),
        "factory_pct": factory_pct,
        "asi_pct": kit.get("asi_pct"),
        "queue_count": active_n,
        "queue_fp": fp,
        "git_head": git_head,
        "verify_ok": last.get("verify_ok"),
        "noop": bool(last.get("noop")),
        "phase": str(ctx.get("phase") or ""),
        "open_flaws": int(flaws.get("open") or 0),
        "dispatch_allowed": ram.get("dispatch_allowed"),
        "last_queue_advance_ts": last_advance,
    }

def record_snapshot(state: dict[str, Any], snap: dict[str, Any]) -> dict[str, Any]:
    history: list[dict[str, Any]] = state.get("snapshots") or []
    if not isinstance(history, list):
        history = []
    history.append(snap)
    state["snapshots"] = history[-24:]
    return state


def _queue_drift_count() -> int:
    try:
        import automation_adapt as adapt

        _, warnings = adapt.heal_queue_drift(root=auto.ROOT, write=False)
        return len(warnings)
    except Exception:  # noqa: BLE001
        return 0


def _dual_brain_mismatch() -> bool:
    try:
        import peer_self_heal as sh

        collision_fn = getattr(sh, "dual_namespace_collision", None)
        if callable(collision_fn):
            collision = collision_fn() or {}
            if collision.get("peer") or collision.get("improve"):
                return True
        work = auto.WORK_QUEUE_PATH.read_text(encoding="utf-8") if auto.WORK_QUEUE_PATH.is_file() else ""
        ctx_md = auto.CONTEXT_PATH.read_text(encoding="utf-8") if auto.CONTEXT_PATH.is_file() else ""
        if not work or not ctx_md:
            return False
        # Phased/Active only — same as sync_queue_drift (Active-twin fallback).
        # Backlog opens are not dual-brain HIGH.
        w_items = auto._parse_phased_work_items(work)
        c_items = auto.context_queue_open_items(ctx_md)
        w_keys = {auto._normalize_queue_key(x) for x in w_items}
        c_keys = {auto._normalize_queue_key(x) for x in c_items}
        return w_keys != c_keys
    except OSError:
        return False


def _log_has_patterns(ctx: dict[str, Any], patterns: tuple[str, ...], *, min_count: int = 2) -> bool:
    lines = (ctx.get("peer_log_tail") or []) + (ctx.get("improve_log_tail") or [])
    return sum(1 for ln in lines if any(p in ln for p in patterns)) >= min_count


# Instant-react: single recent hit → critical overseer dispatch.
_INSTANT_ERROR_PATTERNS: tuple[str, ...] = (
    "plan-gate BLOCKED",
    "Traceback (most recent call last)",
    "verify gate FAIL",
    "verify: FAIL",
    " TimeoutExpired",
    "timed out after",
    "auth not ready",
    "daemon STOPPED",
    "skip primary — plan-gate",
    "cursor-agent non-zero",
    "cursor-agent exit ",
    "dispatch failed",
    "self-heal: failed",
    " ERROR ",
    ": ERROR",
)

# OVERSEER_AGENT_EXIT_SOFT_STAG_2026_09_04 — match peer_agent_gates soft types.
# Soft Episodic exits must NOT stamp critical "verify gate FAIL" / live-log fanout.
_SOFT_CYCLE_FAILURE_TYPES = frozenset(
    {
        "agent_exit_soft",
        "deferred",
        "timeout",
        "keep_working",
        "not_ready",
        "adapt_stale",
    }
)


def _line_age_sec(line: str) -> float | None:
    """Parse leading 'YYYY-MM-DD HH:MM:SS' stamp; None if absent."""
    if len(line) < 19:
        return None
    stamp = line[:19]
    try:
        from datetime import datetime

        ts = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").timestamp()
        return max(0.0, time.time() - ts)
    except ValueError:
        return None



def _auth_currently_ready() -> bool | None:
    """True/False when probe works; None if probe unavailable."""
    try:
        import peer_terminal as pt
        ready, _ = pt.cursor_agent_auth_ready()
        return bool(ready)
    except Exception:  # noqa: BLE001
        return None


def _skip_live_hit_line(ln: str, pat: str) -> bool:
    """Drop echo / stale-auth theater that nests instant-react forever.

    OVERSEER_LIVE_LOG_ECHO_2026_09_04
    OVERSEER_AGENT_EXIT_SOFT_STAG_2026_09_04 — soft Episodic agent exit ≠ red tests.
    OVERSEER_LIVE_SKIP_SIGKILL_EXIT_2026_09_04 — terminal exit -9/143 is storm-trim
    theater (peer_loop soft Episodic on rc<0); must not critical-dispatch overseers.
    OVERSEER_SKIP_LOCAL_CYCLE_TIMEOUT_2026_09_07 — improve parent TimeoutExpired while
    verify quiet-waits under swarm is theater; must not critical-dispatch / bypass cooldown.
    """
    low = (ln or "").lower()
    if "live log:" in low:
        return True
    if "cleared autonomy delays" in low and "auth not ready" in low:
        return True
    if "human-only live hit" in low:
        return True
    # mechanical local cycle TimeoutExpired under verify swarm ≠ critical
    if pat in ("timed out after", " TimeoutExpired") and "local cycle timed out" in low:
        return True
    # OVERSEER_SKIP_NESTED_HEAL_ALL_TIMEOUT_2026_09_07 — error-adapt used to
    # nest full heal-all (verify-gate) under a flat 120s timeout; residual log
    # lines must not critical-dispatch overseers after the nest-safe expand.
    if pat in ("timed out after", " TimeoutExpired") and "heal-all" in low and (
        "120.0" in low or "scripts/peer" in low
    ):
        return True
    if pat == "auth not ready":
        # OVERSEER_AUTH_LIVE_SOFT_2026_09_04 — desktop-ready skips auth stampede.
        try:
            import peer_terminal as pt

            desk_ok, _ = pt.desktop_auth_ready()
            if desk_ok:
                return True
        except Exception:  # noqa: BLE001
            pass
        ready = _auth_currently_ready()
        if ready is True:
            return True
        # Human-only auth-down: still surface in scan, but evaluate softens critical.
    # Soft Episodic / SIGKILL without red tests — playbook: keep working.
    if pat in ("cursor-agent non-zero", "cursor-agent exit "):
        if "soft episodic" in low or "agent_exit_soft" in low:
            return True
        # OVERSEER_HAND_OUT_AGENT_EXIT_ECHO_2026_09_04 — hand_out assignment echo ≠ fresh agent fail.
        if "hand_out:" in low or "←" in (ln or "") or "<-" in low:
            return True
        if "fix verify gate" in low and "unblock worker dispatch" in low:
            return True
        # OVERSEER_LIVE_SKIP_SIGKILL_EXIT_2026_09_04 — Progress Monitor trim ≠ red tests.
        if (
            "exit -9" in low
            or "exit 143" in low
            or "rc=-9" in low
            or "rc=143" in low
            or "sigkill" in low
        ):
            return True
        # Niche assignment echo: "ut: Verify Runner ← … cursor-agent non-zero"
        if re.search(r"\b(ut|niche)\s*:", low):
            return True
    return False

def _soft_cycle_failure(last: dict[str, Any] | None) -> str:
    """Return soft failure_type when last_cycle is Episodic-warn only; else ""."""
    if not isinstance(last, dict):
        return ""
    ft = str(last.get("failure_type") or "").strip().lower()
    if ft in _SOFT_CYCLE_FAILURE_TYPES:
        return ft
    note = str(last.get("note") or "").lower()
    if "soft episodic" in note or "agent_exit_soft" in note:
        return ft or "agent_exit_soft"
    return ""


def scan_live_error_hits(ctx: dict[str, Any] | None = None, *, max_age_sec: float = 90.0) -> list[str]:
    """Tail peer/improve logs for fresh error lines (instant react).

    Needle: SCAN_LIVE_ERROR_HITS_SEEK_TAIL_2026_09_08 — hub improve-loop.log
    ~61MB; ``path.read_text()+splitlines()[-100]`` paid ~221ms on every green
    verify_ok cooldown tick (``apply_mechanical``). Use ``auto.tail_text_lines``
    seek-from-EOF (~0.1ms) — same last-100 semantics without full-file decode.
    """
    hits: list[str] = []
    lines: list[str] = []
    if ctx:
        lines.extend(str(x) for x in (ctx.get("peer_log_tail") or []))
        lines.extend(str(x) for x in (ctx.get("improve_log_tail") or []))
    for name in ("peer-loop.log", "improve-loop.log", "oversight-loop.log", "product-forge.log"):
        path = auto.CONFIG_DIR / name
        if not path.is_file():
            continue
        try:
            lines.extend(auto.tail_text_lines(path, 100))
        except OSError:
            continue
    seen: set[str] = set()
    for ln in reversed(lines[-160:]):
        age = _line_age_sec(ln)
        if age is not None and age > max_age_sec:
            continue
        for pat in _INSTANT_ERROR_PATTERNS:
            if pat not in ln:
                continue
            if _skip_live_hit_line(ln, pat):
                continue
            key = f"{pat}:{ln[-80:]}"
            if key in seen:
                continue
            seen.add(key)
            hits.append(f"live log: {pat.strip()} — {ln.strip()[-90:]}")
            if len(hits) >= 6:
                return hits
            break
    return hits


def live_errors_critical(ctx: dict[str, Any] | None = None) -> bool:
    if "instant_react" in _cfg():
        enabled = bool(_cfg()["instant_react"])
    else:
        enabled = bool(cfg_mod.CFG.get("oversight_instant_react", True))
    if not enabled:
        return False
    return bool(scan_live_error_hits(ctx))


def evaluate_stagnation(
    ctx: dict[str, Any],
    flaws: dict[str, Any],
    *,
    state: dict[str, Any],
    extras: dict[str, Any] | None = None,
) -> StagnationReport:
    report = StagnationReport(stagnant=False)
    last = ctx.get("last_cycle") or {}
    kit = ctx.get("kit") or {}
    ram = ctx.get("ram") or {}
    extras = extras or {}
    history: list[dict[str, Any]] = state.get("snapshots") or []
    if not isinstance(history, list):
        history = []
    thresh = stagnation_cycles_threshold()

    def add(reason: str, points: int, *, critical: bool = False) -> None:
        report.reasons.append(reason)
        report.score += points
        report.stagnant = True
        if critical:
            report.critical = True

    soft_ft = _soft_cycle_failure(last if isinstance(last, dict) else None)
    tests_ok = kit.get("tests_ok")

    # Instant react: live log errors force critical overseer.
    # Soft agent-exit / green tests → demote cursor-agent non-zero theater.
    live_hits = scan_live_error_hits(ctx)
    if soft_ft or tests_ok is True:
        live_hits = [
            h
            for h in live_hits
            if "cursor-agent non-zero" not in h and "cursor-agent exit" not in h
        ]
    for hit in live_hits[:4]:
        # OVERSEER_AUTH_LIVE_SOFT_2026_09_04 — auth live hits never critical-stampede.
        # Desktop-ready → drop; auth-down → reason only (human login, not code fix).
        if "auth not ready" in hit:
            desk_ok = False
            try:
                import peer_terminal as pt

                desk_ok, _ = pt.desktop_auth_ready()
            except Exception:  # noqa: BLE001
                desk_ok = False
            if desk_ok or _auth_currently_ready() is True:
                continue
            add(hit, 40, critical=False)
            continue
        add(hit, 40, critical=True)

    qcount = int(ctx.get("queue_count") or 0)
    phase = str(ctx.get("phase") or "")
    # Prefer Active-only count early so Creative/Remaining cannot inflate idle theater.
    try:
        _early_fp, active_n_early = _active_queue_metrics()
    except Exception:  # noqa: BLE001
        _early_fp, active_n_early = "", qcount
    idle_green = _idle_green_pre_snap(
        ctx, last if isinstance(last, dict) else {}, active_n=active_n_early
    )

    if last.get("verify_ok") is False:
        if soft_ft:
            # OVERSEER_AGENT_EXIT_SOFT_STAG_2026_09_04 — soft Episodic warn only.
            # OVERSEER_HEALTHY_IDLE_SOFT_DEFERRED_2026_09_07 — demote on cleared Active
            # so soft deferred does not stack with flat-100% theater before idle gate.
            if idle_green:
                add(
                    f"soft cycle warn on cleared Active ({soft_ft}) — demote (healthy idle)",
                    4,
                )
            else:
                add(
                    f"soft cycle warn ({soft_ft}) — keep working unless tests red",
                    12,
                )
        else:
            add("verify gate FAIL", 50, critical=True)
    # OVERSEER_HEALTHY_IDLE_DEMOTE_NOOP_2026_09_04 — stale noop on empty Active
    # was critical forever and blocked _healthy_idle_factory (noop veto).
    if last.get("noop"):
        if idle_green:
            add("stale noop on cleared Active — demote (healthy idle)", 6)
        else:
            add("noop cycle — queue fingerprint unchanged after ok verify", 45, critical=True)
    if int(ctx.get("noop_backoff_sec") or 0) > 0:
        if idle_green:
            add(
                f"noop backoff on cleared Active ({int(ctx.get('noop_backoff_sec') or 0)}s) — demote",
                4,
            )
        else:
            add(
                f"noop backoff armed ({int(ctx.get('noop_backoff_sec') or 0)}s remaining)",
                38,
                critical=True,
            )
    if last.get("rc") not in (None, 0):
        if soft_ft:
            add(f"soft agent exit rc={last.get('rc')} ({soft_ft})", 8)
        else:
            add(f"last peer cycle exit rc={last.get('rc')}", 32)

    daemons = kit.get("daemons") or {}
    if daemons.get("peer_loop") is False:
        add("peer-loop daemon STOPPED", 42, critical=True)
    if daemons.get("improve_loop") is False:
        add("improve-loop daemon STOPPED", 38, critical=True)
    if not ctx.get("daemon_running", True):
        add("peer watch reports daemon not running", 40, critical=True)
    if phase == "STOPPED":
        add("peer phase STOPPED", 36, critical=True)

    if flaws.get("critical"):
        add(f"{flaws.get('critical')} critical repo flaw(s) from research", 40, critical=True)
    if any(b.get("severity") == "critical" for b in ctx.get("bottlenecks") or []):
        add("critical self-heal bottleneck(s)", 40, critical=True)
    if any(
        b.get("severity") == "high"
        and str(b.get("id") or "") not in _HUB_PROTECT_STAG_SKIP
        for b in ctx.get("bottlenecks") or []
    ):
        add("high-severity bottleneck(s) open", 18)

    new_flaws = int(extras.get("repo_research_new") or 0)
    if new_flaws >= 5:
        add(f"repo research found {new_flaws} new flaws this cycle", 28, critical=new_flaws >= 10)
    elif new_flaws >= 1:
        add(f"repo research: {new_flaws} new flaw(s)", 12)

    research_stale_sec = float(extras.get("repo_research_stale_sec") or 0)
    # OVERSEER_HEALTHY_IDLE_DEMOTE_RESEARCH_STALE_2026_09_04 — stale research is
    # a heal target (daemon_research_stopped), not soft-dispatch fuel on idle.
    if research_stale_sec > 1800:
        if idle_green:
            add(
                f"repo research aged ({research_stale_sec / 60:.0f}m) — demote (healthy idle)",
                4,
            )
        else:
            add(f"repo flaw research stale ({research_stale_sec / 60:.0f}m ago)", 22)

    if qcount > 30:
        add(f"queue severe bloat ({qcount} open)", 30)
    elif qcount > 20:
        add(f"queue bloat ({qcount} open)", 22)
    elif qcount > 12:
        add(f"queue above compact cap ({qcount} open)", 14)

    if _dual_brain_mismatch():
        add("WORK_QUEUE ↔ self_improve_context mismatch (dual-brain)", 30, critical=True)

    drift_n = kit.get("queue_drift")
    if isinstance(drift_n, int) and drift_n > 0:
        add(f"queue drift warnings ({drift_n})", 20)
    elif "queue_drift" not in kit and _queue_drift_count() > 0:
        add("queue drift detected", 20)

    if phase in ("IDLE", "WAITING") and active_n_early > 0:
        add(f"phase {phase} with {active_n_early} open items — factory idle", 24)
    if phase == "VERIFYING" and int(ctx.get("noop_backoff_sec") or 0) == 0:
        add("stuck in VERIFYING — check verify storm", 16)

    stall = str(ctx.get("stall_reason") or "").strip()
    # OVERSEER_STALE_NOOP_STALL_DEMOTE_2026_09_04 — expired noop_backoff stall
    # string must not critical-dispatch on healthy idle (Active cleared + green).
    if stall:
        if idle_green and "noop" in stall.lower():
            add(f"stale stall ({stall[:40]}) — demote (healthy idle)", 4)
        else:
            add(f"stall reason: {stall[:80]}", 26, critical="noop" in stall.lower())

    # OVERSEER_SEED_NOT_LOCAL_ONLY_2026_09_04 — self-heal seed/rehydrate stamps
    # are mechanical, not "prompt refresh without agent". Ignore those notes
    # even if a mid-clobber seed still carries local_only=True.
    if last.get("local_only"):
        _seed_note = str(last.get("note") or "").lower()
        if "self-heal seeded" not in _seed_note and "self-heal rehydrat" not in _seed_note:
            add("last cycle was local-only (no agent) — prompt refresh without progress", 14)

    failure_type = str(last.get("failure_type") or "").strip()
    if failure_type and not soft_ft:
        add(f"last failure_type: {failure_type[:60]}", 24)
    # soft_ft already scored above — do not double-count agent_exit_soft theater.

    if kit.get("tests_ok") is False:
        _td = str(kit.get("tests_detail") or "").strip()
        # OVERSEER_EMPTY_TESTS_FAIL_STAG_2026_09_04 — empty / "FAIL — failed" ≠ confirmed red.
        _td_l = _td.lower()
        if _td and _td_l not in {"tests: fail — failed", "tests: fail - failed", "failed"} and "fail — failed" not in _td_l:
            add(f"tests failing: {_td[:60]}", 35, critical=True)
    if kit.get("audit_ok") is False:
        add("adapt audit not ok", 28)

    if not ctx.get("auth_ready", True):
        # OVERSEER_AUTH_PAID_API_SOFT_2026_09_04 — KEY redirect ≠ auth-down theater.
        detail = str(ctx.get("auth_detail", "") or "")
        detail_l = detail.lower()
        if "cursor_api_key" in detail_l and ("--paid-api" in detail_l or "paid-api" in detail_l):
            pass
        else:
            add(f"cursor auth not ready: {detail[:50]}", 15)
    if not ctx.get("git_clean", True) and qcount > 0 and phase == "WAITING":
        add(f"dirty tree blocking dispatch: {str(ctx.get('git_detail', ''))[:50]}", 20)

    if ram.get("dispatch_allowed") is False:
        add(f"RAM dispatch blocked (used {ram.get('used_gb', '?')}GB)", 18)

    if _log_has_patterns(ctx, ("timed out", "TimeoutExpired", "unittest"), min_count=3):
        add("unittest/verify timeout storm in logs", 24)
    if _log_has_patterns(ctx, ("ERROR", "Traceback", "FAIL"), min_count=4):
        add("error storm in peer/improve logs", 20)

    snap = metric_snapshot(ctx, flaws)
    # Prefer Active-only count from snap (creative backlog must not inflate qcount).
    active_q = int(snap.get("queue_count") or 0)
    healthy_idle = _healthy_idle_factory(ctx, snap, last if isinstance(last, dict) else {})

    cur_fp = snap.get("queue_fp")
    # OVERSEER_ACTIVE_ONLY_QUEUE_FP_2026_09_04 — skip when Active idle (empty fp).
    # OVERSEER_HEALTHY_IDLE_GATE_QUEUE_FP_2026_09_04 — healthy idle must not
    # accumulate fingerprint theater from stale snapshot history either.
    if history and cur_fp and not healthy_idle:
        same_fp = sum(1 for h in history[-6:] if h.get("queue_fp") == cur_fp)
        if same_fp >= thresh:
            add(f"queue fingerprint unchanged {same_fp} snapshots", 30)

    if history:
        prev_q = [int(h.get("queue_count") or 0) for h in history[-4:] if "queue_count" in h]
        if prev_q and active_q > max(prev_q) + 3:
            add(f"queue grew {active_q - min(prev_q)} items since last snapshots", 18)

        prev_flaws = [int(h.get("open_flaws") or 0) for h in history[-4:]]
        if prev_flaws and snap.get("open_flaws", 0) > max(prev_flaws) + 5:
            add("repo flaw count rising — research finding regressions", 20)

    # OVERSEER_HEALTHY_IDLE_NO_FLAT_STAG_2026_09_04 — skip flat/HEAD theater on idle.
    if not healthy_idle:
        cur_factory = kit.get("factory_pct")
        if history and cur_factory is not None:
            prev = [h.get("factory_pct") for h in history[-5:] if h.get("factory_pct") is not None]
            if prev and all(cur_factory <= p for p in prev[-thresh:]):
                add(f"factory readiness flat at {cur_factory}%", 28)

        cur_asi = kit.get("asi_pct")
        if history and cur_asi is not None:
            prev = [h.get("asi_pct") for h in history[-5:] if h.get("asi_pct") is not None]
            if prev and all(cur_asi <= p for p in prev[-thresh:]):
                add(f"harness rubric flat at {cur_asi}%", 22)

        # OVERSEER_GIT_HEAD_SENTINEL_STAG_2026_09_04 — SHA-only compare.
        cur_git = _comparable_git_head(str(last.get("git_head") or ""))
        if history and cur_git and phase == "WORKING":
            same_git = sum(
                1
                for h in history[-4:]
                if _comparable_git_head(str(h.get("git_head") or "")) == cur_git
            )
            if same_git >= thresh:
                add("git HEAD unchanged while WORKING — agents not landing diffs", 26)

    last_advance = float(snap.get("last_queue_advance_ts") or 0)
    if last_advance > 0:
        since_advance = time.time() - last_advance
        if since_advance > 3600 and active_q > 5:
            add(f"no queue advance in {since_advance / 3600:.1f}h", 32, critical=since_advance > 7200)

    if int(flaws.get("high") or 0) >= 5:
        add(f"{flaws.get('high')} high-severity repo flaws open", 20)

    stagnant_cycles = int(state.get("stagnation_cycles") or 0)
    if healthy_idle or not report.stagnant:
        stagnant_cycles = 0
    else:
        stagnant_cycles += 1
    state["stagnation_cycles"] = stagnant_cycles
    if stagnant_cycles >= thresh and not report.critical and not healthy_idle:
        add(f"{stagnant_cycles} oversight cycles without improvement", 16)

    # OVERSEER_HEALTHY_IDLE_DEMOTE_LIVE_AGENT_EXIT_2026_09_04 — Active cleared +
    # green still critical-dispatched on soft live-log cursor-agent echoes when
    # skip needles were mid-clobber / tests_ok thin. Soft live hits alone must
    # never pierce healthy_idle.
    if healthy_idle and report.critical:
        soft_live = [
            r
            for r in report.reasons
            if "live log:" in r
            and ("cursor-agent non-zero" in r or "cursor-agent exit" in r)
        ]
        hard_markers = (
            "verify gate FAIL",
            "noop cycle",
            "daemon STOPPED",
            "peer phase STOPPED",
            "critical repo flaw",
            "critical self-heal",
            "dual-brain",
            "tests failing",
            "peer-loop daemon",
            "improve-loop daemon",
            "not running",
            "noop backoff",
        )
        other_critical = [
            r
            for r in report.reasons
            if r not in soft_live and any(m in r for m in hard_markers)
        ]
        if soft_live and not other_critical:
            report.reasons = [r for r in report.reasons if r not in soft_live]
            report.critical = False
            report.score = max(0, report.score - 40 * len(soft_live))
            if not report.reasons:
                report.stagnant = False

    threshold = 18 if high_expectations_enabled() else 35
    report.should_dispatch = report.critical or report.score >= threshold
    # OVERSEER_HEALTHY_IDLE_NO_SOFT_DISPATCH_2026_09_04 — Active cleared + green
    # OVERSEER_HEALTHY_IDLE_NO_DISPATCH_2026_09_04 — alias: no soft dispatch on idle.
    if healthy_idle and not report.critical:
        report.should_dispatch = False
    return report


def should_dispatch(
    ctx: dict[str, Any],
    flaws: dict[str, Any],
    *,
    state: dict[str, Any],
    dispatch_enabled: bool,
    force: bool = False,
    stagnation: StagnationReport | None = None,
    extras: dict[str, Any] | None = None,
) -> tuple[bool, StagnationReport, list[str]]:
    hold: list[str] = []
    if force:
        rep = stagnation or StagnationReport(stagnant=True, should_dispatch=True, reasons=["forced"])
        return True, rep, hold
    if not dispatch_enabled:
        hold.append("dispatch disabled")
        return False, StagnationReport(stagnant=False), hold

    since_last = time.time() - float(state.get("last_agent_ts") or 0)
    min_gap = agent_min_interval_sec() if agent_dispatch_mode() == "event" else agent_interval_sec()
    cooldown_left = max(0.0, min_gap - since_last)

    rep = stagnation or evaluate_stagnation(ctx, flaws, state=state, extras=extras)

    if agent_dispatch_mode() == "interval":
        if cooldown_left > 0:
            hold.append(f"interval cooldown {cooldown_left:.0f}s")
            return False, rep, hold
        return True, rep, hold

    if not rep.should_dispatch:
        max_iv = agent_max_interval_sec()
        if max_iv > 0 and since_last >= max_iv:
            rep.reasons.append(f"safety net: {max_iv:.0f}s without review")
            return True, rep, hold
        hold.append("factory advancing — no stagnation trigger")
        return False, rep, hold

    # Critical errors: never delay autonomy. Tiny anti-stampede floor only.
    if rep.critical:
        if bool(cfg_mod.CFG.get("autonomy_never_delay_on_error", True)):
            anti = 8.0
            try:
                anti = max(0.0, float(_cfg().get("critical_anti_stampede_sec") or 8))
            except (TypeError, ValueError):
                anti = 8.0
            if since_last < anti:
                hold.append(f"anti-stampede {anti - since_last:.0f}s")
                return False, rep, hold
            return True, rep, hold
        crit_gap = critical_agent_min_interval_sec()
        crit_left = max(0.0, crit_gap - since_last)
        if crit_left > 0:
            hold.append(f"critical min gap {crit_left:.0f}s")
            return False, rep, hold
        return True, rep, hold

    if cooldown_left > 0:
        hold.append(f"min gap {cooldown_left:.0f}s (non-critical)")
        return False, rep, hold

    return True, rep, hold


def cooldown_remaining(state: dict[str, Any]) -> float:
    since_last = time.time() - float(state.get("last_agent_ts") or 0)
    gap = agent_min_interval_sec() if agent_dispatch_mode() == "event" else agent_interval_sec()
    return max(0.0, gap - since_last)


def repo_research_stale_sec() -> float:
    """Age of last repo flaw research run (0 if never).

    OVERSEER_RESEARCH_STALE_FRESHEST_NS_2026_09_04 — prefer the freshest
    ``repo-research-state.json`` across hub + twin namespaces. A forever
    daemon stuck on ``~/.config/automation`` while research runs under
    ``automation-hub`` falsely reported 57m research_stale and soft-dispatched.
    """
    candidates: list[Path] = []
    try:
        candidates.append(Path(auto.CONFIG_DIR) / "repo-research-state.json")
    except Exception:  # noqa: BLE001
        pass
    home = Path.home() / ".config"
    for ns in ("automation-hub", "automation"):
        candidates.append(home / ns / "repo-research-state.json")
    best_last = 0.0
    seen: set[Path] = set()
    for path in candidates:
        try:
            path = path.resolve()
        except OSError:
            continue
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            last = float(data.get("last_run_ts") or data.get("last_digest_ts") or 0)
            if last > best_last:
                best_last = last
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    if best_last <= 0:
        return 86400.0
    return max(0.0, time.time() - best_last)
