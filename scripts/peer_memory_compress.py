#!/usr/bin/env python3
"""Lossless whole-repo memory compression — ADDITIVE pack only.

Needle: OVERSEER_LOSSLESS_MEMORY_COMPRESS_2026_09_07

Compresses memory-bearing text into a content-addressed, codec-packed
artifact under ``notes/memory_artifacts/``. Never deletes or overwrites
live SoT (notes/, scripts/, peers, dashboard, …).

  --compress   walk repo → pack (dedupe blobs + strong codec)
  --expand     restore pack into a staging dir (never live root)
  --verify     compress→expand round-trip: text bytes equal, blobs sha equal

Large binaries: path + sha256 only (hash-lossless). Secrets skipped.
Hot memory may point at the pack; originals stay on disk.

Usage:
  python3 scripts/peer_memory_compress.py --compress
  python3 scripts/peer_memory_compress.py --verify --pack PATH
  python3 scripts/peer_memory_compress.py --expand --pack PATH --out /tmp/mem-expand
  ./scripts/peer memory-compress
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
import zlib
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

NEEDLE = "OVERSEER_LOSSLESS_MEMORY_COMPRESS_2026_09_07"
ARTIFACT_DIR = ROOT / "notes" / "memory_artifacts"
DEFAULT_PACK_NAME = "repo_memory_pack.json.z"

# Skip walking these directory names entirely.
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".eggs",
        "memory_artifacts",  # do not nest packs inside packs
    }
)

# Never pack secret-bearing paths (basename or suffix match).
SECRET_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        "cursor-agent.env",
        "credentials.json",
        "service-account.json",
        ".netrc",
    }
)
SECRET_SUFFIXES = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".keystore",
)
SECRET_NAME_PARTS = (
    "api_key",
    "apikey",
    "secret_key",
    "private_key",
    "whsec_",
)

# Prefer embedding full body up to this size; larger → hash-ref only.
TEXT_MAX_EMBED_BYTES = 2 * 1024 * 1024  # 2 MiB per file body
BINARY_MAX_EMBED_BYTES = 256 * 1024  # 256 KiB — else hash-ref
DEFAULT_CODEC = "auto"  # zstd > xz > brotli > zlib

TEXT_SUFFIXES = frozenset(
    {
        ".md",
        ".txt",
        ".py",
        ".json",
        ".jsonl",
        ".yml",
        ".yaml",
        ".toml",
        ".ini",
        ".cfg",
        ".sh",
        ".bash",
        ".zsh",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".css",
        ".html",
        ".htm",
        ".svg",
        ".csv",
        ".tsv",
        ".xml",
        ".rst",
        ".mdc",
        ".mjs",
        ".cjs",
        ".sql",
        ".r",
        ".rb",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".swift",
        ".m",
        ".mm",
        ".h",
        ".c",
        ".cc",
        ".cpp",
        ".hpp",
        ".lua",
        ".pl",
        ".ps1",
        ".bat",
        ".command",
        ".plist",
        ".service",
        ".conf",
        ".env.example",
        ".gitignore",
        ".gitattributes",
        ".editorconfig",
        ".dockerignore",
        ".npmrc",
        ".prettierrc",
        ".eslintrc",
    }
)

BINARY_SUFFIXES = frozenset(
    {
        ".pt",
        ".pth",
        ".bin",
        ".safetensors",
        ".onnx",
        ".gguf",
        ".ggml",
        ".npz",
        ".h5",
        ".pkl",
        ".pickle",
        ".npy",
        ".npz",
        ".parquet",
        ".arrow",
        ".feather",
        ".so",
        ".dylib",
        ".dll",
        ".a",
        ".o",
        ".pyc",
        ".pyo",
        ".wasm",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".mp3",
        ".mp4",
        ".mov",
        ".wav",
        ".flac",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".exe",
        ".dmg",
        ".iso",
    }
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_secret_path(rel: str, name: str) -> bool:
    low = name.lower()
    if name in SECRET_BASENAMES or low in SECRET_BASENAMES:
        return True
    if low.startswith(".env.") and low != ".env.example":
        return True
    if any(low.endswith(s) for s in SECRET_SUFFIXES):
        return True
    blob = f"{rel}/{name}".lower()
    return any(p in blob for p in SECRET_NAME_PARTS)


def _looks_text(path: Path, sample: bytes) -> bool:
    suf = path.suffix.lower()
    if suf in TEXT_SUFFIXES or path.name in (
        "Makefile",
        "Dockerfile",
        "LICENSE",
        "AGENTS.md",
        "README",
        "Procfile",
    ):
        return True
    if suf in BINARY_SUFFIXES:
        return False
    if b"\x00" in sample[:8192]:
        return False
    # UTF-8-ish heuristic
    try:
        sample[:8192].decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _codec_encode(raw: bytes, prefer: str = DEFAULT_CODEC) -> tuple[str, bytes]:
    """Return (codec_name, compressed_bytes). Prefer densest available."""
    candidates: list[tuple[str, Callable[[bytes], bytes]]] = []

    def _try_zstd(b: bytes) -> bytes:
        import zstandard as zstd  # type: ignore

        cctx = zstd.ZstdCompressor(level=19)
        return cctx.compress(b)

    def _try_xz(b: bytes) -> bytes:
        import lzma

        return lzma.compress(b, preset=9 | lzma.PRESET_EXTREME)

    def _try_brotli(b: bytes) -> bytes:
        import brotli  # type: ignore

        return brotli.compress(b, quality=11)

    def _try_zlib(b: bytes) -> bytes:
        return zlib.compress(b, level=9)

    order = ["zstd", "xz", "brotli", "zlib"]
    if prefer in order and prefer != "auto":
        order = [prefer] + [c for c in order if c != prefer]
    elif prefer == "auto":
        pass
    else:
        order = ["zlib"]

    impls = {
        "zstd": _try_zstd,
        "xz": _try_xz,
        "brotli": _try_brotli,
        "zlib": _try_zlib,
    }
    best_name = "zlib"
    best_data = _try_zlib(raw)
    for name in order:
        fn = impls[name]
        try:
            out = fn(raw)
        except Exception:  # noqa: BLE001 — missing codec / fail soft
            continue
        if len(out) < len(best_data):
            best_name, best_data = name, out
        candidates.append((name, fn))  # noqa: F841 — keep for clarity
    return best_name, best_data


def _codec_decode(codec: str, data: bytes) -> bytes:
    if codec == "zlib":
        return zlib.decompress(data)
    if codec == "zstd":
        import zstandard as zstd  # type: ignore

        return zstd.ZstdDecompressor().decompress(data)
    if codec == "xz":
        import lzma

        return lzma.decompress(data)
    if codec == "brotli":
        import brotli  # type: ignore

        return brotli.decompress(data)
    raise ValueError(f"unknown codec: {codec}")


def iter_repo_files(root: Path | None = None) -> list[Path]:
    root = root or ROOT
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_DIR_NAMES and not d.startswith(".git")
        )
        # Keep .cursor/rules but skip other heavy dotdirs except .cursor
        base = Path(dirpath)
        rel_parts = base.relative_to(root).parts if base != root else ()
        if rel_parts and rel_parts[0].startswith(".") and rel_parts[0] not in (
            ".cursor",
            ".github",
        ):
            dirnames[:] = []
            continue
        for name in sorted(filenames):
            path = base / name
            if path.is_symlink():
                continue
            if not path.is_file():
                continue
            rel = str(path.relative_to(root))
            if _is_secret_path(rel, name):
                continue
            out.append(path)
    return out


def build_pack(
    *,
    root: Path | None = None,
    codec_prefer: str = DEFAULT_CODEC,
    text_max: int = TEXT_MAX_EMBED_BYTES,
    binary_max: int = BINARY_MAX_EMBED_BYTES,
) -> dict[str, Any]:
    """Build in-memory pack dict (uncompressed JSON object).

    blobs: sha256 → base64? No — store raw bytes in a separate map then
    serialize as hex for JSON? Better: blobs as sha→bytes, outer layer
    codecs the whole msgpack/json of {manifest, blobs_b64}.

    Structure:
      version, needle, created_ts, root_name
      files: [{path, sha256, size, kind: text|binary|hash_ref|skipped_secret,
               mode, embedded: bool}]
      blobs: {sha256: base64 of raw file bytes}  # only embedded
    """
    import base64

    root = root or ROOT
    files_meta: list[dict[str, Any]] = []
    blobs: dict[str, str] = {}  # sha → b64
    raw_total = 0
    embedded_raw = 0
    hash_ref_n = 0
    text_n = 0
    bin_n = 0
    skipped_secret = 0

    for path in iter_repo_files(root):
        rel = str(path.relative_to(root)).replace("\\", "/")
        try:
            data = path.read_bytes()
        except OSError as exc:
            files_meta.append(
                {
                    "path": rel,
                    "sha256": "",
                    "size": 0,
                    "kind": "unreadable",
                    "error": str(exc)[:120],
                    "embedded": False,
                }
            )
            continue
        digest = _sha256(data)
        size = len(data)
        raw_total += size
        sample = data[:8192]
        is_text = _looks_text(path, sample)
        kind = "text" if is_text else "binary"
        embed_cap = text_max if is_text else binary_max
        embed = size <= embed_cap
        if embed:
            if digest not in blobs:
                blobs[digest] = base64.b64encode(data).decode("ascii")
                embedded_raw += size
            else:
                # dedupe: body already stored — still count as embedded meta
                pass
            if is_text:
                text_n += 1
            else:
                bin_n += 1
        else:
            kind = "hash_ref"
            hash_ref_n += 1
            try:
                mode = oct(path.stat().st_mode & 0o777)
            except OSError:
                mode = ""
            files_meta.append(
                {
                    "path": rel,
                    "sha256": digest,
                    "size": size,
                    "kind": kind,
                    "mode": mode,
                    "embedded": False,
                }
            )
            continue
        try:
            mode = oct(path.stat().st_mode & 0o777)
        except OSError:
            mode = ""
        files_meta.append(
            {
                "path": rel,
                "sha256": digest,
                "size": size,
                "kind": kind,
                "mode": mode,
                "embedded": True,
            }
        )

    payload = {
        "version": 1,
        "needle": NEEDLE,
        "created_ts": time.time(),
        "root_name": root.name,
        "policy": {
            "additive_only": True,
            "never_delete_live_sot": True,
            "secrets_skipped": True,
            "hash_ref_over_bytes": {
                "text": text_max,
                "binary": binary_max,
            },
            "lossless": {
                "text": "byte-identical on expand when embedded",
                "hash_ref": "sha256 identity; body not in pack",
            },
        },
        "stats": {
            "file_count": len(files_meta),
            "blob_count": len(blobs),
            "raw_bytes": raw_total,
            "unique_embedded_raw_bytes": 0,  # filled below
            "text_embedded": text_n,
            "binary_embedded": bin_n,
            "hash_ref": hash_ref_n,
            "skipped_secret_note": skipped_secret,
            "dedupe_saved_bytes": 0,
        },
        "files": files_meta,
        "blobs": blobs,
    }
    unique = sum(len(base64.b64decode(v)) for v in blobs.values())
    embedded_sum = sum(f["size"] for f in files_meta if f.get("embedded"))
    payload["stats"]["unique_embedded_raw_bytes"] = unique
    payload["stats"]["dedupe_saved_bytes"] = max(0, embedded_sum - unique)
    _ = embedded_raw  # walk accum kept for future telemetry
    return payload


def pack_to_bytes(payload: dict[str, Any], *, codec_prefer: str = DEFAULT_CODEC) -> tuple[bytes, dict[str, Any]]:
    raw_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    codec, compressed = _codec_encode(raw_json, prefer=codec_prefer)
    header = {
        "format": "automation-memory-pack-v1",
        "needle": NEEDLE,
        "codec": codec,
        "json_sha256": _sha256(raw_json),
        "json_bytes": len(raw_json),
        "pack_bytes": len(compressed),
        "stats": payload.get("stats") or {},
    }
    # Envelope: JSON header line + newline + binary codec payload
    head = (json.dumps(header, separators=(",", ":")) + "\n").encode("utf-8")
    return head + compressed, header


def write_pack(
    *,
    out_path: Path | None = None,
    root: Path | None = None,
    codec_prefer: str = DEFAULT_CODEC,
) -> tuple[Path, dict[str, Any]]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_pack(root=root, codec_prefer=codec_prefer)
    blob, header = pack_to_bytes(payload, codec_prefer=codec_prefer)
    path = out_path or (ARTIFACT_DIR / DEFAULT_PACK_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    # Sidecar summary (human-readable, additive)
    summary = {
        **header,
        "pack_path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "created_ts": payload["created_ts"],
        "policy": payload["policy"],
    }
    side = path.with_suffix(path.suffix + ".summary.json")
    side.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return path, summary


def read_pack(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (header, payload)."""
    raw = path.read_bytes()
    nl = raw.find(b"\n")
    if nl < 0:
        raise ValueError("pack missing header newline")
    header = json.loads(raw[:nl].decode("utf-8"))
    body = raw[nl + 1 :]
    codec = str(header.get("codec") or "zlib")
    json_bytes = _codec_decode(codec, body)
    if _sha256(json_bytes) != header.get("json_sha256"):
        raise ValueError("pack json_sha256 mismatch after decompress")
    payload = json.loads(json_bytes.decode("utf-8"))
    return header, payload


