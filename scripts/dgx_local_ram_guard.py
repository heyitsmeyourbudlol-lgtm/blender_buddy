#!/usr/bin/env python3
"""On-DGX RAM guard loop — trim unittest storms and excess agents every 10s."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
GUARD = SCRIPTS / "dgx_local_ram_guard.sh"
INTERVAL_SEC = 10.0


def _run_once() -> int:
    if not GUARD.is_file():
        print(f"missing {GUARD}", file=sys.stderr)
        return 1
    return int(subprocess.run(["bash", str(GUARD)], check=False).returncode or 0)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--once",
        action="store_true",
        help="Run guard shell once and exit (safe peer default)",
    )
    args = p.parse_args(argv)
    if args.once:
        return _run_once()
    if not GUARD.is_file():
        print(f"missing {GUARD}", file=sys.stderr)
        return 1
    while True:
        subprocess.run(["bash", str(GUARD)], check=False)
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
