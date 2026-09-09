#!/usr/bin/env python3
"""Memory health snapshot — pack age, verify, prefer_librarian, Hot vs MEMORY_SPAN.

Needle: OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07

Used by dashboard (/api/snapshot, /api/agents, /api/memory-health) and CLI.
Free desktop only — mechanical; no paid spawn. Never deletes live SoT.

Usage:
  python3 scripts/peer_memory_health.py
  python3 scripts/peer_memory_health.py --json
  ./scripts/peer memory-health
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import peer_fact_librarian as fl  # noqa: E402
import peer_memory_compress as pmc  # noqa: E402
import peer_memory_span as ms  # noqa: E402

NEEDLE = "OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07"
NO_PAY = ms.NO_PAY_HOT_LINE

PACK_PATH = pmc.ARTIFACT_DIR / pmc.DEFAULT_PACK_NAME
SUMMARY_PATH = Path(str(PACK_PATH) + ".summary.json")
LAST_VERIFY_PATH = pmc.ARTIFACT_DIR / "last_verify.json"
HOT_PATH = ROOT / "notes" / "AGENT_WORKING_MEMORY.md"
SPAN_PATH = ms.MEMORY_SPAN_MD

# Hot considered stale vs MEMORY_SPAN when Hot mtime lags Span by this many seconds.
HOT_STALE_LAG_SEC = 3600


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime if path.is_file() else None
    except OSError:
        return None


def _age_sec(mtime: float | None, *, now: float | None = None) -> float | None:
    if mtime is None:
        return None
    return max(0.0, (now or time.time()) - float(mtime))


def _load_last_verify() -> dict[str, Any]:
    if not LAST_VERIFY_PATH.is_file():
        return {}
    try:
        data = json.loads(LAST_VERIFY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_last_verify(result: dict[str, Any], *, pack_path: Path | None = None) -> Path:
    """Persist verify result for dashboard cheap reads (additive sidecar)."""
    pmc.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = pack_path or PACK_PATH
    payload = {
        "ts": time.time(),
        "ok": bool(result.get("ok")),
        "pack": str(path),
        "pack_mtime": _mtime(path),
        "needle": NEEDLE,
        "text_byte_identical": result.get("text_byte_identical"),
        "hash_ref_sha_ok": result.get("hash_ref_sha_ok"),
        "text_fail": (result.get("text_fail") or [])[:5],
        "hash_ref_fail": (result.get("hash_ref_fail") or [])[:5],
    }
    LAST_VERIFY_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return LAST_VERIFY_PATH


def integrity_ok(pack_path: Path | None = None) -> tuple[bool | None, str]:
    """Cheap pack integrity: header + json_sha256 after decompress (no full expand)."""
    path = pack_path or PACK_PATH
    if not path.is_file():
        return None, "no pack"
    try:
        pmc.read_pack(path)
        return True, "header+json_sha256 ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"integrity fail: {exc}"


def resolve_verify_ok(
    *,
    pack_path: Path | None = None,
    deep: bool = False,
    cheap_integrity: bool = False,
) -> tuple[bool | None, str, dict[str, Any]]:
    """Return (ok, why, detail). Prefer cached last_verify when pack mtime matches.

    Default avoids decompressing the whole pack on every dashboard poll.
    """
    path = pack_path or PACK_PATH
    if not path.is_file():
        return None, "no pack", {}

    if deep:
        try:
            result = pmc.verify_pack(path)
            write_last_verify(result, pack_path=path)
            return bool(result.get("ok")), "deep verify", result
        except Exception as exc:  # noqa: BLE001
            return False, f"deep verify error: {exc}", {"error": str(exc)}

    cached = _load_last_verify()
    pack_m = _mtime(path)
    if cached and cached.get("pack_mtime") is not None and pack_m is not None:
        try:
            if abs(float(cached["pack_mtime"]) - float(pack_m)) < 0.5:
                ok = cached.get("ok")
                if ok is None:
                    return None, "cached verify missing ok", cached
                return bool(ok), "cached last_verify (pack mtime match)", cached
        except (TypeError, ValueError):
            pass

    if cheap_integrity:
        ok, why = integrity_ok(path)
        return ok, why, {"mode": "integrity"}

    # Summary sidecar present + pack readable size → unknown until verify run
    if SUMMARY_PATH.is_file():
        return None, "no cached verify — run ./scripts/peer memory-compress-verify", {
            "mode": "summary_only"
        }
    return None, "no verify cache / summary", {"mode": "unknown"}


def build_memory_health(
    *,
    pack_path: Path | None = None,
    deep_verify: bool = False,
    cheap_integrity: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    now = now or time.time()
    path = pack_path or PACK_PATH
    pack_m = _mtime(path)
    hot_m = _mtime(HOT_PATH)
    span_m = _mtime(SPAN_PATH)
    summary: dict[str, Any] = {}
    if SUMMARY_PATH.is_file():
        try:
            summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            summary = {}

    prefer, prefer_why = fl.should_prefer_librarian(pack_path=path)
    verify_ok, verify_why, verify_detail = resolve_verify_ok(
        pack_path=path,
        deep=deep_verify,
        cheap_integrity=cheap_integrity,
    )

    hot_stale = False
    hot_vs_span_sec: float | None = None
    if hot_m is not None and span_m is not None:
        hot_vs_span_sec = float(span_m) - float(hot_m)
        # Span newer than Hot by > lag → Hot index may be stale
        hot_stale = hot_vs_span_sec > HOT_STALE_LAG_SEC

    created_ts = summary.get("created_ts")
    try:
        created_ts_f = float(created_ts) if created_ts is not None else None
    except (TypeError, ValueError):
        created_ts_f = None

    pack_age = _age_sec(pack_m, now=now)
    if pack_age is None and created_ts_f is not None:
        pack_age = _age_sec(created_ts_f, now=now)

    stats = summary.get("stats") if isinstance(summary.get("stats"), dict) else {}

    healthy = (
        path.is_file()
        and verify_ok is not False
        and not hot_stale
        and HOT_PATH.is_file()
        and SPAN_PATH.is_file()
    )

    return {
        "needle": NEEDLE,
        "no_pay": NO_PAY,
        "ok": healthy,
        "pack": {
            "exists": path.is_file(),
            "path": str(path.relative_to(ROOT)) if path.is_file() and path.is_relative_to(ROOT) else str(path),
            "mtime": pack_m,
            "age_sec": pack_age,
            "age_human": _human_age(pack_age),
            "bytes": path.stat().st_size if path.is_file() else None,
            "json_bytes": summary.get("json_bytes") or stats.get("json_bytes"),
            "pack_bytes": summary.get("pack_bytes"),
            "file_count": stats.get("file_count"),
            "created_ts": created_ts_f,
            "codec": summary.get("codec"),
        },
        "verify_ok": verify_ok,
        "verify_why": verify_why,
        "verify_detail": {
            k: verify_detail.get(k)
            for k in ("ok", "text_fail", "hash_ref_fail", "mode", "error")
            if k in verify_detail
        },
        "prefer_librarian": prefer,
        "prefer_why": prefer_why,
        "hot": {
            "path": "notes/AGENT_WORKING_MEMORY.md",
            "mtime": hot_m,
            "age_sec": _age_sec(hot_m, now=now),
            "age_human": _human_age(_age_sec(hot_m, now=now)),
        },
        "memory_span": {
            "path": "notes/MEMORY_SPAN.md",
            "mtime": span_m,
            "age_sec": _age_sec(span_m, now=now),
            "age_human": _human_age(_age_sec(span_m, now=now)),
        },
        "hot_vs_span_sec": hot_vs_span_sec,
        "hot_stale_vs_span": hot_stale,
        "always_read_paths": list(ms.ALWAYS_READ_PATHS),
        "heal_hint": (
            None
            if healthy
            else (
                "`./scripts/peer memory` · `./scripts/peer memory-compress-verify` · "
                "`./scripts/peer memory-quiz` · `./scripts/peer heal-all`"
            )
        ),
    }


def _human_age(sec: float | None) -> str:
    if sec is None:
        return "—"
    s = int(sec)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def format_report(h: dict[str, Any]) -> str:
    pack = h.get("pack") or {}
    lines = [
        "## Memory health",
        f"- Needle: `{h.get('needle')}`",
        f"- OK: {h.get('ok')}",
        f"- Pack: exists={pack.get('exists')} age={pack.get('age_human')} "
        f"files={pack.get('file_count')} bytes={pack.get('pack_bytes')}",
        f"- Verify: {h.get('verify_ok')} — {h.get('verify_why')}",
        f"- Prefer librarian: {h.get('prefer_librarian')} — {h.get('prefer_why')}",
        f"- Hot age={ (h.get('hot') or {}).get('age_human') } · "
        f"MEMORY_SPAN age={ (h.get('memory_span') or {}).get('age_human') } · "
        f"hot_stale_vs_span={h.get('hot_stale_vs_span')}",
        f"- {NO_PAY}",
    ]
    if h.get("heal_hint"):
        lines.append(f"- Heal: {h['heal_hint']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Memory health snapshot")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--deep-verify", action="store_true", help="Full pack verify + cache")
    ap.add_argument(
        "--integrity",
        action="store_true",
        help="Cheap header+json_sha256 check when no verify cache",
    )
    ap.add_argument("--pack", type=Path, default=None)
    args = ap.parse_args(argv)
    h = build_memory_health(
        pack_path=args.pack,
        deep_verify=bool(args.deep_verify),
        cheap_integrity=bool(args.integrity),
    )
    if args.json:
        print(json.dumps(h, indent=2, default=str))
    else:
        print(format_report(h), end="")
    return 0 if h.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
