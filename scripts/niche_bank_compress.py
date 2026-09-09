#!/usr/bin/env python3
"""Compress niche-bank weights to NVFP4-ish packed sidecars (unique-param lane).

Needle: OVERSEER_NICHE_BANK_COMPRESS_2026_09_07

Packs float32 state_dicts to nibble-packed int storage (~U/2 bytes) for cold
disk residency. Hot path still dequants to float for CPU serve today.
Parallel pack across experts. Local only. No data prune.
"""

from __future__ import annotations

import argparse
import json
import struct
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DISTILL = ROOT / "notes" / "niche_distill"
NEEDLE = "OVERSEER_NICHE_BANK_COMPRESS_2026_09_07"
STATUS = DISTILL / "bank_compress_status.json"


def _pack_tensor(arr_bytes: bytes) -> bytes:
    """Pack float32 → fake NVFP4: scale + signed nibble per value (demo pack)."""
    import array

    floats = array.array("f")
    floats.frombytes(arr_bytes)
    if not floats:
        return b""
    mx = max(abs(x) for x in floats) or 1.0
    scale = mx / 7.0
    out = bytearray()
    out += struct.pack("<f", scale)
    nibble_buf = 0
    have = False
    for x in floats:
        q = int(max(-7, min(7, round(x / scale))))
        n = q & 0xF
        if not have:
            nibble_buf = n
            have = True
        else:
            out.append((nibble_buf << 4) | n)
            have = False
    if have:
        out.append(nibble_buf << 4)
    return bytes(out)


def compress_one(pt_path: Path) -> dict[str, Any]:
    import torch

    blob = torch.load(pt_path, map_location="cpu", weights_only=False)
    sd = blob.get("state_dict") or {}
    packed: dict[str, bytes] = {}
    raw = 0
    packed_n = 0
    for k, t in sd.items():
        if not hasattr(t, "detach"):
            continue
        b = t.detach().cpu().float().contiguous().numpy().tobytes()
        raw += len(b)
        pb = _pack_tensor(b)
        packed[k] = pb
        packed_n += len(pb)
    out_path = pt_path.with_suffix(".nvfp4.pt")
    meta = {
        "needle": NEEDLE,
        "source": str(pt_path.relative_to(ROOT)),
        "raw_bytes": raw,
        "packed_bytes": packed_n,
        "S_approx": (raw / packed_n) if packed_n else None,
        "hot_dtype": "NVFP4_pack_demo",
        "note": "Cold pack for residency; serve still uses float .pt until TE path",
    }
    torch.save({"meta": meta, "packed": packed, "labels": blob.get("labels"), "name": blob.get("name")}, out_path)
    return {**meta, "out": str(out_path.relative_to(ROOT))}


def compress_bank(*, workers: int = 4, limit: int | None = None) -> dict[str, Any]:
    try:
        import torch  # noqa: F401
    except ImportError:
        payload = {
            "needle": NEEDLE,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "n_total": 0,
            "n_ok": 0,
            "skipped": True,
            "reason": "torch_missing",
            "note": (
                "Cold NVFP4-ish nibble pack needs torch. Fail-soft on this host; "
                "run on CLEAN/brain when torch is available. Pack = residency demo, not TE."
            ),
            "local_only": True,
        }
        DISTILL.mkdir(parents=True, exist_ok=True)
        STATUS.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload
    pts = sorted(DISTILL.glob("practice_n*/weights/*_neural.pt"))
    if limit:
        pts = pts[:limit]
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futs = {pool.submit(compress_one, p): p for p in pts}
        for fut in as_completed(futs):
            try:
                rows.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                rows.append({"source": str(futs[fut]), "error": str(exc)})
    ok = [r for r in rows if "error" not in r]
    payload = {
        "needle": NEEDLE,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_total": len(pts),
        "n_ok": len(ok),
        "raw_bytes": sum(int(r.get("raw_bytes") or 0) for r in ok),
        "packed_bytes": sum(int(r.get("packed_bytes") or 0) for r in ok),
        "rows": rows,
        "local_only": True,
        "note": "Cold pack for residency; serve still uses float .pt until TE path",
    }
    if payload["packed_bytes"]:
        payload["S_bank"] = payload["raw_bytes"] / payload["packed_bytes"]
    STATUS.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    args = ap.parse_args(argv)
    out = compress_bank(workers=args.workers, limit=args.limit or None)
    print(json.dumps({k: out[k] for k in out if k != "rows"}, indent=2))
    if out.get("skipped"):
        print(f"skipped={out.get('reason')}")
        return 0
    print(f"rows_ok={out['n_ok']}/{out['n_total']}")
    return 0 if out["n_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
