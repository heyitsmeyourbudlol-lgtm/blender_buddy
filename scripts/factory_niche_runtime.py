#!/usr/bin/env python3
"""Factory niche runtime — parallel route+serve, retrieval, divert, assist hooks.

Needle: OVERSEER_FACTORY_NICHE_RUNTIME_2026_09_07

Wires the ~10M niche bank into peer_loop (fail-soft). Supports:
  - parallel serve of top-k niches
  - note/SOP retrieval context
  - fact-check divert on numeric/hardware claims
  - N32–N34 ship-hook hints (diff/commit/PR) + escalate
  - stall / verify / done-gate assists
  - pre-dispatch N01 practice gate (OVERSEER_NICHE_HOT_PATH_N01_2026_09_07)

Not stock Ollama. Local only. Niches ≠ general LLM.
"""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DISTILL = ROOT / "notes" / "niche_distill"
ART = DISTILL / "factory_assist_last.json"
RETRIEVAL_CACHE = DISTILL / "retrieval_index.json"
NEEDLE = "OVERSEER_FACTORY_NICHE_RUNTIME_2026_09_07"

_NUMERIC_CLAIM = re.compile(
    r"\b(\d+\s*(k|K|M|B|T|GB|MB|tok/s|params?)|NVFP4|GDS|10k|1Q|quadrillion)\b"
)
_DIFF_RISK = re.compile(
    r"\b(diff\s*risk|risky\s*diff|review\s*diff|changed\s*files?|file\s*diff)\b",
    re.I,
)
_COMMIT_MSG = re.compile(
    r"\b(commit\s*msg|commit\s*message|why-msg|git\s*commit)\b",
    re.I,
)
_PR_SUMMARY = re.compile(
    r"\b(pr\s*summary|pull\s*request|pr\s*body|pr\s*bullets)\b",
    re.I,
)


def _cfg() -> dict[str, Any]:
    try:
        import project_automation as auto

        return dict(auto.CFG or {})
    except Exception:  # noqa: BLE001
        return {}


def _truthy(val: Any, default: bool = True) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    s = str(val).strip().lower()
    if s in ("0", "false", "no", "off", ""):
        return False
    if s in ("1", "true", "yes", "on"):
        return True
    return default


def enabled() -> bool:
    if os.environ.get("FACTORY_NICHE_ASSIST", "").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    return _truthy(_cfg().get("factory_niche_assist"), True)


