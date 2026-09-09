#!/usr/bin/env python3
"""Expected vs actual output — discrepancy detection for every agent.

Agents must state expected output before running verify/commands, then compare
side-by-side with actual output. Any mismatch → investigate before DONE.

Usage:
  python3 scripts/peer_output_compare.py --write
  python3 scripts/peer_output_compare.py --block --role verify_runner
  python3 scripts/peer_output_compare.py --compare --expected "ok" --actual "fail"
  ./scripts/peer output-compare --compare --expected-file want.txt --actual-file got.txt
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

OUTPUT_COMPARE_MD = ROOT / "notes" / "OUTPUT_COMPARE.md"
COMPARE_JSONL = auto.CONFIG_DIR / "output-compare.jsonl"

# OVERSEER_OUTPUT_COMPARE_NO_BAD_ESCAPE_2026_09_04
OUTPUT_COMPARE_MANDATE = """**Expected vs actual** — mandatory discrepancy check (every cycle):

Before you declare success, **write both columns** and diff them. Do not skip because you "feel" it worked.

| Step | Rule |
|------|------|
| **Expect** | Before verify/command: state `{exit, key lines, metric}` you expect. |
| **Run** | Execute the narrowest command/test; capture **full** exit code + stderr/stdout tail. |
| **Compare** | Side-by-side: Expected | Actual — line-by-line for failures. |
| **Discrepancy** | Any mismatch → root-cause before more edits; post GLink BLOCK if unexplained. |
| **DONE** | GLink payload includes `expected_vs_actual: match | discrepancy + summary`. |"""

COMPARE_WORKFLOW = """**Compare workflow (after every verify / test / script):**

