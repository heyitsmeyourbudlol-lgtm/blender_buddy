#!/usr/bin/env python3
"""OVERSEER_PURGE_SCRIPTS_TEST_SHADOW_2026_09_04 — durable scripts/test_*.py purge."""
from __future__ import annotations
import os, re, shutil, sys
from pathlib import Path

HOME = Path.home()
ROOT = Path(os.environ.get("AUTOMATION_ROOT", str(HOME / "Automation")))
BIN = HOME / ".config/automation-hub/bin"
VAULT = HOME / ".config/automation-hub/hub-protect"

OLD = (
    '      # Keep scripts/ mirror if present (some peers import from scripts/)\n'
    '      if [[ -f "$REPO/scripts/test_automation.py" ]]; then\n'
    '        cp -f "$src" "$REPO/scripts/test_automation.py"\n'
    '      fi\n'
)
NEW = (
    '      # OVERSEER_PURGE_SCRIPTS_TEST_SHADOW_2026_09_04 — never mirror into scripts/\n'
    '      rm -f "$REPO"/scripts/test_*.py 2>/dev/null || true\n'
)
ALWAYS = (
    '# OVERSEER_PURGE_SCRIPTS_TEST_SHADOW_2026_09_04 — always drop scripts/ shadows\n'
    'rm -f "$REPO"/scripts/test_*.py 2>/dev/null || true\n'
    'echo "hub-protect restored=$restored"'
)

def fix_restore(rt: str) -> str:
    if OLD in rt:
        rt = rt.replace(OLD, NEW)
    rt = re.sub(
        r'(?:# OVERSEER_PURGE_SCRIPTS_TEST_SHADOW_2026_09_04 — always drop scripts/ shadows\n'
        r'rm -f "\$REPO"/scripts/test_\*\.py 2>/dev/null \|\| true\n)+'
        r'echo "hub-protect restored=\$restored"',
        'echo "hub-protect restored=$restored"',
        rt,
    )
    if 'OVERSEER_PURGE_SCRIPTS_TEST_SHADOW_2026_09_04 — always' not in rt and 'echo "hub-protect restored=$restored"' in rt:
        a, b = rt.rsplit('echo "hub-protect restored=$restored"', 1)
        rt = a + ALWAYS + b
    return rt

def patch_restores() -> int:
    n = 0
    for p in [
        ROOT / "scripts/restore-hub-protect.sh",
        BIN / "restore-hub-protect.sh",
        VAULT / "restore-hub-protect.sh",
        VAULT / "scripts" / "restore-hub-protect.sh",
    ]:
        if not p.is_file():
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        nt = fix_restore(t)
        if nt != t:
            p.write_text(nt, encoding="utf-8")
            p.chmod(0o755)
            n += 1
    return n

def purge() -> int:
    n = 0
    for p in (ROOT / "scripts").glob("test_*.py"):
        p.unlink(); n += 1
    # Nested vault copies (hub-protect/scripts/scripts/test_*.py) also re-poison
    if VAULT.is_dir():
        for p in VAULT.rglob("test_*.py"):
            # keep tests/ vault copies under hub-protect/tests/
            if "/tests/" in str(p).replace("\\", "/"):
                continue
            try:
                p.unlink(); n += 1
            except OSError:
                pass
    return n

def main() -> int:
    fixed = patch_restores()
    purged = purge()
    if fixed:
        print(f"heal-false-eval: re-patched restore mirror in {fixed} path(s)")
    if purged:
        print(f"heal-false-eval: purged {purged} scripts/test_*.py shadow(s)")
    # keep a repo copy when possible
    src = Path(__file__).resolve()
    dest = ROOT / "scripts" / "_overseer_land_shadow_purge.py"
    try:
        if not dest.exists() or dest.read_bytes() != src.read_bytes():
            shutil.copy2(src, dest)
    except Exception:
        pass
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
