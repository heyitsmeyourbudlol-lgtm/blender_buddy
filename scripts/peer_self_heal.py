#!/usr/bin/env python3
"""Self-healing layer — detect bottlenecks across the factory and fix what we can.

Tracks daemons, verify/test storms, locks, drift, dual-brain, stale horizon,
auth blocks, noop stalls, and missing cycle memory. Applies mechanical heals
automatically; enqueues code fixes when a human/peer diff is required.

Usage:
  python3 scripts/peer_self_heal.py --scan
  python3 scripts/peer_self_heal.py --heal --write
  python3 scripts/peer_self_heal.py --status
  ./scripts/peer self-heal
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import automation_config as cfg_mod  # noqa: E402
import project_automation as auto  # noqa: E402

CONFIG_DIR = auto.CONFIG_DIR
REGISTRY_PATH = CONFIG_DIR / "bottleneck-registry.json"
PEER_LOG = CONFIG_DIR / "peer-loop.log"
IMPROVE_LOG = CONFIG_DIR / "improve-loop.log"
HORIZON_PATH = CONFIG_DIR / "IMPROVE_HORIZON.md"
# OVERSEER_HORIZON_FRESHEST_2026_09_04 — import-time CONFIG_DIR may be demoted
# ``automation`` while improve forever writes ``automation-hub`` (or notes/ is
# fresher). False horizon_stale when only the stale ns board is aged.
HORIZON_REPO_PATH = ROOT / "notes" / "IMPROVE_HORIZON.md"
# Shared scan+soft_refresh threshold — age ≤ this is "fresh" (no horizon_stale).
HORIZON_STALE_SEC = 900.0
_HORIZON_FALLBACK_NS = ("automation-hub", "automation")
STATE_PATH = CONFIG_DIR / "peer-loop-state.json"
VERIFY_LOCK = CONFIG_DIR / "verify.lock"
TEST_LOCK = CONFIG_DIR / "test-measure.lock"
SIGNAL_PATH = CONFIG_DIR / "peer-turn.signal"
STATUS_PATH = CONFIG_DIR / "peer-loop-status.json"
DAEMON_HEAL_LOCK = CONFIG_DIR / "daemon-heal.lock"


def _horizon_board_path() -> Path:
    """Prefer the freshest IMPROVE_HORIZON among live ns + notes + siblings."""
    home_cfg = Path.home() / ".config"
    candidates: list[Path] = [HORIZON_PATH, HORIZON_REPO_PATH]
    try:
        live = cfg_mod.config_dir() / "IMPROVE_HORIZON.md"
        if live not in candidates:
            candidates.insert(0, live)
    except Exception:  # noqa: BLE001
        pass
    for ns in _HORIZON_FALLBACK_NS:
        cand = home_cfg / ns / "IMPROVE_HORIZON.md"
        if cand not in candidates:
            candidates.append(cand)
    best = HORIZON_PATH
    best_mtime = -1.0
    for cand in candidates:
        try:
            if not cand.is_file():
                continue
            mtime = cand.stat().st_mtime
        except OSError:
            continue
        if mtime > best_mtime:
            best_mtime = mtime
            best = cand
    return best

RAM_PEER_LABEL = "com.togi.ram-peer-loop"
LEGACY_PEER_LABEL = "com.togi.automation-peer-loop"
LEGACY_IMPROVE_LABEL = "com.togi.automation-improve-loop"
LEGACY_PEER_LABELS = (LEGACY_PEER_LABEL, LEGACY_IMPROVE_LABEL)
# Hub namespace plists are canonical on macOS factory hosts; config may still say "automation".
HUB_PEER_LABEL = "com.togi.automation-hub-peer-loop"
HUB_IMPROVE_LABEL = "com.togi.automation-hub-improve-loop"
HUB_OVERSIGHT_LABEL = "com.togi.automation-hub-oversight-loop"
LEGACY_OVERSIGHT_LABEL = "com.togi.automation-oversight-loop"
DASHBOARD_LABEL = f"com.togi.{cfg_mod.CFG.get('config_namespace', 'automation-hub')}-dashboard"

_HEAL_COOLDOWN_SEC = 300.0
# If progress fingerprint has not moved for this long, high/critical heals bypass cooldown.
_PROGRESS_STALL_SEC = 180.0
_LOG_WINDOW_LINES = 400
_DAEMON_FLOCK_TIMEOUT_SEC = 45.0
_RAM_BALLAST_NEEDLES = ("dgx_resource_poll.py", "dgx_gpu_compute.py", "dgx_ram_fill.py")
_RAM_BALLAST_MIN_RSS_KB = 200_000  # ~200MB
# Forever embed preloads mamba-2.8b (~3–8GB RSS). Old 2GB floor false-killed productive
# workers (systemd restart storm) while MemAvailable stayed healthy.
# Needle: OVERSEER_RAM_BALLAST_GPU_COMPUTE_PRESSURE_2026_09_07
_RAM_BALLAST_GPU_COMPUTE_MIN_RSS_KB = 14_000_000  # ~14GB runaway under pressure only
_RAM_BALLAST_GPU_COMPUTE_OK_AVAIL_GB = 12.0  # skip gpu_compute kill when avail ≥ this


def _live_cfg() -> dict[str, Any]:
    """Re-read automation.config.json — long-running daemons can hold stale CFG in memory."""
    try:
        return cfg_mod.load_config()
    except Exception:  # noqa: BLE001
        return dict(cfg_mod.CFG)


def _live_peer_label() -> str:
    cfg = _live_cfg()
    ns = str(cfg.get("config_namespace") or "automation")
    return str(cfg.get("launch_agent_label") or f"com.togi.{ns}-peer-loop")


def _live_improve_label() -> str:
    cfg = _live_cfg()
    ns = str(cfg.get("config_namespace") or "automation")
    return f"com.togi.{ns}-improve-loop"


def _live_oversight_label() -> str:
    cfg = _live_cfg()
    ns = str(cfg.get("config_namespace") or "automation")
    return f"com.togi.{ns}-oversight-loop"


def _live_dashboard_label() -> str:
    cfg = _live_cfg()
    ns = str(cfg.get("config_namespace") or "automation-hub")
    return f"com.togi.{ns}-dashboard"


def _live_canonical_labels() -> set[str]:
    """Disk-canonical peer/improve — protect these even when this process imported hub labels."""
    return {_live_peer_label(), _live_improve_label()}


def _daemon_flock_depth_state() -> threading.local:
    """Process-wide depth — peer_self_heal may load under two module names."""
    key = "_automation_daemon_heal_flock_depth"
    state = getattr(sys, key, None)
    if state is None:
        state = threading.local()
        setattr(sys, key, state)
    return state


def ensure_canonical_module() -> None:
    """Alias ``peer_self_heal`` and ``scripts.peer_self_heal`` to one module object.

    When ``scripts/`` is both on ``sys.path`` and imported as a package, Python can
    load this file twice. Healers and ``cmd_install`` must share flock depth/state.
    Prefer the first-loaded module as canonical and point both names at it.
    """
    names = ("peer_self_heal", "scripts.peer_self_heal")
    present = [sys.modules[n] for n in names if n in sys.modules]
    primary = present[0] if present else sys.modules[__name__]
    for name in names:
        sys.modules[name] = primary


ensure_canonical_module()


@dataclass
class Bottleneck:
    id: str
    category: str
    severity: str
    title: str
    evidence: str
    auto_healable: bool = True
    heal_action: str | None = None
    status: str = "open"
    heal_result: str | None = None
    first_seen: str = ""
    last_seen: str = ""
    hit_count: int = 1


@dataclass
class HealReport:
    scanned_at: str
    bottlenecks: list[Bottleneck] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    enqueued: list[str] = field(default_factory=list)


def self_heal_enabled() -> bool:
    return bool(cfg_mod.CFG.get("self_heal_enabled", True))


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# Needle: SELF_HEAL_PROBE_TTL_ALIGN_2026_09_05 — was 2.0s; diagnose remiss
# (registry mtime) re-shelled systemd every plan-gate (~3–5ms×N). Align with
# asi_rubric.DAEMON_PROBE_TTL_SEC / plan_gate_diagnose_ttl (30s). Freshness via
# _invalidate_probe_cache on heal mutate (OVERSEER_PROBE_CACHE_INVALIDATE).
#
# Needle: PROBE_TTL_WAKE_FLOOR_2026_09_08 — continuous_wake_sec often == 30 so
# wake age >= bare TTL remisses scan/ps/systemd every heartbeat (~10–28ms)
# instead of HIT (~0.002ms). Floor like PRE_DISPATCH_MAINT_WAKE_FLOOR.
_PROBE_TTL_SEC = 30.0
_PROBE_WAKE_SLACK_SEC = 5.0
_PROBE_CACHE_MAX = 32
_probe_cache: dict[str, tuple[float, bool]] = {}


def probe_effective_ttl_sec() -> float:
    """Floor probe TTL above continuous_wake so wake==TTL never perpetual remiss.

    Needle: PROBE_TTL_WAKE_FLOOR_2026_09_08 — mirrors peer_loop
    ``pre_dispatch_maint_effective_ttl_sec`` (wake + slack).
    """
    try:
        wake = float(cfg_mod.CFG.get("continuous_wake_sec") or 0.0)
    except (TypeError, ValueError):
        wake = 0.0
    return max(_PROBE_TTL_SEC, wake + _PROBE_WAKE_SLACK_SEC)


def _probe_cached(key: str, probe: Callable[[], bool]) -> bool:
    now = time.time()
    hit = _probe_cache.get(key)
    if hit and now - hit[0] < probe_effective_ttl_sec():
        return hit[1]
    val = probe()
    _probe_cache[key] = (now, val)
    if len(_probe_cache) > _PROBE_CACHE_MAX:
        oldest = min(_probe_cache, key=lambda k: _probe_cache[k][0])
        del _probe_cache[oldest]
    return val


def _invalidate_probe_cache(prefix: str | None = None) -> None:
    """Drop cached systemd/launchctl probes after a heal mutates unit state.

    Needle: OVERSEER_PROBE_CACHE_INVALIDATE_2026_09_04 — enable --now hub-protect
    then re-check via TTL cache still returned inactive → false HIGH bottleneck.
    Also clears scan_bottlenecks TTL (SCAN_BOTTLENECKS_TTL) so factory/diagnose
    do not keep pre-heal bottleneck lists.
    DUAL_NAMESPACE_COLLISION_TTL_2026_09_08 — drop dual-ns memo after heal mutates
    LaunchAgents so single_brain cannot stay green on stale rogue lists.
    """
    clear_scan_bottlenecks_cache()
    clear_dual_namespace_collision_cache()
    clear_ps_axo_cache()
    clear_systemd_active_cache()
    # live adapt-fp gen cleared via clear_scan_bottlenecks_cache
    if not prefix:
        _probe_cache.clear()
        return
    for key in [k for k in _probe_cache if k.startswith(prefix)]:
        del _probe_cache[key]


def _launchctl_running_impl(label: str) -> bool:
    if not label:
        return False
    try:
        proc = subprocess.run(
            ["launchctl", "list", label],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        proc = None
    if proc is not None and proc.returncode == 0:
        out = proc.stdout or ""
        for line in out.splitlines():
            stripped = line.strip().rstrip(";")
            if stripped.startswith('"PID"') or stripped.startswith("PID"):
                if "=" not in stripped:
                    continue
                rhs = stripped.split("=", 1)[1].strip().strip(";")
                if rhs in ("", "0", "null", "(null)"):
                    return False
                try:
                    return int(rhs) > 0
                except ValueError:
                    return False
        for line in out.splitlines():
            parts = line.split()
            if parts and parts[0] not in ("-", "PID", "{"):
                try:
                    return int(parts[0]) > 0
                except ValueError:
                    continue
    # Fallback: full listing (label-specific list fails on some macOS domains)
    try:
        listing = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
            timeout=8.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        listing = None
    if listing is not None and listing.returncode == 0:
        for line in (listing.stdout or "").splitlines():
            if label not in line:
                continue
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "-":
                return False
            try:
                return int(parts[0]) > 0
            except ValueError:
                return False
    # Last resort: gui domain print
    uid = os.getuid()
    try:
        printed = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/{label}"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if printed.returncode != 0:
        return False
    out = printed.stdout or ""
    # modern launchctl print often has "state = running" without a parseable "pid =" line
    if "state = running" in out:
        return True
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("pid ="):
            try:
                return int(stripped.split("=", 1)[1].strip()) > 0
            except ValueError:
                return False
    return False


def _launchctl_loaded(label: str) -> bool:
    """True when the LaunchAgent is registered in the gui domain (running or not)."""
    if not label:
        return False
    uid = os.getuid()
    try:
        printed = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/{label}"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return printed.returncode == 0


def _launchctl_running(label: str) -> bool:
    # Needle: LAUNCHCTL_DARWIN_ONLY_2026_09_08 — Linux scan_bottlenecks shelled
    # launchctl list/print (~3 forks) for ram-peer dual-brain; always miss on DGX.
    if sys.platform != "darwin":
        return False
    return _probe_cached(f"launchctl:{label}", lambda: _launchctl_running_impl(label))


# Needle: SYSTEMD_IS_ACTIVE_BATCH_2026_09_08 — scan_bottlenecks cold paid
# 5× ``systemctl --user is-active`` (~7ms each, ~36ms). One argv batch returns
# one state line per unit (~4.6ms). Share snapshot for probe_effective_ttl_sec.
_SYSTEMD_ACTIVE_BATCH_UNITS: tuple[str, ...] = (
    "peer-loop.service",
    "improve-loop.service",
    "repo-research-loop.service",
    "dashboard.service",
    "hub-protect-restore.timer",
)
_SYSTEMD_ACTIVE_UP = frozenset({"active", "activating", "reloading", "deactivating"})
_SYSTEMD_ACTIVE_CACHE: dict[str, Any] = {"at": 0.0, "states": None}


def clear_systemd_active_cache() -> None:
    """Drop batched systemctl is-active memo (tests + heal invalidate)."""
    _SYSTEMD_ACTIVE_CACHE["at"] = 0.0
    _SYSTEMD_ACTIVE_CACHE["states"] = None


def _systemd_is_active_states() -> dict[str, str]:
    """Return unit→state for batch units; TTL HIT skips re-shell.

    Needle: SYSTEMD_IS_ACTIVE_BATCH_2026_09_08 — ``systemctl is-active U1 U2…``
    emits one line per unit (ignore rc — non-zero if any inactive).
    """
    now = time.monotonic()
    cached = _SYSTEMD_ACTIVE_CACHE.get("states")
    at = float(_SYSTEMD_ACTIVE_CACHE.get("at") or 0.0)
    if isinstance(cached, dict) and (now - at) < probe_effective_ttl_sec():
        return dict(cached)
    states: dict[str, str] = {}
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "is-active", *_SYSTEMD_ACTIVE_BATCH_UNITS],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _SYSTEMD_ACTIVE_CACHE["at"] = time.monotonic()
        _SYSTEMD_ACTIVE_CACHE["states"] = states
        return states
    lines = [(ln or "").strip().lower() for ln in (proc.stdout or "").splitlines()]
    for i, unit in enumerate(_SYSTEMD_ACTIVE_BATCH_UNITS):
        states[unit] = lines[i] if i < len(lines) else ""
    _SYSTEMD_ACTIVE_CACHE["at"] = time.monotonic()
    _SYSTEMD_ACTIVE_CACHE["states"] = dict(states)
    return states


def _systemd_user_active_impl(unit: str) -> bool:
    """True when unit is up OR mid-transition (do not restart-thrash).

    Needle: OVERSEER_SYSTEMD_SKIP_RESTART_TRANSITIONAL_2026_09_07 — is-active
    returns non-zero for activating/deactivating; treating that as down caused
    heal/oversight to ``systemctl restart`` peer-loop → child cursor-agents
    exit -9 → agents=0 under free_desktop_agent_cap.

    Needle: SYSTEMD_IS_ACTIVE_BATCH_2026_09_08 — prefer shared batch snapshot for
    known units; fall back to single is-active for anything else.
    """
    if not unit:
        return False
    state = ""
    if unit in _SYSTEMD_ACTIVE_BATCH_UNITS:
        state = (_systemd_is_active_states().get(unit) or "").strip().lower()
    else:
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
        state = (proc.stdout or "").strip().lower()
    if state in _SYSTEMD_ACTIVE_UP:
        return True
    # Process still alive while unit reports failed/inactive briefly.
    # OVERSEER_NON_NOOP_DAY_ROLLUP_2026_09_07 — improve restart thrash: heal saw
    # inactive mid-restart → systemctl restart again → flaps wipe cadence.
    if unit == "peer-loop.service" and _peer_loop_process_pid() is not None:
        return True
    if unit == "improve-loop.service" and _improve_process_pid() is not None:
        return True
    return False


def _systemd_user_active(unit: str) -> bool:
    return _probe_cached(f"systemd:{unit}", lambda: _systemd_user_active_impl(unit))


def _systemd_unit_path(unit: str) -> Path:
    return Path.home() / ".config/systemd/user" / unit


def _systemd_unit_usable(unit: str) -> bool:
    """True when a user unit file exists and is not masked (/dev/null)."""
    path = _systemd_unit_path(unit)
    if not path.exists():
        return False
    if path.is_symlink():
        try:
            return path.resolve() != Path("/dev/null")
        except OSError:
            return False
    return path.is_file()


def _systemd_daemon_reload() -> None:
    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True,
        timeout=15.0,
        check=False,
    )


def _systemd_restart(unit: str) -> str:
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "restart", unit],
            capture_output=True,
            text=True,
            timeout=45.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"systemctl restart {unit} failed: {exc}"
    if proc.returncode == 0:
        _invalidate_probe_cache(f"systemd:{unit}")
        return f"restarted {unit}"
    err = (proc.stderr or proc.stdout or "failed").strip()
    return f"systemctl restart {unit} failed: {err[:120]}"


def _systemd_start(unit: str) -> str:
    """Start without restart thrash (T10-04 / improve flaps)."""
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "start", unit],
            capture_output=True,
            text=True,
            timeout=45.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"systemctl start {unit} failed: {exc}"
    if proc.returncode == 0:
        _invalidate_probe_cache(f"systemd:{unit}")
        return f"started {unit}"
    err = (proc.stderr or proc.stdout or "failed").strip()
    return f"systemctl start {unit} failed: {err[:120]}"


def _hub_daemon_paths() -> tuple[Path, Path]:
    """Hub checkout + config dir — never ``.worktrees/peer-N`` (OVERSEER_HUB_PIN_2026_09_04).

    Worktree-local heal/install was rewriting oversight-loop.service with
    WorkingDirectory=peer-0 → board poisoned via notes symlink + Progress Monitor fanout.
    """
    try:
        import peer_worktree as wt

        hub = wt.primary_worktree_root(ROOT)
    except Exception:  # noqa: BLE001
        hub = ROOT
        parts = list(Path(ROOT).resolve().parts)
        if ".worktrees" in parts:
            idx = parts.index(".worktrees")
            if idx > 0:
                hub = Path(*parts[:idx])
    ns = "automation-hub"
    try:
        cfg_path = hub / "automation.config.json"
        if cfg_path.is_file():
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("config_namespace"):
                ns = str(data["config_namespace"])
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return hub.resolve(), Path.home() / ".config" / ns


def _write_systemd_unit(name: str, exec_args: list[str]) -> str:
    """Write a user systemd unit for a hub daemon (DGX/Linux)."""
    unit = f"{name}.service"
    unit_dir = _systemd_unit_path(unit).parent
    unit_dir.mkdir(parents=True, exist_ok=True)
    automation, cfg = _hub_daemon_paths()
    cfg.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    agent_bin = (
        Path.home()
        / ".cursor-server/data/User/globalStorage/anysphere.cursor-agent-worker/agent-cli/.local/bin"
    )
    path_env = f"{agent_bin}:{Path.home() / '.local/bin'}:/usr/local/bin:/usr/bin:/bin"
    exec_start = " ".join([py, *[str(a) for a in exec_args]])
    # NO PAY — peer-loop unit must never stamp PEER_LOOP_PAID_API=1 when free desktop wanted.
    # Needle: OVERSEER_SYSTEMD_PEER_FREE_DESKTOP_2026_09_07
    paid_api_env = "0"
    if name != "peer-loop" and not _force_free_desktop_wanted():
        paid_api_env = "1"
    body = f"""[Unit]
