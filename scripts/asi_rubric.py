#!/usr/bin/env python3
"""Phased rubric toward true ASI — complete one stage, then plan the next.

Overall % = (completed phases + partial credit on the active phase) / completable phases.
Criteria favor runtime delivery (daemon up, last_cycle, verify ok) over “code exists”.
Phase 5 (general autonomy) is asymptotic — never completes; it only drives planning.
"""

from __future__ import annotations

import platform
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent

# Phase complete when every criterion score >= this threshold.
PHASE_COMPLETE_THRESHOLD = 1.0

# Needle: ASI_DAEMON_PROBE_TTL_2026_09_05 — compute_asi_progress shells
# systemctl (~5ms) per label every rubric; write_prompts pays 2× → ~20ms.
# Soft TTL reuses label→ok within one prepare/dispatch window.
#
# Needle: ASI_DAEMON_PROBE_TTL_WAKE_FLOOR_2026_09_08 — continuous_wake_sec
# often == 30 so wake age >= bare TTL remisses daemon probes every heartbeat
# (same collision as peer_self_heal.PROBE_TTL_WAKE_FLOOR). Floor wake+slack.
DAEMON_PROBE_TTL_SEC = 30.0
DAEMON_PROBE_WAKE_SLACK_SEC = 5.0
_DAEMON_PROBE_CACHE: dict[str, tuple[bool, float]] = {}
_IS_DARWIN = platform.system() == "Darwin"

ASI_NORTH_STAR = (
    "100% true Artificial Super Intelligence (ASI) — "
    "generalization, autonomy, and orchestration beyond any system achievable by today's standards"
)


@dataclass(frozen=True)
class RubricCriterion:
    id: str
    title: str
    detail: str
    probe: Callable[[Any], tuple[float, str]]  # (score 0–1, evidence)


@dataclass(frozen=True)
class AsiPhase:
    id: str
    title: str
    summary: str
    criteria: tuple[RubricCriterion, ...]
    completable: bool = True
    plan_when_active: str = ""


@dataclass
class PhaseResult:
    id: str
    title: str
    summary: str
    status: str  # locked | active | complete | asymptotic
    score: float  # 0–1 mean of criteria
    met: bool
    criteria: list[dict[str, Any]]
    completable: bool = True


@dataclass
class AsiRubricResult:
    pct: int
    raw: float
    label: str
    phases: list[PhaseResult]
    current_phase_id: str
    next_plan: str | None
    dimensions: list[dict[str, Any]]  # flat criteria for legacy UI
    north_star: str = ASI_NORTH_STAR
    completed_phase_ids: tuple[str, ...] = ()


def phase_by_id(phase_id: str) -> AsiPhase | None:
    for phase in ASI_PHASES:
        if phase.id == phase_id:
            return phase
    return None


def work_kit_plan_for_phase(phase_id: str) -> str:
    """Actionable plan text for peer/work-kit (never 'improve itself')."""
    phase = phase_by_id(phase_id)
    if not phase:
        return "Advance the active ASI rubric phase via peer_loop / verify / orchestrate."
    return (
        f"{phase.plan_when_active} "
        "Execute via work kit only (peer_loop, verify, orchestrate, worktrees, tasks) — "
        "do not edit automation_improve / horizon / ASI chrome."
    )


def format_phase_advance_plan(previous_phase_id: str, current_phase_id: str) -> str:
    """Copy when a phase just completed and the next section becomes active."""
    prev = phase_by_id(previous_phase_id)
    curr = phase_by_id(current_phase_id)
    prev_title = prev.title if prev else previous_phase_id
    curr_title = curr.title if curr else current_phase_id
    body = work_kit_plan_for_phase(current_phase_id)
    return (
        f"{prev_title} MET. Continuously plan next — {curr_title}: {body}"
    )


def _script_text(name: str) -> str:
    path = SCRIPTS / name
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _systemd_user_active(unit: str) -> bool:
    """True when systemd user unit is active (Linux/DGX).

    Needle: ASI_SHARE_SYSTEMD_IS_ACTIVE_BATCH_2026_09_08 — write_prompts / factory
    remiss paid 2× ``systemctl is-active`` (~5–8ms each) via label TTL while
    ``peer_self_heal`` already batches the same units. Prefer heal's shared
    snapshot (transitional + process fallback) so ASI/factory remiss add **0**
    shells after a scan/heal tick.
    """
    if not unit:
        return False
    if not _IS_DARWIN:
        try:
            import peer_self_heal as heal

            batch = getattr(heal, "_SYSTEMD_ACTIVE_BATCH_UNITS", ())
            if unit in batch and hasattr(heal, "_systemd_user_active"):
                return bool(heal._systemd_user_active(unit))
        except Exception:  # noqa: BLE001 — fall back to single is-active
            pass
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and (proc.stdout or "").strip() == "active"


