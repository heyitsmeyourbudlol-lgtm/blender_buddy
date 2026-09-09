#!/usr/bin/env python3
"""OVERSEER_STAG_FIX_LAND_2026_09_04 — unclobber metrics/poison/static; refresh vault."""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
VAULT = ROOT / "notes" / "agent_vaults" / "system_overseer" / "scripts"
PAUSE = Path.home() / ".config" / "automation-hub" / "RESTORE_PAUSED"


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({len(text)} bytes)")


def fix_peer_loop(text: str) -> str:
    needle = "OVERSEER_METRICS_IGNORE_GIT_CLEAN_2026_09_04"
    replacement = (
        "def metrics_green(live: auto.LiveState) -> bool:\n"
        f"    # {needle} — WORKING + continue_on_dirty:\n"
        "    # dirty porcelain must not paint metrics red (tests/RSS only).\n"
        "    return live.tests_ok and auto.success_metrics_ok(live)\n"
    )
    new, n = re.subn(
        r"def metrics_green\(live: auto\.LiveState\) -> bool:\n(?:    .*\n)*?",
        replacement,
        text,
        count=1,
    )
    if n != 1:
        raise SystemExit(f"peer_loop metrics_green patch failed n={n}")
    return new


def fix_peer_transcript(text: str) -> str:
    if "import peer_last_cycle_poison as _lc_poison" not in text:
        text = text.replace(
            "import peer_worktree\nimport project_automation as auto\n",
            "import peer_worktree\n"
            "import project_automation as auto\n"
            "import peer_last_cycle_poison as _lc_poison  "
            "# OVERSEER_SANITIZE_DEFERRED_VERIFY_OK_2026_09_04\n\n"
            "# Fail-closed re-exports — deferred soft-skip never counts as verify green.\n"
            "sanitize_last_cycle = _lc_poison.sanitize_last_cycle\n"
            "effective_verify_ok = _lc_poison.effective_verify_ok\n"
            "coerce_deferred_verify_ok = _lc_poison.coerce_deferred_verify_ok\n\n",
            1,
        )
    poison_block = '''def is_last_cycle_poison(lc: Any) -> bool:
    """OVERSEER_SCRUB_DEFERRED_POISON_2026_09_04 + FIXTURE_NOTE_OK."""
    if _lc_poison is not None:
        try:
            return bool(_lc_poison.is_last_cycle_poison(lc))
        except Exception:  # noqa: BLE001
            pass
    if not isinstance(lc, dict) or not lc:
        return False
    ft = str(lc.get("failure_type") or "").strip()
    if lc.get("verify_ok") is True and ft == "deferred":
        return True
    try:
        ts = float(lc.get("ts") or 0)
    except (TypeError, ValueError):
        ts = 0.0
    # OVERSEER_SCRUB_FIXTURE_NOTE_OK_2026_09_04 — note alone is not enough.
    if 0 < ts <= 1.0 and not lc.get("queue_fp") and not lc.get("git_head"):
        return True
    return False


def scrub_last_cycle_poison(state: dict[str, Any]) -> str | None:
    # OVERSEER_SANITIZE_DEFERRED_VERIFY_OK_2026_09_04 — never pop failure_type
    if _lc_poison is not None:
        try:
            return _lc_poison.scrub_last_cycle_poison(state)
        except Exception:  # noqa: BLE001
            pass
    lc = state.get("last_cycle")
    if not is_last_cycle_poison(lc):
        return None
    assert isinstance(lc, dict)
    ft = str(lc.get("failure_type") or "").strip()
    try:
        ts = float(lc.get("ts") or 0)
    except (TypeError, ValueError):
        ts = 0.0
    if lc.get("verify_ok") is True and ft == "deferred":
        fixed = dict(lc)
        fixed["verify_ok"] = False
        note = str(fixed.get("note") or "").strip()
        tag = "sanitized: deferred clears verify_ok"
        if tag not in note.lower():
            fixed["note"] = ((note + "; " if note else "") + tag)[:240]
        state["last_cycle"] = fixed
        return "sanitized deferred clears verify_ok"
    if 0 < ts <= 1.0 and not lc.get("queue_fp") and not lc.get("git_head"):
        state.pop("last_cycle", None)
        return "cleared fixture last_cycle (ts<=1.0)"
    state.pop("last_cycle", None)
    return "cleared poison last_cycle"
'''
    new, n = re.subn(
        r"def is_last_cycle_poison\(lc: Any\) -> bool:.*?return \"cleared poison last_cycle\"\n",
        poison_block,
        text,
        count=1,
        flags=re.S,
    )
    if n != 1:
        raise SystemExit(f"peer_transcript poison patch failed n={n}")
    return new