def _expand_target_allowed(out_dir: Path) -> None:
    """Refuse expand into live SoT; allow temp dirs or notes/memory_artifacts/*."""
    out_dir = out_dir.resolve()
    root_resolved = ROOT.resolve()
    if out_dir == root_resolved:
        raise ValueError("expand refuses to write into live repo root")
    try:
        rel = str(out_dir.relative_to(root_resolved))
    except ValueError:
        return  # outside repo — OK
    if rel == "notes/memory_artifacts" or rel.startswith("notes/memory_artifacts/"):
        return
    raise ValueError(
        f"expand staging must be outside repo or under "
        f"notes/memory_artifacts/ (got {rel})"
    )


def expand_pack(
    path: Path,
    out_dir: Path,
    *,
    embedded_only: bool = True,
) -> dict[str, Any]:
    """Restore embedded files into out_dir (staging). Never writes to ROOT.

    hash_ref entries are listed but not restored (body not in pack).
    """
    import base64

    out_dir = out_dir.resolve()
    _expand_target_allowed(out_dir)

    header, payload = read_pack(path)
    blobs = payload.get("blobs") or {}
    restored = 0
    missing_blob = 0
    hash_refs = 0
    for ent in payload.get("files") or []:
        rel = str(ent.get("path") or "")
        if not rel or ".." in rel.split("/"):
            continue
        if not ent.get("embedded"):
            hash_refs += 1
            if embedded_only:
                continue
            continue
        digest = str(ent.get("sha256") or "")
        b64 = blobs.get(digest)
        if b64 is None:
            missing_blob += 1
            continue
        data = base64.b64decode(b64)
        if _sha256(data) != digest:
            raise ValueError(f"blob sha mismatch for {rel}")
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        restored += 1
    return {
        "header": header,
        "restored": restored,
        "hash_refs_skipped": hash_refs,
        "missing_blob": missing_blob,
        "out_dir": str(out_dir),
    }


