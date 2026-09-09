#!/usr/bin/env python3
"""Lightweight retrieval over notes/SOP for niche composer context.

Needle: OVERSEER_NICHE_RETRIEVAL_2026_09_07

Hash-token bag index (no external embed API). Local only.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "notes"
DISTILL = NOTES / "niche_distill"
INDEX_PATH = DISTILL / "retrieval_index.json"
NEEDLE = "OVERSEER_NICHE_RETRIEVAL_2026_09_07"

_GLOBS = (
    "AUTOMATION.md",
    "AGENT_ERROR_PLAYBOOK.md",
    "AGENT_COMMANDS.md",
    "BITNET_NICHE_BANK.md",
    "COMPRESSION_NORTH_STAR.md",
    "DGX_NVFP4_SIDE_QUEST_OPS.md",
    "SOP_INDEX.md",
    "TEAM_CONTEXT.md",
    "HALLUCINATION_GUARD.md",
)


def _tok(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]{3,}", (text or "").lower()))


def build_index() -> dict[str, Any]:
    docs: list[dict[str, Any]] = []
    for name in _GLOBS:
        path = NOTES / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Chunk by ## headings
        parts = re.split(r"(?=^## )", text, flags=re.M)
        for i, part in enumerate(parts):
            chunk = part.strip()
            if len(chunk) < 80:
                continue
            title = chunk.splitlines()[0][:120]
            docs.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "chunk_id": i,
                    "title": title,
                    "text": chunk[:1800],
                    "tokens": sorted(_tok(chunk))[:400],
                }
            )
    payload = {
        "needle": NEEDLE,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_docs": len(docs),
        "docs": docs,
    }
    DISTILL.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return payload


def _load_index() -> dict[str, Any]:
    if not INDEX_PATH.is_file():
        return build_index()
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return build_index()


def retrieve(query: str, *, top_k: int = 3) -> list[dict[str, Any]]:
    idx = _load_index()
    q = _tok(query)
    if not q:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for doc in idx.get("docs") or []:
        toks = set(doc.get("tokens") or [])
        if not toks:
            continue
        inter = len(q & toks)
        if inter <= 0:
            continue
        score = inter / (len(q) ** 0.5)
        scored.append((score, doc))
    scored.sort(key=lambda x: -x[0])
    out = []
    for sc, doc in scored[:top_k]:
        out.append(
            {
                "score": round(sc, 3),
                "path": doc.get("path"),
                "title": doc.get("title"),
                "snippet": (doc.get("text") or "")[:400],
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default="")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--top-k", type=int, default=3)
    args = ap.parse_args(argv)
    if args.rebuild:
        idx = build_index()
        print(json.dumps({"needle": NEEDLE, "n_docs": idx["n_docs"]}, indent=2))
        return 0
    q = args.query or sys.stdin.read()
    print(json.dumps({"needle": NEEDLE, "hits": retrieve(q, top_k=args.top_k)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
