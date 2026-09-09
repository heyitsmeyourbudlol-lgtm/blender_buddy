#!/usr/bin/env python3
"""Train a real ~10M neural student that encodes sidequest + niche skills.

Needle: OVERSEER_N01_NEURAL_TRAIN_2026_09_06

Not a rule baseline. Not stock Ollama. Torch weight updates with loss logs.

Tasks mixed into one student (~10M params):
  - N01 queue_bullet_parse (kit / scope / needle)
  - N03 land-proof needle extract
  - N08 stall class
  - Sidequest knowledge QA (1Q/10T/NVFP4/local-only/factory locks — no prune)

Usage::
    python3 scripts/niche_n01_neural_train.py --train --epochs 8
    python3 scripts/niche_n01_neural_train.py --eval-only
    python3 scripts/niche_n01_neural_train.py --ask "What is the hot dtype?"
    python3 scripts/niche_n01_neural_train.py --serve '- [ ] **[kit] x — scripts/peer_loop.py Needle: `OVERSEER_X`.'
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import time
from pathlib import Path
from typing import Any

NEEDLE = "OVERSEER_N01_NEURAL_TRAIN_2026_09_06"
ROOT = Path(__file__).resolve().parents[1]
DISTILL = ROOT / "notes" / "niche_distill"
PRACTICE = DISTILL / "practice_n01"
WEIGHTS_DIR = PRACTICE / "weights"
NEURAL_PT = WEIGHTS_DIR / "n01_queue_bullet_parse_neural.pt"
CKPT_JSON = PRACTICE / "checkpoint_neural.json"
TRAIN_LOG = PRACTICE / "train_log.jsonl"
STATUS_JSON = PRACTICE / "train_status.json"
KNOWLEDGE_JSON = DISTILL / "sidequest_knowledge.json"
N01_JSONL = DISTILL / "N01_queue_bullet_parse.jsonl"
N01_HELD = DISTILL / "N01_queue_bullet_parse_heldout.jsonl"
N03_JSONL = DISTILL / "N03_land_proof_needle_match.jsonl"
N03_HELD = DISTILL / "N03_land_proof_needle_match_heldout.jsonl"
N08_JSONL = DISTILL / "N08_stall_class_label.jsonl"
N08_HELD = DISTILL / "N08_stall_class_label_heldout.jsonl"
KNOWLEDGE_PARAPHRASE_PREFIXES = (
    "",
    "In this Automation sidequest: ",
    "Kit lock — answer briefly: ",
    "For the local factory model: ",
    "Sidequest honesty: ",
)

VOCAB = 4096
D_MODEL = 256
N_LAYERS = 6
N_HEADS = 4
FF = 1024
MAX_LEN = 192
PASS_BAR = 0.90

_STALL_CLASSES = [
    "healthy",
    "chicken_egg",
    "plan_gate_blocked",
    "verify_fail_tests",
    "verify_fail_agent_exit",
    "queue_drift",
    "adapt_stale",
    "noop_stall",
    "deferred_lean_restamp",
    "last_cycle_poison",
    "dirty_tree_notes_only",
    "loaded_no_pid",
    "namespace_flip",
    "oversight_down",
    "peer_quiet",
    "unknown",
]


def _require_torch():
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("torch required — run on CLEAN with torch installed") from exc
    return torch, nn, F


def hash_token(tok: str) -> int:
    h = 2166136261
    for ch in tok.encode("utf-8", errors="ignore"):
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    return (h % (VOCAB - 1)) + 1  # reserve 0 for pad


def tokenize(text: str, max_len: int = MAX_LEN) -> list[int]:
    text = (text or "").lower()
    parts = re.findall(r"[a-z0-9_./`:-]+|[^a-z0-9\s]", text)
    ids = [hash_token(p) for p in parts[:max_len]]
    if not ids:
        ids = [1]
    return ids


def pad_ids(ids: list[int], max_len: int = MAX_LEN) -> list[int]:
    if len(ids) >= max_len:
        return ids[:max_len]
    return ids + [0] * (max_len - len(ids))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_knowledge() -> list[dict[str, Any]]:
    if not KNOWLEDGE_JSON.is_file():
        return []
    raw = KNOWLEDGE_JSON.read_text(encoding="utf-8")
    # tolerate accidental comment headers
    lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("#")]
    data = json.loads("\n".join(lines))
    assert isinstance(data, list)
    return data


def split_heldout(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        (held if (i % 5) == 4 else train).append(row)
    if not held and rows:
        held = [rows[-1]]
        train = rows[:-1]
    return train, held


def _n01_ex(row: dict[str, Any]) -> dict[str, Any]:
    out = row.get("output") or {}
    return {
        "task": "n01",
        "input": str(row.get("input") or ""),
        "kit": out.get("kit"),
        "scope": str(out.get("scope") or "") or None,
        "needle": out.get("needle"),
        "answer": None,
        "answer_id": -1,
        "stall": None,
    }


def _n03_ex(row: dict[str, Any]) -> dict[str, Any]:
    gold = row.get("output")
    if isinstance(gold, dict):
        needle = gold.get("needle")
    else:
        needle = gold
    return {
        "task": "n03",
        "input": str(row.get("input") or row.get("item") or ""),
        "kit": None,
        "scope": None,
        "needle": needle,
        "answer": None,
        "answer_id": -1,
        "stall": None,
    }


def _n08_ex(row: dict[str, Any]) -> dict[str, Any]:
    inp = row.get("input")
    if isinstance(inp, dict):
        text = json.dumps(inp, ensure_ascii=False)
    else:
        text = str(inp or "")
    gold = row.get("output")
    if isinstance(gold, dict):
        stall = str(gold.get("stall_class") or gold.get("label") or "unknown")
    else:
        stall = str(gold or "unknown")
    if stall not in _STALL_CLASSES:
        stall = "unknown"
    return {
        "task": "n08",
        "input": text,
        "kit": None,
        "scope": None,
        "needle": None,
        "answer": None,
        "answer_id": -1,
        "stall": stall,
    }


def _knowledge_examples() -> tuple[list[dict[str, Any]], list[str]]:
    """Paraphrased prompts → answer_id; answers list is the retrieval vocab."""
    knowledge = load_knowledge()
    answers: list[str] = []
    for row in knowledge:
        ans = str((row.get("output") or {}).get("answer") or "")
        if ans not in answers:
            answers.append(ans)
    answer_to_id = {a: i for i, a in enumerate(answers)}
    examples: list[dict[str, Any]] = []
    for row in knowledge:
        q = str(row.get("input") or "")
        ans = str((row.get("output") or {}).get("answer") or "")
        aid = answer_to_id[ans]
        for prefix in KNOWLEDGE_PARAPHRASE_PREFIXES:
            examples.append(
                {
                    "task": "knowledge",
                    "input": prefix + q,
                    "kit": None,
                    "scope": None,
                    "needle": None,
                    "answer": ans,
                    "answer_id": aid,
                    "stall": None,
                }
            )
    return examples, answers


def build_examples() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Full corpus — no prune. Honest niche heldout files + knowledge split."""
    train: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []

    train.extend(_n01_ex(r) for r in load_jsonl(N01_JSONL))
    held.extend(_n01_ex(r) for r in load_jsonl(N01_HELD))
    train.extend(_n03_ex(r) for r in load_jsonl(N03_JSONL))
    held.extend(_n03_ex(r) for r in load_jsonl(N03_HELD))
    train.extend(_n08_ex(r) for r in load_jsonl(N08_JSONL))
    held.extend(_n08_ex(r) for r in load_jsonl(N08_HELD))

    know_ex, answers = _knowledge_examples()
    k_train, k_held = split_heldout(know_ex)
    train.extend(k_train)
    held.extend(k_held)

    # If dedicated heldout files missing, fall back so eval still runs
    if not held:
        rng = random.Random(20260906)
        rng.shuffle(train)
        train, held = split_heldout(train)

    rng = random.Random(20260906)
    rng.shuffle(train)
    rng.shuffle(held)
    return train, held, answers


