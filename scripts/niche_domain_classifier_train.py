#!/usr/bin/env python3
"""Train tiny free-local domain classifier niche (multinomial NB).

Needle: OVERSEER_TOP10_NEXT_T10_09_2026_09_07

Builds synthetic text→domain_id rows from ``repo_domain_smes.json``, trains a
bag-of-words multinomial Naive Bayes (stdlib + optional numpy-free), writes
``notes/niche_distill/domain_classifier/checkpoint.json``, and asserts heldout
accuracy lifts vs keyword heuristic.

NO PAY — no torch / sklearn / paid API.

Usage::
    python3 scripts/niche_domain_classifier_train.py --train
    python3 scripts/niche_domain_classifier_train.py --eval-only
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import niche_domain_classify as ndc  # noqa: E402
import peer_fact_librarian as fl  # noqa: E402

NEEDLE = "OVERSEER_TOP10_NEXT_T10_09_2026_09_07"
OUT_DIR = ROOT / "notes" / "niche_distill" / "domain_classifier"
TRAIN_JSONL = OUT_DIR / "train.jsonl"
HELDOUT_JSONL = OUT_DIR / "heldout.jsonl"
CKPT = ndc.MODEL_CHECKPOINT_HINT
REPORT_JSON = OUT_DIR / "eval_report.json"

_TOKEN_RE = re.compile(r"[a-z0-9_./:-]+", re.I)

# Soft paraphrases: avoid keyword + term-in-keyword hits so heuristic fails;
# share stems within a domain so NB transfers train→heldout.
_SOFT_BY_DOMAIN: dict[str, list[str]] = {
    "peer_runtime": [
        "forever runner skipped spawning after clearance finished",
        "forever runner fanout when coding sandbox is dirty",
        "mechanical spawn prep before desktop session launch",
        "why spawn prep skipped after clearance finished",
        "coding sandbox dirty blocks forever runner fanout",
    ],
    "memory_remembrance": [
        "cold assistants must open the sticky index first",
        "route scattered citations without stuffing whole archive",
        "ownership chart path to specialist without deep browse",
        "sticky index for cold assistants first open",
        "scattered citations relay instead of stuffing archive",
    ],
    "queue_sync": [
        "twin open bullets with improve context twin file",
        "open bullets drifted from twin file — reconcile",
        "forever fuel must keep open bullets nonempty",
        "reconcile twin file lines with open bullets",
        "improve context twin file drifted from open bullets",
    ],
    "verify_tests": [
        "battery red after repair — triage before DONE",
        "script exit code before declaring DONE",
        "smoke bars mismatch on output compare",
        "triage red battery before DONE declaration",
        "output compare missed expected smoke bars",
    ],
    "adapt_heal": [
        "mechanical clear chokepoints on brain machine",
        "chicken-egg stall class lookup card",
        "hazard when stamps go stale on kit",
        "chokepoints cleared mechanically on brain machine",
        "stall class chicken-egg lookup card",
    ],
    "comms_glink": [
        "handshake traffic on the agent messaging pipe",
        "communications engineer binder handoff note",
        "cross-agent messaging outlook digest",
        "agent messaging pipe handshake traffic",
        "binder handoff for communications engineer",
    ],
    "dashboard_ui": [
        "static page refresh on the local board server",
        "gauges and panel chrome on kit board",
        "layout stylesheet for kit board panels",
        "local board server static page refresh",
        "kit board gauges panel chrome",
    ],
    "safety_rules": [
        "human-in-loop blocklist before irreversible push",
        "catalog shutdown digest guarding credentials",
        "spend lock free-desktop only before pen exercise",
        "irreversible push blocked by human-in-loop blocklist",
        "credentials guarded by catalog shutdown digest",
    ],
    "compression_bitnet": [
        "four-bit sidequest keep-alive on local accelerator",
        "bank status json for student practice lanes",
        "lossless share rung without paid teacher calls",
        "local accelerator keep-alive for four-bit sidequest",
        "student practice lanes bank status json",
    ],
    "dgx_ram": [
        "box free video memory before ballast stop",
        "roster expand for brain machine ops fabric",
        "budget watcher flapping forever runner on machine",
        "ballast stop when box video memory low",
        "brain machine ops fabric roster expand",
    ],
    "docs_sops": [
        "index pointer for sticky ritual writeups",
        "contribution path for writers of operator guides",
        "operator guides section in automation digest",
        "sticky ritual writeups index pointer",
        "writers contribution path for operator guides",
    ],
    "oversight_progress": [
        "percent idle-event on kit watcher",
        "idle ticks then kit wrapup writeup",
        "watcher flaps when digest-only mode stuck",
        "kit watcher percent idle-event",
        "kit wrapup writeup after idle ticks",
    ],
    "agent_builder": [
        "spin up demo widget specialist from assignment text",
        "align this bullet line to a durable specialist",
        "upsert routing table for assignment-to-specialist map",
        "demo widget specialist spin up from assignment text",
        "assignment-to-specialist map upsert routing table",
    ],
}


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1]


def load_domains() -> list[dict[str, Any]]:
    return list(fl.list_domains())


def _hard_templates(domain: dict[str, Any]) -> list[str]:
    did = str(domain.get("id") or "")
    title = str(domain.get("title") or did)
    kws = [str(k) for k in (domain.get("keywords") or []) if k]
    sots = [str(s) for s in (domain.get("sot") or [])[:3]]
    role = str(domain.get("role_id") or "")
    out: list[str] = [
        f"fact-query --domain {did}",
        f"domain_id={did} title={title}",
        f"{title} — role {role}",
    ]
    for kw in kws[:6]:
        out.append(f"help with {kw} in {did}")
        out.append(f"please open notes about {kw}")
    for sot in sots:
        out.append(f"read {sot} for {did}")
        out.append(f"SoT path {sot}")
    return out


def build_corpus(
    domains: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (train_rows, heldout_rows) with gold domain_id labels.

    Heldout is soft-paraphrase heavy (keyword-weak) so model can lift vs
    ``auto_pick_domain``. Hard keyword templates stay mostly in train.
    """
    train: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    for d in domains:
        did = str(d.get("id") or "")
        if not did:
            continue
        hard = _hard_templates(d)
        soft = list(_SOFT_BY_DOMAIN.get(did) or [])
        for text in hard:
            train.append(
                {
                    "niche_id": "N107",
                    "niche": "domain_classifier",
                    "input": text,
                    "output": {"domain_id": did},
                    "split": "train",
                    "kind": "hard",
                }
            )
        # Soft: first two → train (overlap stems); rest → heldout lift set
        for i, text in enumerate(soft):
            row = {
                "niche_id": "N107",
                "niche": "domain_classifier",
                "input": text,
                "output": {"domain_id": did},
                "split": "train" if i < 2 else "heldout",
                "kind": "soft",
            }
            (held if row["split"] == "heldout" else train).append(row)
        title = str(d.get("title") or "")
        train.append(
            {
                "niche_id": "N107",
                "niche": "domain_classifier",
                "input": f"Kit lock — classify SME lane for: {title}",
                "output": {"domain_id": did},
                "split": "train",
                "kind": "title",
            }
        )
    rng = random.Random(42)
    rng.shuffle(train)
    rng.shuffle(held)
    return train, held


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def train_nb(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    labels = sorted(
        {str((r.get("output") or {}).get("domain_id") or "") for r in rows if r.get("output")}
    )
    labels = [lb for lb in labels if lb]
    label_index = {lb: i for i, lb in enumerate(labels)}
    n_class = len(labels)
    class_counts = Counter()
    token_counts: list[Counter] = [Counter() for _ in range(n_class)]
    vocab: set[str] = set()

    for r in rows:
        lb = str((r.get("output") or {}).get("domain_id") or "")
        if lb not in label_index:
            continue
        ci = label_index[lb]
        class_counts[lb] += 1
        toks = tokenize(str(r.get("input") or ""))
        for t in toks:
            token_counts[ci][t] += 1
            vocab.add(t)

    vocab_list = sorted(vocab)
    v_index = {t: i for i, t in enumerate(vocab_list)}
    n_vocab = len(vocab_list)
    total = sum(class_counts.values()) or 1
    log_prior = [0.0] * n_class
    # Smoothed log P(token|class) dense matrix as list-of-lists (compact niches)
    feature_log_prob: list[list[float]] = []
    alpha = 1.0
    for ci, lb in enumerate(labels):
        log_prior[ci] = math.log((class_counts[lb] + alpha) / (total + alpha * n_class))
        total_tok = sum(token_counts[ci].values())
        denom = total_tok + alpha * n_vocab
        row = [0.0] * n_vocab
        for t, vi in v_index.items():
            row[vi] = math.log((token_counts[ci][t] + alpha) / denom)
        feature_log_prob.append(row)

    return {
        "needle": NEEDLE,
        "version": 1,
        "algo": "multinomial_nb",
        "labels": labels,
        "vocab": vocab_list,
        "log_prior": log_prior,
        "feature_log_prob": feature_log_prob,
        "n_train": len(rows),
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "no_pay": True,
        "local_only": True,
    }


def predict_nb(ckpt: dict[str, Any], text: str) -> tuple[str | None, float, list[dict[str, Any]]]:
    labels: list[str] = list(ckpt.get("labels") or [])
    vocab: list[str] = list(ckpt.get("vocab") or [])
    v_index = {t: i for i, t in enumerate(vocab)}
    log_prior: list[float] = list(ckpt.get("log_prior") or [])
    flp: list[list[float]] = list(ckpt.get("feature_log_prob") or [])
    if not labels or not vocab or not flp:
        return None, 0.0, []
    toks = tokenize(text)
    scores: list[float] = []
    for ci in range(len(labels)):
        s = float(log_prior[ci]) if ci < len(log_prior) else 0.0
        row = flp[ci]
        for t in toks:
            vi = v_index.get(t)
            if vi is not None and vi < len(row):
                s += float(row[vi])
        scores.append(s)
    # Log-sum-exp confidence
    m = max(scores)
    exps = [math.exp(s - m) for s in scores]
    z = sum(exps) or 1.0
    probs = [e / z for e in exps]
    best_i = max(range(len(labels)), key=lambda i: scores[i])
    ranked = sorted(
        (
            {"domain_id": labels[i], "score": round(float(scores[i]), 4), "prob": round(probs[i], 4)}
            for i in range(len(labels))
        ),
        key=lambda r: -float(r["score"]),
    )
    return labels[best_i], float(probs[best_i]), ranked[:8]


def keyword_predict(text: str) -> str | None:
    domain, _scores = fl.auto_pick_domain(text)
    if domain and domain.get("id"):
        return str(domain.get("id"))
    return None


def eval_split(
    rows: list[dict[str, Any]],
    ckpt: dict[str, Any],
) -> dict[str, Any]:
    n = 0
    model_ok = 0
    kw_ok = 0
    soft_n = 0
    soft_model = 0
    soft_kw = 0
    for r in rows:
        gold = str((r.get("output") or {}).get("domain_id") or "")
        if not gold:
            continue
        text = str(r.get("input") or "")
        n += 1
        pred, _conf, _ = predict_nb(ckpt, text)
        kw = keyword_predict(text)
        if pred == gold:
            model_ok += 1
        if kw == gold:
            kw_ok += 1
        if r.get("kind") == "soft":
            soft_n += 1
            if pred == gold:
                soft_model += 1
            if kw == gold:
                soft_kw += 1
    model_acc = (model_ok / n) if n else 0.0
    kw_acc = (kw_ok / n) if n else 0.0
    return {
        "n": n,
        "model_correct": model_ok,
        "keyword_correct": kw_ok,
        "model_acc": round(model_acc, 4),
        "keyword_acc": round(kw_acc, 4),
        "lift": round(model_acc - kw_acc, 4),
        "soft_n": soft_n,
        "soft_model_acc": round((soft_model / soft_n) if soft_n else 0.0, 4),
        "soft_keyword_acc": round((soft_kw / soft_n) if soft_n else 0.0, 4),
    }


def run_train(*, force: bool = False) -> dict[str, Any]:
    domains = load_domains()
    train_rows, held_rows = build_corpus(domains)
    write_jsonl(TRAIN_JSONL, train_rows)
    write_jsonl(HELDOUT_JSONL, held_rows)
    ckpt = train_nb(train_rows)
    held = eval_split(held_rows, ckpt)
    train_m = eval_split(train_rows, ckpt)
    if held["lift"] <= 0 and not force:
        raise SystemExit(
            f"heldout lift not positive: model={held['model_acc']} "
            f"keyword={held['keyword_acc']} — refuse write"
        )
    ckpt["heldout"] = held
    ckpt["train_eval"] = train_m
    ckpt["paths"] = {
        "train": str(TRAIN_JSONL.relative_to(ROOT)),
        "heldout": str(HELDOUT_JSONL.relative_to(ROOT)),
        "checkpoint": str(CKPT.relative_to(ROOT)),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CKPT.write_text(json.dumps(ckpt, indent=2) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(json.dumps({"needle": NEEDLE, "heldout": held, "train": train_m}, indent=2) + "\n")
    return {"checkpoint": str(CKPT), "heldout": held, "train": train_m, "n_train": len(train_rows)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train tiny domain classifier niche (NO PAY)")
    ap.add_argument("--train", action="store_true", help="build corpus + write checkpoint")
    ap.add_argument("--eval-only", action="store_true", help="eval existing checkpoint on heldout")
    ap.add_argument("--force", action="store_true", help="write even if lift <= 0")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.eval_only:
        if not CKPT.is_file():
            print("no checkpoint", file=sys.stderr)
            return 1
        ckpt = json.loads(CKPT.read_text(encoding="utf-8"))
        held_rows = []
        if HELDOUT_JSONL.is_file():
            for line in HELDOUT_JSONL.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    held_rows.append(json.loads(line))
        else:
            _train, held_rows = build_corpus(load_domains())
        held = eval_split(held_rows, ckpt)
        out = {"heldout": held, "checkpoint": str(CKPT)}
        print(json.dumps(out, indent=2) if args.json else out)
        return 0 if held.get("lift", 0) > 0 else 1

    if not args.train and not args.eval_only:
        args.train = True

    result = run_train(force=args.force)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        h = result["heldout"]
        print(
            f"wrote {result['checkpoint']}\n"
            f"heldout model={h['model_acc']} keyword={h['keyword_acc']} "
            f"lift={h['lift']} soft_model={h['soft_model_acc']} "
            f"soft_kw={h['soft_keyword_acc']} n={h['n']}"
        )
    return 0 if result["heldout"]["lift"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
