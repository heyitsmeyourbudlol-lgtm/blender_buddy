#!/usr/bin/env python3
"""Live terminal dashboard for the peer loop — WORKING vs IDLE at a glance.

Usage:
  python3 scripts/peer_watch.py              # live refresh (default)
  python3 scripts/peer_watch.py --once       # single snapshot
  python3 scripts/peer_loop.py --watch       # same
  ./scripts/peer-watch
"""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import subprocess
import sys
import termios
import time
import tty
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import peer_loop  # noqa: E402
import peer_terminal  # noqa: E402
import peer_transcript as transcript  # noqa: E402
import project_automation as auto  # noqa: E402

LABEL = peer_loop.LABEL
LOG_PATH = peer_loop.LOG_PATH
STATE_PATH = auto.CONFIG_DIR / "peer-loop-state.json"
SIGNAL_PATH = auto.CONFIG_DIR / "peer-turn.signal"
STATUS_PATH = auto.CONFIG_DIR / "peer-loop-status.json"

# Clear screen + home (no curses dependency).
_CLEAR = "\033[2J\033[H"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_MAGENTA = "\033[35m"


@dataclass
class AgentProc:
    pid: int
    etime: str
    state: str


@dataclass
class PeerSnapshot:
    ts: str
    phase: str  # WORKING | WAITING | VERIFYING | IDLE | STOPPED | UNKNOWN
    phase_detail: str
    daemon_running: bool
    daemon_pid: int | None
    agent: AgentProc | None
    auth_ready: bool
    auth_detail: str
    git_clean: bool
    git_detail: str
    dirty_paths: list[str] = field(default_factory=list)
    queue_count: int = 0
    queue_source: str = "empty"
    queue_preview: list[str] = field(default_factory=list)
    last_log: str = ""
    recent_log: list[str] = field(default_factory=list)
    log_age_sec: float | None = None
    last_cycle_summary: str = ""
    noop_backoff_sec: float = 0.0


def _run(cmd: list[str], *, timeout: float = 5.0) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    out = (proc.stdout or proc.stderr or "").strip()
    return proc.returncode, out


_DAEMON_INFO_TTL_SEC = 2.0
_daemon_info_cache: tuple[float, tuple[bool, int | None]] | None = None


