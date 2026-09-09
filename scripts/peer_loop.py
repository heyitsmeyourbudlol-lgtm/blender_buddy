#!/usr/bin/env python3
"""Forever peer loop — event-driven wake + continuous keep-working when queue has items.

Default: blocks on macOS kqueue (transcript JSONL + repo git + peer-turn.signal).
When the queue has work, waits with a short continuous timeout so cycles keep
running (event OR timeout) — never busy-spins, never idle forever with open work.
Fallback: 300s sleep only when kqueue unavailable.

Usage:
  python3 scripts/peer_loop.py --forever --background   # default
  python3 scripts/peer_loop.py --install                  # daemon: background terminal
  python3 scripts/peer_loop.py --watch                    # live terminal: WORKING vs IDLE
  ./scripts/peer-watch
  ./scripts/peer-loop-run
  python3 scripts/peer_loop.py --forever --clipboard-only   # opt-in: manual ⌘V paste
  python3 scripts/peer_loop.py --forever --cursor-ui         # opt-in: activate Cursor + inject
  python3 scripts/peer_loop.py --forever --paid-api           # opt-in: CURSOR_API_KEY billing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

# (COMPRESSION_LAZY_PEER_LOOP_HOT_2026_09_04) — cold import stays lean.
# (COMPRESSION_LAZY_TRANSCRIPT_TERMINAL_2026_09_04) — peer_transcript ~+4.7MB;
# peer_terminal ~+0.7MB; forever path loads on first use, status/tests stay lean.
# (COMPRESSION_LAZY_PEER_CURSOR_2026_09_04) — UI inject only; daemon --quick path skips.


class _LazyMod:
    """Attribute proxy — load module on first use; preserve call-site names."""

    __slots__ = ("_modname", "_mod")

    def __init__(self, modname: str) -> None:
        object.__setattr__(self, "_modname", modname)
        object.__setattr__(self, "_mod", None)

    def _load(self):  # noqa: ANN202
        mod = object.__getattribute__(self, "_mod")
        if mod is None:
            import importlib

            mod = importlib.import_module(object.__getattribute__(self, "_modname"))
            object.__setattr__(self, "_mod", mod)
        return mod

    def __getattr__(self, name: str):  # noqa: ANN204
        return getattr(self._load(), name)

    def __setattr__(self, name: str, value) -> None:  # noqa: ANN001
        if name in ("_modname", "_mod"):
            object.__setattr__(self, name, value)
            return
        setattr(self._load(), name, value)


peer_cursor = _LazyMod("peer_cursor")
stall = _LazyMod("peer_stall_pivot")
peer_worktree = _LazyMod("peer_worktree")
run_peer_tasks = _LazyMod("run_peer_tasks")
peer_terminal = _LazyMod("peer_terminal")
transcript = _LazyMod("peer_transcript")

LABEL = auto.LAUNCH_AGENT_LABEL
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_PATH = auto.CONFIG_DIR / "peer-loop.log"
POST_CYCLE_HOOK = auto.POST_CYCLE_HOOK

# Mirror peer_transcript.FALLBACK_POLL_SEC — avoid importing transcript at module load.
DEFAULT_FALLBACK_POLL_SEC = 300.0


def effective_fallback_poll_sec() -> float:
    """Prefer free-desktop shorter poll when event watch is unavailable."""
    try:
        return float(transcript.effective_fallback_poll_sec())
    except Exception:  # noqa: BLE001
        return DEFAULT_FALLBACK_POLL_SEC


# Safety net when git-clean wait or agent subprocess exceeds this (cannot event on external process).
DEFAULT_DONE_TIMEOUT_SEC = 7200.0
# After an ok agent cycle that leaves the same queue open, wait before re-dispatching the same plan.
NOOP_BACKOFF_SEC = 120.0
# When queue has work: event wait with this timeout so we keep cycling (event OR heartbeat).
CONTINUOUS_WAKE_SEC = float(auto.CFG.get("continuous_wake_sec") or 90.0)
# DGX overlays of 1–3s must not collapse the heartbeat (notes: _shallow_wake_floor).
_WAKE_HARD_MIN_SEC = 15.0


def _live_wake_cfg() -> dict:
    """Re-read disk config — import-time CFG can hold a DGX hyper-wake overlay."""
    try:
        import automation_config as cfg_mod

        return cfg_mod.load_config()
    except Exception:  # noqa: BLE001
        return dict(auto.CFG)


def _shallow_wake_floor(cfg: dict | None = None) -> float:
    """Minimum continuous heartbeat when the queue is small.

    ``continuous_agent_min_interval_sec`` values below ``_WAKE_HARD_MIN_SEC``
    (DGX ``dgx_speed.local.json`` uses 1) are ignored — they must not become
    the fallback that collapses ``continuous_wake_shallow_floor_sec``.
    """
    cfg = cfg if cfg is not None else _live_wake_cfg()
    try:
        floor = float(cfg.get("continuous_wake_shallow_floor_sec") or 0)
    except (TypeError, ValueError):
        floor = 0.0
    return max(_WAKE_HARD_MIN_SEC, floor)


def effective_continuous_wake_sec(*, open_queue_count: int | None = None) -> float:
    """Live wake interval: floor hyper overlays; raise when the queue is shallow."""
    cfg = _live_wake_cfg()
    try:
        wake = float(cfg.get("continuous_wake_sec") or 90.0)
    except (TypeError, ValueError):
        wake = 90.0
    try:
        max_items = int(cfg.get("continuous_wake_shallow_max_items") or 8)
    except (TypeError, ValueError):
        max_items = 8
    floor = _shallow_wake_floor(cfg)
    if wake < _WAKE_HARD_MIN_SEC:
        wake = floor
    if open_queue_count is None:
        try:
            ctx = auto.load_context_md()
            work = auto.load_work_queue_md()
            live = auto.measure_live_state(quick=True)
            open_queue_count = len(auto.loop_work_items(ctx, work, live=live).open_items)
        except Exception:  # noqa: BLE001
            open_queue_count = 0
    if open_queue_count <= max_items:
        return max(wake, floor)
    return max(wake, _WAKE_HARD_MIN_SEC)


def effective_noop_backoff_sec(*, open_queue_count: int | None = None) -> float:
    """Shorter agent re-dispatch gap when the queue is deep — keep workers grinding."""
    try:
        tuned = float(auto.CFG.get("stall_pivot_noop_backoff_sec") or 0)
        if tuned > 0:
            return max(5.0, tuned)
    except (TypeError, ValueError):
        pass
    try:
        floor = max(5.0, float(auto.CFG.get("continuous_agent_min_interval_sec") or 30.0))
    except (TypeError, ValueError):
        floor = 30.0
    if open_queue_count is None:
        try:
            ctx = auto.load_context_md()
            work = auto.load_work_queue_md()
            live = auto.measure_live_state(quick=True)
            open_queue_count = len(auto.loop_work_items(ctx, work, live=live).open_items)
        except Exception:  # noqa: BLE001
            open_queue_count = 0
    if open_queue_count >= 10:
        return floor
    if open_queue_count >= 3:
        return max(floor, min(NOOP_BACKOFF_SEC, floor * 2))
    return NOOP_BACKOFF_SEC



def _should_spin_after_agent_cycle(last_cycle: dict | None) -> bool:
    """Forever-loop continue heuristic after a cursor-agent cycle.

    Spin only when the last cycle was verify-green and advanced work (not noop).
    Deferred soft-skip must never spin — even if verify_ok were stale True from a
    prior cycle (hub bug: deferred returned without record_cycle_outcome).

    OVERSEER_FLAT_FP_NO_SPIN_2026_09_07 — pre-dispatch / ensure_driving may clear
    ``noop`` while queue_fp stays flat; treat flat fp as non-spin so mass agents
    do not verify-storm the same Active set.
    """
    if not isinstance(last_cycle, dict) or not last_cycle:
        return False
    if str(last_cycle.get("failure_type") or "").strip() == "deferred":
        return False
    if last_cycle.get("noop"):
        return False
    fp_before = str(last_cycle.get("queue_fp_before") or "").strip()
    fp_after = str(
        last_cycle.get("queue_fp_after") or last_cycle.get("queue_fp") or ""
    ).strip()
    if fp_before and fp_after and fp_before == fp_after:
        return False
    return bool(last_cycle.get("verify_ok"))


def _noop_remaining_or_clear(*, state: dict, log_fn, backoff_sec: float | None = None) -> float:
    """Noop backoff seconds left.

    OVERSEER_NOOP_BACKOFF_NOT_ERROR_2026_09_07 — ``autonomy_never_delay_on_error``
    must not clear noop backoff. Noop is intentional cooldown after an ok cycle
    that did not advance queue_fp; treating it as an error caused continuous
    re-dispatch (verify storm / hand_out churn).
    """
    import peer_transcript as transcript

    sec = backoff_sec if backoff_sec is not None else effective_noop_backoff_sec()
    return transcript.noop_backoff_remaining(state, backoff_sec=sec)


def continuous_wake_timeout(
    *,
    has_work: bool,
    noop_remaining: float,
    open_queue_count: int | None = None,
) -> float | None:
    """Event wait timeout: short heartbeat when work remains, else block until event.

    Pure event-driven when idle; continuous keep-working uses timed kqueue wait
    (not a poll loop) so wakes on transcript/git/signal OR timeout.
    """
    if not has_work:
        return None
    if noop_remaining > 0:
        return float(noop_remaining)
    return effective_continuous_wake_sec(open_queue_count=open_queue_count)


# PeerEventWatcher.wait already force-scans on kevent. Post-wait must NOT
# force again — soft TTL reuses wait's fresh cache. Needle:
# REUSE_WAIT_FIND_LATEST_CACHE_2026_09_05
POST_WAIT_FIND_LATEST_FORCE = False


def should_skip_post_wait_transcript_rescan(
    *,
    timed_out: bool,
    watcher_available: bool,
    event_reason: str | None = None,
) -> bool:
    """Reuse pre-wait path/meta when no transcript/git event could have fired.

    ``find_latest_transcript`` remisses after wake sleep (TTL cold ~35ms+). Skip
    the post-wait rescan when:

    - kqueue ``timeout`` + watcher available — no VNODE fired; or
    - ``fallback`` sleep with no watcher (Linux) — loop-head already scanned;
      sleep cannot observe new transcripts, so a second scan is pure steal.

    Needle: OVERSEER_SKIP_POST_WAIT_FIND_LATEST_2026_09_05 ·
    OVERSEER_SKIP_FALLBACK_FIND_LATEST_2026_09_05 (hub port L119).
    """
    if timed_out and watcher_available:
        return True
    if (not watcher_available) and str(event_reason or "") == "fallback":
        return True
    return False


def should_skip_post_wait_live_refresh(
    *,
    timed_out: bool,
    watcher_available: bool,
    event_reason: str | None = None,
) -> bool:
    """Alias: no event → reuse pre-wait ``live``."""
    return should_skip_post_wait_transcript_rescan(
        timed_out=timed_out,
        watcher_available=watcher_available,
        event_reason=event_reason,
    )


def _log(msg: str, *, daemon: bool) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    if daemon:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as fh:
            fh.write(line + "\n")


def metrics_green(live: auto.LiveState) -> bool:
    # OVERSEER_METRICS_IGNORE_GIT_CLEAN_2026_09_04 — WORKING + continue_on_dirty:
    # dirty porcelain must not paint metrics red (tests/RSS only).
    # OVERSEER_METRICS_DIRTY_OK_2026_09_03 / OVERSEER_METRICS_TESTS_ONLY_2026_09_04
    return bool(live.tests_ok) and auto.success_metrics_ok(live)



def should_stop_loop(context_md: str, live: auto.LiveState) -> str | None:
    return auto.stop_reason(context_md, live, loop=True)


def _emit_automation_event(event: str, payload: dict | None = None, *, log_fn=None) -> None:
    try:
        import automation_engine as engine

        result = engine.emit(event, payload or {})
        if log_fn and result.action_results:
            for line in result.action_results:
                log_fn(f"automation: {line}")
    except Exception:  # noqa: BLE001 — rules must not block the loop
        pass


def _emit_peer_cycle(state: dict, *, log_fn=None) -> None:
    try:
        import automation_engine as engine

        result = engine.emit_peer_cycle(state)
        if log_fn and result.action_results:
            for line in result.action_results:
                log_fn(f"automation: {line}")
    except Exception:  # noqa: BLE001
        pass


def run_post_cycle_hook(*, log_fn) -> bool:
    hook = POST_CYCLE_HOOK
    if not hook:
        return True
    if isinstance(hook, list):
        cmd = [str(x) for x in hook]
    else:
        cmd = [str(hook)]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=120.0, check=False)
    if proc.returncode == 0:
        log_fn(f"post_cycle_hook: ok ({' '.join(cmd)})")
        return True
    err = (proc.stderr or proc.stdout or "post_cycle_hook failed").strip().splitlines()
    log_fn(f"post_cycle_hook: FAIL — {err[-1] if err else proc.returncode}")
    return False


def _git_porcelain(cwd: Path) -> str:
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=float(auto.GIT_MEASURE_TIMEOUT_SEC),
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _commit_paths_after_verify() -> list[Path]:
    """Return repo roots to commit: main tree + coding worktree when present."""
    paths: list[Path] = [ROOT.resolve()]
    if peer_worktree.continue_on_dirty_enabled():
        rel, _branch = peer_worktree.coding_worktree_config()
        wt = (ROOT / rel).resolve()
        if wt.is_dir() and wt not in paths:
            paths.append(wt)
    return paths


def _clear_stale_git_index_lock(cwd: Path, *, log_fn, max_age_sec: float = 120.0) -> None:
    """Remove abandoned ``.git/index.lock`` so auto-commit is not forever blocked.

    Overnight stalls: empty locks left for hours while rsync/agents contend.
    Only delete when the lock file is older than ``max_age_sec`` (or empty+old).
    """
    lock = cwd / ".git" / "index.lock"
    if not lock.is_file():
        return
    try:
        age = time.time() - lock.stat().st_mtime
    except OSError:
        return
    if age < max_age_sec:
        return
    try:
        lock.unlink(missing_ok=True)
        log_fn(f"auto-commit: cleared stale index.lock ({cwd.name}, age={age:.0f}s)")
    except OSError as exc:
        log_fn(f"auto-commit: could not clear index.lock ({cwd.name}) — {exc}")


def _git_staged_names(cwd: Path, *, timeout: float) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]


def _git_add_commitworthy(cwd: Path, *, log_fn, timeout: float) -> subprocess.CompletedProcess:
    """Stage everything except configured excludes (weights/local/locks/secrets)."""
    excludes = auto.auto_commit_exclude_pathspecs()
    cmd = ["git", "add", "-A", "--", "."] + excludes
    add = None
    for attempt in range(3):
        add = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if add.returncode == 0:
            return add
        err_blob = f"{add.stderr or ''}{add.stdout or ''}".lower()
        if "index.lock" in err_blob or "another git process" in err_blob:
            _clear_stale_git_index_lock(cwd, log_fn=log_fn, max_age_sec=0.0)
            time.sleep(0.4 * (attempt + 1))
            continue
        return add
    assert add is not None
    return add


def maybe_auto_commit_after_verify(*, log_fn, note: str = "") -> bool:
    """Always commit commit-worthy changes after verify.

    Smart path:
    - Skips local/weights/locks/secrets via ``auto_commit_exclude_globs``
    - Retries a few passes when agents keep writing during commit
    - Treats exclude-only residual dirty as success (continue_on_dirty soft)
    """
    if not auto.auto_commit_after_verify_enabled():
        return True

    timeout = auto.auto_commit_git_timeout_sec()
    max_passes = auto.auto_commit_max_passes()
    committed_any = False
    soft_dirty_only = False

    for cwd in _commit_paths_after_verify():
        for pass_i in range(max_passes):
            dirty = _git_porcelain(cwd)
            if not dirty:
                break

            _clear_stale_git_index_lock(cwd, log_fn=log_fn)
            add = _git_add_commitworthy(cwd, log_fn=log_fn, timeout=timeout)
            if add.returncode != 0:
                err = (add.stderr or add.stdout or "git add failed").strip().splitlines()
                log_fn(
                    f"auto-commit: git add FAIL ({cwd}) — "
                    f"{err[-1] if err else add.returncode}"
                )
                return False

            staged = _git_staged_names(cwd, timeout=timeout)
            if not staged:
                # Dirty remains but only excluded paths (weights/local/locks).
                residual = len([ln for ln in dirty.splitlines() if ln.strip()])
                log_fn(
                    f"auto-commit: soft-dirty only ({cwd.name}) — "
                    f"{residual} excluded/residual path(s); commit-worthy clean"
                )
                soft_dirty_only = True
                break

            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            msg = f"peer cycle: verify ok ({ts})"
            if note:
                msg += f" — {note[:160]}"
            if pass_i > 0:
                msg += f" [pass {pass_i + 1}]"

            commit = subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            out = f"{commit.stdout or ''}{commit.stderr or ''}".lower()
            if commit.returncode == 0:
                short = (commit.stdout or "").strip().splitlines()
                log_fn(
                    f"auto-commit: ok ({cwd.name}, {len(staged)} files"
                    f"{f', pass {pass_i + 1}' if pass_i else ''}) — "
                    f"{short[-1] if short else msg[:72]}"
                )
                committed_any = True
                if auto.auto_push_after_commit_enabled():
                    push = subprocess.run(
                        ["git", "push"],
                        cwd=str(cwd),
                        capture_output=True,
                        text=True,
                        timeout=max(timeout, 300.0),
                        check=False,
                    )
                    if push.returncode == 0:
                        log_fn(f"auto-push: ok ({cwd.name})")
                    else:
                        err = (push.stderr or push.stdout or "git push failed").strip().splitlines()
                        log_fn(
                            f"auto-push: FAIL ({cwd.name}) — "
                            f"{err[-1] if err else push.returncode}"
                        )
                        return False
                continue  # another pass if agents wrote more commit-worthy files

            if "nothing to commit" in out:
                log_fn(f"auto-commit: nothing to commit ({cwd.name})")
                break

            err = (commit.stderr or commit.stdout or "git commit failed").strip().splitlines()
            log_fn(
                f"auto-commit: FAIL ({cwd.name}) — "
                f"{err[-1] if err else commit.returncode}"
            )
            return False
        else:
            # Exhausted passes with remaining dirty — check if commit-worthy left.
            _clear_stale_git_index_lock(cwd, log_fn=log_fn)
            add = _git_add_commitworthy(cwd, log_fn=log_fn, timeout=timeout)
            staged = _git_staged_names(cwd, timeout=timeout) if add.returncode == 0 else ["?"]
            if staged:
                log_fn(
                    f"auto-commit: WARN ({cwd.name}) — still {len(staged)} "
                    f"commit-worthy after {max_passes} passes (will retry next verify)"
                )
                # Unstage so we don't leave a dirty index for humans/agents.
                subprocess.run(
                    ["git", "reset", "-q"],
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            continue

    if not committed_any and not soft_dirty_only:
        log_fn("auto-commit: clean — nothing to commit")
    return True


# Soft TTL so forever-wake does not re-pay full orchestrate self-check every tick.
PRE_DISPATCH_CHECK_TTL_SEC = 60.0
_pre_dispatch_check_at: float = 0.0


def clear_pre_dispatch_check_cache() -> None:
    """Drop pre-dispatch check TTL stamp (tests + forced refresh)."""
    global _pre_dispatch_check_at
    _pre_dispatch_check_at = 0.0


def _should_skip_pre_dispatch_check() -> bool:
    if _pre_dispatch_check_at <= 0.0:
        return False
    return (time.monotonic() - _pre_dispatch_check_at) < PRE_DISPATCH_CHECK_TTL_SEC


def _stamp_pre_dispatch_check() -> None:
    global _pre_dispatch_check_at
    _pre_dispatch_check_at = time.monotonic()


def _open_queue_content_fingerprint() -> str:
    """Content fp of open loop queue — no ``peer_transcript`` import.

    Needle: PRE_DISPATCH_NOOP_CLEAR_LITE_FP_2026_09_08 — pre-dispatch noop-clear
    previously cold-imported ``peer_transcript.current_queue_fingerprint`` (~8–22ms)
    solely to compare against ``last_cycle.queue_fp``.
    QUEUE_FP_LITE_DRY_PROJECT_AUTOMATION_2026_09_08 — delegates to auto SoT.
    """
    fp, _ = auto.current_queue_fingerprint_lite()
    return fp


def _mechanical_pre_dispatch(*, log_fn, role_id: str = "orchestrator") -> bool:
    """Compact → plan-gate → check → ensure-pool before agent spawn.

    Mirrors ``./scripts/peer pre-dispatch`` (compact → … → check → ensure-pool).
    Soft noop / check soft-fail do not block; plan-gate hard-block still returns False.
    Needle: OVERSEER_PRE_DISPATCH_CHECK_POOL_2026_09_07
    """
    try:
        removed, actions = auto.compact_executable_queue(write=True, max_active=12)
        if removed:
            log_fn(f"pre-dispatch: compact removed={removed} ({'; '.join(actions[:2])})")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"pre-dispatch: compact ({exc})")
    try:
        import peer_self_heal as sh

        if sh.self_heal_enabled():
            report = sh.run_cycle(write=True, log_fn=log_fn)
            if report.actions:
                log_fn(f"pre-dispatch: self-heal {len(report.actions)} action(s)")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"pre-dispatch: self-heal ({exc})")
    try:
        # OVERSEER_PRE_DISPATCH_NOOP_CLEAR_FP_2026_09_07 — only clear noop when
        # compact/heal already moved queue_fp. Blind clear defeated backoff and
        # let _should_spin treat flat-fp cycles as green progress.
        # PRE_DISPATCH_NOOP_CLEAR_LITE_FP_2026_09_08 — lite content fp (no tx import).
        state_path = auto.CONFIG_DIR / "peer-loop-state.json"
        if state_path.is_file():
            data = json.loads(state_path.read_text(encoding="utf-8"))
            lc = data.get("last_cycle") if isinstance(data, dict) else None
            if isinstance(lc, dict) and lc.get("noop"):
                fp_now = _open_queue_content_fingerprint()
                fp_prior = str(
                    lc.get("queue_fp") or lc.get("queue_fp_before") or ""
                ).strip()
                if fp_now and fp_prior and fp_now != fp_prior:
                    lc["noop"] = False
                    lc["noop_cleared_pre_dispatch"] = True
                    data["last_cycle"] = lc
                    state_path.write_text(
                        json.dumps(data, indent=2) + "\n", encoding="utf-8"
                    )
                    log_fn(
                        "pre-dispatch: cleared noop — queue_fp advanced "
                        f"({fp_prior[:8]}→{fp_now[:8]})"
                    )
                else:
                    log_fn(
                        "pre-dispatch: keeping noop backoff — queue_fp unchanged"
                    )
    except Exception as exc:  # noqa: BLE001
        log_fn(f"pre-dispatch: noop clear ({exc})")
    try:
        import automation_adapt as adapt

        healed, warns = adapt.heal_queue_drift(root=auto.ROOT, write=True)
        if healed:
            log_fn(f"pre-dispatch: sync-queue healed={len(healed)}")
        if warns:
            log_fn(f"pre-dispatch: sync-queue warn={len(warns)}")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"pre-dispatch: sync-queue ({exc})")
    try:
        import peer_team_context as tc

        tc.write_team_context()
        log_fn("pre-dispatch: team-context refreshed")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"pre-dispatch: team-context ({exc})")
    try:
        import peer_agent_gates as gates

        # OVERSEER_FACTORY_NICHE_RUNTIME_2026_09_07 — parallel niche assist (fail-soft)
        try:
            import factory_niche_runtime as niche_rt

            niche_rt.assist_pre_dispatch(log_fn=log_fn)
        except Exception as exc:  # noqa: BLE001
            log_fn(f"pre-dispatch: niche-assist ({exc})")
        report = gates.run_plan_gate(role_id=role_id, refresh=False, quick=True)
        if report.blocked:
            # One more sync+heal pass for institutional-memory drift before hard stop.
            try:
                import automation_adapt as adapt

                adapt.heal_queue_drift(root=auto.ROOT, write=True)
                report = gates.run_plan_gate(role_id=role_id, refresh=True, quick=True)
            except Exception:  # noqa: BLE001
                pass
            if report.blocked:
                log_fn("pre-dispatch: plan-gate BLOCKED — adapting (heal + playbook + pivot)")
                try:
                    import peer_error_adapt as err_adapt

                    still, acts = err_adapt.adapt_plan_gate(
                        report,
                        log_fn=log_fn,
                        quick=True,
                    )
                    if acts:
                        log_fn(f"pre-dispatch: error-adapt {', '.join(acts[:6])}")
                    if still:
                        log_fn("pre-dispatch: plan-gate still hard-blocked — pivoted; skip primary")
                        return False
                    log_fn("pre-dispatch: plan-gate recovered after adapt")
                except Exception as exc:  # noqa: BLE001
                    log_fn(f"pre-dispatch: error-adapt ({exc})")
                    log_fn("pre-dispatch: plan-gate BLOCKED — fix fail rows before dispatch")
                    return False
        log_fn(f"pre-dispatch: plan-gate ok ({report.warn_count} warn)")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"pre-dispatch: plan-gate ({exc})")
    # CLI compound: check → ensure-pool (after plan-gate). Soft — never hard-block spawn.
    try:
        if _should_skip_pre_dispatch_check():
            log_fn(
                f"pre-dispatch: check skip (TTL {PRE_DISPATCH_CHECK_TTL_SEC:.0f}s)"
            )
        else:
            import peer_orchestrate as orch

            rc = orch.run_self_check(quick=True)
            _stamp_pre_dispatch_check()
            busy = int(getattr(orch, "SELF_CHECK_LOCK_BUSY_RC", 75))
            if rc == 0:
                log_fn("pre-dispatch: check ok")
            elif rc == busy:
                log_fn("pre-dispatch: check skipped (lock busy)")
            else:
                log_fn(f"pre-dispatch: check soft-fail rc={rc}")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"pre-dispatch: check ({exc})")
    try:
        # ensure-pool via inventory_snapshot(ensure_pool=True) + emit TTL skip
        _emit_worktree_inventory(log_fn)
    except Exception as exc:  # noqa: BLE001
        log_fn(f"pre-dispatch: ensure-pool ({exc})")
    return True


def _mechanical_post_cycle(*, log_fn, role_id: str = "orchestrator") -> None:
    """Run done-gate after verify OK — uses last_cycle when args omitted."""
    try:
        import factory_niche_runtime as niche_rt

        niche_rt.assist_done_gate(log_fn=log_fn)
    except Exception as exc:  # noqa: BLE001
        log_fn(f"post-cycle: niche-assist ({exc})")
    try:
        import peer_agent_gates as gates

        expected, actual = gates.last_verify_expected_actual()
        report = gates.run_done_gate(
            role_id=role_id,
            expected=expected,
            actual=actual,
            quick=True,
        )
        if report.blocked:
            log_fn("post-cycle: done-gate BLOCKED")
        else:
            log_fn("post-cycle: done-gate ok")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"post-cycle: done-gate ({exc})")


def _after_verify_ok(*, log_fn, note: str = "") -> None:
    """Post-verify hygiene: auto-commit (default), optional push, then automation rules."""
    resolved = auto.check_off_resolved_self_heal()
    if resolved:
        log_fn(f"queue: checked off {len(resolved)} resolved self-heal item(s)")
    auto.dedupe_work_queue_files(write=True)
    maybe_auto_commit_after_verify(log_fn=log_fn, note=note)
    _mechanical_post_cycle(log_fn=log_fn, role_id="orchestrator")
    refreshed = auto.measure_live_state(quick=True)
    if metrics_green(refreshed):
        _emit_automation_event("peer.verify.ok", {"note": note, "metrics_green": True}, log_fn=log_fn)
    # Verify gate: keep hub worker_pool_size trees ready for next parallel cycle.
    # OVERSEER_LAND_2026_09_03 — skip ensure when emit TTL + floor ready (same-wake ~95ms).
    try:
        import peer_roles as roles

        global _emit_ensure_at
        target = roles.worker_pool_size(auto.load_tasks_config())
        if _should_skip_emit_ensure(target):
            age = time.monotonic() - _emit_ensure_at
            log_fn(
                f"verify: hub pool ensure skipped (floor ready, TTL "
                f"{EMIT_ENSURE_TTL_SEC:.0f}s, age={age:.1f}s)"
            )
        else:
            pool = peer_worktree.ensure_parallel_pool(count=target, log_fn=log_fn)
            _emit_ensure_at = time.monotonic()
            log_fn(f"verify: hub worker pool {len(pool)}/{target} ready")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"verify: hub pool ensure skipped ({exc})")
    try:
        import peer_transcript as pt

        pt.poke_turn_signal()
    except Exception:  # noqa: BLE001
        pass


def dispatch_prompt_text(
    text: str,
    *,
    mode: str,
    clipboard_only: bool,
    press_enter: bool,
    log_fn,
    transcript_path: Path | None = None,
    state: dict | None = None,
    paid_api: bool = False,
    cwd: Path | None = None,
) -> tuple[int, bool]:
    if mode in ("terminal", "background") and not clipboard_only and mode != "direct-ui":
        return peer_terminal.dispatch_via_terminal(
            text,
            log_fn=log_fn,
            state=state,
            record_fn=peer_cursor.record_dispatch,
            paid_api=paid_api,
            cwd=cwd,
        )

    if clipboard_only or mode == "clipboard" or os.environ.get("CURSOR_MINIMIZED") == "1":
        if not auto.copy_to_clipboard(text):
            log_fn("dispatch: clipboard copy failed")
            return 1, False
        log_fn(f"dispatch: copied to clipboard ({len(text)} chars)")
        return 0, False

    turn_count = transcript.count_turns(transcript_path)
    fresh = peer_cursor.should_open_fresh_chat(turn_count=turn_count, prompt_chars=len(text))
    if fresh:
        log_fn(f"dispatch: fresh chat (turns={turn_count}, prompt={len(text)} chars)")

    ok, msg = peer_cursor.inject_text_to_cursor(
        text, press_enter=press_enter, fresh_chat=fresh, cursor_ui=(mode == "direct-ui")
    )
    if ok:
        log_fn(f"dispatch: {msg}")
        if state is not None:
            state = peer_cursor.record_dispatch(state)
            transcript.save_state(state)
        return 0, False
    log_fn(f"dispatch: Cursor inject failed — {msg}")
    if "Accessibility" not in msg:
        log_fn(f"dispatch: {peer_cursor.accessibility_hint()}")
    return 1, False


def dispatch_peer_prompt(
    *,
    quick: bool,
    mode: str,
    clipboard_only: bool,
    press_enter: bool,
    log_fn,
    state: dict | None = None,
    paid_api: bool = False,
    cwd: Path | None = None,
    dirty_continue: bool = False,
) -> tuple[int, bool]:
    text = transcript.build_next_input(quick=quick) or ""
    if not text or text.startswith("Nothing to orchestrate"):
        log_fn("dispatch: nothing to orchestrate")
        return 0, False
    if dirty_continue or (cwd is not None and Path(cwd).resolve() != ROOT.resolve()):
        work = Path(cwd).resolve() if cwd is not None else ROOT.resolve()
        prefix = (
            "## continue_on_dirty — do not stall\n"
            "Main tree may be dirty. **Keep coding.** Do not wait for a clean tree. "
            "peer_loop auto-commits after verify passes. "
            f"Working directory for this cycle: `{work}`.\n\n"
        )
        text = prefix + text
    path = transcript.find_latest_transcript()
    return dispatch_prompt_text(
        text,
        mode=mode,
        clipboard_only=clipboard_only,
        press_enter=press_enter,
        log_fn=log_fn,
        transcript_path=path,
        state=state,
        paid_api=paid_api,
        cwd=cwd,
    )


def _resolve_coding_cwd(live: auto.LiveState, log_fn) -> tuple[Path, bool]:
    """Pick agent cwd. When dirty + continue_on_dirty, prefer coding worktree.

    Returns (cwd, used_isolate). Falls back to ROOT on worktree failure so coding
    still continues on the dirty main tree.
    """
    try:
        import peer_product_forge as forge

        target = forge.active_target()
        if target is not None and forge.forge_active():
            log_fn(f"product-forge: dispatch cwd → {target}")
            return target, False
    except Exception:  # noqa: BLE001
        pass
    if live.git_clean or not peer_worktree.continue_on_dirty_enabled():
        return ROOT, False
    try:
        path = peer_worktree.ensure_coding_worktree()
        log_fn(f"continue_on_dirty: coding worktree → {path}")
        return path, True
    except RuntimeError as exc:
        log_fn(
            f"continue_on_dirty: worktree unavailable ({exc}) — "
            "dispatching on dirty main so coding does not stop"
        )
        return ROOT, False



def wait_for_git_clean(
    *,
    fallback_poll_sec: float,
    timeout_sec: float,
    log_fn,
    watcher: transcript.PeerEventWatcher | None = None,
    state: dict | None = None,
    quick: bool = True,
    use_agent: bool = False,
    paid_api: bool = False,
) -> auto.LiveState | None:
    """Block on git VNODE events until metrics green or safety-net timeout."""
    state = state if state is not None else transcript.load_state()
    state = stall.note_stall(state, "git_clean_wait")
    transcript.save_state(state)
    if timeout_sec <= 0:
        live = auto.measure_live_state(quick=True)
        if metrics_green(live):
            stall.clear_stall(state)
            transcript.save_state(state)
            return live
        return None
    deadline = time.time() + timeout_sec
    pivot_sec = stall.stall_pivot_sec()
    while time.time() < deadline:
        live = auto.measure_live_state(quick=True)
        if metrics_green(live):
            stall.clear_stall(state)
            transcript.save_state(state)
            return live
        log_fn(f"waiting for clean tree… {live.git_detail} · {live.tests_detail}")
        if stall.ready_to_pivot(state):
            try:
                import factory_niche_runtime as niche_rt

                niche_rt.assist_stall("git_clean_wait", log_fn=log_fn)
            except Exception:  # noqa: BLE001
                pass
            stall.maybe_pivot(
                state=state,
                reason="git_clean_wait",
                quick=quick,
                log_fn=log_fn,
                live=live,
                use_agent=use_agent,
                paid_api=paid_api,
            )
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        chunk = min(remaining, pivot_sec + 0.5)
        if watcher is not None and watcher.available:
            watcher.wait(timeout=chunk)
        else:
            time.sleep(min(fallback_poll_sec, chunk))
    return None


def _git_wait_timeout(done_timeout_sec: float) -> float:
    """When continue_on_dirty, never park for hours on a dirty tree."""
    if peer_worktree.continue_on_dirty_enabled():
        return peer_worktree.dirty_wait_sec()
    return done_timeout_sec


def _agents_can_dispatch() -> bool:
    """True when another agent launch is allowed (parallel pool or single-slot)."""
    try:
        import peer_parallel_dispatch as ppd

        running = len(ppd.find_agent_procs())
        if auto.parallel_agent_dispatch_enabled():
            return running < ppd.max_parallel_agent_procs()
        return running == 0
    except Exception:  # noqa: BLE001
        return peer_terminal.find_agent_proc() is None


def _dispatch_agent_cycle(
    *,
    quick: bool,
    log_fn,
    state: dict,
    paid_api: bool,
    work_cwd: Path,
    dirty_continue: bool,
) -> tuple[int, bool]:
    """Launch cursor-agent(s) — parallel niche pool when enabled."""
    if auto.parallel_agent_dispatch_enabled():
        try:
            import peer_orchestrate as po
            import peer_parallel_dispatch as ppd

            plan = po.build_plan(quick=quick, loop=True)
            import peer_roles as roles

            hub_pool = roles.worker_pool_size(auto.load_tasks_config())
            assignments = roles.hub_pool_assignments(list(plan.role_assignments or []))
            try:
                import peer_agent_board as board

                roster = board.ensure_roster()
                roster_asn = roles.hub_pool_assignments(board.roster_assignments(roster))
                if len(roster_asn) >= hub_pool and len(roster_asn) > len(assignments):
                    assignments = roster_asn
                    log_fn(
                        f"parallel: improve roster — {len(assignments)} niche(s) "
                        f"(plan had {len(plan.role_assignments or [])})"
                    )
            except Exception as exc:  # noqa: BLE001
                log_fn(f"parallel: roster merge skipped ({exc})")

            assignments = roles.hub_pool_assignments(assignments)
            if assignments and not plan.stop:
                # Never launch/ensure more hub niches than worker_pool_size (hub cap ≤8).
                cap = min(ppd.hub_dispatch_cap(), hub_pool)
                running = ppd.effective_hub_running()
                log_fn(
                    f"parallel dispatch — {len(assignments)} niche(s), "
                    f"hub {hub_pool}, hub_cap {cap}, {running} hub running"
                )
                pool = peer_worktree.ensure_parallel_pool(count=hub_pool, log_fn=log_fn)
                return ppd.run_parallel_niche_cycle(
                    assignments,
                    pool,
                    log_fn=log_fn,
                    paid_api=paid_api,
                    max_workers=cap,
                )
        except Exception as exc:  # noqa: BLE001
            log_fn(f"parallel dispatch: fallback to single agent ({exc})")

    return dispatch_peer_prompt(
        quick=quick,
        mode="background",
        clipboard_only=False,
        press_enter=False,
        log_fn=log_fn,
        state=state,
        paid_api=paid_api,
        cwd=work_cwd,
        dirty_continue=dirty_continue,
    )


def _run_terminal_cycle(
    *,
    quick: bool,
    log_fn,
    state: dict,
    fallback_poll_sec: float,
    done_timeout_sec: float,
    paid_api: bool,
    watcher: transcript.PeerEventWatcher | None = None,
    live: auto.LiveState | None = None,
) -> bool:
    """Run one cursor-agent cycle. Returns auth_failed.

    Intelligence gates:
    - noop backoff when last ok cycle left the same queue fingerprint
    - verify gate: retry once, classify failure_type into last_cycle
    - verify must pass before ram install / continuous continue
    - last_cycle recorded into state for the next prompt
    - continue_on_dirty: never wait hours for clean; isolate via worktree when possible
    """
    if not auto.has_loop_work(auto.load_context_md(), auto.load_work_queue_md()):
        return False

    if not _mechanical_pre_dispatch(log_fn=log_fn, role_id="orchestrator"):
        log_fn("intelligence: skip primary — plan-gate hard block (error-adapt pivoted)")
        # Never idle: parallel niches / forge may still run; wake improve.
        try:
            import peer_error_adapt as err_adapt

            err_adapt._wake_loops(log_fn=log_fn)
        except Exception:  # noqa: BLE001
            pass
        return False

    fp_before, _items = transcript.current_queue_fingerprint()
    live = live or auto.measure_live_state(quick=True)
    remaining = _noop_remaining_or_clear(state=state, log_fn=log_fn)
    if remaining > 0:
        log_fn(
            f"intelligence: noop backoff {remaining:.0f}s — "
            f"queue fingerprint {fp_before} unchanged after last ok cycle"
        )
        stall.maybe_pivot(
            state=state,
            reason="noop_backoff",
            quick=quick,
            log_fn=log_fn,
            live=live,
            use_agent=False,
            paid_api=paid_api,
        )
        return False

    work_cwd, isolated = _resolve_coding_cwd(live, log_fn)
    dirty_continue = (not live.git_clean) and peer_worktree.continue_on_dirty_enabled()

    label = "paid API" if paid_api else "desktop login"
    log_fn(
        f"terminal cycle — cursor-agent ({label})"
        + (" · continue_on_dirty" if dirty_continue else "")
        + (f" · isolate={work_cwd}" if isolated else "")
    )
    rc, auth_failed = _dispatch_agent_cycle(
        quick=quick,
        log_fn=log_fn,
        state=state,
        paid_api=paid_api,
        work_cwd=work_cwd,
        dirty_continue=dirty_continue,
    )
    if rc != 0:
        # OVERSEER_AGENT_EXIT_SOFT_2026_09_04 — SIGKILL/-9 or non-zero without red
        # tests is soft Episodic (do not freeze factory on agent exit alone).
        # OVERSEER_AGENT_EXIT_SOFT_VERIFY_OK_LAND_2026_09_04 — soft must NOT
        # stamp verify_ok=False (poisoned last_cycle → verify-gate FAIL +
        # rc≠0 critical stagnation + live-log instant-react forever).
        tests_still_ok = False
        try:
            tests_still_ok = bool(auto.measure_live_state(quick=True).tests_ok)
        except Exception:  # noqa: BLE001
            tests_still_ok = False
        soft = (rc < 0) or tests_still_ok
        transcript.record_cycle_outcome(
            state,
            rc=rc,
            verify_ok=bool(soft),
            queue_fp_before=fp_before,
            queue_fp_after=fp_before,
            note=(
                "cursor-agent non-zero exit (soft Episodic)"
                if soft
                else "cursor-agent non-zero exit"
            ),
            failure_type="agent_exit_soft" if soft else None,
        )
        try:
            import peer_error_adapt as err_adapt

            err_adapt.adapt_agent_failure(
                rc=rc,
                note="cursor-agent non-zero exit",
                log_fn=log_fn,
                state=state,
                auth_failed=auth_failed,
                use_agent=not auth_failed,
                paid_api=paid_api,
                quick=quick,
            )
        except Exception as exc:  # noqa: BLE001
            log_fn(f"intelligence: error-adapt after agent fail ({exc})")
        return auth_failed

    # cursor-agent is synchronous — git state is final when subprocess returns.
    if not auto.measure_live_state(quick=True).git_clean:
        if dirty_continue:
            log_fn(
                "terminal: tree still dirty — continue_on_dirty "
                f"(wait ≤{_git_wait_timeout(done_timeout_sec):.0f}s then keep coding)"
            )
        else:
            log_fn("terminal: agent produced changes (git dirty)")

    cleaned = wait_for_git_clean(
        fallback_poll_sec=fallback_poll_sec,
        timeout_sec=_git_wait_timeout(done_timeout_sec),
        log_fn=log_fn,
        watcher=watcher,
        state=state,
        quick=quick,
        use_agent=True,
        paid_api=paid_api,
    )
    if cleaned is None:
        if dirty_continue:
            log_fn(
                "intelligence: continue_on_dirty — skipping long clean wait; "
                "verify tests and keep coding"
            )
        else:
            transcript.record_cycle_outcome(
                state,
                rc=rc,
                verify_ok=False,
                queue_fp_before=fp_before,
                queue_fp_after=fp_before,
                note="git-clean wait timed out",
            )
            lc = state.get("last_cycle")
            if isinstance(lc, dict):
                lc["failure_type"] = "timeout"
                transcript.save_state(state)
            log_fn("intelligence: holding — git never cleaned (verify skipped)")
            return False

    log_fn("intelligence: post-agent verify gate")
    failures, failure_type, verify_retries = run_peer_tasks.run_verify_gate(log_fn=log_fn)
    if failures == -1 and failure_type == "deferred":
        log_fn("intelligence: verify deferred — swarm draining; retry next wake")
        # OVERSEER_LAND_MARK_LOCAL_VERIFY_DEFERRED
        # Atomic failure_type on record — never post-stamp deferred after a green
        # verify_ok (greases last_cycle poison: verify_ok=True + deferred).
        # OVERSEER_ATOMIC_DEFERRED_FT_2026_09_04
        transcript.record_cycle_outcome(
            state,
            rc=rc,
            verify_ok=False,
            queue_fp_before=fp_before,
            queue_fp_after=fp_before,
            note="verify deferred (swarm/lock)",
            failure_type="deferred",
        )
        lc = state.get("last_cycle")
        if isinstance(lc, dict):
            # Keep deferred stamp even if a mock/partial record dropped it.
            lc.setdefault("failure_type", "deferred")
            lc["verify_retries"] = verify_retries
            transcript.save_state(state)
        return False
    verify_ok = failures == 0
    fp_after, _ = transcript.current_queue_fingerprint()
    if verify_ok:
        note = "verify ok after retry" if verify_retries else ""
        if dirty_continue and not (cleaned and cleaned.git_clean):
            note = (note + "; " if note else "") + "continue_on_dirty (tests ok, tree dirty)"
    else:
        bits = [f"verify had {failures} failure(s)"]
        if failure_type:
            bits.append(f"type={failure_type}")
        if verify_retries:
            bits.append(f"retried={verify_retries}")
        note = "; ".join(bits)
    transcript.record_cycle_outcome(
        state,
        rc=rc,
        verify_ok=verify_ok,
        queue_fp_before=fp_before,
        queue_fp_after=fp_after,
        note=note,
    )
    _emit_peer_cycle(state, log_fn=log_fn)
    if not verify_ok:
        lc = state.get("last_cycle")
        if isinstance(lc, dict):
            lc["failure_type"] = failure_type or "other"
            lc["verify_retries"] = verify_retries
            transcript.save_state(state)
        log_fn(
            f"intelligence: verify FAIL ({failures}"
            + (f", {failure_type}" if failure_type else "")
            + f", retries={verify_retries}) — "
            "not installing / not continuous-redispatching until green"
        )
        try:
            import factory_niche_runtime as niche_rt

            niche_rt.assist_verify_fail(failure_type, note, log_fn=log_fn)
        except Exception as exc:  # noqa: BLE001
            log_fn(f"niche-assist: verify ({exc})")
        try:
            import autonomous_repair as ar

            if ar.enabled():
                ar.repair_verify_failure(
                    log_fn=log_fn,
                    state=state,
                    paid_api=paid_api,
                    failure_type=failure_type,
                )
        except Exception as exc:  # noqa: BLE001
            log_fn(f"autonomous repair: failed ({exc})")
        return False
    if verify_retries:
        lc = state.get("last_cycle")
        if isinstance(lc, dict):
            lc["verify_retries"] = verify_retries
            lc["failure_type"] = None
            transcript.save_state(state)

    if cleaned and cleaned.git_clean:
        _maybe_adapt(log_fn)

    if verify_ok:
        _after_verify_ok(log_fn=log_fn, note=note)
        if dirty_continue and not auto.measure_live_state(quick=True).git_clean:
            log_fn(
                "intelligence: continue_on_dirty — verify green; "
                "auto-commit ran (tree may still be dirty until next cycle)"
            )

    if fp_before == fp_after:
        log_fn(
            f"intelligence: queue fingerprint unchanged ({fp_after}) — "
            f"noop backoff {NOOP_BACKOFF_SEC:.0f}s armed"
        )
    return False


def _maybe_dispatch_on_turn(
    *,
    quick: bool,
    mode: str,
    clipboard_only: bool,
    press_enter: bool,
    log_fn,
    state: dict,
    paid_api: bool,
    use_agent: bool,
    meta: transcript.TranscriptMeta | None,
    path: Path | None,
    live: auto.LiveState,
    watcher: transcript.PeerEventWatcher | None,
    fallback_poll_sec: float,
    done_timeout_sec: float,
) -> tuple[dict, bool]:
    """Dispatch when turn_ended (continue_on_dirty skips clean-tree stall). Returns (state, auth_failed)."""
    if meta is None or not transcript.output_generated(meta, state):
        return state, False

    if not live.git_clean:
        if peer_worktree.continue_on_dirty_enabled():
            log_fn("turn: dirty tree — continue_on_dirty (dispatch without clean wait)")
        else:
            cleaned = wait_for_git_clean(
                fallback_poll_sec=fallback_poll_sec,
                timeout_sec=done_timeout_sec,
                log_fn=log_fn,
                watcher=watcher,
                state=state,
                quick=quick,
                use_agent=use_agent,
                paid_api=paid_api,
            )
            if cleaned is None:
                return state, False
            live = cleaned

    if not live.git_clean and not peer_worktree.continue_on_dirty_enabled():
        return state, False

    log_fn(
        f"turn ended — {transcript.conversation_summary_for_log(path)} "
        f"(lines {state.get('processed_lines', 0)}→{meta.line_count})"
    )

    if use_agent and mode in ("background", "terminal"):
        auth_failed = _run_terminal_cycle(
            quick=quick,
            log_fn=log_fn,
            state=state,
            fallback_poll_sec=fallback_poll_sec,
            done_timeout_sec=done_timeout_sec,
            paid_api=paid_api,
            watcher=watcher,
            live=live,
        )
        # Always advance — otherwise the same turn_ended re-fires forever.
        state = transcript.mark_processed(meta, state)
        if auth_failed:
            return state, True
        return state, False

    # Background local-only: no terminal/clipboard/UI — mark turn; caller runs verify.
    if mode == "background" and not use_agent:
        log_fn("turn: local-only (cursor-agent not logged in — no clipboard/UI)")
        state = transcript.mark_processed(meta, state)
        return state, False

    next_input = transcript.build_next_input(quick=quick)
    if not next_input:
        state = transcript.mark_processed(meta, state)
        return state, False

    rc, auth_failed = dispatch_prompt_text(
        next_input,
        mode=mode,
        clipboard_only=clipboard_only,
        press_enter=press_enter,
        log_fn=log_fn,
        transcript_path=path,
        state=state,
        paid_api=paid_api,
    )
    # Always mark processed so a failed paste/auth cannot spin the same turn.
    state = transcript.mark_processed(meta, state)
    # Do NOT _after_verify_ok on tests_ok alone — that skips run_verify_commands
    # and can auto_commit_after_verify unverified WIP (flaw-research gate).
    return state, auth_failed


def _maybe_adapt(log_fn) -> None:
    """Quick adapt when git fingerprint changed since last heal."""
    try:
        import automation_adapt as adapt

        if adapt.should_re_adapt(ROOT):
            log_fn("adapt: git changed — subprocess quick heal (fresh refuse-null)")
            adapt.run_heal_fresh(write=True, target=ROOT, quick=True, force=False)
    except Exception as exc:  # noqa: BLE001 — never block loop on adapt
        log_fn(f"adapt: skipped ({exc})")


def _prepare_continuous_prompts(*, quick: bool, log_fn) -> None:
    """Refresh improve-driven prompts for the next agent/local cycle.

    OVERSEER_PREPARE_PROMPTS_TTL_2026_09_06 — skip gather/write when on-disk
    prompts + fp stamp are age-fresh (continuous wake was re-gathering every tick).
    """
    if not auto.improve_drives_automation():
        try:
            import cursor_self_improve as csi

            suggestion = csi.build_peer_suggestion(quick=quick, loop=True)
            if suggestion:
                path = peer_terminal.write_prompt_file(suggestion)
                log_fn(f"continuous: legacy peer prompt → {path}")
        except Exception as exc:  # noqa: BLE001
            log_fn(f"continuous: legacy peer prompt skipped ({exc})")
    try:
        import automation_improve as improve

        if improve.write_prompts_age_fresh():
            age = improve.write_prompts_fp_age_sec()
            ttl = improve.write_prompts_ttl_sec()
            age_s = f"{age:.1f}s" if age is not None else "?"
            log_fn(
                f"continuous: automation_improve gather deferred "
                f"(prompts age-fresh age={age_s} ttl={ttl:.0f}s)"
            )
            return
        signals = improve.gather_signals(
            quick=quick, research=False, refresh_trends=False, audit=False
        )
        paths = improve.write_prompts(signals, plan=True, execute=True, combined=True)
        log_fn(f"continuous: automation_improve prompts → {len(paths)} file(s)")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"continuous: automation_improve prompts skipped ({exc})")


# Skip ensure_parallel_pool on inventory ticks when floor dirs exist and a recent
# ensure already paid the cost (continuous wake was ~85–95ms/ensure every cycle).
EMIT_ENSURE_TTL_SEC = 60.0
_emit_ensure_at: float = 0.0


def clear_emit_ensure_cache() -> None:
    """Drop emit-ensure TTL stamp (tests + forced pool refresh)."""
    global _emit_ensure_at
    _emit_ensure_at = 0.0


def _hub_parallel_floor_ready(target: int) -> bool:
    """True when hub ``.worktrees/peer-0..N-1`` directories exist (cheap is_dir)."""
    n = max(0, int(target or 0))
    if n <= 0:
        return True
    try:
        hub = peer_worktree.primary_worktree_root(ROOT)
    except Exception:  # noqa: BLE001
        hub = ROOT
    rel_base, prefix = peer_worktree.parallel_pool_config()
    base = hub / rel_base
    for i in range(n):
        if not (base / f"{prefix}-{i}").is_dir():
            return False
    return True


def _should_skip_emit_ensure(target: int) -> bool:
    """Skip ensure when floor ready, inventory healthy, and TTL warm.

    OVERSEER_EMIT_HEALTHY_INV_2026_09_07 — dir-only floor skip is unsafe when
    nested ``peer-*/.worktrees`` pollution exists; refuse TTL skip until ensure
    can prune (matches ``inventory_snapshot`` / POOL_TTL_HEALTHY_INV).
    """
    if _emit_ensure_at <= 0.0:
        return False
    if (time.monotonic() - _emit_ensure_at) >= EMIT_ENSURE_TTL_SEC:
        return False
    if not _hub_parallel_floor_ready(target):
        return False
    try:
        hub = peer_worktree.primary_worktree_root(ROOT)
    except Exception:  # noqa: BLE001
        hub = ROOT
    return peer_worktree._pool_fs_inventory_healthy(hub)


def _emit_worktree_inventory(log_fn) -> None:
    """Inventory git worktrees so parallel peers can isolate scopes (Phase 3).

    OVERSEER_EMIT_INVENTORY_TTL_LIST_SKIP_2026_09_06 — when ensure TTL is warm and
    floor dirs exist, defer porcelain ``list_worktrees`` entirely (continuous wake
    was paying git porcelain every tick after ensure-skip).

    OVERSEER_EMIT_VIA_INVENTORY_SNAPSHOT_2026_09_07 — delegate to
    ``peer_worktree.inventory_snapshot(ensure_pool=True)`` so nested pollution
    cannot stick across EMIT TTL while porcelain stays deferred.
    """
    global _emit_ensure_at
    try:
        import peer_roles as roles

        target = roles.worker_pool_size(auto.load_tasks_config())
        if _should_skip_emit_ensure(target):
            age = time.monotonic() - _emit_ensure_at
            log_fn(
                f"worktree pool: ensure skipped (floor ready, TTL "
                f"{EMIT_ENSURE_TTL_SEC:.0f}s, age={age:.1f}s)"
            )
            log_fn(
                f"worktree: porcelain list deferred "
                f"({target} parallel floor ready)"
            )
            return
        snap = peer_worktree.inventory_snapshot(
            ROOT, ensure_pool=True, log_fn=log_fn
        )
        _emit_ensure_at = time.monotonic()
        if snap.get("porcelain_deferred"):
            log_fn(
                f"worktree: porcelain list deferred "
                f"({target} parallel floor ready; inventory healthy)"
            )
            return
        pool_n = int(snap.get("parallel_count") or 0)
        if pool_n:
            log_fn(
                f"worktree pool: {pool_n} hub trees ready (target {target} peers)"
            )
        total = int(snap.get("total") or 0)
        extras = list(snap.get("parallel") or [])
        log_fn(
            f"worktree: {total} registered, {len(extras)} parallel "
            "(peer_worktree.inventory_snapshot)"
        )
        for e in extras[:6]:
            if isinstance(e, dict):
                path = e.get("path") or "?"
                label = e.get("branch") or e.get("head") or "?"
            else:
                path = getattr(e, "path", "?")
                label = (
                    getattr(e, "branch", None)
                    or ("detached" if getattr(e, "detached", False) else "")
                    or (getattr(e, "head", "") or "?")[:12]
                )
            log_fn(f"worktree: parallel {path} ({label})")
        if not extras:
            log_fn(
                "worktree: no parallel trees — add via "
                "python3 scripts/peer_worktree.py add .worktrees/peer-N -b peer/N --create-branch"
            )
    except Exception as exc:  # noqa: BLE001
        log_fn(f"worktree pool: ensure skipped ({exc})")


_ASI_CLOSE_TOKEN_RE = re.compile(
    r"\[asi phase:[a-z0-9_]+\]|\[maximize-parallel\]",
    re.IGNORECASE,
)


def _asi_close_tokens_open(queue_md: str | None = None) -> bool:
    """True when unchecked WQ has an ASI-phase or maximize-parallel close target."""
    text = auto.load_work_queue_md() if queue_md is None else queue_md
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped.startswith("- [ ]"):
            continue
        if _ASI_CLOSE_TOKEN_RE.search(stripped):
            return True
    return False


def _close_completed_asi_phase_plans(log_fn, *, queue_md: str | None = None) -> bool:
    """Check off completed ASI phase plans + fully-green maximize-parallel kit line."""
    if not _asi_close_tokens_open(queue_md):
        return False
    try:
        import asi_rubric
        import automation_improve as improve

        result = asi_rubric.compute_asi_rubric(improve.gather_signals(quick=True))
    except Exception as exc:  # noqa: BLE001
        log_fn(f"asi plans: close skipped ({exc})")
        return False
    completed = set(result.completed_phase_ids or ())
    close_maximize = False
    for phase in result.phases:
        if not isinstance(phase, dict):
            continue
        for c in phase.get("criteria") or []:
            if str(c.get("id") or "") == "maximize_parallel" and float(c.get("score") or 0) >= 1.0:
                close_maximize = True

    def _match(line: str) -> bool:
        lowered = line.lower()
        # Exact phase-token only (not body text that mentions an older phase id).
        for phase_id in completed:
            token = f"[asi phase:{phase_id}]"
            if token in lowered:
                return True
        # Title-shaped maximize item only — not ASI plan bodies that mention the phrase.
        if close_maximize and "maximize parallel task peers" in lowered and "[asi phase:" not in lowered:
            return True
        return False

    closed = auto.check_off_queue_lines(match=_match)
    if closed:
        log_fn(f"asi plans: checked off {len(closed)} completed item(s)")
        for item in closed[:4]:
            log_fn(f"asi plans: done — {item[:100]}")
        return True
    return False


def _run_local_continuous(
    *,
    quick: bool,
    log_fn,
    state: dict,
    open_items: list | None = None,
) -> bool:
    """Keep working without cursor-agent: refresh prompts + local verify tick.

    Returns True when the caller should immediately continue (queue advanced / work done).
    Runs even when git is dirty — still refreshes prompts and verifies what it can.

    When ``open_items`` is provided, noop backoff uses ``len(open_items)`` and skips
    remasuring live queue depth (callers already paid for the list).
    """
    fp_before, _ = transcript.current_queue_fingerprint()
    if open_items is not None:
        backoff_sec = effective_noop_backoff_sec(open_queue_count=len(open_items))
        remaining = _noop_remaining_or_clear(
            state=state, log_fn=log_fn, backoff_sec=backoff_sec
        )
    else:
        remaining = _noop_remaining_or_clear(state=state, log_fn=log_fn)
    if remaining > 0:
        log_fn(f"continuous: local held — noop backoff {remaining:.0f}s")
        stall.maybe_pivot(
            state=state,
            reason="noop_backoff",
            quick=quick,
            log_fn=log_fn,
            use_agent=False,
            paid_api=False,
        )
        return False

    cooldown = transcript.local_verify_cooldown_remaining(state)
    if cooldown > 0 and bool(auto.CFG.get("autonomy_never_delay_on_error", True)):
        lc = state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else {}
        if isinstance(lc, dict) and lc.get("verify_ok") is False:
            try:
                import peer_error_adapt as err_adapt

                err_adapt.clear_autonomy_delays(log_fn=log_fn, reason="local-verify-fail-bypass")
                cooldown = 0.0
            except Exception:  # noqa: BLE001
                cooldown = 0.0
    log_fn("continuous: queue has work — local keep-working (prompts + verify)")
    _emit_worktree_inventory(log_fn)
    _close_completed_asi_phase_plans(log_fn)
    _prepare_continuous_prompts(quick=quick, log_fn=log_fn)
    _maybe_adapt(log_fn)
    note = "local continuous keep-working"
    soft_ft = ""
    if cooldown > 0:
        log_fn(f"continuous: verify skipped — cooldown {cooldown:.0f}s")
        # Do not invent a fresh verify pass — carry prior evidence only.
        # Never _after_verify_ok here: prior verify_ok must not auto-commit
        # unverified WIP that landed during the cooldown window.
        # Do NOT stamp failure_type=deferred here — that pairs with carried
        # verify_ok=True and trips plan-gate "last_cycle poison".
        prev = state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else {}
        if isinstance(prev, dict) and "verify_ok" in prev:
            verify_ok = bool(prev.get("verify_ok"))
        else:
            verify_ok = False
        rc = 0
        note = "local continuous keep-working; verify skipped (cooldown)"
    else:
        # _run_local_cycle calls _after_verify_ok only when ready=True (real
        # pass). Deferred/idle (rc=0, ready=False) must not auto-commit or
        # stamp verify_ok=True (that re-arms agent dispatch while swarm drains).
        verify_failed, verified = _run_local_cycle(
            quick=quick, log_fn=log_fn, state=state
        )
        rc = 1 if verify_failed else 0
        verify_ok = verified
        if not verified and not verify_failed:
            note = "local continuous keep-working; verify deferred/not-ready"
            soft_ft = "deferred"
            verify_ok = False
    fp_after, _ = transcript.current_queue_fingerprint()
    advanced = fp_before != fp_after
    # Atomic soft deferred — coerce via record_cycle_outcome (no post-stamp grease).
    # OVERSEER_ATOMIC_DEFERRED_FT_2026_09_04
    transcript.record_cycle_outcome(
        state,
        rc=rc,
        verify_ok=verify_ok,
        queue_fp_before=fp_before,
        queue_fp_after=fp_after,
        note=note,
        local_only=True,
        failure_type=soft_ft or None,
    )
    if advanced:
        log_fn("continuous: queue advanced — spinning again")
        return True
    log_fn(
        f"continuous: local tick complete — "
        f"event wait ≤{CONTINUOUS_WAKE_SEC:.0f}s (agent dispatch not blocked by local tick)"
    )
    return False


def _run_local_cycle(
    *, quick: bool, log_fn, state: dict | None = None
) -> tuple[bool, bool]:
    """Local-only tick — verify/self-check, no LLM, no clipboard, no UI.

    Honors local_only_verify_cooldown so unittest cannot storm RAM.
    Returns (verify_failed, verified) — verified only after real
    ``run_verify_commands`` pass (ready=True from run_local_cycle).
    """
    st = state if state is not None else transcript.load_state()
    cooldown = transcript.local_verify_cooldown_remaining(st)
    if cooldown > 0:
        log_fn(f"local: verify skipped — cooldown {cooldown:.0f}s")
        return False, False

    rc, ready = run_peer_tasks.run_local_cycle(quick=quick, log_fn=log_fn)
    # OVERSEER_LAND_MARK_LOCAL_VERIFY_DEFERRED — deferred/idle soft-skip
    # (rc=0, ready=False) must not arm cooldown — only mark after a real
    # verify pass or a real verify failure.
    if ready or rc != 0:
        transcript.mark_local_verify(st)
    if ready:
        _after_verify_ok(log_fn=log_fn, note="local verify cycle")
    return rc != 0, ready


def _install_sigusr1_anti_flap(log_fn) -> None:
    """Treat SIGUSR1 as poke — never die (OVERSEER_NON_NOOP_DAY_ROLLUP_2026_09_07).

    Agents sometimes ``systemctl kill -s USR1 peer-loop`` expecting nginx-style
    reload; default kills python → flap storm wipes short cycle ring / stalls
    T10-04 day rollup. Bash wrappers must also ``trap '' USR1``.
    """

    def _on_usr1(_signum: int, _frame: object) -> None:
        try:
            log_fn("SIGUSR1 ignored (anti-flap) — poke peer-turn.signal instead of exit")
            transcript.poke_turn_signal()
        except Exception:  # noqa: BLE001
            pass

    try:
        signal.signal(signal.SIGUSR1, _on_usr1)
    except (ValueError, OSError, AttributeError):
        pass


def run_forever(
    *,
    quick: bool,
    mode: str,
    clipboard_only: bool,
    press_enter: bool,
    daemon: bool,
    from_transcript: bool,
    fallback_poll_sec: float | None = None,
    done_timeout_sec: float = DEFAULT_DONE_TIMEOUT_SEC,
    paid_api: bool = False,
) -> int:
    log_fn = lambda msg: _log(msg, daemon=daemon)  # noqa: E402
    if fallback_poll_sec is None:
        fallback_poll_sec = effective_fallback_poll_sec()

    _install_sigusr1_anti_flap(log_fn)
    _maybe_adapt(log_fn)

    use_agent = False
    if mode == "background":
        if paid_api or peer_terminal.api_key_configured():
            ready, detail = peer_terminal.cursor_agent_auth_ready()
            use_agent = ready and (paid_api or not peer_terminal.api_key_configured())
            if peer_terminal.api_key_configured() and not paid_api:
                log_fn("background: CURSOR_API_KEY set — blocked without --paid-api; local-only")
                use_agent = False
            elif use_agent:
                log_fn(f"background: cursor-agent ({detail})")
            else:
                log_fn(f"background: local-only ({detail})")
        else:
            ready, detail = peer_terminal.desktop_auth_ready()
            use_agent = ready
            if use_agent:
                log_fn(f"background: cursor-agent ({detail})")
            else:
                log_fn(f"background: local-only ({detail})")
    elif mode == "terminal":
        log_fn("peer loop forever (--paid-api / cursor-agent)")
        if not paid_api:
            log_fn("terminal: refusing to run without --paid-api when CURSOR_API_KEY configured")
            return 2
        ready, detail = peer_terminal.cursor_agent_auth_ready()
        if not ready:
            log_fn(f"terminal: auth not ready — {detail}")
            log_fn(f"terminal: {peer_terminal.auth_fix_hint()}")
        use_agent = ready
    elif mode == "clipboard":
        log_fn(
            "peer loop forever (clipboard — opt-in; paste manually with ⌘V)"
            + (" · transcript-driven" if from_transcript else "")
        )
    elif from_transcript and mode == "direct-ui":
        log_fn("peer loop forever (transcript → cursor-ui inject — opt-in; steals focus)")
    else:
        log_fn("peer loop forever (event-driven)")

    watcher = transcript.PeerEventWatcher()
    if watcher.setup(repo_root=ROOT):
        mode_label = "mtime-poll" if getattr(watcher, "_mtime_mode", False) else "kqueue"
        log_fn(
            f"event-driven ({mode_label}): transcript + {transcript.SIGNAL_PATH.name} "
            f"(touch to wake; fallback={fallback_poll_sec:.0f}s)"
        )
    else:
        log_fn(f"event watch unavailable — fallback poll every {fallback_poll_sec:.0f}s")

    state = transcript.load_state()
    bootstrapped = bool(state.get("bootstrapped"))
    if not isinstance(state.get("last_cycle"), dict):
        fp, _ = transcript.current_queue_fingerprint()
        transcript.record_cycle_outcome(
            state,
            rc=0,
            verify_ok=False,
            queue_fp_before=fp,
            queue_fp_after=fp,
            note="bootstrap last_cycle on loop start (unverified)",
            local_only=True,
        )
        stall.clear_stall(state)
        log_fn("bootstrap: seeded last_cycle memory")
    last_self_heal_ts = 0.0
    try:
        self_heal_interval = max(30.0, float(auto.CFG.get("self_heal_interval_sec") or 60))
    except (TypeError, ValueError):
        self_heal_interval = 60.0

    try:
        while True:
            if time.time() - last_self_heal_ts >= self_heal_interval:
                try:
                    import peer_self_heal as self_heal

                    if self_heal.self_heal_enabled():
                        report = self_heal.run_cycle(write=True, log_fn=log_fn)
                        if report.actions:
                            log_fn(f"self-heal: {len(report.actions)} action(s)")
                        last_self_heal_ts = time.time()
                except Exception as exc:  # noqa: BLE001
                    log_fn(f"self-heal: failed ({exc})")
                    last_self_heal_ts = time.time()

            context_md = auto.load_context_md()
            live = auto.measure_live_state(quick=quick)
            stop = should_stop_loop(context_md, live)
            if stop:
                log_fn(f"peer loop done — {stop}")
                return 0

            path = transcript.find_latest_transcript()
            meta = transcript.read_transcript_meta(path)

            if (
                not bootstrapped
                and metrics_green(live)
                and auto.has_loop_work(context_md, auto.load_work_queue_md(), live=live)
            ):
                log_fn("bootstrap dispatch — peer plan")
                if use_agent and mode in ("background", "terminal"):
                    auth_failed = _run_terminal_cycle(
                        quick=quick,
                        log_fn=log_fn,
                        state=state,
                        fallback_poll_sec=fallback_poll_sec,
                        done_timeout_sec=done_timeout_sec,
                        paid_api=paid_api,
                        watcher=watcher,
                    )
                    if auth_failed:
                        use_agent = False
                        log_fn("background: cursor-agent auth failed — local-only (retry on next turn)")
                        _run_local_cycle(quick=quick, log_fn=log_fn, state=state)
                elif mode == "background" and not use_agent:
                    log_fn("bootstrap: local-only (no cursor-agent — verify only)")
                    _run_local_cycle(quick=quick, log_fn=log_fn, state=state)
                else:
                    _rc, auth_failed = dispatch_peer_prompt(
                        quick=quick,
                        mode=mode,
                        clipboard_only=clipboard_only,
                        press_enter=press_enter,
                        log_fn=log_fn,
                        state=state,
                        paid_api=paid_api,
                    )
                    if auth_failed:
                        use_agent = False
                # Always mark bootstrapped — never spin forever on auth/dispatch failure.
                bootstrapped = True
                state["bootstrapped"] = True
                if meta is not None:
                    state = transcript.mark_processed(meta, state)
                else:
                    transcript.save_state(state)
                continue

            # Continuous keep-working: event-driven wake + timed heartbeat when queue has work.
            context_md = auto.load_context_md()
            queue_md = auto.load_work_queue_md()
            has_work = auto.has_loop_work(context_md, queue_md, live=live)
            open_items = auto.loop_work_items(context_md, queue_md, live=live).open_items
            open_n = len(open_items)
            backoff_sec = effective_noop_backoff_sec(open_queue_count=open_n)
            noop_left = _noop_remaining_or_clear(
                state=state, log_fn=log_fn, backoff_sec=backoff_sec
            )
            verify_cd = transcript.local_verify_cooldown_remaining(state)
            if verify_cd > 0 and bool(auto.CFG.get("autonomy_never_delay_on_error", True)):
                lc = state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else {}
                if isinstance(lc, dict) and lc.get("verify_ok") is False:
                    try:
                        import peer_error_adapt as err_adapt

                        err_adapt.clear_autonomy_delays(log_fn=log_fn, reason="verify-fail-bypass")
                        verify_cd = 0.0
                    except Exception:  # noqa: BLE001
                        verify_cd = 0.0

            if mode == "background" and has_work and stall.stall_pivot_enabled():
                if noop_left > 0:
                    state = stall.note_stall(state, "noop_backoff")
                elif verify_cd > 0:
                    state = stall.note_stall(state, "verify_cooldown")
                elif not live.git_clean and not peer_worktree.continue_on_dirty_enabled():
                    state = stall.note_stall(state, "dirty_tree")
                else:
                    lc = state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else {}
                    if lc and not lc.get("verify_ok"):
                        # Never hold primary on verify fail when never_delay — repair+dispatch.
                        if bool(auto.CFG.get("autonomy_never_delay_on_error", True)):
                            state = stall.clear_stall(state)
                        else:
                            state = stall.note_stall(state, "verify_fail_hold")
                    else:
                        state = stall.clear_stall(state)
                transcript.save_state(state)

            if mode == "background" and has_work and noop_left <= 0:
                can_agent = use_agent and (
                    live.git_clean or peer_worktree.continue_on_dirty_enabled()
                )
                if can_agent:
                    if use_agent and not live.git_clean:
                        log_fn("continuous: git dirty — continue_on_dirty agent cycle")
                    else:
                        log_fn("continuous: queue has work — cursor-agent cycle")
                    auth_failed = _run_terminal_cycle(
                        quick=quick,
                        log_fn=log_fn,
                        state=state,
                        fallback_poll_sec=fallback_poll_sec,
                        done_timeout_sec=done_timeout_sec,
                        paid_api=paid_api,
                        watcher=watcher,
                        live=live,
                    )
                    if auth_failed:
                        use_agent = False
                        log_fn("background: cursor-agent auth failed — local-only keep-working")
                        if _run_local_continuous(
                            quick=quick, log_fn=log_fn, state=state, open_items=open_items
                        ):
                            continue
                    else:
                        lc = state.get("last_cycle") or {}
                        # Spin only on green non-noop. Deferred soft-skip must not
                        # re-dispatch (stale verify_ok or race while swarm drains).
                        if _should_spin_after_agent_cycle(lc):
                            continue
                        # verify fail or noop → fall through to timed event wait
                else:
                    # Local-only (no agent): still keep working (prompts + verify).
                    if use_agent and not live.git_clean:
                        log_fn("continuous: git dirty — local keep-working (continue_on_dirty off)")
                    if _run_local_continuous(
                        quick=quick, log_fn=log_fn, state=state, open_items=open_items
                    ):
                        continue

            elif mode == "background" and has_work and noop_left > 0 and stall.ready_to_pivot(state):
                try:
                    import factory_niche_runtime as niche_rt

                    niche_rt.assist_stall("noop_backoff", log_fn=log_fn)
                except Exception:  # noqa: BLE001
                    pass
                stall.maybe_pivot(
                    state=state,
                    reason="noop_backoff",
                    quick=quick,
                    log_fn=log_fn,
                    live=live,
                    use_agent=use_agent,
                    paid_api=paid_api,
                )
            elif (
                mode == "background"
                and has_work
                and verify_cd > 0
                and stall.ready_to_pivot(state)
            ):
                try:
                    import factory_niche_runtime as niche_rt

                    niche_rt.assist_stall("verify_cooldown", log_fn=log_fn)
                except Exception:  # noqa: BLE001
                    pass
                stall.maybe_pivot(
                    state=state,
                    reason="verify_cooldown",
                    quick=quick,
                    log_fn=log_fn,
                    live=live,
                    use_agent=use_agent,
                    paid_api=paid_api,
                )
            elif (
                mode == "background"
                and has_work
                and stall.ready_to_pivot(state)
            ):
                lc = state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else {}
                if lc and not lc.get("verify_ok"):
                    try:
                        import autonomous_repair as ar

                        if ar.enabled():
                            ar.repair_verify_failure(
                                log_fn=log_fn,
                                state=state,
                                paid_api=paid_api,
                                failure_type=str(lc.get("failure_type") or ""),
                            )
                    except Exception as exc:  # noqa: BLE001
                        log_fn(f"autonomous repair: stall pivot failed ({exc})")

            if mode == "background":
                if has_work:
                    wake = continuous_wake_timeout(
                        has_work=True,
                        noop_remaining=noop_left,
                        open_queue_count=open_n,
                    )
                    log_fn(
                        f"idle: event wait ≤{wake:.0f}s "
                        "(kqueue transcript/git/signal OR continuous heartbeat)"
                    )
                else:
                    log_fn("idle: queue empty — waiting for transcript/signal/git event")

            wake_timeout = continuous_wake_timeout(
                has_work=has_work,
                noop_remaining=noop_left,
                open_queue_count=open_n,
            )
            event = watcher.wait(timeout=wake_timeout) if watcher.available else transcript.PeerEvent(reason="fallback")
            if not watcher.available:
                time.sleep(wake_timeout if wake_timeout is not None else fallback_poll_sec)
            elif event.reason == "timeout" and has_work:
                log_fn("continuous: heartbeat — wake to keep working")
                if use_agent and noop_left <= 0 and _agents_can_dispatch():
                    running = peer_terminal.count_agent_procs()
                    cap = auto.max_parallel_agent_procs() if auto.parallel_agent_dispatch_enabled() else 1
                    log_fn(
                        f"continuous: heartbeat — dispatch cursor-agent "
                        f"({running}/{cap} running, queue open)"
                    )
                    auth_failed = _run_terminal_cycle(
                        quick=quick,
                        log_fn=log_fn,
                        state=state,
                        fallback_poll_sec=fallback_poll_sec,
                        done_timeout_sec=done_timeout_sec,
                        paid_api=paid_api,
                        watcher=watcher,
                        live=live,
                    )
                    if auth_failed:
                        use_agent = False
                elif stall.stall_pivot_enabled() and (noop_left > 0 or verify_cd > 0):
                    reason = "noop_backoff" if noop_left > 0 else "verify_cooldown"
                    stall.maybe_pivot(
                        state=state,
                        reason=reason,
                        quick=quick,
                        log_fn=log_fn,
                        live=live,
                        use_agent=use_agent,
                        paid_api=paid_api,
                    )

            # Re-check desktop auth each wake — login mid-session upgrades without reinstall.
            if mode == "background" and not paid_api and not peer_terminal.api_key_configured():
                ready, detail = peer_terminal.desktop_auth_ready()
                if ready and not use_agent:
                    use_agent = True
                    log_fn(f"background: cursor-agent now ready ({detail})")
                elif not ready and use_agent:
                    use_agent = False
                    log_fn(f"background: cursor-agent lost auth — local-only ({detail})")

            # OVERSEER_SKIP_POST_WAIT_FIND_LATEST_2026_09_05 — timeout/fallback
            # reuse loop-head path/meta/live (hub port from peer-1 L119).
            _event_reason = str(getattr(event, "reason", "") or "")
            _timed_out = _event_reason == "timeout"
            _watch_ok = bool(getattr(watcher, "available", False))
            if not should_skip_post_wait_transcript_rescan(
                timed_out=_timed_out,
                watcher_available=_watch_ok,
                event_reason=_event_reason,
            ):
                path = transcript.find_latest_transcript()
                meta = transcript.read_transcript_meta(path)
            if not should_skip_post_wait_live_refresh(
                timed_out=_timed_out,
                watcher_available=_watch_ok,
                event_reason=_event_reason,
            ):
                live = auto.measure_live_state(quick=quick)

            if from_transcript or mode in ("background", "terminal", "clipboard", "direct-ui"):
                state, auth_failed = _maybe_dispatch_on_turn(
                    quick=quick,
                    mode=mode,
                    clipboard_only=clipboard_only,
                    press_enter=press_enter,
                    log_fn=log_fn,
                    state=state,
                    paid_api=paid_api,
                    use_agent=use_agent,
                    meta=meta,
                    path=path,
                    live=live,
                    watcher=watcher,
                    fallback_poll_sec=fallback_poll_sec,
                    done_timeout_sec=done_timeout_sec,
                )
                if auth_failed:
                    use_agent = False
                    log_fn("background: cursor-agent auth failed — local-only (retry on next turn)")
                    continue

            # Local-only wake: prompts already refreshed in continuous path; skip duplicate
            # verify here — cooldown in _run_local_cycle covers heartbeat/signal ticks.
            if (
                mode == "background"
                and not use_agent
                and live.git_clean
                and has_work
                and event.reason in ("timeout", "signal", "git")
                and transcript.local_verify_cooldown_remaining(state) <= 0
            ):
                _run_local_cycle(quick=quick, log_fn=log_fn, state=state)

            if not live.git_clean:
                if peer_worktree.continue_on_dirty_enabled():
                    # Do not park the forever loop on dirty main — heartbeat will
                    # re-enter continuous agent cycles.
                    pass
                else:
                    cleaned = wait_for_git_clean(
                        fallback_poll_sec=fallback_poll_sec,
                        timeout_sec=min(done_timeout_sec, CONTINUOUS_WAKE_SEC * 4),
                        log_fn=log_fn,
                        watcher=watcher,
                        state=state,
                        quick=quick,
                        use_agent=use_agent,
                        paid_api=paid_api,
                    )
                    if cleaned and metrics_green(cleaned):
                        # metrics_green ≠ verify gate — only auto-commit after real pass.
                        import run_peer_tasks as _rpt

                        failures, failure_type, _retries = _rpt.run_verify_gate(
                            log_fn=log_fn, retry_once=False
                        )
                        if failures == 0:
                            _after_verify_ok(log_fn=log_fn, note="git clean event")
                        else:
                            log_fn(
                                "intelligence: git clean — metrics green but verify "
                                f"not passed (failures={failures}"
                                + (f", {failure_type}" if failure_type else "")
                                + "); skip auto-commit"
                            )
                        # Clean again — immediately keep working if queue still open.
                        continue

            if event.reason == "git" and meta is not None and not meta.turn_ended:
                continue
    finally:
        watcher.close()


def plist_body(*, install_mode: str = "background") -> str:
    """install_mode: background (default) | clipboard | direct-ui | paid-api"""
    py = sys.executable
    script = SCRIPTS / "peer_loop.py"
    args = [py, str(script), "--forever", "--daemon", "--quick"]
    env_extra = ""
    if install_mode == "paid-api":
        args.append("--paid-api")
        env_extra = """
    <key>PEER_LOOP_PAID_API</key>
    <string>1</string>"""
    elif install_mode == "clipboard":
        args.extend(["--from-transcript", "--clipboard-only"])
        env_extra = """
    <key>CURSOR_MINIMIZED</key>
    <string>1</string>"""
    elif install_mode == "direct-ui":
        args.extend(["--from-transcript", "--direct-ui"])
    else:
        args.append("--background")
    args_xml = "\n".join(f"    <string>{a}</string>" for a in args)
    home = Path.home()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
{args_xml}
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>WorkingDirectory</key>
  <string>{ROOT}</string>
  <key>StandardOutPath</key>
  <string>{LOG_PATH}</string>
  <key>StandardErrorPath</key>
  <string>{LOG_PATH}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>{home}</string>
    <key>PATH</key>
    <string>{home}/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>{env_extra}
  </dict>
</dict>
</plist>
"""


