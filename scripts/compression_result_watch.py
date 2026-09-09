#!/usr/bin/env python3
"""Time + result watchdog — if compression progress stalls, fix it (free desktop).

Needle: OVERSEER_COMPRESSION_RESULT_WATCH_2026_09_06

Not rule-theater: wall-clock + fingerprint of *results*.
If the fingerprint does not move within ``STALL_SEC``, heal mechanically then
dispatch a free cursor-agent to unblock the current gate.

Always-on via systemd ``compression-result-watch.service``.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ART = ROOT / "notes" / "compression_artifacts"
STATE_PATH = Path.home() / ".config" / "automation" / "compression-result-watch.json"
NEEDLE = "OVERSEER_COMPRESSION_RESULT_WATCH_2026_09_06"

sys.path.insert(0, str(SCRIPTS))
os.chdir(ROOT)
os.environ["AUTOMATION_FORCE_FREE_DESKTOP"] = "1"
os.environ["PEER_LOOP_PAID_API"] = "0"


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}", flush=True)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def cursor_count() -> int:
    try:
        out = subprocess.check_output(
            ["ps", "-u", Path.home().name, "-o", "args="],
            text=True,
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return 0
    return sum(1 for line in out.splitlines() if "cursor-agent" in line)


def rung0_alive() -> bool:
    try:
        out = subprocess.check_output(
            ["ps", "-u", Path.home().name, "-o", "args="],
            text=True,
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    for line in out.splitlines():
        if "compression_train_rung0.py" not in line:
            continue
        if "python" in line and "bash -c" not in line and "pgrep" not in line:
            return True
    return False


def ensure_rung0() -> None:
    if rung0_alive():
        return
    rung = SCRIPTS / "compression_train_rung0.py"
    if not rung.is_file():
        log(f"missing {rung}")
        return
    if not (ART / "train_unlock.json").is_file():
        return
    env = os.environ.copy()
    env["COMPRESSION_TRAIN_UNLOCKED"] = "1"
    env["COMPRESSION_HOT_DTYPE"] = "NVFP4"
    env["COMPRESSION_MIN_RAM"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    log_path = Path.home() / ".config" / "automation" / "compression-rung0.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n# {NEEDLE} relaunch {time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
        fh.flush()
        proc = subprocess.Popen(
            [sys.executable, "-u", str(rung), "--train", "--min-ram"],
            cwd=str(ROOT),
            env=env,
            stdout=fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    log(f"relaunched rung0 pid={proc.pid}")


def service_active(name: str) -> bool:
    return subprocess.getoutput(f"systemctl --user is-active {name}").strip() == "active"


def kill_ram_hogs() -> list[str]:
    """SIGKILL true ballast only — reuse peer_self_heal pressure gate.

    Needle: OVERSEER_RAM_BALLAST_GPU_COMPUTE_PRESSURE_2026_09_07 — do not kill
    productive ``dgx_gpu_compute`` (mamba-2.8b ~3–8GB) while MemAvailable is healthy.
    """
    try:
        import peer_self_heal as heal

        msg = heal._heal_ram_ballast({})
        # Parse "killed N ballast (pid:MB, ...)" → list for callers/logs.
        if msg.startswith("killed ") and "(" in msg:
            inner = msg.split("(", 1)[1].split(")", 1)[0]
            return [p.strip() for p in inner.split(",") if p.strip()]
        return []
    except Exception:  # noqa: BLE001
        # Fallback: poll/fill only at 200MB; never touch gpu_compute here.
        killed: list[str] = []
        needles = ("dgx_resource_poll.py", "dgx_ram_fill.py")
        try:
            out = subprocess.check_output(
                ["ps", "-u", Path.home().name, "-o", "pid=,rss=,args="],
                text=True,
                errors="replace",
            )
        except (OSError, subprocess.CalledProcessError):
            return killed
        for line in out.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) < 3:
                continue
            pid_s, rss_s, args = parts[0], parts[1], parts[2]
            if not any(n in args for n in needles):
                continue
            try:
                rss = int(rss_s)
            except ValueError:
                continue
            if rss < 200_000:
                continue
            try:
                os.kill(int(pid_s), signal.SIGKILL)
                killed.append(f"{pid_s}:{rss // 1024}MB")
            except (ProcessLookupError, ValueError, PermissionError):
                pass
        return killed


def ensure_free_auth() -> None:
    hub = Path.home() / ".config" / "automation-hub"
    suffix = "env"
    paid = hub / f"cursor-agent.{suffix}"
    park = hub / f"cursor-agent.{suffix}.paid-disabled"
    if paid.is_file():
        try:
            paid.replace(park)
            log("parked API-key file — free desktop only")
        except OSError as exc:
            log(f"park key failed: {exc}")


def result_fingerprint() -> dict[str, Any]:
    """Capture what 'results moving' means for this sidequest."""
    ready = _read(ROOT / "notes" / "COMPRESSION_TRAIN_READY.md")
    recipe = _read(ROOT / "notes" / "COMPRESSION_TRAIN_RECIPE.md")
    wq = _read(ROOT / "notes" / "WORK_QUEUE.md")
    ctx = _read(ROOT / "scripts" / "self_improve_context.md")

    open_comp = [
        ln.strip()
        for ln in wq.splitlines()
        if ln.strip().startswith("- [ ]") and "compression" in ln.lower()
    ]
    done_comp = [
        ln.strip()
        for ln in wq.splitlines()
        if ln.strip().startswith("- [x]") and "compression" in ln.lower()
    ]

    arts: dict[str, Any] = {}
    for name in (
        "t4_scale_result.json",
        "train_unlock.json",
        "rung0_model_skeleton.json",
        "rung0_heartbeat.json",
        "stress_bars.json",
        "gpu_accel_status.json",
    ):
        p = ART / name
        if p.is_file():
            arts[name] = {"mtime": int(p.stat().st_mtime), "sha": _sha(_read(p)[:4000])}
        else:
            arts[name] = None

    recipe_locked = (
        "**Status:** **LOCKED**" in recipe
        or "Status:** **LOCKED" in recipe
        or "recipe_locked=true" in recipe
        or "OVERSEER_COMPRESSION_TRAIN_UNLOCK" in recipe
    )
    t4_done = "OVERSEER_COMPRESSION_T4_SCALE" in ready or "T4 quality/scale path | **GO**" in ready
    train_unlocked = (ART / "train_unlock.json").is_file()
    stress = {}
    sp = ART / "stress_bars.json"
    if sp.is_file():
        try:
            stress = json.loads(sp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            stress = {}

    hb = ART / "rung0_heartbeat.json"
    hb_age = None
    if hb.is_file():
        hb_age = int(time.time() - hb.stat().st_mtime)
    # Minute bucket so a live heartbeat moves the core digest every ~60s
    hb_bucket = None if hb_age is None else int(hb.stat().st_mtime) // 60

    snap = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "t4_done": t4_done,
        "recipe_locked": recipe_locked,
        "train_unlocked": train_unlocked,
        "rung0_alive": rung0_alive(),
        "hb_age_sec": hb_age,
        "hb_bucket": hb_bucket,
        "integrate_allowed": bool(stress.get("integrate_allowed")),
        "stress_status": stress.get("status"),
        "open_compression": len(open_comp),
        "done_compression": len(done_comp),
        "open_sha": _sha("\n".join(open_comp[:20])),
        "recipe_sha": _sha(recipe[:8000]),
        "ready_sha": _sha(ready[:8000]),
        "ctx_sha": _sha(ctx[:4000]),
        "arts": arts,
        "agents": cursor_count(),
        "svc": {
            "peer-loop": service_active("peer-loop"),
            "keep-alive": service_active("compression-keep-alive"),
            "auto-train": service_active("compression-auto-train"),
            "gpu-worker": service_active("compression-gpu-worker"),
            "result-watch": True,
        },
    }
    # Single digest for stall compare (exclude ts + volatile agent count noise)
    core = {
        k: snap[k]
        for k in (
            "t4_done",
            "recipe_locked",
            "train_unlocked",
            "integrate_allowed",
            "stress_status",
            "open_sha",
            "recipe_sha",
            "ready_sha",
            "arts",
            "hb_bucket",
            "rung0_alive",
        )
    }
    snap["core_sha"] = _sha(json.dumps(core, sort_keys=True))
    return snap


def load_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    ART.mkdir(parents=True, exist_ok=True)
    (ART / "result_watch_status.json").write_text(
        json.dumps({"needle": NEEDLE, **state}, indent=2) + "\n", encoding="utf-8"
    )


def restart_services() -> None:
    """Restart compression fleet. Do not bounce healthy peer-loop (flap eater)."""
    peer_up = service_active("peer-loop")
    for unit in (
        "compression-keep-alive",
        "compression-auto-train",
        "compression-gpu-worker",
    ):
        subprocess.call(
            ["systemctl", "--user", "restart", f"{unit}.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.call(
            ["systemctl", "--user", "enable", "--now", f"{unit}.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    # Only restart peer-loop when it is actually down (or zero agents + dead keep-alive).
    if not peer_up:
        subprocess.call(
            ["systemctl", "--user", "restart", "peer-loop.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.call(
            ["systemctl", "--user", "enable", "--now", "peer-loop.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log("restarted dead peer-loop")
    else:
        log("peer-loop healthy — skip restart (anti-flap)")


def queue_unblock_fuel(snap: dict[str, Any]) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M")
    if not snap.get("recipe_locked"):
        item = (
            f"- [ ] [compression-train] WATCHDOG: freeze COMPRESSION_TRAIN_RECIPE "
            f"**Status:** **LOCKED** now ({ts}Z) {NEEDLE}"
        )
    elif not snap.get("train_unlocked"):
        item = (
            f"- [ ] [compression-train] WATCHDOG: recipe locked but unlock missing — "
            f"run compression_auto_train --start ({ts}Z) {NEEDLE}"
        )
    elif snap.get("stress_status") == "WAITING_FOR_FULL_TRAIN":
        item = (
            f"- [ ] [compression-train] WATCHDOG: advance full train / fill stress_bars "
            f"({ts}Z) {NEEDLE}"
        )
    else:
        item = (
            f"- [ ] [compression-train] WATCHDOG: results stalled — diagnose next gate "
            f"({ts}Z) {NEEDLE}"
        )
    for rel in ("notes/WORK_QUEUE.md", "scripts/self_improve_context.md"):
        path = ROOT / rel
        text = _read(path) if path.is_file() else "# queue\n"
        if NEEDLE in text and "WATCHDOG" in text and item.split("(")[0] in text:
            continue
        if not text.endswith("\n"):
            text += "\n"
        text += item + "\n"
        path.write_text(text, encoding="utf-8")
    # Wake peer loop
    sig = Path.home() / ".config" / "automation-hub" / "peer-turn.signal"
    try:
        sig.parent.mkdir(parents=True, exist_ok=True)
        sig.write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ") + "\n", encoding="utf-8")
    except OSError:
        pass


def dispatch_cursor_fix(snap: dict[str, Any]) -> None:
    """Free desktop cursor-agent: diagnose stall and land a concrete fix."""
    try:
        import peer_terminal as pt

        if not pt.force_free_desktop_auth():
            log("refusing dispatch — free lock off")
            return
    except Exception as exc:  # noqa: BLE001
        log(f"peer_terminal import: {exc}")
        return

    prompt = f"""{NEEDLE} — RESULT STALL FIX (desktop login $0 only — NEVER paid API).