def _label_to_systemd_unit(label: str) -> str | None:
    """Map LaunchAgent-style labels to systemd user units (Linux/DGX).

    OVERSEER_ASI_OVERSIGHT_SYSTEMD_MAP_2026_09_08 — oversight must map here;
    factory_progress Linux path shares this probe (FACTORY_DAEMON_PROBE_SHARE_ASI_TTL)
    and previously stuck at ``oversight optional`` / factory 99% while
    ``oversight-loop.service`` was active.
    """
    low = (label or "").lower()
    if "oversight-loop" in low or low.endswith("-oversight-loop"):
        return "oversight-loop.service"
    if "improve-loop" in low or low.endswith("-improve-loop"):
        return "improve-loop.service"
    if "peer-loop" in low or low.endswith("-peer-loop"):
        return "peer-loop.service"
    return None


def clear_daemon_probe_cache() -> None:
    """Drop daemon probe TTL cache (tests + forced refresh)."""
    _DAEMON_PROBE_CACHE.clear()


def daemon_probe_effective_ttl_sec() -> float:
    """Floor daemon-probe TTL above continuous_wake so wake==TTL never remiss.

    Needle: ASI_DAEMON_PROBE_TTL_WAKE_FLOOR_2026_09_08 — prefer heal's
    ``probe_effective_ttl_sec`` when loaded (one SoT); else wake+slack locally.
    """
    try:
        import peer_self_heal as heal

        fn = getattr(heal, "probe_effective_ttl_sec", None)
        if callable(fn):
            return float(fn())
    except Exception:  # noqa: BLE001
        pass
    try:
        import project_automation as auto

        wake = float(auto.CFG.get("continuous_wake_sec") or 0.0)
    except Exception:  # noqa: BLE001
        wake = 0.0
    return max(DAEMON_PROBE_TTL_SEC, wake + DAEMON_PROBE_WAKE_SLACK_SEC)


