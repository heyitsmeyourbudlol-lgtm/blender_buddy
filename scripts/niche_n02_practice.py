#!/usr/bin/env python3
"""N02 queue_kit_vs_research — practice distill / eval / serve (N01/N07 stamp).

OVERSEER_NICHE_PRACTICE_N02_2026_09_07

Same recipe as N07: existing heldout → niche accuracy → checkpoint → serve.
Deterministic rule baseline + ckpt under ``notes/niche_distill/practice_n02/``.
Does **not** rewrite/prune train or heldout JSONL (assignment: no corpus prune).

Explicit cue preference (as/label=/→/[X]/Factory X) — trailing
``(kit/research/creative/defer)`` legends must not steal the label.

Usage::

    python3 scripts/niche_n02_practice.py              # eval existing heldout + write ckpt
    python3 scripts/niche_n02_practice.py --eval-only
    python3 scripts/niche_n02_practice.py --serve 'Classify … as kit. (kit/research/creative/defer)'
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# OVERSEER_NICHE_PRACTICE_N02_2026_09_07
NEEDLE = "OVERSEER_NICHE_PRACTICE_N02_2026_09_07"
ROOT = Path(__file__).resolve().parents[1]
DISTILL = ROOT / "notes" / "niche_distill"
TRAIN_JSONL = DISTILL / "N02_queue_kit_vs_research.jsonl"
HELDOUT_JSONL = DISTILL / "N02_queue_kit_vs_research_heldout.jsonl"
PRACTICE_DIR = DISTILL / "practice_n02"
CKPT_JSON = PRACTICE_DIR / "checkpoint.json"
WEIGHTS_DIR = PRACTICE_DIR / "weights"
WEIGHTS_PT = WEIGHTS_DIR / "n02_queue_kit_vs_research_practice.pt"

# Explicit cues only — do not match bare words inside trailing legends.
_LABEL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("kit", re.compile(r"(?:label\s*=\s*|as\s+|→\s*|\[|Factory\s+)kit\b", re.I)),
    (
        "research",
        re.compile(r"(?:label\s*=\s*|as\s+|→\s*|\[|Factory\s+)research\b", re.I),
    ),
    (
        "creative",
        re.compile(r"(?:label\s*=\s*|as\s+|→\s*|\[|Factory\s+)creative\b", re.I),
    ),
    ("defer", re.compile(r"(?:label\s*=\s*|as\s+|→\s*|\[|Factory\s+)defer\b", re.I)),
)

_PT_MAGIC = b"N02P"
_PT_VERSION = 1


@dataclass(frozen=True)
class EvalReport:
    niche_id: str
    n_train: int
    n_heldout: int
    heldout_accuracy: float
    pass_bar: float
    passed: bool
    checkpoint: str
    weights: str
    needle: str


def predict(item: str) -> dict[str, str]:
    """Rule baseline for N02 — first explicit kit/research/creative/defer cue."""
    text = (item or "").strip()
    for label, pat in _LABEL_PATTERNS:
        if pat.search(text):
            return {"label": label}
    return {"label": "unknown"}


def _exact_match(pred: dict[str, Any], gold: Any) -> bool:
    if not isinstance(gold, dict):
        return False
    return pred.get("label") == gold.get("label")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        rows.append(json.loads(raw))
    return rows


def write_checkpoint(*, n_train: int, n_heldout: int, accuracy: float) -> None:
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    rules = {
        "kind": "n02_rule_baseline",
        "version": _PT_VERSION,
        "needle": NEEDLE,
        "predict": "scripts/niche_n02_practice.py:predict",
        "grain": "~10M neural swap keeps this layout (see checkpoint_neural.json)",
        "cue_policy": "explicit as/label=/→/[X]/Factory X only; ignore legend lists",
    }
    payload = json.dumps(rules, separators=(",", ":")).encode("utf-8")
    blob = _PT_MAGIC + struct.pack(">HI", _PT_VERSION, len(payload)) + payload
    WEIGHTS_PT.write_bytes(blob)
    manifest = {
        "needle": NEEDLE,
        "niche_id": "N02",
        "niche": "queue_kit_vs_research",
        "checkpoint": str(CKPT_JSON.relative_to(ROOT)),
        "weights": str(WEIGHTS_PT.relative_to(ROOT)),
        "train_jsonl": str(TRAIN_JSONL.relative_to(ROOT)),
        "heldout_jsonl": str(HELDOUT_JSONL.relative_to(ROOT)),
        "n_train": n_train,
        "n_heldout": n_heldout,
        "heldout_accuracy": round(accuracy, 4),
        "pass_bar": 0.90,
        "passed": accuracy >= 0.90,
        "serve": "python3 scripts/niche_n02_practice.py --serve '<item>'",
        "recipe": "notes/niche_distill/RECIPE.md",
        "corpus_prune": False,
    }
    CKPT_JSON.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load_weights_pt(path: Path = WEIGHTS_PT) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw[:4] != _PT_MAGIC:
        raise ValueError(f"bad practice .pt magic: {path}")
    ver, n = struct.unpack(">HI", raw[4:10])
    if ver != _PT_VERSION:
        raise ValueError(f"unsupported practice .pt version {ver}")
    return json.loads(raw[10 : 10 + n].decode("utf-8"))


def eval_heldout(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    ok = 0
    for row in rows:
        pred = predict(str(row.get("input") or ""))
        if _exact_match(pred, row.get("output")):
            ok += 1
    return ok / len(rows)


def run_train_eval(*, write: bool = True) -> EvalReport:
    """Score existing heldout; optionally write rule ckpt. Never rewrites JSONL."""
    train_rows = load_jsonl(TRAIN_JSONL) if TRAIN_JSONL.is_file() else []
    if not HELDOUT_JSONL.is_file():
        raise FileNotFoundError(
            f"heldout missing (no corpus prune / no rewrite): {HELDOUT_JSONL}"
        )
    heldout = load_jsonl(HELDOUT_JSONL)
    acc = eval_heldout(heldout)
    if write:
        write_checkpoint(
            n_train=len(train_rows), n_heldout=len(heldout), accuracy=acc
        )
    return EvalReport(
        niche_id="N02",
        n_train=len(train_rows),
        n_heldout=len(heldout),
        heldout_accuracy=acc,
        pass_bar=0.90,
        passed=acc >= 0.90,
        checkpoint=str(CKPT_JSON.relative_to(ROOT)),
        weights=str(WEIGHTS_PT.relative_to(ROOT)),
        needle=NEEDLE,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--eval-only", action="store_true", help="score heldout; no ckpt write")
    p.add_argument("--serve", metavar="ITEM", help="label kit/research/creative/defer → JSON")
    p.add_argument("--json", action="store_true", help="print EvalReport as JSON")
    args = p.parse_args(argv)

    if args.serve is not None:
        print(json.dumps(predict(args.serve), ensure_ascii=False))
        return 0

    if args.eval_only:
        heldout = load_jsonl(HELDOUT_JSONL)
        acc = eval_heldout(heldout)
        report = EvalReport(
            niche_id="N02",
            n_train=0,
            n_heldout=len(heldout),
            heldout_accuracy=acc,
            pass_bar=0.90,
            passed=acc >= 0.90,
            checkpoint=str(CKPT_JSON.relative_to(ROOT)),
            weights=str(WEIGHTS_PT.relative_to(ROOT)),
            needle=NEEDLE,
        )
    else:
        report = run_train_eval(write=True)
        meta = load_weights_pt()
        assert meta.get("needle") == NEEDLE, meta

    if args.json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(
            f"N02 practice {NEEDLE}\n"
            f"  heldout={report.n_heldout} acc={report.heldout_accuracy:.3f} "
            f"pass_bar={report.pass_bar} passed={report.passed}\n"
            f"  checkpoint={report.checkpoint}\n"
            f"  weights={report.weights}"
        )
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
