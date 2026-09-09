#!/usr/bin/env python3
"""Continuous Cursor system oversight — mechanical heal + digest + cursor-agent review.

Orchestrates self-heal, queue compact, automation digest, and repo flaw research into
one human-readable board at ``notes/SYSTEM_OVERSIGHT.md``, then dispatches cursor-agent
when auth/RAM allow and no factory agent is busy.

Usage:
  python3 scripts/peer_oversight.py --once
  python3 scripts/peer_oversight.py --forever --daemon
  python3 scripts/peer_oversight.py --install
  ./scripts/peer oversight
  ./scripts/peer oversight-install
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

# OVERSEER_HUB_PIN_2026_09_04 — forever daemon must not run from .worktrees/peer-N
# (notes/SYSTEM_OVERSIGHT.md is often a symlink into hub → false stagnation fanout).
if ".worktrees" in ROOT.parts:
    _parts = list(ROOT.parts)
    _idx = _parts.index(".worktrees")
    _hub = Path(*_parts[:_idx]) if _idx > 0 else ROOT
    _hub_script = _hub / "scripts" / "peer_oversight.py"
    if _hub_script.is_file() and _hub_script.resolve() != Path(__file__).resolve():
        os.execv(sys.executable, [sys.executable, str(_hub_script), *sys.argv[1:]])

import automation_config as cfg_mod  # noqa: E402
import peer_investigate as investigate  # noqa: E402
import peer_oversight_events as events  # noqa: E402
import peer_self_heal as self_heal  # noqa: E402
import project_automation as auto  # noqa: E402

CONFIG_DIR = auto.CONFIG_DIR
STATE_PATH = CONFIG_DIR / "oversight-state.json"
PROMPT_PATH = CONFIG_DIR / "oversight-prompt.md"
LOG_PATH = CONFIG_DIR / "oversight-loop.log"

NAMESPACE = str(cfg_mod.CFG.get("config_namespace") or "automation")
OVERSIGHT_LABEL = f"com.togi.{NAMESPACE}-oversight-loop"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{OVERSIGHT_LABEL}.plist"


def _disk_oversight_identity() -> tuple[str, str, Path, Path]:
    """Re-read disk namespace — stale hub-oversight must not reinstall hub labels."""
    cfg = cfg_mod.load_config()
    ns = str(cfg.get("config_namespace") or "automation")
    label = f"com.togi.{ns}-oversight-loop"
    plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    log = Path.home() / ".config" / ns / "oversight-loop.log"
    return ns, label, plist, log


def _cfg() -> dict[str, Any]:
    raw = cfg_mod.CFG.get("oversight") or {}
    return raw if isinstance(raw, dict) else {}


def oversight_enabled() -> bool:
    block = _cfg()
    if "enabled" in block:
        return bool(block["enabled"])
    return bool(cfg_mod.CFG.get("oversight_enabled", True))


def mechanical_interval_sec() -> float:
    block = _cfg()
    try:
        # Instant-react mode allows sub-minute mechanical scans (log/error watch).
        floor = 5.0 if instant_react_enabled() else 60.0
        val = block.get("mechanical_interval_sec") or cfg_mod.CFG.get("oversight_mechanical_interval_sec") or 15
        return max(floor, float(val))
    except (TypeError, ValueError):
        return 15.0 if instant_react_enabled() else 300.0


def instant_react_enabled() -> bool:
    block = _cfg()
    if "instant_react" in block:
        return bool(block["instant_react"])
    return bool(cfg_mod.CFG.get("oversight_instant_react", True))


def agent_interval_sec() -> float:
    block = _cfg()
    try:
        val = block.get("agent_interval_sec") or cfg_mod.CFG.get("oversight_agent_interval_sec") or 900
        return max(120.0, float(val))
    except (TypeError, ValueError):
        return 900.0


def dispatch_agent_enabled() -> bool:
    block = _cfg()
    if "dispatch_agent" in block:
        return bool(block["dispatch_agent"])
    return bool(cfg_mod.CFG.get("oversight_dispatch_agent", True))


def digest_path() -> Path:
    block = _cfg()
    rel = str(block.get("digest_path") or cfg_mod.CFG.get("oversight_digest_path") or "notes/SYSTEM_OVERSIGHT.md")
    p = Path(rel)
    return p if p.is_absolute() else ROOT / p


def autonomous_execution_enabled() -> bool:
    return bool(cfg_mod.CFG.get("autonomous_execution", True))


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _refresh_oversight_runtime(*, log_fn: Callable[[str], None] | None = None) -> None:
    """OVERSEER_RELOAD_EVENTS_HUB_NS_2026_09_04 — forever must not stay on twin ns.

    Daemon started under ``~/.config/automation`` while disk ``config_namespace``
    is ``automation-hub`` kept Creative queue_fp + stale research (57m) and an
    in-memory pre-CLEARED healthy_idle gate → score 144 soft-dispatch forever.
    Rebind paths from disk each cycle and reload events so landed needles apply
    without waiting for a manual systemctl restart.
    """
    global CONFIG_DIR, STATE_PATH, PROMPT_PATH, LOG_PATH, events
    log = log_fn or (lambda _m: None)
    try:
        fresh = cfg_mod.load_config() if hasattr(cfg_mod, "load_config") else dict(cfg_mod.CFG)
        if isinstance(fresh, dict) and fresh:
            cfg_mod.CFG.clear()
            cfg_mod.CFG.update(fresh)
        ns = str(cfg_mod.CFG.get("config_namespace") or "automation-hub")
        new_dir = Path.home() / ".config" / ns
        if new_dir != CONFIG_DIR:
            log(f"oversight: rebind CONFIG_DIR {CONFIG_DIR.name} → {ns}")
        CONFIG_DIR = new_dir
        STATE_PATH = CONFIG_DIR / "oversight-state.json"
        PROMPT_PATH = CONFIG_DIR / "oversight-prompt.md"
        LOG_PATH = CONFIG_DIR / "oversight-loop.log"
        # Keep investigate/research helpers on the same ns as this daemon.
        auto.CONFIG_DIR = CONFIG_DIR
        if hasattr(cfg_mod, "config_dir"):
            # project_automation often caches via cfg_mod.config_dir()
            pass
        events = importlib.reload(events)
    except Exception as exc:  # noqa: BLE001
        log(f"oversight: runtime refresh failed ({exc})")


def agent_cooldown_remaining() -> float:
    return events.cooldown_remaining(_load_state())



# OVERSEER_FANOUT_CAP_2026_09_03 — never stack System Overseer cursor-agents.
# OVERSEER_FANOUT_FLOCK_2026_09_04 — async spawn raced /proc count → 30+ overseers.
# OVERSEER_FANOUT_PENDING_STAMP_2026_09_04 — async spawn invisible in /proc briefly;
# stamp blocks a second dispatch until live count catches up (or TTL expires).
# OVERSEER_FANOUT_TRIM_SIGKILL_2026_09_04 — SIGTERM-only left 7/8 zombies; escalate.
OVERSEER_PROMPT_NEEDLE = "System Overseer"
OVERSEER_FANOUT_MAX = 1
OVERSEER_DISPATCH_LOCK = CONFIG_DIR / "overseer-dispatch.lock"
OVERSEER_FANOUT_PENDING = CONFIG_DIR / "overseer-fanout-pending"
OVERSEER_FANOUT_PENDING_TTL_SEC = 180.0


def _cmdline_is_overseer(cmd: str) -> bool:
    """True when cmdline is a cursor-agent -p System Overseer dispatch.

    Do NOT reject bare ``worker`` — Cursor CLI lives under
    ``.../cursor-agent-worker/...`` so that substring matches every agent.
    Only skip dedicated worker-server argv tokens.
    """
    if "cursor-agent" not in cmd and "agent-cli" not in cmd:
        return False
    tokens = cmd.split()
    if any(t in ("worker-server", "--worker-server") for t in tokens):
        return False
    return (
        OVERSEER_PROMPT_NEEDLE in cmd
        or "System overseer" in cmd
        or "event-triggered stagnation dispatch" in cmd
    )


def _overseer_running_count() -> int:
    """Count live System Overseer cursor-agent processes (fanout gate)."""
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return 0
    n = 0
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if not raw:
            continue
        cmd = raw.replace(b"\0", b" ").decode("utf-8", errors="replace")
        if _cmdline_is_overseer(cmd):
            n += 1
    return n


def _try_overseer_dispatch_lock():
    """Non-blocking exclusive lock around fanout check + async spawn.

    Returns open file handle (held) or None if another dispatcher owns the lock.
    """
    import fcntl

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        fh = open(OVERSEER_DISPATCH_LOCK, "a+", encoding="utf-8")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.seek(0)
        fh.truncate()
        fh.write(f"{os.getpid()} {time.time():.3f}\n")
        fh.flush()
        return fh
    except OSError:
        return None


def _agent_running() -> bool:
    """True if any peer cursor-agent is live (niche busy signal)."""
    try:
        import peer_parallel_dispatch as ppd

        return bool(ppd.find_agent_procs())
    except Exception:  # noqa: BLE001
        import peer_watch

        return peer_watch.find_agent_proc() is not None


def _fanout_pending_age_sec() -> float | None:
    """Age of pending-spawn stamp; None if absent/stale."""
    try:
        if not OVERSEER_FANOUT_PENDING.is_file():
            return None
        raw = OVERSEER_FANOUT_PENDING.read_text(encoding="utf-8", errors="replace").strip()
        started = float(raw.split()[0])
        age = max(0.0, time.time() - started)
        if age > OVERSEER_FANOUT_PENDING_TTL_SEC:
            OVERSEER_FANOUT_PENDING.unlink(missing_ok=True)
            return None
        return age
    except (OSError, ValueError, IndexError):
        return None


def _mark_fanout_pending() -> None:
    """OVERSEER_FANOUT_PENDING_STAMP_2026_09_04 — count as live until /proc sees agent."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        OVERSEER_FANOUT_PENDING.write_text(f"{time.time():.6f}\n", encoding="utf-8")
    except OSError:
        pass