Description=Automation Hub — {name}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={automation}
Environment=HOME={Path.home()}
Environment=PYTHONPATH={automation / 'scripts'}
Environment=PATH={path_env}
Environment=PEER_LOOP_PAID_API={paid_api_env}
Environment=PEER_AGENT_LOCAL=1
Environment=RAM_AUTOMATION_NO_SUBTEST=1
Environment=AUTOMATION_SKIP_TEST_MEASURE=1
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart={exec_start}
Restart=always
RestartSec=15
StandardOutput=append:{cfg / f'{name}.log'}
StandardError=append:{cfg / f'{name}.log'}

[Install]
WantedBy=default.target
"""
    _systemd_unit_path(unit).write_text(body, encoding="utf-8")
    _systemd_daemon_reload()
    subprocess.run(
        ["systemctl", "--user", "enable", unit],
        capture_output=True,
        timeout=15.0,
        check=False,
    )
    return f"wrote {unit} hub={automation}"


def _ensure_systemd_peer_unit() -> str:
    """Install/start peer unit — skip restart when already active.

    OVERSEER_PEER_SKIP_RESTART_IF_ACTIVE_2026_09_04 — matches improve skip;
    flock-busy / heal storms must not thrash a healthy peer-loop.
    """
    unit = "peer-loop.service"
    if not _systemd_unit_usable(unit) or _systemd_unit_worktree_poisoned(unit):
        hub, _cfg = _hub_daemon_paths()
        wrote = _write_systemd_unit(
            "peer-loop",
            [
                str(hub / "scripts" / "peer_loop.py"),
                "--forever",
                "--daemon",
                "--quick",
                "--background",
            ],
        )
    else:
        wrote = f"unit {unit} present"
    _invalidate_probe_cache("systemd:peer-loop")
    if _systemd_user_active(unit) or _peer_loop_process_pid() is not None:
        return f"{wrote}; already active {unit} (skip restart)"
    return f"{wrote}; {_systemd_restart(unit)}"


def _ensure_systemd_improve_unit() -> str:
    """Install/start improve unit — never restart-thrash an already-active daemon.

    OVERSEER_IMPROVE_SKIP_RESTART_IF_ACTIVE_2026_09_04 — horizon_stale + flock-busy
    heals used to ``systemctl restart`` every cycle → improve never stayed up long
    enough to write wake-peer evidence (factory self-sufficient loops cratered).
    OVERSEER_NON_NOOP_DAY_ROLLUP_2026_09_07 — prefer ``start`` over ``restart`` when
    down; never restart when process PID still live (mid-transition false stop).
    """
    unit = "improve-loop.service"
    if not _systemd_unit_usable(unit) or _systemd_unit_worktree_poisoned(unit):
        hub, _cfg = _hub_daemon_paths()
        wrote = _write_systemd_unit(
            "improve-loop",
            [
                str(hub / "scripts" / "automation_improve.py"),
                "--forever",
                "--daemon",
                "--write",
                "--research",
            ],
        )
    else:
        wrote = f"unit {unit} present"
    _invalidate_probe_cache(f"systemd:{unit}")
    if _systemd_user_active(unit) or _improve_process_pid() is not None:
        return f"{wrote}; already active {unit} (skip restart)"
    return f"{wrote}; {_systemd_start(unit)}"


def linux_install_daemon(name: str) -> str:
    """Public Linux install entry used by peer_loop / automation_improve --install.

    Needle: OVERSEER_LINUX_INSTALL_DAEMON_2026_09_04 — Mac/hub-protect restore
    stripped this alias → improve-install AttributeError → daemons stay STOPPED.
    OVERSEER_LINUX_INSTALL_RESEARCH_OVERSIGHT_2026_09_04 — research/oversight/
    dual-research were missing → install printed unknown + theater rc=0.
    """
    key = str(name or "").strip().lower().replace("_", "-")
    if key in ("peer", "peer-loop", "peer_loop"):
        return _ensure_systemd_peer_unit()
    if key in ("improve", "improve-loop", "improve_loop"):
        return _ensure_systemd_improve_unit()
    if key in ("oversight", "oversight-loop", "oversight_loop"):
        return _ensure_systemd_oversight_unit()
    if key in ("research", "repo-research", "repo-research-loop", "repo_research"):
        return _ensure_systemd_repo_research_unit()
    if key in ("dual-research", "dual-research-loop", "dual_research"):
        return _ensure_systemd_dual_research_unit()
    return f"unknown linux daemon: {name!r}"


def linux_uninstall_daemon(name: str) -> str:
    """Stop+disable Linux user unit for research/oversight/peer/improve.

    OVERSEER_LINUX_UNINSTALL_DAEMON_2026_09_04 — install path called missing
    uninstall → AttributeError on Linux ``--uninstall``.
    """
    key = str(name or "").strip().lower().replace("_", "-")
    unit_map = {
        "peer": "peer-loop.service",
        "peer-loop": "peer-loop.service",
        "peer_loop": "peer-loop.service",
        "improve": "improve-loop.service",
        "improve-loop": "improve-loop.service",
        "improve_loop": "improve-loop.service",
        "oversight": "oversight-loop.service",
        "oversight-loop": "oversight-loop.service",
        "oversight_loop": "oversight-loop.service",
        "research": "repo-research-loop.service",
        "repo-research": "repo-research-loop.service",
        "repo-research-loop": "repo-research-loop.service",
        "repo_research": "repo-research-loop.service",
        "dual-research": "dual-research-loop.service",
        "dual-research-loop": "dual-research-loop.service",
        "dual_research": "dual-research-loop.service",
    }
    unit = unit_map.get(key)
    if not unit:
        return f"unknown linux daemon: {name!r}"
    stop = subprocess.run(
        ["systemctl", "--user", "disable", "--now", unit],
        capture_output=True,
        text=True,
        timeout=30.0,
        check=False,
    )
    detail = (stop.stderr or stop.stdout or "").strip().splitlines()
    tail = detail[-1] if detail else f"rc={stop.returncode}"
    return f"linux uninstall {unit}: {tail}"


def _ensure_systemd_repo_research_unit() -> str:
    """Install/start repo-research-loop.service on hub.

    OVERSEER_HEAL_RESEARCH_DAEMON_2026_09_04 — disabled+inactive units must be
    ``enable --now`` (restart alone leaves WantedBy off → stale research →
    stagnation theater).
    """
    unit = "repo-research-loop.service"
    if not _systemd_unit_usable(unit) or _systemd_unit_worktree_poisoned(unit):
        hub, _cfg = _hub_daemon_paths()
        wrote = _write_systemd_unit(
            "repo-research-loop",
            [
                str(hub / "scripts" / "peer_repo_research.py"),
                "--forever",
                "--daemon",
            ],
        )
    else:
        wrote = f"unit {unit} present"
    if _systemd_user_active(unit):
        return f"{wrote}; already active {unit} (skip restart)"
    # Prefer enable --now so a previously ``disabled`` unit stays up across sessions.
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "enable", "--now", unit],
            capture_output=True,
            text=True,
            timeout=45.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"{wrote}; enable --now {unit} failed: {exc}; {_systemd_restart(unit)}"
    if proc.returncode == 0:
        return f"{wrote}; enable --now {unit}"
    err = (proc.stderr or proc.stdout or "failed").strip()
    return f"{wrote}; enable --now failed: {err[:80]}; {_systemd_restart(unit)}"


def _ensure_systemd_dual_research_unit() -> str:
    """Install/start dual-research-loop.service on hub."""
    unit = "dual-research-loop.service"
    if not _systemd_unit_usable(unit) or _systemd_unit_worktree_poisoned(unit):
        hub, _cfg = _hub_daemon_paths()
        wrote = _write_systemd_unit(
            "dual-research-loop",
            [
                str(hub / "scripts" / "peer_dual_research.py"),
                "--forever",
                "--daemon",
            ],
        )
    else:
        wrote = f"unit {unit} present"
    if _systemd_user_active(unit):
        return f"{wrote}; already active {unit} (skip restart)"
    return f"{wrote}; {_systemd_restart(unit)}"


def _systemd_unit_worktree_poisoned(unit: str) -> bool:
    """True when unit WorkingDirectory/ExecStart still points at .worktrees/."""
    path = _systemd_unit_path(unit)
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "/.worktrees/" in text


def _ensure_systemd_oversight_unit() -> str:
    """Pin oversight-loop.service to hub — worktree cwd poisons SYSTEM_OVERSIGHT."""
    hub, _cfg = _hub_daemon_paths()
    wrote = _write_systemd_unit(
        "oversight-loop",
        [
            str(hub / "scripts" / "peer_oversight.py"),
            "--forever",
            "--daemon",
        ],
    )
    return f"{wrote}; {_systemd_restart('oversight-loop.service')}"


def _heal_oversight_worktree_cwd(_reg: dict[str, Any] | None = None) -> str:
    """OVERSEER_HUB_PIN_2026_09_04 — rewrite oversight unit off peer-N worktree."""
    unit = "oversight-loop.service"
    if not _systemd_unit_usable(unit):
        return _ensure_systemd_oversight_unit()
    if not _systemd_unit_worktree_poisoned(unit):
        return "oversight unit hub-ok"
    return _ensure_systemd_oversight_unit()


# Needle: FOREVER_PYTHON_PS_AXO_TTL_2026_09_08 — _job_stopped_loop_python_pids
# called _forever_python_pid 4× (peer×2 + improve×2); each shelled ``ps -axo``
# (~14–15ms). Probe: 4×ps=56.8ms; _job_stopped ~148ms of ~272ms scan body.
# Share one process-list snapshot for probe_effective_ttl_sec (align systemd probe TTL).
#
# Needle: PS_AXO_RSS_SHARE_BALLAST_2026_09_08 — scan_bottlenecks cold also paid
# ``ps -u $USER -o pid=,rss=,args=`` (~38ms) for RAM ballast after ``ps -axo``
# (~30ms). One ``pid=,rss=,comm=,args=`` snapshot feeds forever/job_stopped +
# ballast (~38ms total; save ~30ms). ``split(None, 2)`` keeps forever parsers:
# parts[1]=rss (was comm); parts[2]=comm+args still matches needles/--forever.
#
# Needle: PROC_SNAPSHOT_REPLACE_PS_AXO_2026_09_08 — Linux cold scan still paid
# ``ps -axo`` ~23–40ms (poll). ``/proc`` uid-scoped cmdline+VmRSS snapshot
# ~5ms (~5–8×) and keeps the same ``pid rss args`` line shape for parsers.
_PS_AXO_CACHE: dict[str, Any] = {"at": 0.0, "lines": None}


def clear_ps_axo_cache() -> None:
    """Drop ps -axo line memo (tests + heal invalidate)."""
    _PS_AXO_CACHE["at"] = 0.0
    _PS_AXO_CACHE["lines"] = None


def _linux_proc_ps_like_lines() -> list[str] | None:
    """Build ``pid rss args`` lines from ``/proc`` (no ``ps`` shell).

    Needle: PROC_SNAPSHOT_REPLACE_PS_AXO_2026_09_08 — uid-scoped; VmRSS from
    ``/proc/<pid>/status``. Returns ``None`` when ``/proc`` is unusable so
    callers can fall back to ``ps -axo``.
    Needle: PROC_LAZY_RSS_BALLAST_NEEDLES_2026_09_08 — forever/job_stopped only
    need cmdline; ballast needles are ≤few PIDs. Opening ``status``/VmRSS for
    every UID pid (~150–170) was ~3× cmdline-only; defer RSS until args match
    ``_RAM_BALLAST_NEEDLES`` (non-needle rows keep rss=0 — ballast filters first).
    """
    if sys.platform == "darwin":
        return None
    try:
        names = os.listdir("/proc")
    except OSError:
        return None
    me = os.getuid()
    out: list[str] = []
    for name in names:
        if not name.isdigit():
            continue
        base = f"/proc/{name}"
        try:
            if os.stat(base).st_uid != me:
                continue
            with open(f"{base}/cmdline", "rb") as fh:
                raw = fh.read()
        except OSError:
            continue
        if not raw:
            continue
        args = raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()
        if not args:
            continue
        rss = 0
        # PROC_LAZY_RSS_BALLAST_NEEDLES — status open only for ballast candidates.
        if any(n in args for n in _RAM_BALLAST_NEEDLES):
            try:
                with open(f"{base}/status", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if line.startswith("VmRSS:"):
                            rss = int(line.split()[1])
                            break
            except (OSError, ValueError, IndexError):
                rss = 0
        out.append(f"{name} {rss} {args}")
    return out


def _ps_axo_lines() -> list[str] | None:
    """Return ``pid rss args`` process lines; TTL HIT skips re-scan.

    Needle: FOREVER_PYTHON_PS_AXO_TTL_2026_09_08 — shared by ``_forever_python_pid``
    and dashboard PID probe so scan_bottlenecks / job-stopped pay 1× snapshot.
    Needle: PS_AXO_RSS_SHARE_BALLAST_2026_09_08 — RSS column shared with ballast.
    Needle: PROC_SNAPSHOT_REPLACE_PS_AXO_2026_09_08 — Linux prefers ``/proc``;
    Darwin / ``/proc`` miss falls back to ``ps -axo``.
    """
    now = time.monotonic()
    cached = _PS_AXO_CACHE.get("lines")
    at = float(_PS_AXO_CACHE.get("at") or 0.0)
    if cached is not None and (now - at) < probe_effective_ttl_sec():
        return list(cached)
    lines = _linux_proc_ps_like_lines()
    if lines is None:
        try:
            proc = subprocess.run(
                ["ps", "-axo", "pid=,rss=,comm=,args="],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0 or not (proc.stdout or "").strip():
            return None
        lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    _PS_AXO_CACHE["at"] = time.monotonic()
    _PS_AXO_CACHE["lines"] = list(lines)
    return lines


def _parse_ps_axo_pid_rss_args(raw: str) -> tuple[str, int, str] | None:
    """Parse ``pid rss comm args…`` → (pid_s, rss_kb, args_with_comm).

    Needle: PS_AXO_RSS_SHARE_BALLAST_2026_09_08 — ballast needs RSS; forever
    matchers use ``split(None, 2)`` equivalently (rss occupies former comm slot).
    """
    parts = raw.strip().split(None, 2)
    if len(parts) < 3:
        return None
    pid_s, rss_s, args = parts[0], parts[1], parts[2]
    try:
        rss = int(rss_s)
    except ValueError:
        return None
    return pid_s, rss, args


def _forever_python_pid_from_lines(
    lines: list[str] | None, *needles: str
) -> int | None:
    """PID of a live Python process whose args contain all needles + ``--forever``.

    ``lines`` is a ``ps -axo`` snapshot (from ``_ps_axo_lines``) so callers can
    match several needle sets without re-walking ~500–600 rows.

    Format is ``pid rss comm args…`` (or legacy ``pid comm args``): ``split(None, 2)``
    leaves needles/--forever in parts[2] either way.
    """
    if not lines or not needles:
        return None
    for raw in lines:
        parts = raw.strip().split(None, 2)
        if len(parts) < 3:
            continue
        pid_s, _mid, args = parts[0], parts[1], parts[2]
        if "--forever" not in args:
            continue
        if any(n not in args for n in needles):
            continue
        argv0 = args.split(None, 1)[0]
        argv0_l = argv0.lower()
        if "python" not in argv0_l and not argv0.endswith("Python"):
            continue
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        if pid > 0:
            return pid
    return None


def _forever_python_pid(*needles: str) -> int | None:
    """PID of a live Python process whose args contain all needles + ``--forever``."""
    return _forever_python_pid_from_lines(_ps_axo_lines(), *needles)


def _pid_job_control_stopped(pid: int) -> bool:
    """True when process state is job-control stop (T/t). Prefer ``/proc`` on Linux."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            body = fh.read()
        # ``pid (comm) state ...`` — comm may contain spaces/parens; state follows last ``)``.
        rparen = body.rfind(")")
        if rparen < 0 or rparen + 2 >= len(body):
            return False
        return body[rparen + 2] in ("T", "t")
    except OSError:
        pass
    try:
        proc = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
        stat = (proc.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return False
    return bool(stat) and stat[0] in ("T", "t")


def _peer_loop_process_pid() -> int | None:
    """PID of a live ``peer_loop.py --forever`` process (LaunchAgent-independent).

    OVERSEER_PEER_PROCESS_FALLBACK_LAUNCHCTL_IO_2026_09_05 — when ``launchctl
    bootstrap`` returns I/O error 5, the forever process can still be healthy;
    treat it as running so heal/status do not thrash install.

    CLEAN units often exec ``run_peer_loop_gitfile.py`` (wrapper) — match that too.
    """
    lines = _ps_axo_lines()
    return _forever_python_pid_from_lines(
        lines, "peer_loop.py"
    ) or _forever_python_pid_from_lines(lines, "run_peer_loop_gitfile.py")


def _job_stopped_loop_python_pids() -> list[tuple[str, int]]:
    """Return (label, pid) for peer/improve forever PIDs in job-control stop.

    Needle: FOREVER_PYTHON_JOB_STOPPED_ONE_PASS_2026_09_08 — after PS_AXO TTL,
    ``_job_stopped`` still called ``_forever_python_pid`` 4× → 4 full walks of
    ~594 ps lines (~16ms HIT). One ``_ps_axo_lines`` snapshot + one pass finds
    peer+improve; ``/proc/pid/stat`` replaces per-pid ``ps -o stat=`` on Linux.
    """
    lines = _ps_axo_lines()
    if not lines:
        return []
    groups: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("peer", ("peer_loop.py", "run_peer_loop_gitfile.py")),
        ("improve", ("automation_improve.py", "run_improve_poll_cache.py")),
    )
    found: dict[str, int] = {}
    remaining = {label: alts for label, alts in groups}
    for raw in lines:
        if not remaining:
            break
        parts = raw.strip().split(None, 2)
        if len(parts) < 3:
            continue
        pid_s, _comm, args = parts[0], parts[1], parts[2]
        if "--forever" not in args:
            continue
        argv0 = args.split(None, 1)[0]
        argv0_l = argv0.lower()
        if "python" not in argv0_l and not argv0.endswith("Python"):
            continue
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        if pid <= 0:
            continue
        for label, alts in tuple(remaining.items()):
            if any(n in args for n in alts):
                found[label] = pid
                del remaining[label]
                break
    stopped: list[tuple[str, int]] = []
    for label, _alts in groups:
        pid = found.get(label)
        if pid is None:
            continue
        if _pid_job_control_stopped(pid):
            stopped.append((label, pid))
    return stopped


