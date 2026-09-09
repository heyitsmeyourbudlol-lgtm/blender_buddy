#!/usr/bin/env python3
"""One-shot niche assist on Active WORK_QUEUE head (fail-soft).

Needle: OVERSEER_COMMAND_ECOSYSTEM_PLAN_2026_09_07

Usage::
    python3 scripts/niche_assist_once.py
    ./scripts/peer niche-assist-once
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

WQ = ROOT / "notes" / "WORK_QUEUE.md"


def _active_head() -> str:
    if not WQ.is_file():
        return "parse WORK_QUEUE Active bullets"
    in_active = False
    for raw in WQ.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw.strip().startswith("## Active"):
            in_active = True
            continue
        if in_active and raw.startswith("## "):
            break
        if in_active and raw.lstrip().startswith("- ["):
            return raw.strip()
    return "parse WORK_QUEUE Active bullets"


def main() -> int:
    text = _active_head()
    out: dict = {"input": text, "ok": False}
    try:
        import factory_dynamics as fd

        out["dynamics"] = fd.params_for_assist() if hasattr(fd, "params_for_assist") else {}
    except Exception as exc:  # noqa: BLE001
        out["dynamics_error"] = str(exc)
    try:
        import factory_niche_runtime as rt

        served = rt.route_and_serve(text, top_k=3)
        out["assist"] = {
            k: served.get(k)
            for k in (
                "best",
                "routes",
                "escalate_to_big_model",
                "mint_suggestion",
                "gpu_share",
                "device",
            )
            if k in served
        }
        out["ok"] = True
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