def _clear_fanout_pending_if_live() -> None:
    """Drop stamp once a real overseer cmdline is visible (or TTL)."""
    try:
        if _overseer_running_count() >= 1:
            OVERSEER_FANOUT_PENDING.unlink(missing_ok=True)
            return
        _fanout_pending_age_sec()  # TTL sweep
    except Exception:  # noqa: BLE001
        pass


def _overseer_fanout_blocked() -> bool:
    """Hard cap: refuse a new overseer when one is already running (or pending)."""
    try:
        _clear_fanout_pending_if_live()
        if _overseer_running_count() >= OVERSEER_FANOUT_MAX:
            return True
        # Pending async spawn — treat as occupied even before /proc cmdline lands.
        return _fanout_pending_age_sec() is not None
    except Exception:  # noqa: BLE001
        return False


def _overseer_pids() -> list[int]:
    """PIDs of live System Overseer cursor-agent processes."""
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return []
    pids: list[int] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if not raw:
            continue
        cmd = raw.replace(b"\0", b" ").decode("utf-8", errors="replace")
        if _cmdline_is_overseer(cmd):
            pids.append(int(entry.name))
    return pids


def trim_excess_overseers(*, keep: int | None = None, protect: set[int] | None = None) -> str:
    """OVERSEER_FANOUT_FLOCK_WIRE_2026_09_04 — SIGTERM extras beyond FANOUT_MAX.

    Async spawn raced the /proc count when the dispatch flock was never held;
    heal + post-cap paths call this to collapse the swarm.

    OVERSEER_FANOUT_TRIM_SIGKILL_2026_09_04 — SIGTERM alone left zombies; escalate.
    """
    keep_n = OVERSEER_FANOUT_MAX if keep is None else max(1, int(keep))
    protect = set(protect or ())
    protect.add(os.getpid())
    try:
        p = os.getpid()
        for _ in range(8):
            protect.add(p)
            stat = (Path("/proc") / str(p) / "stat").read_text().split()
            p = int(stat[3])
            if p <= 1:
                break
    except (OSError, ValueError, IndexError):
        pass
    pids = _overseer_pids()
    if len(pids) <= keep_n:
        _clear_fanout_pending_if_live()
        return f"overseer fanout ok count={len(pids)}<={keep_n}"
    keep_set: list[int] = [p for p in pids if p in protect]
    for p in sorted(pids, reverse=True):
        if len(keep_set) >= keep_n:
            break
        if p not in keep_set:
            keep_set.append(p)
    victims = [p for p in pids if p not in keep_set]
    killed = 0
    for pid in victims:
        try:
            os.kill(pid, signal.SIGTERM)
            killed += 1
        except OSError:
            continue
    # Escalate lingering victims (cursor-agent often ignores quick SIGTERM).
    time.sleep(0.35)
    still = [p for p in victims if p in set(_overseer_pids())]
    sigkill_n = 0
    for pid in still:
        try:
            os.kill(pid, signal.SIGKILL)
            sigkill_n += 1
        except OSError:
            continue
    _clear_fanout_pending_if_live()
    return (
        f"trimmed overseer fanout killed={killed} sigkill={sigkill_n} "
        f"kept={len(keep_set)} was={len(pids)}"
    )