```
1. Write expected (1–3 lines): exit code + substring or metric
2. Run command → capture actual exit + last 20 lines output
3. ./scripts/peer output-compare --compare --expected "..." --actual "..."
4. If discrepancy → read first diff hunk → pinpoint → fix → re-compare
5. Only DONE when compare reports MATCH (or discrepancy explained + filed)
```"""

COMPARE_QUESTIONS: tuple[str, ...] = (
    "What **exact** output do I expect (exit code + key lines or metric) after my change?",
    "Did I run the command and capture **actual** output myself — not assume from memory?",
    "Expected vs actual side-by-side — what lines differ? (paste or `./scripts/peer output-compare`)",
    "If discrepancy exists: is it env/flake, wrong fix, or wrong expectation — which one?",
    "Before DONE: does actual output match what I promised in Plan — yes or no with evidence?",
)

NICHE_COMPARE: dict[str, tuple[str, ...]] = {
    "verify_runner": (
        "Expected: verify exit 0 + self-check OK — actual: paste first failing line if not.",
        "Compare unittest summary line expected vs actual (Ran N tests / FAILED).",
    ),
    "factory_engineer": (
        "Expected: self-check + targeted test green — compare dispatch metric before/after.",
    ),
    "adapt_specialist": (
        "Expected: audit clean or listed findings — compare `--audit` output to expectation.",
    ),
    "queue_steward": (
        "Expected: drift=0 between WORK_QUEUE and self_improve_context — diff the pair.",
    ),
    "communications_engineer": (
        "Expected: byte/token count — compare measure before vs after on hot path.",
    ),
    "compression_engineer": (
        "Expected: RSS MB delta — compare ram-status snapshot before vs after.",
    ),
    "safety_auditor": (
        "Expected: PASS or BLOCK with gate ids — actual review must match stated tier.",
    ),
    "command_builder": (
        "Expected: compound exit 0 — compare `./scripts/peer commands-sync` output.",
    ),
    "orchestrator": (
        "Expected: N peers DONE + verify green — compare GLink bus vs plan task list.",
    ),
}


@dataclass(frozen=True)
class CompareResult:
    match: bool
    expected: str
    actual: str
    summary: str
    diff_lines: tuple[str, ...]

    def format_report(self) -> str:
        status = "MATCH" if self.match else "DISCREPANCY"
        lines = [
            f"## Output compare — {status}",
            "",
            f"**Summary:** {self.summary}",
            "",
            "**Expected:**",
            "```",
            self.expected.rstrip() or "(empty)",
            "```",
            "",
            "**Actual:**",
            "```",
            self.actual.rstrip() or "(empty)",
            "```",
        ]
        if self.diff_lines:
            lines.extend(["", "**Diff (expected → actual):**", "```diff"])
            lines.extend(self.diff_lines)
            lines.append("```")
        return "\n".join(lines)


def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _read_arg(value: str) -> str:
    raw = str(value or "")
    if raw.startswith("@"):
        path = Path(raw[1:]).expanduser()
        return path.read_text(encoding="utf-8", errors="replace")
    return raw


def compare_outputs(expected: str, actual: str) -> CompareResult:
    """Line-oriented compare — returns match flag + unified diff hunks."""
    exp = _normalize_text(expected)
    act = _normalize_text(actual)
    if exp == act:
        return CompareResult(
            match=True,
            expected=exp,
            actual=act,
            summary="Expected and actual match exactly.",
            diff_lines=(),
        )
    exp_lines = exp.splitlines() or [""]
    act_lines = act.splitlines() or [""]
    diff = list(
        difflib.unified_diff(
            exp_lines,
            act_lines,
            fromfile="expected",
            tofile="actual",
            lineterm="",
        )
    )
    summary = f"{len(diff)} diff line(s); first change at hunk header or line mismatch."
    if not diff and exp != act:
        summary = "Texts differ (whitespace-normalized mismatch)."
    return CompareResult(
        match=False,
        expected=exp,
        actual=act,
        summary=summary,
        diff_lines=tuple(diff[:40]),
    )


def compare_exit_and_output(
    *,
    expected_exit: int,
    actual_exit: int,
    expected_output: str = "",
    actual_output: str = "",
) -> CompareResult:
    exp_parts = [f"exit={expected_exit}"]
    act_parts = [f"exit={actual_exit}"]
    if expected_output.strip():
        exp_parts.append(expected_output.strip())
    if actual_output.strip():
        act_parts.append(actual_output.strip())
    result = compare_outputs("\n".join(exp_parts), "\n".join(act_parts))
    if actual_exit != expected_exit and result.match:
        return CompareResult(
            match=False,
            expected=result.expected,
            actual=result.actual,
            summary=f"Exit code mismatch: expected {expected_exit}, got {actual_exit}.",
            diff_lines=result.diff_lines,
        )
    if actual_exit != expected_exit:
        summary = f"Exit code mismatch: expected {expected_exit}, got {actual_exit}. {result.summary}"
        return CompareResult(
            match=False,
            expected=result.expected,
            actual=result.actual,
            summary=summary,
            diff_lines=result.diff_lines,
        )
    return result


def run_command_capture(cmd: str | list[str], *, cwd: Path | None = None) -> tuple[int, str]:
    if isinstance(cmd, str):
        argv = cmd if cmd.strip().startswith("[") else cmd.split()
    else:
        argv = list(cmd)
    proc = subprocess.run(
        argv,
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    tail = "\n".join(combined.splitlines()[-20:])
    return proc.returncode, tail


def base_role_id(role_id: str) -> str:
    rid = str(role_id or "").strip()
    m = re.match(r"^(.+)_L\d+$", rid)
    return m.group(1) if m else rid


def format_niche_compare(role_id: str) -> str:
    base = base_role_id(role_id)
    tips = NICHE_COMPARE.get(base, ())
    if not tips:
        return "- State expected verify output before run; diff actual before DONE."
    return "\n".join(f"- {t}" for t in tips)


def format_output_compare_block(*, role_id: str | None = None) -> str:
    lines = [
        "## Expected vs actual (discrepancy check)",
        "",
        OUTPUT_COMPARE_MANDATE,
        "",
        COMPARE_WORKFLOW,
        "",
        "**Compare questions (answer before DONE):**",
        "",
    ]
    for i, q in enumerate(COMPARE_QUESTIONS, 1):
        lines.append(f"{i}. {q}")
    if role_id:
        lines.extend(["", "**Niche compare focus:**", format_niche_compare(role_id), ""])
    lines.append(
        "_Tool:_ `./scripts/peer output-compare --compare --expected \"...\" --actual \"...\"` "
        "or `--expected-file` / `--actual-file`."
    )
    return "\n".join(lines).strip()


def record_discrepancy(
    role_id: str,
    *,
    expected: str,
    actual: str,
    note: str = "",
) -> None:
    result = compare_outputs(expected, actual)
    text = (
        f"output-compare: {'match' if result.match else 'discrepancy'} — "
        f"{note or result.summary}"[:400]
    )
    try:
        import peer_project_learning as pl

        pl.record_learning(role_id, text, also_agent_note=True)
    except Exception:  # noqa: BLE001
        COMPARE_JSONL.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "role_id": role_id,
            "match": result.match,
            "expected": expected[:500],
            "actual": actual[:500],
            "note": note,
            "ts": time.time(),
        }
        with COMPARE_JSONL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")


def write_output_compare_md() -> Path:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines = [
        "# Expected vs actual — output discrepancy check",
        "",
        f"_Updated {now}_ · every agent · compare before DONE",
        "",
        OUTPUT_COMPARE_MANDATE,
        "",
        COMPARE_WORKFLOW,
        "",
        "## Compare questions",
        "",
    ]
    for i, q in enumerate(COMPARE_QUESTIONS, 1):
        lines.append(f"{i}. {q}")
    lines.extend(["", "## Niche compare focus", ""])
    for rid in sorted(NICHE_COMPARE):
        title = rid.replace("_", " ").title()
        lines.append(f"### {title}")
        lines.append(format_niche_compare(rid))
        lines.append("")
    OUTPUT_COMPARE_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_COMPARE_MD.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return OUTPUT_COMPARE_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Expected vs actual output compare")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--block", action="store_true")
    parser.add_argument("--role", default="")
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--expected", default="")
    parser.add_argument("--actual", default="")
    parser.add_argument("--expected-file", default="")
    parser.add_argument("--actual-file", default="")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--note", default="")
    parser.add_argument("--run", default="", help="Run command; use with --expect-exit")
    parser.add_argument("--expect-exit", type=int, default=0)
    args = parser.parse_args()

    if args.record:
        if not args.role or not (args.expected or args.expected_file) or not (
            args.actual or args.actual_file
        ):
            print(
                "output-compare --record requires --role, expected, and actual",
                file=sys.stderr,
            )
            return 1
        exp = _read_arg(args.expected_file or args.expected)
        act = _read_arg(args.actual_file or args.actual)
        record_discrepancy(args.role, expected=exp, actual=act, note=args.note)
        print(f"recorded compare for {args.role}")
        return 0

    if args.compare or args.run:
        if args.run:
            rc, tail = run_command_capture(args.run)
            exp = f"exit={args.expect_exit}"
            act = f"exit={rc}\n{tail}"
            result = compare_exit_and_output(
                expected_exit=args.expect_exit,
                actual_exit=rc,
                expected_output="",
                actual_output=tail,
            )
        else:
            exp = _read_arg(args.expected_file or args.expected)
            act = _read_arg(args.actual_file or args.actual)
            if not exp and not act:
                print("output-compare --compare requires --expected and --actual", file=sys.stderr)
                return 1
            result = compare_outputs(exp, act)
        print(result.format_report())
        return 0 if result.match else 2

    if args.block:
        print(format_output_compare_block(role_id=args.role or None))
        return 0

    path = write_output_compare_md()
    print(f"output-compare: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
