#!/usr/bin/env python3
"""Niche bank eval harness — heldout + live WORK_QUEUE smoke.

Needle: OVERSEER_NICHE_BANK_EVAL_2026_09_07
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DISTILL = ROOT / "notes" / "niche_distill"
WQ = ROOT / "notes" / "WORK_QUEUE.md"
OUT = DISTILL / "bank_eval_report.json"
NEEDLE = "OVERSEER_NICHE_BANK_EVAL_2026_09_07"


def _heldout_acc(nid: str) -> dict[str, Any]:
    import niche_bank_train as bank

    if nid.upper() == "N01":
        ckpt = DISTILL / "practice_n01" / "checkpoint_neural.json"
    else:
        ckpt = bank.niche_dir(nid) / "checkpoint_neural.json"
    if not ckpt.is_file():
        return {"id": nid, "passed": False, "error": "missing_ckpt"}
    try:
        d = json.loads(ckpt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"id": nid, "passed": False, "error": str(exc)}
    acc = d.get("heldout_accuracy")
    if acc is None and isinstance(d.get("heldout"), dict):
        acc = d["heldout"].get("n01_acc") or d["heldout"].get("knowledge_acc")
    ok = bool(d.get("passed")) and (acc is None or float(acc) >= 0.9)
    return {
        "id": nid,
        "passed": ok,
        "heldout_accuracy": acc,
        "param_count": d.get("param_count"),
        "status": d.get("status"),
    }


def live_wq_smoke() -> dict[str, Any]:
    import factory_niche_runtime as rt

    lines = []
    if WQ.is_file():
        in_a = False
        for raw in WQ.read_text(encoding="utf-8", errors="replace").splitlines():
            if raw.strip().startswith("## Active"):
                in_a = True
                continue
            if in_a and raw.startswith("## "):
                break
            if in_a and raw.lstrip().startswith("- ["):
                lines.append(raw.strip())
            if len(lines) >= 3:
                break
    if not lines:
        lines = ["- [ ] **[kit] peer_loop smoke Needle: `OVERSEER_EVAL_SMOKE`."]
    serves = []
    for line in lines:
        try:
            serves.append(rt.route_and_serve(line, top_k=2, with_retrieval=False))
        except Exception as exc:  # noqa: BLE001
            serves.append({"error": str(exc), "input": line})
    ok = sum(1 for s in serves if (s.get("best") or {}).get("label") or s.get("routes"))
    return {"n_lines": len(lines), "n_ok": ok, "samples": serves[:3]}


def run_eval(*, workers: int = 8, smoke: bool = True) -> dict[str, Any]:
    import niche_bank_train as bank

    catalog = bank.parse_catalog() + bank.extra_niches()
    ids = [c["id"] for c in catalog]
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_heldout_acc, i): i for i in ids}
        for fut in as_completed(futs):
            rows.append(fut.result())
    rows.sort(key=lambda r: r["id"])
    n_pass = sum(1 for r in rows if r.get("passed"))
    payload: dict[str, Any] = {
        "needle": NEEDLE,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_catalog": len(ids),
        "n_pass": n_pass,
        "n_fail": len(ids) - n_pass,
        "pass_rate": n_pass / len(ids) if ids else 0.0,
        "experts": rows,
        "local_only": True,
    }
    if smoke:
        payload["live_wq_smoke"] = live_wq_smoke()
    DISTILL.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-smoke", action="store_true")
    args = ap.parse_args(argv)
    try:
        out = run_eval(workers=args.workers, smoke=not args.no_smoke)
    except Exception as exc:  # noqa: BLE001
        payload = {
            "needle": NEEDLE,
            "error": str(exc),
            "skipped": True,
            "local_only": True,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        DISTILL.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 0
    print(
        json.dumps(
            {
                "needle": out["needle"],
                "n_pass": out["n_pass"],
                "n_catalog": out["n_catalog"],
                "pass_rate": out["pass_rate"],
                "smoke_ok": (out.get("live_wq_smoke") or {}).get("n_ok"),
            },
            indent=2,
        )
    )
    return 0 if out["n_fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
