#!/usr/bin/env python3
"""OVERSEER_LAND_HOLD TTL — forever holds starve Mac-clobber restore.

Needle: OVERSEER_LAND_HOLD_TTL_2026_09_03
OVERSEER_LAND_HOLD_FUTURE_MTIME_2026_09_04 — touch -d tomorrow must expire.
OVERSEER_UNSTUB_RESTORE_ON_CLEAR_2026_09_04 — clear must unstub paused wrap.
OVERSEER_CLEAR_STALE_RESTORE_PAUSED_2026_09_04 — leftover RESTORE_PAUSED flags
keep heal/scan stuck on HIGH hub_protect_restore_paused while wrap is live.
OVERSEER_ROOT_RESTORE_PAUSED_2026_09_04 — repo-root RESTORE_PAUSED (overseer-stag
land twin) must clear with hub flags; Mac clobber previously dropped CLEAR_STALE.
OVERSEER_MAC_CLOBBER_PROTECT_RESPECT_2026_09_04 — intentional defend window
(body/flag contains mac-clobber-protect) must not be force-cleared by heal.
OVERSEER_MAC_CLOBBER_STARTED_2026_09_04 — mtime refresh cannot starve forever;
first-sighting started stamp bounds the protect window.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import time
from pathlib import Path

HOLD_PATH = Path.home() / ".config/automation-hub/OVERSEER_LAND_HOLD"
PROTECT_STARTED_PATH = Path.home() / ".config/automation-hub/OVERSEER_LAND_HOLD.started"
REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_HOLD = REPO_ROOT / "OVERSEER_LAND_HOLD"
RESTORE = Path.home() / ".config/automation-hub/bin/restore-hub-protect.sh"
RESTORE_REAL = RESTORE.with_name(RESTORE.name + ".real")
REPO_RESTORE = Path(__file__).resolve().parent / "restore-hub-protect.sh"
HUB_CFG = Path.home() / ".config/automation-hub"
RESTORE_PAUSED_FLAGS: tuple[Path, ...] = (
    HUB_CFG / "RESTORE_PAUSED",
    HUB_CFG / "hub-protect" / "RESTORE_PAUSED",
    # OVERSEER_ROOT_RESTORE_PAUSED_2026_09_04 — overseer-stag land twin at repo root
    REPO_ROOT / "RESTORE_PAUSED",
)
MAX_AGE_SEC = 90.0
MAC_CLOBBER_PROTECT_NEEDLE = "mac-clobber-protect"
MAC_CLOBBER_PROTECT_MAX_AGE_SEC = 1800.0


def hold_body(path: Path | None = None) -> str:
    if path is None:
        path = HOLD_PATH
    try:
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _protect_started_age_sec() -> float | None:
    try:
        if not PROTECT_STARTED_PATH.is_file():
            return None
        raw = PROTECT_STARTED_PATH.read_text(encoding="utf-8", errors="replace").strip()
        started = float(raw.split()[0])
        return max(0.0, time.time() - started)
    except (OSError, ValueError, IndexError):
        return None


def _mark_protect_started() -> None:
    try:
        if PROTECT_STARTED_PATH.is_file():
            return
        PROTECT_STARTED_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROTECT_STARTED_PATH.write_text(f"{time.time():.6f}\n", encoding="utf-8")
    except OSError:
        pass


def _clear_protect_started() -> str:
    try:
        if PROTECT_STARTED_PATH.is_file():
            PROTECT_STARTED_PATH.unlink(missing_ok=True)
            return "cleared protect-started"
    except OSError as exc:
        return f"protect-started clear failed: {exc}"
    return "protect-started absent"


def intentional_mac_clobber_protect(*, max_age_sec: float | None = None) -> bool:
    """Needle: OVERSEER_MAC_CLOBBER_PROTECT_RESPECT_2026_09_04 + STARTED_2026_09_04."""
    body = hold_body().lower()
    flag_hit = False
    for flag in RESTORE_PAUSED_FLAGS:
        try:
            if flag.is_file() and MAC_CLOBBER_PROTECT_NEEDLE in flag.read_text(
                encoding="utf-8", errors="replace"
            ).lower():
                flag_hit = True
                break
        except OSError:
            continue
    if MAC_CLOBBER_PROTECT_NEEDLE not in body and not flag_hit:
        return False
    _mark_protect_started()
    started_age = _protect_started_age_sec()
    limit = MAC_CLOBBER_PROTECT_MAX_AGE_SEC if max_age_sec is None else max_age_sec
    if started_age is not None and started_age >= limit:
        return False
    age = hold_age_sec()
    if age is None:
        return flag_hit and restore_is_paused()
    if age >= limit:
        return False
    return True


def hold_age_sec(path: Path | None = None) -> float | None:
    if path is None:
        path = HOLD_PATH
    try:
        if not path.is_file():
            return None
        delta = time.time() - float(path.stat().st_mtime)
        if delta < 0:
            return MAX_AGE_SEC + abs(delta)
        return delta
    except OSError:
        return None


def restore_is_paused(path: Path | None = None) -> bool:
    if path is None:
        path = RESTORE
    try:
        if not path.is_file():
            return False
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    head = text[:500].lower()
    if "restore paused" in head:
        return True
    return "paused" in head and "exit 0" in head and len(text) < 400


def clear_stale_restore_paused(*, force: bool = False) -> str:
    # OVERSEER_FORCE_CLEAR_RESTORE_PAUSED_2026_09_04 — force bypasses mac-clobber
    if not force and intentional_mac_clobber_protect():
        return "RESTORE_PAUSED kept (mac-clobber-protect)"
    age = hold_age_sec()
    fresh_hold = age is not None and age < MAX_AGE_SEC and not force
    if fresh_hold:
        return "RESTORE_PAUSED kept (fresh land-hold)"
    cleared: list[str] = []
    for flag in RESTORE_PAUSED_FLAGS:
        if not flag.is_file():
            continue
        try:
            flag.unlink(missing_ok=True)
            if flag.parent.name == "hub-protect":
                label = f"hub-protect/{flag.name}"
            elif flag.parent == REPO_ROOT:
                label = "repo/RESTORE_PAUSED"
            else:
                label = flag.name
            cleared.append(label)
        except OSError as exc:
            return f"RESTORE_PAUSED clear failed: {exc}"
    if not cleared:
        return "RESTORE_PAUSED absent"
    return f"cleared stale RESTORE_PAUSED ({', '.join(cleared)})"


def unstub_restore() -> str:
    if intentional_mac_clobber_protect():
        return "unstub skipped (mac-clobber-protect)"
    if not RESTORE.is_file():
        return "restore absent"
    if not restore_is_paused():
        return "restore not paused"
    src = None
    for cand in (RESTORE_REAL, REPO_RESTORE):
        if cand.is_file() and not restore_is_paused(cand):
            src = cand
            break
    if src is None:
        return "unstub source missing"
    try:
        shutil.copy2(src, RESTORE)
        RESTORE.chmod(0o755)
    except OSError as exc:
        return f"unstub failed: {exc}"
    return f"unstubbed from {src.name}"


def clear_expired(*, max_age_sec: float = MAX_AGE_SEC, force: bool = False) -> str:
    parts: list[str] = []
    if intentional_mac_clobber_protect():
        age = hold_age_sec()
        parts.append(
            f"land-hold kept (mac-clobber-protect age={age if age is not None else 'n/a'}s)"
        )
        parts.append("RESTORE_PAUSED kept (mac-clobber-protect)")
        return "; ".join(parts)
    age = hold_age_sec()
    if age is None:
        parts.append("land-hold absent")
    elif not force and age < max_age_sec:
        parts.append(f"land-hold fresh age={age:.0f}s<{max_age_sec:.0f}s")
    else:
        try:
            HOLD_PATH.unlink(missing_ok=True)
            parts.append(f"cleared land-hold age={age:.0f}s force={force}")
        except OSError as exc:
            parts.append(f"land-hold clear failed: {exc}")
    if ROOT_HOLD.is_file():
        try:
            ROOT_HOLD.unlink(missing_ok=True)
            parts.append("cleared root OVERSEER_LAND_HOLD")
        except OSError as exc:
            parts.append(f"root hold clear failed: {exc}")
    parts.append(clear_stale_restore_paused(force=force))
    parts.append(_clear_protect_started())
    return "; ".join(parts)


def run_restore() -> str:
    if intentional_mac_clobber_protect():
        return "skip restore (mac-clobber-protect)"
    unstub = unstub_restore()
    if not RESTORE.is_file():
        return f"{unstub}; restore script absent"
    try:
        proc = subprocess.run(
            ["bash", str(RESTORE)],
            capture_output=True,
            text=True,
            timeout=60.0,
            check=False,
        )
        line = (proc.stdout or proc.stderr or "").strip().splitlines()
        tail = line[-1][:160] if line else f"restore rc={proc.returncode}"
        return f"{unstub}; {tail}" if unstub != "restore not paused" else tail
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"{unstub}; restore error: {exc}"


def clear_and_restore(*, force: bool = False) -> dict[str, str]:
    return {"clear": clear_expired(force=force), "restore": run_restore()}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--clear", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--restore", action="store_true")
    p.add_argument("--unstub", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    if args.unstub and not (args.clear or args.restore or args.force):
        msg = unstub_restore()
        print(msg)
        return 0 if "failed" not in msg and "missing" not in msg else 1
    if args.clear or args.restore or args.force:
        out = {
            "clear": clear_expired(force=bool(args.force or args.clear)),
            "restore": run_restore() if (args.restore or args.force) else "skipped",
        }
        if args.json:
            import json
            print(json.dumps(out, indent=2))
        else:
            print(out["clear"])
            if out["restore"] != "skipped":
                print(out["restore"])
        return 0
    age = hold_age_sec()
    print(
        f"age={age if age is not None else 'absent'} max={MAX_AGE_SEC} "
        f"paused={restore_is_paused()} protect={intentional_mac_clobber_protect()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
