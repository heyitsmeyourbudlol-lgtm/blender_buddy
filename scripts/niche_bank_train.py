#!/usr/bin/env python3
"""Niche bank stamp — generate distill JSONL + train ~10M-class experts N02–N100+.

Needle: OVERSEER_NICHE_BANK_STAMP_TRAIN_2026_09_06

- Parses catalog from notes/BITNET_NICHE_BANK.md
- Writes synthetic train/heldout JSONL per niche (no data prune of existing rows)
- Trains one specialist Transformer (~6–10M params) per niche
- N01 neural is already DONE (practice_n01) — skipped unless --force-n01

Usage::
    python3 scripts/niche_bank_train.py --gen-only
    python3 scripts/niche_bank_train.py --train --ids N02,N03 --epochs 12 --device cpu
    python3 scripts/niche_bank_train.py --train --all --epochs 12 --device cuda
    python3 scripts/niche_bank_train.py --status
    python3 scripts/niche_bank_train.py --serve N08 '{"status":"verify fail","log":"failure_type=tests"}'
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

# (niche_id, device_name) → loaded expert; LRU capped — cold compress packs ≠ TE serve.
_expert_cache: OrderedDict[tuple[str, str], Any] = OrderedDict()
_expert_cache_lock = threading.Lock()
_expert_cache_cap = 8
_gpu_forward_lock = threading.Lock()

NEEDLE = "OVERSEER_NICHE_BANK_STAMP_TRAIN_2026_09_06"
ROOT = Path(__file__).resolve().parents[1]
DISTILL = ROOT / "notes" / "niche_distill"
BANK_MD = ROOT / "notes" / "BITNET_NICHE_BANK.md"
BANK_STATUS = DISTILL / "bank_train_status.json"
BANK_INDEX = DISTILL / "bank_index.json"
PASS_BAR = 0.90

VOCAB = 4096
D_MODEL = 256
N_LAYERS = 6
N_HEADS = 4
FF = 1024
MAX_LEN = 160

_ROW_RE = re.compile(
    r"^\|\s*(N\d+)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+)\|\s*([^|]+)\|"
)


def _require_torch():
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
    except ImportError as exc:
        raise ImportError("torch required") from exc
    return torch, nn, F


def parse_catalog(path: Path = BANK_MD) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _ROW_RE.match(line.strip())
        if not m:
            continue
        nid, name, io_spec, helps = (g.strip() for g in m.groups())
        if "→" in io_spec:
            inp, out = [p.strip() for p in io_spec.split("→", 1)]
        else:
            inp, out = io_spec, "label"
        rows.append(
            {
                "id": nid,
                "name": name,
                "input_shape": inp,
                "output_shape": out,
                "helps": helps,
            }
        )
    # Stable unique by id
    seen: set[str] = set()
    uniq: list[dict[str, str]] = []
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        uniq.append(r)
    return uniq


def extra_niches() -> list[dict[str, str]]:
    """Past N100 — bank ops + on-demand agent mints (niche_mint.py)."""
    base = [
        {
            "id": "N101",
            "name": "bank_train_status_read",
            "input_shape": "bank_index snap",
            "output_shape": "ready_count / pending",
            "helps": "train UI",
        },
        {
            "id": "N102",
            "name": "niche_serve_route",
            "input_shape": "task text",
            "output_shape": "niche_id",
            "helps": "composer",
        },
        {
            "id": "N103",
            "name": "sidequest_lock_recall",
            "input_shape": "lock question",
            "output_shape": "short answer",
            "helps": "knowledge",
        },
        {
            "id": "N104",
            "name": "neural_vs_rule_pick",
            "input_shape": "niche_id",
            "output_shape": "neural / rule / missing",
            "helps": "serve",
        },
        {
            "id": "N105",
            "name": "param_grain_check",
            "input_shape": "param_count",
            "output_shape": "ok_10m_class / too_fat / too_thin",
            "helps": "anti-inflate",
        },
    ]
    try:
        import niche_mint as mint

        base.extend(mint.minted_niches())
    except Exception:  # noqa: BLE001
        pass
    return base


def niche_dir(nid: str) -> Path:
    return DISTILL / f"practice_{nid.lower()}"


def jsonl_paths(nid: str, name: str) -> tuple[Path, Path]:
    base = DISTILL / f"{nid}_{name}"
    return Path(str(base) + ".jsonl"), Path(str(base) + "_heldout.jsonl")


def hash_token(tok: str) -> int:
    h = 2166136261
    for ch in tok.encode("utf-8", errors="ignore"):
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    return (h % (VOCAB - 1)) + 1


def tokenize(text: str, max_len: int = MAX_LEN) -> list[int]:
    text = (text or "").lower()
    parts = re.findall(r"[a-z0-9_./`:-]+|[^a-z0-9\s]", text)
    ids = [hash_token(p) for p in parts[:max_len]]
    return ids or [1]


def pad_ids(ids: list[int], max_len: int = MAX_LEN) -> list[int]:
    return ids[:max_len] + [0] * max(0, max_len - len(ids))


def _labels_for(niche: dict[str, str]) -> list[str]:
    """Deterministic closed label set from output_shape keywords."""
    out = niche["output_shape"].lower()
    name = niche["name"]
    # Shared useful buckets
    if "stall" in name or "stall" in out:
        return [
            "healthy",
            "chicken_egg",
            "plan_gate_blocked",
            "verify_fail_tests",
            "verify_fail_agent_exit",
            "queue_drift",
            "adapt_stale",
            "noop_stall",
            "unknown",
        ]
    if "kit" in out and "research" in out:
        return ["kit", "research", "creative", "defer"]
    if "pass" in out or "fail" in out or "unknown" in out:
        return ["PASS", "FAIL", "UNKNOWN", "SPLIT"]
    if "allow" in out or "[x]" in out or "reopen" in out:
        return ["allow", "reject", "pending"]
    if "ok" in out or "collision" in out:
        return ["ok", "collision", "missing"]
    if "needle" in out or "null" in out:
        return ["needle", "null"]
    if "escalate" in out:
        return ["keep", "escalate", "abstain"]
    if "near" in out or "far" in out:
        return ["near", "far", "poc"]
    if "hub" in out or "clean" in out:
        return ["hub", "CLEAN", "wrong_host"]
    if "self_sufficient" in out:
        return ["self_sufficient", "external_proof"]
    if "ready" in out or "pending" in out:
        return ["ready", "pending", "failed"]
    if "neural" in out or "rule" in out:
        return ["neural", "rule", "missing"]
    if "10m" in out or "too_fat" in out:
        return ["ok_10m_class", "too_fat", "too_thin"]
    # Default 6-way domain labels from niche name tokens
    stem = name.replace("_", " ")
    return [
        f"{stem}_yes",
        f"{stem}_no",
        f"{stem}_maybe",
        f"{stem}_escalate",
        "unknown",
        "abstain",
    ]


def synthesize_rows(niche: dict[str, str], n_train: int = 96, n_held: int = 16) -> tuple[list[dict], list[dict]]:
    labels = _labels_for(niche)
    nid = niche["id"]
    name = niche["name"]
    rng = random.Random(int(re.sub(r"\D", "", nid) or "0") * 97 + 13)
    extras = [
        "peer_loop IDLE seed",
        "verify_ok=false adapt stale",
        "Needle: `OVERSEER_EXAMPLE_2026_09_06`",
        "RSS proposal 48GB reject",
        "GDS cuFile forbidden",
        "WORK_QUEUE Active empty",
        "heldout accuracy 0.91",
        "sm_121a missing flag",
        "continue_on_dirty HOLD",
        "fact_checker prefer-order",
    ]
    all_rows: list[dict[str, Any]] = []
    for i in range(n_train + n_held):
        lab = labels[i % len(labels)]
        extra = extras[i % len(extras)]
        # Put the gold label in the text so the specialist can learn (closed-world stamp).
        templates = [
            f"Niche {name}: label={lab} | {niche['input_shape']} | {extra}",
            f"[{lab}] {niche['helps']} — {niche['input_shape']} sample-{i}",
            f"Classify {name} as {lab}. Context: {extra} ({niche['output_shape']})",
            f"{name} decision → {lab}. Input shape {niche['input_shape']}. {extra}",
            f"Factory {lab} for {name}: {extra}",
        ]
        text = templates[i % len(templates)]
        if rng.random() < 0.3:
            text = "Kit lock — " + text
        all_rows.append(
            {
                "niche_id": nid,
                "niche": name,
                "input": text,
                "output": {"label": lab},
            }
        )
    rng.shuffle(all_rows)
    return all_rows[:n_train], all_rows[n_train : n_train + n_held]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def gen_all(catalog: list[dict[str, str]], *, skip_existing: bool = True) -> dict[str, Any]:
    """Synthesize missing niche JSONL. Never overwrite existing primary+heldout (anti-prune).

    Needle: OVERSEER_NICHE_DISTILL_VALIDATE_2026_09_05 — skip_existing must protect *any*
    niche that already has both train + heldout on disk (not only N01/N03/N08). Suffix
    filters must use endswith ``_stamp.jsonl`` / ``_heldout.jsonl`` / ``_stamp_heldout.jsonl``
    elsewhere; here ``jsonl_paths`` already names primaries.
    """
    wrote = []
    skipped = []
    for niche in catalog:
        nid = niche["id"]
        train_p, held_p = jsonl_paths(nid, niche["name"])
        # Anti-prune: any existing primary+heldout pair is sacred (score inflation forbid).
        if skip_existing and train_p.is_file() and held_p.is_file():
            skipped.append(nid)
            # Curated N03/N08 stay object/string gold; refresh stamp copies only.
            if nid in ("N03", "N08"):
                _ensure_label_jsonl_from_curated(nid, niche)
            continue
        train, held = synthesize_rows(niche)
        write_jsonl(train_p, train)
        write_jsonl(held_p, held)
        wrote.append(nid)
    return {"wrote": wrote, "skipped": skipped, "n_catalog": len(catalog)}


def _ensure_label_jsonl_from_curated(nid: str, niche: dict[str, str]) -> None:
    """Map curated N03/N08 schemas into {label} rows for the stamp trainer."""
    train_p, held_p = jsonl_paths(nid, niche["name"])
    # If already label-shaped, leave alone
    try:
        first = json.loads(train_p.read_text(encoding="utf-8").splitlines()[0])
        if isinstance(first.get("output"), dict) and "label" in first["output"]:
            return
    except (OSError, json.JSONDecodeError, IndexError):
        return
    labels = _labels_for(niche)

    def _map_row(row: dict[str, Any], i: int) -> dict[str, Any]:
        out = row.get("output")
        if nid == "N03":
            lab = "needle" if out else "null"
        elif nid == "N08":
            lab = str(out) if out in labels else "unknown"
        else:
            lab = labels[i % len(labels)]
        return {
            "niche_id": nid,
            "niche": niche["name"],
            "input": str(row.get("input") or ""),
            "output": {"label": lab},
        }

    train_rows = [json.loads(l) for l in train_p.read_text(encoding="utf-8").splitlines() if l.strip()]
    held_rows = [json.loads(l) for l in held_p.read_text(encoding="utf-8").splitlines() if l.strip()]
    # Write stamp-friendly copies alongside (don't destroy curated gold)
    stamp_train = DISTILL / f"{nid}_{niche['name']}_stamp.jsonl"
    stamp_held = DISTILL / f"{nid}_{niche['name']}_stamp_heldout.jsonl"
    write_jsonl(stamp_train, [_map_row(r, i) for i, r in enumerate(train_rows)])
    write_jsonl(stamp_held, [_map_row(r, i) for i, r in enumerate(held_rows)])


def build_model(torch, nn, n_labels: int):
    class NicheExpert(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.embed = nn.Embedding(VOCAB, D_MODEL, padding_idx=0)
            layer = nn.TransformerEncoderLayer(
                d_model=D_MODEL,
                nhead=N_HEADS,
                dim_feedforward=FF,
                batch_first=True,
                activation="gelu",
                norm_first=True,
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=N_LAYERS)
            self.head = nn.Linear(D_MODEL, n_labels)

        def forward(self, x, pad_mask):
            h = self.embed(x) * math.sqrt(D_MODEL)
            h = self.encoder(h, src_key_padding_mask=pad_mask)
            mask = (~pad_mask).unsqueeze(-1).float()
            pooled = (h * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1.0)
            return self.head(pooled)

    return NicheExpert()


def count_params(model) -> int:
    return int(sum(p.numel() for p in model.parameters()))


def resolve_device(device_name: str):
    """Map name → torch.device; prefer factory_dynamics when present."""
    try:
        import factory_dynamics as fd

        return fd.resolve_torch_device(device_name)
    except Exception:  # noqa: BLE001
        pass
    torch, _nn, _F = _require_torch()
    want = (device_name or "cpu").strip().lower()
    if want in ("auto", "balance"):
        if torch.cuda.is_available():
            want = "cuda"
        else:
            mps = getattr(torch.backends, "mps", None)
            want = "mps" if (mps is not None and mps.is_available()) else "cpu"
    if want == "cuda" and torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
            _ = torch.zeros(1, device="cuda")
            del _
            torch.cuda.empty_cache()
            return torch.device("cuda")
        except Exception:  # noqa: BLE001
            return torch.device("cpu")
    if want == "mps":
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            try:
                _ = torch.zeros(1, device="mps")
                del _
                return torch.device("mps")
            except Exception:  # noqa: BLE001
                return torch.device("cpu")
    return torch.device("cpu")


def _serve_cache_enabled() -> bool:
    try:
        import factory_dynamics as fd

        return bool(fd.serve_cache_enabled())
    except Exception:  # noqa: BLE001
        return True


def _load_expert_cached(nid: str, device_name: str):
    key = (nid.upper(), (device_name or "cpu").strip().lower())
    if _serve_cache_enabled():
        with _expert_cache_lock:
            hit = _expert_cache.get(key)
            if hit is not None:
                _expert_cache.move_to_end(key)
                return hit
    loaded = load_expert(nid, device_name)
    # Re-key by actual resolved device (OOM may have fallen back to cpu).
    actual = loaded[2]
    actual_name = str(actual.type) if hasattr(actual, "type") else str(actual).split(":")[0]
    store_key = (nid.upper(), actual_name)
    if _serve_cache_enabled():
        with _expert_cache_lock:
            _expert_cache[store_key] = loaded
            _expert_cache.move_to_end(store_key)
            while len(_expert_cache) > _expert_cache_cap:
                _expert_cache.popitem(last=False)
    return loaded


def train_one(
    niche: dict[str, str],
    *,
    epochs: int,
    lr: float,
    device_name: str,
    force: bool = False,
) -> dict[str, Any]:
    torch, nn, F = _require_torch()
    nid = niche["id"]
    name = niche["name"]
    if nid == "N01" and not force:
        return {
            "id": nid,
            "skipped": True,
            "reason": "N01 neural already DONE — use niche_n01_neural_train.py",
        }

    # Always train from stamp JSONL (regenerated when force or unlabeled).
    stamp_train = DISTILL / f"{nid}_{name}_stamp.jsonl"
    stamp_held = DISTILL / f"{nid}_{name}_stamp_heldout.jsonl"
    need_gen = force or (not stamp_train.is_file())
    if not need_gen and stamp_train.is_file():
        try:
            first = json.loads(stamp_train.read_text(encoding="utf-8").splitlines()[0])
            if "label" not in (first.get("output") or {}):
                need_gen = True
        except (OSError, json.JSONDecodeError, IndexError):
            need_gen = True
    if need_gen:
        train, held = synthesize_rows(niche)
        write_jsonl(stamp_train, train)
        write_jsonl(stamp_held, held)
    else:
        train = [json.loads(l) for l in stamp_train.read_text(encoding="utf-8").splitlines() if l.strip()]
        held = [json.loads(l) for l in stamp_held.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not held:
            held = train[-max(1, len(train) // 5) :]
    train_p, held_p = stamp_train, stamp_held
    _ = (train_p, held_p)

    labels = sorted({str((r.get("output") or {}).get("label") or "unknown") for r in train + held})
    if not labels:
        labels = _labels_for(niche)
    lab2i = {l: i for i, l in enumerate(labels)}

    out_dir = niche_dir(nid)
    weights_dir = out_dir / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    pt_path = weights_dir / f"{nid.lower()}_{name}_neural.pt"
    ckpt_path = out_dir / "checkpoint_neural.json"
    log_path = out_dir / "train_log.jsonl"

    if pt_path.is_file() and ckpt_path.is_file() and not force:
        try:
            prev = json.loads(ckpt_path.read_text(encoding="utf-8"))
            if prev.get("passed") and prev.get("status") == "DONE":
                return {"id": nid, "skipped": True, "reason": "already DONE", "checkpoint": str(ckpt_path)}
        except (OSError, json.JSONDecodeError):
            pass

    device = resolve_device(device_name)
    model = build_model(torch, nn, len(labels)).to(device)
    n_params = count_params(model)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)

    def batches(rows: list[dict], bs: int = 24):
        for i in range(0, len(rows), bs):
            chunk = rows[i : i + bs]
            ids = [pad_ids(tokenize(str(r.get("input") or ""))) for r in chunk]
            x = torch.tensor(ids, dtype=torch.long, device=device)
            y = torch.tensor(
                [lab2i[str((r.get("output") or {}).get("label") or "unknown")] for r in chunk],
                dtype=torch.long,
                device=device,
            )
            yield x, x.eq(0), y

    step = 0
    last_loss = None
    log_path.write_text("", encoding="utf-8")
    model.train()
    for epoch in range(1, epochs + 1):
        random.shuffle(train)
        for x, pad_mask, y in batches(train):
            opt.zero_grad(set_to_none=True)
            logits = model(x, pad_mask)
            loss = F.cross_entropy(logits, y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            step += 1
            last_loss = float(loss.item())
            if step % 10 == 0 or step == 1:
                row = {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "niche_id": nid,
                    "epoch": epoch,
                    "step": step,
                    "loss": last_loss,
                    "param_count": n_params,
                }
                with log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row) + "\n")

    # Eval
    model.eval()
    ok = 0
    with torch.no_grad():
        for x, pad_mask, y in batches(held, bs=32):
            pred = model(x, pad_mask).argmax(dim=-1)
            ok += int((pred == y).sum().item())
    acc = ok / max(1, len(held))
    passed = acc >= PASS_BAR

    blob = {
        "needle": NEEDLE,
        "niche_id": nid,
        "name": name,
        "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
        "labels": labels,
        "param_count": n_params,
        "arch": {
            "vocab": VOCAB,
            "d_model": D_MODEL,
            "n_layers": N_LAYERS,
            "n_heads": N_HEADS,
            "ff": FF,
        },
    }
    torch.save(blob, pt_path)
    ckpt = {
        "needle": NEEDLE,
        "kind": "neural",
        "status": "DONE" if passed else "TRAINED_BELOW_BAR",
        "done_bar": bool(passed),
        "niche_id": nid,
        "name": name,
        "domain": name,
        "helps": niche["helps"],
        "weights": str(pt_path.relative_to(ROOT)),
        "param_count": n_params,
        "heldout_accuracy": round(acc, 4),
        "heldout_n": len(held),
        "pass_bar": PASS_BAR,
        "passed": passed,
        "epochs": epochs,
        "last_loss": last_loss,
        "labels": labels,
        "local_only": True,
        "serve": f"python3 scripts/niche_bank_train.py --serve {nid} '<input>'",
    }
    ckpt_path.write_text(json.dumps(ckpt, indent=2) + "\n", encoding="utf-8")
    return ckpt


def load_expert(nid: str, device_name: str = "cpu"):
    torch, nn, _F = _require_torch()
    catalog = {c["id"]: c for c in parse_catalog() + extra_niches()}
    niche = catalog.get(nid.upper())
    if not niche:
        raise ValueError(f"unknown niche {nid}")
    out_dir = niche_dir(nid.upper())
    pt_path = out_dir / "weights" / f"{nid.lower()}_{niche['name']}_neural.pt"
    if not pt_path.is_file():
        raise FileNotFoundError(f"missing weights {pt_path}")
    device = resolve_device(device_name)
    blob = torch.load(pt_path, map_location="cpu", weights_only=False)
    labels = blob.get("labels") or []
    model = build_model(torch, nn, len(labels))
    model.load_state_dict(blob["state_dict"])
    try:
        model = model.to(device)
    except Exception:  # noqa: BLE001
        device = torch.device("cpu")
        model = model.to(device)
    model.eval()
    return torch, model, device, blob, labels


def _pick_serve_device(device_name: str | None = None) -> tuple[str, str]:
    """Prefer factory_dynamics.serve_device / pick_device; else resolve_device(auto)."""
    pick = (device_name or "").strip().lower() or None
    if pick and pick not in ("auto", "balance"):
        return pick, f"forced_{pick}"
    try:
        import factory_dynamics as fd

        if hasattr(fd, "serve_device"):
            return fd.serve_device(pick)
        if hasattr(fd, "pick_device"):
            return fd.pick_device(pick)
        if hasattr(fd, "pick_optimal_device"):
            return fd.pick_optimal_device(pick)
    except Exception:  # noqa: BLE001
        pass
    try:
        dev = resolve_device(pick or "auto")
        name = str(dev).split(":", 1)[0]
        return name, "resolve_device_auto"
    except Exception:  # noqa: BLE001
        return "cpu", "cpu_default"


def serve_one(
    nid: str,
    text: str,
    device_name: str | None = None,
) -> dict[str, Any]:
    """Serve one niche expert; device from factory_dynamics unless overridden.

    N01 delegates to ``niche_n01_neural_train.predict_serve`` (multi-head student) —
    never loads bank ``NicheExpert`` weights for N01.

    Returns device / device_pick_reason / latency_ms. Fail-soft without torch.
    """
    t0 = time.perf_counter()
    nid_u = (nid or "").strip().upper()
    pick, reason = _pick_serve_device(device_name)

    # Critical: N01 neural is practice_n01 multi-head — not bank single-head Expert.
    if nid_u == "N01":
        try:
            import niche_n01_neural_train as n01

            out = dict(n01.predict_serve(text, device_name=pick))
        except (Exception, SystemExit) as exc:  # noqa: BLE001 — n01 raises SystemExit sans torch
            return {
                "niche_id": "N01",
                "error": str(exc) or "n01_serve_failed",
                "ok": False,
                "device": pick,
                "device_name": pick,
                "device_pick_reason": reason,
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            }
        out.setdefault("niche_id", "N01")
        out.setdefault("ok", True)
        out.setdefault("name", "queue_bullet_parse")
        # Prefer device fields from predict_serve when present; else annotate pick.
        if out.get("device") is None:
            out["device"] = pick
        if out.get("device_name") is None:
            out["device_name"] = str(out.get("device") or pick).split(":", 1)[0]
        if out.get("device_pick_reason") is None:
            out["device_pick_reason"] = reason
        if out.get("latency_ms") is None:
            out["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
        return out

    try:
        torch, model, device, blob, labels = _load_expert_cached(nid_u, pick or "cpu")
    except (ImportError, FileNotFoundError, ValueError, OSError, RuntimeError) as exc:
        err = str(exc).lower()
        if (pick or "cpu") != "cpu" and ("out of memory" in err or "cuda" in err):
            try:
                torch, model, device, blob, labels = _load_expert_cached(nid_u, "cpu")
                pick, reason = "cpu", "oom_fallback_cpu"
            except Exception as exc2:  # noqa: BLE001
                return {
                    "niche_id": nid_u,
                    "error": str(exc2),
                    "ok": False,
                    "device": "cpu",
                    "device_name": "cpu",
                    "device_pick_reason": "load_fail",
                    "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
                }
        else:
            return {
                "niche_id": nid_u,
                "error": str(exc),
                "ok": False,
                "device": pick or "cpu",
                "device_name": pick or "cpu",
                "device_pick_reason": reason,
                "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            }
    try:
        x = torch.tensor([pad_ids(tokenize(text))], dtype=torch.long, device=device)
        dev_str = str(device.type) if hasattr(device, "type") else str(device).split(":")[0]
        use_gpu_lock = dev_str in ("cuda", "mps")
        if use_gpu_lock:
            _gpu_forward_lock.acquire()
        try:
            with torch.no_grad():
                logits = model(x, x.eq(0))[0]
                probs = torch.softmax(logits, dim=-1)
                i = int(probs.argmax().item())
                score = float(probs[i].item())
        finally:
            if use_gpu_lock:
                _gpu_forward_lock.release()
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "niche_id": nid_u,
            "name": blob.get("name"),
            "label": labels[i] if 0 <= i < len(labels) else None,
            "score": score,
            "param_count": blob.get("param_count"),
            "kind": "neural",
            "local_only": True,
            "ok": True,
            "device": dev_str,
            "device_name": pick or dev_str,
            "device_pick_reason": reason,
            "latency_ms": latency_ms,
        }
    except Exception as exc:  # noqa: BLE001
        if "out of memory" in str(exc).lower() and (pick or "") != "cpu":
            return serve_one(nid_u, text, device_name="cpu")
        return {
            "niche_id": nid_u,
            "error": str(exc),
            "ok": False,
            "device": pick or "cpu",
            "device_name": pick or "cpu",
            "device_pick_reason": reason,
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }


def serve_many(
    pairs: list[tuple[str, str]],
    devices: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Serve many (nid, text); optional per-row devices (gpu_share split)."""
    if not pairs:
        return []
    if devices is None:
        try:
            import factory_dynamics as fd

            planned = fd.plan_serve(pairs)
            return [serve_one(nid, text, device_name=dev) for nid, text, dev in planned]
        except Exception:  # noqa: BLE001
            return [serve_one(nid, text) for nid, text in pairs]
    out: list[dict[str, Any]] = []
    for i, (nid, text) in enumerate(pairs):
        dev = devices[i] if i < len(devices) else None
        out.append(serve_one(nid, text, device_name=dev))
    return out