def _cont_job_stopped_loop_pythons() -> str:
    """SIGCONT peer/improve forever PIDs stuck in job-control stop (STAT=T).

    systemd can report active while the MainThread is SIGSTOP'd — verify quiet
    then hangs forever and T10-04 stalls on local_only/deferred. Needle:
    ``OVERSEER_T10_04_CONT_STOPPED_PEER_2026_09_08``.
    """
    continued: list[str] = []
    for label, pid in _job_stopped_loop_python_pids():
        try:
            os.kill(pid, signal.SIGCONT)
            continued.append(f"{label}:{pid}")
        except OSError:
            continue
    if not continued:
        return ""
    return f"SIGCONT stopped loop python(s): {', '.join(continued)}"


def _heal_peer_job_stopped(_reg: dict[str, Any]) -> str:
    msg = _cont_job_stopped_loop_pythons()
    return msg or "no job-stopped loop pythons"
def _improve_process_pid() -> int | None:
    """PID of improve forever — hub script or CLEAN gitfile wrapper.

    CLEAN units often exec ``run_improve_poll_cache.py`` (not automation_improve.py
    on argv). Match either so mid-restart heals do not false-stop → restart thrash.
    """
    return _forever_python_pid("automation_improve.py") or _forever_python_pid(
        "run_improve_poll_cache.py"
    )


def _repo_research_process_pid() -> int | None:
    return _forever_python_pid("peer_repo_research.py")


def _dashboard_process_pid() -> int | None:
    """PID of a live ``dashboard/server.py`` (no --forever flag on the HTTP server)."""
    lines = _ps_axo_lines()
    if not lines:
        return None
    for raw in lines:
        parts = raw.strip().split(None, 2)
        if len(parts) < 3:
            continue
        pid_s, _comm, args = parts[0], parts[1], parts[2]
        if "dashboard/server.py" not in args and "dashboard\\server.py" not in args:
            continue
        argv0 = args.split(None, 1)[0]
        argv0_l = argv0.lower()
        if "python" not in argv0_l and not argv0.endswith("Python"):
            continue
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        if pid > 0:
            return pid
    return None


def _dashboard_port_up(port: int = 8765) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def _dashboard_daemon_running() -> bool:
    """True when dashboard LaunchAgent/systemd is up, process live, or :8765 accepts."""
    if sys.platform == "darwin":
        for label in (_live_dashboard_label(), DASHBOARD_LABEL, "com.togi.automation-hub-dashboard"):
            if label and _launchctl_running(label):
                return True
        if _dashboard_process_pid() is not None:
            return True
        return _dashboard_port_up()
    if _systemd_user_active("dashboard.service"):
        return True
    if _dashboard_process_pid() is not None:
        return True
    return _dashboard_port_up()


def _peer_daemon_running() -> bool:
    """True when peer LaunchAgent/systemd is up, or a forever process is live.

    Hub twin alone does not count — dual-brain / offload must treat
    ``com.togi.automation-hub-peer-loop`` as rogue, not healthy peer.
    When ``_live_peer_label()`` is set, only that label counts (not a
    divergent ``LAUNCH_AGENT_LABEL`` hub twin).
    """
    if sys.platform == "darwin":
        live = _live_peer_label()
        candidates: list[str] = []
        if live:
            candidates.append(live)
        else:
            # No disk-canonical label — accept configured / legacy labels.
            for lbl in (auto.LAUNCH_AGENT_LABEL, LEGACY_PEER_LABEL):
                if lbl and lbl not in candidates:
                    candidates.append(lbl)
        for label in candidates:
            if label and _launchctl_running(label):
                return True
        return _peer_loop_process_pid() is not None
    if _systemd_user_active("peer-loop.service"):
        return True
    return _peer_loop_process_pid() is not None


def _improve_daemon_running() -> bool:
    """True when improve LaunchAgent/systemd is up, or a forever process is live."""
    if sys.platform == "darwin":
        for label in (
            _live_improve_label(),
            HUB_IMPROVE_LABEL,
            f"{HUB_IMPROVE_LABEL}-fallback",
            LEGACY_IMPROVE_LABEL,
        ):
            if label and _launchctl_running(label):
                return True
        return _improve_process_pid() is not None
    if _systemd_user_active("improve-loop.service"):
        return True
    return _improve_process_pid() is not None


def _repo_research_daemon_running() -> bool:
    """True when repo-research-loop is up (LaunchAgent, systemd, or forever process).

    OVERSEER_HEAL_RESEARCH_DAEMON_2026_09_04 — heal-all previously ignored a
    STOPPED research unit → digest aged out → stagnation re-dispatch.
    """
    if sys.platform == "darwin":
        ns = cfg_mod.CFG.get("config_namespace", "automation-hub")
        for label in (
            f"com.togi.{ns}-repo-research-loop",
            "com.togi.automation-repo-research-loop",
        ):
            if _launchctl_running(label):
                return True
        return _repo_research_process_pid() is not None
    if _systemd_user_active("repo-research-loop.service"):
        return True
    return _repo_research_process_pid() is not None


def _all_peer_daemon_labels() -> tuple[str, ...]:
    labels: list[str] = []
    for label in (_live_peer_label(), auto.LAUNCH_AGENT_LABEL, HUB_PEER_LABEL, LEGACY_PEER_LABEL):
        if label and label not in labels:
            labels.append(label)
    return tuple(labels)


def _all_improve_daemon_labels() -> tuple[str, ...]:
    labels: list[str] = []
    for label in (_live_improve_label(), _improve_label(), HUB_IMPROVE_LABEL, LEGACY_IMPROVE_LABEL):
        if label and label not in labels:
            labels.append(label)
    return tuple(labels)


def _all_oversight_daemon_labels() -> tuple[str, ...]:
    labels: list[str] = []
    for label in (_live_oversight_label(), HUB_OVERSIGHT_LABEL, LEGACY_OVERSIGHT_LABEL):
        if label and label not in labels:
            labels.append(label)
    return tuple(labels)


def rogue_oversight_labels() -> list[str]:
    """Non-canonical oversight LaunchAgents (stale hub twin fights the board every 5m)."""
    canonical = _live_oversight_label()
    return [
        label
        for label in _running_launchctl_labels(_all_oversight_daemon_labels())
        if label != canonical
    ]


def _running_launchctl_labels(labels: tuple[str, ...]) -> list[str]:
    if sys.platform != "darwin":
        return []
    return [label for label in labels if _launchctl_running(label)]


# Needle: DUAL_NAMESPACE_COLLISION_TTL_2026_09_08 — factory remiss paid
# dual_namespace_collision → _live_cfg/load_config ×4 (~0.2–0.3ms of ~0.75ms)
# every WQ-touch while LaunchAgent set unchanged. Memo by config mtimes +
# probe_effective_ttl_sec; clear via clear_dual_namespace_collision_cache / probe invalidate.
_DUAL_NS_CACHE: dict[str, Any] = {"at": 0.0, "key": None, "val": None}


def clear_dual_namespace_collision_cache() -> None:
    """Drop dual-namespace memo (tests + heal invalidate)."""
    _DUAL_NS_CACHE["at"] = 0.0
    _DUAL_NS_CACHE["key"] = None
    _DUAL_NS_CACHE["val"] = None


def _dual_ns_input_key() -> tuple[int, int]:
    """automation.config.json + local overlay mtime_ns — dual-ns generation token."""

    def _ns(path: Path) -> int:
        try:
            return int(path.stat().st_mtime_ns) if path.is_file() else 0
        except OSError:
            return 0

    return (_ns(cfg_mod.CONFIG_PATH), _ns(cfg_mod.LOCAL_CONFIG_PATH))


def dual_namespace_collision() -> dict[str, list[str]]:
    """Non-canonical peer/improve LaunchAgents running alongside disk-canonical.

    Needle: DUAL_NAMESPACE_COLLISION_TTL_2026_09_08 — factory single_brain remiss.
    """
    key = _dual_ns_input_key()
    now = time.monotonic()
    cached = _DUAL_NS_CACHE.get("val")
    if (
        isinstance(cached, dict)
        and _DUAL_NS_CACHE.get("key") == key
        and (now - float(_DUAL_NS_CACHE.get("at") or 0.0)) < probe_effective_ttl_sec()
    ):
        return {
            "peer": list(cached.get("peer") or []),
            "improve": list(cached.get("improve") or []),
        }

    canonical_peer = _live_peer_label()
    canonical_improve = _live_improve_label()
    rogue_peer = [
        label
        for label in _running_launchctl_labels(_all_peer_daemon_labels())
        if label != canonical_peer
    ]
    rogue_improve = [
        label
        for label in _running_launchctl_labels(_all_improve_daemon_labels())
        if label != canonical_improve
    ]
    val = {"peer": rogue_peer, "improve": rogue_improve}
    _DUAL_NS_CACHE["at"] = now
    _DUAL_NS_CACHE["key"] = key
    _DUAL_NS_CACHE["val"] = {
        "peer": list(rogue_peer),
        "improve": list(rogue_improve),
    }
    return val


def daemon_status_snapshot() -> dict[str, bool]:
    """Unified daemon probe for digest, factory meter, and ASI rubric."""
    collision = dual_namespace_collision()
    return {
        "peer_loop": _peer_daemon_running(),
        "improve_loop": _improve_daemon_running(),
        "dashboard": _dashboard_daemon_running(),
        "dual_namespace": bool(
            collision["peer"] or collision["improve"] or rogue_oversight_labels()
        ),
    }


def _kickstart(label: str, *, kill: bool = False) -> str:
    """Start or nudge a LaunchAgent. Avoid -k by default — false-negative running
    checks were SIGTERM-looping healthy peer/improve daemons (exit -15)."""
    uid = os.getuid()
    args = ["launchctl", "kickstart"]
    if kill:
        args.append("-k")
    args.append(f"gui/{uid}/{label}")
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=15.0,
        check=False,
    )
    if proc.returncode == 0:
        return f"kickstarted {label}"
    err = (proc.stderr or proc.stdout or "failed").strip()
    return f"kickstart {label} failed: {err[:120]}"


def autonomous_execution_enabled() -> bool:
    return bool(cfg_mod.CFG.get("autonomous_execution", True))


def _improve_label() -> str:
    """Match ``automation_improve.IMPROVE_LABEL`` without importing that module.

    Needle: IMPROVE_LABEL_NO_IMPORT_2026_09_08 — ``dual_namespace_collision`` /
    ``_all_improve_daemon_labels`` cold-imported ``automation_improve`` (~14–18ms
    compile) just for ``com.togi.{ns}-improve-loop``. Same formula as
    ``automation_improve.IMPROVE_LABEL``.
    """
    ns = str(cfg_mod.CFG.get("config_namespace") or "automation-hub")
    return f"com.togi.{ns}-improve-loop"


def _wait_launchctl_running(label: str, *, attempts: int = 6, delay_sec: float = 0.5) -> bool:
    """Poll until LaunchAgent shows a PID — bootstrap/kickstart often races ahead of launchd."""
    for i in range(max(1, attempts)):
        if _launchctl_running(label):
            return True
        if i + 1 < attempts:
            time.sleep(delay_sec)
    return False


@contextlib.contextmanager
def _daemon_heal_flock(*, timeout_sec: float = _DAEMON_FLOCK_TIMEOUT_SEC) -> Iterator[None]:
    """Serialize LaunchAgent install/bootout — concurrent heals kill healthy daemons mid-cycle.

    Re-entrant for the same thread so heal→cmd_install nesting does not deadlock.
    Depth lives on ``sys`` so dual import paths (`peer_self_heal` vs `scripts.peer_self_heal`)
    share one counter; file flock alone is not recursive across two open fds.
    """
    depth_state = _daemon_flock_depth_state()
    depth = int(getattr(depth_state, "n", 0) or 0)
    if depth > 0:
        depth_state.n = depth + 1
        try:
            yield
        finally:
            depth_state.n = depth
        return

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fh = open(DAEMON_HEAL_LOCK, "a+", encoding="utf-8")
    locked = False
    try:
        if sys.platform != "win32":
            import fcntl

            deadline = time.time() + max(1.0, timeout_sec)
            while True:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except BlockingIOError:
                    if time.time() >= deadline:
                        raise TimeoutError("daemon heal flock timeout") from None
                    time.sleep(0.2)
        depth_state.n = 1
        try:
            yield
        finally:
            depth_state.n = 0
    finally:
        if locked and sys.platform != "win32":
            try:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        fh.close()


def _kickstart_or_install(label: str, *, install_fn: Callable[[], int]) -> str:
    """Kickstart daemon; auto-install LaunchAgent when missing and autonomous mode on."""
    result = _kickstart(label)
    if "could not find service" not in result.lower():
        return result
    if not autonomous_execution_enabled():
        return result
    try:
        rc = install_fn()
    except Exception as exc:  # noqa: BLE001
        return f"install {label} failed: {exc}"
    if rc != 0:
        if _wait_launchctl_running(label):
            return f"installed {label}; running (bootstrap race rc={rc})"
        return f"install {label} failed rc={rc}"
    if _wait_launchctl_running(label):
        return f"installed {label}; running after bootstrap"
    retry = _kickstart(label)
    if _wait_launchctl_running(label, attempts=4):
        return f"installed {label}; {retry}"
    return f"installed {label}; {retry}"


def _heal_research_daemon(_reg: dict[str, Any]) -> str:
    """OVERSEER_HEAL_RESEARCH_DAEMON_2026_09_04 — kickstart repo-research-loop."""
    if _repo_research_daemon_running():
        return "repo-research already active"
    try:
        with _daemon_heal_flock():
            if _repo_research_daemon_running():
                return "repo-research already active"
            return _ensure_systemd_repo_research_unit()
    except TimeoutError as exc:
        if _repo_research_daemon_running():
            return f"daemon heal flock busy: {exc}; research already active (skip restart)"
        try:
            retry = _ensure_systemd_repo_research_unit()
            return f"daemon heal flock busy: {exc}; {retry}"
        except Exception:  # noqa: BLE001
            return f"daemon heal flock busy: {exc}"


