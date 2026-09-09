#!/usr/bin/env python3
"""Anti-amnesia quiz harness — SoT needle recall checks (mechanical).

Needle: OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07

Quizzes fixture/pack SoT needles. Fail → suggest heal / Hot refresh.
Free desktop only — no paid spawn.

Usage:
  python3 scripts/peer_memory_quiz.py --self-check
  python3 scripts/peer_memory_quiz.py --answer active_open_count=0 --answer no_pay=ok
  ./scripts/peer memory-quiz
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import peer_fact_librarian as fl  # noqa: E402
import peer_memory_compress as pmc  # noqa: E402
import peer_memory_span as ms  # noqa: E402

NEEDLE = "OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07"
NO_PAY = ms.NO_PAY_HOT_LINE
HEAL_HINT = (
    "Quiz FAIL — refresh Hot + pack: `./scripts/peer memory` · "
    "`./scripts/peer memory-compress-verify` · `./scripts/peer heal-all` · "
    "open `notes/AGENT_WORKING_MEMORY.md`"
)


def _read(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _active_open_count() -> int:
    text = _read("notes/WORK_QUEUE.md")
    in_active = False
    n = 0
    for line in text.splitlines():
        if line.startswith("## Active"):
            in_active = True
            continue
        if in_active and line.startswith("## "):
            break
        if in_active and line.strip().startswith("- [ ]"):
            n += 1
    return n


def _pack_exists() -> bool:
    return (pmc.ARTIFACT_DIR / pmc.DEFAULT_PACK_NAME).is_file()


def _domain_owners_for_path(sample: str = "scripts/peer_loop.py") -> str | None:
    for d in fl.list_domains():
        if fl.path_in_domain(sample, d):
            return str(d.get("id") or "")
    return None


QuizFn = Callable[[], dict[str, Any]]


def _q_no_pay() -> dict[str, Any]:
    text = _read("AGENTS.md") + "\n" + _read("notes/AGENT_WORKING_MEMORY.md")
    ok = "never paid" in text.lower() or "no pay" in text.lower() or "NO PAY" in text
    return {
        "id": "no_pay",
        "prompt": "Does Always-read / AGENTS enforce NO PAY (free desktop only)?",
        "expected": "yes — free desktop/local/CLEAN only",
        "actual": "present" if ok else "missing",
        "ok": ok,
    }


def _q_active_open() -> dict[str, Any]:
    n = _active_open_count()
    return {
        "id": "active_open_count",
        "prompt": "How many open (- [ ]) items under ## Active in WORK_QUEUE?",
        "expected": str(n),
        "actual": str(n),
        "ok": True,  # self-check always knows; grading uses --answer
        "value": n,
    }


def _q_pack_additive() -> dict[str, Any]:
    text = (
        _read("notes/SOP_LOSSLESS_MEMORY_COMPRESSION.md")
        + "\n"
        + _read("notes/AGENT_WORKING_MEMORY.md")
        + "\n"
        + _read("AGENTS.md")
    )
    ok = (
        "additive" in text.lower()
        and ("never delete" in text.lower() or "do not delete" in text.lower() or "pack is additive" in text.lower())
    ) or ("pack" in text.lower() and "live SoT" in text)
    # Softer: working memory says never delete live SoT
    if "never delete live SoT" in text or "never delete live sot" in text.lower():
        ok = True
    if "pack is additive" in text.lower() or "additive archive" in text.lower():
        ok = True
    return {
        "id": "pack_additive",
        "prompt": "Is the memory pack additive-only (never delete live SoT)?",
        "expected": "yes — additive archive only",
        "actual": "present" if ok else "missing",
        "ok": ok,
    }


def _q_always_read() -> dict[str, Any]:
    text = _read("notes/AGENT_WORKING_MEMORY.md")
    need = [
        "notes/AGENT_WORKING_MEMORY.md",
        "notes/WORK_QUEUE.md",
        "AGENTS.md",
    ]
    missing = [p for p in need if p not in text]
    # Working memory is the index — it should list the others
    listed = "WORK_QUEUE" in text and "AGENTS" in text
    return {
        "id": "always_read",
        "prompt": "Does AGENT_WORKING_MEMORY list Always-read SoT paths?",
        "expected": "WORK_QUEUE + AGENTS (+ peers)",
        "actual": "listed" if listed else f"missing:{missing}",
        "ok": listed,
    }


def _q_fact_query() -> dict[str, Any]:
    text = _read("notes/AGENT_WORKING_MEMORY.md") + "\n" + _read("notes/SOP_AGENT_REMEMBRANCE.md")
    ok = "fact-query" in text
    return {
        "id": "fact_query",
        "prompt": "Is `./scripts/peer fact-query` documented as the fact path?",
        "expected": "yes",
        "actual": "present" if ok else "missing",
        "ok": ok,
    }


def _q_domain_sme() -> dict[str, Any]:
    did = _domain_owners_for_path("scripts/peer_loop.py")
    ok = did is not None
    return {
        "id": "domain_peer_loop",
        "prompt": "Which domain SME owns scripts/peer_loop.py?",
        "expected": did or "peer_runtime/peer_loop",
        "actual": did or "none",
        "ok": ok,
        "value": did,
    }


def _q_pack_present() -> dict[str, Any]:
    ok = _pack_exists()
    return {
        "id": "pack_present",
        "prompt": "Does notes/memory_artifacts/repo_memory_pack.json.z exist?",
        "expected": "yes",
        "actual": "yes" if ok else "no",
        "ok": ok,
    }


def _q_prefer_librarian() -> dict[str, Any]:
    prefer, why = fl.should_prefer_librarian()
    return {
        "id": "prefer_librarian",
        "prompt": "Should main agent prefer Fact Librarian (pack threshold)?",
        "expected": str(prefer).lower(),
        "actual": f"{prefer} — {why}",
        "ok": True,
        "value": prefer,
        "why": why,
    }


QUIZ_BANK: list[QuizFn] = [
    _q_no_pay,
    _q_active_open,
    _q_pack_additive,
    _q_always_read,
    _q_fact_query,
    _q_domain_sme,
    _q_pack_present,
    _q_prefer_librarian,
]


def run_self_check() -> dict[str, Any]:
    rows = [fn() for fn in QUIZ_BANK]
    # Self-check: structural SoT presence questions must pass;
    # value-reporting questions (active_open, prefer_librarian) always ok=True.
    hard = [r for r in rows if r["id"] not in {"active_open_count", "prefer_librarian"}]
    failed = [r for r in hard if not r.get("ok")]
    return {
        "mode": "self-check",
        "needle": NEEDLE,
        "no_pay": NO_PAY,
        "ok": not failed,
        "passed": len(hard) - len(failed),
        "failed": len(failed),
        "total_hard": len(hard),
        "rows": rows,
        "heal_hint": None if not failed else HEAL_HINT,
    }


def grade_answers(answers: dict[str, str]) -> dict[str, Any]:
    """Grade agent-provided answers against live SoT."""
    truth = {r["id"]: r for r in (fn() for fn in QUIZ_BANK)}
    rows: list[dict[str, Any]] = []
    failed = 0
    for qid, ans in answers.items():
        t = truth.get(qid)
        if t is None:
            rows.append(
                {
                    "id": qid,
                    "ok": False,
                    "answer": ans,
                    "expected": None,
                    "note": "unknown question id",
                }
            )
            failed += 1
            continue
        expected = t.get("value", t.get("expected"))
        ok = _answers_match(qid, ans, t)
        if not ok:
            failed += 1
        rows.append(
            {
                "id": qid,
                "ok": ok,
                "answer": ans,
                "expected": expected,
                "prompt": t.get("prompt"),
            }
        )
    return {
        "mode": "grade",
        "needle": NEEDLE,
        "no_pay": NO_PAY,
        "ok": failed == 0 and bool(answers),
        "passed": len(answers) - failed,
        "failed": failed,
        "rows": rows,
        "heal_hint": None if failed == 0 else HEAL_HINT,
    }


def _answers_match(qid: str, ans: str, truth: dict[str, Any]) -> bool:
    a = (ans or "").strip().lower()
    if qid == "active_open_count":
        try:
            digits = re.sub(r"[^0-9-]", "", a)
            got = int(digits) if digits not in {"", "-"} else None
            want = truth.get("value")
            if want is None:
                want = -1
            return got is not None and int(got) == int(want)
        except (TypeError, ValueError):
            return False
    if qid == "prefer_librarian":
        want = bool(truth.get("value"))
        if a in {"1", "true", "yes", "y", "prefer", "prefer_librarian"}:
            return want is True
        if a in {"0", "false", "no", "n"}:
            return want is False
        return a == str(want).lower()
    if qid == "domain_peer_loop":
        want = str(truth.get("value") or truth.get("expected") or "").lower()
        return want in a or a in want
    if qid in {"no_pay", "pack_additive", "always_read", "fact_query", "pack_present"}:
        if a in {"yes", "y", "true", "ok", "pass", "present", "1"}:
            return bool(truth.get("ok"))
        if a in {"no", "n", "false", "fail", "missing", "0"}:
            return not bool(truth.get("ok"))
        # free-text: accept if expected keywords appear
        exp = str(truth.get("expected") or "").lower()
        return any(tok in a for tok in exp.split() if len(tok) > 3) or a == exp
    return a == str(truth.get("expected") or "").lower()


def format_report(result: dict[str, Any]) -> str:
    lines = [
        "## Anti-amnesia quiz",
        f"- Mode: {result.get('mode')}",
        f"- Needle: `{result.get('needle')}`",
        f"- {NO_PAY}",
        f"- Passed={result.get('passed')} Failed={result.get('failed')}",
        "",
    ]
    for row in result.get("rows") or []:
        mark = "PASS" if row.get("ok") else "FAIL"
        lines.append(
            f"- **{mark}** `{row.get('id')}` — {row.get('prompt') or ''}"
        )
        if row.get("expected") is not None:
            lines.append(f"  expected={row.get('expected')} actual/answer={row.get('actual', row.get('answer'))}")
    hint = result.get("heal_hint")
    if hint:
        lines.extend(["", f"**Heal:** {hint}"])
    lines.append("")
    lines.append(f"Result: {'PASS' if result.get('ok') else 'FAIL'}")
    return "\n".join(lines) + "\n"


def list_questions() -> list[dict[str, Any]]:
    return [
        {"id": r["id"], "prompt": r["prompt"], "expected_hint": r.get("expected")}
        for r in (fn() for fn in QUIZ_BANK)
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Anti-amnesia SoT quiz harness")
    ap.add_argument("--self-check", action="store_true", help="Verify SoT needles present")
    ap.add_argument(
        "--answer",
        action="append",
        default=[],
        help="Grade answer id=value (repeatable)",
    )
    ap.add_argument("--list", action="store_true", help="List question ids")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.list:
        qs = list_questions()
        if args.json:
            print(json.dumps(qs, indent=2))
        else:
            for q in qs:
                print(f"{q['id']}: {q['prompt']}")
        return 0

    if args.answer:
        answers: dict[str, str] = {}
        for item in args.answer:
            if "=" not in item:
                print(f"bad --answer (want id=value): {item}", file=sys.stderr)
                return 2
            k, v = item.split("=", 1)
            answers[k.strip()] = v.strip()
        result = grade_answers(answers)
    else:
        # Default: self-check
        result = run_self_check()

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(format_report(result), end="")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
