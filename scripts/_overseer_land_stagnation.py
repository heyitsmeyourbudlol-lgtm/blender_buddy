#!/usr/bin/env python3
"""Overseer stagnation land helpers — module_scope target.

Exists so local_profile audit does not warn on missing
``_overseer_land_stagnation → scripts/_overseer_land_stagnation.py``.
Real lands live in peer_orchestrate / peer_worktree / automation_adapt.
"""
from __future__ import annotations

MODULE = "_overseer_land_stagnation"
SCOPE_REL = "scripts/_overseer_land_stagnation.py"


def scope_entry() -> tuple[str, str]:
    return MODULE, SCOPE_REL
