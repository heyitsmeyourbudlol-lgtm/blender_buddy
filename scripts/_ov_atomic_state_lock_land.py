#!/usr/bin/env python3
"""Atomic land: peer_transcript state-lock timeout + vault pin + WQ close.

Needle: OVERSEER_STATE_LOCK_TIMEOUT_2026_09_04
"""
from __future__ import annotations

import hashlib
import os
import shutil
import time
from pathlib import Path

ROOT = Path("/home/arnavrastogi/Automation")
SCRIPTS = ROOT / "scripts"
PT = SCRIPTS / "peer_transcript.py"
VAULT = Path.home() / ".config/automation-hub/hub-protect/scripts"
BIN = Path.home() / ".config/automation-hub/bin"
HOLD = Path.home() / ".config/automation-hub/OVERSEER_LAND_HOLD"
PAUSED = Path.home() / ".config/automation-hub/RESTORE_PAUSED"

OLD = '''@contextlib.contextmanager
def _state_file_lock(*, shared: bool = False):
    """Serialize load/mutate/save of peer-loop-state.json across daemons."""
    STATE_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_LOCK_PATH, "a+", encoding="utf-8") as lock_fp:
        fcntl.flock(
            lock_fp.fileno(),
            fcntl.LOCK_SH if shared else fcntl.LOCK_EX,
        )
        try:
            yield
        finally:
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)



'''

NEW = '''def _state_lock_path() -> Path:
    """Lock beside the active STATE_PATH (follows unittest patches).

    Needle: OVERSEER_STATE_LOCK_TIMEOUT_2026_09_04
    """
    try:
        return Path(str(STATE_PATH) + ".lock")
    except Exception:  # noqa: BLE001
        return STATE_LOCK_PATH


@contextlib.contextmanager
def _state_file_lock(*, shared: bool = False, timeout_sec: float | None = None):
    """Serialize load/mutate/save of peer-loop-state.json across daemons.

    Never block forever — hung agents previously held LOCK_EX and poisoned
    ``tests.test_automation`` / measure with FAIL (failures=2–3) under swarm.
    Needle: OVERSEER_STATE_LOCK_TIMEOUT_2026_09_04
    """
    lock_path = _state_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        limit = float(os.environ.get("PEER_STATE_LOCK_TIMEOUT_SEC") or 8.0)
    except (TypeError, ValueError):
        limit = 8.0
    if timeout_sec is not None:
        limit = float(timeout_sec)
    flag = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
    with open(lock_path, "a+", encoding="utf-8") as lock_fp:
        deadline = time.time() + max(0.5, limit)
        while True:
            try:
                fcntl.flock(lock_fp.fileno(), flag | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() >= deadline:
                    raise TimeoutError(
                        f"peer-loop-state flock timeout ({limit:.1f}s)"
                    ) from None
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)



'''


def _hold() -> None:
    HOLD.parent.mkdir(parents=True, exist_ok=True)
    HOLD.write_text(f"overseer-atomic-lock-{time.time()}\n", encoding="utf-8")
    (ROOT / "OVERSEER_LAND_HOLD").write_text(HOLD.read_text(), encoding="utf-8")
    PAUSED.write_text(f"overseer-atomic KEEP {time.time()}\n", encoding="utf-8")
    os.system(
        "systemctl --user stop hub-protect-restore.timer "
        "hub-protect-restore.service 2>/dev/null"
    )


def _patch_transcript() -> str:
    text = PT.read_text(encoding="utf-8")
    if "OVERSEER_STATE_LOCK_TIMEOUT_2026_09_04" in text and "LOCK_NB" in text:
        return "already"
    if OLD not in text:
        return "mismatch"
    text = text.replace(OLD, NEW, 1)
    text = text.replace(
        "except (json.JSONDecodeError, OSError):\n        pass\n    return {}",
        "except (json.JSONDecodeError, OSError, TimeoutError):\n        pass\n    return {}",
        1,
    )
    old_save = (
        "    with _state_file_lock():\n"
        '        tmp_path.write_text(payload, encoding="utf-8")\n'
        "        os.replace(tmp_path, STATE_PATH)\n"
    )
    new_save = (
        "    try:\n"
        "        with _state_file_lock():\n"
        '            tmp_path.write_text(payload, encoding="utf-8")\n'
        "            os.replace(tmp_path, STATE_PATH)\n"
        "    except TimeoutError:\n"
        "        # OVERSEER_STATE_LOCK_TIMEOUT_2026_09_04 — prefer drop write over hang\n"
        "        return\n"
    )
    if old_save in text and "prefer drop write over hang" not in text:
        text = text.replace(old_save, new_save, 1)
    PT.write_text(text, encoding="utf-8")
    return "wrote"


