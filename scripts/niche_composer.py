#!/usr/bin/env python3
"""Route a task string → top niche IDs from the bank catalog.

Needle: OVERSEER_NICHE_COMPOSER_ROUTE_2026_09_06
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import niche_bank_train as bank  # noqa: E402

NEEDLE = "OVERSEER_NICHE_COMPOSER_ROUTE_2026_09_06"


def score_niche(text: str, niche: dict[str, str]) -> float:
    t = text.lower()
    s = 0.0
    name = niche["name"].lower().replace("_", " ")
    for tok in name.split():
        if len(tok) > 2 and tok in t:
            s += 2.0
    for tok in re.findall(r"[a-z0-9_]{3,}", niche["helps"].lower()):
        if tok in t:
            s += 1.0
    for tok in re.findall(r"[a-z0-9_]{3,}", niche["input_shape"].lower()):
        if tok in t:
            s += 0.5
    # Prefer ready neural experts slightly
    ckpt = bank.niche_dir(niche["id"]) / "checkpoint_neural.json"
    if niche["id"] == "N01":
        ckpt = bank.DISTILL / "practice_n01" / "checkpoint_neural.json"
    if ckpt.is_file():
        try:
            d = json.loads(ckpt.read_text(encoding="utf-8"))
            if d.get("passed"):
                s += 0.25
        except (OSError, json.JSONDecodeError):
            pass
    return s


def route(text: str, *, top_k: int = 5) -> dict[str, Any]:
    catalog = bank.parse_catalog() + bank.extra_niches()
    ranked = sorted(
        ((score_niche(text, n), n) for n in catalog),
        key=lambda x: (-x[0], x[1]["id"]),
    )
    top = [
        {
            "id": n["id"],
            "name": n["name"],
            "score": round(sc, 3),
            "helps": n["helps"],
        }
        for sc, n in ranked[:top_k]
        if sc > 0
    ]
    if not top:
        top = [{"id": "N01", "name": "queue_bullet_parse", "score": 0.0, "helps": "fallback"}]
    return {"needle": NEEDLE, "input": text, "routes": top, "local_only": True}


def route_and_serve(text: str, *, top_k: int = 3) -> dict[str, Any]:
    """Route then parallel-serve via factory_niche_runtime (merge + escalate)."""
    import factory_niche_runtime as rt

    return rt.route_and_serve(text, top_k=top_k, with_retrieval=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--top-k", type=int, default=0, help="0 = use factory_niche_top_k config")
    ap.add_argument("--serve", action="store_true", help="parallel serve top routes")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    text = args.text or sys.stdin.read()
    if args.serve:
        import factory_niche_runtime as rt

        k = args.top_k if args.top_k > 0 else rt.default_top_k()
        out = route_and_serve(text, top_k=min(k, 5))
    else:
        k = args.top_k if args.top_k > 0 else 5
        out = route(text, top_k=k)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
