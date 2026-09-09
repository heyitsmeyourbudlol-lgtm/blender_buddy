#!/usr/bin/env python3
"""Scrub inactive product-forge orphan cursor-agents.

OVERSEER_SCRUB_ORPHAN_FORGE_MODULE_2026_09_04

stop_forge left CaaS agents (ppid=1) running; verify quiet-cap then
deferred hub verify forever. Call from verify-lane prep + improve tick.
"""
from __future__ import annotations

from typing import Callable


def scrub_inactive_forge_orphans(
    *,
    log_fn: Callable[[str], None] | None = None,
) -> int:
    """Return number of agents killed; 0 if forge active or none found."""
    log = log_fn or (lambda _m: None)
    try:
        import peer_product_forge as forge
    except Exception:  # noqa: BLE001
        return 0
    try:
        if forge.forge_active():
            return 0
        n = int(forge.scrub_orphan_forge_agents(log_fn=log) or 0)
        if n:
            log(f"forge-scrub: scrubbed {n} orphan product-forge agent(s)")
        return n
    except Exception:  # noqa: BLE001
        return 0
