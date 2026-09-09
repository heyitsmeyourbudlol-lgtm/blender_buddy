#!/usr/bin/env python3
"""Watch NVIDIA DGX Spark — health, heal, RAM overload guard."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

DEFAULT_SERVICES = (
    "peer-loop",
    "improve-loop",
    "comms-improve-loop",
    "factory-fanout",
    "factory-sprint",
    "dgx-ram-accel",
    "dgx-ram-guard",
    "knowledge-indexer",
    "dashboard",
)
MAC_DAEMONS = (
    "com.togi.automation-peer-loop",
    "com.togi.automation-improve-loop",
    "com.togi.automation-oversight-loop",
    "com.togi.automation-repo-research-loop",
    "com.togi.automation-hub-peer-loop",
    "com.togi.automation-hub-peer-loop-fallback",
    "com.togi.automation-hub-improve-loop",
    "com.togi.automation-hub-improve-loop-fallback",
    "com.togi.automation-hub-comms-improve-loop",
    "com.togi.automation-hub-dashboard",
    "com.togi.automation-hub-repo-research-loop",
    "com.togi.automation-hub-oversight-loop",
    "com.togi.ram-peer-loop",
)
# Only stop true dual-brain / park agents on Mac. Hub peer+improve must keep running
# locally — dgx_watch was bootout-looping them every interval (~30s → exit -15 unload).
# Hub oversight is always rogue on Mac when config_namespace=automation (stale twin).
ROGUE_MAC_DAEMONS = (
    "com.togi.ram-peer-loop",
    "com.togi.automation-hub-oversight-loop",
)
# When Mac is offloaded to CLEAN (dgx_mac_offload.sh), keep these stopped locally.
OFFLOAD_ROGUE_MAC_DAEMONS = MAC_DAEMONS + (
    "com.togi.automation-hub-oversight-loop",
)
# Mac-local UI — keep even when peer/improve run on CLEAN. dgx_watch was
# bootout+disable looping the dashboard every interval under mac-offloaded.
MAC_KEEP_LOCAL = (
    "com.togi.automation-hub-dashboard",
)
OFFLOAD_MARKER = Path.home() / ".config" / "automation-hub" / "mac-offloaded"


def mac_offloaded() -> bool:
    """True when dgx_mac_offload left a marker (Mac loops run on CLEAN)."""
    return OFFLOAD_MARKER.is_file()


def rogue_mac_targets() -> tuple[str, ...]:
    """Bootout candidates minus disk-live peer/improve/oversight labels.

    If mac-offloaded marker is present, treat all transferable Mac automation
    LaunchAgents as rogue so heal/watch cannot revive a dual-brain.
    Dashboard stays on Mac (local :8765 UI) — never bootout/disable it.
    """
    keep = set(MAC_KEEP_LOCAL)
    if mac_offloaded():
        return tuple(
            label
            for label in dict.fromkeys(OFFLOAD_ROGUE_MAC_DAEMONS)
            if label not in keep
        )
    skip: set[str] = set(keep)
    try:
        import peer_self_heal as heal

        skip.update(
            {
                heal._live_peer_label(),
                heal._live_improve_label(),
                heal._live_oversight_label(),
            }
        )
    except Exception:  # noqa: BLE001
        pass
    return tuple(label for label in ROGUE_MAC_DAEMONS if label not in skip)

# Remote heal — env: MIN_AVAIL_GB CRIT_AVAIL_GB MAX_USED_GB UNITTEST_CAP MAX_AGENTS BUDGET_PY
_REMOTE_RAM_GUARD = r"""
set -euo pipefail
actions=()
killed_unittest=0
killed_agents=0
restarted_peer=0
BUDGET="${BUDGET_PY:-$HOME/Automation/scripts/dgx_ram_budget.py}"

mem_avail_kb=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
mem_total_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
used_kb=$((mem_total_kb - mem_avail_kb))

max_used_kb=0
if [ "${MAX_USED_GB:-0}" != "0" ]; then
  max_used_kb=$(awk -v g="${MAX_USED_GB}" 'BEGIN{printf "%.0f", g*1024*1024}')
fi
min_kb=$(awk -v g="${MIN_AVAIL_GB:-12}" 'BEGIN{printf "%.0f", g*1024*1024}')
crit_kb=$(awk -v g="${CRIT_AVAIL_GB:-6}" 'BEGIN{printf "%.0f", g*1024*1024}')
over_budget=0
if [ "$max_used_kb" -gt 0 ] && [ "$used_kb" -gt "$max_used_kb" ]; then
  over_budget=1