def _launchctl_running(label: str, *, now: float | None = None) -> bool:
    """True when the hub daemon is up — LaunchAgent on macOS, systemd user unit on Linux/DGX.

    Soft-caches per label for ``daemon_probe_effective_ttl_sec()`` so ASI rubric /
    write_prompts do not re-shell ``systemctl``/``launchctl`` on every criterion.
    Linux skips ``launchctl`` (FileNotFoundError tax) and goes straight to systemd.
    """
    if not label:
        return False
    ts = time.monotonic() if now is None else now
    cached = _DAEMON_PROBE_CACHE.get(label)
    if cached is not None:
        ok, at = cached
        if (ts - at) < daemon_probe_effective_ttl_sec():
            return ok
    ok = False
    if _IS_DARWIN:
        try:
            proc = subprocess.run(
                ["launchctl", "list", label],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            if proc.returncode == 0:
                # exit code column -; pid column 0 means not running
                for line in (proc.stdout or "").splitlines():
                    if label in line:
                        parts = line.split()
                        if len(parts) >= 2 and parts[0] != "-":
                            ok = True
                            break
                if not ok and "pid" in (proc.stdout or "").lower():
                    ok = True
        except (OSError, subprocess.TimeoutExpired):
            pass
    if not ok:
        unit = _label_to_systemd_unit(label)
        if unit and _systemd_user_active(unit):
            ok = True
    _DAEMON_PROBE_CACHE[label] = (ok, ts)
    return ok


def _log_age_sec(path: Path) -> float | None:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


# Needle: LOG_TAIL_SEEK_2026_09_05 — improve-loop.log ~20MB; path.read_text()
# then [-tail] paid ~38ms on every factory first-MISS / ASI log probe. Seek
# last N bytes (~0.014ms) preserves needle semantics without full-file decode.
def _read_log_tail(path: Path, tail_bytes: int = 32000) -> str:
    """Read only the last ``tail_bytes`` of a log (seek from EOF)."""
    n = max(0, int(tail_bytes))
    with path.open("rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - n))
        return fh.read().decode("utf-8", errors="replace")


# Needle: LOG_HAS_RECENT_ANY_MTIME_MEMO_2026_09_08 — factory remiss called
# ``_log_has_recent_any`` every tick (~0.17ms) re-seeking 32KB of a ~50MB
# improve-loop.log while mtime unchanged. Memo by path+mtime_ns+needles;
# age string stays fresh; clear on tests.
_LOG_HAS_ANY_CACHE: dict[str, Any] = {
    "key": None,
    "ok": None,
    "matched": None,
}


def clear_log_has_recent_any_cache() -> None:
    """Drop log-has-recent-any mtime memo (tests + after log rotation)."""
    _LOG_HAS_ANY_CACHE["key"] = None
    _LOG_HAS_ANY_CACHE["ok"] = None
    _LOG_HAS_ANY_CACHE["matched"] = None


def _log_has_recent(
    path: Path,
    needle: str,
    max_age_sec: float = 900.0,
    *,
    tail_bytes: int = 32000,
) -> tuple[bool, str]:
    age = _log_age_sec(path)
    if age is None:
        return False, f"log missing: {path.name}"
    if age > max_age_sec:
        return False, f"{path.name} stale ({age:.0f}s)"
    try:
        tail = _read_log_tail(path, tail_bytes)
    except OSError:
        return False, f"cannot read {path.name}"
    hit = needle.lower() in tail.lower()
    return hit, f"{path.name} age={age:.0f}s; '{needle}'={hit}"


def _log_has_recent_any(
    path: Path,
    needles: tuple[str, ...],
    max_age_sec: float = 900.0,
    *,
    tail_bytes: int = 32000,
) -> tuple[bool, str]:
    """True when any needle appears in a fresh-enough log tail.

    Needle: LOG_HAS_RECENT_ANY_MTIME_MEMO_2026_09_08 — skip re-seek when
    path mtime unchanged (factory remiss / self_sufficiency wake credit).
    """
    try:
        mtime_ns = int(path.stat().st_mtime_ns)
    except OSError:
        return False, f"log missing: {path.name}"
    age = max(0.0, time.time() - (mtime_ns / 1_000_000_000.0))
    if age > max_age_sec:
        return False, f"{path.name} stale ({age:.0f}s)"

    key = (str(path), mtime_ns, needles, float(max_age_sec), int(tail_bytes))
    if (
        _LOG_HAS_ANY_CACHE.get("key") == key
        and _LOG_HAS_ANY_CACHE.get("ok") is not None
    ):
        ok = bool(_LOG_HAS_ANY_CACHE["ok"])
        matched = _LOG_HAS_ANY_CACHE.get("matched")
        if ok:
            return True, f"{path.name} age={age:.0f}s; matched '{matched}'"
        return False, f"{path.name} age={age:.0f}s; no activity needle in tail"

    try:
        tail = _read_log_tail(path, tail_bytes).lower()
    except OSError:
        return False, f"cannot read {path.name}"
    matched: str | None = None
    for needle in needles:
        if needle.lower() in tail:
            matched = needle
            break
    ok = matched is not None
    _LOG_HAS_ANY_CACHE["key"] = key
    _LOG_HAS_ANY_CACHE["ok"] = ok
    _LOG_HAS_ANY_CACHE["matched"] = matched
    if ok:
        return True, f"{path.name} age={age:.0f}s; matched '{matched}'"
    return False, f"{path.name} age={age:.0f}s; no activity needle in tail"


def _probe_ctx(signals: Any) -> dict[str, Any]:
    """Shared probe context from ImproveSignals + paths.

    Needle: ASI_PROBE_CTX_NO_IMPROVE_IMPORT_2026_09_08 — do not cold-import
    ``automation_improve`` just for ``IMPROVE_LABEL`` + ``SCRIPTS`` (probed
    ~11–44ms compile). Label formula matches ``automation_improve.IMPROVE_LABEL``;
    ``SCRIPTS`` is this module's dir (same as improve.SCRIPTS).
    """
    import project_automation as auto

    config = auto.CONFIG_DIR
    loop_state = signals.loop_state if isinstance(getattr(signals, "loop_state", None), dict) else {}
    last = loop_state.get("last_cycle") if isinstance(loop_state.get("last_cycle"), dict) else {}
    live = signals.live or {}

    peer_loop = _script_text("peer_loop.py")
    run_peer = _script_text("run_peer_tasks.py")
    peer_orch = _script_text("peer_orchestrate.py")
    peer_tx = _script_text("peer_transcript.py")
    improve_src = _script_text("automation_improve.py")

    # Canonical peer label only — hub/legacy collision is a separate bottleneck.
    peer_labels = (str(getattr(auto, "LAUNCH_AGENT_LABEL", "") or ""),)
    ns = str(auto.CFG.get("config_namespace") or "automation-hub")
    improve_label = f"com.togi.{ns}-improve-loop"

    return {
        "signals": signals,
        "live": live,
        "loop_state": loop_state,
        "last_cycle": last,
        "config": config,
        "peer_loop": peer_loop,
        "run_peer": run_peer,
        "peer_orch": peer_orch,
        "peer_tx": peer_tx,
        "improve_src": improve_src,
        "improve_label": improve_label,
        "peer_labels": peer_labels,
        "peer_log": config / "peer-loop.log",
        "improve_log": config / "improve-loop.log",
        "peer_status": config / "peer-loop-status.json",
        "worktree_path": SCRIPTS / "peer_worktree.py",
    }


def _c(id: str, title: str, detail: str, probe: Callable[[Any], tuple[float, str]]) -> RubricCriterion:
    return RubricCriterion(id=id, title=title, detail=detail, probe=probe)


# --- Phase 1: Grounded loop — daemons alive, cycles recorded ---

def _p1_improve_daemon(ctx: dict[str, Any]) -> tuple[float, str]:
    ok = _launchctl_running(str(ctx["improve_label"]))
    return (1.0 if ok else 0.0, f"improve daemon running={ok}")


def _p1_peer_daemon(ctx: dict[str, Any]) -> tuple[float, str]:
    for label in ctx["peer_labels"]:
        if label and _launchctl_running(label):
            return 1.0, f"peer daemon running ({label})"
    return 0.0, "peer daemon not running"


def _p1_last_cycle(ctx: dict[str, Any]) -> tuple[float, str]:
    last = ctx["last_cycle"]
    if last:
        keys = sorted(last.keys())
        return 1.0, f"last_cycle present ({', '.join(keys[:6])}{'…' if len(keys) > 6 else ''})"
    return 0.0, "no last_cycle in peer-loop-state"


def _p1_peer_log_recent(ctx: dict[str, Any]) -> tuple[float, str]:
    """Peer activity — last_cycle is primary; log needles are fallback.

    Heavy parallel/DGX logging can push ``continuous:`` lines out of a small
    tail window; do not regress Phase 1 when state shows a recent cycle.
    """
    last = ctx["last_cycle"]
    if last:
        try:
            age = max(0.0, time.time() - float(last.get("ts") or 0))
        except (TypeError, ValueError):
            age = None
        if age is not None and age < 3600.0:
            return 1.0, f"last_cycle age={age:.0f}s — peer loop active"
    needles = (
        "continuous:",
        "keep-working",
        "parallel:",
        "cursor-agent finished",
        "wake peer",
        "background",
    )
    ok, ev = _log_has_recent_any(ctx["peer_log"], needles, max_age_sec=3600.0)
    if ok:
        return 1.0, ev
    log_age = _log_age_sec(ctx["peer_log"])
    if log_age is not None and log_age < 180.0 and last:
        return 1.0, f"{ctx['peer_log'].name} fresh ({log_age:.0f}s) + last_cycle present"
    return 0.0, ev


# --- Phase 2: Verify & memory ---

def _p2_verify_ok(ctx: dict[str, Any]) -> tuple[float, str]:
    last = ctx["last_cycle"]
    if not last:
        return 0.0, "no last_cycle"
    if last.get("verify_ok") is True:
        return 1.0, "last_cycle.verify_ok=True"
    if last.get("verify_ok") is False:
        return 0.0, f"last_cycle.verify_ok=False ({last.get('note', '')})"
    return 0.5, "last_cycle.verify_ok unset"


def _p2_verify_retry_path(ctx: dict[str, Any]) -> tuple[float, str]:
    pl = "run_verify_gate" in ctx["peer_loop"]
    rpt = "def run_verify_gate" in ctx["run_peer"]
    if pl and rpt:
        return 1.0, "verify retry gate wired"
    return 0.5 if (pl or rpt) else 0.0, f"peer_loop={pl}; run_peer_tasks={rpt}"


def _p2_harness_memory(ctx: dict[str, Any]) -> tuple[float, str]:
    has_fn = "format_harness_memory" in ctx["peer_tx"] or "with_harness_memory" in ctx["peer_tx"]
    has_lc = bool(ctx["last_cycle"])
    if has_fn and has_lc:
        return 1.0, "harness memory + last_cycle"
    if has_fn:
        return 0.5, "harness code present; no last_cycle yet"
    return 0.0, "harness memory not wired"


# --- Phase 3: Parallel orchestration ---

def _p3_worktree_integrated(ctx: dict[str, Any]) -> tuple[float, str]:
    pl = ctx["peer_loop"]
    wt = ctx["worktree_path"].is_file()
    integrated = wt and ("peer_worktree" in pl) and ("list_worktrees" in pl)
    if integrated:
        return 1.0, "peer_loop uses peer_worktree"
    if wt and "peer_worktree" in pl:
        return 0.75, "peer_worktree imported; list_worktrees not called yet"
    if wt:
        return 0.5, "peer_worktree.py exists; not wired into peer_loop"
    return 0.0, "no worktree integration"


def _p3_maximize_parallel(ctx: dict[str, Any]) -> tuple[float, str]:
    if "Maximize parallel Task" in ctx["peer_orch"]:
        return 1.0, "maximize parallel peers in orchestrate prompts"
    return 0.0, "missing parallel peer orchestration wording"


def _p3_no_perpetual_noop(ctx: dict[str, Any]) -> tuple[float, str]:
    last = ctx["last_cycle"]
    if not last:
        return 0.0, "no last_cycle to judge noop"
    if last.get("noop") is not True:
        return 1.0, "last cycle advanced queue (noop=false or unset after work)"
    # Continuous keep-working often noops on the tick *after* an advance — credit
    # a recent fingerprint change so Phase 3 is not stuck on heartbeat noise.
    adv = ctx["loop_state"].get("last_queue_advance_ts")
    try:
        age = time.time() - float(adv or 0)
    except (TypeError, ValueError):
        age = None
    if age is not None and 0 <= age < 3600.0:
        return 1.0, f"queue advanced {age:.0f}s ago (recent); last tick noop"
    return 0.0, "last ok cycle was noop — queue not advancing"


# --- Phase 4: Autonomous improve → work ---

def _p4_improve_drives_work(ctx: dict[str, Any]) -> tuple[float, str]:
    src = ctx["improve_src"]
    mech = "apply_mechanical" in src
    enq = "enqueue_work_opportunities" in src
    if mech and enq:
        return 1.0, "improve heal + enqueue implemented"
    return 0.5 if (mech or enq) else 0.0, f"mechanical={mech}; enqueue={enq}"


def _p4_improve_log_active(ctx: dict[str, Any]) -> tuple[float, str]:
    ok, ev = _log_has_recent(ctx["improve_log"], "drive work kit", max_age_sec=600.0)
    if not ok:
        ok2, ev2 = _log_has_recent(ctx["improve_log"], "mechanical:", max_age_sec=600.0)
        return (1.0 if ok2 else 0.0, ev2 if ok2 else ev)
    return 1.0, ev


def _p4_peer_woken(ctx: dict[str, Any]) -> tuple[float, str]:
    ok, ev = _log_has_recent(ctx["improve_log"], "wake peer", max_age_sec=1800.0)
    return (1.0 if ok else 0.0, ev)


# --- Phase 5: General autonomy (asymptotic) ---

def _p5_coordinator(ctx: dict[str, Any]) -> tuple[float, str]:
    trends = getattr(ctx["signals"], "trend_report", None) or {}
    for t in trends.get("trends") or []:
        if t.get("id") == "coordinator_routing":
            st = str(t.get("kit_status", "")).lower()
            if st == "have":
                return 1.0, "coordinator routing: have"
            if st == "partial":
                return 0.5, "coordinator routing: partial"
            return 0.0, "coordinator routing: gap"
    return 0.0, "coordinator trend unknown"


def _p5_mcp(ctx: dict[str, Any]) -> tuple[float, str]:
    trends = getattr(ctx["signals"], "trend_report", None) or {}
    for t in trends.get("trends") or []:
        if t.get("id") == "mcp_tool_layer":
            st = str(t.get("kit_status", "")).lower()
            if st == "have":
                return 1.0, "MCP layer: have"
            if st == "partial":
                return 0.5, "MCP layer: partial"
            return 0.0, "MCP layer: gap"
    return 0.0, "MCP trend unknown"


def _p5_runtime_end_to_end(ctx: dict[str, Any]) -> tuple[float, str]:
    """Honest composite: verify ok + peer log + not noop."""
    v, _ = _p2_verify_ok(ctx)
    log, _ = _p1_peer_log_recent(ctx)
    n, _ = _p3_no_perpetual_noop(ctx)
    score = (v + log + n) / 3.0
    return score, f"verify={v:.1f} log={log:.1f} advance={n:.1f}"


ASI_PHASES: tuple[AsiPhase, ...] = (
    AsiPhase(
        id="grounded_loop",
        title="Phase 1 — Grounded loop",
        summary="Daemons run and peer cycles leave footprints in state and logs.",
        plan_when_active="Stabilize peer + improve daemons; record last_cycle after every agent run.",
        criteria=(
            _c("improve_daemon", "Improve forever running", "LaunchAgent alive", _p1_improve_daemon),
            _c("peer_daemon", "Peer loop running", "LaunchAgent alive", _p1_peer_daemon),
            _c("last_cycle_recorded", "Cycle memory", "peer-loop-state has last_cycle", _p1_last_cycle),
            _c("peer_log_recent", "Peer activity", "peer-loop.log touched in last hour", _p1_peer_log_recent),
        ),
    ),
    AsiPhase(
        id="verify_memory",
        title="Phase 2 — Verify & memory",
        summary="Post-agent verify passes; harness remembers the last cycle.",
        plan_when_active="Fix verify gate failures; persist last_cycle + inject retrospect into next peer prompt.",
        criteria=(
            _c("verify_ok", "Last verify passed", "last_cycle.verify_ok is True", _p2_verify_ok),
            _c("verify_retry", "Self-healing verify", "retry-once gate exists", _p2_verify_retry_path),
            _c("harness_memory", "Harness memory", "transcript injects last_cycle", _p2_harness_memory),
        ),
    ),
    AsiPhase(
        id="parallel_orchestration",
        title="Phase 3 — Parallel orchestration",
        summary="Multiple agents work disjoint scopes without stalling the queue.",
        plan_when_active="Integrate worktrees; maximize parallel Task peers per cycle; break noop loops.",
        criteria=(
            _c("worktree_integrated", "Worktree isolation", "peer_loop uses peer_worktree", _p3_worktree_integrated),
            _c("maximize_parallel", "Parallel peer prompts", "orchestrate maximizes Task peers", _p3_maximize_parallel),
            _c("queue_advances", "Queue advances", "last cycle not a noop fingerprint", _p3_no_perpetual_noop),
        ),
    ),
    AsiPhase(
        id="autonomous_improve_work",
        title="Phase 4 — Autonomous improve → work",
        summary="Improve forever heals, enqueues kit work, and wakes peer without human steering.",
        plan_when_active="Close improve→enqueue→peer dispatch loop; prove queue items land from improve cycles.",
        criteria=(
            _c("improve_drives_work", "Improve drives work kit", "mechanical + enqueue hooks", _p4_improve_drives_work),
            _c("improve_log_active", "Improve cycling", "improve-loop.log shows drive/heal", _p4_improve_log_active),
            _c("peer_woken", "Peer woken", "improve touches peer-turn.signal", _p4_peer_woken),
        ),
    ),
    AsiPhase(
        id="general_autonomy",
        title="Phase 5 — General autonomy (asymptotic)",
        summary="Coordinator routing, MCP, end-to-end autonomy — demanding of time; never fully possessed.",
        plan_when_active="Plan next general-autonomy capability after phases 1–4 are green.",
        completable=False,
        criteria=(
            _c("coordinator_routing", "Coordinator routing", "trend kit_status", _p5_coordinator),
            _c("mcp_layer", "MCP tool layer", "trend kit_status", _p5_mcp),
            _c("runtime_e2e", "End-to-end delivery", "verify + log + queue advance", _p5_runtime_end_to_end),
        ),
    ),
)


def _evaluate_phase(phase: AsiPhase, ctx: dict[str, Any]) -> PhaseResult:
    crit_rows: list[dict[str, Any]] = []
    scores: list[float] = []
    for c in phase.criteria:
        score, evidence = c.probe(ctx)
        score = max(0.0, min(1.0, float(score)))
        scores.append(score)
        crit_rows.append({
            "id": c.id,
            "name": c.id,
            "title": c.title,
            "detail": c.detail,
            "score": score,
            "weight": 1.0 / max(1, len(phase.criteria)),
            "evidence": evidence,
            "phase_id": phase.id,
        })
    mean = sum(scores) / len(scores) if scores else 0.0
    met = mean >= PHASE_COMPLETE_THRESHOLD and all(s >= PHASE_COMPLETE_THRESHOLD for s in scores)
    return PhaseResult(
        id=phase.id,
        title=phase.title,
        summary=phase.summary,
        status="asymptotic" if not phase.completable else "locked",
        score=mean,
        met=met,
        criteria=crit_rows,
        completable=phase.completable,
    )


def compute_asi_rubric(signals: Any) -> AsiRubricResult:
    """Score phased rubric; pct reflects completed phases + active phase progress only."""
    ctx = _probe_ctx(signals)
    results: list[PhaseResult] = []
    active_set = False
    current_id = ASI_PHASES[0].id
    next_plan: str | None = None

    for phase in ASI_PHASES:
        pr = _evaluate_phase(phase, ctx)
        if not phase.completable:
            pr.status = "asymptotic"
            if not active_set:
                # Phases 1–4 all complete → phase 5 is the planning horizon
                all_prior = all(r.met for r in results if r.completable)
                if all_prior:
                    pr.status = "active"
                    active_set = True
                    current_id = phase.id
                    next_plan = work_kit_plan_for_phase(phase.id)
            results.append(pr)
            continue

        if pr.met:
            pr.status = "complete"
            results.append(pr)
            continue

        if not active_set:
            pr.status = "active"
            active_set = True
            current_id = phase.id
            # Finish this phase; when MET, improve enqueues the next phase plan.
            next_plan = work_kit_plan_for_phase(phase.id)
            idx = ASI_PHASES.index(phase)
            if idx + 1 < len(ASI_PHASES):
                nxt = ASI_PHASES[idx + 1]
                next_plan = (
                    f"Finish {phase.title}: {phase.plan_when_active} "
                    f"When MET, immediately plan {nxt.title}: {nxt.plan_when_active} "
                    "(work kit only — peer_loop / verify / orchestrate)."
                )
            results.append(pr)
            break

        pr.status = "locked"
        results.append(pr)
        break

    # Fill remaining phases as locked if we broke early
    seen = {r.id for r in results}
    for phase in ASI_PHASES:
        if phase.id not in seen:
            pr = _evaluate_phase(phase, ctx)
            pr.status = "locked" if phase.completable else "asymptotic"
            results.append(pr)

    completable = [r for r in results if r.completable]
    n = len(completable) or 1
    progress_units = 0.0
    for r in completable:
        if r.status == "complete":
            progress_units += 1.0
        elif r.status == "active":
            progress_units += r.score
            break
        else:
            break

    raw = progress_units / n
    pct = max(0, min(100, int(round(raw * 100))))

    active_title = next((r.title for r in results if r.status == "active"), "")
    if pct >= 100:
        label = (
            f"{pct}% phased rubric complete — phase 5 (general autonomy) remains asymptotic; "
            "true ASI not possessed yet"
        )
    elif active_title:
        label = (
            f"{pct}% toward ASI — active: {active_title}; "
            "finish this phase, then plan the next"
        )
    else:
        label = f"{pct}% toward ASI — not possessed yet; remaining upgrades are demanding of time"

    flat_dims: list[dict[str, Any]] = []
    for r in results:
        flat_dims.extend(r.criteria)

    completed_ids = tuple(
        r.id for r in results if r.status == "complete" and r.completable
    )

    return AsiRubricResult(
        pct=pct,
        raw=raw,
        label=label,
        phases=[{
            "id": r.id,
            "title": r.title,
            "summary": r.summary,
            "status": r.status,
            "score": round(r.score, 3),
            "met": r.met,
            "completable": r.completable,
            "criteria": r.criteria,
        } for r in results],
        current_phase_id=current_id,
        next_plan=next_plan,
        dimensions=flat_dims,
        completed_phase_ids=completed_ids,
    )
