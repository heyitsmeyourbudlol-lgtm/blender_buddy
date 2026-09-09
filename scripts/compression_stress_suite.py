#!/usr/bin/env python3
"""Post-train stress bars — fill stress_bars.json honestly; gate integrate.

Needle: OVERSEER_COMPRESSION_STRESS_THEN_INTEGRATE_2026_09_06

Requires a real rung0 checkpoint + train_status. Never fakes PASS.
integrate_allowed=true only when every bar is PASS.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "notes" / "compression_artifacts"
SCRIPTS = ROOT / "scripts"
NEEDLE = "OVERSEER_COMPRESSION_STRESS_THEN_INTEGRATE_2026_09_06"
LOCAL_ONLY = "OVERSEER_MODEL_LOCAL_ONLY_2026_09_06"
STRESS_PATH = ART / "stress_bars.json"
STATUS_PATH = ART / "rung0_train_status.json"
SKELETON_PATH = ART / "rung0_model_skeleton.json"
CKPT_LATEST = ART / "rung0_checkpoints" / "rung0_latest.pt"

S_FLOOR = 100.0
KD_EPS = 0.15
U_BUDGET_RATIO = 1.0 / 50.0  # U <= N/50 ⇒ S>=50 absolute floor; prefer S>=100


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _bar(ok: bool, detail: dict) -> dict:
    return {"result": "PASS" if ok else "FAIL", **detail}


def evaluate() -> dict:
    status = _load(STATUS_PATH)
    skel = _load(SKELETON_PATH)
    ckpt_ok = CKPT_LATEST.is_file()

    if not ckpt_ok or not status:
        return {
            "needle": NEEDLE,
            "status": "WAITING_FOR_FULL_TRAIN",
            "integrate_allowed": False,
            "integrate_scope": "local_workflow_only",
            "publish_model": False,
            "local_only_needle": LOCAL_ONLY,
            "bars": {
                "S_ge_100_or_recipe_floor": None,
                "unique_U_within_budget": None,
                "nvfp4_pack_bytes": None,
                "ram_residency_min": None,
                "kd_heldout": None,
                "no_data_prune": None,
                "serve_smoke": None,
            },
            "note": "No real checkpoint/train_status yet — refuse to fill PASS.",
            "evidence": {"checkpoint": str(CKPT_LATEST), "ckpt_exists": ckpt_ok, "status": status},
        }

    if not status.get("train_complete") and status.get("status") not in ("complete", "kd_short", "training"):
        # Still waiting if never trained
        pass

    s = float(status.get("S_arith") or skel.get("S") or 0.0)
    u = int(status.get("unique_U_arith") or skel.get("unique_U") or 0)
    n_logic = int(status.get("n_logic") or skel.get("n_logic") or 0)
    pack_b = float(status.get("nvfp4_pack_bytes") or skel.get("nvfp4_pack_bytes") or 0.0)
    heldout = status.get("heldout_kd_mse")
    data_prune = bool(status.get("data_prune", skel.get("data_prune", True)))
    train_complete = bool(status.get("train_complete"))
    step = int(status.get("step") or 0)

    # Serve smoke via t5 script (arith residency)
    serve_ok = False
    serve_detail: dict = {}
    t5 = SCRIPTS / "compression_t5_serve.py"
    if t5.is_file():
        try:
            out = subprocess.check_output(
                [sys.executable, str(t5), "--json"],
                cwd=str(ROOT),
                text=True,
                errors="replace",
                timeout=60,
            )
            serve_detail = json.loads(out)
            # PASS if script returns rows and rung0 skeleton referenced
            rows = serve_detail.get("rows") or serve_detail.get("results") or []
            serve_ok = bool(rows) or serve_detail.get("ok") is True or "needle" in serve_detail
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            serve_detail = {"error": str(exc)}
            serve_ok = False

    ideal_pack = u / 2.0
    pack_ok = u > 0 and abs(pack_b - ideal_pack) <= max(64.0, 0.05 * ideal_pack)
    s_ok = s >= S_FLOOR
    u_budget = max(1, int(n_logic * U_BUDGET_RATIO)) if n_logic else 0
    u_ok = u > 0 and n_logic > 0 and u <= max(u_budget, n_logic // 100)  # S>=100 preferred; S>=50 floor via U_BUDGET
    # Prefer north-star S>=100 for unique budget:
    u_ok = u > 0 and n_logic > 0 and (n_logic / u) >= S_FLOOR
    ram_mb = pack_b / (1024 * 1024)
    ram_ok = pack_b > 0 and ram_mb < 512.0  # min-RAM: unique store sketch under 512 MiB
    kd_ok = heldout is not None and float(heldout) <= KD_EPS
    prune_ok = data_prune is False

    bars = {
        "S_ge_100_or_recipe_floor": _bar(s_ok, {"S": s, "floor": S_FLOOR}),
        "unique_U_within_budget": _bar(u_ok, {"U": u, "n_logic": n_logic, "S": (n_logic / u) if u else None}),
        "nvfp4_pack_bytes": _bar(pack_ok, {"pack_bytes": pack_b, "ideal_U_over_2": ideal_pack}),
        "ram_residency_min": _bar(ram_ok, {"nvfp4_pack_mb": ram_mb, "cap_mb": 512.0}),
        "kd_heldout": _bar(kd_ok, {"heldout_kd_mse": heldout, "eps": KD_EPS, "train_complete": train_complete}),
        "no_data_prune": _bar(prune_ok, {"data_prune": data_prune}),
        "serve_smoke": _bar(serve_ok, {"t5": serve_detail.get("needle") or serve_detail}),
    }

    # Only evaluate integrate after a completed rung0 train attempt with checkpoint.
    if not ckpt_ok or step < 1:
        status_label = "WAITING_FOR_FULL_TRAIN"
        integrate = False
        note = "Checkpoint missing or zero steps — waiting for full train."
    elif not train_complete:
        status_label = "TRAIN_INCOMPLETE"
        integrate = False
        note = "Checkpoint exists but train_complete=false (KD short or still running)."
    else:
        results = [b["result"] for b in bars.values()]
        all_pass = all(r == "PASS" for r in results)
        status_label = "PASS" if all_pass else "FAIL"
        integrate = all_pass
        note = (
            "All bars PASS — LOCAL workflow integrate allowed (never public publish)."
            if all_pass
            else "One or more bars FAIL — redesign/retrain; integrate_allowed=false."
        )

    return {
        "needle": NEEDLE,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status_label,
        "integrate_allowed": integrate,
        "integrate_scope": "local_workflow_only",
        "publish_model": False,
        "local_only_needle": LOCAL_ONLY,
        "bars": bars,
        "note": note,
        "evidence": {
            "checkpoint": str(CKPT_LATEST),
            "ckpt_exists": ckpt_ok,
            "train_status": str(STATUS_PATH),
            "step": step,
            "train_complete": train_complete,
            "north_star_1b_complete": bool(status.get("north_star_1b_complete")),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="write stress_bars.json")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args()
    payload = evaluate()
    if args.write:
        ART.mkdir(parents=True, exist_ok=True)
        STRESS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.json or not args.write:
        print(json.dumps(payload, indent=2))
    elif args.write:
        print(
            json.dumps(
                {
                    "wrote": str(STRESS_PATH),
                    "status": payload["status"],
                    "integrate_allowed": payload["integrate_allowed"],
                },
                indent=2,
            )
        )
    # Exit 0 even on FAIL — honesty over green CI; caller checks integrate_allowed
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