fi

if [ -f "$BUDGET" ]; then
  unittest_n=$(python3 "$BUDGET" --unittest-count 2>/dev/null || echo "0")
else
  unittest_n=$(pgrep -af '[pP]ython.* -m unittest' 2>/dev/null | grep -vi cursor-agent | wc -l | tr -d ' ')
fi
if [ "${unittest_n:-0}" -gt "${UNITTEST_CAP:-20}" ]; then
  if [ -f "$BUDGET" ]; then
    python3 "$BUDGET" --trim-unittest-storm 2>/dev/null || true
  else
    pgrep -af '[pP]ython.* -m unittest' 2>/dev/null | grep -vi cursor-agent | awk '{print $1}' | xargs -r kill -9 2>/dev/null || true
  fi
  killed_unittest=$((unittest_n - UNITTEST_CAP))
  actions+=("killed_unittest")
fi

agent_pids=$(pgrep -af 'cursor-agent' 2>/dev/null | grep -E '(^| )-p( |$)' | grep -v worker | awk '{print $1}' || true)
agent_n=0
if [ -n "$agent_pids" ]; then
  agent_n=$(echo "$agent_pids" | wc -l | tr -d ' ')
fi
if [ "${agent_n:-0}" -gt "${MAX_AGENTS:-8}" ] && { [ "$mem_avail_kb" -lt "$min_kb" ] || [ "$over_budget" -eq 1 ]; }; then
  echo "$agent_pids" | tail -n +$((MAX_AGENTS + 1)) | xargs -r kill -9 2>/dev/null || true
  killed_agents=$((agent_n - MAX_AGENTS))
  actions+=("trimmed_agents")
fi

mem_avail_kb=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
used_kb=$((mem_total_kb - mem_avail_kb))
if [ "$max_used_kb" -gt 0 ] && [ "$used_kb" -gt "$max_used_kb" ]; then
  over_budget=1
else
  over_budget=0
fi

# OVERSEER_DGX_WATCH_RESTART_COOLDOWN_2026_09_06 — prefer trim before restart;
# never mark restarted_peer=1 on `systemctl … || true` (false success thrash).
# OVERSEER_NON_NOOP_DAY_ROLLUP_2026_09_07 — do not bounce healthy peer-loop for RAM
# (SIGUSR1/restart flaps wipe cycle ring + stall T10-04 day rollup); trim only.
if [ "$mem_avail_kb" -lt "$crit_kb" ] || [ "$over_budget" -eq 1 ]; then
  actions+=("trim_before_restart")
  if [ -f "$BUDGET" ]; then
    python3 "$BUDGET" --trim-unittest-storm 2>/dev/null || true
  else
    pgrep -af '[pP]ython.* -m unittest' 2>/dev/null | grep -vi cursor-agent | awk '{print $1}' | xargs -r kill -9 2>/dev/null || true
  fi
  pgrep -af 'cursor-agent' 2>/dev/null | grep -E '(^| )-p( |$)' | grep -v worker | awk '{print $1}' | xargs -r kill -9 2>/dev/null || true
  mem_avail_kb=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
  used_kb=$((mem_total_kb - mem_avail_kb))
  if [ "$max_used_kb" -gt 0 ] && [ "$used_kb" -gt "$max_used_kb" ]; then
    over_budget=1
  else
    over_budget=0
  fi
fi

if [ "$mem_avail_kb" -lt "$crit_kb" ] || [ "$over_budget" -eq 1 ]; then
  cooldown_sec="${PEER_RESTART_COOLDOWN_SEC:-3600}"
  cooldown_file="${XDG_RUNTIME_DIR:-/tmp}/peer-loop-ram-restart.ts"
  now_ts=$(date +%s)
  skip_restart=0
  if systemctl --user is-active --quiet peer-loop.service 2>/dev/null; then
    skip_restart=1
    actions+=("skip_restart_peer_active_anti_flap")
  fi
  if [ -f "$cooldown_file" ]; then
    last_ts=$(cat "$cooldown_file" 2>/dev/null || echo 0)
    case "$last_ts" in
      ''|*[!0-9]*) last_ts=0 ;;
    esac
    if [ $((now_ts - last_ts)) -lt "$cooldown_sec" ]; then
      skip_restart=1
      actions+=("skip_restart_cooldown")
    fi
  fi
  if [ "$skip_restart" -eq 0 ]; then
    if systemctl --user restart peer-loop.service 2>/dev/null; then
      restarted_peer=1
      echo "$now_ts" >"$cooldown_file" 2>/dev/null || true
      actions+=("restarted_peer_loop")
    else
      actions+=("restart_peer_failed")
    fi
  fi
  sleep 2
  if [ -f "$BUDGET" ]; then
    python3 "$BUDGET" --trim-unittest-storm 2>/dev/null || true
  else
    pgrep -af '[pP]ython.* -m unittest' 2>/dev/null | grep -vi cursor-agent | awk '{print $1}' | xargs -r kill -9 2>/dev/null || true
  fi
  pgrep -af 'cursor-agent' 2>/dev/null | grep -E '(^| )-p( |$)' | grep -v worker | awk '{print $1}' | xargs -r kill -9 2>/dev/null || true
  mem_avail_kb=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
  used_kb=$((mem_total_kb - mem_avail_kb))
