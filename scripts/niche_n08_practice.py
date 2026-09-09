#!/usr/bin/env python3
"""N08 stall_class_label — P1 practice distill / eval / serve (N01 stamp).

OVERSEER_NICHE_P1_N03_N08_2026_09_06

Same recipe as N01: schema → train/heldout → niche accuracy → checkpoint → serve.
Deterministic rule baseline + ckpt under ``notes/niche_distill/practice_n08/``.

Usage::

    python3 scripts/niche_n08_practice.py              # train+eval+write ckpt
    python3 scripts/niche_n08_practice.py --eval-only
    python3 scripts/niche_n08_practice.py --serve '{"status":"…","log":"…"}'
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
TRAIN_JSONL = DISTILL / "N08_stall_class_label.jsonl"
HELDOUT_JSONL = DISTILL / "N08_stall_class_label_heldout.jsonl"
PRACTICE_DIR = DISTILL / "practice_n08"
CKPT_JSON = PRACTICE_DIR / "checkpoint.json"
WEIGHTS_DIR = PRACTICE_DIR / "weights"
WEIGHTS_PT = WEIGHTS_DIR / "n08_stall_class_label_practice.pt"

_STALL_CLASSES = (
    "plan_gate_blocked",
    "verify_fail_agent_exit",
    "verify_fail_tests",
    "adapt_stale",
    "queue_drift",
    "peer_quiet",
    "namespace_flip",
    "oversight_down",
    "loaded_no_pid",
    "noop_stall",
    "deferred_lean_restamp",
    "last_cycle_poison",
    "chicken_egg",
    "dirty_tree_notes_only",
    "healthy",
)

_PT_MAGIC = b"N08P"
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


def _blob(inp: Any) -> tuple[str, str, str]:
    if isinstance(inp, dict):
        status = str(inp.get("status") or "")
        log = str(inp.get("log") or "")
    elif isinstance(inp, str):
        try:
            obj = json.loads(inp)
        except json.JSONDecodeError:
            return inp.lower(), "", inp.lower()
        if isinstance(obj, dict):
            status = str(obj.get("status") or "")
            log = str(obj.get("log") or "")
        else:
            return inp.lower(), "", inp.lower()
    else:
        return "", "", ""
    return status.lower(), log.lower(), f"{status}\n{log}".lower()


def predict(inp: Any) -> str:
    """Rule baseline for N08 — priority-ordered stall class from status+log."""
    _status, _log, both = _blob(inp)

    # Soft plan-gate warn only (dispatch continues) — not "soft warn ignored".
    if "plan-gate soft" in both:
        return "healthy"

    # Chicken-egg before plain plan_gate / adapt / verify.
    if "chicken-egg" in both or "chicken_egg" in both:
        return "chicken_egg"
    if (
        "plan-gate" in both
        and ("verify_ok=false" in both or "verify fail" in both)
        and ("adapt" in both or "queue drift" in both or "nobody fixes" in both)
    ):
        return "chicken_egg"

    # Explicit bottleneck ids (stall-watch stamp).
    bm = re.search(r"bottleneck\s+id=([a-z0-9_]+)", both)
    if bm:
        bid = bm.group(1)
        if bid == "queue_drift":
            return "queue_drift"
        if bid == "adapt_stale":
            return "adapt_stale"
        if bid in ("verify_fail_hold", "verify_fail_tests"):
            return "verify_fail_tests"
        if bid == "noop_stall":
            return "noop_stall"
        if bid == "deferred_lean_restamp":
            return "deferred_lean_restamp"
        if bid in ("last_cycle_deferred_poison", "last_cycle_poison"):
            return "last_cycle_poison"
        if bid == "verify_fail_agent_exit":
            return "verify_fail_agent_exit"

    # Typed verify failures before substring traps (e.g. test_queue_drift).
    if "failure_type=tests" in both or "unittest fail" in both:
        return "verify_fail_tests"
    if "failure_type=timeout" in both and "verify" in both:
        return "verify_fail_tests"

    if (
        "failure_type=agent_exit" in both
        or "cursor-agent non-zero" in both
        # Live peer_watch Cycle rows include rc=0 · verify=ok — must not trap as agent_exit
        # (P1-G7). Only non-zero rc= counts.
        or re.search(r"\brc=[1-9]\d*\b", both)
        or "verify quiet" in both
        or "agent_cap" in both
    ):
        return "verify_fail_agent_exit"

    # Improve daemon down before namespace heuristics ("wrong namespace" in log).
    if "improve not 24/7" in both and "stopped" in both:
        return "oversight_down"
    # Live peer_watch / LaunchAgent blobs: "improve LaunchAgent STOPPED".
    if re.search(r"\bimprove\b.{0,40}\bstopped\b", both):
        return "oversight_down"
    if "oversight stopped" in both or (
        "oversight" in both and ("stopped" in both or "not running" in both)
    ):
        return "oversight_down"
    # peer-progress-watch snap: peer_up=false / improve_up=false (P2-G5).
    if "peer_up=false" in both or "improve_up=false" in both:
        return "oversight_down"
    if "peer_up false" in both or "improve_up false" in both:
        return "oversight_down"

    if "queue drift" in both or re.search(r"(?<![a-z0-9_])queue_drift(?![a-z0-9_])", both):
        return "queue_drift"
    if "work_queue" in both and (
        "self_improve_context" in both or "drift=" in both or "!=" in both
    ):
        return "queue_drift"
    if "active corrupt" in both or "pasted self-check" in both:
        return "queue_drift"

    # loaded_no_pid before namespace_flip — hub LaunchAgent id contains
    # automation-hub-peer-loop and must not steal loaded-no-pid (P2).
    if "loaded-no-pid" in both or "loaded_no_pid" in both:
        return "loaded_no_pid"

    if (
        "dual launchagent" in both
        or "wrong launchagent" in both
        or ("config_namespace" in both and ("flip" in both or "→" in both or "->" in both))
        or "automation-hub-peer-loop" in both
    ):
        return "namespace_flip"

    # P2-G8: green WORKING / Cycle rc=0·verify=ok before peer_quiet — live
    # `peer status` paints "log quiet until subprocess" under STATE●WORKING.
    if (
        "lean-green" in both
        or "lean_green=no-hold" in both
        or (re.search(r"\brc=0\b", both) and "verify=ok" in both)
        or ("verify_ok=true" in both and "noop=false" in both)
        or ("verify_ok=true" in both and "healed" in both)
        or ("idle empty active" in both and "seed" in both)
    ):
        return "healthy"

    if (
        "peer quiet" in both
        or "peer log quiet" in both
        # Do NOT match UI chrome "log quiet until subprocess" (WORKING state).
        or "poke no-op" in both
    ):
        return "peer_quiet"

    if (
        "porcelain only notes/" in both
        or "porcelain notes/" in both
        or "notes-only porcelain" in both
        or "notes only porcelain" in both
        or "git dirty notes-only" in both
        or "dirty_tree_notes_only" in both
        or ("notes-only" in both and "porcelain" in both)
    ):
        return "dirty_tree_notes_only"

    # last_cycle_poison: contiguous phrase, failure_type=deferred, OR live
    # triad last_cycle + deferred + verify_ok (without requiring failure_type=).
    # Must stay before green short-circuit so verify_ok=true does not → healthy.
    if "last_cycle poison" in both or (
        "failure_type=deferred" in both
        and (
            "verify_ok=true" in both
            or re.search(r"verify_ok\s*=?\s*true", both) is not None
            or ("last_cycle" in both and "verify_ok" in both)
        )
    ) or (
        "last_cycle" in both
        and "deferred" in both
        and (
            "verify_ok=true" in both
            or re.search(r"verify_ok\s*=?\s*true", both) is not None
            or "verify_ok" in both
        )
        and "deferred_lean" not in both
        and "lean verify" not in both
    ):
        return "last_cycle_poison"

    if (
        "deferred_lean_restamp" in both
        or "deferred-swarm" in both
        or ("deferred" in both and "lean" in both and "restamp" in both)
        or ("waiting" in both and "deferred" in both and "lean" in both)
    ):
        return "deferred_lean_restamp"

    if "noop_backoff" in both or "noop_stall" in both or "idle theater" in both:
        return "noop_stall"

    if "plan-gate blocked" in both or (
        "plan-gate" in both and ("hard-fail" in both or "skip primary" in both)
    ):
        if "chicken" not in both:
            return "plan_gate_blocked"

    # P2-G1: green Cycle / last_cycle short-circuit *before* residual "adapt_stale"
    # substring (e.g. "adapt_stale healed" under Cycle rc=0 · verify=ok). Active
    # adapt still wins via bottleneck id= / should_re_adapt / ADAPT_STALE earlier.
    if (
        "lean-green" in both
        or "lean_green=no-hold" in both
        or (re.search(r"\brc=0\b", both) and "verify=ok" in both)
        or ("verify_ok=true" in both and "noop=false" in both)
        or ("verify_ok=true" in both and "healed" in both)
        or ("idle empty active" in both and "seed" in both)
    ):
        return "healthy"

    if "adapt_stale" in both or "should_re_adapt" in both:
        return "adapt_stale"

    return "healthy"


def _exact_match(pred: str, gold: Any) -> bool:
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
        "kind": "n08_rule_baseline",
        "version": _PT_VERSION,
        "needle": NEEDLE,
        "predict": "scripts/niche_n08_practice.py:predict",
        "classes": list(_STALL_CLASSES),
        "grain": "~10M neural swap keeps this layout",
    }
    payload = json.dumps(rules, separators=(",", ":")).encode("utf-8")
    blob = _PT_MAGIC + struct.pack(">HI", _PT_VERSION, len(payload)) + payload
    WEIGHTS_PT.write_bytes(blob)
    manifest = {
        "needle": NEEDLE,
        "niche_id": "N08",
        "niche": "stall_class_label",
        "checkpoint": str(CKPT_JSON.relative_to(ROOT)),
        "weights": str(WEIGHTS_PT.relative_to(ROOT)),
        "train_jsonl": str(TRAIN_JSONL.relative_to(ROOT)),
        "heldout_jsonl": str(HELDOUT_JSONL.relative_to(ROOT)),
        "n_train": n_train,
        "n_heldout": n_heldout,
        "heldout_accuracy": round(accuracy, 4),
        "pass_bar": 0.90,
        "passed": accuracy >= 0.90,
        "serve": "python3 scripts/niche_n08_practice.py --serve '{\"status\":\"…\",\"log\":\"…\"}'",
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
        pred = predict(row.get("input"))
        if _exact_match(pred, row.get("output")):
            ok += 1
    return ok / len(rows)


def eval_full(rows: list[dict[str, Any]]) -> tuple[float, list[tuple[int, str, str]]]:
    """Score all rows; return accuracy + miss list (idx, pred, gold)."""
    misses: list[tuple[int, str, str]] = []
    if not rows:
        return 0.0, misses
    ok = 0
    for i, row in enumerate(rows):
        pred = predict(row.get("input"))
        gold = row.get("output")
        if _exact_match(pred, gold):
            ok += 1
        else:
            misses.append((i, pred, str(gold)))
    return ok / len(rows), misses


def run_train_eval(*, write: bool = True) -> EvalReport:
    rows = load_jsonl(TRAIN_JSONL)
    train, heldout = split_train_heldout(rows)
    if write:
        write_heldout(heldout)
    acc = eval_heldout(heldout)
    if write:
        write_checkpoint(n_train=len(train), n_heldout=len(heldout), accuracy=acc)
    return EvalReport(
        niche_id="N08",
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
    p.add_argument(
        "--serve",
        metavar="JSON",
        help='classify one status+log blob → stall class JSON string',
    )
    p.add_argument("--json", action="store_true", help="print EvalReport as JSON")
    p.add_argument(
        "--debug-full",
        action="store_true",
        help="score full train JSONL and print misses",
    )
    args = p.parse_args(argv)

    if args.serve is not None:
        print(json.dumps(predict(args.serve), ensure_ascii=False))
        return 0

    if args.debug_full:
        rows = load_jsonl(TRAIN_JSONL)
        acc, misses = eval_full(rows)
        print(f"full={len(rows)} acc={acc:.3f} misses={len(misses)}")
        for i, pred, gold in misses:
            print(f"  [{i}] pred={pred!r} gold={gold!r}")
        return 0 if acc >= 0.90 else 1

    if args.eval_only:
        if HELDOUT_JSONL.is_file():
            heldout = load_jsonl(HELDOUT_JSONL)
        else:
            _, heldout = split_train_heldout(load_jsonl(TRAIN_JSONL))
        acc = eval_heldout(heldout)
        report = EvalReport(
            niche_id="N08",
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
            f"N08 practice {NEEDLE}\n"
            f"  heldout={report.n_heldout} acc={report.heldout_accuracy:.3f} "
            f"pass_bar={report.pass_bar} passed={report.passed}\n"
            f"  checkpoint={report.checkpoint}\n"
            f"  weights={report.weights}"
        )
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