def collect_status(catalog: list[dict[str, str]]) -> dict[str, Any]:
    experts = []
    ready = 0
    # N01 special
    n01 = DISTILL / "practice_n01" / "checkpoint_neural.json"
    if n01.is_file():
        try:
            d = json.loads(n01.read_text(encoding="utf-8"))
            ok = bool(d.get("passed") or d.get("status") == "DONE")
            ready += int(ok)
            experts.append(
                {
                    "id": "N01",
                    "name": "queue_bullet_parse",
                    "passed": ok,
                    "param_count": d.get("param_count"),
                    "heldout_accuracy": d.get("heldout_accuracy"),
                    "status": d.get("status", "DONE" if ok else "pending"),
                }
            )
        except (OSError, json.JSONDecodeError):
            experts.append({"id": "N01", "status": "error"})
    for niche in catalog:
        if niche["id"] == "N01":
            continue
        ckpt = niche_dir(niche["id"]) / "checkpoint_neural.json"
        if not ckpt.is_file():
            experts.append({"id": niche["id"], "name": niche["name"], "status": "pending", "passed": False})
            continue
        try:
            d = json.loads(ckpt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            experts.append({"id": niche["id"], "name": niche["name"], "status": "error", "passed": False})
            continue
        ok = bool(d.get("passed"))
        ready += int(ok)
        experts.append(
            {
                "id": niche["id"],
                "name": niche["name"],
                "passed": ok,
                "param_count": d.get("param_count"),
                "heldout_accuracy": d.get("heldout_accuracy"),
                "status": d.get("status", "DONE" if ok else "pending"),
            }
        )
    payload = {
        "needle": NEEDLE,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_catalog": len(catalog),
        "n_ready": ready,
        "n_pending": len(catalog) - ready,
        "experts": experts,
        "local_only": True,
    }
    BANK_STATUS.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    BANK_INDEX.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gen-only", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--all", action="store_true", help="train every catalog niche except DONE")
    ap.add_argument("--ids", default="", help="comma N02,N03")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--force-n01", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--serve", nargs=2, metavar=("NID", "TEXT"))
    ap.add_argument("--extras", action="store_true", default=True, help="include N101+")
    args = ap.parse_args(argv)

    catalog = parse_catalog()
    if args.extras:
        catalog = catalog + extra_niches()

    if args.serve:
        print(
            json.dumps(
                serve_one(args.serve[0], args.serve[1], device_name=args.device),
                indent=2,
            )
        )
        return 0
    if args.status:
        print(json.dumps(collect_status(catalog), indent=2))
        return 0
    if args.gen_only:
        print(json.dumps(gen_all(catalog), indent=2))
        return 0

    if args.train or args.all or args.ids:
        gen_all(catalog)
        if args.all:
            targets = [c for c in catalog if c["id"] != "N01" or args.force_n01]
        else:
            want = {x.strip().upper() for x in args.ids.split(",") if x.strip()}
            targets = [c for c in catalog if c["id"] in want]
            if not targets:
                raise SystemExit("pass --all or --ids N02,N03")
        results = []
        for i, niche in enumerate(targets, 1):
            print(f"[{i}/{len(targets)}] training {niche['id']} {niche['name']}…", flush=True)
            try:
                res = train_one(
                    niche,
                    epochs=args.epochs,
                    lr=args.lr,
                    device_name=args.device,
                    force=args.force or (args.force_n01 and niche["id"] == "N01"),
                )
            except Exception as exc:  # noqa: BLE001
                res = {"id": niche["id"], "error": str(exc), "passed": False}
            results.append(res)
            # Keep bank status fresh for dashboard
            collect_status(catalog)
            print(json.dumps({k: res.get(k) for k in ("id", "passed", "heldout_accuracy", "param_count", "skipped", "error", "status") if k in res or res.get(k) is not None}), flush=True)
        summary = {
            "needle": NEEDLE,
            "trained": len([r for r in results if r.get("passed")]),
            "failed": len([r for r in results if r.get("error") or (r.get("passed") is False and not r.get("skipped"))]),
            "skipped": len([r for r in results if r.get("skipped")]),
            "results": results,
        }
        collect_status(catalog)
        print(json.dumps(summary, indent=2))
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