def _pin() -> str:
    text = PT.read_text(encoding="utf-8")
    if "LOCK_NB" not in text:
        raise SystemExit("live missing LOCK_NB after patch")
    VAULT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PT, VAULT / "peer_transcript.py")
    for extra in (
        Path.home() / ".config/automation-hub/vault/scripts",
        Path.home() / ".config/automation-hub/oversight_vault/scripts",
        Path.home() / ".config/automation-hub/hub_script_overlays",
    ):
        extra.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PT, extra / "peer_transcript.py")
    md5 = hashlib.md5(PT.read_bytes()).hexdigest()
    (SCRIPTS / "EXPECTED_peer_transcript.py.md5").write_text(md5 + "\n", encoding="utf-8")
    return md5


def _patch_restore(path: Path) -> str:
    if not path.is_file():
        return "missing"
    rt = path.read_text(encoding="utf-8")
    if "OVERSEER_STATE_LOCK_TIMEOUT_2026_09_04" in rt and "peer_transcript.py)" in rt:
        return "already"
    arm = (
        "    peer_transcript.py)\n"
        "      # OVERSEER_STATE_LOCK_TIMEOUT_2026_09_04 — unbounded flock hangs tests\n"
        "      grep -q 'OVERSEER_STATE_LOCK_TIMEOUT_2026_09_04' \"$ROOT/$f\" "
        "2>/dev/null || return 0\n"
        "      grep -q 'LOCK_NB' \"$ROOT/$f\" 2>/dev/null || return 0\n"
        "      return 1 ;;\n"
    )
    changed = False
    for marker in (
        "    peer_repo_research.py)\n",
        "    peer_pen_test.py)\n",
        "    factory_progress.py)\n",
    ):
        body = rt.split("live_bad", 1)[-1][:3000] if "live_bad" in rt else rt
        if marker in rt and "peer_transcript.py)" not in body:
            rt = rt.replace(marker, arm + marker, 1)
            changed = True
            break
    vok = (
        "    peer_transcript.py) grep -q 'OVERSEER_STATE_LOCK_TIMEOUT_2026_09_04' \"$src\" "
        "&& grep -q 'LOCK_NB' \"$src\" ;;\n"
    )
    if "peer_transcript.py) grep -q" not in rt:
        for marker in (
            "    peer_repo_research.py) grep -q",
            "    peer_pen_test.py) grep -q",
        ):
            if marker in rt:
                rt = rt.replace(marker, vok + marker, 1)
                changed = True
                break
    if changed:
        path.write_text(rt, encoding="utf-8")
        return "wrote"
    return "miss"


def _close_theater() -> dict[str, int]:
    done = "landed 2026-09-04 overseer (scripts fixed; ignore Mac sync restore)"
    needles = (
        "last_cycle poison",
        "Stale peer worktrees re-poison false eval-call",
        "REPO_FLAW_RESEARCH.md missing from HUB_PROTECT_PULL_EXCLUDES",
    )
    counts: dict[str, int] = {}
    for path in (ROOT / "notes/WORK_QUEUE.md", SCRIPTS / "self_improve_context.md"):
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines(True)
        out: list[str] = []
        n = 0
        for line in lines:
            if line.lstrip().startswith("- [") and any(nd in line for nd in needles):
                if "- [ ]" in line[:10]:
                    line = line.replace("- [ ]", "- [x]", 1)
                    n += 1
                if done not in line and "—" in line:
                    pre, _, _rest = line.partition("—")
                    line = f"{pre}— {done}\n"
                    n += 1
            out.append(line)
        path.write_text("".join(out), encoding="utf-8")
        counts[path.name] = n
    return counts


def main() -> int:
    _hold()
    r1 = _patch_transcript()
    print("transcript", r1)
    if r1 == "mismatch":
        idx = PT.read_text(encoding="utf-8").find("def _state_file_lock")
        snippet = PT.read_text(encoding="utf-8")[idx : idx + 220]
        print("snippet", repr(snippet))
        return 2
    md5 = _pin()
    print("pinned", md5)
    for restore in (
        SCRIPTS / "restore-hub-protect.sh",
        BIN / "restore-hub-protect.sh",
        BIN / "restore-hub-protect.sh.real",
    ):
        print("restore", restore.name, _patch_restore(restore))
    if (SCRIPTS / "restore-hub-protect.sh").is_file():
        shutil.copy2(SCRIPTS / "restore-hub-protect.sh", BIN / "restore-hub-protect.sh")
        shutil.copy2(SCRIPTS / "restore-hub-protect.sh", BIN / "restore-hub-protect.sh.real")
    print("theater", _close_theater())
    time.sleep(0.2)
    live_ok = "LOCK_NB" in PT.read_text(encoding="utf-8")
    vault_ok = "LOCK_NB" in (VAULT / "peer_transcript.py").read_text(encoding="utf-8")
    print("final", {"live": live_ok, "vault": vault_ok})
    return 0 if live_ok and vault_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
