#!/usr/bin/env python3
"""Agent-triggered niche mint — propose/start a tiny specialist when work reveals a gap.

Needle: OVERSEER_NICHE_MINT_ON_DEMAND_2026_09_07

Agents call this when they stumble on a closed-world job a local ~10M model
could speed up (repeated classify/triage that rules can't cover cheaply).

Not mass bank expansion. Guardrails: dedupe, rate limit, Backlog enqueue
(not Active flood), optional train.

Usage::
    python3 scripts/niche_mint.py --propose --name foo_bar --io "text → label" --reason "…"
    python3 scripts/niche_mint.py --start --name foo_bar --io "text → label" --reason "…" [--train]
    python3 scripts/niche_mint.py --suggest-from-assist
    python3 scripts/niche_mint.py --list
    ./scripts/peer niche-mint --start --name … --io "…" --reason "…"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any

NEEDLE = "OVERSEER_NICHE_MINT_ON_DEMAND_2026_09_07"
ROOT = Path(__file__).resolve().parents[1]
DISTILL = ROOT / "notes" / "niche_distill"
MINTED = DISTILL / "minted_catalog.json"
MINT_LOG = DISTILL / "mint_log.jsonl"
SUGGESTIONS = DISTILL / "mint_suggestions.jsonl"
ASSIST_LAST = DISTILL / "factory_assist_last.json"
BANK_MD = ROOT / "notes" / "BITNET_NICHE_BANK.md"
WQ = ROOT / "notes" / "WORK_QUEUE.md"
CTX = ROOT / "scripts" / "self_improve_context.md"

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,48}$")
_RATE_SEC = 3600  # 1 mint/hour unless --force


def _cfg() -> dict[str, Any]:
    try:
        import project_automation as auto

        return dict(auto.CFG or {})
    except Exception:  # noqa: BLE001
        return {}


def _load_minted() -> dict[str, Any]:
    if not MINTED.is_file():
        return {"needle": NEEDLE, "niches": [], "local_only": True}
    try:
        return json.loads(MINTED.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"needle": NEEDLE, "niches": [], "local_only": True}


def _save_minted(blob: dict[str, Any]) -> None:
    DISTILL.mkdir(parents=True, exist_ok=True)
    blob["needle"] = NEEDLE
    blob["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    MINTED.write_text(json.dumps(blob, indent=2) + "\n", encoding="utf-8")


def _append_log(row: dict[str, Any]) -> None:
    DISTILL.mkdir(parents=True, exist_ok=True)
    row = dict(row)
    row.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    row.setdefault("needle", NEEDLE)
    with MINT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def minted_niches() -> list[dict[str, str]]:
    """Catalog rows for niche_bank_train.extra_niches merge.

    Skip ids already present in the markdown catalog so N### is not doubled
    after ``_append_bank_md_row``.
    """
    try:
        import niche_bank_train as bank

        have = {r["id"] for r in bank.parse_catalog()}
    except Exception:  # noqa: BLE001
        have = set()
    out: list[dict[str, str]] = []
    for n in _load_minted().get("niches") or []:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        nid = str(n["id"]).upper()
        if nid in have:
            continue
        out.append(
            {
                "id": nid,
                "name": str(n.get("name") or "minted"),
                "input_shape": str(n.get("input_shape") or "text"),
                "output_shape": str(n.get("output_shape") or "label"),
                "helps": str(n.get("helps") or "on-demand mint"),
            }
        )
    return out


def _full_catalog() -> list[dict[str, str]]:
    import niche_bank_train as bank

    rows = list(bank.parse_catalog()) + list(bank.extra_niches())
    seen: set[str] = set()
    uniq: list[dict[str, str]] = []
    for r in rows:
        rid = str(r.get("id") or "")
        if not rid or rid in seen:
            continue
        seen.add(rid)
        uniq.append(r)
    return uniq


def next_niche_id() -> str:
    nums = []
    for n in _full_catalog():
        m = re.match(r"N(\d+)$", n["id"], re.I)
        if m:
            nums.append(int(m.group(1)))
    for n in minted_niches():
        m = re.match(r"N(\d+)$", n["id"], re.I)
        if m:
            nums.append(int(m.group(1)))
    nxt = max(nums) + 1 if nums else 106
    return f"N{nxt}"


def slug_name(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "minted_niche"
    if not s[0].isalpha():
        s = "n_" + s
    return s[:48]


def find_duplicate(name: str, io_spec: str = "") -> dict[str, str] | None:
    """Return existing niche if name/helps/io looks like a duplicate."""
    want = slug_name(name)
    tokens = set(re.findall(r"[a-z0-9]+", (name + " " + io_spec).lower()))
    best: tuple[float, dict[str, str]] | None = None
    for n in _full_catalog():
        nm = slug_name(n["name"])
        if nm == want:
            return n
        ntok = set(re.findall(r"[a-z0-9]+", f"{n['name']} {n.get('input_shape')} {n.get('output_shape')} {n.get('helps')}".lower()))
        if not tokens or not ntok:
            continue
        overlap = len(tokens & ntok) / max(1, len(tokens | ntok))
        if overlap >= 0.55:
            if best is None or overlap > best[0]:
                best = (overlap, n)
    return best[1] if best else None


def parse_io(io_spec: str) -> tuple[str, str]:
    s = (io_spec or "").strip()
    if "→" in s:
        a, b = s.split("→", 1)
        return a.strip() or "text", b.strip() or "label"
    if "->" in s:
        a, b = s.split("->", 1)
        return a.strip() or "text", b.strip() or "label"
    return s or "text", "label"


def _rate_limited(*, force: bool) -> str | None:
    if force:
        return None
    if not MINT_LOG.is_file():
        return None
    try:
        lines = MINT_LOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines[-40:]):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("action") not in ("start", "train"):
            continue
        ts = row.get("unix")
        if isinstance(ts, (int, float)) and time.time() - float(ts) < _RATE_SEC:
            return f"rate_limit: last mint {int(time.time() - float(ts))}s ago (use --force)"
    return None


def propose(
    *,
    name: str,
    io_spec: str,
    reason: str,
    helps: str = "",
    examples: list[str] | None = None,
) -> dict[str, Any]:
    name = slug_name(name)
    if not _NAME_RE.match(name):
        return {"ok": False, "error": "bad_name", "hint": "use snake_case 3–48 chars"}
    inp, out = parse_io(io_spec)
    dup = find_duplicate(name, io_spec)
    if dup:
        return {
            "ok": False,
            "error": "duplicate",
            "existing": dup,
            "hint": f"use existing {dup['id']} {dup['name']} — do not mint",
            "needle": NEEDLE,
        }
    nid = next_niche_id()
    proposal = {
        "ok": True,
        "action": "propose",
        "id": nid,
        "name": name,
        "input_shape": inp,
        "output_shape": out,
        "helps": helps or "agent on-demand",
        "reason": (reason or "").strip() or "unspecified",
        "examples": examples or [],
        "needle": NEEDLE,
        "next": f"python3 scripts/niche_mint.py --start --name {name} --io '{inp} → {out}' --reason '{reason[:80]}'",
    }
    _append_log({**proposal, "unix": time.time()})
    return proposal


def _append_bank_md_row(niche: dict[str, str]) -> None:
    if not BANK_MD.is_file():
        return
    text = BANK_MD.read_text(encoding="utf-8")
    marker = "| N100 |"
    row = (
        f"| {niche['id']} | `{niche['name']}` | "
        f"{niche['input_shape']} → {niche['output_shape']} | {niche['helps']} |\n"
    )
    if f"| {niche['id']} |" in text:
        return
    # Append near end of catalog table if N100 present; else append section
    if marker in text:
        # insert after last N### table row before blank/non-table
        lines = text.splitlines(keepends=True)
        last_idx = -1
        for i, ln in enumerate(lines):
            if re.match(r"^\|\s*N\d+\s*\|", ln):
                last_idx = i
        if last_idx >= 0:
            lines.insert(last_idx + 1, row)
            BANK_MD.write_text("".join(lines), encoding="utf-8")
            return
    BANK_MD.write_text(
        text.rstrip()
        + f"\n\n### On-demand mints\n\n| ID | Name | I/O | Helps |\n|----|------|-----|-------|\n{row}",
        encoding="utf-8",
    )


def _enqueue_backlog(niche: dict[str, str], reason: str) -> str:
    line = (
        f"- [ ] **[niche-mint] Train/serve {niche['id']} `{niche['name']}`** — "
        f"{reason[:120]} — `python3 scripts/niche_bank_train.py --train --ids {niche['id']}` "
        f"— Needle `{NEEDLE}`"
    )
    for path in (WQ, CTX):
        if not path.is_file():
            continue
        body = path.read_text(encoding="utf-8")
        if niche["id"] in body and niche["name"] in body:
            continue
        if "## Backlog" in body:
            body = body.replace("## Backlog", f"## Backlog\n{line}", 1)
        else:
            body = body.rstrip() + f"\n\n## Backlog\n{line}\n"
        path.write_text(body, encoding="utf-8")
    return line


def start(
    *,
    name: str,
    io_spec: str,
    reason: str,
    helps: str = "",
    examples: list[str] | None = None,
    train: bool = False,
    enqueue: bool = True,
    force: bool = False,
    device: str = "auto",
) -> dict[str, Any]:
    limited = _rate_limited(force=force)
    if limited:
        return {"ok": False, "error": limited, "needle": NEEDLE}

    prop = propose(name=name, io_spec=io_spec, reason=reason, helps=helps, examples=examples)
    if not prop.get("ok"):
        return prop

    niche = {
        "id": prop["id"],
        "name": prop["name"],
        "input_shape": prop["input_shape"],
        "output_shape": prop["output_shape"],
        "helps": prop["helps"],
        "reason": prop["reason"],
        "examples": prop.get("examples") or [],
        "status": "scaffolded",
        "minted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    blob = _load_minted()
    niches = list(blob.get("niches") or [])
    niches.append(niche)
    blob["niches"] = niches
    _save_minted(blob)
    _append_bank_md_row(niche)

    import niche_bank_train as bank

    train_rows, held_rows = bank.synthesize_rows(niche)
    # Blend agent examples into train set when provided
    for i, ex in enumerate(examples or []):
        if not ex.strip():
            continue
        labs = bank._labels_for(niche)
        lab = labs[i % len(labs)]
        train_rows[i % len(train_rows)] = {
            "niche_id": niche["id"],
            "niche": niche["name"],
            "input": ex.strip(),
            "output": {"label": lab},
        }
    tp, hp = bank.jsonl_paths(niche["id"], niche["name"])
    bank.write_jsonl(tp, train_rows)
    bank.write_jsonl(hp, held_rows)

    qline = _enqueue_backlog(niche, reason) if enqueue else ""

    train_result: dict[str, Any] | None = None
    if train:
        try:
            train_result = bank.train_one(
                niche,
                epochs=int(_cfg().get("factory_niche_mint_epochs") or 8),
                lr=float(_cfg().get("factory_niche_mint_lr") or 3e-4),
                device_name=device if device != "auto" else "cuda",
                force=True,
            )
            niche["status"] = "trained" if train_result.get("passed") else "train_attempted"
            blob = _load_minted()
            for n in blob.get("niches") or []:
                if n.get("id") == niche["id"]:
                    n["status"] = niche["status"]
                    n["train"] = {
                        k: train_result.get(k)
                        for k in ("passed", "heldout_accuracy", "param_count", "status", "error")
                        if k in train_result or train_result.get(k) is not None
                    }
            _save_minted(blob)
        except Exception as exc:  # noqa: BLE001
            train_result = {"error": str(exc), "ok": False}
            niche["status"] = "train_error"

    out = {
        "ok": True,
        "action": "start",
        "niche": niche,
        "jsonl": {"train": str(tp.relative_to(ROOT)), "heldout": str(hp.relative_to(ROOT))},
        "queue_line": qline,
        "train": train_result,
        "serve": f"python3 scripts/niche_bank_train.py --serve {niche['id']} '<input>'",
        "needle": NEEDLE,
        "honesty": "Closed-world stamp; not a general LLM. Prefer existing niche if duplicate.",
    }
    _append_log({**out, "unix": time.time(), "action": "start"})
    return out


def record_opportunity(
    *,
    text: str,
    reason: str = "escalate",
    routes: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Called from factory_niche_runtime when assist escalates — soft suggestion only."""
    if os.environ.get("FACTORY_NICHE_MINT_SUGGEST", "").strip().lower() in ("0", "false", "no"):
        return None
    enabled = _cfg().get("factory_niche_mint_suggest", True)
    if enabled is False:
        return None
    snippet = (text or "").strip()[:240]
    if len(snippet) < 12:
        return None
    # Derive a rough name from top tokens
    toks = re.findall(r"[a-z][a-z0-9_]{2,}", snippet.lower())
    name = slug_name("_".join(toks[:4]) or "assist_gap")
    dup = find_duplicate(name, snippet)
    row = {
        "action": "suggest",
        "name": name,
        "reason": reason,
        "snippet": snippet,
        "routes": (routes or [])[:3],
        "duplicate_of": dup,
        "hint": (
            f"existing {dup['id']}"
            if dup
            else f"./scripts/peer niche-mint --start --name {name} --io 'text → label' --reason '{reason}'"
        ),
        "unix": time.time(),
        "needle": NEEDLE,
    }
    DISTILL.mkdir(parents=True, exist_ok=True)
    with SUGGESTIONS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def suggest_from_assist() -> dict[str, Any]:
    if not ASSIST_LAST.is_file():
        return {"ok": False, "error": "no_assist_last"}
    try:
        blob = json.loads(ASSIST_LAST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}
    text = str(blob.get("input") or "")
    if blob.get("escalate_to_big_model") or blob.get("divert"):
        sug = record_opportunity(
            text=text,
            reason="assist_escalate" if blob.get("escalate_to_big_model") else "assist_divert",
            routes=blob.get("routes") or [],
        )
        return {"ok": True, "suggestion": sug, "assist": {"escalate": blob.get("escalate_to_big_model")}}
    return {"ok": True, "suggestion": None, "hint": "last assist did not escalate — no mint needed"}