def _cmd_install_body(*, install_mode: str = "background", force: bool = False) -> int:
    """Bootstrap peer LaunchAgent without taking the daemon-heal flock (caller may hold it)."""
    # OVERSEER_PEER_LINUX_INSTALL_2026_09_04 — Linux has no launchctl; mirror improve/oversight.
    if sys.platform != "darwin":
        import peer_self_heal as heal

        heal.ensure_canonical_module()
        print(heal.linux_install_daemon("peer"))
        return 0
    global LABEL, PLIST_PATH, LOG_PATH
    # Re-read disk config so stale long-running healers (hub twin) don't install wrong labels.
    import automation_config as cfg_mod

    cfg = cfg_mod.load_config()
    ns = str(cfg.get("config_namespace") or "automation")
    LABEL = str(cfg.get("launch_agent_label") or f"com.togi.{ns}-peer-loop")
    PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    LOG_PATH = auto.CONFIG_DIR / "peer-loop.log"
    # Prefer live config_dir if namespace drifted in-process.
    try:
        live_dir = Path.home() / ".config" / ns
        LOG_PATH = live_dir / "peer-loop.log"
    except Exception:  # noqa: BLE001
        pass

    uid = os.getuid()
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(plist_body(install_mode=install_mode))
    import peer_self_heal as heal

    heal.ensure_canonical_module()
    if not force and heal._launchctl_running(LABEL):
        print(f"peer loop agent: {PLIST_PATH}")
        print(f"log: {LOG_PATH}")
        print(f"already running ({LABEL}) — plist refreshed; skip bootout")
        if install_mode == "background":
            ready, detail = peer_terminal.desktop_auth_ready()
            if ready:
                print(f"runs forever — background terminal (cursor-agent: {detail})")
            else:
                print(f"runs forever — background local-only ({detail}; no clipboard, no Cursor UI)")
        return 0
    # Loaded but stopped: kickstart only — bootout thrash was SIGTERM-looping healthy agents.
    if not force and heal._launchctl_loaded(LABEL):
        nudge = heal._kickstart(LABEL)
        print(f"peer loop agent: {PLIST_PATH}")
        print(f"log: {LOG_PATH}")
        print(f"already loaded ({LABEL}) — {nudge}; skip bootout")
        if heal._wait_launchctl_running(LABEL, attempts=4, delay_sec=0.4):
            return 0
        print(f"WARNING: kickstart did not yield PID — try --force to rebootstrap", file=sys.stderr)
        return 1
    if force or heal._launchctl_loaded(LABEL):
        subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], capture_output=True)
        time.sleep(1.0)
    proc = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "bootstrap failed").strip()
        # Already loaded race: kickstart instead of failing hard.
        if "already" in err.lower() or "in use" in err.lower():
            nudge = heal._kickstart(LABEL)
            print(f"peer loop agent: {PLIST_PATH}")
            print(f"log: {LOG_PATH}")
            print(f"bootstrap race — {nudge}")
            return 0 if heal._wait_launchctl_running(LABEL, attempts=4, delay_sec=0.4) else 1
        print(err, file=sys.stderr)
        return 1
    print(f"peer loop agent: {PLIST_PATH}")
    print(f"log: {LOG_PATH}")
    if install_mode == "paid-api":
        ready, detail = peer_terminal.cursor_agent_auth_ready()
        print("WARNING: --paid-api mode — cursor-agent bills API quota", file=sys.stderr)
        print("runs forever via cursor-agent in terminal — never switches to Cursor UI")
        if ready:
            print(f"auth: ok ({detail})")
        else:
            print(f"WARNING: cursor-agent auth not ready — {detail}", file=sys.stderr)
            print(peer_terminal.auth_fix_hint(), file=sys.stderr)
    elif install_mode == "background":
        ready, detail = peer_terminal.desktop_auth_ready()
        if ready:
            print(f"runs forever — background terminal (cursor-agent: {detail})")
        else:
            print(f"runs forever — background local-only ({detail}; no clipboard, no Cursor UI)")
    elif install_mode == "clipboard":
        print("runs forever — $0 clipboard + transcript (CURSOR_MINIMIZED=1, paste manually with ⌘V)")
    else:
        print("runs forever — cursor-ui inject + transcript (opt-in; steals focus)")
        print(f"tradeoff: {peer_cursor.accessibility_hint()}", file=sys.stderr)
    return 0


