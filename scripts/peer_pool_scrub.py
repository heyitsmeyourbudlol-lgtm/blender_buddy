"""Load scrub impl from hub-protect vault (Mac rsync-safe).

OVERSEER_SCRUB_IMPL_2026_09_04
OVERSEER_SCRUB_PARK_LOCAL_2026_09_04
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

__all__ = ["scrub_pool_tracked_config_dirt"]

_IMPL_CANDIDATES = (
    Path.home() / ".config/automation-hub/hub-protect/scripts/peer_pool_scrub_impl.py",
    Path.home() / ".config/automation-hub/bin/peer_pool_scrub_impl.py",
    Path.home() / ".config/automation-hub/hub-protect/peer_pool_scrub_impl.py",
)


def _load():
    for path in _IMPL_CANDIDATES:
        try:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            if "def scrub_pool_tracked_config_dirt" not in text:
                continue
            if "OVERSEER_SCRUB_PARK_LOCAL_2026_09_04" not in text:
                continue
            spec = importlib.util.spec_from_file_location("_peer_pool_scrub_impl", path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fn = getattr(mod, "scrub_pool_tracked_config_dirt", None)
            if callable(fn):
                return fn
        except Exception:  # noqa: BLE001
            continue
    raise ImportError(
        "peer_pool_scrub: vault impl missing — restore hub-protect peer_pool_scrub_impl.py"
    )


scrub_pool_tracked_config_dirt = _load()
