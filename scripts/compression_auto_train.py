#!/usr/bin/env python3
"""When compression research gates clear, instantly start the min-RAM model rung.

Needle: OVERSEER_COMPRESSION_AUTO_TRAIN_2026_09_05

Gates (all required):
  - T0–T3 probes green (unittests)
  - T4 marked Done/PASS/GO in COMPRESSION_TRAIN_READY.md
  - Recipe card Status LOCKED (not stub TRAIN-LOCKED-only)

Then:
  - Write train unlock artifact
  - Flip recipe to train_unlocked path
  - Launch rung-0 scaffold: shared NVFP4 body + LoRA, minimize U & RAM

Post-train (human policy OVERSEER_COMPRESSION_STRESS_THEN_INTEGRATE_2026_09_06):
  Full train → ALL stress bars PASS → only then workflow integrate.
  Unlock/start ≠ integrate.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ART = ROOT / "notes" / "compression_artifacts"
NEEDLE = "OVERSEER_COMPRESSION_AUTO_TRAIN_2026_09_05"
UNLOCK_NEEDLE = "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))
os.chdir(ROOT)


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}", flush=True)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def t_probes_green() -> bool:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name in (
        "tests.test_compression_t0_pack",
        "tests.test_compression_t1_share",
        "tests.test_compression_t2_svd",
        "tests.test_compression_t3_bitdistill",
    ):
        try:
            suite.addTests(loader.loadTestsFromName(name))
        except Exception as exc:  # noqa: BLE001
            log(f"probe load fail {name}: {exc}")
            return False
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    return result.wasSuccessful()


def t4_complete(ready_text: str) -> bool:
    markers = (
        "T4 | **Done",
        "T4 | **PASS",
        "T4 quality/scale path | **GO",
        "OVERSEER_COMPRESSION_T4_",
        "**T4** — **Done",
        "T4 scale rung | **Done",
        "T4 scale rung | **PASS",
        "OVERSEER_COMPRESSION_T4_SCALE_2026_09_06",
    )
    return any(m in ready_text for m in markers)


def recipe_locked(recipe_text: str) -> bool:
    if UNLOCK_NEEDLE in recipe_text and "train_unlocked=true" in recipe_text.replace(" ", ""):
        return True
    # Explicit lock line (peers must write this when freezing the card)
    if "**Status:** **LOCKED**" in recipe_text or "Status:** **LOCKED" in recipe_text:
        return True
    if "TRAIN_RECIPE_LOCKED" in recipe_text or "recipe_locked=true" in recipe_text:
        return True
    return False


def research_complete() -> bool:
    ready = _read(ROOT / "notes" / "COMPRESSION_TRAIN_READY.md")
    recipe = _read(ROOT / "notes" / "COMPRESSION_TRAIN_RECIPE.md")
    if not t4_complete(ready):
        return False
    if not recipe_locked(recipe):
        return False
    if not t_probes_green():
        log("T0–T3 unittest not green — hold train")
        return False
    return True


def write_unlock_artifact(*, reason: str) -> Path:
    ART.mkdir(parents=True, exist_ok=True)
    path = ART / "train_unlock.json"
    payload = {
        "needle": UNLOCK_NEEDLE,
        "auto_train_needle": NEEDLE,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "train_unlocked": True,
        "reason": reason,
        "north_star": {
            "logical_params": 1_000_000_000,
            "unique_target": 10_000_000,
            "S": 100,
            "hot_dtype": "NVFP4",
            "data_prune": False,
            "objective": "max efficiency / min resident RAM for unique store",
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def stamp_recipe_unlocked() -> None:
    path = ROOT / "notes" / "COMPRESSION_TRAIN_RECIPE.md"
    text = _read(path)
    banner = (
        f"\n\n---\n**{UNLOCK_NEEDLE}** · auto-train · train_unlocked=true · "
        f"{time.strftime('%Y-%m-%d %H:%M')}Z\n"
        "Hot path **NVFP4**; minimize unique U and RAM; no data prune; "
        "ALBERT-BitMoE primary + LoRA-Hive control.\n"
    )
    if UNLOCK_NEEDLE not in text:
        path.write_text(text.rstrip() + banner, encoding="utf-8")


def stamp_ready_train_go() -> None:
    path = ROOT / "notes" / "COMPRESSION_TRAIN_READY.md"
    text = _read(path)
    note = (
        f"\n\n### Auto-train GO ({UNLOCK_NEEDLE})\n\n"
        f"**Real model training:** **GO** — unlocked {time.strftime('%Y-%m-%d %H:%M')}Z by `{NEEDLE}`.\n"
        "First rung: min-RAM unique store @ NVFP4 (rung0 scaffold).\n"
    )
    if UNLOCK_NEEDLE not in text:
        path.write_text(text.rstrip() + note, encoding="utf-8")


def launch_rung0() -> int:
    """Start minimal efficient model scaffold + optional train entrypoint."""
    rung = SCRIPTS / "compression_train_rung0.py"
    if not rung.is_file():
        log(f"missing {rung} — cannot start model")
        return 2
    if rung0_alive():
        log("rung0 already running — skip relaunch")
        return 0
    env = os.environ.copy()
    env["COMPRESSION_TRAIN_UNLOCKED"] = "1"
    env["COMPRESSION_HOT_DTYPE"] = "NVFP4"
    env["COMPRESSION_MIN_RAM"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    log(f"starting rung0: {rung}")
    # Detach so keep-alive can continue
    log_path = Path.home() / ".config" / "automation" / "compression-rung0.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n# {NEEDLE} launch {time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n")
        fh.flush()
        proc = subprocess.Popen(
            [sys.executable, "-u", str(rung), "--train", "--min-ram"],
            cwd=str(ROOT),
            env=env,
            stdout=fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    log(f"rung0 pid={proc.pid} log={log_path}")
    time.sleep(1.5)
    if not rung0_alive():
        log("rung0 died immediately — check compression-rung0.log")
        return 3
    return 0


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
        # Real worker only (not ssh/bash wrappers that mention the path)
        if "python" in line and "bash -c" not in line and "pgrep" not in line:
            return True
    return False


def ensure_rung0() -> int:
    if rung0_alive():
        log("rung0 already running")
        return 0
    return launch_rung0()


def start_model_if_ready(*, force: bool = False) -> int:
    unlock_path = ART / "train_unlock.json"
    if unlock_path.is_file() and not force:
        try:
            prev = json.loads(unlock_path.read_text(encoding="utf-8"))
            if prev.get("train_unlocked"):
                log("already unlocked — ensure rung0 running")
                return ensure_rung0()
        except (json.JSONDecodeError, OSError):
            pass

    if not research_complete():
        log("research NOT complete — hold (need T4 Done + recipe LOCKED + T0–T3 green)")
        return 1

    write_unlock_artifact(reason="all research gates green; min-RAM NVFP4 train")
    stamp_recipe_unlocked()
    stamp_ready_train_go()
    return ensure_rung0()


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="print gate status JSON")
    ap.add_argument("--start", action="store_true", help="start model if gates green")
    ap.add_argument("--force", action="store_true", help="re-fire unlock/rung0 if already unlocked")
    ap.add_argument("--watch", action="store_true", help="poll forever; start/relaunch rung0 when green")
    ap.add_argument("--poll-sec", type=int, default=60)
    args = ap.parse_args()

    ready = _read(ROOT / "notes" / "COMPRESSION_TRAIN_READY.md")
    recipe = _read(ROOT / "notes" / "COMPRESSION_TRAIN_RECIPE.md")
    status = {
        "needle": NEEDLE,
        "t4_complete": t4_complete(ready),
        "recipe_locked": recipe_locked(recipe),
        "probes_green": t_probes_green() if args.check or args.start or args.watch else None,
        "research_complete": None,
    }
    if args.check:
        status["probes_green"] = t_probes_green()
        status["research_complete"] = (
            status["t4_complete"] and status["recipe_locked"] and status["probes_green"]
        )
        status["rung0_alive"] = rung0_alive()
        print(json.dumps(status, indent=2))
        return 0

    if args.watch:
        log(f"{NEEDLE} watch poll={args.poll_sec}s (forever — relaunch rung0 if it dies)")
        while True:
            if research_complete():
                rc = start_model_if_ready(force=args.force)
                if rc != 0:
                    log(f"ensure train rc={rc}")
                elif not rung0_alive():
                    log("rung0 missing after ensure — retry next poll")
                else:
                    log("gates green · rung0 live")
            else:
                log("waiting on T4 + recipe LOCKED + probes")
            time.sleep(max(15, args.poll_sec))

    if args.start:
        return start_model_if_ready(force=args.force)

    print(json.dumps({**status, "hint": "pass --check | --start | --watch"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