def cmd_install(*, install_mode: str = "background", force: bool = False) -> int:
    import peer_self_heal as heal

    heal.ensure_canonical_module()
    with heal._daemon_heal_flock():
        return _cmd_install_body(install_mode=install_mode, force=force)


def cmd_uninstall() -> int:
    # OVERSEER_PEER_LINUX_INSTALL_2026_09_04 — stop/disable systemd peer unit on Linux.
    if sys.platform != "darwin":
        import peer_self_heal as heal

        heal.ensure_canonical_module()
        print(heal.linux_uninstall_daemon("peer"))
        return 0
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], capture_output=True)
    if PLIST_PATH.is_file():
        PLIST_PATH.unlink()
    print("peer loop agent removed")
    return 0


def _resolve_mode(args: argparse.Namespace) -> str:
    """Background terminal is default; clipboard, cursor-ui, paid-api are opt-in."""
    if args.paid_api:
        return "terminal"
    if args.direct_ui or args.cursor_ui:
        return "direct-ui"
    if args.clipboard_only:
        return "clipboard"
    if args.background or args.terminal:
        return "background"
    return "background"


def _resolve_install_mode(args: argparse.Namespace) -> str:
    if args.paid_api:
        return "paid-api"
    if args.direct_ui or args.cursor_ui:
        return "direct-ui"
    if args.clipboard_only:
        return "clipboard"
    if args.background or args.terminal:
        return "background"
    return "background"


