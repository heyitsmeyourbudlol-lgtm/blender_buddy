#!/usr/bin/env python3
"""Amnesia combat — session ledger, spaced stickies, distill, claim ledger.

SCOPE A from notes/AGENT_AMNESIA_RESEARCH.md (needle OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07).

Usage:
  python3 scripts/peer_session_amnesia.py append --decision "…" --paths a,b --needle NEEDLE
  python3 scripts/peer_session_amnesia.py distill --bullets-file /tmp/b.txt --target conversation
  python3 scripts/peer_session_amnesia.py claim --claim "verify green" --source "path:line"
  python3 scripts/peer_session_amnesia.py sticky-status
  ./scripts/peer session-ledger-append --decision "…" --paths notes/WORK_QUEUE.md
  ./scripts/peer session-distill --bullets-file …
  ./scripts/peer session-claim --claim "…" --source "…"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

NEEDLE = "OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07"

SESSION_LEDGER_DIR = ROOT / "notes" / "session_ledger"
CLAIM_LEDGER_DIR = SESSION_LEDGER_DIR / "claims"
PEER_CONVERSATION_MD = ROOT / "notes" / "PEER_CONVERSATION.md"
STATE_PATH = auto.CONFIG_DIR / "session-amnesia-state.json"

# Spaced sticky reinject — every N Hot refreshes re-emit the trio.
DEFAULT_STICKY_EVERY_N = 5

NO_PAY_STICKY = (
    "NO PAY: free desktop/local/CLEAN only — never paid API/Stripe/credits"
)
FACTORY_WORKS_STICKY = (
    "FACTORY WORKS: adapt → native verify → worktree/PR → irreversible artifact "
    "(executable factory work — not ASI/kit theater)"
)
PACK_SAFE_STICKY = (
    "PACK ≠ DELETE: lossless pack is additive archive only — never delete live SoT"
)

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(sk|pk|rk)_(live|test)_[A-Za-z0-9]{8,}"),
    re.compile(r"(?i)\bwhsec_[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|secret|password|token|bearer)\s*[:=]\s*\S+"),
    re.compile(r"(?i)\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"(?i)\b(AKIA|ASIA)[A-Z0-9]{16}"),
)

CITATION_RE = re.compile(
    r"`?([A-Za-z0-9_./-]+\.(?:py|md|json|jsonl|sh|txt|html|js|css))(?::(\d+))?`?"
    r"|`?(OVERSEER_[A-Z0-9_]+)`?"
)

VERDICTS = frozenset({"PASS", "FAIL", "SPLIT", "UNKNOWN", "OVERCLAIM"})


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _relpath(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def scrub_secrets(text: str) -> str:
    """Redact secret-shaped substrings before write-through."""
    out = str(text or "")
    for pat in SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"hot_refresh_count": 0, "last_sticky_at": 0, "sticky_every_n": DEFAULT_STICKY_EVERY_N}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"hot_refresh_count": 0, "last_sticky_at": 0, "sticky_every_n": DEFAULT_STICKY_EVERY_N}
    return data if isinstance(data, dict) else {"hot_refresh_count": 0}


def _save_state(state: dict[str, Any]) -> None:
    auto.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def sticky_every_n(state: dict[str, Any] | None = None) -> int:
    st = state if state is not None else _load_state()
    try:
        n = int(st.get("sticky_every_n") or DEFAULT_STICKY_EVERY_N)
    except (TypeError, ValueError):
        n = DEFAULT_STICKY_EVERY_N
    return max(1, n)


def format_spaced_sticky_block(*, force: bool = False, bump: bool = True) -> str:
    """Every N Hot refreshes, re-emit NO-PAY + factory-works + pack≠delete.

    Call from peer_transcript Hot path. ``bump=True`` increments the refresh
    counter (production). Tests can pass ``bump=False`` with a fixture state
    via monkeypatch of STATE_PATH.
    """
    state = _load_state()
    count = int(state.get("hot_refresh_count") or 0)
    if bump:
        count += 1
        state["hot_refresh_count"] = count
    every = sticky_every_n(state)
    due = force or (count > 0 and count % every == 0)
    if bump:
        if due:
            state["last_sticky_at"] = count
        _save_state(state)
    if not due:
        return ""
    return "\n".join(
        [
            "## Spaced stickies (amnesia combat — re-emit every "
            f"{every} Hot refreshes)",
            f"- {NO_PAY_STICKY}",
            f"- {FACTORY_WORKS_STICKY}",
            f"- {PACK_SAFE_STICKY}",
            f"- Needle: `{NEEDLE}` · refresh #{count}",
        ]
    )


def sticky_status() -> dict[str, Any]:
    state = _load_state()
    count = int(state.get("hot_refresh_count") or 0)
    every = sticky_every_n(state)
    next_in = every - (count % every) if every else 0
    if count > 0 and count % every == 0:
        next_in = every
    return {
        "hot_refresh_count": count,
        "sticky_every_n": every,
        "last_sticky_at": int(state.get("last_sticky_at") or 0),
        "next_sticky_in": next_in,
        "stickies": [NO_PAY_STICKY, FACTORY_WORKS_STICKY, PACK_SAFE_STICKY],
        "needle": NEEDLE,
    }


def ledger_path(*, day: str | None = None) -> Path:
    return SESSION_LEDGER_DIR / f"{day or _utc_day()}.jsonl"


def claim_ledger_path(*, day: str | None = None) -> Path:
    return CLAIM_LEDGER_DIR / f"{day or _utc_day()}.jsonl"


def append_session_ledger(
    *,
    decision: str,
    paths: list[str] | None = None,
    needle: str = "",
    falsifier: str = "",
    role_id: str = "",
    extra: dict[str, Any] | None = None,
) -> Path:
    """Append one write-through row before DONE/reply. Scrubs secrets."""
    decision_s = scrub_secrets(str(decision or "").strip())
    if not decision_s:
        raise ValueError("decision required")
    clean_paths: list[str] = []
    for p in paths or []:
        s = scrub_secrets(str(p).strip())
        if s:
            clean_paths.append(s[:240])
    row: dict[str, Any] = {
        "ts": time.time(),
        "iso": _utc_iso(),
        "decision": decision_s[:2000],
        "paths": clean_paths[:32],
        "needle": scrub_secrets(str(needle or "").strip())[:200],
        "falsifier": scrub_secrets(str(falsifier or "").strip())[:500],
        "role_id": scrub_secrets(str(role_id or "").strip())[:80],
        "kind": "session_ledger",
    }
    if extra and isinstance(extra, dict):
        for k, v in list(extra.items())[:8]:
            if isinstance(v, (str, int, float, bool)) or v is None:
                row[str(k)[:40]] = scrub_secrets(str(v))[:500] if isinstance(v, str) else v
    SESSION_LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    path = ledger_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
    return path


def _parse_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("- ", "* ", "• ")):
            line = line[2:].strip()
        elif re.match(r"^\d+[.)]\s+", line):
            line = re.sub(r"^\d+[.)]\s+", "", line).strip()
        if line:
            bullets.append(scrub_secrets(line)[:500])
    return bullets[:15]


def _has_citation(bullet: str) -> bool:
    return bool(CITATION_RE.search(bullet))


def format_distill_block(bullets: list[str], *, title: str = "Turn distill") -> str:
    lines = [f"### {title} ({_utc_iso()})", ""]
    for i, b in enumerate(bullets, 1):
        cite_ok = "✓" if _has_citation(b) else "⚠ uncited"
        lines.append(f"{i}. {b} _{cite_ok}_")
    lines.append("")
    lines.append(f"_Needle:_ `{NEEDLE}` · cite `path:line` or OVERSEER_* only.")
    return "\n".join(lines)


def distill_to_conversation(
    bullets: list[str],
    *,
    conversation_path: Path | None = None,
) -> Path:
    """Append cited distill bullets under PEER_CONVERSATION Recent turns."""
    path = conversation_path or PEER_CONVERSATION_MD
    clean = [b for b in bullets if b]
    if not clean:
        raise ValueError("distill requires 1–15 bullets")
    if len(clean) > 15:
        clean = clean[:15]
    block = format_distill_block(clean, title="ASSISTANT (turn-end distill)")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        body = path.read_text(encoding="utf-8", errors="replace")
    else:
        body = (
            "# Peer conversation — canonical summary for loop input\n\n"
            "## Recent turns (since summary)\n\n"
        )
    marker = "## Recent turns (since summary)"
    if marker in body:
        insert_at = body.index(marker) + len(marker)
        new_body = body[:insert_at] + "\n\n" + block + "\n" + body[insert_at:]
    else:
        new_body = body.rstrip() + "\n\n" + marker + "\n\n" + block + "\n"
    path.write_text(new_body, encoding="utf-8")
    return path


def distill_to_last_cycle_pins(
    bullets: list[str],
    *,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pin distill bullets onto last_cycle.amnesia_pins (does not invent verify_ok)."""
    import peer_transcript as pt

    live = state if state is not None else pt.load_state()
    lc = live.get("last_cycle")
    if not isinstance(lc, dict):
        lc = {}
        live["last_cycle"] = lc
    pins = [
        {"text": scrub_secrets(b)[:400], "cited": _has_citation(b)}
        for b in bullets[:15]
        if b
    ]
    lc["amnesia_pins"] = pins
    lc["amnesia_pins_ts"] = time.time()
    lc["amnesia_pins_iso"] = _utc_iso()
    if state is None:
        pt.save_state(live)
    return live