def verify_pack(
    path: Path,
    *,
    root: Path | None = None,
    staging: Path | None = None,
) -> dict[str, Any]:
    """Lossless verify: embedded files byte-identical to live; hash_refs sha match live."""
    root = root or ROOT
    header, payload = read_pack(path)
    import base64

    blobs = payload.get("blobs") or {}
    text_ok = 0
    text_fail: list[str] = []
    hash_ok = 0
    hash_fail: list[str] = []
    missing_live: list[str] = []

    # Expand to staging and compare
    own_staging = staging is None
    if staging is None:
        staging = Path(
            tempfile.mkdtemp(prefix="mem-pack-verify-", dir=str(ARTIFACT_DIR))
        )
    try:
        expand_pack(path, staging, embedded_only=True)
        for ent in payload.get("files") or []:
            rel = str(ent.get("path") or "")
            live = root / rel
            digest = str(ent.get("sha256") or "")
            if ent.get("embedded"):
                staged = staging / rel
                if not staged.is_file():
                    text_fail.append(f"missing_staged:{rel}")
                    continue
                got = staged.read_bytes()
                if _sha256(got) != digest:
                    text_fail.append(f"sha_staged:{rel}")
                    continue
                if live.is_file():
                    live_b = live.read_bytes()
                    if live_b != got:
                        text_fail.append(f"byte_diff_live:{rel}")
                        continue
                text_ok += 1
            else:
                # hash_ref: live must match recorded sha if present
                if not live.is_file():
                    missing_live.append(rel)
                    continue
                live_sha = _sha256(live.read_bytes())
                if live_sha != digest:
                    hash_fail.append(rel)
                else:
                    hash_ok += 1
        # Round-trip JSON integrity already checked in read_pack
        ok = not text_fail and not hash_fail
        return {
            "ok": ok,
            "pack": str(path),
            "codec": header.get("codec"),
            "json_bytes": header.get("json_bytes"),
            "pack_bytes": header.get("pack_bytes"),
            "ratio": (
                round(header["json_bytes"] / header["pack_bytes"], 3)
                if header.get("pack_bytes")
                else None
            ),
            "raw_bytes": (payload.get("stats") or {}).get("raw_bytes"),
            "unique_embedded_raw_bytes": (payload.get("stats") or {}).get(
                "unique_embedded_raw_bytes"
            ),
            "dedupe_saved_bytes": (payload.get("stats") or {}).get("dedupe_saved_bytes"),
            "text_byte_identical": text_ok,
            "text_fail": text_fail[:20],
            "hash_ref_sha_ok": hash_ok,
            "hash_ref_fail": hash_fail[:20],
            "missing_live_hash_ref": missing_live[:20],
            "blob_count": len(blobs),
            "staging": str(staging),
            "needle": NEEDLE,
        }
    finally:
        if own_staging and staging.is_dir():
            # Only delete staging we created under memory_artifacts
            import shutil

            try:
                staging.resolve().relative_to(ARTIFACT_DIR.resolve())
                shutil.rmtree(staging, ignore_errors=True)
            except ValueError:
                pass


