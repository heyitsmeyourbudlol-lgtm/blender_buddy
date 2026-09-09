#!/usr/bin/env python3
"""Validate niche distill JSONL — schema check + anti-prune floors.

OVERSEER_NICHE_DISTILL_VALIDATE_2026_09_05
Needle land: OVERSEER_NICHE_GEN_ALL_SKIP_EXISTING_2026_09_08

Dataset curator gate: grow/validate schemas; NEVER prune rows to inflate
heldout accuracy (S21: schema-frozen; no row drop).

Usage::

    python3 scripts/niche_distill_validate.py
    python3 scripts/niche_distill_validate.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

NEEDLE = "OVERSEER_NICHE_DISTILL_VALIDATE_2026_09_05"
ROOT = Path(__file__).resolve().parents[1]
DISTILL = ROOT / "notes" / "niche_distill"

# Anti-prune floors — counts may only rise (score-inflation ban).
# Bump after intentional append-only expands; never lower.
# Locked 2026-09-08 dataset_curator (gen_all skip_existing + live appends).
# FLOOR_FLOOR_MIN: never-below baselines (N02/N04 intentional dups @96).

FLOOR_FLOOR_MIN: dict[str, int] = {
    "N01_queue_bullet_parse.jsonl": 60,
    "N01_queue_bullet_parse_heldout.jsonl": 12,
    "N03_land_proof_needle_match.jsonl": 63,
    "N03_land_proof_needle_match_heldout.jsonl": 12,
    "N08_stall_class_label.jsonl": 63,
    "N08_stall_class_label_heldout.jsonl": 14,
    "N02_queue_kit_vs_research.jsonl": 96,
    "N02_queue_kit_vs_research_heldout.jsonl": 16,
    "N04_active_empty_seed_pick.jsonl": 96,
    "N04_active_empty_seed_pick_heldout.jsonl": 16,
}

FLOOR_ROWS: dict[str, int] = {
    "N01_queue_bullet_parse.jsonl": 68,
    "N01_queue_bullet_parse_heldout.jsonl": 24,
    "N03_land_proof_needle_match.jsonl": 63,
    "N03_land_proof_needle_match_heldout.jsonl": 12,
    "N08_stall_class_label.jsonl": 67,
    "N08_stall_class_label_heldout.jsonl": 16,
    "N02_queue_kit_vs_research.jsonl": 98,
    "N02_queue_kit_vs_research_heldout.jsonl": 16,
    "N04_active_empty_seed_pick.jsonl": 96,
    "N04_active_empty_seed_pick_heldout.jsonl": 16,
}
# Alias for callers / tests preferring the bank-wide name.
ANTI_PRUNE_FLOORS = FLOOR_ROWS


def effective_floor(name: str) -> int:
    """Rise-only floor: max(FLOOR_ROWS, FLOOR_FLOOR_MIN)."""
    return max(FLOOR_ROWS.get(name, 0), FLOOR_FLOOR_MIN.get(name, 0))


# Suffix filters — use endswith, NEVER substring ``_stamp`` / ``_heldout``
# (N65_last_resort_stamp_seed / N74_heldout_split_ok false-exclude primaries).
_STAMP_SUFFIXES = ("_stamp.jsonl", "_stamp_heldout.jsonl")
_HELDOUT_SUFFIX = "_heldout.jsonl"

N08_ENUM = frozenset(
    {
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
    }
)

REQUIRED = ("niche_id", "input", "output")


def _is_corpus_jsonl(name: str) -> bool:
    """Primary or heldout niche corpora — not mint logs / stamps / bank status."""
    if not name.endswith(".jsonl"):
        return False
    if not name.startswith("N"):
        return False
    if name.endswith(_STAMP_SUFFIXES):
        return False
    return True


def is_primary_jsonl(name: str) -> bool:
    """True for train primaries (excludes heldout + stamps). endswith-only filters."""
    if not _is_corpus_jsonl(name):
        return False
    return not name.endswith(_HELDOUT_SUFFIX)


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    if not path.is_file():
        return rows, [f"{path.name}: missing file"]
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(f"{path.name}:{i}: JSON {exc}")
            continue
        if not isinstance(obj, dict):
            issues.append(f"{path.name}:{i}: not an object")
            continue
        for key in REQUIRED:
            if key not in obj:
                issues.append(f"{path.name}:{i}: missing {key}")
        rows.append(obj)
    return rows, issues


def _check_n01(path: Path, rows: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    for i, row in enumerate(rows, 1):
        if row.get("niche_id") != "N01":
            issues.append(f"{path.name}:{i}: niche_id want N01")
        if not isinstance(row.get("input"), str):
            issues.append(f"{path.name}:{i}: input must be string")
        out = row.get("output")
        if not isinstance(out, dict):
            issues.append(f"{path.name}:{i}: output must be object")
            continue
        if set(out.keys()) != {"kit", "scope", "needle"}:
            issues.append(f"{path.name}:{i}: output keys must be kit/scope/needle")
            continue
        if out["kit"] is not None and not isinstance(out["kit"], bool):
            issues.append(f"{path.name}:{i}: kit must be bool|null")
        if not isinstance(out["scope"], str):
            issues.append(f"{path.name}:{i}: scope must be string")
        if out["needle"] is not None and not isinstance(out["needle"], str):
            issues.append(f"{path.name}:{i}: needle must be string|null")
    return issues


def _check_n03(path: Path, rows: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    for i, row in enumerate(rows, 1):
        if row.get("niche_id") != "N03":
            issues.append(f"{path.name}:{i}: niche_id want N03")
        if not isinstance(row.get("input"), str):
            issues.append(f"{path.name}:{i}: input must be string")
        out = row.get("output")
        if out is not None and not isinstance(out, str):
            issues.append(f"{path.name}:{i}: output must be string|null")
    return issues


def _check_n08(path: Path, rows: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    for i, row in enumerate(rows, 1):
        if row.get("niche_id") != "N08":
            issues.append(f"{path.name}:{i}: niche_id want N08")
        inp = row.get("input")
        if not isinstance(inp, dict) or set(inp.keys()) != {"status", "log"}:
            issues.append(f"{path.name}:{i}: input must be {{status,log}}")
        elif not all(isinstance(inp[k], str) for k in ("status", "log")):
            issues.append(f"{path.name}:{i}: status/log must be strings")
        out = row.get("output")
        if out not in N08_ENUM:
            issues.append(f"{path.name}:{i}: unknown stall class {out!r}")
    return issues


def _bank_schema_scan(distill: Path) -> tuple[dict[str, int], list[str]]:
    """Schema-check every primary+heldout JSONL (endswith stamp filters)."""
    counts: dict[str, int] = {}
    issues: list[str] = []
    files = sorted(p for p in distill.iterdir() if p.is_file() and _is_corpus_jsonl(p.name))
    for path in files:
        rows, load_issues = _load_jsonl(path)
        issues.extend(load_issues)
        counts[path.name] = len(rows)
        for i, row in enumerate(rows, 1):
            nid = row.get("niche_id")
            if isinstance(nid, str) and nid and not path.name.startswith(nid + "_"):
                issues.append(f"{path.name}:{i}: niche_id={nid!r} vs filename")
    return counts, issues


def validate(*, distill: Path = DISTILL) -> dict[str, Any]:
    report: dict[str, Any] = {
        "needle": NEEDLE,
        "ok": True,
        "distill": str(distill),
        "counts": {},
        "bank_counts": {},
        "floors": {k: effective_floor(k) for k in sorted(set(FLOOR_ROWS) | set(FLOOR_FLOOR_MIN))},
        "issues": [],
        "files": 0,
        "rows": 0,
    }
    if not distill.is_dir():
        report["ok"] = False
        report["issues"].append(f"missing distill dir: {distill}")
        return report

    checkers = {
        "N01": _check_n01,
        "N03": _check_n03,
        "N08": _check_n08,
    }

    for name in sorted(set(FLOOR_ROWS) | set(FLOOR_FLOOR_MIN)):
        floor = effective_floor(name)
        path = distill / name
        rows, load_issues = _load_jsonl(path)
        report["issues"].extend(load_issues)
        n = len(rows)
        report["counts"][name] = n
        if n < floor:
            report["issues"].append(
                f"{name}: prune forbidden — count {n} < floor {floor} "
                "(do not drop rows to inflate metrics)"
            )
        prefix = name[:3]
        checker = checkers.get(prefix)
        if checker and rows:
            report["issues"].extend(checker(path, rows))

    bank_counts, bank_issues = _bank_schema_scan(distill)
    report["bank_counts"] = bank_counts
    report["files"] = len(bank_counts)
    report["rows"] = sum(bank_counts.values())
    report["issues"].extend(bank_issues)

    report["ok"] = not report["issues"]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON report")
    parser.add_argument(
        "--distill",
        type=Path,
        default=DISTILL,
        help="niche_distill directory",
    )
    args = parser.parse_args(argv)
    report = validate(distill=args.distill)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"niche_distill_validate {NEEDLE}")
        print(f"  files={report['files']} rows={report['rows']} ok={report['ok']}")
        for name, n in sorted(report["counts"].items()):
            floor = effective_floor(name)
            mark = "ok" if n >= floor else "FAIL"
            print(f"  floor[{mark}] {name}: {n} ≥ {floor}")
        if report["issues"]:
            print("ISSUES:")
            for issue in report["issues"][:40]:
                print(f"  - {issue}")
            if len(report["issues"]) > 40:
                print(f"  … +{len(report['issues']) - 40} more")
        else:
            print("OK — schema + anti-prune floors + bank scan")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
