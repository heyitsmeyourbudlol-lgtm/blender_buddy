#!/usr/bin/env python3
"""Export the peer automation kit as a portable tarball."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import automation_adapt as adapt  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Bundle automation kit for export")
    parser.add_argument("--tar", action="store_true", help="Write dist/automation-kit-YYYY-MM-DD.tar.gz")
    parser.add_argument("--out-dir", type=Path, help="Output directory (default: ./dist)")
    args = parser.parse_args()

    if not args.tar:
        parser.print_help()
        return 0

    path = adapt.export_tarball(args.out_dir)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