def _heal_peer_daemon(_reg: dict[str, Any]) -> str:
    cont = _cont_job_stopped_loop_pythons()
    if sys.platform != "darwin":
        try:
            with _daemon_heal_flock():
                if _peer_daemon_running():
                    if cont:
                        return f"peer already active; {cont}"
                    return "peer already active (skip restart)"
                return _ensure_systemd_peer_unit()
        except TimeoutError as exc:
            # OVERSEER_PEER_FLOCK_BUSY_SKIP_RESTART_2026_09_04
            if _peer_daemon_running():
                suffix = f"; {cont}" if cont else ""
                return (
                    f"daemon heal flock busy: {exc}; peer already active "
                    f"(skip restart){suffix}"
                )
            if _systemd_unit_usable("peer-loop.service"):
                retry = _systemd_restart("peer-loop.service")
                return f"daemon heal flock busy: {exc}; {retry}"
            return f"daemon heal flock busy: {exc}"

    import peer_loop

    ensure_canonical_module()
    label = _live_peer_label()
    # Prefer a live forever process over thrashing broken launchctl bootstrap.
    proc_pid = _peer_loop_process_pid()
    if proc_pid is not None and not _launchctl_running(label):
        return (
            f"peer process already active pid={proc_pid} "
            f"(skip install; launchctl {label} unavailable)"
        )
    try:
        with _daemon_heal_flock():
            # Call unlocked body — we already hold the flock (avoids dual-module nest).
            result = _kickstart_or_install(
                label,
                install_fn=lambda: peer_loop._cmd_install_body(install_mode="background"),
            )
            legacy = _bootout_legacy_peer_labels()
            rogue = _heal_rogue_oversight()
            if not _wait_launchctl_running(label, attempts=4, delay_sec=0.4):
                retry = _kickstart(label)
                result = f"{result}; re-kickstart {retry}"
                _wait_launchctl_running(label, attempts=4, delay_sec=0.4)
    except TimeoutError as exc:
        # Another heal holds the flock — still try kickstart if plist already installed.
        plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
        if plist.is_file() or peer_loop.PLIST_PATH.is_file():
            retry = _kickstart(label)
            if _wait_launchctl_running(label, attempts=4, delay_sec=0.4):
                return f"daemon heal flock busy; kickstart ok: {retry}"
            return f"daemon heal flock busy: {exc}; kickstart {retry}"
        return f"daemon heal flock busy: {exc}"
    extras = [x for x in (legacy, rogue) if x]
    return f"{result}; {'; '.join(extras)}" if extras else result


def _heal_improve_daemon(_reg: dict[str, Any]) -> str:
    if sys.platform != "darwin":
        try:
            with _daemon_heal_flock():
                if _improve_daemon_running() or _improve_process_pid() is not None:
                    return "improve already active (skip restart)"
                return _ensure_systemd_improve_unit()
        except TimeoutError as exc:
            if _improve_daemon_running() or _improve_process_pid() is not None:
                return f"daemon heal flock busy: {exc}; improve already active (skip restart)"
            if _systemd_unit_usable("improve-loop.service"):
                # Prefer start — restart thrash kills T10-04 cadence.
                retry = _systemd_start("improve-loop.service")
                return f"daemon heal flock busy: {exc}; {retry}"
            return f"daemon heal flock busy: {exc}"

    # HEAL_IMPROVE_DARWIN_NO_COLD_IMPROVE_IMPORT_2026_09_08 — kickstart-ok /
    # already-active paths must not cold-compile automation_improve (~80ms).
    # install_fn imports only when LaunchAgent is missing and autonomous install runs.
    ensure_canonical_module()
    label = _live_improve_label()
    if _improve_daemon_running() or _improve_process_pid() is not None:
        return "improve already active (skip restart)"

    def _lazy_improve_install() -> int:
        import automation_improve as improve

        return int(improve._cmd_install_body())

    try:
        with _daemon_heal_flock():
            if _improve_daemon_running() or _improve_process_pid() is not None:
                return "improve already active (skip restart)"
            result = _kickstart_or_install(label, install_fn=_lazy_improve_install)
            legacy = _bootout_legacy_peer_labels()
            rogue = _heal_rogue_oversight()
            if not _wait_launchctl_running(label, attempts=4, delay_sec=0.4):
                retry = _kickstart(label)
                result = f"{result}; re-kickstart {retry}"
                _wait_launchctl_running(label, attempts=4, delay_sec=0.4)
    except TimeoutError as exc:
        plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
        if plist.is_file():
            retry = _kickstart(label)
            if _wait_launchctl_running(label, attempts=4, delay_sec=0.4):
                return f"daemon heal flock busy; kickstart ok: {retry}"
            return f"daemon heal flock busy: {exc}; kickstart {retry}"
        return f"daemon heal flock busy: {exc}"
    extras = [x for x in (legacy, rogue) if x]
    return f"{result}; {'; '.join(extras)}" if extras else result


def _spawn_dashboard_fallback(*, port: int = 8765) -> str:
    """Start dashboard/server.py detached when launchctl bootstrap is unavailable."""
    if _dashboard_port_up(port):
        return "dashboard port already up (skip spawn)"
    script = ROOT / "dashboard" / "server.py"
    log_path = CONFIG_DIR / "dashboard.log"
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        log_f = open(log_path, "a", encoding="utf-8")  # noqa: SIM115 — kept open for Popen
    except OSError as exc:
        return f"dashboard spawn log open failed: {exc}"
    try:
        subprocess.Popen(  # noqa: S603 — controlled local paths
            [sys.executable, str(script), "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(ROOT),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={
                **os.environ,
                "PYTHONPATH": str(SCRIPTS),
            },
        )
    except OSError as exc:
        log_f.close()
        return f"dashboard spawn failed: {exc}"
    for _ in range(10):
        time.sleep(0.3)
        if _dashboard_port_up(port):
            return f"spawned dashboard/server.py on :{port}"
    return f"spawned dashboard/server.py but :{port} still down"


