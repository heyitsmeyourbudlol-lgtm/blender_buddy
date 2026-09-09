#!/usr/bin/env python3
"""Tiny niche domain classifier — free-local NB when trained, else keyword heuristic.

Needle: OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07 (#14) · T10-09 train
``OVERSEER_TOP10_NEXT_T10_09_2026_09_07``

Usage:
  python3 scripts/niche_domain_classify.py "noop plan-gate"
  python3 scripts/niche_domain_classify.py --json "notes/WORK_QUEUE.md Active"
  ./scripts/peer niche-domain-classify "compression NVFP4"
  python3 scripts/niche_domain_classifier_train.py --train
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import peer_fact_librarian as fl  # noqa: E402

NEEDLE = "OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07"
TRAIN_NEEDLE = "OVERSEER_TOP10_NEXT_T10_09_2026_09_07"
MODEL_CHECKPOINT_HINT = ROOT / "notes" / "niche_distill" / "domain_classifier" / "checkpoint.json"

_TOKEN_RE = re.compile(r"[a-z0-9_./:-]+", re.I)
_CKPT_CACHE: dict[str, Any] | None = None


def model_available() -> bool:
    """True when a trained niche checkpoint exists."""
    return MODEL_CHECKPOINT_HINT.is_file()


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1]


def load_checkpoint(*, force: bool = False) -> dict[str, Any] | None:
    global _CKPT_CACHE
    if _CKPT_CACHE is not None and not force:
        return _CKPT_CACHE
    if not MODEL_CHECKPOINT_HINT.is_file():
        _CKPT_CACHE = None
        return None
    try:
        data = json.loads(MODEL_CHECKPOINT_HINT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _CKPT_CACHE = None
        return None
    if not isinstance(data, dict) or not data.get("labels") or not data.get("vocab"):
        _CKPT_CACHE = None
        return None
    _CKPT_CACHE = data
    return data


def infer_model(query: str, *, ckpt: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return domain_id / confidence / scores from multinomial NB checkpoint."""
    data = ckpt if ckpt is not None else load_checkpoint()
    if not data:
        return None
    labels: list[str] = list(data.get("labels") or [])
    vocab: list[str] = list(data.get("vocab") or [])
    v_index = {t: i for i, t in enumerate(vocab)}
    log_prior: list[float] = [float(x) for x in (data.get("log_prior") or [])]
    flp_raw = data.get("feature_log_prob") or []
    if not labels or not vocab or not flp_raw:
        return None
    toks = _tokenize(query)
    scores: list[float] = []
    for ci in range(len(labels)):
        s = log_prior[ci] if ci < len(log_prior) else 0.0
        row = flp_raw[ci]
        for t in toks:
            vi = v_index.get(t)
            if vi is not None and vi < len(row):
                s += float(row[vi])
        scores.append(s)
    m = max(scores) if scores else 0.0
    exps = [math.exp(s - m) for s in scores]
    z = sum(exps) or 1.0
    probs = [e / z for e in exps]
    best_i = max(range(len(labels)), key=lambda i: scores[i])
    ranked = sorted(
        (
            {
                "domain_id": labels[i],
                "score": round(float(scores[i]), 4),
                "prob": round(probs[i], 4),
            }
            for i in range(len(labels))
        ),
        key=lambda r: -float(r["prob"]),
    )
    return {
        "domain_id": labels[best_i],
        "confidence": round(float(probs[best_i]), 3),
        "scores": ranked[:8],
    }


def classify(query: str, *, prefer_model: bool = True) -> dict[str, Any]:
    """Return domain_id + confidence + source (heuristic|model|stub)."""
    q = str(query or "").strip()
    out: dict[str, Any] = {
        "needle": NEEDLE,
        "train_needle": TRAIN_NEEDLE,
        "query": q[:400],
        "domain_id": None,
        "confidence": 0.0,
        "source": "stub",
        "scores": [],
        "model_ready": model_available(),
        "no_pay": True,
    }
    if not q:
        out["source"] = "stub"
        out["note"] = "empty query"
        return out

    if prefer_model and model_available():
        pred = infer_model(q)
        if pred and pred.get("domain_id"):
            domain = fl.get_domain(str(pred["domain_id"]))
            out["domain_id"] = pred["domain_id"]
            out["confidence"] = pred.get("confidence") or 0.0
            out["scores"] = pred.get("scores") or []
            out["source"] = "model"
            if domain:
                out["role_id"] = domain.get("role_id")
            out["note"] = (
                f"checkpoint {MODEL_CHECKPOINT_HINT.relative_to(ROOT)}"
            )
            return out
        out["note"] = "checkpoint present but infer failed — falling through to heuristic"

    domain, scores = fl.auto_pick_domain(q)
    scored = [{"domain_id": did, "score": sc} for did, sc in (scores or [])[:8]]
    out["scores"] = scored
    if domain and domain.get("id"):
        best_sc = float(scored[0]["score"]) if scored else 0.0
        conf = min(1.0, max(0.0, best_sc / 20.0))
        out["domain_id"] = domain.get("id")
        out["confidence"] = round(conf, 3)
        out["source"] = "heuristic"
        out["role_id"] = domain.get("role_id")
        return out

    out["source"] = "stub"
    out["note"] = "no domain score > 0 — pass --domain explicitly or enrich keywords"
    return out


def format_classify(result: dict[str, Any]) -> str:
    did = result.get("domain_id") or "—"
    src = result.get("source") or "?"
    conf = result.get("confidence")
    lines = [
        f"domain_id={did} source={src} confidence={conf}",
        f"model_ready={result.get('model_ready')} needle={NEEDLE}",
    ]
    if result.get("note"):
        lines.append(f"note={result['note']}")
    if result.get("scores"):
        top = ", ".join(
            f"{r['domain_id']}:{r.get('prob', r.get('score'))}"
            for r in (result.get("scores") or [])[:5]
        )
        lines.append(f"scores={top}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Niche domain classifier (model + heuristic)")
    ap.add_argument("query", nargs="*", help="query text")
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--no-model",
        action="store_true",
        help="skip model even if checkpoint exists",
    )
    args = ap.parse_args(argv)
    q = " ".join(args.query).strip()
    if not q and not sys.stdin.isatty():
        q = sys.stdin.read().strip()
    if not q:
        ap.print_help()
        return 2
    result = classify(q, prefer_model=not args.no_model)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_classify(result))
    return 0 if result.get("domain_id") else 1


if __name__ == "__main__":
    raise SystemExit(main())