def fix_peer_repo_research(text: str) -> str:
    needle = "OVERSEER_STATIC_PRESENT_TRUE_ON_MATCH_2026_09_04"
    replacement = (
        "    for pid, pattern, _level, desc in STATIC_PATTERNS:\n"
        "        if desc != title and pid not in str(raw.get(\"id\") or \"\"):\n"
        "            continue\n"
        "        if not re.search(pattern, line):\n"
        "            continue\n"
        f"        # {needle} — match ⇒ still present.\n"
        "        # Catalog/comment skips above already filter false positives; inverted\n"
        "        # eval_call/shell_true→False wrongly resolved real sinks on empty merge.\n"
        "        return True\n"
        "    if evidence and evidence in line and (\".eval(\" in line or \"eval(\" in line):\n"
        "        return True\n"
        "    return False\n"
    )
    new, n = re.subn(
        r"    for pid, pattern, _level, desc in STATIC_PATTERNS:\n"
        r"        if desc != title and pid not in str\(raw\.get\(\"id\"\) or \"\"\):\n"
        r"            continue\n"
        r"        if not re\.search\(pattern, line\):\n"
        r"            continue\n"
        r"(?:        if pid in \(\"eval_call\", \"shell_true\"\):\n"
        r"            return False\n)?"
        r"        return True\n"
        r"    if evidence and evidence in line and .*?:\n"
        r"        return True\n"
        r"    return False\n",
        replacement,
        text,
        count=1,
    )
    if n != 1:
        raise SystemExit(f"peer_repo_research static patch failed n={n}")
    return new


def main() -> int:
    PAUSE.parent.mkdir(parents=True, exist_ok=True)
    PAUSE.write_text("1\n", encoding="utf-8")
    VAULT.mkdir(parents=True, exist_ok=True)

    targets = {
        "peer_loop.py": fix_peer_loop,
        "peer_transcript.py": fix_peer_transcript,
        "peer_repo_research.py": fix_peer_repo_research,
    }
    for name, fixer in targets.items():
        live = SCRIPTS / name
        text = fixer(live.read_text(encoding="utf-8"))
        _write(live, text)
        vault_path = VAULT / name
        _write(vault_path, text)
        md5_path = SCRIPTS / f"EXPECTED_{name}.md5"
        md5_path.write_text(_md5(live) + "\n", encoding="utf-8")
        print(f"md5 {name}={_md5(live)}")

    # Also keep poison module vaulted
    for extra in ("peer_last_cycle_poison.py",):
        src = SCRIPTS / extra
        if src.is_file():
            shutil.copy2(src, VAULT / extra)
            print(f"vaulted {extra}")

    # Smoke
    sys.path.insert(0, str(SCRIPTS))
    import importlib

    for mod in ("peer_loop", "peer_transcript", "peer_repo_research", "peer_last_cycle_poison"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    import peer_loop
    import peer_transcript as pt
    import project_automation as auto

    dirty = auto.LiveState(False, "dirty", True, "ok", 13.0, "ok")
    assert peer_loop.metrics_green(dirty), "metrics_green dirty must be True"
    assert pt.is_last_cycle_poison({"ts": 1.0, "verify_ok": True, "note": "ok"})
    assert "OVERSEER_STATIC_PRESENT_TRUE_ON_MATCH_2026_09_04" in (
        SCRIPTS / "peer_repo_research.py"
    ).read_text(encoding="utf-8")
    print("smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