fi

avail_gb=$(awk -v k="$mem_avail_kb" 'BEGIN{printf "%.1f", k/1024/1024}')
used_gb=$(awk -v k="$used_kb" 'BEGIN{printf "%.1f", k/1024/1024}')
level=ok
if [ "$mem_avail_kb" -lt "$crit_kb" ] || [ "$over_budget" -eq 1 ]; then level=critical
elif [ "$mem_avail_kb" -lt "$min_kb" ]; then level=warn
fi

actions_csv=$(IFS=,; echo "${actions[*]:-}")
printf '{"avail_gb":%s,"used_gb":%s,"total_kb":%s,"avail_kb":%s,"level":"%s","unittest_before":%s,"agents_before":%s,"killed_unittest":%s,"killed_agents":%s,"restarted_peer":%s,"over_budget":%s,"actions":"%s"}\n' \
  "$avail_gb" "$used_gb" "$mem_total_kb" "$mem_avail_kb" "$level" "${unittest_n:-0}" "${agent_n:-0}" \
  "$killed_unittest" "$killed_agents" "$restarted_peer" "$over_budget" "$actions_csv"
"""


def _dgx_cfg() -> dict[str, Any]:
    """Nested dgx_host view with overlay clamps (never prefer stale 96/48)."""
    # Share overlay + ceiling clamp with the live RAM guard path.
    import dgx_ram_budget as budget

    return budget._dgx_cfg()


def dgx_primary() -> bool:
    return bool(_dgx_cfg().get("primary", True))


def ssh_host() -> str:
    remote = auto.CFG.get("agent_remote") or {}
    if isinstance(remote, dict) and remote.get("ssh_host"):
        return str(remote["ssh_host"])
    return str(_dgx_cfg().get("ssh_host") or "CLEAN")


def remote_root() -> str:
    remote = auto.CFG.get("agent_remote") or {}
    if isinstance(remote, dict) and remote.get("remote_root"):
        return str(remote["remote_root"])
    return str(_dgx_cfg().get("remote_root") or "/home/arnavrastogi")


def watch_interval_sec() -> int:
    try:
        return max(10, int(_dgx_cfg().get("watch_interval_sec") or 30))
    except (TypeError, ValueError):
        return 30


def mac_unittest_cap() -> int:
    try:
        return max(1, int(_dgx_cfg().get("mac_unittest_cap") or 15))
    except (TypeError, ValueError):
        return 15


_DGX_UNITTEST_CAP_CEILING = 20  # hard ceiling so stale nested 96 cannot pass through
_DGX_AGENTS_CAP_CEILING = 96


def dgx_unittest_cap() -> int:
    try:
        top = auto.CFG.get("dgx_unittest_cap")
        nested = _dgx_cfg().get("dgx_unittest_cap")
        if top is not None and nested is not None:
            return max(1, min(int(top), int(nested)))
        if top is not None:
            return max(1, int(top))
        return max(1, min(int(nested or _DGX_UNITTEST_CAP_CEILING), _DGX_UNITTEST_CAP_CEILING))
    except (TypeError, ValueError):
        return _DGX_UNITTEST_CAP_CEILING


def dgx_max_cursor_agents() -> int:
    try:
        peers = int(auto.max_parallel_agent_procs())
        nested = _dgx_cfg().get("dgx_max_cursor_agents")
        if nested is not None:
            return max(1, min(int(nested), peers, _DGX_AGENTS_CAP_CEILING))
        return max(1, min(peers, _DGX_AGENTS_CAP_CEILING))
    except (TypeError, ValueError):
        return _DGX_AGENTS_CAP_CEILING


def ram_min_avail_gb() -> float:
    try:
        return float(_dgx_cfg().get("ram_min_avail_gb") or 12)
    except (TypeError, ValueError):
        return 12.0


def ram_critical_avail_gb() -> float:
    try:
        return float(_dgx_cfg().get("ram_critical_avail_gb") or 6)
    except (TypeError, ValueError):
        return 6.0


def ram_max_used_gb() -> float | None:
    try:
        raw = _dgx_cfg().get("ram_max_used_gb")
        if raw is None:
            return None
        return max(1.0, float(raw))
    except (TypeError, ValueError):
        return None


def _effective_ram_thresholds(total_gb: float) -> tuple[float, float]:
    import dgx_ram_budget as budget

    return budget.effective_ram_thresholds(total_gb)


def heal_ram_enabled() -> bool:
    return bool(_dgx_cfg().get("heal_ram", True))


def heal_services_enabled() -> bool:
    return bool(_dgx_cfg().get("heal_services", True))


def status_path() -> Path:
    ns = str(auto.CFG.get("config_namespace") or "automation-hub")
    return Path.home() / ".config" / ns / "dgx-watch.json"


def log_path() -> Path:
    return status_path().with_suffix(".log")


def _log(msg: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp}  {msg}"
    print(line)
    log_path().parent.mkdir(parents=True, exist_ok=True)
    with log_path().open("a") as fh:
        fh.write(line + "\n")


def _ssh(script: str, *, timeout: float = 60.0) -> tuple[int, str]:
    # CLEAN under RAM pressure can accept TCP but delay the SSH banner >12s.
    # Needle: OVERSEER_DGX_SSH_LONG_BANNER_2026_09_08
    try:
        proc = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=45",
                "-o",
                "ServerAliveInterval=10",
                "-o",
                "ServerAliveCountMax=3",
                ssh_host(),
                script,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    out = (proc.stdout or proc.stderr or "").strip()
    return proc.returncode, out


def _parse_remote_json(out: str) -> dict[str, Any] | None:
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
    return None


def fetch_remote_mem() -> dict[str, Any] | None:
    rc, out = _ssh(
        "awk '/^MemTotal:|^MemAvailable:/ {print $1,$2}' /proc/meminfo | tr '\\n' ' '",
        timeout=10.0,
    )
    if rc != 0:
        return None
    total_kb = avail_kb = 0
    for token in out.split():
        if token == "MemTotal:":
            continue
        if token == "MemAvailable:":
            continue
        try:
            val = int(token)
        except ValueError:
            continue
        if total_kb == 0:
            total_kb = val
        else:
            avail_kb = val
            break
    if total_kb <= 0:
        return None
    total_gb = total_kb / 1024 / 1024
    avail_gb = avail_kb / 1024 / 1024
    used_gb = max(0.0, total_gb - avail_gb)
    min_avail, crit_avail = _effective_ram_thresholds(total_gb)
    level = "ok"
    cap = ram_max_used_gb()
    if cap is not None and used_gb >= cap:
        level = "critical"
    elif avail_gb < crit_avail:
        level = "critical"
    elif avail_gb < min_avail:
        level = "warn"
    return {
        "avail_gb": round(avail_gb, 1),
        "used_gb": round(used_gb, 1),
        "total_gb": round(total_gb, 1),
        "avail_kb": avail_kb,
        "ram_max_used_gb": cap,
        "ram_min_avail_gb": min_avail,
        "level": level,
    }


def guard_dgx_ram(*, heal: bool = True) -> dict[str, Any]:
    """Check DGX RAM; heal immediately when below thresholds."""
    mem = fetch_remote_mem()
    if mem is None:
        return {"action": "unreachable"}

    result: dict[str, Any] = dict(mem)
    if mem["level"] == "ok":
        result["action"] = "ok"
        return result

    _log(
        f"dgx RAM {mem['level']}: {mem.get('used_gb', '?')}GB used / "
        f"{mem.get('ram_max_used_gb') or '∞'}GB cap, {mem['avail_gb']}GB free "
        f"(min {mem.get('ram_min_avail_gb', ram_min_avail_gb())}GB)"
    )

    if not heal or not heal_ram_enabled():
        result["action"] = "alert_only"
        return result

    min_avail, crit_avail = _effective_ram_thresholds(mem.get("total_gb") or 0)
    max_used = ram_max_used_gb() or 0
    try:
        cooldown = max(300, int(auto.CFG.get("peer_restart_cooldown_sec") or 3600))
    except (TypeError, ValueError):
        cooldown = 3600
    args = (
        f"MIN_AVAIL_GB={min_avail} "
        f"CRIT_AVAIL_GB={crit_avail} "
        f"MAX_USED_GB={max_used} "
        f"UNITTEST_CAP={dgx_unittest_cap()} "
        f"MAX_AGENTS={dgx_max_cursor_agents()} "
        f"PEER_RESTART_COOLDOWN_SEC={cooldown}"
    )
    script = f"{args} bash -s <<'EOS'\n{_REMOTE_RAM_GUARD}\nEOS"
    rc, out = _ssh(script, timeout=45.0)
    healed = _parse_remote_json(out)
    if healed:
        result.update(healed)
        actions = healed.get("actions") or ""
        if actions:
            _log(f"dgx RAM heal: {actions} — now {healed.get('avail_gb')}GB free")
            result["action"] = "healed"
        elif mem["level"] in ("warn", "critical"):
            result["action"] = "still_pressure"
        else:
            result["action"] = "ok"
    else:
        result["action"] = "heal_failed"
        result["heal_detail"] = out[-200:] if out else f"ssh rc={rc}"
        _log(f"dgx RAM heal failed — {result['heal_detail']}")

    return result


def count_mac_unittest() -> int:
    try:
        proc = subprocess.run(
            ["pgrep", "-lf", "unittest"],
            capture_output=True,
            text=True,
            timeout=8.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if proc.returncode != 0 or not proc.stdout:
        return 0
    return len([ln for ln in proc.stdout.splitlines() if ln.strip()])


def guard_mac_unittest_storm() -> dict[str, Any]:
    count = count_mac_unittest()
    cap = mac_unittest_cap()
    if count <= cap:
        return {"count": count, "action": "ok"}
    _log(f"mac guard: unittest storm ({count}>{cap}) — killing")
    subprocess.run(["pkill", "-9", "-f", "Python -m unittest"], check=False)
    time.sleep(1)
    after = count_mac_unittest()
    return {"count": count, "after": after, "action": "killed"}


def mac_daemon_check() -> list[str]:
    """Return running Mac LaunchAgents that conflict with the hub (dual-brain)."""
    running: list[str] = []
    try:
        proc = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
            timeout=8.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return running
    if proc.returncode != 0 or not proc.stdout:
        return running
    for label in rogue_mac_targets():
        for line in proc.stdout.splitlines():
            if label in line and not line.strip().startswith("-"):
                parts = line.split()
                if len(parts) >= 1 and parts[0] != "-":
                    running.append(label)
                    break
    return running


def stop_mac_daemons() -> list[str]:
    uid = os.getuid()
    stopped: list[str] = []
    for label in rogue_mac_targets():
        rc = subprocess.run(
            ["launchctl", "bootout", f"gui/{uid}/{label}"],
            capture_output=True,
            check=False,
        ).returncode
        if rc == 0:
            stopped.append(label)
            subprocess.run(
                ["launchctl", "disable", f"gui/{uid}/{label}"],
                capture_output=True,
                check=False,
            )
    if mac_offloaded():
        # Also kill nohup/direct script children (LaunchAgent bootout alone misses these).
        # OVERSEER_NO_HARDCODED_CURSOR_AGENT_PATH_2026_09_05 — portable basename;
        # never embed /Users/... (repo-research hardcoded_path probe).
        for pat in (
            "scripts/peer_loop.py",
            "scripts/automation_improve.py",
            "scripts/peer_oversight.py",
            "scripts/peer_repo_research.py",
            "scripts/peer_pen_test.py",
            "cursor-agent",
        ):
            rc = subprocess.run(["pkill", "-f", pat], capture_output=True, check=False).returncode
            if rc == 0:
                stopped.append(f"pkill:{pat}")
    return stopped


def remote_service_status() -> dict[str, str]:
    services = _dgx_cfg().get("services")
    names = tuple(services) if isinstance(services, list) and services else DEFAULT_SERVICES
    joined = " ".join(names)
    rc, out = _ssh(f"systemctl --user is-active {joined} 2>/dev/null")
    states: dict[str, str] = {}
    lines = out.splitlines()
    for i, name in enumerate(names):
        states[name] = lines[i].strip() if i < len(lines) else "unknown"
    states["_ssh_rc"] = str(rc)
    return states


def heal_remote_services() -> list[str]:
    services = _dgx_cfg().get("services")
    names = tuple(services) if isinstance(services, list) and services else DEFAULT_SERVICES
    healed: list[str] = []
    status = remote_service_status()
    for name in names:
        if status.get(name) == "active":
            continue
        _log(f"heal: restarting {name} on {ssh_host()}")
        _ssh(f"systemctl --user restart {name}.service")
        healed.append(name)
    return healed


def next_interval_sec(ram_report: dict[str, Any] | None) -> int:
    """Poll faster when DGX RAM is under pressure."""
    base = watch_interval_sec()
    if not ram_report:
        return base
    level = ram_report.get("level") or ram_report.get("action")
    if level in ("critical", "healed", "still_pressure", "heal_failed"):
        return 10
    if level == "warn":
        return 20
    return base


def run_watch(*, heal: bool = True) -> dict[str, Any]:
    report: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "host": ssh_host(),
        "primary": dgx_primary(),
    }

    rc, ping = _ssh("echo ok", timeout=55.0)
    report["ssh_ok"] = rc == 0 and ping == "ok"
    if not report["ssh_ok"]:
        report["ssh_detail"] = ping
        _log(f"WARN: ssh {ssh_host()} down — {ping}")
    else:
        report["dgx_ram"] = guard_dgx_ram(heal=heal)
        mem = report["dgx_ram"]
        if mem.get("action") == "ok":
            _log(f"dgx mem ok: {mem.get('avail_gb')}GB free / {mem.get('total_gb')}GB")
        report["services"] = remote_service_status()
        # Under critical RAM / failed heal, restarting every unit worsens OOM and
        # can wedge sshd (seen 2026-09-08: heal storm → SSH banner timeout).
        # Needle: OVERSEER_DGX_WATCH_SKIP_RESTART_ON_CRITICAL_2026_09_08
        ram_action = str((report.get("dgx_ram") or {}).get("action") or "")
        ram_level = str((report.get("dgx_ram") or {}).get("level") or "")
        skip_svc = ram_level == "critical" or ram_action in {
            "heal_failed",
            "still_pressure",
            "unreachable",
        }
        if heal and heal_services_enabled() and not skip_svc:
            bad = [k for k, v in report["services"].items() if not k.startswith("_") and v != "active"]
            if bad:
                report["healed"] = heal_remote_services()
        elif skip_svc and heal and heal_services_enabled():
            report["healed_skipped"] = f"ram_{ram_level or ram_action}"
            _log(f"heal: skip service restarts ({report['healed_skipped']})")

    report["mac_unittest"] = guard_mac_unittest_storm()
    rogue = mac_daemon_check()
    report["mac_daemons_running"] = rogue
    report["mac_offloaded"] = mac_offloaded()
    if heal and (rogue or mac_offloaded()):
        report["mac_daemons_stopped"] = stop_mac_daemons()
        if report["mac_daemons_stopped"]:
            _log(f"mac guard: stopped local daemons {report['mac_daemons_stopped']}")

    report["next_interval_sec"] = next_interval_sec(report.get("dgx_ram") if report.get("ssh_ok") else None)

    status_path().parent.mkdir(parents=True, exist_ok=True)
    status_path().write_text(json.dumps(report, indent=2) + "\n")
    return report


def cmd_status() -> int:
    path = status_path()
    if path.is_file():
        print(path.read_text())
        return 0
    report = run_watch(heal=False)
    print(json.dumps(report, indent=2))
    return 0 if report.get("ssh_ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch DGX Spark automation host")
    parser.add_argument("--status", action="store_true", help="Print last watch report")
    parser.add_argument("--no-heal", action="store_true", help="Report only; do not heal")
    parser.add_argument("--forever", action="store_true", help="Loop watch (for LaunchAgent)")
    args = parser.parse_args()

    if args.status:
        return cmd_status()

    if args.forever:
        _log(f"dgx watch forever — {ssh_host()} (RAM guard on)")
        while True:
            interval = watch_interval_sec()
            try:
                report = run_watch(heal=not args.no_heal)
                interval = int(report.get("next_interval_sec") or interval)
            except Exception as exc:  # noqa: BLE001
                _log(f"watch error: {exc}")
                interval = 15
            time.sleep(interval)
        return 0

    report = run_watch(heal=not args.no_heal)
    return 0 if report.get("ssh_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