def kit_label(v: Any) -> int:
    if v is True:
        return 2
    if v is False:
        return 1
    return 0  # null/unknown


def build_label_vocabs(examples: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    scopes: dict[str, int] = {"<none>": 0}
    needles: dict[str, int] = {"<none>": 0}
    for ex in examples:
        if ex.get("scope"):
            s = ex["scope"]
            if s not in scopes:
                scopes[s] = len(scopes)
        if ex.get("needle"):
            n = str(ex["needle"])
            if n not in needles:
                needles[n] = len(needles)
    return scopes, needles


def build_model(torch, nn, n_scope: int, n_needle: int, n_knowledge: int):
    class SidequestStudent(nn.Module):
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
            self.kit_head = nn.Linear(D_MODEL, 3)
            self.scope_head = nn.Linear(D_MODEL, n_scope)
            self.needle_head = nn.Linear(D_MODEL, n_needle)
            self.stall_head = nn.Linear(D_MODEL, len(_STALL_CLASSES))
            self.knowledge_head = nn.Linear(D_MODEL, max(1, n_knowledge))
            self.answer_head = nn.Linear(D_MODEL, VOCAB)

        def encode(self, x, pad_mask):
            h = self.embed(x) * math.sqrt(D_MODEL)
            h = self.encoder(h, src_key_padding_mask=pad_mask)
            mask = (~pad_mask).unsqueeze(-1).float()
            pooled = (h * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1.0)
            return pooled

        def forward(self, x, pad_mask):
            pooled = self.encode(x, pad_mask)
            return {
                "kit": self.kit_head(pooled),
                "scope": self.scope_head(pooled),
                "needle": self.needle_head(pooled),
                "stall": self.stall_head(pooled),
                "knowledge": self.knowledge_head(pooled),
                "answer": self.answer_head(pooled),
            }

    return SidequestStudent()


def count_params(model) -> int:
    return int(sum(p.numel() for p in model.parameters()))


def write_status(payload: dict[str, Any]) -> None:
    PRACTICE.mkdir(parents=True, exist_ok=True)
    STATUS_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def append_log(row: dict[str, Any]) -> None:
    PRACTICE.mkdir(parents=True, exist_ok=True)
    with TRAIN_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def batchify(examples: list[dict[str, Any]], torch, device, batch_size: int = 16):
    for i in range(0, len(examples), batch_size):
        chunk = examples[i : i + batch_size]
        ids = [pad_ids(tokenize(ex["input"])) for ex in chunk]
        x = torch.tensor(ids, dtype=torch.long, device=device)
        pad_mask = x.eq(0)
        yield chunk, x, pad_mask


def train_loop(*, epochs: int, lr: float, device_name: str) -> dict[str, Any]:
    torch, nn, F = _require_torch()
    device = torch.device(device_name if (device_name != "cuda" or torch.cuda.is_available()) else "cpu")
    train_ex, held_ex, answers = build_examples()
    # Oversample niches so skills aren't drowned by knowledge paraphrases
    boost = [ex for ex in train_ex if ex["task"] in ("n01", "n03", "n08")]
    train_ex = train_ex + boost * 3
    scopes, needles = build_label_vocabs(train_ex + held_ex)
    inv_scope = {v: k for k, v in scopes.items()}
    inv_needle = {v: k for k, v in needles.items()}
    model = build_model(torch, nn, len(scopes), len(needles), len(answers)).to(device)
    n_params = count_params(model)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)

    write_status(
        {
            "needle": NEEDLE,
            "status": "running",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "param_count": n_params,
            "device": str(device),
            "epoch": 0,
            "step": 0,
            "loss": None,
            "n_train": len(train_ex),
            "n_heldout": len(held_ex),
            "n_scope": len(scopes),
            "n_needle": len(needles),
            "n_knowledge": len(answers),
            "note": "real weight updates — sidequest knowledge + niches",
        }
    )
    if TRAIN_LOG.is_file():
        TRAIN_LOG.unlink()

    step = 0
    last_loss = None
    for epoch in range(1, epochs + 1):
        model.train()
        random.Random(20260906 + epoch).shuffle(train_ex)
        epoch_loss = 0.0
        n_batches = 0
        for chunk, x, pad_mask in batchify(train_ex, torch, device):
            out = model(x, pad_mask)
            losses = []
            for j, ex in enumerate(chunk):
                task = ex["task"]
                if task == "n01":
                    losses.append(
                        2.0
                        * F.cross_entropy(
                            out["kit"][j : j + 1],
                            torch.tensor([kit_label(ex["kit"])], device=device),
                        )
                    )
                    sid = scopes.get(ex.get("scope") or "<none>", 0)
                    losses.append(
                        F.cross_entropy(out["scope"][j : j + 1], torch.tensor([sid], device=device))
                    )
                    nid = needles.get(str(ex["needle"]) if ex.get("needle") else "<none>", 0)
                    losses.append(
                        F.cross_entropy(out["needle"][j : j + 1], torch.tensor([nid], device=device))
                    )
                elif task == "n03":
                    nid = needles.get(str(ex["needle"]) if ex.get("needle") else "<none>", 0)
                    losses.append(
                        F.cross_entropy(out["needle"][j : j + 1], torch.tensor([nid], device=device))
                    )
                elif task == "n08":
                    si = _STALL_CLASSES.index(ex["stall"] if ex["stall"] in _STALL_CLASSES else "unknown")
                    losses.append(
                        F.cross_entropy(out["stall"][j : j + 1], torch.tensor([si], device=device))
                    )
                elif task == "knowledge":
                    aid = int(ex.get("answer_id", -1))
                    if aid >= 0:
                        losses.append(
                            2.0
                            * F.cross_entropy(
                                out["knowledge"][j : j + 1],
                                torch.tensor([aid], device=device),
                            )
                        )
                    ans_ids = tokenize(ex.get("answer") or "", max_len=64)
                    for tid in ans_ids[:16]:
                        losses.append(
                            0.25
                            * F.cross_entropy(out["answer"][j : j + 1], torch.tensor([tid], device=device))
                        )
            if not losses:
                continue
            loss = torch.stack(losses).mean()
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            step += 1
            last_loss = float(loss.item())
            epoch_loss += last_loss
            n_batches += 1
            if step % 5 == 0 or step == 1:
                row = {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "epoch": epoch,
                    "step": step,
                    "loss": last_loss,
                    "param_count": n_params,
                }
                append_log(row)
                write_status(
                    {
                        "needle": NEEDLE,
                        "status": "running",
                        "ts": row["ts"],
                        "param_count": n_params,
                        "device": str(device),
                        "epoch": epoch,
                        "step": step,
                        "loss": last_loss,
                        "n_train": len(train_ex),
                        "n_heldout": len(held_ex),
                    }
                )
        metrics = evaluate(model, held_ex, torch, device, scopes, needles)
        append_log(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "epoch": epoch,
                "step": step,
                "loss": epoch_loss / max(1, n_batches),
                "heldout": metrics,
                "param_count": n_params,
            }
        )

    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "needle": NEEDLE,
        "kind": "neural",
        "param_count": n_params,
        "arch": {
            "vocab": VOCAB,
            "d_model": D_MODEL,
            "n_layers": N_LAYERS,
            "n_heads": N_HEADS,
            "ff": FF,
            "max_len": MAX_LEN,
        },
        "scopes": scopes,
        "needles": needles,
        "inv_scope": inv_scope,
        "inv_needle": inv_needle,
        "answers": answers,
        "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
        "stall_classes": _STALL_CLASSES,
    }
    torch.save(payload, NEURAL_PT)
    metrics = evaluate(model, held_ex, torch, device, scopes, needles)
    n01_acc = metrics.get("n01_acc")
    kit_acc = metrics.get("n01_kit_acc")
    know_acc = metrics.get("knowledge_acc") or 0.0
    n01_held_n = int(metrics.get("n01_n") or 0)
    niche_ok = all(
        (metrics.get(k) or 0.0) >= PASS_BAR
        for k in ("n01_acc", "n03_acc", "n08_acc")
        if metrics.get(k) is not None
    )
    if n01_held_n >= 3:
        passed = bool(n01_acc is not None and n01_acc >= PASS_BAR and know_acc >= 0.7 and niche_ok)
    else:
        passed = bool(kit_acc is not None and kit_acc >= PASS_BAR and know_acc >= 0.7)

    ckpt = {
        "needle": NEEDLE,
        "kind": "neural",
        "niche_id": "N01_plus_sidequest",
        "weights": str(NEURAL_PT.relative_to(ROOT)),
        "param_count": n_params,
        "heldout": metrics,
        "heldout_accuracy": n01_acc,
        "pass_bar": PASS_BAR,
        "passed": passed,
        "epochs": epochs,
        "last_loss": last_loss,
        "local_only": True,
        "not_stock_ollama": True,
        "knowledge_corpus": str(KNOWLEDGE_JSON.relative_to(ROOT)),
        "n_knowledge_answers": len(answers),
        "serve": "python3 scripts/niche_n01_neural_train.py --serve '<line>'",
        "ask": "python3 scripts/niche_n01_neural_train.py --ask '<question>'",
    }
    CKPT_JSON.write_text(json.dumps(ckpt, indent=2) + "\n", encoding="utf-8")
    write_status(
        {
            "needle": NEEDLE,
            "status": "completed",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "param_count": n_params,
            "device": str(device),
            "epoch": epochs,
            "step": step,
            "loss": last_loss,
            "heldout": metrics,
            "passed": passed,
            "checkpoint": str(CKPT_JSON.relative_to(ROOT)),
            "weights": str(NEURAL_PT.relative_to(ROOT)),
        }
    )
    return ckpt