def parallel_enabled() -> bool:
    env = os.environ.get("FACTORY_NICHE_PARALLEL", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    return _truthy(_cfg().get("factory_niche_parallel"), True)


def parallel_workers() -> int:
    """Thread pool size when parallel serve is on; 1 when parallel is off.

    ``factory_niche_parallel`` is a bool enable flag (not worker count).
    Worker count comes from ``factory_niche_workers`` / FACTORY_NICHE_WORKERS,
    then factory_dynamics.adaptive_cpu_workers when available.
    """
    if not parallel_enabled():
        return 1
    raw = os.environ.get("FACTORY_NICHE_WORKERS")
    if raw is None or raw == "":
        raw = _cfg().get("factory_niche_workers", 4)
    try:
        base = max(1, min(16, int(raw)))
    except (TypeError, ValueError):
        base = 4
    try:
        import factory_dynamics as fd

        return int(fd.adaptive_cpu_workers(base))
    except Exception:  # noqa: BLE001
        return base


def default_top_k() -> int:
    raw = os.environ.get("FACTORY_NICHE_TOP_K") or _cfg().get("factory_niche_top_k") or 3
    try:
        base = max(1, min(8, int(raw)))
    except (TypeError, ValueError):
        base = 3
    try:
        import factory_dynamics as fd

        return int(fd.adaptive_top_k(base))
    except Exception:  # noqa: BLE001
        return base


def _escalate_floor() -> float:
    try:
        import factory_dynamics as fd

        return float(fd.escalate_floor())
    except Exception:  # noqa: BLE001
        return 0.35


def _import_bank():
    import niche_bank_train as bank

    return bank


def _import_composer():
    import niche_composer as composer

    return composer


def retrieve(query: str, *, top_k: int = 3) -> list[dict[str, Any]]:
    """Cheap bag-of-tokens retrieval over notes + SOPs (no external embed API)."""
    import niche_retrieval as nr

    return nr.retrieve(query, top_k=top_k)


def fact_check_divert(text: str) -> dict[str, Any] | None:
    """If text looks like a hardware/numeric claim → require fact_checker niche."""
    if not _NUMERIC_CLAIM.search(text or ""):
        return None
    return {
        "divert": "fact_checker",
        "niche_hint": "N13",
        "reason": "numeric_or_hardware_claim",
        "needle": NEEDLE,
    }


def ship_hooks_divert(text: str) -> dict[str, Any] | None:
    """N32–N34 thin hooks: diff risk / commit msg / PR summary → niche hint + escalate.

    Covered also by assist_pre_dispatch (queue lines) + fact-check divert for
    numeric claims; this adds explicit ship-path routing when wording matches.
    """
    t = text or ""
    if _DIFF_RISK.search(t):
        return {
            "divert": "diff_risk_label",
            "niche_hint": "N32",
            "reason": "diff_risk_hook",
            "escalate_to_big_model": True,
            "needle": NEEDLE,
        }
    if _COMMIT_MSG.search(t):
        return {
            "divert": "commit_msg_style",
            "niche_hint": "N33",
            "reason": "commit_msg_hook",
            "escalate_to_big_model": True,
            "needle": NEEDLE,
        }
    if _PR_SUMMARY.search(t):
        return {
            "divert": "pr_summary_bullets",
            "niche_hint": "N34",
            "reason": "pr_summary_hook",
            "escalate_to_big_model": True,
            "needle": NEEDLE,
        }
    return None


def serve_parallel(
    pairs: list[tuple[str, str]],
    *,
    workers: int | None = None,
) -> list[dict[str, Any]]:
    """Serve many (niche_id, text) pairs in parallel threads.

    Assigns CPU/GPU via factory_dynamics when available; observes batch for
    live balance adjust. Fail-soft if dynamics/torch missing.
    """
    bank = _import_bank()
    n = workers or parallel_workers()
    out: list[dict[str, Any]] = []
    if not pairs:
        return out

    devices: list[str] = ["cpu"] * len(pairs)
    try:
        import factory_dynamics as fd

        devices = list(fd.assign_devices(len(pairs)))
        if len(devices) < len(pairs):
            devices = devices + ["cpu"] * (len(pairs) - len(devices))
    except Exception:  # noqa: BLE001
        devices = ["cpu"] * len(pairs)

    def _one(item: tuple[str, str], device: str) -> dict[str, Any]:
        nid, text = item
        try:
            return bank.serve_one(nid, text, device_name=device)
        except TypeError:
            # Older serve_one without device_name kwarg
            try:
                return bank.serve_one(nid, text)
            except Exception as exc:  # noqa: BLE001
                return {"niche_id": nid, "error": str(exc), "ok": False, "device_name": device}
        except Exception as exc:  # noqa: BLE001
            return {
                "niche_id": nid,
                "error": str(exc),
                "ok": False,
                "device_name": device,
            }

    jobs = list(zip(pairs, devices))
    # Safer pattern: serialize GPU/MPS forwards (bank also holds _gpu_forward_lock);
    # CPU rows may fan out in a thread pool.
    gpu_jobs = [(p, d) for p, d in jobs if d in ("cuda", "mps")]
    cpu_jobs = [(p, d) for p, d in jobs if d not in ("cuda", "mps")]
    out = [_one(p, d) for p, d in gpu_jobs]
    if cpu_jobs:
        if n <= 1 or len(cpu_jobs) == 1:
            out.extend(_one(p, d) for p, d in cpu_jobs)
        else:
            with ThreadPoolExecutor(max_workers=n) as pool:
                futs = {pool.submit(_one, p, d): (p, d) for p, d in cpu_jobs}
                for fut in as_completed(futs):
                    out.append(fut.result())

    try:
        import factory_dynamics as fd

        latencies: list[tuple[str, float]] = []
        for s in out:
            dev = str(s.get("device_name") or s.get("device") or "cpu")
            try:
                ms = float(s.get("latency_ms") or 0.0)
            except (TypeError, ValueError):
                ms = 0.0
            latencies.append((dev, ms))
        adjust = fd.adjust_after_batch(out, latencies_ms=latencies)
        for s in out:
            if isinstance(s, dict):
                s.setdefault("balance_adjust", adjust)
    except Exception:  # noqa: BLE001
        pass
    return out


def route_and_serve(
    text: str,
    *,
    top_k: int | None = None,
    with_retrieval: bool = True,
) -> dict[str, Any]:
    composer = _import_composer()
    k = default_top_k() if top_k is None else top_k
    routed = composer.route(text, top_k=k)
    routes = list(routed.get("routes") or [])
    ctx: list[dict[str, Any]] = []
    if with_retrieval:
        try:
            ctx = retrieve(text, top_k=3)
        except Exception:  # noqa: BLE001
            ctx = []
    divert = fact_check_divert(text)
    ship = ship_hooks_divert(text)
    # Ensure hinted niches are in the serve set
    seen = {r.get("id") for r in routes if r.get("id")}
    for hint_src in (divert, ship):
        if not hint_src:
            continue
        hid = hint_src.get("niche_hint")
        if hid and hid not in seen:
            routes.append(
                {
                    "id": hid,
                    "name": hint_src.get("divert") or hid,
                    "score": 0.5,
                    "helps": hint_src.get("reason"),
                }
            )
            seen.add(hid)
    pairs = [(r["id"], text) for r in routes if r.get("id")]
    serves = serve_parallel(pairs)
    # Merge: pick highest score serve among successes
    best = None
    for s in serves:
        if s.get("error"):
            continue
        if best is None or float(s.get("score") or 0) > float(best.get("score") or 0):
            best = s
    escalate = False
    floor = _escalate_floor()
    if best is None or float(best.get("score") or 0) < floor:
        escalate = True
    if ship and ship.get("escalate_to_big_model"):
        escalate = True
    if divert:
        escalate = True  # numeric claims always escalate alongside fact niche
    balance_adjust = None
    dynamics_meta: dict[str, Any] = {}
    try:
        import factory_dynamics as fd

        if serves and isinstance(serves[0], dict):
            balance_adjust = serves[0].get("balance_adjust")
        dynamics_meta = {
            "gpu_share": fd.gpu_share(),
            "escalate_floor": floor,
            "device_mode": fd.device_mode(),
            "balance_enabled": fd.balance_enabled(),
            "device": (fd.pick_device()[0] if hasattr(fd, "pick_device") else None),
            "device_pick_reason": (fd.pick_device()[1] if hasattr(fd, "pick_device") else None),
            "log": fd.log_line(),
        }
    except Exception:  # noqa: BLE001
        dynamics_meta = {"escalate_floor": floor}
    payload = {
        "needle": NEEDLE,
        "input": text,
        "routes": routes,
        "serves": serves,
        "best": best,
        "retrieval": ctx,
        "divert": divert or ship,
        "ship_hook": ship,
        "escalate_to_big_model": escalate,
        "escalate_floor": floor,
        "parallel_enabled": parallel_enabled(),
        "parallel_workers": parallel_workers(),
        "top_k": k,
        "gpu_share": dynamics_meta.get("gpu_share"),
        "device": dynamics_meta.get("device"),
        "device_pick_reason": dynamics_meta.get("device_pick_reason"),
        "balance_adjust": balance_adjust,
        "dynamics": dynamics_meta,
        "local_only": True,
        "honesty": (
            "Closed-world niche specialists + hash-token retrieval — not a general LLM. "
            "Factory dynamics = live CPU/GPU serve share + adaptive escalate/top_k — "
            "not continuous training, not TE. Compression cold pack ≠ TensorRT-LLM TE."
        ),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if escalate:
        try:
            import niche_mint as mint

            sug = mint.record_opportunity(
                text=text,
                reason="route_escalate",
                routes=routes if isinstance(routes, list) else [],
            )
            if sug:
                payload["mint_suggestion"] = {
                    "name": sug.get("name"),
                    "hint": sug.get("hint"),
                    "duplicate_of": sug.get("duplicate_of"),
                }
        except Exception:  # noqa: BLE001
            pass
    try:
        DISTILL.mkdir(parents=True, exist_ok=True)
        ART.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
    return payload


def _active_queue_lines(limit: int = 5) -> list[str]:
    wq = ROOT / "notes" / "WORK_QUEUE.md"
    if not wq.is_file():
        return []
    lines: list[str] = []
    in_active = False
    for raw in wq.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw.strip().startswith("## Active"):
            in_active = True
            continue
        if in_active and raw.startswith("## "):
            break
        if in_active and raw.lstrip().startswith("- ["):
            lines.append(raw.strip())
            if len(lines) >= limit:
                break
    return lines


def assist_pre_dispatch(log_fn: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Pre-dispatch niche assist — prefer cheap N01 practice before neural bank.

    OVERSEER_NICHE_HOT_PATH_N01_2026_09_07 — practice parse is the hot path;
    ``route_and_serve`` (torch experts) only when N01 fail-closes.
    """
    log = log_fn or (lambda _m: None)
    if not enabled():
        return {"skipped": True, "reason": "disabled"}
    lines = _active_queue_lines(3)
    if not lines:
        log("niche-assist: no Active opens")
        return {"skipped": True, "reason": "empty_active"}
    results = []
    n01_hits = 0
    for line in lines:
        # Cheap mechanical gate first (no torch) — fail-closed to neural route.
        try:
            import niche_hot_path as nhp

            parsed = nhp.parse_queue_bullet(line)
            if parsed:
                n01_hits += 1
                label = (
                    parsed.get("scope")
                    or parsed.get("needle")
                    or str(parsed.get("kit"))
                )
                results.append(
                    {
                        "needle": nhp.NEEDLE,
                        "input": line,
                        "best": {
                            "niche_id": "N01",
                            "label": label,
                            "kit": parsed.get("kit"),
                            "scope": parsed.get("scope"),
                            "score": 1.0,
                            "source": "n01_practice",
                        },
                        "serves": [
                            {
                                "niche_id": "N01",
                                "label": label,
                                "score": 1.0,
                                "kind": "rule",
                            }
                        ],
                        "escalate_to_big_model": False,
                        "source": "n01_practice",
                    }
                )
                continue
        except Exception as exc:  # noqa: BLE001
            log(f"niche-assist: N01 hot-path ({exc})")
        try:
            results.append(route_and_serve(line, top_k=default_top_k()))
        except Exception as exc:  # noqa: BLE001
            log(f"niche-assist: route fail ({exc})")
    best_labels = []
    for r in results:
        b = r.get("best") or {}
        if b.get("label"):
            src = b.get("source") or r.get("source") or ""
            tag = f"{b.get('niche_id')}={b.get('label')}"
            if src:
                tag = f"{tag}/{src}"
            best_labels.append(tag)
        if r.get("divert"):
            log(f"niche-assist: FACT divert — {r['divert'].get('reason')}")
        if r.get("ship_hook"):
            log(f"niche-assist: ship hook — {r['ship_hook'].get('reason')}")
    if best_labels:
        log(f"niche-assist: pre-dispatch {', '.join(best_labels[:6])}")
    if n01_hits:
        log(f"niche-assist: N01 practice gate hit={n01_hits} (skipped neural)")
    try:
        import factory_dynamics as fd

        log(fd.log_line())
    except Exception:  # noqa: BLE001
        pass
    return {
        "needle": NEEDLE,
        "hot_path_needle": "OVERSEER_NICHE_HOT_PATH_N01_2026_09_07",
        "n": len(results),
        "n01_practice_hits": n01_hits,
        "results": results,
    }


def assist_verify_fail(
    failure_type: str | None,
    note: str,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    log = log_fn or (lambda _m: None)
    if not enabled():
        return {"skipped": True}
    blob = f"verify fail type={failure_type or 'other'} {note}"
    try:
        out = route_and_serve(blob, top_k=default_top_k())
        # Prefer N08 / N09 style
        for s in out.get("serves") or []:
            if s.get("niche_id") in ("N08", "N09") and s.get("label"):
                log(f"niche-assist: verify→{s['niche_id']}={s['label']} ({s.get('score'):.2f})")
                break
        else:
            b = out.get("best") or {}
            if b.get("label"):
                log(f"niche-assist: verify→{b.get('niche_id')}={b.get('label')}")
        try:
            import factory_dynamics as fd

            log(fd.log_line())
        except Exception:  # noqa: BLE001
            pass
        return out
    except Exception as exc:  # noqa: BLE001
        log(f"niche-assist: verify assist ({exc})")
        return {"error": str(exc)}


def assist_stall(
    reason: str,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    log = log_fn or (lambda _m: None)
    if not enabled():
        return {"skipped": True}
    try:
        out = route_and_serve(f"stall {reason}", top_k=min(2, default_top_k()))
        for s in out.get("serves") or []:
            if s.get("niche_id") == "N08" and s.get("label"):
                log(f"niche-assist: stall→N08={s['label']}")
                break
        else:
            b = out.get("best") or {}
            if b.get("label"):
                log(f"niche-assist: stall→{b.get('niche_id')}={b.get('label')}")
        try:
            import factory_dynamics as fd

            log(fd.log_line())
        except Exception:  # noqa: BLE001
            pass
        return out
    except Exception as exc:  # noqa: BLE001
        log(f"niche-assist: stall ({exc})")
        return {"error": str(exc)}


def assist_done_gate(log_fn: Callable[[str], None] | None = None) -> dict[str, Any]:
    log = log_fn or (lambda _m: None)
    if not enabled():
        return {"skipped": True}
    try:
        out = route_and_serve("done-gate checklist allow checkbox flip?", top_k=min(2, default_top_k()))
        b = out.get("best") or {}
        if b.get("label"):
            log(f"niche-assist: done-gate→{b.get('niche_id')}={b.get('label')}")
        try:
            import factory_dynamics as fd

            log(fd.log_line())
        except Exception:  # noqa: BLE001
            pass
        return out
    except Exception as exc:  # noqa: BLE001
        log(f"niche-assist: done-gate ({exc})")
        return {"error": str(exc)}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--pre-dispatch", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.pre_dispatch:
        out = assist_pre_dispatch(print)
    else:
        text = args.text or sys.stdin.read()
        out = route_and_serve(text)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