def main() -> int:
    parser = argparse.ArgumentParser(description="Forever peer orchestration loop")
    parser.add_argument("--forever", action="store_true", help="Run until Loop: exhausted")
    parser.add_argument(
        "--background",
        action="store_true",
        help="Background terminal (default for --install and --forever)",
    )
    parser.add_argument(
        "--paid-api",
        action="store_true",
        help="Opt-in: cursor-agent with CURSOR_API_KEY (bills API quota)",
    )
    parser.add_argument(
        "--terminal",
        action="store_true",
        help="Alias for --background (not paid API)",
    )
    parser.add_argument(
        "--direct-ui",
        action="store_true",
        help="Opt-in: activate Cursor and inject via AX (steals focus)",
    )
    parser.add_argument(
        "--cursor-ui",
        action="store_true",
        help="Alias for --direct-ui (legacy name)",
    )
    parser.add_argument(
        "--from-transcript",
        action="store_true",
        help="Dispatch on transcript turn_ended (clipboard/direct-ui modes)",
    )
    parser.add_argument("--once", action="store_true", help="Single dispatch")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Live terminal dashboard (WORKING vs IDLE) — see peer_watch.py",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="One-shot peer-loop status snapshot (same as peer_watch --once)",
    )
    parser.add_argument("--daemon", action="store_true", help="Log to file (LaunchAgent)")
    parser.add_argument("--install", action="store_true", help="Install KeepAlive LaunchAgent")
    parser.add_argument("--uninstall", action="store_true", help="Remove LaunchAgent")
    parser.add_argument("--quick", action="store_true", help="Cache tests/RSS until git changes")
    parser.add_argument(
        "--clipboard-only",
        action="store_true",
        help="Opt-in: copy prompt to clipboard for manual ⌘V paste",
    )
    parser.add_argument("--no-enter", action="store_true", help="Paste without Return (cursor-ui)")
    parser.add_argument(
        "--done-timeout-sec",
        type=float,
        default=DEFAULT_DONE_TIMEOUT_SEC,
        help="Safety net max wait for git-clean / agent subprocess (default: 7200s)",
    )
    args = parser.parse_args()

    mode = _resolve_mode(args)
    paid_api = bool(args.paid_api)
    if paid_api:
        os.environ["PEER_LOOP_PAID_API"] = "1"
    from_transcript = args.from_transcript or args.forever or mode in ("clipboard", "direct-ui")
    clipboard_only = (
        mode == "clipboard"
        or args.clipboard_only
        or os.environ.get("CURSOR_MINIMIZED") == "1"
    )
    press_enter = not args.no_enter

    if args.install:
        return cmd_install(install_mode=_resolve_install_mode(args))
    if args.uninstall:
        return cmd_uninstall()
    if args.watch or args.status:
        import peer_watch

        if args.status:
            return peer_watch.run_once()
        return peer_watch.run_watch()

    if args.once:
        log_fn = lambda msg: _log(msg, daemon=False)
        text = transcript.build_next_input(quick=args.quick)
        if not text:
            log_fn("nothing to dispatch")
            return 0
        return dispatch_prompt_text(
            text,
            mode=mode,
            clipboard_only=clipboard_only,
            press_enter=press_enter,
            log_fn=log_fn,
            paid_api=paid_api,
        )[0]

    if args.forever:
        return run_forever(
            quick=args.quick,
            mode=mode,
            clipboard_only=clipboard_only,
            press_enter=press_enter,
            daemon=args.daemon,
            from_transcript=from_transcript,
            done_timeout_sec=args.done_timeout_sec,
            paid_api=paid_api,
        )

    print("Use --forever, --once, --watch, or --status (see --help)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
