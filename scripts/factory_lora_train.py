#!/usr/bin/env python3
"""Factory LoRA LLM scaffold — train *our* small instruct adapter (local).

Needle: OVERSEER_FACTORY_LORA_LLM_2026_09_07

Builds a tiny causal LM + LoRA-style low-rank adapters on sidequest/kit text.
This is the path to a *trained* chat-ish model (not stock Ollama).
Default: min-RAM CPU/CUDA dry train that writes checkpoint + loss log.

Usage::
    python3 scripts/factory_lora_train.py --train --steps 200
    python3 scripts/factory_lora_train.py --ask "What is NVFP4?"
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "notes" / "factory_llm"
WEIGHTS = OUT_DIR / "factory_lora_student.pt"
CKPT = OUT_DIR / "factory_lora_checkpoint.json"
LOG = OUT_DIR / "factory_lora_train_log.jsonl"
NEEDLE = "OVERSEER_FACTORY_LORA_LLM_2026_09_07"

VOCAB = 2048
D = 128
N_LAYERS = 2
SEQ = 64


def _require_torch():
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("torch required") from exc
    return torch, nn, F


def hash_tok(t: str) -> int:
    h = 2166136261
    for c in t.encode("utf-8", errors="ignore"):
        h ^= c
        h = (h * 16777619) & 0xFFFFFFFF
    return (h % (VOCAB - 1)) + 1


def tokenize(text: str) -> list[int]:
    parts = re.findall(r"[a-z0-9_./`-]+", (text or "").lower())
    ids = [hash_tok(p) for p in parts[: SEQ - 1]] or [1]
    return ids


def corpus() -> list[str]:
    paths = [
        ROOT / "notes" / "niche_distill" / "sidequest_knowledge.json",
        ROOT / "notes" / "DGX_NVFP4_SIDE_QUEST_OPS.md",
        ROOT / "notes" / "COMPRESSION_NORTH_STAR.md",
        ROOT / "notes" / "BITNET_NICHE_BANK.md",
    ]
    lines: list[str] = []
    for p in paths:
        if not p.is_file():
            continue
        if p.suffix == ".json":
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                for row in data:
                    q = row.get("input")
                    a = (row.get("output") or {}).get("answer")
                    if q and a:
                        lines.append(f"Q: {q}\nA: {a}")
            except (OSError, json.JSONDecodeError, TypeError, AttributeError):
                pass
        else:
            for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if len(ln.strip()) > 40:
                    lines.append(ln.strip()[:400])
    return lines or ["Q: What is hot dtype?\nA: NVFP4"]


def build_model(torch, nn):
    class LoRALinear(nn.Module):
        def __init__(self, inn: int, out: int, r: int = 4):
            super().__init__()
            self.weight = nn.Parameter(torch.randn(out, inn) * 0.02)
            self.A = nn.Parameter(torch.randn(r, inn) * 0.02)
            self.B = nn.Parameter(torch.zeros(out, r))

        def forward(self, x):
            base = x @ self.weight.T
            return base + (x @ self.A.T) @ self.B.T

    class TinyLM(nn.Module):
        def __init__(self):
            super().__init__()
            self.embed = nn.Embedding(VOCAB, D)
            self.blocks = nn.ModuleList([LoRALinear(D, D) for _ in range(N_LAYERS)])
            self.norm = nn.LayerNorm(D)
            self.head = LoRALinear(D, VOCAB)

        def forward(self, x):
            h = self.embed(x)
            for blk in self.blocks:
                h = h + torch.tanh(blk(h))
            h = self.norm(h)
            return self.head(h)

    return TinyLM()


def train_loop(*, steps: int = 200, lr: float = 3e-3, device_name: str = "cpu") -> dict[str, Any]:
    torch, nn, F = _require_torch()
    device = torch.device(device_name if device_name != "cuda" or torch.cuda.is_available() else "cpu")
    model = build_model(torch, nn).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    data = corpus()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG.write_text("", encoding="utf-8")
    n_params = sum(p.numel() for p in model.parameters())
    last_loss = None
    for step in range(1, steps + 1):
        text = random.choice(data)
        ids = tokenize(text)
        if len(ids) < 2:
            ids = ids + [1]
        x = torch.tensor([ids[:-1]], dtype=torch.long, device=device)
        y = torch.tensor([ids[1:]], dtype=torch.long, device=device)
        # pad
        if x.size(1) < SEQ - 1:
            pad = SEQ - 1 - x.size(1)
            x = F.pad(x, (0, pad))
            y = F.pad(y, (0, pad), value=0)
        logits = model(x)
        loss = F.cross_entropy(logits.reshape(-1, VOCAB), y.reshape(-1), ignore_index=0)
        opt.zero_grad()
        loss.backward()
        opt.step()
        last_loss = float(loss.item())
        if step == 1 or step % 20 == 0 or step == steps:
            row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "step": step, "loss": last_loss, "param_count": n_params}
            with LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
    torch.save({"state_dict": model.state_dict(), "param_count": n_params, "needle": NEEDLE}, WEIGHTS)
    ckpt = {
        "needle": NEEDLE,
        "kind": "factory_lora_lm",
        "status": "TRAINED",
        "param_count": n_params,
        "steps": steps,
        "last_loss": last_loss,
        "weights": str(WEIGHTS.relative_to(ROOT)),
        "local_only": True,
        "not_stock_ollama": True,
        "note": "Tiny LoRA-LM on kit/sidequest text — our trained chat-ish student (not Ollama).",
    }
    CKPT.write_text(json.dumps(ckpt, indent=2) + "\n", encoding="utf-8")
    return ckpt


def ask(question: str, device_name: str = "cpu") -> dict[str, Any]:
    torch, nn, F = _require_torch()
    if not WEIGHTS.is_file():
        raise SystemExit("missing weights — run --train first")
    blob = torch.load(WEIGHTS, map_location="cpu", weights_only=False)
    device = torch.device("cpu")
    model = build_model(torch, nn)
    model.load_state_dict(blob["state_dict"])
    model.eval()
    ids = tokenize("Q: " + question + "\nA:")
    x = torch.tensor([ids], dtype=torch.long)
    with torch.no_grad():
        for _ in range(24):
            logits = model(x)[0, -1]
            nxt = int(torch.argmax(logits).item())
            if nxt <= 0:
                break
            x = torch.cat([x, torch.tensor([[nxt]])], dim=1)
            if x.size(1) >= SEQ:
                break
    # Detokenize poorly — return id trail + note; prefer knowledge fallback via N01 ask
    return {
        "question": question,
        "token_ids": x[0].tolist(),
        "param_count": blob.get("param_count"),
        "kind": "factory_lora_lm",
        "note": "Toy detok — for factual locks prefer niche_n01_neural_train --ask",
        "local_only": True,
        "not_stock_ollama": True,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--steps", type=int, default=200)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--ask", metavar="Q")
    args = ap.parse_args(argv)
    if args.ask or args.train:
        try:
            import torch  # noqa: F401
        except ImportError:
            payload = {
                "needle": NEEDLE,
                "skipped": True,
                "reason": "torch_missing",
                "local_only": True,
                "not_stock_ollama": True,
                "note": (
                    "Tiny LoRA-LM scaffold needs torch. Fail-soft here — "
                    "not a production LLM even when trained."
                ),
            }
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            CKPT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(payload, indent=2))
            return 0
    if args.ask:
        print(json.dumps(ask(args.ask, args.device), indent=2))
        return 0
    if args.train:
        print(json.dumps(train_loop(steps=args.steps, device_name=args.device), indent=2))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
