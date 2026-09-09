#!/usr/bin/env python3
"""Live factory niche hot path — cheap practice gates before cursor-agent.

Needle: OVERSEER_NICHE_HOT_PATH_N01_2026_09_07

Wires train-ready practice niches into peer dispatch so parse / needle / stall
class run as mechanical gates instead of burning a full cursor-agent turn.

**Live hook (this land):** N01 ``queue_bullet_parse`` on ``peer_orchestrate``
scope + prompt enrichment. Fail-closed: any import/IO/predict error → ``None``
so callers keep existing template_match / backtick scope logic.

N03 / N08 practice predictors are exported for inventory + future gates; not
yet the primary dispatch hook.

Local only. CLEAN-compatible (pure Python, no Mac-only APIs).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DISTILL = ROOT / "notes" / "niche_distill"
NEEDLE = "OVERSEER_NICHE_HOT_PATH_N01_2026_09_07"

# Practice niches with P0/P1 recipe + weights (inventory + hooks).
_PRACTICE = {
    "N01": {
        "name": "queue_bullet_parse",
        "dir": DISTILL / "practice_n01",
        "ckpt": DISTILL / "practice_n01" / "checkpoint.json",
        "weights": DISTILL
        / "practice_n01"
        / "weights"
        / "n01_queue_bullet_parse_practice.pt",
        "neural": DISTILL
        / "practice_n01"
        / "weights"
        / "n01_queue_bullet_parse_neural.pt",
        "helps": "compact / dispatch",
    },
    "N03": {
        "name": "land_proof_needle_match",
        "dir": DISTILL / "practice_n03",
        "ckpt": DISTILL / "practice_n03" / "checkpoint.json",
        "weights": DISTILL
        / "practice_n03"
        / "weights"
        / "n03_land_proof_needle_match_practice.pt",
        "neural": DISTILL
        / "practice_n03"
        / "weights"
        / "n03_land_proof_needle_match_neural.pt",
        "helps": "anti false-[x]",
    },
    "N08": {
        "name": "stall_class_label",
        "dir": DISTILL / "practice_n08",
        "ckpt": DISTILL / "practice_n08" / "checkpoint.json",
        "weights": DISTILL
        / "practice_n08"
        / "weights"
        / "n08_stall_class_label_practice.pt",
        "neural": DISTILL
        / "practice_n08"
        / "weights"
        / "n08_stall_class_label_neural.pt",
        "helps": "stall-watch",
    },
}


def enabled() -> bool:
    """Env ``FACTORY_NICHE_HOT_PATH=0`` disables; default on."""
    raw = os.environ.get("FACTORY_NICHE_HOT_PATH", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return True


def _ckpt_passed(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if meta.get("passed") is True:
        return True
    try:
        return float(meta.get("heldout_accuracy") or 0) >= float(
            meta.get("pass_bar") or 0.9
        )
    except (TypeError, ValueError):
        return False


def niche_ready(nid: str) -> dict[str, Any]:
    """Inventory one practice niche — weights + ckpt pass bar."""
    spec = _PRACTICE.get(nid.upper())
    if not spec:
        return {"id": nid, "ready": False, "reason": "unknown"}
    practice_ok = spec["weights"].is_file() and _ckpt_passed(spec["ckpt"])
    neural_ckpt = spec["dir"] / "checkpoint_neural.json"
    neural_ok = spec["neural"].is_file() and (
        _ckpt_passed(neural_ckpt) if neural_ckpt.is_file() else True
    )
    return {
        "id": nid.upper(),
        "name": spec["name"],
        "helps": spec["helps"],
        "practice_ready": practice_ok,
        "neural_ready": neural_ok,
        "ready": practice_ok,  # hot path uses rule practice (no torch)
        "weights": str(spec["weights"].relative_to(ROOT)) if practice_ok else None,
        "neural_weights": str(spec["neural"].relative_to(ROOT))
        if neural_ok
        else None,
    }


def inventory_ready() -> dict[str, Any]:
    """N01/N03/N08 readiness snap for factory / dashboard."""
    experts = [niche_ready(nid) for nid in ("N01", "N03", "N08")]
    return {
        "needle": NEEDLE,
        "hot_path": "N01",
        "n_ready": sum(1 for e in experts if e.get("ready")),
        "experts": experts,
        "local_only": True,
    }


def parse_queue_bullet(line: str) -> dict[str, Any] | None:
    """N01 practice predict — fail-closed ``None`` on any error / disabled / unreadiness.

    Returns kit / scope / needle plus metadata. Callers must fall back to
    existing scope-hint logic when this returns ``None`` or empty scope.
    """
    if not enabled():
        return None
    text = (line or "").strip()
    if not text:
        return None
    ready = niche_ready("N01")
    if not ready.get("ready"):
        return None
    try:
        import niche_n01_practice as n01

        pred = n01.predict(text)
    except Exception:  # noqa: BLE001 — fail-closed
        return None
    if not isinstance(pred, dict):
        return None
    return {
        "niche_id": "N01",
        "name": "queue_bullet_parse",
        "kit": pred.get("kit"),
        "scope": (pred.get("scope") or "") or None,
        "needle": pred.get("needle"),
        "source": "n01_practice",
        "kind": "rule",
        "local_only": True,
        "land_needle": NEEDLE,
    }


def format_prompt_block(line: str) -> str:
    """Compact mechanical parse for peer prompts — empty string if unavailable."""
    parsed = parse_queue_bullet(line)
    if not parsed:
        return ""
    kit = parsed.get("kit")
    kit_s = "true" if kit is True else "false" if kit is False else "null"
    scope = parsed.get("scope") or "(none)"
    needle = parsed.get("needle") or "(none)"
    return (
        "**Mechanical N01 parse (do not re-derive — cheap gate):** "
        f"kit={kit_s} scope=`{scope}` needle=`{needle}` "
        f"[{NEEDLE}]"
    )


def extract_land_needle(item: str) -> str | None:
    """N03 practice — land-proof needle or None (fail-closed)."""
    if not enabled() or not niche_ready("N03").get("ready"):
        return None
    try:
        import niche_n03_practice as n03

        return n03.predict(item)
    except Exception:  # noqa: BLE001
        return None


def classify_stall(status: str, log: str = "") -> str | None:
    """N08 practice — stall class label or None (fail-closed)."""
    if not enabled() or not niche_ready("N08").get("ready"):
        return None
    try:
        import niche_n08_practice as n08

        return n08.predict({"status": status, "log": log})
    except Exception:  # noqa: BLE001
        return None


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inventory", action="store_true")
    ap.add_argument("--serve", metavar="LINE", help="N01 parse one queue line")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.inventory or args.serve is None:
        out: Any = inventory_ready()
    else:
        out = parse_queue_bullet(args.serve) or {"ok": False, "fallback": True}
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
