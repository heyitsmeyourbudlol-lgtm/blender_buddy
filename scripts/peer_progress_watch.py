#!/usr/bin/env python3
"""Forever progress watchdog — time + result based kit self-heal.

Needle: OVERSEER_PEER_PROGRESS_WATCH_2026_09_06

If the kit progress fingerprint does not move within STALL_SEC, run a full
``peer_self_heal.run_cycle`` (mechanical heals) and poke the peer loop.
Not rule theater: wall-clock idle on real results.

    systemd: peer-progress-watch.service (CLEAN)
    CLI:     python3 scripts/peer_progress_watch.py --forever
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
os.chdir(ROOT)

STATE_PATH = Path.home() / ".config" / "automation" / "peer-progress-watch.json"
# Prefer live hub ns when present
_HUB_STATE = Path.home() / ".config" / "automation-hub" / "peer-progress-watch.json"
NEEDLE = "OVERSEER_PEER_PROGRESS_WATCH_2026_09_06"


def _state_path() -> Path:
    hub = Path.home() / ".config" / "automation-hub"
    if hub.is_dir():
        return hub / "peer-progress-watch.json"
    return STATE_PATH


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}", flush=True)


def load_state() -> dict:
    path = _state_path()
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def tick(*, stall_sec: float, write: bool) -> dict:
    import peer_self_heal as heal

    state = load_state()
    registry = heal._load_registry()
    snap, moved, idle = heal.update_progress_fp(registry)
    heal._save_registry(registry)

    now = time.time()
    if moved:
        log(
            f"{NEEDLE} progress MOVED sha={snap.get('core_sha')} "
            f"open={snap.get('open_n')} verify={snap.get('verify_ok')} "
            f"agents={snap.get('agents')}"
        )
        state["last_move_ts"] = now
        state["last_sha"] = snap.get("core_sha")
        state["last_snap"] = snap
        state["stall_heals"] = int(state.get("stall_heals") or 0)
        save_state(state)
        return state

    idle_eff = idle if idle > 0 else now - float(state.get("last_move_ts") or now)
    state["idle_sec"] = idle_eff
    state["last_snap"] = snap

    soft = not snap.get("peer_up")
    if idle_eff >= stall_sec or (soft and idle_eff >= min(90.0, stall_sec / 2)):
        last_heal = float(state.get("last_heal_ts") or 0)
        if now - last_heal < min(stall_sec, 120):
            log(f"{NEEDLE} stall idle={idle_eff:.0f}s but heal cooldown")
            save_state(state)
            return state
        log(f"{NEEDLE} STALL idle={idle_eff:.0f}s — run_cycle (write={write})")
        if write:
            report = heal.run_cycle(write=True, log_fn=log)
            n = len(report.bottlenecks)
            a = len(report.actions)
            log(f"{NEEDLE} healed bottlenecks={n} actions={a}")
            try:
                sig = heal.SIGNAL_PATH
                sig.parent.mkdir(parents=True, exist_ok=True)
                sig.write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ") + "\n", encoding="utf-8")
            except OSError:
                pass
        state["last_heal_ts"] = now
        state["stall_heals"] = int(state.get("stall_heals") or 0) + 1
    else:
        log(
            f"{NEEDLE} ok idle={idle_eff:.0f}s/{stall_sec:.0f}s "
            f"sha={snap.get('core_sha')} agents={snap.get('agents')}"
        )
    save_state(state)
    return state


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--forever", action="store_true")
    ap.add_argument(
        "--stall-sec",
        type=float,
        default=float(os.environ.get("PROGRESS_STALL_SEC", "180")),
    )
    ap.add_argument(
        "--poll-sec",
        type=float,
        default=float(os.environ.get("PROGRESS_POLL_SEC", "45")),
    )
    ap.add_argument("--dry-run", action="store_true", help="scan only — no heal write")
    args = ap.parse_args()

    log(f"{NEEDLE} stall_sec={args.stall_sec} poll_sec={args.poll_sec}")
    write = not args.dry_run
    tick(stall_sec=args.stall_sec, write=write)
    if args.once and not args.forever:
        return 0
    while True:
        time.sleep(max(15.0, args.poll_sec))
        tick(stall_sec=args.stall_sec, write=write)


if __name__ == "__main__":
    raise SystemExit(main())