def evaluate(model, held_ex, torch, device, scopes, needles) -> dict[str, float | int | None]:
    torch_mod, _nn, _F = _require_torch()
    model.eval()
    n01_ok = n01_n = kit_ok = 0
    know_ok = know_n = 0
    n03_ok = n03_n = 0
    n08_ok = n08_n = 0
    with torch_mod.no_grad():
        for chunk, x, pad_mask in batchify(held_ex, torch_mod, device, batch_size=16):
            out = model(x, pad_mask)
            for j, ex in enumerate(chunk):
                if ex["task"] == "n01":
                    n01_n += 1
                    pred_kit = int(out["kit"][j].argmax().item())
                    gold_kit = kit_label(ex["kit"])
                    if pred_kit == gold_kit:
                        kit_ok += 1
                    pred_s = int(out["scope"][j].argmax().item())
                    gold_s = scopes.get(ex.get("scope") or "<none>", 0)
                    pred_n = int(out["needle"][j].argmax().item())
                    gold_n = needles.get(str(ex["needle"]) if ex.get("needle") else "<none>", 0)
                    if pred_kit == gold_kit and pred_s == gold_s and pred_n == gold_n:
                        n01_ok += 1
                elif ex["task"] == "n03":
                    n03_n += 1
                    pred_n = int(out["needle"][j].argmax().item())
                    gold_n = needles.get(str(ex["needle"]) if ex.get("needle") else "<none>", 0)
                    if pred_n == gold_n:
                        n03_ok += 1
                elif ex["task"] == "n08":
                    n08_n += 1
                    pred = int(out["stall"][j].argmax().item())
                    gold = _STALL_CLASSES.index(ex["stall"] if ex["stall"] in _STALL_CLASSES else "unknown")
                    if pred == gold:
                        n08_ok += 1
                elif ex["task"] == "knowledge":
                    know_n += 1
                    aid = int(ex.get("answer_id", -1))
                    pred = int(out["knowledge"][j].argmax().item())
                    if aid >= 0 and pred == aid:
                        know_ok += 1
    return {
        "n01_acc": (n01_ok / n01_n) if n01_n else None,
        "n01_kit_acc": (kit_ok / n01_n) if n01_n else None,
        "n01_n": n01_n,
        "n03_acc": (n03_ok / n03_n) if n03_n else None,
        "n08_acc": (n08_ok / n08_n) if n08_n else None,
        "knowledge_acc": (know_ok / know_n) if know_n else None,
        "knowledge_n": know_n,
    }


