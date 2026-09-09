#!/usr/bin/env python3
"""Thin wrapper: niche_mint --start --train with env/args (fail-soft).

Needle: OVERSEER_COMMAND_ECOSYSTEM_PLAN_2026_09_07

Usage::
    python3 scripts/niche_mint_train.py --name foo --io "a → b" --reason "…"
    ./scripts/peer niche-mint-train -- --name foo --io "a → b" --reason "…"
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import niche_mint as mint  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    # Force train path via niche_mint CLI
    if "--start" not in argv:
        argv = ["--start", "--train", *argv]
    elif "--train" not in argv:
        argv.insert(argv.index("--start") + 1, "--train")
    return mint.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
