#!/usr/bin/env python3
"""S23 alias — profile-once DGX util / TE FP4 (delegates to ``gpu_profile_once``).

OVERSEER_GPU_PROFILE_ONCE_2026_09_05

``notes/RESEARCH_SPEED_TRAINING.md`` S23 originally proposed this path name.
Canonical implementation: ``scripts/gpu_profile_once.py`` (hash-gate + meters).

Usage::

    python3 scripts/compression_train_profile.py
    python3 scripts/compression_train_profile.py --json
    python3 scripts/compression_train_profile.py --force
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

# OVERSEER_GPU_PROFILE_ONCE_2026_09_05
import gpu_profile_once as _impl  # noqa: E402

NEEDLE = _impl.NEEDLE
main = _impl.main

if __name__ == "__main__":
    raise SystemExit(main())