def _ensure_core_daemons(log: Callable[[str], None]) -> list[str]:
    actions: list[str] = []
    if not autonomous_execution_enabled():
        return actions
    try:
        daemons = investigate._daemon_status()
        if not daemons.get("peer_loop"):
            msg = self_heal._heal_peer_daemon({})
            actions.append(f"daemon: {msg}")
            log(f"oversight: {msg}")
        if not daemons.get("improve_loop"):
            msg = self_heal._heal_improve_daemon({})
            actions.append(f"daemon: {msg}")
            log(f"oversight: {msg}")
    except Exception as exc:  # noqa: BLE001
        log(f"oversight: daemon heal failed ({exc})")
    return actions


def _repo_flaw_summary() -> dict[str, Any]:
    try:
        import peer_repo_research as prr

        registry = prr._load_findings_registry()
        items = registry.get("items") or {}
        open_flaws = [
            v for v in items.values()
            if isinstance(v, dict) and v.get("status") != "resolved"
        ]
        critical = sum(1 for f in open_flaws if f.get("severity") == "critical")
        high = sum(1 for f in open_flaws if f.get("severity") == "high")
        top = sorted(
            open_flaws,
            key=lambda f: prr.SEVERITY_ORDER.get(str(f.get("severity")), 9),
        )[:6]
        return {
            "open": len(open_flaws),
            "critical": critical,
            "high": high,
            "top": [
                f"[{f.get('severity')}] {f.get('title')}: {str(f.get('evidence', ''))[:80]}"
                for f in top
            ],
            "digest": str(prr.digest_path()),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:120]}


def _health_emoji(ctx: dict[str, Any], flaws: dict[str, Any]) -> str:
    daemons = (ctx.get("kit") or {}).get("daemons") or {}
    bn = ctx.get("bottlenecks") or []
    if not daemons.get("peer_loop") or not daemons.get("improve_loop"):
        return "🔴"
    if flaws.get("critical") or any(b.get("severity") == "critical" for b in bn):
        return "🔴"
    if flaws.get("high") or flaws.get("open", 0) > 10:
        return "🟡"
    last = ctx.get("last_cycle") or {}
    if last.get("noop") or int(ctx.get("queue_count") or 0) > 20:
        return "🟡"
    return "🟢"