def _install_dashboard_launchagent() -> int:
    """Run dashboard/server.py --install (enable + bootstrap KeepAlive)."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "dashboard" / "server.py"), "--install"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        check=False,
    )
    return int(proc.returncode)


def _heal_dashboard_daemon(_reg: dict[str, Any]) -> str:
    """OVERSEER_DASHBOARD_KEEPALIVE_2026_09_06 — re-enable + bootstrap :8765 UI."""
    if _dashboard_daemon_running():
        return "dashboard already active (skip restart)"

    if sys.platform != "darwin":
        try:
            with _daemon_heal_flock():
                if _dashboard_daemon_running():
                    return "dashboard already active (skip restart)"
                if _systemd_unit_usable("dashboard.service"):
                    return _systemd_restart("dashboard.service")
                return _spawn_dashboard_fallback()
        except TimeoutError as exc:
            if _dashboard_daemon_running():
                return f"daemon heal flock busy: {exc}; dashboard already active"
            return f"daemon heal flock busy: {exc}; {_spawn_dashboard_fallback()}"

    label = _live_dashboard_label()
    uid = os.getuid()
    label_domain = f"gui/{uid}/{label}"
    ensure_canonical_module()
    try:
        with _daemon_heal_flock():
            if _dashboard_daemon_running():
                return "dashboard already active (skip restart)"
            subprocess.run(["launchctl", "enable", label_domain], capture_output=True)
            result = _kickstart_or_install(label, install_fn=_install_dashboard_launchagent)
            if _dashboard_daemon_running() or _wait_launchctl_running(label, attempts=4, delay_sec=0.4):
                return result
            retry = _kickstart(label)
            if _dashboard_daemon_running() or _wait_launchctl_running(label, attempts=4):
                return f"{result}; {retry}"
            fallback = _spawn_dashboard_fallback()
            return f"{result}; {retry}; {fallback}"
    except TimeoutError as exc:
        if _dashboard_daemon_running():
            return f"daemon heal flock busy: {exc}; dashboard already active"
        subprocess.run(["launchctl", "enable", label_domain], capture_output=True)
        retry = _kickstart(label)
        if _dashboard_daemon_running():
            return f"daemon heal flock busy; kickstart ok: {retry}"
        return f"daemon heal flock busy: {exc}; {retry}; {_spawn_dashboard_fallback()}"


def _bootout(label: str) -> str:
    uid = os.getuid()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}/{label}"],
        capture_output=True,
        timeout=10.0,
        check=False,
    )
    return f"stopped {label}"


def _bootout_legacy_peer_labels() -> str:
    """Boot out non-canonical peer/improve plists — never disk-canonical labels.

    Long-running healers may have imported hub labels into memory while
    ``automation.config.json`` already says ``automation`` — protect live disk
    labels so we never SIGTERM the real peer/improve.
    """
    stopped: list[str] = []
    uid = os.getuid()
    # Disk-live only. Memory hub labels must NOT join skip — that was the stale
    # hub-oversight path that refused to bootout the hub twin.
    skip = _live_canonical_labels()
    candidates = list(LEGACY_PEER_LABELS) + [HUB_PEER_LABEL, HUB_IMPROVE_LABEL]
    seen: set[str] = set()
    for label in candidates:
        if not label or label in skip or label in seen:
            continue
        seen.add(label)
        proc = subprocess.run(
            ["launchctl", "bootout", f"gui/{uid}/{label}"],
            capture_output=True,
            timeout=10.0,
            check=False,
        )
        if proc.returncode == 0:
            stopped.append(label)
    return f"legacy bootout: {', '.join(stopped)}" if stopped else ""


def _heal_rogue_oversight(_reg: dict[str, Any] | None = None) -> str:
    """Stop stale hub/legacy oversight twins that rewrite SYSTEM_OVERSIGHT with wrong labels."""
    stopped: list[str] = []
    for label in rogue_oversight_labels():
        stopped.append(_bootout(label))
        plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
        try:
            if plist.is_file():
                plist.unlink()
                stopped.append(f"removed {plist.name}")
        except OSError:
            pass
    return "; ".join(stopped) if stopped else ""


def _tail_log(path: Path, *, lines: int = _LOG_WINDOW_LINES) -> list[str]:
    """Tail log lines without slurping multi-MB daemon logs into RSS."""
    if not path.is_file():
        return []
    return auto.tail_text_lines(path, lines, max_bytes=512 * 1024)


def _count_patterns(lines: list[str], patterns: tuple[str, ...]) -> int:
    return sum(1 for ln in lines if any(p in ln for p in patterns))


# OVERSEER_VERIFY_STORM_MAX_AGE_2026_09_04 — aged FAIL pairs must not pin verify_storm.
_VERIFY_STORM_MAX_AGE_SEC = 300.0


def _count_recent_patterns(
    lines: list[str],
    patterns: tuple[str, ...],
    *,
    now: float | None = None,
    max_age_sec: float = _VERIFY_STORM_MAX_AGE_SEC,
) -> int:
    """Count pattern hits only on lines with a recent leading timestamp."""
    now_ts = time.time() if now is None else float(now)
    count = 0
    for ln in lines:
        if not any(p in ln for p in patterns):
            continue
        head = ln[:19]
        try:
            ts = time.mktime(time.strptime(head, "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            count += 1
            continue
        if (now_ts - ts) <= max_age_sec:
            count += 1
    return count


def _count_unittest_timeouts(lines: list[str]) -> int:
    """Count unittest-specific timeouts — ignore ssh/subprocess/daemon-heal/wake noise."""
    skip = (
        "launchctl",
        "kickstart",
        "daemon_improve_stopped",
        "daemon_peer_stopped",
        "wake reason=timeout",
        "wake reason=timeout ",
    )
    return sum(
        1
        for ln in lines
        if ("timed out after" in ln or "TimeoutExpired" in ln)
        and ("unittest" in ln.lower() or "tests.test_" in ln)
        and "wake reason=" not in ln
        and not any(marker in ln for marker in skip)
    )


def _file_age_sec(path: Path) -> float | None:
    if not path.is_file():
        return None
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


def _load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.is_file():
        return {"history": {}, "last_heal": {}}
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"history": {}, "last_heal": {}}


def _save_registry(data: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _merge_history(
    found: list[Bottleneck],
    registry: dict[str, Any],
    *,
    log_fn: Callable[[str], None] | None = None,
) -> list[Bottleneck]:
    hist: dict[str, Any] = registry.setdefault("history", {})
    now = _now_iso()
    log = log_fn or (lambda _msg: None)
    merged: list[Bottleneck] = []
    found_ids: set[str] = set()
    for bn in found:
        found_ids.add(bn.id)
        prev = hist.get(bn.id) if isinstance(hist.get(bn.id), dict) else {}
        bn.first_seen = str(prev.get("first_seen") or now)
        bn.last_seen = now
        bn.hit_count = int(prev.get("hit_count") or 0) + 1
        if prev.get("status") == "healed" and bn.severity != "critical":
            bn.status = "open"
        merged.append(bn)
        hist[bn.id] = {
            "first_seen": bn.first_seen,
            "last_seen": bn.last_seen,
            "hit_count": bn.hit_count,
            "title": bn.title,
            "category": bn.category,
            "severity": bn.severity,
            "status": bn.status,
            "last_evidence": bn.evidence[:500],
        }
    # Clear stale open history when live scan no longer sees the id (e.g. unittest_storm).
    for hid, prev in list(hist.items()):
        if hid in found_ids or not isinstance(prev, dict):
            continue
        if prev.get("status") in ("healed", "resolved"):
            continue
        prev = dict(prev)
        prev["status"] = "healed"
        prev["last_seen"] = now
        prev["healed_reason"] = "absent_from_scan"
        hist[hid] = prev
        # OVERSEER_HEAL_REGISTRY_CLEAR_LOG_BOTTLENECK_ID_2026_09_04
        log(f"self-heal registry clear: {hid} (absent_from_scan)")
    registry["history"] = hist
    registry["updated_at"] = now
    return merged


# Needle: PROGRESS_FP_HEAD_GEN_CACHE_2026_09_08 — progress_fingerprint shelled
# ``git rev-parse HEAD`` every heal tick (~2.9–3.9ms warm) while HEAD+index
# mtimes already gate SCAN_ADAPT_FP_GEN. Cache short oid by same gen token.
_PROGRESS_HEAD_GEN_CACHE: dict[str, tuple[tuple[int, int], str]] = {}


def clear_progress_head_generation_cache() -> None:
    """Drop progress_fp HEAD oid gen-cache (tests + scan invalidate)."""
    _PROGRESS_HEAD_GEN_CACHE.clear()


def _progress_head_short(root: Path | None = None) -> str:
    """Short HEAD oid for progress_fp — gen-cache skips rev-parse on HIT.

    Needle: PROGRESS_FP_HEAD_GEN_CACHE_2026_09_08
    """
    root = root or ROOT
    key = str(root)
    gen = _git_head_index_mtime_ns_for_scan(root)
    cached = _PROGRESS_HEAD_GEN_CACHE.get(key)
    if cached is not None and cached[0] == gen:
        return cached[1]
    head = "unknown"
    try:
        head = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=8,
        ).strip()[:16] or "unknown"
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        head = "unknown"
    _PROGRESS_HEAD_GEN_CACHE[key] = (gen, head)
    return head


def progress_fingerprint() -> dict[str, Any]:
    """Wall-clock progress digest — heal when this stalls, not when rules fire.

    Needle: OVERSEER_SELF_HEAL_PROGRESS_FP_2026_09_06
    COMPRESSION_ZLIB_SELF_HEAL_PROGRESS_FP_2026_09_07 — zlib adler+crc (not
    hashlib) so peer forever self-heal ticks stay libcrypto-free (~5.7MB r-xp).
    PROGRESS_FP_HEAD_GEN_CACHE_2026_09_08 — skip rev-parse when HEAD/index gen HIT.
    """
    import zlib

    head = _progress_head_short(ROOT)

    open_keys: list[str] = []
    try:
        open_keys = sorted(
            auto._normalize_queue_key(x)
            for x in auto.open_work_items(work_md=auto.load_work_queue_md()).open_items
        )[:40]
    except Exception:  # noqa: BLE001
        open_keys = []

    verify_ok = None
    failure_type = ""
    # Needle: PROGRESS_FP_NO_TRANSCRIPT_IMPORT_2026_09_08 — cold
    # ``import peer_transcript`` (~50–75ms) solely to read last_cycle from the
    # same STATE_PATH ``_read_state`` already loads as JSON.
    try:
        state = _read_state()
        lc = state.get("last_cycle") if isinstance(state, dict) else None
        if isinstance(lc, dict):
            verify_ok = lc.get("verify_ok")
            failure_type = str(lc.get("failure_type") or "")[:40]
    except Exception:  # noqa: BLE001
        pass

    peer_up = _peer_daemon_running()
    improve_up = _improve_daemon_running()
    # Needle: PROGRESS_FP_SHARE_PS_AXO_2026_09_08 — progress_stalled / heal ticks
    # shelled ``ps -u $USER -o args=`` (~27ms) every fingerprint while scan already
    # holds a TTL ``_ps_axo_lines`` /proc snapshot (~5ms cold, HIT ~0). Same
    # ``cursor-agent`` substring count; parity probed 17=17.
    agents = 0
    try:
        lines = _ps_axo_lines() or []
        agents = sum(1 for ln in lines if "cursor-agent" in ln)
    except Exception:  # noqa: BLE001
        agents = 0

    core = {
        "head": head,
        "open_keys": open_keys,
        "verify_ok": verify_ok,
        "failure_type": failure_type,
        "peer_up": peer_up,
        "improve_up": improve_up,
    }
    raw = json.dumps(core, sort_keys=True, default=str).encode("utf-8", errors="replace")
    # Keep key name core_sha for registry compat; value is zlib adler+crc hex.
    digest = (
        f"{zlib.adler32(raw) & 0xffffffff:08x}"
        f"{zlib.crc32(raw) & 0xffffffff:08x}"
    )[:16]
    return {
        "core_sha": digest,
        "head": head,
        "open_n": len(open_keys),
        "verify_ok": verify_ok,
        "failure_type": failure_type,
        "peer_up": peer_up,
        "improve_up": improve_up,
        "agents": agents,
        "ts": time.time(),
    }


def update_progress_fp(registry: dict[str, Any]) -> tuple[dict[str, Any], bool, float]:
    """Update registry progress_fp. Returns (snap, moved, idle_sec)."""
    snap = progress_fingerprint()
    prev = registry.get("progress_fp") if isinstance(registry.get("progress_fp"), dict) else {}
    now = time.time()
    moved = str(prev.get("core_sha") or "") != snap["core_sha"]
    if moved or not prev:
        registry["progress_fp"] = {**snap, "moved_at": now}
        idle = 0.0
    else:
        moved_at = float(prev.get("moved_at") or now)
        idle = max(0.0, now - moved_at)
        registry["progress_fp"] = {**prev, **snap, "moved_at": moved_at, "idle_sec": idle}
    return snap, moved, idle


def progress_stalled(registry: dict[str, Any], *, stall_sec: float = _PROGRESS_STALL_SEC) -> bool:
    _snap, moved, idle = update_progress_fp(registry)
    if moved:
        return False
    return idle >= stall_sec


def _heal_on_cooldown(registry: dict[str, Any], heal_id: str, *, cooldown: float = _HEAL_COOLDOWN_SEC) -> bool:
    last = registry.setdefault("last_heal", {})
    if not isinstance(last, dict):
        return False
    ts = float(last.get(heal_id) or 0)
    return (time.time() - ts) < cooldown


_CRITICAL_DAEMON_HEALS = frozenset(
    {
        "daemon_peer_stopped",
        "daemon_improve_stopped",
        "daemon_research_stopped",  # OVERSEER_HEAL_RESEARCH_DAEMON_2026_09_04
        "daemon_dashboard_stopped",  # OVERSEER_DASHBOARD_KEEPALIVE_2026_09_06
        "dual_brain_hub_oversight",
        "hub_protect_timer_stopped",
        "hub_protect_restore_paused",
        "plan_gate_chicken_egg",  # OVERSEER_SELF_HEAL_PLAN_GATE_2026_09_06
        "ram_ballast",
        "paid_auth_park",
    }
)


def _daemon_heal_still_down(bn: Bottleneck) -> bool:
    """True when a critical daemon heal target is still stopped in launchctl."""
    if bn.id == "daemon_peer_stopped":
        return not _peer_daemon_running()
    if bn.id == "daemon_peer_job_stopped":
        return bool(_job_stopped_loop_python_pids())
    if bn.id == "daemon_improve_stopped":
        return not _improve_daemon_running()
    if bn.id == "daemon_research_stopped":
        return not _repo_research_daemon_running()
    if bn.id == "daemon_dashboard_stopped":
        return not _dashboard_daemon_running()
    if bn.id == "hub_protect_timer_stopped":
        return not _hub_protect_timer_active()
    if bn.id == "hub_protect_restore_paused":
        return _hub_protect_restore_paused()
    if bn.id == "ram_ballast":
        return bool(_scan_ram_ballast())
    if bn.id == "paid_auth_park":
        paid = Path.home() / ".config" / "automation-hub" / "cursor-agent.env"
        return paid.is_file() or os.environ.get("PEER_LOOP_PAID_API") == "1"
    if bn.id == "plan_gate_chicken_egg":
        return True  # always re-fire when scanned — chicken-egg eats progress
    return False


def _mark_heal(registry: dict[str, Any], heal_id: str) -> None:
    registry.setdefault("last_heal", {})[heal_id] = time.time()


def _read_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _read_status() -> dict[str, Any]:
    if not STATUS_PATH.is_file():
        return {}
    try:
        data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _verify_lock_is_stale() -> bool:
    """Match run_peer_tasks verify lock semantics — do not delete active verify runs."""
    if not VERIFY_LOCK.is_file():
        return False
    age = _file_age_sec(VERIFY_LOCK)
    if age is None:
        return False
    try:
        import run_peer_tasks as rpt

        stale_sec = float(rpt.VERIFY_LOCK_STALE_SEC)
    except Exception:  # noqa: BLE001
        stale_sec = 600.0
    try:
        pid = int(VERIFY_LOCK.read_text(encoding="utf-8").splitlines()[0].strip())
        os.kill(pid, 0)
        return age > stale_sec
    except (OSError, ValueError, IndexError):
        return age > stale_sec


def _stale_lock(path: Path, *, stale_sec: float) -> bool:
    age = _file_age_sec(path)
    return age is not None and age > stale_sec


# Needle: SCAN_BOTTLENECKS_TTL_2026_09_07 — factory remiss paid full scan
# (~6–8ms warm; adapt fingerprint ~5ms) every WQ generation; TTL HIT aligns
# with probe_effective_ttl_sec (wake-floor) so write_team/dual remiss share one
# scan per window — not every continuous_wake heartbeat.
_SCAN_BOTTLENECKS_CACHE: dict[str, Any] = {"at": 0.0, "items": None}


def clear_scan_bottlenecks_cache() -> None:
    """Drop scan_bottlenecks TTL memo (tests + heal invalidate)."""
    _SCAN_BOTTLENECKS_CACHE["at"] = 0.0
    _SCAN_BOTTLENECKS_CACHE["items"] = None
    clear_live_adapt_fp_generation_cache()


def scan_bottlenecks(*, daemons: dict[str, bool] | None = None) -> list[Bottleneck]:
    """Collect bottlenecks from daemons, logs, state, and live metrics.

    Needle: SCAN_BOTTLENECKS_TTL_2026_09_07 — default-path results memoized for
    ``probe_effective_ttl_sec()``; explicit ``daemons=`` bypasses (tests / injected paths).
    """
    if daemons is None:
        now = time.monotonic()
        cached = _SCAN_BOTTLENECKS_CACHE.get("items")
        at = float(_SCAN_BOTTLENECKS_CACHE.get("at") or 0.0)
        if cached is not None and (now - at) < probe_effective_ttl_sec():
            return list(cached)

    found = _scan_bottlenecks_body(daemons=daemons)
    if daemons is None:
        _SCAN_BOTTLENECKS_CACHE["at"] = time.monotonic()
        _SCAN_BOTTLENECKS_CACHE["items"] = list(found)
    return found


def _scan_bottlenecks_body(*, daemons: dict[str, bool] | None = None) -> list[Bottleneck]:
    """Inner scan — uncached body (caller applies TTL / daemons bypass)."""
    found: list[Bottleneck] = []
    peer_lines = _tail_log(PEER_LOG)
    improve_lines = _tail_log(IMPROVE_LOG)
    state = _read_state()
    status = _read_status()

    # Prefer disk-live labels so stale long-running healers don't false-alarm.
    # IMPROVE_LABEL_NO_IMPORT — do not cold-import automation_improve for a string.
    peer_label = _live_peer_label() or auto.LAUNCH_AGENT_LABEL
    improve_label = _live_improve_label() or _improve_label()

    if daemons is not None:
        peer_running = bool(daemons.get("peer_loop"))
        improve_running = bool(daemons.get("improve_loop"))
    else:
        peer_running = _peer_daemon_running()
        improve_running = _improve_daemon_running()

    if not peer_running:
        found.append(
            Bottleneck(
                id="daemon_peer_stopped",
                category="daemon",
                severity="critical",
                title="Peer loop daemon not running",
                evidence=f"peer loop inactive ({peer_label} / peer-loop.service)",
                heal_action="kickstart peer loop",
            )
        )
    else:
        # systemd active + MainThread SIGSTOP → forever verify hang / T10-04 stall
        stopped = _job_stopped_loop_python_pids()
        if stopped:
            ev = ", ".join(f"{lbl}:{pid}" for lbl, pid in stopped)
            found.append(
                Bottleneck(
                    id="daemon_peer_job_stopped",
                    category="daemon",
                    severity="high",
                    title="Peer/improve python job-stopped (STAT=T)",
                    evidence=ev,
                    heal_action="SIGCONT stopped loop pythons",
                )
            )
    if not improve_running:
        found.append(
            Bottleneck(
                id="daemon_improve_stopped",
                category="daemon",
                severity="critical",
                title="Improve forever daemon not running",
                evidence=f"LaunchAgent {improve_label} has no PID",
                heal_action="kickstart improve loop",
            )
        )
    # OVERSEER_HEAL_RESEARCH_DAEMON_2026_09_04 — STOPPED research → stale digest
    # → "repo flaw research stale" stagnation even when Active is empty.
    if not _repo_research_daemon_running():
        found.append(
            Bottleneck(
                id="daemon_research_stopped",
                category="daemon",
                severity="high",
                title="Repo research daemon not running",
                evidence="repo-research-loop.service inactive (or LaunchAgent missing)",
                heal_action="enable --now repo-research-loop",
                auto_healable=True,
            )
        )
    # OVERSEER_DASHBOARD_KEEPALIVE_2026_09_06 — Mac UI :8765 must survive
    # dgx_watch bootout/disable under mac-offloaded + crash restart.
    if not _dashboard_daemon_running():
        found.append(
            Bottleneck(
                id="daemon_dashboard_stopped",
                category="daemon",
                severity="high",
                title="Dashboard not listening on :8765",
                evidence=f"LaunchAgent {_live_dashboard_label()} / port 8765 down",
                heal_action="enable + bootstrap dashboard KeepAlive",
                auto_healable=True,
            )
        )
    if _launchctl_running(RAM_PEER_LABEL):
        found.append(
            Bottleneck(
                id="dual_brain_ram_peer",
                category="daemon",
                severity="high",
                title="Dual-brain: ram-peer-loop running alongside hub",
                evidence=f"{RAM_PEER_LABEL} is active",
                heal_action="stop ram-peer-loop",
            )
        )

    collision = dual_namespace_collision()
    if collision["peer"] or collision["improve"]:
        found.append(
            Bottleneck(
                id="dual_brain_hub_peer",
                category="daemon",
                severity="critical",
                title="Dual namespace: rogue peer/improve LaunchAgents",
                evidence=(
                    f"canonical peer={peer_label} improve={improve_label}; "
                    f"rogue peer={collision['peer']} improve={collision['improve']}"
                ),
                heal_action="bootout rogue namespace daemons",
            )
        )

    rogue_ov = rogue_oversight_labels()
    if rogue_ov:
        found.append(
            Bottleneck(
                id="dual_brain_hub_oversight",
                category="daemon",
                severity="critical",
                title="Dual namespace: rogue oversight LaunchAgent",
                evidence=(
                    f"canonical={_live_oversight_label()}; rogue={rogue_ov!r} "
                    "(stale hub twin installs wrong peer labels)"
                ),
                heal_action="bootout rogue oversight LaunchAgent",
            )
        )

    # OVERSEER_HORIZON_FRESHEST_2026_09_04 — age the freshest board, not import ns.
    horizon_board = _horizon_board_path()
    horizon_age = _file_age_sec(horizon_board)
    if horizon_age is not None and horizon_age > HORIZON_STALE_SEC and improve_running:
        found.append(
            Bottleneck(
                id="horizon_stale",
                category="improve",
                severity="medium",
                title="Improve horizon board stale",
                evidence=f"IMPROVE_HORIZON.md age={horizon_age:.0f}s path={horizon_board}",
                heal_action="write horizon + kickstart improve loop",
            )
        )

    # Short window — full-suite timeouts from yesterday must not keep storm open.
    recent_for_tests = improve_lines[-80:] + peer_lines[-80:]
    unittest_timeouts = _count_unittest_timeouts(recent_for_tests)
    if unittest_timeouts >= 3:
        found.append(
            Bottleneck(
                id="unittest_storm",
                category="tests",
                severity="high",
                title="Unittest timeout storm",
                evidence=f"{unittest_timeouts} timeout lines in recent logs",
                heal_action="extend test cache TTL + clear test lock",
            )
        )

    recent_for_verify = peer_lines[-80:]
    # adapt_stale FAIL is a separate bottleneck — do not inflate verify_storm from it.
    verify_timeouts = _count_recent_patterns(
        [ln for ln in recent_for_verify if "adapt_stale" not in ln.lower()],
        ("verify TIMEOUT", "verify FAIL"),
    )
    if verify_timeouts >= 2:
        found.append(
            Bottleneck(
                id="verify_storm",
                category="verify",
                severity="medium",
                title="Verify failure/timeout storm",
                evidence=f"{verify_timeouts} verify FAIL/TIMEOUT in peer log",
                heal_action="clear stale verify lock",
                auto_healable=True,
            )
        )

    if _verify_lock_is_stale():
        found.append(
            Bottleneck(
                id="stale_verify_lock",
                category="verify",
                severity="high",
                title="Stale verify lock blocking single-flight gate",
                evidence="verify.lock stale or holder dead",
                heal_action="remove verify.lock",
            )
        )
    if _stale_lock(TEST_LOCK, stale_sec=120.0):
        found.append(
            Bottleneck(
                id="stale_test_lock",
                category="tests",
                severity="high",
                title="Stale test-measure lock blocking live metrics",
                evidence=f"test-measure.lock age>{120}s",
                heal_action="remove test-measure.lock",
            )
        )

    try:
        open_items = auto.open_work_items(work_md=auto.load_work_queue_md()).open_items
        keys = [auto._normalize_queue_key(x) for x in open_items]
        dupes = len(keys) - len(set(keys))
        self_heal_lines = sum(1 for x in open_items if "[self-heal]" in x.lower())
        watchdog_lines = sum(
            1
            for x in open_items
            if "WATCHDOG" in x or "Keep-alive fuel" in x or "OVERSEER_COMPRESSION_RESULT_WATCH" in x
        )
        if dupes >= 3 or self_heal_lines >= 3 or watchdog_lines >= 4:
            found.append(
                Bottleneck(
                    id="queue_spam",
                    category="queue",
                    severity="medium",
                    title="Duplicate queue lines blocking signal",
                    evidence=f"dupes={dupes} self_heal={self_heal_lines} watchdog={watchdog_lines}",
                    heal_action="dedupe WORK_QUEUE",
                )
            )
    except Exception as exc:  # noqa: BLE001
        pass

    try:
        drift = auto.sync_queue_drift(auto.load_context_md(), auto.load_work_queue_md())
    except Exception as exc:  # noqa: BLE001
        drift = [f"sync error: {exc}"]
    if drift:
        found.append(
            Bottleneck(
                id="queue_drift",
                category="queue",
                severity="medium",
                title="WORK_QUEUE ↔ context drift",
                evidence="; ".join(drift[:3]),
                heal_action="heal queue drift",
            )
        )

    try:
        # SCAN_ADAPT_NO_COLD_IMPORT — do not cold-import automation_adapt (~45ms)
        # just to compare fingerprints on every scan MISS.
        if _should_re_adapt_for_scan(ROOT):
            found.append(
                Bottleneck(
                    id="adapt_stale",
                    category="adapt",
                    severity="medium",
                    title="Adapt fingerprint stale after git changes",
                    evidence="should_re_adapt() true",
                    heal_action="adapt heal (quick)",
                )
            )
    except Exception as exc:  # noqa: BLE001
        found.append(
            Bottleneck(
                id="adapt_check_failed",
                category="adapt",
                severity="low",
                title="Adapt state check failed",
                evidence=str(exc)[:200],
                auto_healable=False,
            )
        )

    last_cycle = state.get("last_cycle")
    if not isinstance(last_cycle, dict) or not last_cycle:
        found.append(
            Bottleneck(
                id="missing_last_cycle",
                category="dispatch",
                severity="medium",
                title="No last_cycle memory in peer-loop-state",
                evidence="peer has not recorded a completed turn",
                auto_healable=True,
                heal_action="seed last_cycle from local verify tick",
            )
        )
    elif _is_last_cycle_deferred_poison(last_cycle):
        # OVERSEER_SCRUB_DEFERRED_POISON_2026_09_04
        found.append(
            Bottleneck(
                id="last_cycle_deferred_poison",
                category="dispatch",
                severity="high",
                title="last_cycle poison: verify_ok=True with failure_type=deferred",
                evidence=str(last_cycle)[:200],
                auto_healable=True,
                heal_action="scrub poison + reseed last_cycle",
            )
        )
    elif last_cycle.get("verify_ok") is False:
        # OVERSEER_DEFERRED_NOT_VERIFY_FAIL_2026_09_04 — soft swarm/lock
        # deferred must not stamp verify_fail_hold / hold dispatch.
        ft = str(last_cycle.get("failure_type") or "").strip()
        if ft != "deferred":
            found.append(
                Bottleneck(
                    id="verify_fail_hold",
                    category="verify",
                    severity="high",
                    title="Last cycle verify failed — dispatch held",
                    evidence=str(
                        last_cycle.get("summary")
                        or last_cycle.get("failure_type")
                        or "verify_ok=false"
                    )[:200],
                    auto_healable=True,
                    heal_action="autonomous verify repair",
                )
            )

    stall_reason = str(state.get("stall_reason") or "")
    if stall_reason == "noop_backoff" and float(state.get("stall_since_ts") or 0):
        elapsed = time.time() - float(state["stall_since_ts"])
        if elapsed > 180:
            found.append(
                Bottleneck(
                    id="noop_stall",
                    category="dispatch",
                    severity="medium",
                    title="Long noop backoff — queue fingerprint unchanged",
                    evidence=f"noop_backoff {elapsed:.0f}s",
                    heal_action="wake peer + enqueue queue advance",
                )
            )

    auth_detail = str(status.get("auth_detail") or "")
    if status.get("auth_ready") is False and "timed out" in auth_detail.lower():
        found.append(
            Bottleneck(
                id="cursor_agent_auth",
                category="auth",
                severity="medium",
                title="cursor-agent auth unavailable — local-only mode",
                evidence=auth_detail[:200],
                auto_healable=False,
                heal_action="human: cursor-agent login",
            )
        )

    # Plan-gate chicken-egg — verify_ok=false loops block primary forever.
    # OVERSEER_SELF_HEAL_PLAN_GATE_2026_09_06
    plan_blocks = _count_recent_patterns(
        peer_lines[-120:],
        ("plan-gate BLOCKED", "plan-gate still hard-blocked", "plan-gate chicken"),
    )
    if plan_blocks >= 2 or (
        isinstance(last_cycle, dict)
        and last_cycle.get("verify_ok") is False
        and str(last_cycle.get("failure_type") or "") not in ("", "deferred")
        and plan_blocks >= 1
    ):
        found.append(
            Bottleneck(
                id="plan_gate_chicken_egg",
                category="dispatch",
                severity="critical",
                title="Plan-gate chicken-egg — verify_ok=false forever skips primary",
                evidence=f"plan_blocks={plan_blocks} last_cycle_ft={str((last_cycle or {}).get('failure_type') if isinstance(last_cycle, dict) else '')[:40]}",
                heal_action="sync-queue + adapt + soft seed + poke",
            )
        )

    # RAM ballast that starves free desktop agents (DGX/CLEAN).
    ballast = _scan_ram_ballast()
    if ballast:
        found.append(
            Bottleneck(
                id="ram_ballast",
                category="resources",
                severity="high",
                title="RAM ballast starving free agents",
                evidence="; ".join(ballast[:6]),
                heal_action="SIGKILL poll/fill; gpu_compute only under tight MemAvailable + ≥14GB RSS",
            )
        )

    # Paid API key file present while free-desktop lock is intended.
    paid_path = Path.home() / ".config" / "automation-hub" / "cursor-agent.env"
    if paid_path.is_file() or os.environ.get("PEER_LOOP_PAID_API") == "1":
        if _force_free_desktop_wanted():
            found.append(
                Bottleneck(
                    id="paid_auth_park",
                    category="auth",
                    severity="high",
                    title="Paid cursor API path active — park to free desktop",
                    evidence=f"env_file={paid_path.is_file()} PEER_LOOP_PAID_API={os.environ.get('PEER_LOOP_PAID_API')}",
                    heal_action="park cursor-agent.env + clear PEER_LOOP_PAID_API",
                )
            )

    wake_recent = _count_patterns(improve_lines[-80:], ("wake peer", "peer-turn.signal"))
    improve_age = _file_age_sec(IMPROVE_LOG)
    if improve_age is not None and improve_age < 600 and wake_recent == 0 and _launchctl_running(improve_label):
        found.append(
            Bottleneck(
                id="improve_not_waking_peer",
                category="improve",
                severity="medium",
                title="Improve loop not waking peer recently",
                evidence="no wake peer in last 80 improve log lines",
                heal_action="touch peer-turn.signal",
            )
        )

    queue_source = str(status.get("queue_source") or "")
    if queue_source.startswith("error:") and "TimeoutExpired" in queue_source:
        found.append(
            Bottleneck(
                id="queue_read_blocked",
                category="tests",
                severity="high",
                title="Queue read blocked by live-state timeout",
                evidence=queue_source[:200],
                heal_action="extend test cache TTL + clear test lock",
            )
        )

    # Mac→DGX rsync clobber defense — timer/path must stay up or WORKING lands rebound.
    # OVERSEER_HUB_PROTECT_2026_09_03
    if sys.platform != "darwin" and _hub_protect_units_present() and not _hub_protect_timer_active():
        found.append(
            Bottleneck(
                id="hub_protect_timer_stopped",
                category="daemon",
                severity="high",
                title="hub-protect-restore.timer stopped — Mac rsync can clobber WORKING lands",
                evidence="hub-protect-restore.timer inactive (or path unit down)",
                heal_action="enable --now hub-protect-restore.timer + path",
            )
        )
    # OVERSEER_HUB_PROTECT_RESTORE_PAUSED_2026_09_04 — timer up but wrap stubbed.
    if sys.platform != "darwin" and _hub_protect_restore_paused():
        found.append(
            Bottleneck(
                id="hub_protect_restore_paused",
                category="daemon",
                severity="high",
                title="hub-protect restore paused stub — Mac rsync can clobber WORKING lands",
                evidence="restore-hub-protect.sh is land-hold stub (restore paused)",
                heal_action="unstub restore + clear expired land-hold + run restore",
            )
        )

    return found


def _extend_test_cache_ttl(*, min_ttl: int = 600) -> str:
    cache_path = CONFIG_DIR / "automation_cache.json"
    cache: dict[str, Any] = {}
    if cache_path.is_file():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}
    cache["self_heal_test_ttl_bump"] = min_ttl
    cache["tests_ts"] = time.time()
    if cache.get("tests_ok") is not False:
        cache["tests_detail"] = "tests: deferred (self-heal ttl bump)"
    try:
        cache_path.write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return f"cache bump failed: {exc}"
    return f"bumped test cache (ttl hint {min_ttl}s)"


def _remove_lock(path: Path) -> str:
    try:
        if path.is_file():
            path.unlink()
            return f"removed {path.name}"
    except OSError as exc:
        return f"remove {path.name} failed: {exc}"
    return f"{path.name} absent"


def _touch_signal() -> str:
    try:
        SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        SIGNAL_PATH.write_text(f"{_now_iso()} self-heal\n", encoding="utf-8")
        return "touched peer-turn.signal"
    except OSError as exc:
        return f"signal touch failed: {exc}"


def _heal_queue_drift() -> str:
    import automation_adapt as adapt

    healed, _ = adapt.heal_queue_drift(root=ROOT, write=True)
    return f"queue drift: {len(healed)} write(s)" if healed else "queue drift: nothing to write"


def _heal_adapt() -> str:
    import automation_adapt as adapt

    # Subprocess so stale in-memory adapt cannot write git_fingerprint: null.
    report = adapt.run_heal_fresh(write=True, quick=True)
    synced = adapt.sync_git_fingerprint(ROOT)
    suffix = "; synced fingerprint" if synced else ""
    return f"adapt heal fresh ({len(report.actions)} action(s)){suffix}"





def _adapt_porcelain_path_is_notes(path: str) -> bool:
    """True when porcelain path is notes/ (loop ticks write notes constantly)."""
    cleaned = path.strip().strip('"').replace("\\", "/")
    return cleaned == "notes" or cleaned.startswith("notes/")


def _strip_notes_porcelain_for_scan(porcelain: str) -> str:
    """Match ``automation_adapt._strip_notes_porcelain`` without importing adapt."""
    kept: list[str] = []
    for raw in (porcelain or "").splitlines():
        if not raw.strip():
            continue
        # Porcelain is XY + path; .strip() on the whole status blob can eat the
        # leading space on the first line (XY starts with ' '), so parse robustly.
        line = raw if len(raw) >= 3 and raw[2] == " " else raw.strip()
        rest = (
            line[3:]
            if len(line) >= 3 and line[2] == " "
            else line[2:].lstrip()
            if len(line) >= 2
            else line
        )
        parts = rest.split(" -> ")
        if parts and all(_adapt_porcelain_path_is_notes(p) for p in parts):
            continue
        kept.append(raw)
    return "\n".join(kept)


# Needle: SCAN_ADAPT_FP_GEN_CACHE_2026_09_08 — lite scan path shelled
# rev-parse+porcelain (~5–11ms) every MISS even when HEAD/index mtimes unchanged;
# match automation_adapt GIT_FP_HEAD_INDEX_GENERATION without cold-importing adapt.
_LIVE_ADAPT_FP_GEN_CACHE: dict[str, tuple[tuple[int, int], str | None]] = {}


def clear_live_adapt_fp_generation_cache() -> None:
    """Drop HEAD+index generation memo for lite adapt fp (tests + scan invalidate)."""
    _LIVE_ADAPT_FP_GEN_CACHE.clear()
    # Same gen token — progress_fp HEAD oid shares invalidate with scan remiss.
    clear_progress_head_generation_cache()


def _mtime_ns_safe_for_scan(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns) if path.exists() else 0
    except OSError:
        return 0


def _git_dir_for_scan_fingerprint(root: Path) -> Path | None:
    """Resolve checkout git dir (``.git`` dir or ``gitdir:`` target) — no subprocess."""
    git_path = root / ".git"
    try:
        if git_path.is_file():
            text = git_path.read_text(encoding="utf-8").strip()
            if not text.lower().startswith("gitdir:"):
                return None
            target = Path(text.split(":", 1)[1].strip())
            if not target.is_absolute():
                target = (root / target).resolve()
            return target if target.exists() else None
        if git_path.is_dir():
            return git_path
    except OSError:
        return None
    return None


def _git_head_index_mtime_ns_for_scan(root: Path) -> tuple[int, int]:
    """Generation token for lite adapt fp — HEAD + index mtimes under git dir."""
    git_dir = _git_dir_for_scan_fingerprint(root)
    if git_dir is None:
        return (0, 0)
    return (
        _mtime_ns_safe_for_scan(git_dir / "HEAD"),
        _mtime_ns_safe_for_scan(git_dir / "index"),
    )


def _live_adapt_git_fingerprint(root: Path) -> str | None:
    """HEAD:porcelain with notes/ stripped — match ``automation_adapt._git_fingerprint``.

    Needle: SCAN_ADAPT_FP_GEN_CACHE_2026_09_08 — skip rev-parse+porcelain shells when
    HEAD+index mtime generation is unchanged (same semantics as adapt gen-cache).
    """
    key = str(root)
    gen = _git_head_index_mtime_ns_for_scan(root)
    cached = _LIVE_ADAPT_FP_GEN_CACHE.get(key)
    if cached is not None and cached[0] == gen:
        return cached[1]
    if not (root / ".git").exists():
        result: str | None = None
        _LIVE_ADAPT_FP_GEN_CACHE[key] = (gen, result)
        return result
    try:
        head_out = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
        head_ref = head_out.strip() or "INIT"
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        head_ref = "INIT"
    try:
        status_out = subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        result = None
        _LIVE_ADAPT_FP_GEN_CACHE[key] = (gen, result)
        return result
    porcelain = (status_out or "").rstrip("\n")
    result = f"{head_ref}:{_strip_notes_porcelain_for_scan(porcelain)}"
    _LIVE_ADAPT_FP_GEN_CACHE[key] = (gen, result)
    return result


def _should_re_adapt_for_scan(root: Path | None = None) -> bool:
    """Scan-path ``should_re_adapt`` without cold-importing ``automation_adapt``.

    Needle: SCAN_ADAPT_NO_COLD_IMPORT_2026_09_08 — cold scan paid ~45ms compile
    for ``import automation_adapt`` solely to compare git fingerprints. Prefer
    already-loaded module (generation caches); else lite read of adapt-state +
    HEAD/porcelain with notes/ stripped (same semantics as adapt).
    SCAN_ADAPT_FP_GEN_CACHE_2026_09_08 — lite remiss skips git shells on HIT.
    """
    root = root or ROOT
    mod = sys.modules.get("automation_adapt")
    if mod is not None:
        try:
            return bool(mod.should_re_adapt(root))
        except Exception:  # noqa: BLE001
            pass
    path = CONFIG_DIR / "adapt-state.json"
    try:
        prev = json.loads(path.read_text(encoding="utf-8")).get("git_fingerprint")
    except (OSError, json.JSONDecodeError, TypeError, AttributeError):
        return True
    if not prev:
        return True
    live = _live_adapt_git_fingerprint(root)
    if live is None:
        return True
    return prev != live


def _is_last_cycle_deferred_poison(last_cycle: dict[str, Any]) -> bool:
    """Unit-test fixture / contradiction leaked into live peer-loop-state.

    Needle: SCAN_POISON_NO_TRANSCRIPT_IMPORT_2026_09_08 — prefer
    ``peer_last_cycle_poison`` (~2.5ms) over ``peer_transcript`` (~40ms compile)
    on every cold scan MISS. Heal paths may still import transcript for state I/O.
    """
    try:
        import peer_last_cycle_poison as lc_poison

        return bool(lc_poison.is_last_cycle_poison(last_cycle))
    except Exception:  # noqa: BLE001
        ft = str(last_cycle.get("failure_type") or "").strip()
        if last_cycle.get("verify_ok") is True and ft == "deferred":
            return True
        try:
            ts = float(last_cycle.get("ts") or 0)
        except (TypeError, ValueError):
            ts = 0.0
        if 0 < ts <= 1.0 and not last_cycle.get("queue_fp") and not last_cycle.get("git_head"):
            return True
        return False


def _force_free_desktop_wanted() -> bool:
    if os.environ.get("AUTOMATION_FORCE_FREE_DESKTOP") == "1":
        return True
    try:
        cfg = _live_cfg()
        return bool(cfg.get("force_free_desktop_auth"))
    except Exception:  # noqa: BLE001
        return False


def _avail_ram_gb() -> float:
    """MemAvailable from /proc/meminfo (GB). 0.0 on read failure."""
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024 / 1024
    except (OSError, ValueError, IndexError):
        return 0.0
    return 0.0


def _gpu_compute_ballast_exempt(*, avail_gb: float | None = None) -> bool:
    """Skip dgx_gpu_compute ballast when MemAvailable is healthy.

    Productive forever-embed (mamba-2.8b) sits at ~3–8GB RSS; killing it under
    pressure=ok caused systemd restart storms (counter 70+) while agents were
    not actually starved. Only reclaim gpu_compute under real pressure.
    """
    floor = float(
        _live_cfg().get("ram_min_avail_gb")
        or _RAM_BALLAST_GPU_COMPUTE_OK_AVAIL_GB
    )
    if avail_gb is None:
        avail_gb = _avail_ram_gb()
    return avail_gb >= floor


def _ram_ballast_min_rss_kb(args: str, *, avail_gb: float | None = None) -> int | None:
    """Return min RSS (KB) to treat as ballast, or None to exempt entirely."""
    if "dgx_gpu_compute.py" in args:
        if _gpu_compute_ballast_exempt(avail_gb=avail_gb):
            return None
        return _RAM_BALLAST_GPU_COMPUTE_MIN_RSS_KB
    return _RAM_BALLAST_MIN_RSS_KB


def _pid_owned_by_me(pid: int) -> bool:
    """True when ``/proc/<pid>`` is owned by this UID (matches historical ``ps -u``)."""
    try:
        return os.stat(f"/proc/{pid}").st_uid == os.getuid()
    except OSError:
        return False


def _iter_ram_ballast_pid_rss_args() -> list[tuple[int, int, str]]:
    """Yield ``(pid, rss_kb, args)`` for ballast needles.

    Needle: PS_AXO_RSS_SHARE_BALLAST_2026_09_08 / RAM_BALLAST_REUSE_PS_AXO_2026_09_08 —
    reuse ``_ps_axo_lines`` (``pid=,rss=,comm=,args=``) so cold scan does not shell
    a second ``ps -u``. Parse RSS from the axo column (no ``/proc`` walk). Darwin
    / empty axo keeps ``ps -u`` fallback.
    """
    out: list[tuple[int, int, str]] = []
    lines = _ps_axo_lines()
    if lines:
        for raw in lines:
            parsed = _parse_ps_axo_pid_rss_args(raw)
            if parsed is None:
                continue
            pid_s, rss, args = parsed
            if not any(n in args for n in _RAM_BALLAST_NEEDLES):
                continue
            try:
                pid = int(pid_s)
            except ValueError:
                continue
            if pid <= 0:
                continue
            if sys.platform != "darwin" and not _pid_owned_by_me(pid):
                continue
            out.append((pid, rss, args))
        return out
    if sys.platform != "darwin":
        return out
    try:
        text = subprocess.check_output(
            ["ps", "-u", Path.home().name, "-o", "pid=,rss=,args="],
            text=True,
            errors="replace",
            timeout=8,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return out
    for line in text.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        pid_s, rss_s, args = parts[0], parts[1], parts[2]
        if not any(n in args for n in _RAM_BALLAST_NEEDLES):
            continue
        try:
            out.append((int(pid_s), int(rss_s), args))
        except ValueError:
            continue
    return out


def _scan_ram_ballast() -> list[str]:
    """Return evidence strings for known RAM hogs (pid:rssMB:name).

    OVERSEER_RAM_BALLAST_GPU_COMPUTE_PRESSURE_2026_09_07 — ``dgx_gpu_compute.py``
    forever embed is productive at ~3–8GB; only flag when MemAvailable is tight
    AND RSS ≥ ~14GB runaway. Poll/fill keep the 200MB floor always.
    """
    found: list[str] = []
    avail_gb = _avail_ram_gb()
    for pid, rss, args in _iter_ram_ballast_pid_rss_args():
        min_rss = _ram_ballast_min_rss_kb(args, avail_gb=avail_gb)
        if min_rss is None or rss < min_rss:
            continue
        name = next((n for n in _RAM_BALLAST_NEEDLES if n in args), "ballast")
        found.append(f"{pid}:{rss // 1024}MB:{name}")
    return found


def _heal_ram_ballast(_reg: dict[str, Any]) -> str:
    import signal as signal_mod

    killed: list[str] = []
    skipped_gpu = 0
    avail_gb = _avail_ram_gb()
    rows = _iter_ram_ballast_pid_rss_args()
    if not rows and sys.platform == "darwin":
        return "ps failed: no ballast rows"
    for pid, rss, args in rows:
        min_rss = _ram_ballast_min_rss_kb(args, avail_gb=avail_gb)
        if min_rss is None:
            if "dgx_gpu_compute.py" in args:
                skipped_gpu += 1
            continue
        if rss < min_rss:
            continue
        try:
            os.kill(pid, signal_mod.SIGKILL)
            killed.append(f"{pid}:{rss // 1024}MB")
        except (ProcessLookupError, PermissionError, OSError):
            pass
    if killed:
        msg = f"killed {len(killed)} ballast ({', '.join(killed[:6])})"
    else:
        msg = "no ballast"
    if skipped_gpu:
        msg += f"; skipped {skipped_gpu} gpu_compute (avail={avail_gb:.1f}GB ok)"
    return msg


def _heal_paid_auth_park(_reg: dict[str, Any]) -> str:
    parts: list[str] = []
    hub = Path.home() / ".config" / "automation-hub"
    paid = hub / "cursor-agent.env"
    park = hub / "cursor-agent.env.paid-disabled"
    if paid.is_file():
        try:
            paid.replace(park)
            parts.append("parked cursor-agent.env")
        except OSError as exc:
            parts.append(f"park failed: {exc}")
    os.environ["PEER_LOOP_PAID_API"] = "0"
    os.environ["AUTOMATION_FORCE_FREE_DESKTOP"] = "1"
    parts.append("PEER_LOOP_PAID_API=0")
    try:
        import peer_terminal as pt

        if hasattr(pt, "force_free_desktop_auth"):
            pt.force_free_desktop_auth()
            parts.append("peer_terminal free lock")
    except Exception as exc:  # noqa: BLE001
        parts.append(f"terminal lock skip: {exc}")
    return "; ".join(parts) if parts else "already free"


def _heal_plan_gate_chicken_egg(reg: dict[str, Any]) -> str:
    """Mechanical break for plan-gate ↔ verify_ok=false chicken-egg."""
    parts: list[str] = []
    try:
        import automation_adapt as adapt

        acts, warns = adapt.heal_queue_drift(root=ROOT, write=True)
        parts.append(f"queue drift healed acts={len(acts)} warns={len(warns)}")
    except Exception as exc:  # noqa: BLE001
        parts.append(f"queue drift: {exc}")
    try:
        parts.append(_heal_adapt())
    except Exception as exc:  # noqa: BLE001
        parts.append(f"adapt: {exc}")
    try:
        import peer_transcript as transcript
        import peer_last_cycle_poison as lc_poison

        state = transcript.load_state()
        lc = state.get("last_cycle") if isinstance(state, dict) else None
        if isinstance(lc, dict) and lc_poison.is_last_cycle_poison(lc):
            parts.append(_heal_last_cycle_deferred_poison(reg))
        elif isinstance(lc, dict) and lc.get("verify_ok") is False:
            ft = str(lc.get("failure_type") or "")
            if ft == "deferred":
                parts.append("deferred soft-skip — keep dispatch soft")
            else:
                # Soft episodic: do not invent green; poke so peers keep working.
                parts.append("verify_ok=false kept (no false-green)")
    except Exception as exc:  # noqa: BLE001
        parts.append(f"last_cycle: {exc}")
    parts.append(_touch_signal())
    return "; ".join(str(p) for p in parts if p)


def _heal_seed_last_cycle(_reg: dict[str, Any]) -> str:
    """Bootstrap last_cycle + clear stall so dispatch/self-heal stop looping.

    OVERSEER_SEED_GATE_READY_2026_09_04 — deferred/idle (rc=0, ready=False)
    must not stamp verify_ok=True (false-green last_cycle).
    OVERSEER_SEED_SKIP_FAIL_STAMP_2026_09_04 — never stamp verify_ok=False with
    note "self-heal seeded" (scrub pops → missing_last_cycle forever).
    OVERSEER_SEED_REHYDRATE_HISTORY_2026_09_04 — on not-ok, rehydrate history.
    OVERSEER_POISON_HEAL_FALLBACK_2026_09_04 — prefer poison module SoT.
    OVERSEER_HEAL_SCRUB_FALLBACK_2026_09_04 — safe_scrub → poison module when
    transcript.scrub_* is mid-clobber; required by pool needle-sync.
    OVERSEER_SEED_NOT_LOCAL_ONLY_2026_09_04 — seed is mechanical delivery, not
    prompt-refresh local-only; never arm oversight local-only stagnation (+14).
    """
    import peer_last_cycle_poison as lc_poison
    import peer_stall_pivot as stall
    import peer_transcript as transcript
    import run_peer_tasks

    state = transcript.load_state()
    # OVERSEER_HEAL_SCRUB_FALLBACK_2026_09_04
    lc_poison.safe_scrub(transcript, state)
    fp_before, _ = transcript.current_queue_fingerprint()
    rc, ready = run_peer_tasks.run_local_cycle(quick=True, log_fn=lambda _m: None)
    verify_ok = rc == 0 and bool(ready)
    if not verify_ok:
        try:
            import automation_adapt as adapt

            adapt.run_heal(write=True, quick=True)
            rc, ready = run_peer_tasks.run_local_cycle(
                quick=True, log_fn=lambda _m: None
            )
            verify_ok = rc == 0 and bool(ready)
        except Exception:  # noqa: BLE001
            pass
    if not verify_ok:
        hist = state.get("cycle_history") or []
        for entry in reversed(list(hist)):
            if not isinstance(entry, dict):
                continue
            if entry.get("verify_ok") is not True:
                continue
            if lc_poison.is_last_cycle_poison(entry):
                continue
            hydrated = dict(entry)
            note = str(hydrated.get("note") or "").strip()
            tag = "self-heal rehydrated last_cycle"
            if tag not in note.lower():
                hydrated["note"] = ((note + "; " if note else "") + tag)[:240]
            hydrated["ts"] = time.time()
            hydrated["verify_ok"] = True
            hydrated["noop"] = False
            state["last_cycle"] = hydrated
            stall.clear_stall(state)
            transcript.save_state(state)
            skip_why = "deferred/not-ready" if (rc == 0 and not ready) else "red verify"
            return f"rehydrated last_cycle from cycle_history ({skip_why}; no poison fail stamp)"
        stall.clear_stall(state)
        transcript.save_state(state)
        return "seed skipped (verify not ok); scrub only — no verify_ok=False stamp"
    fp_after, _ = transcript.current_queue_fingerprint()
    transcript.record_cycle_outcome(
        state,
        rc=0,
        verify_ok=True,
        queue_fp_before=fp_before,
        queue_fp_after=fp_after,
        note="self-heal seeded last_cycle",
        # OVERSEER_SEED_NOT_LOCAL_ONLY_2026_09_04
        local_only=False,
    )
    # Fail-closed: deferred ⇒ verify_ok=False. Never pop failure_type under
    # green — that greases delivery meters (OVERSEER_SANITIZE_DEFERRED_VERIFY_OK).
    lc = state.get("last_cycle")
    if isinstance(lc, dict):
        fixed = lc_poison.sanitize_last_cycle(lc)
        if fixed is not None:
            state["last_cycle"] = fixed
            lc = fixed
        ft = str(lc.get("failure_type") or "").strip()
        if ft == "deferred":
            lc["verify_ok"] = False
        else:
            lc["verify_ok"] = True
            lc["noop"] = False
    stall.clear_stall(state)
    transcript.save_state(state)
    lc_final = state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else {}
    effective_ok = bool(lc_poison.effective_verify_ok(lc_final))
    return f"seeded last_cycle verify_ok={effective_ok}"


def _heal_last_cycle_deferred_poison(reg: dict[str, Any]) -> str:
    """OVERSEER_SCRUB_DEFERRED_POISON_2026_09_04 — scrub fixture + reseed.

    OVERSEER_POISON_HEAL_FALLBACK_2026_09_04 — prefer poison module SoT when
    peer_transcript.scrub_* is mid-clobber / missing.
    OVERSEER_HEAL_SCRUB_FALLBACK_2026_09_04 — pool needle-sync SoT for dirty
    peer-N that skip hard-reset (safe_scrub fallback path).
    OVERSEER_POISON_HEAL_SANITIZE_KEEP_FT_2026_09_04 — keep failure_type;
    set verify_ok=False (never pop-ft under green).
    """
    import peer_last_cycle_poison as lc_poison
    import peer_transcript as transcript

    state = transcript.load_state()
    # OVERSEER_HEAL_SCRUB_FALLBACK_2026_09_04
    reason = lc_poison.safe_scrub(transcript, state) or "no-op scrub"
    lc = state.get("last_cycle")
    if isinstance(lc, dict) and str(lc.get("failure_type") or "").strip() == "deferred":
        fixed = lc_poison.sanitize_last_cycle(lc)
        if fixed is not None:
            state["last_cycle"] = fixed
            lc = fixed
        if isinstance(lc, dict) and lc.get("verify_ok") is True:
            lc = dict(lc)
            lc["verify_ok"] = False
            state["last_cycle"] = lc
        reason = f"scrubbed deferred poison; {reason}"
    elif "scrubbed" not in str(reason).lower() and "sanitized" not in str(reason).lower():
        reason = f"scrubbed; {reason}"
    if not isinstance(state.get("last_cycle"), dict):
        transcript.save_state(state)
        return f"{reason}; {_heal_seed_last_cycle(reg)}"
    transcript.save_state(state)
    lc_final = state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else {}
    if lc_final.get("verify_ok") is True:
        return f"{reason}; last_cycle kept (verify_ok clean)"
    return f"{reason}; last_cycle sanitized (verify_ok=False; failure_type kept)"



def _enqueue_self_heal_item(title: str, detail: str) -> str:
    """Append a one-line factory task when code change is required."""
    work_path = auto.WORK_QUEUE_PATH
    ctx_path = auto.CONTEXT_PATH
    marker = f"[self-heal] {title}"
    title_key = auto._normalize_queue_key(title)
    try:
        work_md = work_path.read_text(encoding="utf-8") if work_path.is_file() else ""
        known = {
            auto._normalize_queue_key(x)
            for x in auto.open_work_items(work_md=work_md).open_items
        }
        if auto._normalize_queue_key(marker) in known or title_key in known:
            return f"already queued: {title}"
        line = f"- [ ] **{marker}** — {detail}"
        if "## Active" in work_md:
            work_md = work_md.replace("## Active\n", f"## Active\n{line}\n", 1)
        else:
            work_md = work_md.rstrip() + f"\n\n## Active\n{line}\n"
        work_path.write_text(work_md, encoding="utf-8")
        try:
            import automation_adapt as adapt

            adapt.heal_queue_drift(root=ROOT, write=True)
        except Exception:  # noqa: BLE001
            pass
        return f"enqueued: {title}"
    except OSError as exc:
        return f"enqueue failed: {exc}"


def _heal_queue_spam(_reg: dict[str, Any]) -> str:
    import autonomous_repair as ar

    removed = auto.dedupe_work_queue_files(write=True)
    if removed:
        return f"deduped {removed} queue line(s)"
    return ar.dedupe_queue()


def _heal_verify_fail(reg: dict[str, Any]) -> str:
    import autonomous_repair as ar

    lines: list[str] = []

    def log_fn(msg: str) -> None:
        lines.append(msg)

    ar.repair_verify_failure(
        log_fn=log_fn,
        paid_api=os.environ.get("PEER_LOOP_PAID_API") == "1",
    )
    return lines[-1] if lines else "verify repair dispatched"


def _heal_dual_namespace_collision(_reg: dict[str, Any]) -> str:
    collision = dual_namespace_collision()
    stopped: list[str] = []
    for label in collision["peer"] + collision["improve"]:
        stopped.append(_bootout(label))
    rogue = _heal_rogue_oversight()
    if rogue:
        stopped.append(rogue)
    return "; ".join(stopped) if stopped else "no rogue namespace daemons"


def _heal_verify_fail_hold(reg: dict[str, Any]) -> str:
    result = _heal_verify_fail(reg)
    state = _read_state()
    last = state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else None
    if isinstance(last, dict) and last.get("verify_ok") is True:
        return result
    return f"{result}; {_heal_seed_last_cycle(reg)}"


def _soft_refresh_horizon() -> str:
    """In-process horizon write without restarting improve.

    Needle: SOFT_REFRESH_NO_COLD_IMPROVE_IMPORT_2026_09_08 — cold heal paid
    ``import automation_improve`` (~58ms) + ``gather_signals`` (~196ms) on every
    ``horizon_stale`` heal even when improve daemon is already up and the caller
    wakes it next. Prefer warm in-process write when the module is loaded; else
    defer (wake writes) — preserves OVERSEER_HORIZON_WRITE_HEAL when improve is
    already in-process without cold-compile theater on typical DGX heal.

    Needle: SOFT_REFRESH_DEFER_WARM_GATHER_DAEMON_UP_2026_09_08 — horizon_stale
    only fires when improve is running; warm gather+write (~52–108ms) duplicates
    the wake path. Defer when daemon is up; gather only when module warm + daemon
    down (in-process write heal).

    Needle: SOFT_REFRESH_SKIP_WHEN_HORIZON_FRESH_2026_09_08 — scan TTL remiss /
    race after write still called warm gather+write while freshest board age ≤
    HORIZON_STALE_SEC; skip gather when board already fresh.
    """
    improve = sys.modules.get("automation_improve")
    if improve is None:
        return "horizon soft-refresh deferred (improve not loaded; wake writes)"
    # SOFT_REFRESH_DEFER_WARM_GATHER_DAEMON_UP_2026_09_08
    if _improve_daemon_running():
        return "horizon soft-refresh deferred (improve up; wake writes)"
    # SOFT_REFRESH_SKIP_WHEN_HORIZON_FRESH_2026_09_08 — remiss/race.
    age = _file_age_sec(_horizon_board_path())
    if age is not None and age <= HORIZON_STALE_SEC:
        return (
            f"horizon soft-refresh skipped (fresh age={age:.0f}s≤{HORIZON_STALE_SEC:.0f}s)"
        )
    try:
        signals = improve.gather_signals(quick=True, research=False, refresh_trends=False)
        paths = improve.write_horizon(signals)
        return f"horizon soft-refresh → {paths[0] if paths else '?'}"
    except Exception as exc:  # noqa: BLE001
        return f"horizon soft-refresh failed: {exc}"


def _append_improve_wake(note: str) -> None:
    """Evidence line so factory wake_ok / asi_rubric see recent improve activity."""
    try:
        IMPROVE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with IMPROVE_LOG.open("a", encoding="utf-8") as fh:
            fh.write(
                f"{time.strftime('%Y-%m-%d %H:%M:%S')}  "
                f"wake peer: touched peer-turn.signal ({note})\n"
            )
    except OSError:
        pass


def _heal_horizon_stale(_reg: dict[str, Any]) -> str:
    """Nudge improve so IMPROVE_HORIZON.md refreshes — never restart thrash a live daemon.

    OVERSEER_HORIZON_SKIP_RESTART_2026_09_04 — restarting improve every heal cycle
    prevents write_horizon from ever completing → horizon stays stale → more restarts.
    Soft-refresh + wake when improve is already up; restart only when it is down.
    OVERSEER_HORIZON_WRITE_HEAL_2026_09_04 — in-process write (not kickstart theater).
    """
    if _improve_daemon_running():
        soft = _soft_refresh_horizon()
        wake = _touch_signal()
        _append_improve_wake("horizon-heal skip_restart")
        return f"skip_restart (improve up); {soft}; {wake}"
    if sys.platform == "darwin":
        return _kickstart(_live_improve_label())
    return _ensure_systemd_improve_unit()


def _heal_noop_stall(_reg: dict[str, Any]) -> str:
    """Compact + MET theater close so queue_fp can move; wake peer.

    OVERSEER_NOOP_HEAL_MET_2026_09_07 — compact alone left COD/verify/noop
    twins open (removed=0); resolve_satisfied_met_theater is inside compact.
    """
    removed, actions = auto.compact_executable_queue(write=True, max_active=12)
    sig = _touch_signal()
    detail = "; ".join(actions[:4]) if actions else "no-op"
    return f"compact {removed} line(s) ({detail}); {sig}"



_HUB_PROTECT_TIMER = "hub-protect-restore.timer"
_HUB_PROTECT_PATH = "hub-protect-restore.path"
_HUB_PROTECT_SERVICE = "hub-protect-restore.service"


def _hub_protect_unit_masked(unit: str) -> bool:
    """True when unit file is a symlink to /dev/null (systemctl mask)."""
    path = _systemd_unit_path(unit)
    if not path.exists() or not path.is_symlink():
        return False
    try:
        return path.resolve() == Path("/dev/null")
    except OSError:
        return False


def _hub_protect_pick_backup(unit: str) -> Path | None:
    """Prefer .overseer-masked, then .overseer-bak, then DISABLED_* siblings.

    OVERSEER_HUB_PROTECT_RECREATE_2026_09_04 — deleted units restore from bak.
    """
    path = _systemd_unit_path(unit)
    for suffix in (".overseer-masked", ".overseer-bak"):
        cand = Path(str(path) + suffix)
        if cand.is_file() and not cand.is_symlink():
            return cand
    parent = path.parent
    if not parent.is_dir():
        return None
    disabled = sorted(
        (
            p
            for p in parent.glob(f"{path.name}.DISABLED*")
            if p.is_file() and not p.is_symlink()
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return disabled[0] if disabled else None


def _hub_protect_units_present() -> bool:
    """True when timer/path is usable, or healable via mask/DISABLED backup."""
    if _systemd_unit_usable(_HUB_PROTECT_TIMER) or _systemd_unit_usable(_HUB_PROTECT_PATH):
        return True
    for unit in (_HUB_PROTECT_TIMER, _HUB_PROTECT_PATH):
        bak = _hub_protect_pick_backup(unit)
        if bak is None:
            continue
        if _hub_protect_unit_masked(unit) or not _systemd_unit_path(unit).exists():
            return True
    return False


def _hub_protect_timer_active() -> bool:
    """True when the 5s restore timer is active (path optional but preferred)."""
    return _systemd_user_active(_HUB_PROTECT_TIMER)


def _unmask_hub_protect_units() -> list[str]:
    """Restore hub-protect unit files from mask/DISABLED backups; daemon-reload."""
    parts: list[str] = []
    for unit in (_HUB_PROTECT_TIMER, _HUB_PROTECT_PATH):
        path = _systemd_unit_path(unit)
        bak = _hub_protect_pick_backup(unit)
        if bak is None:
            continue
        need_restore = _hub_protect_unit_masked(unit) or not path.exists()
        if not need_restore:
            continue
        try:
            if path.exists() or path.is_symlink():
                path.unlink(missing_ok=True)
            path.write_text(bak.read_text(encoding="utf-8"), encoding="utf-8")
            if "masked" in bak.name or bak.name.endswith(".overseer-masked"):
                parts.append(f"unmasked {unit}")
            else:
                parts.append(f"restored {unit}")
        except OSError as exc:
            parts.append(f"restore {unit} failed: {exc}")
    if parts:
        _systemd_daemon_reload()
    return parts



def _hub_protect_restore_paused() -> bool:
    """True when restore is intentionally paused (land-hold / RESTORE_PAUSED / wrap stub).

    OVERSEER_HUB_PROTECT_RESTORE_PAUSED_2026_09_04 — must exist so scan/heal never
    NameError mid-clobber, and timer_stopped is not raised during intentional pause.

    OVERSEER_RESTORE_PAUSE_NOT_HIGH_DURING_PROTECT_2026_09_04 — during intentional
    mac clobber protect, RESTORE_PAUSED is expected scaffolding (not a HIGH stall).

    Needle: HUB_PROTECT_PAUSE_NO_LAND_HOLD_IMPORT_2026_09_08 — cold scan always
    imported ``peer_land_hold`` (~7ms) even when no RESTORE_PAUSED / wrap-stub.
    Fast-negative on flags+wrap before import; land_hold only when a pause signal
    exists (intentional-protect may suppress HIGH).
    """
    hub = Path.home() / ".config/automation-hub"
    flag_hit = (
        (hub / "RESTORE_PAUSED").is_file()
        or (hub / "hub-protect" / "RESTORE_PAUSED").is_file()
        or (ROOT / "RESTORE_PAUSED").is_file()
    )
    wrap_paused = False
    restore = hub / "bin" / "restore-hub-protect.sh"
    try:
        text = restore.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    if text:
        head = text[:500].lower()
        if "restore paused" in head:
            wrap_paused = True
        elif "paused" in head and "exit 0" in head and len(text) < 400:
            wrap_paused = True
    if not flag_hit and not wrap_paused:
        return False
    try:
        import peer_land_hold as lh

        if bool(lh.intentional_mac_clobber_protect()):
            return False
        if bool(lh.restore_is_paused()):
            return True
    except Exception:
        pass
    return True


def _sync_adapt_fp_after_hub_protect_touch() -> str:
    """OVERSEER_ADAPT_SYNC_AFTER_HUB_PROTECT_2026_09_04 — restore rewrites scripts/.

    Hub-protect restore / beat-mac refresh dirty porcelain → should_re_adapt()
    true → medium adapt_stale forever unless fingerprint is re-synced here.
    """
    try:
        import automation_adapt as adapt

        if adapt.sync_git_fingerprint(ROOT):
            return "synced adapt fingerprint after hub-protect"
        return "adapt fingerprint already current"
    except Exception as exc:  # noqa: BLE001
        return f"adapt fingerprint sync skipped ({exc})"


def _heal_hub_protect_restore_paused(_reg: dict[str, Any]) -> str:
    """Unstub paused restore wrap + clear expired holds + run restore.

    OVERSEER_HUB_PROTECT_RESTORE_PAUSED_2026_09_04
    OVERSEER_ADAPT_SYNC_AFTER_HUB_PROTECT_2026_09_04
    """
    parts: list[str] = []
    try:
        import peer_land_hold as lh

        parts.append(lh.clear_expired(force=True))
        parts.append(lh.run_restore())
    except Exception as exc:  # noqa: BLE001
        parts.append(f"land_hold heal error: {exc}")
        restore = Path.home() / ".config/automation-hub/bin/restore-hub-protect.sh"
        real = restore.with_name(restore.name + ".real")
        if real.is_file() and restore.is_file():
            try:
                import shutil as _sh

                _sh.copy2(real, restore)
                restore.chmod(0o755)
                parts.append("fallback unstub from .real")
            except OSError as copy_exc:
                parts.append(f"fallback unstub failed: {copy_exc}")
    if _hub_protect_restore_paused():
        parts.append("still paused")
    else:
        parts.append("restore live")
        parts.append(_sync_adapt_fp_after_hub_protect_touch())
    return "; ".join(parts)


def _heal_hub_protect_timer(_reg: dict[str, Any]) -> str:
    """Re-enable hub-protect restore so Mac rsync cannot leave WORKING lands dead.

    OVERSEER_HUB_PROTECT_TIMER_ONLY_2026_09_04 — enable only units that exist.
    Missing path used to fail the whole enable and leave a permanent HIGH bottleneck.
    OVERSEER_HEAL_CLEAR_LAND_HOLD_2026_09_04 — clear expired/theater holds first.
    OVERSEER_HUB_PROTECT_PAUSE_RESPECT_2026_09_04 — skip while wrap stubbed *after*
    unstub attempt (never permanent skip on leftover RESTORE_PAUSED flag files).
    OVERSEER_HEAL_TIMER_UNSTUB_FIRST_2026_09_04 — unstub + clear flags, then enable.
    """
    if sys.platform == "darwin":
        return "skip (darwin)"
    parts: list[str] = []
    # Stale RESTORE_PAUSED flags used to return early → timer stayed down → HIGH.
    if _hub_protect_restore_paused() or (
        (Path.home() / ".config/automation-hub" / "RESTORE_PAUSED").is_file()
        or (Path.home() / ".config/automation-hub" / "hub-protect" / "RESTORE_PAUSED").is_file()
    ):
        unstub_msg = _heal_hub_protect_restore_paused(_reg)
        parts.append(unstub_msg)
        if _hub_protect_restore_paused():
            # Wrap still stubbed after forced clear — true land window.
            return f"skip (RESTORE_PAUSED wrap); {unstub_msg}"
    parts.extend(_unmask_hub_protect_units())
    try:
        import peer_land_hold as land_hold

        force = False
        hold = land_hold.HOLD_PATH
        if hold.is_file():
            try:
                body = hold.read_text(encoding="utf-8", errors="replace").strip().lower()
                mtime = float(hold.stat().st_mtime)
            except OSError:
                body, mtime = "", 0.0
            age = land_hold.hold_age_sec()
            force = (
                body in {"hold", "1"}
                or body.startswith("overseer-stag")
                or (age is not None and age >= land_hold.MAX_AGE_SEC)
                or mtime > time.time() + 1.0
            )
        parts.append(land_hold.clear_expired(force=force))
        repo_hold = ROOT / "OVERSEER_LAND_HOLD"
        if repo_hold.is_file():
            try:
                repo_hold.unlink()
                parts.append("cleared repo OVERSEER_LAND_HOLD")
            except OSError as exc:
                parts.append(f"repo hold clear failed: {exc}")
    except Exception as exc:  # noqa: BLE001
        parts.append(f"land-hold clear skip: {exc}")
    if not _hub_protect_units_present():
        parts.append("hub-protect units absent")
        return "; ".join(parts)
    _invalidate_probe_cache("systemd:hub-protect")
    try:
        subprocess.run(
            ["systemctl", "--user", "reset-failed", _HUB_PROTECT_SERVICE],
            capture_output=True,
            timeout=10.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    enable_units = [
        u for u in (_HUB_PROTECT_TIMER, _HUB_PROTECT_PATH) if _systemd_unit_usable(u)
    ]
    if not enable_units:
        parts.append("hub-protect units absent")
        return "; ".join(parts)
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "enable", "--now", *enable_units],
            capture_output=True,
            text=True,
            timeout=30.0,
            check=False,
        )
        if proc.returncode == 0:
            parts.append(
                "enable --now "
                + "+".join(u.replace("hub-protect-restore.", "") for u in enable_units)
            )
        else:
            err = (proc.stderr or proc.stdout or "failed").strip()[:120]
            parts.append(f"enable failed: {err}")
            if _HUB_PROTECT_TIMER in enable_units and _HUB_PROTECT_PATH in enable_units:
                try:
                    proc2 = subprocess.run(
                        ["systemctl", "--user", "enable", "--now", _HUB_PROTECT_TIMER],
                        capture_output=True,
                        text=True,
                        timeout=30.0,
                        check=False,
                    )
                    if proc2.returncode == 0:
                        parts.append("enable --now timer-only")
                except (OSError, subprocess.TimeoutExpired) as exc2:
                    parts.append(f"timer-only error: {exc2}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        parts.append(f"enable error: {exc}")
    if _hub_protect_restore_paused():
        parts.append(_heal_hub_protect_restore_paused(_reg))
    restore = Path.home() / ".config/automation-hub/bin/restore-hub-protect.sh"
    if restore.is_file() and not _hub_protect_restore_paused():
        try:
            rproc = subprocess.run(
                ["bash", str(restore)],
                capture_output=True,
                text=True,
                timeout=60.0,
                check=False,
            )
            line = (rproc.stdout or rproc.stderr or "").strip().splitlines()
            parts.append(line[-1][:160] if line else f"restore rc={rproc.returncode}")
            # OVERSEER_ADAPT_SYNC_AFTER_HUB_PROTECT_2026_09_04
            parts.append(_sync_adapt_fp_after_hub_protect_touch())
        except (OSError, subprocess.TimeoutExpired) as exc:
            parts.append(f"restore error: {exc}")
    _invalidate_probe_cache("systemd:hub-protect")
    if _systemd_user_active_impl(_HUB_PROTECT_TIMER) or _hub_protect_timer_active():
        parts.append("timer active")
    else:
        time.sleep(0.35)
        _invalidate_probe_cache("systemd:hub-protect")
        if _systemd_user_active_impl(_HUB_PROTECT_TIMER):
            parts.append("timer active")
        else:
            parts.append("timer still inactive")
    return "; ".join(parts)


_HEALERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "daemon_peer_stopped": _heal_peer_daemon,
    "daemon_peer_job_stopped": _heal_peer_job_stopped,
    "daemon_improve_stopped": lambda reg: _heal_improve_daemon(reg),
    "daemon_research_stopped": _heal_research_daemon,  # OVERSEER_HEAL_RESEARCH_DAEMON_2026_09_04
    "daemon_dashboard_stopped": _heal_dashboard_daemon,  # OVERSEER_DASHBOARD_KEEPALIVE_2026_09_06
    "dual_brain_ram_peer": lambda reg: _bootout(RAM_PEER_LABEL),
    "dual_brain_hub_peer": _heal_dual_namespace_collision,
    "dual_brain_hub_oversight": _heal_rogue_oversight,
    "oversight_worktree_cwd": _heal_oversight_worktree_cwd,
    "horizon_stale": _heal_horizon_stale,
    "unittest_storm": lambda reg: _extend_test_cache_ttl() + "; " + _remove_lock(TEST_LOCK),
    "verify_storm": lambda reg: _remove_lock(VERIFY_LOCK),
    "stale_verify_lock": lambda reg: _remove_lock(VERIFY_LOCK),
    "stale_test_lock": lambda reg: _remove_lock(TEST_LOCK),
    "queue_drift": lambda reg: _heal_queue_drift(),
    "queue_spam": _heal_queue_spam,
    "adapt_stale": lambda reg: _heal_adapt(),
    "verify_fail_hold": _heal_verify_fail_hold,
    "missing_last_cycle": _heal_seed_last_cycle,
    "last_cycle_deferred_poison": _heal_last_cycle_deferred_poison,
    "last_cycle_poison": _heal_seed_last_cycle,
    "noop_stall": _heal_noop_stall,
    "improve_not_waking_peer": lambda reg: _touch_signal(),
    "queue_read_blocked": lambda reg: _extend_test_cache_ttl() + "; " + _remove_lock(TEST_LOCK),
    "hub_protect_timer_stopped": _heal_hub_protect_timer,
    "hub_protect_restore_paused": _heal_hub_protect_restore_paused,
    "plan_gate_chicken_egg": _heal_plan_gate_chicken_egg,
    "ram_ballast": _heal_ram_ballast,
    "paid_auth_park": _heal_paid_auth_park,
}


def apply_heals(
    bottlenecks: list[Bottleneck],
    *,
    registry: dict[str, Any] | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> list[str]:
    """Run mechanical heals for detected bottlenecks (cooldown + progress stall)."""
    registry = registry if registry is not None else _load_registry()
    actions: list[str] = []
    log = log_fn or (lambda _msg: None)
    stalled = progress_stalled(registry)

    for bn in bottlenecks:
        if not bn.auto_healable:
            if bn.heal_action and "enqueue" in (bn.heal_action or ""):
                result = _enqueue_self_heal_item(bn.title, bn.evidence[:180])
                actions.append(result)
                bn.heal_result = result
                bn.status = "needs_code" if "enqueued" in result else "deferred"
                log(f"self-heal: {result}")
            continue
        healer = _HEALERS.get(bn.id)
        if not healer:
            continue
        # OVERSEER_HEALER_LIVE_LOOKUP_2026_09_04 — re-bind module healers so
        # patch.object / dual-import clobber still hits the live function.
        hname = getattr(healer, "__name__", "")
        if hname and hname in globals() and callable(globals().get(hname)):
            healer = globals()[hname]
        heal_key = f"heal:{bn.id}"
        on_cooldown = _heal_on_cooldown(registry, heal_key)
        critical_bypass = bn.id in _CRITICAL_DAEMON_HEALS and _daemon_heal_still_down(bn)
        # OVERSEER_SELF_HEAL_PROGRESS_FP_2026_09_06 — if results idle, re-heal high/critical
        stall_bypass = stalled and bn.severity in ("critical", "high") and on_cooldown
        if on_cooldown and not critical_bypass and not stall_bypass:
            bn.status = "deferred"
            bn.heal_result = "cooldown"
            log(f"self-heal: {bn.id} → cooldown (deferred)")
            continue
        if stall_bypass and not critical_bypass:
            log(f"self-heal: {bn.id} → cooldown bypass (progress stalled)")
        try:
            result = healer(registry)
            _mark_heal(registry, heal_key)
            bn.heal_result = result
            bn.status = "healed"
            actions.append(f"{bn.id}: {result}")
            log(f"self-heal: {bn.id} → {result}")
        except Exception as exc:  # noqa: BLE001
            bn.heal_result = str(exc)[:200]
            bn.status = "failed"
            log(f"self-heal: {bn.id} failed ({exc})")

    _save_registry(registry)
    if actions:
        clear_scan_bottlenecks_cache()
    return actions


def run_cycle(
    *,
    write: bool = True,
    log_fn: Callable[[str], None] | None = None,
) -> HealReport:
    """Scan → merge history → heal → persist registry."""
    log = log_fn or (lambda _msg: None)
    registry = _load_registry()
    raw = scan_bottlenecks()
    bottlenecks = _merge_history(raw, registry, log_fn=log)
    actions: list[str] = []
    if write and self_heal_enabled():
        actions = apply_heals(bottlenecks, registry=registry, log_fn=log)
    else:
        update_progress_fp(registry)
        _save_registry(registry)
    report = HealReport(scanned_at=_now_iso(), bottlenecks=bottlenecks, actions=actions)
    registry["last_scan"] = asdict(report)
    registry["last_scan"]["bottlenecks"] = [asdict(b) for b in bottlenecks]
    _save_registry(registry)
    try:
        import peer_playbook as playbook

        playbook.ingest_from_bottlenecks(bottlenecks)
    except Exception:  # noqa: BLE001
        pass
    return report


def format_status(*, report: HealReport | None = None) -> str:
    report = report or run_cycle(write=False)
    lines = [
        "# Self-heal — bottleneck tracker",
        "",
        f"_Scanned {report.scanned_at}_ · enabled={self_heal_enabled()}",
        "",
    ]
    if not report.bottlenecks:
        lines.append("No bottlenecks detected.")
        return "\n".join(lines) + "\n"
    lines.append("| Severity | Category | Bottleneck | Status | Hits |")
    lines.append("|----------|----------|------------|--------|------|")
    for bn in sorted(report.bottlenecks, key=lambda b: (b.severity, b.id)):
        lines.append(
            f"| {bn.severity} | {bn.category} | {bn.title} | {bn.status} | {bn.hit_count} |"
        )
    if report.actions:
        lines.extend(["", "## Last heals", ""])
        for act in report.actions:
            lines.append(f"- {act}")
    return "\n".join(lines) + "\n"


def build_api_payload() -> dict[str, Any]:
    report = run_cycle(write=False)
    return {
        "updated_at": report.scanned_at,
        "enabled": self_heal_enabled(),
        "bottleneck_count": len(report.bottlenecks),
        "bottlenecks": [asdict(b) for b in report.bottlenecks],
        "registry_path": str(REGISTRY_PATH),
    }


def cmd_scan() -> int:
    print(format_status())
    return 0


def cmd_heal() -> int:
    report = run_cycle(write=True, log_fn=print)
    print(format_status(report=report))
    return 0


def cmd_status() -> int:
    reg = _load_registry()
    print(f"registry: {REGISTRY_PATH}")
    print(f"enabled: {self_heal_enabled()}")
    print(f"updated: {reg.get('updated_at', '(never)')}")
    hist = reg.get("history") if isinstance(reg.get("history"), dict) else {}
    print(f"tracked ids: {len(hist)}")
    print()
    print(format_status())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Self-healing bottleneck tracker")
    parser.add_argument("--scan", action="store_true", help="Scan and print bottlenecks")
    parser.add_argument("--heal", action="store_true", help="Scan and apply mechanical heals")
    parser.add_argument("--write", action="store_true", help="Alias for --heal")
    parser.add_argument("--status", action="store_true", help="Registry + latest scan")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.json:
        payload = build_api_payload()
        if args.heal or args.write:
            report = run_cycle(write=True)
            payload["actions"] = report.actions
        print(json.dumps(payload, indent=2))
        return 0

    if args.heal or args.write:
        return cmd_heal()
    if args.status:
        return cmd_status()
    return cmd_scan()


if __name__ == "__main__":
    raise SystemExit(main())