def format_hot_pack_pointer(pack_path: Path | None = None) -> str:
    """Short Hot-memory pointer at latest pack (does not inline pack body)."""
    path = pack_path
    if path is None:
        candidate = ARTIFACT_DIR / DEFAULT_PACK_NAME
        if candidate.is_file():
            path = candidate
        else:
            return ""
    if not path.is_file():
        return ""
    try:
        raw = path.read_bytes()
        nl = raw.find(b"\n")
        header = json.loads(raw[:nl].decode("utf-8")) if nl > 0 else {}
    except (OSError, json.JSONDecodeError):
        header = {}
    rel = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    pb = header.get("pack_bytes") or path.stat().st_size
    jb = header.get("json_bytes") or "?"
    codec = header.get("codec") or "?"
    return (
        "## Lossless memory pack (additive — live SoT unchanged)\n"
        f"- Pack: `{rel}` ({codec}, {pb} B packed / {jb} B JSON)\n"
        f"- Expand/verify: `python3 scripts/peer_memory_compress.py --verify --pack {rel}`\n"
        f"- Needle: `{NEEDLE}` — never treat pack as license to delete live files."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Lossless additive repo memory pack")
    ap.add_argument("--compress", action="store_true")
    ap.add_argument("--expand", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--pack", type=Path, help="pack path")
    ap.add_argument("--out", type=Path, help="expand staging dir")
    ap.add_argument("--codec", default=DEFAULT_CODEC, help="zstd|xz|brotli|zlib|auto")
    ap.add_argument("--root", type=Path, default=None)
    args = ap.parse_args(argv)

    if not (args.compress or args.expand or args.verify):
        ap.print_help()
        return 2

    root = args.root or ROOT

    if args.compress:
        path, summary = write_pack(out_path=args.pack, root=root, codec_prefer=args.codec)
        stats = summary.get("stats") or {}
        raw_b = stats.get("raw_bytes") or 0
        uniq = stats.get("unique_embedded_raw_bytes") or 0
        pack_b = summary.get("pack_bytes") or path.stat().st_size
        print(f"wrote {path}")
        print(f"codec={summary.get('codec')} needle={NEEDLE}")
        print(f"raw_bytes={raw_b} unique_embedded={uniq} pack_bytes={pack_b}")
        if pack_b:
            print(
                f"ratio_vs_raw={raw_b / pack_b:.2f}x  "
                f"ratio_vs_json={ (summary.get('json_bytes') or 0) / pack_b:.2f}x  "
                f"dedupe_saved={stats.get('dedupe_saved_bytes')}"
            )
        print("policy=additive_only (live SoT not modified/deleted)")
        return 0

    pack = args.pack or (ARTIFACT_DIR / DEFAULT_PACK_NAME)
    if not pack.is_file():
        print(f"pack not found: {pack}", file=sys.stderr)
        return 1

    if args.expand:
        out = args.out
        if out is None:
            out = ARTIFACT_DIR / f"_expand_{int(time.time())}"
        result = expand_pack(pack, out)
        print(json.dumps(result, indent=2))
        return 0 if result.get("missing_blob", 1) == 0 else 1

    if args.verify:
        report = verify_pack(pack, root=root)
        try:
            import peer_memory_health as pmh

            pmh.write_last_verify(report, pack_path=pack)
        except Exception:  # noqa: BLE001 — verify still reports if cache write fails
            pass
        print(json.dumps(report, indent=2))
        return 0 if report.get("ok") else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
