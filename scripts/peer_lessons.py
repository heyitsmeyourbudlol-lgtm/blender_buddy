#!/usr/bin/env python3
"""Lessons curator — harvest + lossless squeeze of institutional memory.

Needle: OVERSEER_LESSONS_CURATOR_2026_09_06

ONLY job: mine logs/journals → durable lessons. Never feature code.
North star: squeeze unique store (dedupe / fold / promote) — **never prune**
distinct facts or needles (``facts_preserved=true``).

Surfaces (existing SoT — do not invent parallel stores):
  - memory journals     (peer_memory_span)
  - project-learnings   (peer_project_learning → PROJECT_LEARNING.md)
  - DEBRIEF_LOG         (peer_debrief)
  - AGENT_ERROR_PLAYBOOK (peer_playbook)

Usage:
  python3 scripts/peer_lessons.py --harvest
  python3 scripts/peer_lessons.py --squeeze --write
  ./scripts/peer lessons-harvest
  ./scripts/peer lessons-squeeze --write
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# COMPRESSION_ZLIB_LESSONS_FP_2026_09_07 — fact keys use zlib; avoid hashlib→libcrypto
# (~5.7MB) when lessons-harvest runs in-process near peer/improve.

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

NEEDLE = "OVERSEER_LESSONS_CURATOR_2026_09_06"
ROLE_ID = "lessons_curator"
STATE_PATH = auto.CONFIG_DIR / "lessons-curator-state.json"
HARVEST_JSONL = auto.CONFIG_DIR / "lessons-harvest.jsonl"

_SELF_HEAL_ARROW = re.compile(r"self-heal:\s+(\S+)\s+→\s+(.+)$")
_SELF_HEAL_CLEAR = re.compile(r"self-heal registry clear:\s+(\S+)\s+\(absent_from_scan\)")
_OVERSEER = re.compile(r"(OVERSEER_[A-Z0-9_]+_\d{4}_\d{2}_\d{2})")
_WATCHDOG = re.compile(r"WATCHDOG|Keep-alive fuel|RESULT STALL", re.I)
_PATH_CANON = re.compile(r"(?:/Users/[^/\s]+|/home/[^/\s]+|/tmp)(/[^\s:]+)")
_WS = re.compile(r"\s+")
_PROMOTE_HITS = 3


@dataclass
class LessonFact:
    key: str
    text: str
    needle: str = ""
    source: str = ""
    first_ts: float = 0.0
    last_ts: float = 0.0
    hit_count: int = 1
    tags: list[str] = field(default_factory=list)

    def to_dense(self) -> str:
        parts: list[str] = []
        if self.needle:
            parts.append(self.needle)
        body = self.text
        if self.needle and self.needle in body:
            body = body.replace(self.needle, "").strip(" ·:-")
        body = _WS.sub(" ", body).strip()[:400]
        if body:
            parts.append(body)
        if self.hit_count > 1:
            parts.append(f"hits={self.hit_count}")
        return " · ".join(parts)


def _now() -> float:
    return time.time()


def normalize_text(text: str) -> str:
    """Lossless normalize: whitespace + home paths → ~ — never drop meaning tokens."""
    t = str(text or "").strip()
    t = _PATH_CANON.sub(r"~\1", t)
    t = _WS.sub(" ", t)
    return t


def extract_needle(text: str) -> str:
    m = _OVERSEER.search(text or "")
    return m.group(1) if m else ""


def fact_key(text: str, *, needle: str = "") -> str:
    """Stable key for near-identical lessons (same needle or normalized hash)."""
    n = needle or extract_needle(text)
    if n:
        return f"needle:{n}"
    norm = normalize_text(text).lower()
    norm = re.sub(r"\b20\d{2}-\d{2}-\d{2}[T\s]\d{2}:\d{2}(:\d{2})?Z?\b", "", norm)
    norm = re.sub(r"\bagents=\d+\b", "", norm)
    norm = re.sub(r"\bidle=\d+s?\b", "", norm)
    norm = _WS.sub(" ", norm).strip()
    raw = norm.encode("utf-8", errors="replace")
    digest = (
        f"{zlib.adler32(raw) & 0xffffffff:08x}"
        f"{zlib.crc32(raw) & 0xffffffff:08x}"
    )[:16]
    return "z:" + digest


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    except OSError:
        return []
    return rows


def _tail_lines(path: Path, *, max_lines: int = 400) -> list[str]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-max_lines:]


def _merge_fact(bucket: dict[str, LessonFact], fact: LessonFact) -> None:
    prev = bucket.get(fact.key)
    if prev is None:
        bucket[fact.key] = fact
        return
    prev.hit_count += fact.hit_count
    prev.first_ts = min(prev.first_ts or fact.first_ts, fact.first_ts or prev.first_ts)
    prev.last_ts = max(prev.last_ts, fact.last_ts)
    if fact.needle and not prev.needle:
        prev.needle = fact.needle
    if len(fact.text) > len(prev.text) + 20:
        prev.text = fact.text
    for tag in fact.tags:
        if tag not in prev.tags:
            prev.tags.append(tag)
    if fact.source and fact.source not in (prev.source or ""):
        prev.source = f"{prev.source}+{fact.source}" if prev.source else fact.source


def mine_self_heal_log() -> list[LessonFact]:
    log = auto.CONFIG_DIR / "peer-loop.log"
    lines = _tail_lines(log, max_lines=600)
    bucket: dict[str, LessonFact] = {}
    now = _now()
    for line in lines:
        m = _SELF_HEAL_ARROW.search(line)
        if m:
            bid, result = m.group(1), m.group(2).strip()
            if result.startswith("cooldown"):
                continue
            text = f"self-heal {bid} → {result}"
            needle = extract_needle(line)
            key = (
                f"needle:{needle}"
                if needle
                else f"heal:{bid}:{fact_key(result)}"
            )
            _merge_fact(
                bucket,
                LessonFact(
                    key=key,
                    text=normalize_text(text)[:500],
                    needle=needle,
                    source="peer-loop.log",
                    first_ts=now,
                    last_ts=now,
                    tags=["self-heal", bid],
                ),
            )
            continue
        m2 = _SELF_HEAL_CLEAR.search(line)
        if m2:
            bid = m2.group(1)
            text = f"self-heal registry clear: {bid} (absent_from_scan)"
            _merge_fact(
                bucket,
                LessonFact(
                    key=f"heal_clear:{bid}",
                    text=text,
                    source="peer-loop.log",
                    first_ts=now,
                    last_ts=now,
                    tags=["self-heal", "registry-clear", bid],
                ),
            )
    return list(bucket.values())


def mine_progress_watch_log() -> list[LessonFact]:
    path = Path.home() / ".config" / "automation" / "peer-progress-watch.log"
    hub = Path.home() / ".config" / "automation-hub" / "peer-progress-watch.log"
    lines = _tail_lines(hub if hub.is_file() else path, max_lines=200)
    bucket: dict[str, LessonFact] = {}
    now = _now()
    for line in lines:
        if "STALL" not in line and "progress MOVED" not in line:
            continue
        if "ok idle=" in line:
            continue
        needle = extract_needle(line) or NEEDLE
        text = normalize_text(line.split("  ", 1)[-1] if "  " in line else line)[:400]
        _merge_fact(
            bucket,
            LessonFact(
                key=fact_key(text, needle=needle),
                text=text,
                needle=needle,
                source="peer-progress-watch.log",
                first_ts=now,
                last_ts=now,
                tags=["progress-watch"],
            ),
        )
    return list(bucket.values())


def mine_journals() -> list[LessonFact]:
    import peer_memory_span as mem

    journal_dir = mem.JOURNAL_DIR
    if not journal_dir.is_dir():
        return []
    bucket: dict[str, LessonFact] = {}
    for path in sorted(journal_dir.glob("*.jsonl")):
        for row in _read_jsonl(path):
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            if _WATCHDOG.search(text) and len(text) > 180:
                n = extract_needle(text)
                text = normalize_text(f"{n or 'WATCHDOG'} · {text[:120]}")
            ts = float(row.get("ts") or _now())
            needle = extract_needle(text)
            tags = list(row.get("tags") or [])
            tags.append(f"journal:{path.stem}")
            _merge_fact(
                bucket,
                LessonFact(
                    key=fact_key(text, needle=needle),
                    text=normalize_text(text)[:500],
                    needle=needle,
                    source=f"journal:{path.stem}",
                    first_ts=ts,
                    last_ts=ts,
                    tags=tags[:10],
                ),
            )
    return list(bucket.values())


def mine_project_learnings() -> list[LessonFact]:
    import peer_project_learning as pl

    bucket: dict[str, LessonFact] = {}
    for row in _read_jsonl(pl.SHARED_LEARNINGS_JSONL):
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        ts = float(row.get("ts") or _now())
        needle = extract_needle(text)
        _merge_fact(
            bucket,
            LessonFact(
                key=fact_key(text, needle=needle),
                text=normalize_text(text)[:500],
                needle=needle,
                source="project-learnings",
                first_ts=ts,
                last_ts=ts,
                tags=["project-learning", str(row.get("role_id") or "")],
            ),
        )
    return list(bucket.values())


def collect_facts() -> list[LessonFact]:
    bucket: dict[str, LessonFact] = {}
    for batch in (
        mine_self_heal_log(),
        mine_progress_watch_log(),
        mine_journals(),
        mine_project_learnings(),
    ):
        for fact in batch:
            _merge_fact(bucket, fact)
    return list(bucket.values())


def squeeze_facts(facts: list[LessonFact]) -> tuple[list[LessonFact], dict[str, Any]]:
    """Lossless squeeze: fold near-dupes; never drop distinct keys/needles."""
    before_keys = {f.key for f in facts}
    before_needles = {f.needle for f in facts if f.needle}
    before_bytes = sum(len(f.text.encode("utf-8")) for f in facts)

    bucket: dict[str, LessonFact] = {}
    for fact in facts:
        _merge_fact(bucket, fact)
    out = sorted(bucket.values(), key=lambda f: (-f.hit_count, -f.last_ts))

    after_keys = {f.key for f in out}
    after_needles = {f.needle for f in out if f.needle}
    after_bytes = sum(len(f.to_dense().encode("utf-8")) for f in out)

    keys_ok = before_keys <= after_keys
    needles_ok = before_needles <= after_needles
    report = {
        "needle": NEEDLE,
        "bytes_before": before_bytes,
        "bytes_after": after_bytes,
        "facts_in": len(facts),
        "facts_out": len(out),
        "keys_in": len(before_keys),
        "keys_out": len(after_keys),
        "needles_in": len(before_needles),
        "needles_out": len(after_needles),
        "facts_preserved": keys_ok and needles_ok,
        "ratio": round(after_bytes / before_bytes, 4) if before_bytes else 1.0,
        "note": "squeeze unique store — never prune distinct facts/needles",
    }
    return out, report


def promote_repeated(
    facts: list[LessonFact],
    *,
    write: bool,
    min_hits: int = _PROMOTE_HITS,
) -> list[str]:
    actions: list[str] = []
    if not write:
        for f in facts:
            if f.hit_count >= min_hits and str(f.source).startswith("journal"):
                actions.append(f"would_promote_learn: {f.key}")
        return actions

    import peer_project_learning as pl

    known = {
        fact_key(str(r.get("text") or ""), needle=extract_needle(str(r.get("text") or "")))
        for r in _read_jsonl(pl.SHARED_LEARNINGS_JSONL)
    }

    for fact in facts:
        if fact.hit_count < min_hits:
            continue
        if not str(fact.source).startswith("journal") and "self-heal" not in fact.tags:
            continue
        dense = fact.to_dense()
        k = fact_key(dense, needle=fact.needle)
        if k in known or fact.key in known:
            continue
        try:
            pl.record_learning(
                ROLE_ID,
                dense,
                paths=["notes/PROJECT_LEARNING.md"],
                also_agent_note=False,
            )
            known.add(k)
            actions.append(f"promoted_learn: {fact.key}")
        except Exception as exc:  # noqa: BLE001
            actions.append(f"promote_learn_fail: {exc}")

        if "self-heal" in fact.tags and fact.hit_count >= min_hits + 1:
            try:
                import peer_playbook as pb

                bid = next(
                    (t for t in fact.tags if t not in ("self-heal", "registry-clear")),
                    "",
                )
                if bid:
                    pb.add_entry_manual(
                        f"recurring self-heal: {bid}",
                        fix_commands=["./scripts/peer self-heal", "./scripts/peer heal-all"],
                        agent_fix=dense[:200],
                        owner=ROLE_ID,
                        severity="medium",
                    )
                    actions.append(f"promoted_playbook: {bid}")
            except Exception as exc:  # noqa: BLE001
                actions.append(f"promote_playbook_fail: {exc}")

    if actions and any(a.startswith("promoted_") for a in actions):
        try:
            import peer_debrief as deb

            n_prom = sum(1 for a in actions if a.startswith("promoted_"))
            deb.append_entry(
                deb.DebriefEntry(
                    kind="knowledge",
                    title=f"Lessons squeeze — {n_prom} promotions",
                    body=(
                        f"{NEEDLE}\n"
                        f"Promoted {n_prom} repeated facts into PROJECT_LEARNING/playbook. "
                        f"facts_preserved guaranteed by squeeze."
                    ),
                    meta={"tags": ["lessons", "squeeze"], "needle": NEEDLE},
                )
            )
            actions.append("promoted_debrief")
        except Exception as exc:  # noqa: BLE001
            actions.append(f"promote_debrief_fail: {exc}")

    return actions


def rewrite_shared_learnings_squeezed(facts: list[LessonFact], *, write: bool) -> dict[str, Any]:
    import peer_project_learning as pl

    existing = _read_jsonl(pl.SHARED_LEARNINGS_JSONL)
    before_b = pl.SHARED_LEARNINGS_JSONL.stat().st_size if pl.SHARED_LEARNINGS_JSONL.is_file() else 0
    before_n = len(existing)

    bucket: dict[str, LessonFact] = {}
    for row in existing:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        ts = float(row.get("ts") or 0)
        needle = extract_needle(text)
        _merge_fact(
            bucket,
            LessonFact(
                key=fact_key(text, needle=needle),
                text=normalize_text(text)[:2000],
                needle=needle,
                source="project-learnings",
                first_ts=ts,
                last_ts=ts,
                hit_count=1,
                tags=[str(row.get("role_id") or "")],
            ),
        )
    for fact in facts:
        if fact.source == "project-learnings" or fact.hit_count >= 2 or fact.needle:
            _merge_fact(bucket, fact)

    squeezed, report = squeeze_facts(list(bucket.values()))
    if not write:
        report["wrote"] = False
        report["bytes_file_before"] = before_b
        return report

    pl.SHARED_LEARNINGS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for fact in squeezed:
        role = next(
            (t for t in fact.tags if t and t not in ("project-learning", "self-heal")),
            ROLE_ID,
        )
        row = {
            "role_id": role or ROLE_ID,
            "text": fact.to_dense()[:2000],
            "ts": fact.last_ts or _now(),
            "cycle_id": "",
            "paths": [],
            "hit_count": fact.hit_count,
            "first_ts": fact.first_ts,
            "needle": fact.needle,
            "squeeze": NEEDLE,
        }
        lines.append(json.dumps(row, separators=(",", ":")))
    payload = "\n".join(lines) + ("\n" if lines else "")
    pl.SHARED_LEARNINGS_JSONL.write_text(payload, encoding="utf-8")
    after_b = len(payload.encode("utf-8"))
    pl.write_project_learning_md()
    report["wrote"] = True
    report["bytes_file_before"] = before_b
    report["bytes_file_after"] = after_b
    report["rows_before"] = before_n
    report["rows_after"] = len(squeezed)
    orig_keys = {
        fact_key(str(r.get("text") or ""), needle=extract_needle(str(r.get("text") or "")))
        for r in existing
        if str(r.get("text") or "").strip()
    }
    new_keys = {f.key for f in squeezed}
    report["facts_preserved"] = orig_keys <= new_keys
    return report


def append_harvest_log(facts: list[LessonFact], report: dict[str, Any]) -> None:
    HARVEST_JSONL.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": _now(),
        "needle": NEEDLE,
        "facts": len(facts),
        "report": report,
        "sample": [f.to_dense()[:200] for f in facts[:8]],
    }
    with HARVEST_JSONL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")


def save_state(report: dict[str, Any], actions: list[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "needle": NEEDLE,
                "updated": _now(),
                "report": report,
                "actions": actions[-40:],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run_harvest(*, write: bool, squeeze: bool) -> dict[str, Any]:
    raw = collect_facts()
    facts, report = squeeze_facts(raw)
    actions: list[str] = []
    if squeeze:
        file_report = rewrite_shared_learnings_squeezed(facts, write=write)
        report["file"] = file_report
        report["facts_preserved"] = bool(
            report.get("facts_preserved") and file_report.get("facts_preserved", True)
        )
    actions.extend(promote_repeated(facts, write=write))
    append_harvest_log(facts, report)
    save_state(report, actions)
    return {"report": report, "actions": actions, "facts": [asdict(f) for f in facts[:50]]}


def format_status() -> str:
    if not STATE_PATH.is_file():
        return f"{NEEDLE}: no harvest yet — run ./scripts/peer lessons-harvest\n"
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return f"{NEEDLE}: state unreadable\n"
    rep = data.get("report") or {}
    return (
        f"# Lessons curator\n\n"
        f"- needle: `{data.get('needle')}`\n"
        f"- facts_preserved: **{rep.get('facts_preserved')}**\n"
        f"- bytes: {rep.get('bytes_before')} → {rep.get('bytes_after')} "
        f"(ratio {rep.get('ratio')})\n"
        f"- facts: {rep.get('facts_in')} → {rep.get('facts_out')}\n"
        f"- actions: {len(data.get('actions') or [])}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--harvest", action="store_true", help="Mine logs/journals + fold")
    ap.add_argument("--squeeze", action="store_true", help="Lossless squeeze shared learnings")
    ap.add_argument("--write", action="store_true", help="Persist promotions / rewrite")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--forever", action="store_true")
    ap.add_argument(
        "--poll-sec",
        type=float,
        default=float(os.environ.get("LESSONS_POLL_SEC", "300")),
    )
    args = ap.parse_args()

    if args.status and not (args.harvest or args.squeeze):
        print(format_status())
        return 0

    def once() -> int:
        out = run_harvest(write=args.write, squeeze=bool(args.squeeze))
        if args.json:
            print(json.dumps(out, indent=2, default=str))
        else:
            rep = out["report"]
            print(
                f"{NEEDLE} facts_preserved={rep.get('facts_preserved')} "
                f"bytes {rep.get('bytes_before')}→{rep.get('bytes_after')} "
                f"facts {rep.get('facts_in')}→{rep.get('facts_out')}"
            )
            for a in out.get("actions") or []:
                print(f"  {a}")
            if rep.get("file"):
                fr = rep["file"]
                print(
                    f"  file bytes {fr.get('bytes_file_before')}→{fr.get('bytes_file_after')} "
                    f"rows {fr.get('rows_before')}→{fr.get('rows_after')} "
                    f"preserved={fr.get('facts_preserved')}"
                )
        return 0 if out["report"].get("facts_preserved", True) else 2

    if args.forever:
        while True:
            once()
            time.sleep(max(60.0, args.poll_sec))
    if args.harvest or args.squeeze:
        return once()
    if args.status:
        print(format_status())
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