def distill_turn(
    text: str,
    *,
    target: str = "conversation",
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn-end conversation distill → PEER_CONVERSATION and/or last_cycle pins."""
    bullets = _parse_bullets(text)
    if not bullets:
        raise ValueError("no bullets parsed")
    if len(bullets) < 1 or len(bullets) > 15:
        raise ValueError("need 1–15 cited bullets")
    uncited = [b for b in bullets if not _has_citation(b)]
    result: dict[str, Any] = {
        "bullets": len(bullets),
        "uncited": len(uncited),
        "target": target,
        "needle": NEEDLE,
    }
    tgt = (target or "conversation").strip().lower()
    if tgt in ("conversation", "both", "peer_conversation"):
        path = distill_to_conversation(bullets)
        result["conversation"] = _relpath(path)
    if tgt in ("last_cycle", "pins", "both"):
        distill_to_last_cycle_pins(bullets, state=state)
        result["last_cycle_pins"] = True
    if tgt not in ("conversation", "both", "peer_conversation", "last_cycle", "pins"):
        raise ValueError("target must be conversation|last_cycle|both")
    return result


def _read_snippet(rel: str, line_no: int | None, *, max_chars: int = 240) -> str | None:
    path = ROOT / rel
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if line_no is None:
        return scrub_secrets("\n".join(lines[:3]))[:max_chars]
    idx = max(1, line_no) - 1
    if idx >= len(lines):
        return None
    return scrub_secrets(lines[idx])[:max_chars]


def evaluate_session_claim(
    claim: str,
    *,
    source: str = "",
    evidence: str = "",
    role_id: str = "",
) -> dict[str, Any]:
    """OVERCLAIM-style row for session facts (thin reuse of fact_checker pattern).

    Verdict rules (mechanical, no paid APIs):
    - No source path → OVERCLAIM
    - Source file missing → FAIL
    - Source file:line present + claim text loosely matches snippet → PASS
    - Source present but claim contradicts common verify/queue signals → OVERCLAIM/SPLIT
    """
    claim_s = scrub_secrets(str(claim or "").strip())
    if not claim_s:
        raise ValueError("claim required")
    source_s = scrub_secrets(str(source or "").strip())
    evidence_s = scrub_secrets(str(evidence or "").strip())[:500]

    file_part = ""
    line_no: int | None = None
    m = re.match(r"^([^:]+):(\d+)$", source_s)
    if m:
        file_part, line_no = m.group(1), int(m.group(2))
    elif source_s:
        file_part = source_s

    verdict = "UNKNOWN"
    note = ""
    snippet = ""

    if not file_part:
        verdict = "OVERCLAIM"
        note = "no file:line source — session claim requires citation"
    else:
        snippet_opt = _read_snippet(file_part, line_no)
        if snippet_opt is None:
            verdict = "FAIL"
            note = f"source missing or line OOB: {file_part}" + (f":{line_no}" if line_no else "")
        else:
            snippet = snippet_opt
            claim_l = claim_s.lower()
            snip_l = snippet.lower()
            # Soft lexical overlap — not semantic; guards empty/theater citations.
            tokens = [t for t in re.split(r"[^a-z0-9_]+", claim_l) if len(t) >= 4]
            hits = sum(1 for t in tokens if t in snip_l)
            if tokens and hits == 0 and not evidence_s:
                verdict = "OVERCLAIM"
                note = "source opened but claim tokens absent from snippet (and no evidence)"
            elif "verify" in claim_l and "ok" in claim_l and "false" in snip_l:
                verdict = "OVERCLAIM"
                note = "verify-ok claim vs snippet containing false"
            elif hits >= 1 or evidence_s:
                verdict = "PASS"
                note = f"grounded ({hits}/{len(tokens)} token hits)" if tokens else "evidence supplied"
            else:
                verdict = "SPLIT"
                note = "source exists; weak token overlap"

    row = {
        "ts": time.time(),
        "iso": _utc_iso(),
        "id": f"S{_utc_day().replace('-', '')}-{int(time.time()) % 100000:05d}",
        "claim": claim_s[:500],
        "verdict": verdict,
        "source": source_s[:240],
        "evidence": evidence_s or snippet[:240],
        "note": note[:240],
        "role_id": scrub_secrets(str(role_id or "").strip())[:80],
        "kind": "session_claim",
        "needle": NEEDLE,
    }
    CLAIM_LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    path = claim_ledger_path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
    row["ledger"] = _relpath(path)
    return row


def worktree_hub_rules_block() -> str:
    """Document hub SoT vs worktree-local scratch (for Hot / SOP)."""
    return "\n".join(
        [
            "## Hub SoT vs worktree scratch",
            "- **Hub SoT (never fork):** `WORK_QUEUE` ↔ `self_improve_context`, "
            "`AGENT_WORKING_MEMORY`, Hot/pack, `session_ledger/`, Fact Librarian pack.",
            "- **Worktree-local OK:** `notes/worktree_scratch/` ephemeral notes only — "
            "do not promote scratch into Always-read; land durable facts to hub.",
            "- **Deletes:** never delete live SoT because a pack exists; safe deletes = "
            "scratch/temp only.",
            f"- Needle: `{NEEDLE}`",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Session amnesia combat helpers")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_app = sub.add_parser("append", help="Write-through session ledger row")
    p_app.add_argument("--decision", required=True)
    p_app.add_argument("--paths", default="", help="Comma-separated paths")
    p_app.add_argument("--needle", default="")
    p_app.add_argument("--falsifier", default="")
    p_app.add_argument("--role", default="")

    p_dist = sub.add_parser("distill", help="Turn-end cited bullets → conversation/pins")
    p_dist.add_argument("--text", default="")
    p_dist.add_argument("--bullets-file", default="")
    p_dist.add_argument(
        "--target",
        default="conversation",
        choices=("conversation", "last_cycle", "both"),
    )

    p_claim = sub.add_parser("claim", help="Session claim ledger (OVERCLAIM-style)")
    p_claim.add_argument("--claim", required=True)
    p_claim.add_argument("--source", default="", help="path or path:line")
    p_claim.add_argument("--evidence", default="")
    p_claim.add_argument("--role", default="")

    sub.add_parser("sticky-status", help="Spaced sticky counter status")
    sub.add_parser("sticky-preview", help="Force spaced sticky block to stdout")
    sub.add_parser("hub-rules", help="Print worktree vs hub SoT rules")

    args = parser.parse_args()

    if args.cmd == "append":
        paths = [p.strip() for p in str(args.paths).split(",") if p.strip()]
        path = append_session_ledger(
            decision=args.decision,
            paths=paths,
            needle=args.needle,
            falsifier=args.falsifier,
            role_id=args.role,
        )
        print(f"session-ledger: {_relpath(path)}")
        return 0

    if args.cmd == "distill":
        text = args.text
        if args.bullets_file:
            text = Path(args.bullets_file).read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            print("distill requires --text or --bullets-file", file=sys.stderr)
            return 1
        try:
            result = distill_turn(text, target=args.target)
        except ValueError as exc:
            print(f"distill: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "claim":
        try:
            row = evaluate_session_claim(
                args.claim,
                source=args.source,
                evidence=args.evidence,
                role_id=args.role,
            )
        except ValueError as exc:
            print(f"claim: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(row, indent=2))
        return 0 if row.get("verdict") != "FAIL" else 2

    if args.cmd == "sticky-status":
        print(json.dumps(sticky_status(), indent=2))
        return 0

    if args.cmd == "sticky-preview":
        print(format_spaced_sticky_block(force=True, bump=False))
        return 0

    if args.cmd == "hub-rules":
        print(worktree_hub_rules_block())
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