def list_minted() -> dict[str, Any]:
    blob = _load_minted()
    return {
        "ok": True,
        "n": len(blob.get("niches") or []),
        "niches": blob.get("niches") or [],
        "path": str(MINTED.relative_to(ROOT)),
        "needle": NEEDLE,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="On-demand niche mint for agents")
    ap.add_argument("--propose", action="store_true")
    ap.add_argument("--start", action="store_true")
    ap.add_argument("--train", action="store_true", help="with --start: train immediately")
    ap.add_argument("--no-enqueue", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--suggest-from-assist", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--name", default="")
    ap.add_argument("--io", default="text → label")
    ap.add_argument("--reason", default="")
    ap.add_argument("--helps", default="")
    ap.add_argument("--example", action="append", default=[])
    ap.add_argument("--device", default="auto")
    args = ap.parse_args(argv)

    if args.list:
        print(json.dumps(list_minted(), indent=2))
        return 0
    if args.suggest_from_assist:
        print(json.dumps(suggest_from_assist(), indent=2))
        return 0
    if args.start:
        if not args.name or not args.reason:
            print(json.dumps({"ok": False, "error": "--name and --reason required"}))
            return 2
        out = start(
            name=args.name,
            io_spec=args.io,
            reason=args.reason,
            helps=args.helps,
            examples=args.example,
            train=args.train,
            enqueue=not args.no_enqueue,
            force=args.force,
            device=args.device,
        )
        print(json.dumps(out, indent=2, default=str))
        return 0 if out.get("ok") else 1
    if args.propose:
        if not args.name or not args.reason:
            print(json.dumps({"ok": False, "error": "--name and --reason required"}))
            return 2
        out = propose(
            name=args.name,
            io_spec=args.io,
            reason=args.reason,
            helps=args.helps,
            examples=args.example,
        )
        print(json.dumps(out, indent=2))
        return 0 if out.get("ok") else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
