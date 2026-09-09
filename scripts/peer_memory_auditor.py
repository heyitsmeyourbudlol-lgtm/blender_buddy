#!/usr/bin/env python3
"""Memory auditor — flag uncited worker claims vs pack/SoT (mechanical).

Needle: OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07

MVP: free desktop only — grep pack index + live Always-read SoT.
No paid API / no cursor-agent spawn required.

Usage:
  python3 scripts/peer_memory_auditor.py --claim "WQ Active has 3 open items"
  python3 scripts/peer_memory_auditor.py --claims-file /tmp/claims.txt
  echo "NO PAY forever" | python3 scripts/peer_memory_auditor.py --stdin
  ./scripts/peer memory-audit --claim "…"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import peer_fact_librarian as fl  # noqa: E402
import peer_memory_compress as pmc  # noqa: E402
import peer_memory_span as ms  # noqa: E402

NEEDLE = "OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07"
NO_PAY = "NO PAY: free desktop/local/CLEAN only — never paid API/Stripe/credits"

# Stopwords / noise for claim token extraction (mechanical, not NLP).
_STOP = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "of",
        "in",
        "on",
        "for",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "that",
        "this",
        "these",
        "those",
        "with",
        "as",
        "at",
        "by",
        "from",
        "it",
        "its",
        "we",
        "you",
        "they",
        "not",
        "no",
        "yes",
        "true",
        "false",
        "null",
        "none",
        "via",
        "into",
        "than",
        "then",
        "also",
        "just",
        "only",
        "should",
        "must",
        "will",
        "can",
        "may",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "our",
        "your",
        "their",
        # Too common in SoT — alone never counts as a cite
        "claim",
        "claims",
        "path",
        "paths",
        "file",
        "files",
        "line",
        "lines",
        "note",
        "notes",
        "item",
        "items",
        "open",
        "active",
        "without",
        "completely",
        "invented",
        "see",
        "using",
        "used",
        "work",
        "works",
        "test",
        "tests",
        "check",
        "green",
        "true",
        "false",
        "null",
    }
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]{3,}")
_PATH_HINT_RE = re.compile(
    r"(?:notes|scripts|dashboard|repos)/[A-Za-z0-9_./-]+\.[A-Za-z0-9]+"
)
_OVERSEER_RE = re.compile(r"OVERSEER_[A-Z0-9_]+")


def _normalize_claims(raw: list[str]) -> list[str]:
    out: list[str] = []
    for line in raw:
        s = (line or "").strip()
        if not s or s.startswith("#"):
            continue
        # Drop leading bullets / claim ids
        s = re.sub(r"^[-*]\s+", "", s)
        s = re.sub(r"^C\d+\s*[:.|]\s*", "", s, flags=re.I)
        if s:
            out.append(s)
    return out


def extract_needles(claim: str) -> list[str]:
    """Extract citation needles from a claim (paths, OVERSEER ids, content tokens)."""
    needles: list[str] = []
    for m in _OVERSEER_RE.findall(claim):
        needles.append(m)
    for m in _PATH_HINT_RE.findall(claim):
        needles.append(m)
    for tok in _TOKEN_RE.findall(claim):
        low = tok.lower()
        if low in _STOP:
            continue
        if tok.startswith("http"):
            continue
        if len(tok) < 4 and not tok.isupper():
            continue
        needles.append(tok)
    # de-dupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for n in needles:
        key = n.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(n)
    return uniq[:32]


def _load_sot_corpus(*, always_read: bool = True, extra_paths: list[Path] | None = None) -> dict[str, str]:
    """path → lowercase text for live SoT grepping."""
    corpus: dict[str, str] = {}
    paths: list[Path] = []
    if always_read:
        for rel in ms.ALWAYS_READ_PATHS:
            paths.append(ROOT / rel)
    for p in extra_paths or []:
        paths.append(p)
    # Always include pack summary + remembrance SOPs (thin).
    paths.extend(
        [
            ROOT / "notes" / "SOP_AGENT_REMEMBRANCE.md",
            ROOT / "notes" / "SOP_LOSSLESS_MEMORY_COMPRESSION.md",
            ROOT / "notes" / "AGENT_AMNESIA_RESEARCH.md",
        ]
    )
    for path in paths:
        if not path.is_file():
            continue
        try:
            rel = str(path.relative_to(ROOT))
        except ValueError:
            rel = str(path)
        try:
            corpus[rel] = path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
    return corpus


def _pack_path_index(pack_path: Path | None = None) -> list[str]:
    path = pack_path or pmc.ARTIFACT_DIR / pmc.DEFAULT_PACK_NAME
    if not path.is_file():
        return []
    try:
        _header, payload = pmc.read_pack(path)
    except Exception:  # noqa: BLE001
        return []
    return [str(e.get("path") or "") for e in (payload.get("files") or []) if e.get("path")]


def _cite_in_corpus(needle: str, corpus: dict[str, str]) -> list[str]:
    low = needle.lower()
    hits: list[str] = []
    for rel, text in corpus.items():
        if low in text:
            hits.append(rel)
            if len(hits) >= 5:
                break
    return hits


def _cite_in_pack_index(needle: str, pack_paths: list[str]) -> list[str]:
    low = needle.lower()
    hits: list[str] = []
    for p in pack_paths:
        if low in p.lower():
            hits.append(p)
            if len(hits) >= 5:
                break
    return hits


def _content_cite_ok(citations: list[dict[str, Any]]) -> bool:
    """Avoid single dictionary-word false cites (e.g. 'citation' in research doc)."""
    if len(citations) >= 2:
        return True
    for c in citations:
        n = str(c.get("needle") or "")
        if _OVERSEER_RE.fullmatch(n) or _PATH_HINT_RE.fullmatch(n):
            return True
        # Repo-style identifiers: WORK_QUEUE, AGENT_WORKING_MEMORY
        if re.fullmatch(r"[A-Z][A-Z0-9_]{5,}", n):
            return True
        # Rare tokens with digits (hashes, versions) — only if they actually hit
        if any(ch.isdigit() for ch in n) and len(n) >= 10:
            return True
    return False


def audit_claims(
    claims: list[str],
    *,
    pack_path: Path | None = None,
    min_needles: int = 1,
    require_path_or_overseer: bool = False,
) -> dict[str, Any]:
    """Audit claims; flag those without SoT/pack citation hits.

    A claim is CITED when ≥1 extracted needle hits live SoT corpus or pack path index.
    Claims with zero extractable needles → UNCITED (cannot prove).
    """
    claims = _normalize_claims(claims)
    corpus = _load_sot_corpus()
    pack_paths = _pack_path_index(pack_path)
    prefer, prefer_why = fl.should_prefer_librarian(pack_path=pack_path)

    rows: list[dict[str, Any]] = []
    uncited = 0
    for claim in claims:
        needles = extract_needles(claim)
        citations: list[dict[str, Any]] = []
        for n in needles:
            sot_hits = _cite_in_corpus(n, corpus)
            pack_hits = _cite_in_pack_index(n, pack_paths)
            if sot_hits or pack_hits:
                citations.append(
                    {
                        "needle": n,
                        "sot": sot_hits[:3],
                        "pack_paths": pack_hits[:3],
                    }
                )
        strong = any(
            _OVERSEER_RE.fullmatch(c["needle"]) or _PATH_HINT_RE.fullmatch(c["needle"])
            for c in citations
        )
        content_ok = _content_cite_ok(citations)
        ok = strong or content_ok
        if require_path_or_overseer:
            ok = strong
        if not needles:
            ok = False
        status = "CITED" if ok else "UNCITED"
        if not ok:
            uncited += 1
        rows.append(
            {
                "claim": claim,
                "status": status,
                "needles": needles,
                "citations": citations,
                "strong_cite": strong,
            }
        )

    ok_all = uncited == 0 and bool(claims)
    return {
        "ok": ok_all,
        "needle": NEEDLE,
        "no_pay": NO_PAY,
        "claim_count": len(claims),
        "cited": len(claims) - uncited,
        "uncited": uncited,
        "prefer_librarian": prefer,
        "prefer_why": prefer_why,
        "pack_paths_indexed": len(pack_paths),
        "sot_files_scanned": len(corpus),
        "rows": rows,
        "heal_hint": (
            None
            if ok_all
            else (
                "Uncited claims — open Always-read SoT, run "
                "`./scripts/peer fact-query \"…\"`, then re-audit. "
                "Heal: `./scripts/peer memory` · `./scripts/peer heal-all`"
            )
        ),
    }


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "## Memory auditor (mechanical — no paid spawn)",
        f"- Needle: `{result.get('needle')}`",
        f"- Claims: {result.get('claim_count')} · cited={result.get('cited')} · "
        f"uncited={result.get('uncited')}",
        f"- Prefer librarian: {result.get('prefer_librarian')} — {result.get('prefer_why')}",
        f"- Pack path index: {result.get('pack_paths_indexed')} · "
        f"SoT files: {result.get('sot_files_scanned')}",
        f"- {NO_PAY}",
        "",
    ]
    for i, row in enumerate(result.get("rows") or [], 1):
        st = row.get("status")
        lines.append(f"{i}. **{st}** — {row.get('claim')}")
        cites = row.get("citations") or []
        if cites:
            for c in cites[:4]:
                sot = ", ".join(c.get("sot") or []) or "—"
                lines.append(f"   - needle `{c.get('needle')}` → SoT: {sot}")
        elif row.get("needles"):
            lines.append(f"   - needles tried: {', '.join((row.get('needles') or [])[:6])}")
        else:
            lines.append("   - no extractable needles (add path:line or OVERSEER_* )")
    hint = result.get("heal_hint")
    if hint:
        lines.extend(["", f"**Heal:** {hint}"])
    lines.append("")
    lines.append(f"Result: {'PASS' if result.get('ok') else 'FAIL'}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Memory auditor — flag uncited claims")
    ap.add_argument("--claim", action="append", default=[], help="Claim text (repeatable)")
    ap.add_argument("--claims-file", type=Path, help="One claim per line")
    ap.add_argument("--stdin", action="store_true", help="Read claims from stdin")
    ap.add_argument("--pack", type=Path, default=None, help="Pack path override")
    ap.add_argument("--json", action="store_true", help="JSON stdout")
    ap.add_argument(
        "--require-strong",
        action="store_true",
        help="Require path or OVERSEER_* citation (stricter)",
    )
    args = ap.parse_args(argv)

    raw: list[str] = list(args.claim or [])
    if args.claims_file and args.claims_file.is_file():
        raw.extend(args.claims_file.read_text(encoding="utf-8", errors="replace").splitlines())
    if args.stdin or (not raw and not sys.stdin.isatty()):
        raw.extend(sys.stdin.read().splitlines())

    if not raw:
        print(
            "memory-audit: provide --claim, --claims-file, or --stdin\n"
            f"{NO_PAY}",
            file=sys.stderr,
        )
        return 2

    result = audit_claims(
        raw,
        pack_path=args.pack,
        require_path_or_overseer=bool(args.require_strong),
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_report(result), end="")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
