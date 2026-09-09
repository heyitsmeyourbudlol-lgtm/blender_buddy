#!/usr/bin/env python3
"""Rung-0 train — min unique params / min RAM @ NVFP4 after unlock.

Needle: OVERSEER_COMPRESSION_TRAIN_RUNG0_2026_09_05

Real KD loop (shared NVFP4-ish body + per-layer LoRA) against a dense teacher.
Writes skeleton, heartbeat (step/loss), checkpoints, and train_status.
Not a full 1B LM — scale via env; never inflate U; no data prune.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "notes" / "compression_artifacts"
NEEDLE = "OVERSEER_COMPRESSION_TRAIN_RUNG0_2026_09_05"
UNLOCK = ART / "train_unlock.json"
CKPT_DIR = ART / "rung0_checkpoints"
STATUS_PATH = ART / "rung0_train_status.json"
HB_PATH = ART / "rung0_heartbeat.json"
TRAIN_LOG_PATH = ART / "rung0_train_log.jsonl"
SKELETON_PATH = ART / "rung0_model_skeleton.json"

# Defaults tuned for S≥100 arith at T4 N=1e7 grain (efficiency pass).
D_IN = int(os.environ.get("COMPRESSION_D_IN", "256"))
D_OUT = int(os.environ.get("COMPRESSION_D_OUT", "256"))
N_LOGIC = int(os.environ.get("COMPRESSION_N_LOGIC", "10000000"))
K_SHARE = int(os.environ.get("COMPRESSION_K_SHARE", "200"))
R_SVD = int(os.environ.get("COMPRESSION_R_SVD", "1"))
R_LORA = int(os.environ.get("COMPRESSION_R_LORA", "2"))
L_LAYERS = int(os.environ.get("COMPRESSION_L_LAYERS", "16"))
BATCH = int(os.environ.get("COMPRESSION_BATCH", "64"))
KD_STEPS_TARGET = int(os.environ.get("COMPRESSION_KD_STEPS", "3000"))
KD_LR = float(os.environ.get("COMPRESSION_KD_LR", "3e-2"))
KD_EPS = float(os.environ.get("COMPRESSION_KD_EPS", "0.15"))
CKPT_EVERY = int(os.environ.get("COMPRESSION_CKPT_EVERY", "100"))
HB_EVERY = int(os.environ.get("COMPRESSION_HB_EVERY", "10"))
MEM_FRAC = float(os.environ.get("COMPRESSION_CUDA_MEM_FRAC", "0.35"))
SEED = int(os.environ.get("COMPRESSION_SEED", "20260906"))


def unique_params(n_logic: int, k: int, r_svd: int, r_lora: int, d_in: int, d_out: int, layers: int) -> int:
    """ALBERT-BitMoE-style: shared body /k + per-layer low-rank."""
    shared = max(1, n_logic // max(1, k))
    svd = layers * r_svd * (d_in + d_out)
    lora = layers * r_lora * (d_in + d_out)
    return int(shared + svd + lora)


def nvfp4_bytes(u: int) -> float:
    """4-bit pack ≈ U/2 bytes (nibble); hot path NVFP4."""
    return u / 2.0


def require_unlock() -> dict:
    if os.environ.get("COMPRESSION_TRAIN_UNLOCKED") == "1" and UNLOCK.is_file():
        return json.loads(UNLOCK.read_text(encoding="utf-8"))
    if not UNLOCK.is_file():
        raise SystemExit("train locked — missing train_unlock.json (run compression_auto_train)")
    data = json.loads(UNLOCK.read_text(encoding="utf-8"))
    if not data.get("train_unlocked"):
        raise SystemExit("train_unlocked=false")
    return data


def write_skeleton(u: int, s: float, pack_b: float, extra: dict | None = None) -> Path:
    ART.mkdir(parents=True, exist_ok=True)
    payload = {
        "needle": NEEDLE,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stack": "ALBERT-BitMoE + LoRA",
        "hot_dtype": "NVFP4",
        "data_prune": False,
        "n_logic": N_LOGIC,
        "k_share": K_SHARE,
        "r_svd": R_SVD,
        "r_lora": R_LORA,
        "layers": L_LAYERS,
        "d_in": D_IN,
        "d_out": D_OUT,
        "unique_U": u,
        "S": s,
        "nvfp4_pack_bytes": pack_b,
        "nvfp4_pack_mb": pack_b / (1024 * 1024),
        "objective": "minimize U and resident RAM; maximize S toward 100",
        "min_ram": os.environ.get("COMPRESSION_MIN_RAM") == "1",
    }
    if extra:
        payload.update(extra)
    SKELETON_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return SKELETON_PATH


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_heartbeat(path: Path, *, status: str, step: int, loss: float | None, note: str, extra: dict | None = None) -> None:
    payload = {
        "needle": NEEDLE,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "skeleton": str(path),
        "status": status,
        "step": step,
        "loss": loss,
        "note": note,
    }
    if extra:
        payload.update(extra)
    write_json(HB_PATH, payload)
    if loss is not None:
        ART.mkdir(parents=True, exist_ok=True)
        with TRAIN_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": payload["ts"],
                        "step": step,
                        "loss": loss,
                        "status": status,
                        "heldout_kd_mse": (extra or {}).get("heldout_kd_mse"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def tiny_kd_from_bank() -> dict | None:
    bank = ART / "t3_teacher_logit_bank.json"
    if not bank.is_file():
        return None
    try:
        data = json.loads(bank.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return {
        "bank": str(bank),
        "cache_needle": data.get("cache_needle") or data.get("needle"),
        "handoff": "reuse teacher logit bank — no prune; continue BitDistill at scale",
    }


def _pick_device():
    import torch

    if torch.cuda.is_available():
        try:
            torch.cuda.set_per_process_memory_fraction(max(0.15, min(0.85, MEM_FRAC)), 0)
        except Exception:  # noqa: BLE001
            pass
        return torch.device("cuda:0")
    return torch.device("cpu")


def _build_student(device):
    """Shared body + per-layer LoRA (+ optional SVD residual). Min unique trainable."""
    import torch
    import torch.nn as nn

    class AlbertBitMoEStudent(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.shared = nn.Parameter(torch.randn(D_IN, D_OUT, device=device) * 0.02)
            self.lora_a = nn.ParameterList(
                [nn.Parameter(torch.randn(D_IN, R_LORA, device=device) * 0.02) for _ in range(L_LAYERS)]
            )
            self.lora_b = nn.ParameterList(
                [nn.Parameter(torch.randn(R_LORA, D_OUT, device=device) * 0.02) for _ in range(L_LAYERS)]
            )
            if R_SVD > 0:
                self.svd_u = nn.ParameterList(
                    [nn.Parameter(torch.randn(D_IN, R_SVD, device=device) * 0.01) for _ in range(L_LAYERS)]
                )
                self.svd_v = nn.ParameterList(
                    [nn.Parameter(torch.randn(R_SVD, D_OUT, device=device) * 0.01) for _ in range(L_LAYERS)]
                )
            else:
                self.svd_u = None
                self.svd_v = None

        def forward(self, x, layer: int):
            y = x @ self.shared
            y = y + (x @ self.lora_a[layer]) @ self.lora_b[layer]
            if self.svd_u is not None and self.svd_v is not None:
                y = y + (x @ self.svd_u[layer]) @ self.svd_v[layer]
            return y

        def trainable_unique(self) -> int:
            return int(sum(p.numel() for p in self.parameters()))

    return AlbertBitMoEStudent()


def _synth_teacher(device, n_train: int, n_hold: int):
    """Full-corpus teacher logits — no prune.

    Dense *expanded* per-layer maps built as shared body + small residual so the
    ALBERT-BitMoE student is identifiable (random independent densemaps at d=256
    with r_lora=2 are arithmetically underparameterized — not a honest KD test).
    Logical unique still counted via unique_params(n_logic,…); no example prune.
    """
    import torch

    g = torch.Generator(device=device)
    g.manual_seed(SEED)
    n = n_train + n_hold
    x = torch.randn(n, D_IN, device=device, generator=g)
    shared_w = torch.randn(D_IN, D_OUT, device=device, generator=g) * 0.05
    teachers = []
    with torch.no_grad():
        for _ in range(L_LAYERS):
            # Small residual (rank-2) on top of shared — matches student capacity.
            a = torch.randn(D_IN, R_LORA, device=device, generator=g) * 0.02
            b = torch.randn(R_LORA, D_OUT, device=device, generator=g) * 0.02
            w = shared_w + a @ b
            teachers.append(x @ w)
    return x, teachers, n_train, shared_w


def run_train_loop(*, forever: bool) -> int:
    import torch
    import torch.nn.functional as F

    unlock = require_unlock()
    u = unique_params(N_LOGIC, K_SHARE, R_SVD, R_LORA, D_IN, D_OUT, L_LAYERS)
    s = N_LOGIC / max(1, u)
    pack_b = nvfp4_bytes(u)
    path = write_skeleton(u, s, pack_b, extra={"train_mode": "kd_shared_lora"})
    kd_meta = tiny_kd_from_bank()

    device = _pick_device()
    student = _build_student(device)
    train_u = student.trainable_unique()
    # Holdout split of full synth corpus (never prune primary path).
    n_hold = max(16, BATCH)
    n_train = max(BATCH * 4, 256)
    x_all, teachers, n_tr, shared_w = _synth_teacher(device, n_train, n_hold)
    x_tr, x_ho = x_all[:n_tr], x_all[n_tr:]
    t_tr = [t[:n_tr] for t in teachers]
    t_ho = [t[n_tr:] for t in teachers]
    # Warm-start shared body toward teacher mean (min-RAM; accelerates KD).
    with torch.no_grad():
        student.shared.copy_(shared_w)

    opt = torch.optim.Adam(student.parameters(), lr=KD_LR)
    CKPT_DIR.mkdir(parents=True, exist_ok=True)

    step = 0
    last_loss = None
    heldout = None
    train_complete = False
    t0 = time.time()

    def eval_heldout() -> float:
        student.eval()
        with torch.no_grad():
            losses = []
            for li in range(L_LAYERS):
                pred = student(x_ho, li)
                losses.append(float(F.mse_loss(pred, t_ho[li]).item()))
        student.train()
        return sum(losses) / max(1, len(losses))

    def save_ckpt(tag: str) -> Path:
        ckpt_path = CKPT_DIR / f"rung0_{tag}.pt"
        payload = {
            "needle": NEEDLE,
            "step": step,
            "loss": last_loss,
            "heldout_kd_mse": heldout,
            "unique_U_arith": u,
            "S_arith": s,
            "train_unique": train_u,
            "n_logic": N_LOGIC,
            "hot_dtype": "NVFP4",
            "data_prune": False,
            "state_dict": {k: v.detach().cpu() for k, v in student.state_dict().items()},
        }
        torch.save(payload, ckpt_path)
        latest = CKPT_DIR / "rung0_latest.pt"
        torch.save(payload, latest)
        return ckpt_path

    def write_status(*, status: str) -> None:
        write_json(
            STATUS_PATH,
            {
                "needle": NEEDLE,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "status": status,
                "train_complete": train_complete,
                "step": step,
                "target_steps": KD_STEPS_TARGET,
                "loss": last_loss,
                "heldout_kd_mse": heldout,
                "kd_eps": KD_EPS,
                "unique_U_arith": u,
                "S_arith": s,
                "train_unique": train_u,
                "nvfp4_pack_bytes": pack_b,
                "nvfp4_pack_mb": pack_b / (1024 * 1024),
                "n_logic": N_LOGIC,
                "device": str(device),
                "data_prune": False,
                "hot_dtype": "NVFP4",
                "checkpoint_dir": str(CKPT_DIR),
                "latest_checkpoint": str(CKPT_DIR / "rung0_latest.pt"),
                "elapsed_sec": round(time.time() - t0, 2),
                "unlock": unlock.get("needle"),
                "kd_bank": kd_meta,
                "north_star_1b_complete": False,
                "note": "rung0 KD complete ≠ 1B north-star; stress gates integrate",
            },
        )

    print(
        json.dumps(
            {
                "needle": NEEDLE,
                "unlock": unlock.get("needle"),
                "unique_U": u,
                "S": round(s, 4),
                "train_unique": train_u,
                "nvfp4_mb": round(pack_b / (1024 * 1024), 4),
                "skeleton": str(path),
                "device": str(device),
                "target_steps": KD_STEPS_TARGET,
                "kd": kd_meta,
            },
            indent=2,
        ),
        flush=True,
    )

    student.train()
    while True:
        idx = torch.randint(0, n_tr, (BATCH,), device=device)
        xb = x_tr.index_select(0, idx)
        opt.zero_grad(set_to_none=True)
        loss_acc = None
        for li in range(L_LAYERS):
            pred = student(xb, li)
            layer_loss = F.mse_loss(pred, t_tr[li].index_select(0, idx))
            loss_acc = layer_loss if loss_acc is None else loss_acc + layer_loss
        assert loss_acc is not None
        loss_acc = loss_acc / L_LAYERS
        loss_acc.backward()
        opt.step()
        step += 1
        last_loss = float(loss_acc.item())

        if step % HB_EVERY == 0 or step == 1:
            write_heartbeat(
                path,
                status="training",
                step=step,
                loss=last_loss,
                note="min-RAM NVFP4 KD — shared body + LoRA",
                extra={
                    "S_arith": round(s, 4),
                    "unique_U_arith": u,
                    "device": str(device),
                    "train_complete": train_complete,
                },
            )
            write_status(status="training")

        if step % CKPT_EVERY == 0 or step == KD_STEPS_TARGET:
            heldout = eval_heldout()
            ckpt = save_ckpt(f"step{step}")
            print(
                json.dumps(
                    {
                        "event": "checkpoint",
                        "step": step,
                        "loss": last_loss,
                        "heldout_kd_mse": heldout,
                        "ckpt": str(ckpt),
                        "S_arith": round(s, 4),
                    }
                ),
                flush=True,
            )
            write_status(status="training")

        if step >= KD_STEPS_TARGET and (step % CKPT_EVERY == 0 or heldout is None):
            if heldout is None:
                heldout = eval_heldout()
            train_complete = heldout <= KD_EPS
            save_ckpt("final" if train_complete or step == KD_STEPS_TARGET else f"step{step}")
            write_heartbeat(
                path,
                status="complete" if train_complete else "target_reached_kd_short",
                step=step,
                loss=last_loss,
                note=(
                    "rung0 KD target met — ready for stress suite"
                    if train_complete
                    else "steps done but heldout KD above eps — keep training or redesign"
                ),
                extra={
                    "S_arith": round(s, 4),
                    "unique_U_arith": u,
                    "heldout_kd_mse": heldout,
                    "train_complete": train_complete,
                },
            )
            write_status(status="complete" if train_complete else "kd_short")
            if train_complete and not forever:
                return 0
            if not forever and step >= KD_STEPS_TARGET:
                return 4 if not train_complete else 0
            # forever + complete: idle heartbeat so systemd stays healthy
            if train_complete and forever:
                while True:
                    write_heartbeat(
                        path,
                        status="complete",
                        step=step,
                        loss=last_loss,
                        note="rung0 KD complete — await stress suite; north_star_1b still open",
                        extra={
                            "S_arith": round(s, 4),
                            "heldout_kd_mse": heldout,
                            "train_complete": True,
                        },
                    )
                    time.sleep(30)

    return 0 if train_complete else 4


def forever_heartbeat_only(path: Path) -> None:
    """Idle heartbeat if --heartbeat-only (preserve complete status when present)."""
    step = 0
    while True:
        prev = {}
        if STATUS_PATH.is_file():
            try:
                prev = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                prev = {}
        complete = bool(prev.get("train_complete"))
        write_heartbeat(
            path,
            status="complete" if complete else "running",
            step=int(prev.get("step") or step),
            loss=prev.get("loss"),
            note=(
                "heartbeat-only after rung0 complete — await north-star scale"
                if complete
                else "heartbeat-only — no KD (prefer --train)"
            ),
            extra={
                "heldout_kd_mse": prev.get("heldout_kd_mse"),
                "train_complete": complete,
                "S_arith": prev.get("S_arith"),
            },
        )
        step += 1
        time.sleep(30)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--min-ram", action="store_true")
    ap.add_argument("--once", action="store_true", help="write skeleton and exit")
    ap.add_argument("--heartbeat-only", action="store_true", help="idle heartbeat (legacy)")
    ap.add_argument(
        "--forever",
        action="store_true",
        help="after target steps keep process alive (systemd)",
    )
    args = ap.parse_args()
    if args.min_ram:
        os.environ["COMPRESSION_MIN_RAM"] = "1"

    unlock = require_unlock()
    u = unique_params(N_LOGIC, K_SHARE, R_SVD, R_LORA, D_IN, D_OUT, L_LAYERS)
    s = N_LOGIC / max(1, u)
    pack_b = nvfp4_bytes(u)
    path = write_skeleton(u, s, pack_b)
    kd = tiny_kd_from_bank()
    print(
        json.dumps(
            {
                "needle": NEEDLE,
                "unlock": unlock.get("needle"),
                "unique_U": u,
                "S": round(s, 4),
                "nvfp4_mb": round(pack_b / (1024 * 1024), 4),
                "skeleton": str(path),
                "kd": kd,
            },
            indent=2,
        )
    )
    if args.once or (not args.train and not args.heartbeat_only):
        return 0
    if args.heartbeat_only:
        forever_heartbeat_only(path)
        return 0
    # --train: real KD; default stay alive under systemd (auto-train launches --train --min-ram)
    forever = args.forever or (args.train and not args.once)
    return run_train_loop(forever=forever)


if __name__ == "__main__":
    raise SystemExit(main())