def resolve_device(device_name: str):
    """Map cuda|mps|cpu|auto → torch.device; prefer factory_dynamics when present."""
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


def load_model(device_name: str = "cpu"):
    torch, nn, _F = _require_torch()
    device = resolve_device(device_name)
    if not NEURAL_PT.is_file():
        raise SystemExit(f"missing weights: {NEURAL_PT} — train first")
    # Always unpickle on CPU first, then move — avoids CUDA OOM during deserialize.
    blob = torch.load(NEURAL_PT, map_location="cpu", weights_only=False)
    scopes = blob.get("scopes") or {"<none>": 0}
    needles = blob.get("needles") or {"<none>": 0}
    answers = blob.get("answers") or []
    model = build_model(torch, nn, len(scopes), len(needles), len(answers))
    model.load_state_dict(blob["state_dict"])
    try:
        model = model.to(device)
    except Exception:  # noqa: BLE001
        device = torch.device("cpu")
        model = model.to(device)
    model.eval()
    return torch, model, device, blob


def predict_serve(line: str, device_name: str | None = None) -> dict[str, Any]:
    pick = (device_name or "").strip().lower() or None
    reason = "caller"
    if pick is None or pick in ("auto", "balance"):
        try:
            import factory_dynamics as fd

            pick, reason = fd.pick_device(pick)
        except Exception:  # noqa: BLE001
            pick, reason = "cpu", "cpu_default"
    else:
        reason = f"forced_{pick}"
    torch, model, device, blob = load_model(pick or "cpu")
    scopes = blob.get("scopes") or {}
    needles = blob.get("needles") or {}
    inv_s = blob.get("inv_scope") or {v: k for k, v in scopes.items()}
    inv_n = blob.get("inv_needle") or {v: k for k, v in needles.items()}
    inv_s = {int(k): v for k, v in inv_s.items()}
    inv_n = {int(k): v for k, v in inv_n.items()}
    ids = pad_ids(tokenize(line))
    x = torch.tensor([ids], dtype=torch.long, device=device)
    pad_mask = x.eq(0)
    with torch.no_grad():
        out = model(x, pad_mask)
    kit_i = int(out["kit"][0].argmax().item())
    kit = {0: None, 1: False, 2: True}[kit_i]
    scope = inv_s.get(int(out["scope"][0].argmax().item()), None)
    needle = inv_n.get(int(out["needle"][0].argmax().item()), None)
    if scope == "<none>":
        scope = None
    if needle == "<none>":
        needle = None
    dev_str = str(device.type) if hasattr(device, "type") else str(device).split(":")[0]
    return {
        "kit": kit,
        "scope": scope,
        "needle": needle,
        "kit_confidence": float(torch.softmax(out["kit"][0], dim=-1).max().item()),
        "kind": "neural",
        "param_count": blob.get("param_count"),
        "local_only": True,
        "not_stock_ollama": True,
        "device": dev_str,
        "device_name": pick or dev_str,
        "device_pick_reason": reason,
        "ok": True,
    }


