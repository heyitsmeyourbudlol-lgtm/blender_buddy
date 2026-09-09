#!/usr/bin/env python3
"""Lock WQ↔SIC Active opens: Newdrop-after-tip + kit-run + T10-04. Scratch only."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path("/Users/togi/Automation")
WQ = ROOT / "notes/WORK_QUEUE.md"
SIC = ROOT / "scripts/self_improve_context.md"


def tip_number() -> int:
    out = subprocess.check_output(
        [
            "gh",
            "pr",
            "list",
            "-R",
            "heyitsmeyourbudlol-lgtm/caas-changelog",
            "--state",
            "merged",
            "--limit",
            "1",
            "--json",
            "number",
            "-q",
            ".[0].number",
        ],
        text=True,
    ).strip()
    return int(out)


def active_bounds(lines: list[str]) -> tuple[int, int]:
    a0 = a1 = None
    for i, line in enumerate(lines):
        if line.startswith("## Active"):
            a0 = i
        elif a0 is not None and a1 is None and line.startswith("## "):
            a1 = i
            break
    if a0 is None:
        raise SystemExit("no Active section")
    if a1 is None:
        a1 = len(lines)
    return a0, a1


def build_opens(tip: int) -> list[str]:
    newdrop = (
        f"- [ ] **[top10] Newdrop production — next meaningful non-UI merge** — after #{tip}; "
        "file-scoped `/Users/togi/CaaS`; verify `npm test` + `check:controls`; "
        "**no UI unless flaw**; prefer backend/security/ops; done=PR merged; "
        "update EXTERNAL_PROOF + FACTORY_PROOF + scoreboard. "
        "Tasks: `notes/TOP10_PRODUCTION_POWER_TASKS.md`\n"
    )
    kit = (
        "- [ ] **[factory] Kit-run fifteenth registry target** — pick next Mac `.git` "
        "(CyberActivity — empty repo seed + origin if needed; not CPT/Doc2Api/battery/browser/"
        "falcon-ai/MATTERNTHREAD/deepseek-cursor-proxy/Newdrop/RAM/Hub/Terminal/F.I.R.E./"
        "Marketplace/SaaS/News); `./scripts/peer kit-run` A→E; writeback proof; Mac `gh` for PR; NO PAY\n"
    )
    t10 = (
        "- [ ] **[top10] TOP10_NEXT T10-04 non-noop ≥8/day** — partial 2026-09-08 restamp 04:27Z: "
        "observational only · free-desktop verify quiet + clear-deferred in-place still held · "
        "measured **7 today · proj 37.7/day · week_avg 7.0 [GAP]** `meets_bar=false` "
        "(proj alone no longer false-PASS); CLEAN peer+improve **active**; "
        "keep open until ≥8 observed/day; NO PAY — `notes/TOP10_NEXT.md` · needles "
        "`OVERSEER_T10_04_FREE_DESKTOP_VERIFY_QUIET_2026_09_08` · "
        "`OVERSEER_T10_04_CLEAR_DEFERRED_NO_LOCAL_ONLY_2026_09_08`\n"
    )
    return [newdrop, kit, t10]


def rewrite(path: Path, tip: int, with_remaining: bool) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    a0, a1 = active_bounds(lines)
    body = lines[a0 + 1 : a1]
    closed: list[str] = []
    for line in body:
        s = line.rstrip("\n")
        if s.startswith("- [x]"):
            closed.append(s + "\n")
    opens = build_opens(tip)
    rest = lines[a1:]
    out_rest: list[str] = []
    i = 0
    while i < len(rest):
        if rest[i].startswith("## Remaining work"):
            i += 1
            while i < len(rest) and not rest[i].startswith("## "):
                i += 1
            continue
        out_rest.append(rest[i])
        i += 1
    text = "".join(["## Active\n", *opens, *closed, *out_rest])
    if with_remaining:
        text = text.rstrip() + "\n\n## Remaining work (priority order)\n" + "".join(opens) + "\n"
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path}")


def main() -> None:
    tip = tip_number()
    print(f"tip={tip}")
    rewrite(WQ, tip, with_remaining=False)
    rewrite(SIC, tip, with_remaining=True)
    for path in (WQ, SIC):
        opens = []
        ina = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## Active"):
                ina = True
                continue
            if ina and line.startswith("## "):
                break
            if ina and line.startswith("- [ ]"):
                opens.append(line)
        print(path.name, "opens", len(opens))
        for line in opens:
            print(" ", line[:120])


if __name__ == "__main__":
    main()
