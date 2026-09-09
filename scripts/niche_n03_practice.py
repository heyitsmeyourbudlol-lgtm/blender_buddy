#!/usr/bin/env python3
"""N03 land_proof_needle_match — P1 practice distill / eval / serve (N01 stamp).

OVERSEER_NICHE_P1_N03_N08_2026_09_06

Same recipe as N01: schema → train/heldout → niche accuracy → checkpoint → serve.
Deterministic rule baseline + ckpt under ``notes/niche_distill/practice_n03/``.

Usage::

    python3 scripts/niche_n03_practice.py              # train+eval+write ckpt
    python3 scripts/niche_n03_practice.py --eval-only
    python3 scripts/niche_n03_practice.py --serve '[kit] … Needle: `OVERSEER_X`.'
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

# OVERSEER_NICHE_P1_N03_N08_2026_09_06
NEEDLE = "OVERSEER_NICHE_P1_N03_N08_2026_09_06"
ROOT = Path(__file__).resolve().parents[1]
DISTILL = ROOT / "notes" / "niche_distill"
TRAIN_JSONL = DISTILL / "N03_land_proof_needle_match.jsonl"
HELDOUT_JSONL = DISTILL / "N03_land_proof_needle_match_heldout.jsonl"
PRACTICE_DIR = DISTILL / "practice_n03"
CKPT_JSON = PRACTICE_DIR / "checkpoint.json"
WEIGHTS_DIR = PRACTICE_DIR / "weights"
WEIGHTS_PT = WEIGHTS_DIR / "n03_land_proof_needle_match_practice.pt"

# Prefer Needle: `OVERSEER_…`; else first OVERSEER_* token (anti false-[x] → null).
_NEEDLE_LABELED_RE = re.compile(
    r"(?:Needle|landed(?:\s+overseer)?)\s*:\s*`?(OVERSEER_[A-Z0-9_]+)`?",
    re.I,
)
_NEEDLE_TICK_RE = re.compile(r"`(OVERSEER_[A-Z0-9_]+)`")
_NEEDLE_BARE_RE = re.compile(r"\b(OVERSEER_[A-Z0-9_]+)\b")

_PT_MAGIC = b"N03P"
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


def _bare_path_fragment(text: str, start: int, token: str) -> bool:
    """P2 — reject bare OVERSEER_* stolen from paths (notes/OVERSEER_NOTES.md)."""
    if start > 0 and text[start - 1] in "/\\":
        return True
    end = start + len(token)
    if end < len(text) and text[end] == ".":
        return True
    return False


def predict(item: str) -> str | None:
    """Rule baseline for N03 — earliest claimable OVERSEER by position, else null.

    Document order beats labeled-first search so land-proof twin ticks before a
    later ``Needle:`` primary (P1-G1 / STRESS_GAPS). Labeled / tick / bare are
    only match shapes — not priority tiers. Bare path fragments are skipped (P2).
    """
    text = (item or "").strip()
    if not text:
        return None
    cands: list[tuple[int, str]] = []
    for rx in (_NEEDLE_LABELED_RE, _NEEDLE_TICK_RE, _NEEDLE_BARE_RE):
        for m in rx.finditer(text):
            start, tok = m.start(1), m.group(1)
            if rx is _NEEDLE_BARE_RE and _bare_path_fragment(text, start, tok):
                continue
            cands.append((start, tok))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0])
    return cands[0][1]


def _exact_match(pred: str | None, gold: Any) -> bool:
    return pred == gold


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        rows.append(json.loads(raw))
    return rows


def split_train_heldout(
    rows: list[dict[str, Any]], *, hold_frac: float = 0.2
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministic ~20% heldout (every 5th row) — recipe stamp, not RNG."""
    heldout: list[dict[str, Any]] = []
    train: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if (i % 5) == 4:
            heldout.append(row)
        else:
            train.append(row)
    if not heldout and rows:
        heldout = [rows[-1]]
        train = rows[:-1]
    _ = hold_frac
    return train, heldout


def write_heldout(rows: list[dict[str, Any]]) -> None:
    HELDOUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with HELDOUT_JSONL.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_checkpoint(*, n_train: int, n_heldout: int, accuracy: float) -> None:
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    rules = {
        "kind": "n03_rule_baseline",
        "version": _PT_VERSION,
        "needle": NEEDLE,
        "predict": "scripts/niche_n03_practice.py:predict",
        "grain": "~10M neural swap keeps this layout",
    }
    payload = json.dumps(rules, separators=(",", ":")).encode("utf-8")
    blob = _PT_MAGIC + struct.pack(">HI", _PT_VERSION, len(payload)) + payload
    WEIGHTS_PT.write_bytes(blob)
    manifest = {
        "needle": NEEDLE,
        "niche_id": "N03",
        "niche": "land_proof_needle_match",
        "checkpoint": str(CKPT_JSON.relative_to(ROOT)),
        "weights": str(WEIGHTS_PT.relative_to(ROOT)),
        "train_jsonl": str(TRAIN_JSONL.relative_to(ROOT)),
        "heldout_jsonl": str(HELDOUT_JSONL.relative_to(ROOT)),
        "n_train": n_train,
        "n_heldout": n_heldout,
        "heldout_accuracy": round(accuracy, 4),
        "pass_bar": 0.90,
        "passed": accuracy >= 0.90,
        "serve": "python3 scripts/niche_n03_practice.py --serve '<item>'",
        "recipe": "notes/niche_distill/RECIPE.md",
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
    rows = load_jsonl(TRAIN_JSONL)
    train, heldout = split_train_heldout(rows)
    if write:
        write_heldout(heldout)
    acc = eval_heldout(heldout)
    if write:
        write_checkpoint(n_train=len(train), n_heldout=len(heldout), accuracy=acc)
    return EvalReport(
        niche_id="N03",
        n_train=len(train),
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
    p.add_argument("--eval-only", action="store_true", help="score heldout; no rewrite")
    p.add_argument("--serve", metavar="ITEM", help="extract land-proof needle → JSON")
    p.add_argument("--json", action="store_true", help="print EvalReport as JSON")
    args = p.parse_args(argv)

    if args.serve is not None:
        print(json.dumps(predict(args.serve), ensure_ascii=False))
        return 0

    if args.eval_only:
        if HELDOUT_JSONL.is_file():
            heldout = load_jsonl(HELDOUT_JSONL)
        else:
            _, heldout = split_train_heldout(load_jsonl(TRAIN_JSONL))
        acc = eval_heldout(heldout)
        report = EvalReport(
            niche_id="N03",
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
            f"N03 practice {NEEDLE}\n"
            f"  heldout={report.n_heldout} acc={report.heldout_accuracy:.3f} "
            f"pass_bar={report.pass_bar} passed={report.passed}\n"
            f"  checkpoint={report.checkpoint}\n"
            f"  weights={report.weights}"
        )
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
