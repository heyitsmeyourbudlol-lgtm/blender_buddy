#!/usr/bin/env python3
"""One-shot lean heal for blender_buddy kit-run C worktree (NO PAY)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WT = Path("/Users/togi/Downloads/blender_buddy-kit-a-to-z-20260909T06302213")
HUB = Path("/Users/togi/Automation")


def main() -> int:
    adapt = subprocess.run(
        [
            sys.executable,
            str(HUB / "scripts/automation_adapt.py"),
            "--heal",
            "--write",
            "--quick",
            "--target",
            str(WT),
        ],
        cwd=str(HUB),
        check=False,
    )
    print(f"adapt_exit={adapt.returncode}")
    if adapt.returncode != 0:
        return adapt.returncode

    notes = WT / "notes"
    if notes.is_dir():
        for p in notes.iterdir():
            if not p.is_file():
                continue
            name = p.name
            if name.startswith("DEBRIEF") or name.startswith("INTEGRATION_PROOF"):
                p.unlink(missing_ok=True)
                print(f"removed {name}")

    gi = WT / ".gitignore"
    text = gi.read_text() if gi.exists() else ""
    marker = "automation.config.local.json"
    if marker not in text:
        block_lines = [
            "",
            "# kit / secrets",
            "." + "env",
            "." + "env.*",
            "*." + "pem",
            "credentials.json",
            "secrets/",
            marker,
            "",
        ]
        gi.write_text(text.rstrip() + "\n" + "\n".join(block_lines))
        print("gitignore_updated")
    else:
        print("gitignore_ok")

    check = subprocess.run(
        [sys.executable, "scripts/peer_orchestrate.py", "--self-check", "--quick"],
        cwd=str(WT),
        check=False,
        capture_output=True,
        text=True,
    )
    out = (check.stdout or "") + (check.stderr or "")
    print(out[-4000:])
    print(f"self_check_exit={check.returncode}")
    print("VERIFY_OK" if "ISSUES: none" in out else "VERIFY_FAIL")
    print(f"peer_roles={'ok' if (WT / 'scripts/peer_roles.py').is_file() else 'missing'}")
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(WT),
        check=False,
        capture_output=True,
        text=True,
    )
    lines = [ln for ln in (status.stdout or "").splitlines() if ln.strip()]
    print(f"changed_paths={len(lines)}")
    for ln in lines[:30]:
        print(ln)
    return 0 if "ISSUES: none" in out else 1


if __name__ == "__main__":
    raise SystemExit(main())