def build_oversight_digest(
    ctx: dict[str, Any],
    *,
    flaws: dict[str, Any],
    actions: list[str],
    dispatched: bool,
    agent_pending: bool = False,
    agent_cooldown: float = 0.0,
    stagnation: events.StagnationReport | None = None,
    dispatch_hold: list[str] | None = None,
) -> str:
    kit = ctx.get("kit") or {}
    daemons = kit.get("daemons") or {}
    last = ctx.get("last_cycle") or {}
    bn = ctx.get("bottlenecks") or []
    health = _health_emoji(ctx, flaws)
    ts = ctx.get("ts") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# System oversight",
        "",
        f"_Updated {ts}_ · overseer {health}",
        "",
        "> **Continuous Cursor oversight** — mechanical refresh every "
        f"{mechanical_interval_sec():.0f}s; cursor-agent on **stagnation** "
        f"(high expectations, min gap {events.agent_min_interval_sec():.0f}s).",
        "",
        "## At a glance",
        "",
        "| Signal | Value |",
        "|--------|-------|",
        f"| Oversight daemon | RUNNING (this file) |",
        f"| Peer loop | {'RUNNING' if daemons.get('peer_loop') else '**STOPPED**'} |",
        f"| Improve loop | {'RUNNING' if daemons.get('improve_loop') else '**STOPPED**'} |",
        f"| Phase | **{ctx.get('phase')}** — {str(ctx.get('phase_detail', ''))[:80]} |",
        f"| Queue | {ctx.get('queue_count')} open ({ctx.get('queue_source')}) |",
        f"| Repo flaws | {flaws.get('open', '?')} open ({flaws.get('critical', 0)} critical, {flaws.get('high', 0)} high) |",
        f"| Bottlenecks | {len(bn)} open |",
        f"| Tests | {kit.get('tests_detail', '?')} |",
        f"| Factory | {kit.get('factory_pct', '?')}% |",
    ]

    if stagnation and stagnation.reasons:
        review = "dispatched" if dispatched else ("pending" if agent_pending else "held")
        if dispatch_hold and not dispatched:
            review = f"held ({dispatch_hold[0][:55]})"
        elif stagnation.should_dispatch and not dispatched and not agent_pending:
            review = f"due — {'; '.join(stagnation.reasons[:2])[:70]}"
    else:
        review = "dispatched" if dispatched else ("pending" if agent_pending else "idle (advancing)")
        if agent_cooldown > 0 and not dispatched:
            review = f"idle (min gap {agent_cooldown:.0f}s)"
    lines.append(f"| Cursor review | {review} |")
    lines.append("")

    if stagnation and stagnation.reasons:
        lines.extend(["## Stagnation signals", ""])
        if stagnation.should_dispatch:
            lines.append(f"_Score **{stagnation.score}** — improvement bar not met._")
        for r in stagnation.reasons[:8]:
            lines.append(f"- {r}")
        lines.append("")

    try:
        import peer_playbook as playbook

        pb_hits = playbook.match_many(
            (stagnation.reasons if stagnation else [])
            + [b.get("title", "") for b in bn]
            + [str(last.get("failure_type") or ""), str(last.get("summary") or "")]
        )
        if pb_hits:
            lines.extend(["## Instant fixes (playbook)", "", playbook.format_instant_fixes(pb_hits), ""])
    except Exception:  # noqa: BLE001
        pass

    if bn:
        lines.extend(["## Bottlenecks", ""])
        for b in bn[:8]:
            lines.append(f"- **[{b['severity']}]** {b['title']} — {b['evidence'][:100]}")
        lines.append("")

    if flaws.get("top"):
        lines.extend(["## Repo flaws (top)", ""])
        for item in flaws["top"]:
            lines.append(f"- {item}")
        lines.append("")

    if ctx.get("queue_preview"):
        lines.extend(["## Queue (top)", ""])
        for item in ctx.get("queue_preview") or []:
            lines.append(f"- {item}")
        lines.append("")

    if actions:
        lines.extend(["## This cycle", ""])
        for a in actions:
            lines.append(f"- {a}")
        lines.append("")

    lines.extend(
        [
            "## Cursor agent notes",
            "",
            "_Cursor overseer appends dated bullets here after each review._",
            "",
        ]
    )

    path = digest_path()
    if path.is_file():
        try:
            old = path.read_text(encoding="utf-8")
            if "## Cursor agent notes" in old:
                kept: list[str] = []
                for ln in old.split("## Cursor agent notes", 1)[1].splitlines():
                    s = ln.strip()
                    if s.startswith("## "):
                        break  # stop before Linked digests / Commands
                    if s.startswith("_") or s.startswith(">"):
                        continue
                    # Digest link bullets sometimes leak into agent notes; never retain.
                    if "AUTOMATION_DIGEST" in s or "REPO_FLAW" in s:
                        continue
                    if s.startswith("- Automation:") or s.startswith("- Repo flaws:"):
                        continue
                    # Dated overseer blocks only — drop orphan/indented paste without a date header.
                    if ln.startswith("  - ") and not (
                        s.startswith("- **20")
                        or s.startswith("- **Found:")
                        or s.startswith("- **Fixed:")
                        or s.startswith("- **Still broken:")
                        or s.startswith("- **Needs human:")
                    ):
                        continue
                    if s.startswith("- ") and "Cursor overseer" not in s:
                        kept.append(ln)
                if kept:
                    # Notes are newest-first; kept[-N] dropped fresh overseer
                    # bullets (self-check false PASS notes never stuck).
                    lines.extend(kept[:80])
                    lines.append("")
        except OSError:
            pass

    lines.extend(
        [
            "## Linked digests",
            "",
            f"- Automation: `{investigate.digest_path()}`",
            f"- Repo flaws: `{flaws.get('digest', 'notes/REPO_FLAW_RESEARCH.md')}`",
            "",
            "## Commands",
            "",
            "```bash",
            "./scripts/peer oversight              # one oversight cycle",
            "./scripts/peer oversight-force          # cursor-agent now",
            "./scripts/peer oversight-status",
            "./scripts/peer heal-all                 # mechanical heal",
            "./scripts/peer watch                    # live dashboard",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def build_oversight_prompt(
    ctx: dict[str, Any],
    flaws: dict[str, Any],
    *,
    stagnation: events.StagnationReport | None = None,
) -> str:
    digest = digest_path()
    bn_lines = [
        f"- [{b['severity']}] {b['title']}: {b['evidence'][:120]}"
        for b in ctx.get("bottlenecks") or []
    ] or ["- (none)"]
    flaw_lines = flaws.get("top") or ["- (none)"]
    queue_lines = ctx.get("queue_preview") or ["- (empty)"]
    last = ctx.get("last_cycle") or {}
    stag = stagnation.reasons if stagnation and stagnation.reasons else ["- stagnation detected"]
    try:
        import peer_playbook as playbook

        pb_block = playbook.format_prompt_block(
            playbook.match_many(stag + [b.get("title", "") for b in ctx.get("bottlenecks") or []])
        )
    except Exception:  # noqa: BLE001
        pb_block = ""
    bar = """
## High expectations

Dispatched because automation is **not improving enough**. Verify-ok alone is failure if
queue fingerprint, factory %, or git HEAD did not advance.

**Success = at least one:** queue item completed · factory +2% · permanent scripts/ fix · bottleneck removed.
**Attack:** noop root-cause · compact-queue theater · land minimal diff · test-quick green.
""" if events.high_expectations_enabled() else ""

    return f"""# System overseer — event-triggered stagnation dispatch

You are the **System Overseer** for `{ROOT.name}`. The factory stalled — fix it now.

## Why dispatched
{chr(10).join(f'- {r}' for r in stag)}

- Phase: **{ctx.get('phase')}** · verify={'ok' if last.get('verify_ok') else 'FAIL'} · noop={last.get('noop')}
- Queue: {ctx.get('queue_count')} open · flaws: {flaws.get('open', '?')} ({flaws.get('critical', 0)} critical)
{bar}
**Bottlenecks:** {chr(10).join(bn_lines)}
**Flaws:** {chr(10).join(f'- {f}' for f in flaw_lines)}
**Queue:** {chr(10).join(f'- {q}' for q in queue_lines)}

{pb_block}
Read `{digest}`, `notes/REPO_FLAW_RESEARCH.md`, `notes/WORK_QUEUE.md`, `notes/AGENT_ERROR_PLAYBOOK.md`.
Fix with `./scripts/peer heal-all` / `noop-break`. Append **Cursor agent notes** in `{digest}`.
Enqueue ≤2 `[oversight]` items only if blocked after fixing. `./scripts/peer test-quick` if Python changed.
"""


def write_digest(**kwargs: Any) -> Path:
    text = build_oversight_digest(**kwargs)
    path = digest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_oversight_cycle(
    *,
    log_fn: Callable[[str], None] | None = None,
    force_agent: bool = False,
    digest_only: bool = False,
    dispatch_agent: bool | None = None,
) -> dict[str, Any]:
    log = log_fn or (lambda _m: None)
    if not oversight_enabled():
        log("oversight: disabled")
        return {"skipped": "disabled"}

    # OVERSEER_RELOAD_EVENTS_HUB_NS_2026_09_04 — rebind hub ns + reload events.
    _refresh_oversight_runtime(log_fn=log)

    actions: list[str] = []
    actions.extend(_ensure_core_daemons(log))

    # Instant react: heal gate/agent failures before digest/dispatch.
    try:
        import peer_error_adapt as err_adapt

        drive = err_adapt.ensure_driving(log_fn=log, quick=True)
        for act in (drive.get("actions") or [])[:6]:
            actions.append(f"error-adapt: {act}")
        if drive.get("still_blocked"):
            actions.append("error-adapt: still hard-blocked — overseer will fire")
    except Exception as exc:  # noqa: BLE001
        log(f"oversight: error-adapt failed ({exc})")

    try:
        report = self_heal.run_cycle(write=True, log_fn=log)
        if report.actions:
            actions.extend(f"self-heal: {a}" for a in report.actions)
    except Exception as exc:  # noqa: BLE001
        log(f"oversight: self-heal failed ({exc})")

    ctx = investigate.collect_context()
    if ctx.get("last_cycle", {}).get("noop") or int(ctx.get("queue_count") or 0) > 15:
        try:
            removed, compact_actions = auto.compact_executable_queue(write=True)
            if removed:
                actions.append(f"compact: {removed} line(s)")
                actions.extend(f"compact: {a}" for a in compact_actions)
                ctx = investigate.collect_context()
        except Exception as exc:  # noqa: BLE001
            log(f"oversight: compact failed ({exc})")

    prr_result: dict[str, Any] = {}
    try:
        import peer_repo_research as prr

        prr_result = prr.run_research_cycle(log_fn=log, force=True, digest_only=True)
        actions.append(f"repo-research: {prr_result.get('open', 0)} open flaws")
    except Exception as exc:  # noqa: BLE001
        log(f"oversight: repo-research failed ({exc})")

    try:
        investigate.write_digest(
            ctx,
            actions=actions,
            dispatched=False,
        )
        actions.append(f"automation digest → {investigate.digest_path().name}")
    except Exception as exc:  # noqa: BLE001
        log(f"oversight: automation digest failed ({exc})")

    flaws = _repo_flaw_summary()
    cooldown = agent_cooldown_remaining()

    try:
        import peer_playbook as playbook

        playbook.ingest_from_context(ctx)
    except Exception as exc:  # noqa: BLE001
        log(f"oversight: playbook ingest failed ({exc})")

    state = _load_state()
    events.record_snapshot(state, events.metric_snapshot(ctx, flaws))
    extras = {
        "repo_research_new": int(prr_result.get("new") or 0),
        "repo_research_stale_sec": events.repo_research_stale_sec(),
    }
    stagnation = events.evaluate_stagnation(ctx, flaws, state=state, extras=extras)
    dispatch_ok, stagnation, hold_reasons = events.should_dispatch(
        ctx,
        flaws,
        state=state,
        dispatch_enabled=dispatch_agent if dispatch_agent is not None else dispatch_agent_enabled(),
        force=force_agent,
        stagnation=stagnation,
        extras=extras,
    )

    path = write_digest(
        ctx=ctx,
        flaws=flaws,
        actions=actions,
        dispatched=False,
        agent_cooldown=cooldown,
        stagnation=stagnation,
        dispatch_hold=hold_reasons,
    )
    log(f"oversight: digest → {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")

    if digest_only:
        _save_state(state)
        return {"digest": str(path), "actions": actions, "stagnation": stagnation.reasons}

    should_dispatch = dispatch_agent if dispatch_agent is not None else dispatch_agent_enabled()
    dispatched = False
    agent_pending = False

    if should_dispatch and dispatch_ok:
        prompt = build_oversight_prompt(ctx, flaws, stagnation=stagnation)
        PROMPT_PATH.write_text(prompt, encoding="utf-8")

        # OVERSEER_FANOUT_FLOCK_WIRE_2026_09_04 — hold lock across count+spawn.
        lock_fh = _try_overseer_dispatch_lock()
        if lock_fh is None:
            log("oversight: overseer dispatch lock held — skip spawn race")
            actions.append("skip dispatch: overseer flock")
            agent_pending = True
            try:
                trim_msg = trim_excess_overseers()
                if "killed=" in trim_msg:
                    log(f"oversight: {trim_msg}")
                    actions.append(trim_msg)
            except Exception:  # noqa: BLE001
                pass
        else:
            try:
                # Fanout cap first — critical must NOT stack another System Overseer.
                if _overseer_fanout_blocked():
                    log(
                        f"oversight: overseer fanout cap ({OVERSEER_FANOUT_MAX}) — "
                        "skip dispatch (System Overseer already running)"
                    )
                    actions.append("skip dispatch: overseer fanout cap")
                    agent_pending = True
                    try:
                        trim_msg = trim_excess_overseers()
                        if "killed=" in trim_msg:
                            log(f"oversight: {trim_msg}")
                            actions.append(trim_msg)
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    busy = _agent_running()
                    critical = bool(stagnation and stagnation.critical)
                    if busy and not critical:
                        log("oversight: cursor-agent busy — defer dispatch")
                        actions.append("skip dispatch: agent busy")
                        agent_pending = True
                    else:
                        if busy and critical:
                            log("oversight: CRITICAL — dispatch overseer despite busy niches")
                            actions.append("critical: dispatch despite busy")
                        try:
                            import dgx_ram_budget as budget

                            if not budget.dispatch_allowed():
                                log("oversight: RAM cap — skip dispatch")
                                actions.append("skip dispatch: RAM cap")
                                should_dispatch = False
                        except Exception:  # noqa: BLE001
                            pass

                        if should_dispatch:
                            try:
                                import peer_terminal as terminal

                                ready, detail = terminal.desktop_auth_ready()
                                if not ready:
                                    log(f"oversight: auth not ready — {detail}")
                                    actions.append(f"skip dispatch: {detail}")
                                else:
                                    if _overseer_fanout_blocked():
                                        log("oversight: fanout raced during auth — skip")
                                        actions.append("skip dispatch: fanout raced")
                                        agent_pending = True
                                    else:
                                        rc, _ = terminal.run_cursor_agent(
                                            prompt, log_fn=log, sync=False, paid_api=False
                                        )
                                        dispatched = rc == 0
                                        why = "; ".join(stagnation.reasons[:2])[:100]
                                        actions.append(
                                            f"dispatched overseer ({why})"
                                            if dispatched
                                            else f"dispatch rc={rc}"
                                        )
                                        if dispatched:
                                            state["last_agent_ts"] = time.time()
                                            state["last_dispatch_reasons"] = stagnation.reasons[:6]
                                            state["stagnation_cycles"] = 0
                            except Exception as exc:  # noqa: BLE001
                                log(f"oversight: dispatch failed ({exc})")
                                actions.append(f"dispatch failed: {exc}")
            finally:
                try:
                    lock_fh.close()
                except Exception:  # noqa: BLE001
                    pass

        write_digest(
            ctx=ctx,
            flaws=flaws,
            actions=actions,
            dispatched=dispatched,
            agent_pending=agent_pending or (dispatch_ok and not dispatched),
            agent_cooldown=0 if dispatched else cooldown,
            stagnation=stagnation,
            dispatch_hold=hold_reasons,
        )
    elif should_dispatch:
        actions.append(f"held: {'; '.join(hold_reasons[:2])}")
        log(f"oversight: held — {'; '.join(hold_reasons[:2])}")

    try:
        import automation_adapt as adapt

        if adapt.sync_git_fingerprint(ROOT):
            actions.append("adapt: synced git fingerprint after mechanical writes")
    except Exception as exc:  # noqa: BLE001
        log(f"oversight: adapt fingerprint sync failed ({exc})")

    state["last_run_ts"] = time.time()
    state["last_dispatched"] = dispatched
    state["last_actions"] = actions[-10:]
    state["last_health"] = _health_emoji(ctx, flaws)
    state["last_stagnation_score"] = stagnation.score
    _save_state(state)

    return {
        "digest": str(path),
        "dispatched": dispatched,
        "actions": actions,
        "health": state["last_health"],
        "stagnation_score": stagnation.score,
        "stagnation_reasons": stagnation.reasons,
        "dispatch_hold": hold_reasons,
        "agent_cooldown": agent_cooldown_remaining(),
    }


def _log_daemon(msg: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp}  {msg}\n")


def run_forever(*, daemon: bool = False) -> int:
    log_fn = _log_daemon if daemon else print
    log_fn(
        f"oversight forever — mechanical every {mechanical_interval_sec():.0f}s · "
        f"instant_react={instant_react_enabled()} · "
        f"cursor-agent on stagnation/errors (mode={events.agent_dispatch_mode()})"
    )
    watcher = None
    try:
        import peer_transcript as transcript

        watcher = transcript.PeerEventWatcher()
        if watcher.setup(repo_root=None):
            # Only log files — never peer-turn.signal (would feedback-loop with wake_peer).
            for name in ("peer-loop.log", "improve-loop.log", "product-forge.log"):
                watcher.watch_path(CONFIG_DIR / name)
            log_fn("oversight: watching peer/improve/forge logs (instant react)")
        else:
            watcher = None
            log_fn("oversight: kqueue unavailable — interval sleep only")
    except Exception as exc:  # noqa: BLE001
        watcher = None
        log_fn(f"oversight: event watch failed ({exc})")

    try:
        while True:
            result = run_oversight_cycle(log_fn=log_fn)
            # Critical live errors: don't wait full interval — short poll then recheck.
            reasons = result.get("stagnation_reasons") or []
            criticalish = result.get("dispatched") or any(
                "live log:" in str(r) or "verify gate FAIL" in str(r) for r in reasons
            )
            wait = 5.0 if (instant_react_enabled() and criticalish and not result.get("dispatched")) else mechanical_interval_sec()
            if watcher is not None and getattr(watcher, "available", False):
                # Discard kevents from our own digest/log/self-heal writes this cycle.
                drained = watcher.drain()
                if drained:
                    log_fn(f"oversight: drained {drained} self-wake event(s)")
                event = watcher.wait(timeout=wait)
                reason = getattr(event, "reason", "") if event else ""
                if reason in ("timeout", "fallback", ""):
                    continue
                # Log noise is constant — only interrupt wait for fresh error lines.
                # LINUX_MTIME_LOG_EXTRA_REASON_BASELINE_2026_09_08 — Linux mtime
                # extras emit reason=log (not signal); no-hit → benign sleep.
                hits = events.scan_live_error_hits(max_age_sec=45.0)
                if hits:
                    log_fn(f"oversight: live error ({hits[0][:70]}) — instant rescan")
                elif reason in ("transcript", "signal"):
                    log_fn(f"oversight: wake ({reason}) — rescanning")
                else:
                    # Benign log write (reason=log|git) — finish remaining interval.
                    time.sleep(min(wait, mechanical_interval_sec()))
            else:
                time.sleep(wait)
    except KeyboardInterrupt:
        log_fn("oversight forever stopped")
        return 0
    finally:
        if watcher is not None:
            try:
                watcher.close()
            except Exception:  # noqa: BLE001
                pass


def plist_body() -> str:
    py = sys.executable
    script = SCRIPTS / "peer_oversight.py"
    args = [py, str(script), "--forever", "--daemon"]
    args_xml = "\n".join(f"    <string>{a}</string>" for a in args)
    home = Path.home()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{OVERSIGHT_LABEL}</string>
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
    <string>{home}/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>PYTHONPATH</key>
    <string>{SCRIPTS}</string>
  </dict>
</dict>
</plist>
"""


def cmd_install() -> int:
    """OVERSEER_LINUX_OVERSIGHT_STATUS_2026_09_04 — Linux uses systemd, not launchctl."""
    global NAMESPACE, OVERSIGHT_LABEL, PLIST_PATH, LOG_PATH
    ns, label, plist, log = _disk_oversight_identity()
    NAMESPACE = ns
    OVERSIGHT_LABEL = label
    PLIST_PATH = plist
    LOG_PATH = log
    if sys.platform != "darwin":
        import peer_self_heal as heal

        print(heal.linux_install_daemon("oversight"))
        print(f"log: {LOG_PATH}")
        print(f"digest: {digest_path()}")
        print(f"mechanical every {mechanical_interval_sec():.0f}s · cursor-agent: event/stagnation")
        return 0
    uid = os.getuid()
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(plist_body())
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{OVERSIGHT_LABEL}"], capture_output=True)
    proc = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print((proc.stderr or proc.stdout or "bootstrap failed").strip(), file=sys.stderr)
        return 1
    print(f"oversight agent: {PLIST_PATH}")
    print(f"log: {LOG_PATH}")
    print(f"digest: {digest_path()}")
    print(f"mechanical every {mechanical_interval_sec():.0f}s · cursor-agent: event/stagnation")
    return 0


def cmd_uninstall() -> int:
    """OVERSEER_LINUX_OVERSIGHT_STATUS_2026_09_04 — Linux tear-down via systemd."""
    global NAMESPACE, OVERSIGHT_LABEL, PLIST_PATH, LOG_PATH
    ns, label, plist, log = _disk_oversight_identity()
    NAMESPACE = ns
    OVERSIGHT_LABEL = label
    PLIST_PATH = plist
    LOG_PATH = log
    if sys.platform != "darwin":
        import peer_self_heal as heal

        print(heal.linux_uninstall_daemon("oversight"))
        return 0
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{OVERSIGHT_LABEL}"], capture_output=True)
    if PLIST_PATH.is_file():
        PLIST_PATH.unlink()
    print("oversight agent removed")
    return 0


def cmd_status() -> int:
    """OVERSEER_LINUX_OVERSIGHT_STATUS_2026_09_04 — never call launchctl on Linux.

    launchctl FileNotFoundError crashed ``./scripts/peer oversight-status`` and
    made stall-watch treat oversight as STOPPED while systemd was healthy.
    """
    global NAMESPACE, OVERSIGHT_LABEL, PLIST_PATH, LOG_PATH
    ns, label, plist, log = _disk_oversight_identity()
    NAMESPACE = ns
    OVERSIGHT_LABEL = label
    PLIST_PATH = plist
    LOG_PATH = log
    running = False
    live_label = OVERSIGHT_LABEL
    if sys.platform != "darwin":
        import peer_self_heal as heal

        running = heal._systemd_user_active("oversight-loop.service")
        live_label = "oversight-loop.service"
    else:
        uid = os.getuid()
        candidate_labels = [
            OVERSIGHT_LABEL,
            "com.togi.automation-oversight-loop",
            "com.togi.automation-hub-oversight-loop",
        ]
        seen: set[str] = set()
        for cand in candidate_labels:
            if cand in seen:
                continue
            seen.add(cand)
            try:
                proc = subprocess.run(
                    ["launchctl", "print", f"gui/{uid}/{cand}"],
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if proc.returncode == 0 and "state = running" in (proc.stdout or ""):
                running = True
                live_label = cand
                break
    state = _load_state()
    print(f"enabled: {oversight_enabled()}")
    print(f"label: {live_label}")
    print(f"state: {'RUNNING' if running else 'STOPPED'}")
    print(f"dispatch mode: {events.agent_dispatch_mode()}")
    print(f"mechanical interval: {mechanical_interval_sec():.0f}s")
    print(f"agent min interval: {events.agent_min_interval_sec():.0f}s")
    print(f"stagnation cycles: {events.stagnation_cycles_threshold()}")
    print(f"high expectations: {events.high_expectations_enabled()}")
    print(f"agent cooldown: {agent_cooldown_remaining():.0f}s")
    print(f"last stagnation score: {state.get('last_stagnation_score', '?')}")
    print(f"last dispatch reasons: {state.get('last_dispatch_reasons', [])}")
    print(f"last health: {state.get('last_health', '?')}")
    print(f"digest: {digest_path()}")
    print(f"log: {LOG_PATH}")
    return 0 if running else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuous Cursor system oversight")
    parser.add_argument("--once", action="store_true", help="Single oversight cycle")
    parser.add_argument("--forever", action="store_true", help="Loop forever")
    parser.add_argument("--force", action="store_true", help="Force cursor-agent dispatch")
    parser.add_argument("--digest-only", action="store_true", help="Mechanical refresh only")
    parser.add_argument("--no-dispatch", action="store_true", help="Skip cursor-agent")
    parser.add_argument("--daemon", action="store_true", help="Log to oversight-loop.log")
    parser.add_argument("--install", action="store_true", help="Install LaunchAgent")
    parser.add_argument("--uninstall", action="store_true", help="Remove LaunchAgent")
    parser.add_argument("--status", action="store_true", help="Daemon status")
    args = parser.parse_args()

    if args.install:
        return cmd_install()
    if args.uninstall:
        return cmd_uninstall()
    if args.status:
        return cmd_status()
    if args.forever:
        return run_forever(daemon=args.daemon)

    result = run_oversight_cycle(
        log_fn=_log_daemon if args.daemon else print,
        force_agent=args.force,
        digest_only=args.digest_only,
        dispatch_agent=False if args.no_dispatch else None,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