def _linux_daemon_pid(unit: str) -> int | None:
    try:
        proc = subprocess.run(
            [
                "systemctl",
                "--user",
                "show",
                unit,
                "--property=MainPID",
            ],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    for line in (proc.stdout or "").splitlines():
        if line.startswith("MainPID="):
            try:
                val = int(line.split("=", 1)[1].strip())
                return val if val > 0 else None
            except ValueError:
                return None
    return None


def _peer_process_fallback() -> tuple[bool, int | None]:
    """Treat a live ``peer_loop.py --forever`` as daemon-ok when LaunchAgent is down.

    OVERSEER_PEER_PROCESS_FALLBACK_LAUNCHCTL_IO_2026_09_05
    """
    import peer_self_heal as heal

    pid = heal._peer_loop_process_pid()
    if pid is None:
        return False, None
    return True, pid


def daemon_info() -> tuple[bool, int | None]:
    global _daemon_info_cache
    now = time.time()
    if _daemon_info_cache and now - _daemon_info_cache[0] < _DAEMON_INFO_TTL_SEC:
        return _daemon_info_cache[1]

    if sys.platform != "darwin":
        import peer_self_heal as heal

        active = heal._systemd_user_active("peer-loop.service")
        pid = _linux_daemon_pid("peer-loop.service") if active else None
        if active:
            result = (True, pid)
        else:
            result = _peer_process_fallback()
        _daemon_info_cache = (now, result)
        return result

    uid = os.getuid()
    rc, out = _run(["launchctl", "list", LABEL])
    # launchctl list LABEL prints "PID Status Label" when loaded
    if rc != 0:
        rc2, out2 = _run(["launchctl", "print", f"gui/{uid}/{LABEL}"])
        if rc2 != 0:
            result = _peer_process_fallback()
            _daemon_info_cache = (now, result)
            return result
        pid = None
        for line in out2.splitlines():
            line = line.strip()
            if line.startswith("pid ="):
                try:
                    pid = int(line.split("=", 1)[1].strip())
                except ValueError:
                    pid = None
                break
        result = (True, pid)
        _daemon_info_cache = (now, result)
        return result
    # Format: "PID\tLastExit\tLabel" or similar from `launchctl list | rg`
    rc, listing = _run(["launchctl", "list"])
    if rc != 0:
        result = _peer_process_fallback()
        _daemon_info_cache = (now, result)
        return result
    for line in listing.splitlines():
        if LABEL not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "-":
            result = (True, None)
            _daemon_info_cache = (now, result)
            return result
        try:
            result = (True, int(parts[0]))
            _daemon_info_cache = (now, result)
            return result
        except ValueError:
            result = (True, None)
            _daemon_info_cache = (now, result)
            return result
    result = _peer_process_fallback()
    _daemon_info_cache = (now, result)
    return result


def find_agent_proc() -> AgentProc | None:
    """Find background `cursor-agent -p` peer cycle (not the worker daemon)."""
    try:
        import peer_parallel_dispatch as ppd

        proc = ppd.find_agent_proc()
        if proc is not None:
            return AgentProc(pid=proc.pid, etime=proc.etime, state=proc.state)
    except Exception:  # noqa: BLE001 — dashboard must not crash
        pass
    return None


def _porcelain_path(line: str) -> str | None:
    """Parse a `git status --porcelain` line into a path (handles renames)."""
    # Official format: XY<space>PATH  (or PATH -> PATH for renames)
    m = re.match(r"^.. (.*)$", line)
    if not m:
        return None
    path = m.group(1)
    if path.startswith('"') and path.endswith('"'):
        path = path[1:-1]
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    return path or None


def git_snapshot() -> tuple[bool, str, list[str]]:
    rc, porcelain = _run(["git", "status", "--porcelain"])
    if rc != 0:
        return False, "git status failed", []
    lines = [ln for ln in porcelain.splitlines() if ln.strip()]
    paths = [p for p in (_porcelain_path(ln) for ln in lines) if p]
    if not paths:
        return True, "clean working tree", []
    modified = sum(1 for ln in lines if not ln.startswith("??") and not ln.startswith("!!"))
    untracked = sum(1 for ln in lines if ln.startswith("??"))
    detail = f"{len(paths)} path(s) ({modified} modified, {untracked} untracked)"
    return False, detail, paths[:12]


def read_log_tail(n: int = 12) -> tuple[list[str], str, float | None]:
    if not LOG_PATH.is_file():
        return [], "(no log yet)", None
    try:
        mtime = LOG_PATH.stat().st_mtime
        age = max(0.0, time.time() - mtime)
        lines = auto.tail_text_lines(LOG_PATH, max(n * 4, 48))
    except OSError:
        return [], "(log unreadable)", None
    # Deduplicate consecutive identical lines (daemon sometimes double-logs)
    deduped: list[str] = []
    for ln in lines:
        if not deduped or deduped[-1] != ln:
            deduped.append(ln)
    recent = deduped[-n:]
    last = recent[-1] if recent else "(empty log)"
    # Strip timestamp prefix for last display if present
    return recent, last, age


def queue_snapshot(
    *,
    git_clean: bool | None = None,
    live: auto.LiveState | None = None,
) -> tuple[int, str, list[str]]:
    try:
        ctx = auto.load_context_md()
        work = auto.load_work_queue_md()
        primary = auto.open_work_items(ctx, work)
        if primary.open_items:
            state = auto.QueueState(open_items=primary.open_items, source=primary.source)
        elif live is not None:
            state = auto.loop_work_items(ctx, work, live=live)
        elif git_clean is not None:
            stub = auto.LiveState(
                git_clean=git_clean,
                git_detail="",
                tests_ok=True,
                tests_detail="",
                import_rss_mb=None,
                footprint_detail="",
            )
            state = auto.loop_work_items(ctx, work, live=stub)
        else:
            live = auto.measure_live_state(quick=True)
            state = auto.loop_work_items(ctx, work, live=live)
    except Exception as exc:  # noqa: BLE001 — dashboard must not crash
        return 0, f"error:{exc}", []
    preview = [item[:72] for item in state.open_items[:4]]
    return len(state.open_items), state.source, preview


def classify_phase(
    *,
    daemon_ok: bool,
    agent: AgentProc | None,
    last_log: str,
    queue_count: int,
    git_clean: bool,
) -> tuple[str, str]:
    if not daemon_ok:
        hint = (
            "peer-loop.service not active — run: python3 scripts/peer_loop.py --install"
            if sys.platform != "darwin"
            else "LaunchAgent not loaded — run: python3 scripts/peer_loop.py --install"
        )
        return "STOPPED", hint

    low = last_log.lower()
    if agent is not None:
        return (
            "WORKING",
            f"cursor-agent -p pid {agent.pid} · elapsed {agent.etime} · state {agent.state} "
            f"(log quiet until subprocess exits)",
        )

    if "waiting for clean tree" in low:
        return "WAITING", "cycle paused until git is clean (agent may still be writing)"
    if "stall pivot:" in low:
        return "WORKING", "stall pivot — what else can I do (alternate improvements)"
    if "verify:" in low:
        return "VERIFYING", "local verify commands running"
    if "terminal cycle" in low or "continuous: queue has work" in low or "keep-working" in low:
        return "WORKING", "continuous keep-working cycle (agent or local)"
    if "continuous: heartbeat" in low:
        return "WORKING", "continuous heartbeat — event timeout, spinning again"
    if "idle: queue empty" in low:
        return "IDLE", "queue empty — sleeping on transcript/git/signal events"
    if "event wait" in low and queue_count > 0:
        return "WORKING", "event wait with continuous heartbeat (≤45s)"
    if "event-driven" in low or "kqueue" in low:
        if queue_count > 0 and not git_clean:
            return "WAITING", "queue has work but tree dirty — local keep-working / wait clean"
        if queue_count > 0:
            return "WORKING", "queue open — continuous / waiting on events"
        return "IDLE", "event-driven sleep (kqueue) — not spinning"
    if "local-only" in low or "local keep-working" in low:
        return "WORKING", "local-only continuous — prompts + verify ticks"
    if "auth failed" in low or "not logged in" in low:
        return "IDLE", "auth not ready — run cursor-agent login"

    try:
        import peer_worktree as pwt

        dirty_ok = pwt.continue_on_dirty_enabled()
    except Exception:  # noqa: BLE001
        dirty_ok = False

    if queue_count > 0 and not git_clean:
        if dirty_ok:
            return "WORKING", "dirty tree — continue_on_dirty; dispatch via worktrees"
        return "WAITING", "dirty tree with open queue — mid-cycle or blocked on commit"
    if queue_count > 0:
        return "UNKNOWN", "queue open, no live agent — may be between cycles"
    return "IDLE", "no agent · no open queue"


def collect_snapshot(*, live: auto.LiveState | None = None) -> PeerSnapshot:
    daemon_ok, daemon_pid = daemon_info()
    agent = find_agent_proc()
    if live is not None:
        git_clean = live.git_clean
        git_detail = live.git_detail
        dirty: list[str] = []
    else:
        git_clean, git_detail, dirty = git_snapshot()
    recent, last, age = read_log_tail(14)
    qcount, qsource, qpreview = queue_snapshot(git_clean=git_clean, live=live)
    try:
        # OVERSEER_WATCH_AUTH_PAID_API_2026_09_04 — desktop_auth_ready returns
        # False whenever CURSOR_API_KEY is set (billing redirect). Live peer-loop
        # often runs --paid-api; report cursor_agent_auth_ready so oversight does
        # not thrash "auth not ready" on a healthy paid path.
        if peer_terminal.api_key_configured():
            auth_ready, auth_detail = peer_terminal.cursor_agent_auth_ready()
        else:
            auth_ready, auth_detail = peer_terminal.desktop_auth_ready()
    except Exception as exc:  # noqa: BLE001
        auth_ready, auth_detail = False, f"auth check failed: {exc}"

    state = transcript.load_state()
    lc = state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else {}
    backoff = transcript.noop_backoff_remaining(state, backoff_sec=peer_loop.NOOP_BACKOFF_SEC)
    cycle_bits = []
    if lc:
        cycle_bits.append(f"rc={lc.get('rc')}")
        cycle_bits.append("verify=ok" if lc.get("verify_ok") else "verify=FAIL")
        if lc.get("noop"):
            cycle_bits.append("noop")
        if lc.get("git_head"):
            cycle_bits.append(str(lc.get("git_head"))[:40])
        if lc.get("note"):
            cycle_bits.append(str(lc.get("note"))[:60])
    cycle_summary = " · ".join(cycle_bits) if cycle_bits else "(no cycle yet)"

    phase, detail = classify_phase(
        daemon_ok=daemon_ok,
        agent=agent,
        last_log=last,
        queue_count=qcount,
        git_clean=git_clean,
    )
    if agent is None and backoff > 0:
        phase, detail = "IDLE", f"noop backoff {backoff:.0f}s — same queue after last ok"
    elif agent is None and lc.get("verify_ok") is False:
        phase, detail = "WAITING", "last cycle verify FAIL — holding continuous re-dispatch"

    snap = PeerSnapshot(
        ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        phase=phase,
        phase_detail=detail,
        daemon_running=daemon_ok,
        daemon_pid=daemon_pid,
        agent=agent,
        auth_ready=auth_ready,
        auth_detail=auth_detail,
        git_clean=git_clean,
        git_detail=git_detail,
        dirty_paths=dirty,
        queue_count=qcount,
        queue_source=qsource,
        queue_preview=qpreview,
        last_log=last,
        recent_log=recent,
        log_age_sec=age,
        last_cycle_summary=cycle_summary,
        noop_backoff_sec=backoff,
    )
    try:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(snap)
        STATUS_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    except OSError:
        pass
    return snap


def _phase_color(phase: str) -> str:
    if phase == "WORKING":
        return _GREEN
    if phase in ("WAITING", "VERIFYING", "UNKNOWN"):
        return _YELLOW
    if phase == "STOPPED":
        return _RED
    return _CYAN  # IDLE


def _age_str(sec: float | None) -> str:
    if sec is None:
        return "?"
    if sec < 90:
        return f"{sec:.0f}s ago"
    if sec < 3600:
        return f"{sec / 60:.1f}m ago"
    return f"{sec / 3600:.1f}h ago"


def _row(text: str, width: int = 96) -> str:
    """Box row; truncate on visible (ANSI-stripped) length only."""
    plain = re.sub(r"\033\[[0-9;]*m", "", text)
    if len(plain) > width - 2:
        # Truncate the plain form so we never slice mid-escape
        text = plain[: width - 5] + "…"
    return f"│ {text}"


def render(snap: PeerSnapshot) -> str:
    color = _phase_color(snap.phase)
    width = 96
    bar = "─" * (width - 2)
    lines: list[str] = []
    lines.append(f"┌{bar}┐")
    lines.append(_row(f"{_BOLD}{auto.PROJECT_NAME} peer loop{_RESET}  {_DIM}{snap.ts}{_RESET}", width))
    lines.append(f"├{bar}┤")
    lines.append(
        _row(
            f"STATE  {color}{_BOLD}● {snap.phase}{_RESET}  {_DIM}{snap.phase_detail}{_RESET}",
            width,
        )
    )
    daemon = (
        f"ok pid {snap.daemon_pid}"
        if snap.daemon_running and snap.daemon_pid
        else ("loaded (no pid)" if snap.daemon_running else "NOT RUNNING")
    )
    lines.append(_row(f"Daemon {_GREEN if snap.daemon_running else _RED}{daemon}{_RESET}", width))
    auth_c = _GREEN if snap.auth_ready else _YELLOW
    lines.append(_row(f"Auth   {auth_c}{snap.auth_detail}{_RESET}", width))
    git_c = _GREEN if snap.git_clean else _YELLOW
    lines.append(_row(f"Git    {git_c}{snap.git_detail}{_RESET}", width))
    lines.append(
        _row(
            f"Queue  {_MAGENTA}{snap.queue_count} open{_RESET} · source={snap.queue_source}",
            width,
        )
    )
    for item in snap.queue_preview:
        lines.append(_row(f"       · {item}", width))
    age = _age_str(snap.log_age_sec)
    lines.append(_row(f"Log    {_DIM}updated {age}{_RESET}  {LOG_PATH.name}", width))
    lines.append(_row(f"Cycle  {_DIM}{snap.last_cycle_summary}{_RESET}", width))
    if snap.noop_backoff_sec > 0:
        lines.append(_row(f"Hold   {_YELLOW}noop backoff {snap.noop_backoff_sec:.0f}s{_RESET}", width))
    lines.append(f"├{bar}┤")
    lines.append(_row(f"{_BOLD}recent log{_RESET}", width))
    for ln in snap.recent_log[-8:]:
        short = re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", ln)
        lines.append(_row(f" {short}", width))
    if snap.dirty_paths:
        lines.append(f"├{bar}┤")
        lines.append(_row(f"{_BOLD}dirty paths{_RESET}", width))
        for p in snap.dirty_paths[:8]:
            lines.append(_row(f" {p}", width))
    lines.append(f"├{bar}┤")
    lines.append(_row(f"{_DIM}keys: q quit · r poke wake signal · space refresh now{_RESET}", width))
    lines.append(
        _row(
            f"{_DIM}WORKING = agent alive · IDLE = sleeping on events · WAITING = dirty tree{_RESET}",
            width,
        )
    )
    lines.append(f"└{bar}┘")
    return "\n".join(lines)


def poke_signal() -> None:
    SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL_PATH.touch()


def _read_key(timeout: float) -> str | None:
    if not sys.stdin.isatty():
        time.sleep(timeout)
        return None
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if not ready:
            return None
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def run_watch(*, interval: float = 1.0) -> int:
    print(f"{_DIM}peer-watch — live status (Ctrl+C or q to quit){_RESET}", flush=True)
    try:
        while True:
            snap = collect_snapshot()
            sys.stdout.write(_CLEAR + render(snap) + "\n")
            sys.stdout.flush()
            key = _read_key(interval)
            if key in ("q", "Q", "\x03"):
                break
            if key in ("r", "R"):
                poke_signal()
            # space / other → immediate refresh on next loop
    except KeyboardInterrupt:
        pass
    print(f"\n{_DIM}peer-watch stopped{_RESET}")
    return 0


def run_once(*, as_json: bool = False) -> int:
    snap = collect_snapshot()
    if as_json:
        print(json.dumps(asdict(snap), indent=2))
    else:
        print(render(snap))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Live terminal dashboard for peer loop")
    parser.add_argument("--once", action="store_true", help="Print one snapshot and exit")
    parser.add_argument("--status", action="store_true", help="Alias for --once")
    parser.add_argument("--json", action="store_true", help="Machine-readable snapshot")
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Refresh seconds for live mode (default: 1)",
    )
    parser.add_argument("--poke", action="store_true", help="Touch peer-turn.signal and exit")
    args = parser.parse_args()
    if args.poke:
        poke_signal()
        print(f"poked {SIGNAL_PATH}")
        return 0
    if args.once or args.status or args.json:
        return run_once(as_json=args.json)
    return run_watch(interval=max(0.3, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