Results fingerprint stuck. Current snapshot:
{json.dumps({k: snap[k] for k in ('t4_done','recipe_locked','train_unlocked','integrate_allowed','stress_status','open_compression','agents','svc','core_sha')}, indent=2)}

Do this now (minimal diffs):
1. If recipe_locked=false → edit notes/COMPRESSION_TRAIN_RECIPE.md to **Status:** **LOCKED** with frozen NVFP4/min-U/no-prune fields (honest).
2. Else if train not unlocked → run `python3 scripts/compression_auto_train.py --start` and fix failures.
3. Else advance train/stress_bars toward integrate_allowed.
4. Sync WORK_QUEUE ↔ self_improve_context.
5. Do not choose paid billing. Prefer DGX CLEAN paths.

Verify: unittest if code; leave a short note in COMPRESSION_TRAIN_READY Agent notes if useful.
"""
    try:
        import peer_terminal as pt

        rc, auth_fail = pt.run_cursor_agent(
            prompt,
            log_fn=log,
            paid_api=False,
            sync=False,
            timeout_sec=3600,
        )
        log(f"cursor-agent dispatch rc={rc} auth_fail={auth_fail} (async)")
    except Exception as exc:  # noqa: BLE001
        log(f"dispatch failed: {exc}")


def heal_stall(snap: dict[str, Any]) -> None:
    log(f"{NEEDLE} STALL — healing (core_sha={snap.get('core_sha')})")
    ensure_free_auth()
    killed = kill_ram_hogs()
    if killed:
        log(f"killed ballast {killed}")
    if snap.get("train_unlocked") and not snap.get("rung0_alive"):
        ensure_rung0()
    restart_services()
    # After service bounce, rung0 may need another kick
    time.sleep(2)
    if snap.get("train_unlocked"):
        ensure_rung0()
    queue_unblock_fuel(snap)
    # Small pause then agent
    time.sleep(3)
    if cursor_count() < 4:
        dispatch_cursor_fix(snap)
    else:
        log(f"agents already={cursor_count()} — skip extra dispatch; fuel+restart done")


def tick(state: dict[str, Any], *, stall_sec: float, poll_sec: float) -> dict[str, Any]:
    snap = result_fingerprint()
    now = time.time()
    last_sha = state.get("last_core_sha")
    last_move = float(state.get("last_move_ts") or now)
    if last_sha != snap["core_sha"]:
        log(
            f"results MOVED sha={snap['core_sha']} "
            f"t4={snap['t4_done']} lock={snap['recipe_locked']} "
            f"unlock={snap['train_unlocked']} rung0={snap['rung0_alive']} "
            f"agents={snap['agents']}"
        )
        state["last_core_sha"] = snap["core_sha"]
        state["last_move_ts"] = now
        state["last_snap"] = snap
        state["stall_heals"] = int(state.get("stall_heals") or 0)
        save_state(state)
        return state

    idle = now - last_move
    state["last_snap"] = snap
    state["idle_sec"] = idle
    # Immediate soft stalls: dead agents+keep-alive, dead auto-train after lock,
    # or unlocked train with no rung0 process / stale heartbeat
    soft = (snap["agents"] == 0 and not snap["svc"].get("keep-alive")) or (
        not snap["svc"].get("auto-train") and snap.get("recipe_locked")
    )
    if snap.get("train_unlocked") and not snap.get("rung0_alive"):
        soft = True
    hb_age = snap.get("hb_age_sec")
    if snap.get("train_unlocked") and hb_age is not None and hb_age > max(120.0, stall_sec / 2):
        soft = True
    if idle >= stall_sec or soft:
        # Cooldown between heals
        last_heal = float(state.get("last_heal_ts") or 0)
        if now - last_heal >= min(stall_sec, 300):
            heal_stall(snap)
            state["last_heal_ts"] = now
            state["stall_heals"] = int(state.get("stall_heals") or 0) + 1
            # After heal, do not reset last_move — only real result sha moves count
        else:
            log(f"stall idle={idle:.0f}s but heal cooldown")
    else:
        log(
            f"watch ok idle={idle:.0f}s/{stall_sec:.0f}s sha={snap['core_sha']} "
            f"agents={snap['agents']}"
        )
    save_state(state)
    return state


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--forever", action="store_true")
    ap.add_argument("--stall-sec", type=float, default=float(os.environ.get("WATCH_STALL_SEC", "600")))
    ap.add_argument("--poll-sec", type=float, default=float(os.environ.get("WATCH_POLL_SEC", "60")))
    ap.add_argument("--force-heal", action="store_true")
    args = ap.parse_args()

    log(f"{NEEDLE} stall_sec={args.stall_sec} poll_sec={args.poll_sec} FREE desktop only")
    ensure_free_auth()
    state = load_state()
    if args.force_heal:
        heal_stall(result_fingerprint())
        return 0

    state = tick(state, stall_sec=args.stall_sec, poll_sec=args.poll_sec)
    if args.once and not args.forever:
        return 0
    while True:
        time.sleep(max(15.0, args.poll_sec))
        state = tick(state, stall_sec=args.stall_sec, poll_sec=args.poll_sec)


if __name__ == "__main__":
    raise SystemExit(main())
