"""Unified RAM+GPU resource poll — snapshot, mechanical fix, cursor-agent callback.

Runs on a short interval (default 15s). Each tick:
  1. Snapshot RAM footprint + GPU util
  2. Write ``resource-poll-latest.json`` (always) for agents to read
  3. Run ``dgx_resource_priority.handle_beep`` — mechanical fixes + agent dispatch
  4. On beep/transition: write ``resource-poll-alert.json`` + poke ``peer-turn.signal``

Usage:
  python3 scripts/dgx_resource_poll.py --once
  python3 scripts/dgx_resource_poll.py --forever
  python3 scripts/dgx_resource_poll.py --snapshot --json
  python3 scripts/dgx_resource_poll.py --force-agent
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import project_automation as auto

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import dgx_resource_priority as rp  # noqa: E402

LATEST_PATH = auto.CONFIG_DIR / "resource-poll-latest.json"
ALERT_PATH = auto.CONFIG_DIR / "resource-poll-alert.json"
LOG_PATH = auto.CONFIG_DIR / "resource-poll.log"
SIGNAL_PATH = auto.CONFIG_DIR / "peer-turn.signal"


def _cfg() -> dict[str, Any]:
    raw = auto.CFG.get("resource_poll")
    return raw if isinstance(raw, dict) else {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", True))


def interval_sec() -> float:
    try:
        return max(5.0, float(_cfg().get("interval_sec") or 15))
    except (TypeError, ValueError):
        return 15.0


def poke_peer_on_beep() -> bool:
    return bool(_cfg().get("poke_peer_on_beep", True))


def poke_peer_on_transition() -> bool:
    return bool(_cfg().get("poke_peer_on_transition", True))


def write_latest() -> bool:
    return bool(_cfg().get("write_latest", True))


def _log(msg: str, *, log_fn: Callable[[str], None] | None = None) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  resource-poll: {msg}"
    if log_fn:
        log_fn(line)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _poke_peer(*, reason: str) -> bool:
    try:
        SIGNAL_PATH.write_text(f"{time.time()}\nresource-poll:{reason}\n", encoding="utf-8")
        return True
    except OSError:
        return False


def _agent_commands() -> list[str]:
    return [
        "python3 scripts/dgx_resource_poll.py --snapshot --json",
        "python3 scripts/dgx_resource_priority.py --snapshot --json",
        "python3 scripts/dgx_ram_budget.py --priority-snapshot --json",
        "python3 scripts/dgx_gpu_events.py --snapshot --json",
    ]


def snapshot() -> dict[str, Any]:
    snap = rp.snapshot(force_live=True)  # compression: never echo poll-latest
    snap["poll_enabled"] = enabled()
    snap["interval_sec"] = interval_sec()
    return snap


def poll_once(
    *,
    log_fn: Callable[[str], None] = print,
    force_agent: bool = False,
    skip_agent: bool = False,
) -> dict[str, Any]:
    """One poll tick — snapshot, persist, handle beep, optional peer poke."""
    try:
        import dgx_ram_budget as budget

        # OVERSEER_TRIM_ONE_CENSUS_2026_09_06 — one /proc walk (was 2× list inside trim).
        sc_pids, ut_pids = budget.classify_storm_worker_pids()
        budget.trim_self_check_storm(pids=sc_pids)
        budget.trim_unittest_storm(pids=ut_pids)
    except ImportError:
        pass

    snap = snapshot()
    report: dict[str, Any] = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "snapshot": snap,
    }

    if write_latest():
        _write_json(LATEST_PATH, snap)

    prev_alert: dict[str, Any] = {}
    try:
        if ALERT_PATH.is_file():
            prev_alert = json.loads(ALERT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        prev_alert = {}

    was_beeping = bool(prev_alert.get("beeping"))
    beep_report = rp.handle_beep(
        log_fn=lambda m: _log(m, log_fn=log_fn),
        force_agent=force_agent and not skip_agent,
    )
    report.update(beep_report)

    now_beeping = bool(beep_report.get("beeping"))
    transition = bool(beep_report.get("transition"))
    agent_dispatched = bool(beep_report.get("resource_fix_dispatched"))

    if was_beeping and not now_beeping:
        _write_json(
            ALERT_PATH,
            {
                "alert": False,
                "ts": report["ts"],
                "reason": "cleared",
                "beeping": False,
                "development_allowed": True,
                "note": "Resources green — development may resume",
            },
        )
        report["alert_cleared"] = True
        if poke_peer_on_transition() and _poke_peer(reason="cleared"):
            report["peer_poked"] = True
            _log("poke peer-turn.signal (green)", log_fn=log_fn)
    elif now_beeping or agent_dispatched or transition:
        alert = {
            "alert": now_beeping,
            "ts": report["ts"],
            "reason": "beeping"
            if now_beeping
            else ("agent_dispatched" if agent_dispatched else "transition"),
            "beeping": now_beeping,
            "development_allowed": beep_report.get("development_allowed"),
            "worst_mode": beep_report.get("worst_mode"),
            "transition": transition,
            "was_beeping": was_beeping,
            "ram": beep_report.get("ram") or {},
            "gpu": beep_report.get("gpu") or {},
            "agent_dispatched": agent_dispatched,
            "agent_commands": _agent_commands(),
            "note": "RAM/GPU infra priority — run agent_commands and fix resources before development",
        }
        _write_json(ALERT_PATH, alert)
        report["alert_written"] = True

        if now_beeping and not was_beeping and poke_peer_on_beep() and _poke_peer(reason="beep"):
            report["peer_poked"] = True
            _log("poke peer-turn.signal (beep start)", log_fn=log_fn)
        elif transition and poke_peer_on_transition() and _poke_peer(reason="transition"):
            report["peer_poked"] = True
            _log(f"poke peer-turn.signal (transition → {beep_report.get('worst_mode')})", log_fn=log_fn)

    ram = snap.get("ram") or {}
    gpu = snap.get("gpu") or {}
    _log(
        f"tick RAM `{ram.get('mode')}` {ram.get('footprint_gb', '?')}GB · "
        f"GPU `{gpu.get('mode')}` {gpu.get('gpu_util_pct', '?')}% · "
        f"beeping={now_beeping} dev={beep_report.get('development_allowed')}",
        log_fn=log_fn,
    )
    return report


def run_forever(*, log_fn: Callable[[str], None] = print) -> None:
    _log(f"forever interval={interval_sec():.0f}s", log_fn=log_fn)
    while True:
        try:
            poll_once(log_fn=log_fn)
        except Exception as exc:  # noqa: BLE001
            _log(f"tick error — {exc}", log_fn=log_fn)
        time.sleep(interval_sec())


def main() -> int:
    parser = argparse.ArgumentParser(description="DGX RAM+GPU resource poll — agent callback loop")
    parser.add_argument("--once", action="store_true", help="Run one poll tick")
    parser.add_argument("--forever", action="store_true", help="Poll forever (daemon)")
    parser.add_argument("--snapshot", action="store_true", help="Print combined snapshot JSON")
    parser.add_argument("--force-agent", action="store_true", help="Dispatch cursor-agent even if cooldown")
    parser.add_argument("--skip-agent", action="store_true", help="Mechanical only — no cursor-agent")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.snapshot and not (args.once or args.forever or args.force_agent):
        payload = snapshot()
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            ram = payload.get("ram") or {}
            gpu = payload.get("gpu") or {}
            print(
                f"resource: beeping={payload.get('beeping')} "
                f"RAM {ram.get('mode')} {ram.get('footprint_gb', '?')}GB "
                f"GPU {gpu.get('mode')} {gpu.get('gpu_util_pct', '?')}%"
            )
        return 0

    if args.forever:
        if not enabled():
            print("resource_poll disabled in config", file=sys.stderr)
            return 0
        run_forever(log_fn=lambda m: None if args.json else print(m))
        return 0

    report = poll_once(
        log_fn=lambda m: None if args.json else print(m),
        force_agent=args.force_agent,
        skip_agent=args.skip_agent,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    return 1 if report.get("beeping") and not args.skip_agent else 0


if __name__ == "__main__":
    raise SystemExit(main())