def ask(question: str, device_name: str | None = None) -> dict[str, Any]:
    pick = (device_name or "").strip().lower() or None
    reason = "caller"
    if pick is None or pick in ("auto", "balance"):
        try:
            import factory_dynamics as fd

            pick, reason = fd.pick_device(pick)
        except Exception:  # noqa: BLE001
            pick, reason = "cpu", "cpu_default"
    else:
        reason = f"forced_{pick}"
    torch, model, device, blob = load_model(pick or "cpu")
    answers = blob.get("answers") or []
    ids = pad_ids(tokenize(question))
    x = torch.tensor([ids], dtype=torch.long, device=device)
    pad_mask = x.eq(0)
    with torch.no_grad():
        out = model(x, pad_mask)
        aid = int(out["knowledge"][0].argmax().item())
        conf = float(torch.softmax(out["knowledge"][0], dim=-1).max().item())
    best = answers[aid] if 0 <= aid < len(answers) else ""
    dev_str = str(device.type) if hasattr(device, "type") else str(device).split(":")[0]
    return {
        "question": question,
        "answer": best,
        "score": conf,
        "answer_id": aid,
        "param_count": blob.get("param_count"),
        "kind": "neural_knowledge",
        "local_only": True,
        "not_stock_ollama": True,
        "device": dev_str,
        "device_name": pick or dev_str,
        "device_pick_reason": reason,
        "ok": True,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--epochs", type=int, default=24)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--serve", metavar="LINE")
    ap.add_argument("--ask", metavar="QUESTION")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.serve is not None:
        print(json.dumps(predict_serve(args.serve, device_name=args.device), indent=2))
        return 0
    if args.ask is not None:
        print(json.dumps(ask(args.ask, device_name=args.device), indent=2))
        return 0
    if args.eval_only:
        torch, model, device, blob = load_model(args.device)
        _train, held, _answers = build_examples()
        scopes = blob.get("scopes") or {"<none>": 0}
        needles = blob.get("needles") or {"<none>": 0}
        metrics = evaluate(model, held, torch, device, scopes, needles)
        payload = {"needle": NEEDLE, "param_count": blob.get("param_count"), "heldout": metrics}
        print(json.dumps(payload, indent=2))
        return 0
    if args.train:
        ckpt = train_loop(epochs=args.epochs, lr=args.lr, device_name=args.device)
        print(json.dumps(ckpt, indent=2))
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
