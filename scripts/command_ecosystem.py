#!/usr/bin/env python3
"""Command ecosystem — coverage matrix, raw-script tips, Backlog enqueue.

Needle: OVERSEER_COMMAND_ECOSYSTEM_PLAN_2026_09_07

Implements notes/COMMAND_ECOSYSTEM_PLAN.md phases 0–1 (+ first executable slice):
  - scripts entrypoints ↔ peer command coverage
  - soft tips for raw ``python3 scripts/`` chains
  - top gaps → Backlog (not Active flood)
  - regenerate notes/COMMAND_COVERAGE.md

Usage::
    python3 scripts/command_ecosystem.py --write
    python3 scripts/command_ecosystem.py --enqueue
    python3 scripts/command_ecosystem.py --tips
    ./scripts/peer command-coverage
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent

import sys

sys.path.insert(0, str(SCRIPTS))

import peer_commands as pc  # noqa: E402
import peer_command_builder as cbuilder  # noqa: E402

NEEDLE = "OVERSEER_COMMAND_ECOSYSTEM_PLAN_2026_09_07"
COVERAGE_MD = ROOT / "notes" / "COMMAND_COVERAGE.md"
COVERAGE_JSON = ROOT / "notes" / "command_coverage.json"
WQ = ROOT / "notes" / "WORK_QUEUE.md"
CTX = ROOT / "scripts" / "self_improve_context.md"

# Layer taxonomy (peer command tags should include one of these when possible)
LAYERS = ("life", "dispatch", "dev", "factory-ai", "product", "meta")

LAYER_BY_CATEGORY: dict[str, str] = {
    "compound": "life",
    "agent": "dispatch",
    "factory": "factory-ai",
    "meta": "meta",
    "improve": "dev",
    "health": "life",
    "daemon": "life",
    "worktree": "dispatch",
    "ops": "meta",
    "ram": "life",
    "niche": "factory-ai",
}

SKIP_SCRIPTS = frozenset(
    {
        "__init__",
        "conftest",
        "automation_config",  # library, not a verb
        "project_automation",
        "peer_commands",  # meta registry
    }
)

# Prefix injected into role niche tasks (idempotent)
COMMAND_ECOSYSTEM_PREFIX = (
    "Prefer `./scripts/peer` (`commands-list --pivotal`); "
    "missing recipe → `commands-cycle`. "
)


def _script_is_cli(path: Path) -> bool:
    """True if file looks like an agent-callable CLI entrypoint."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if path.name.startswith("_"):
        return False
    stem = path.stem
    if stem in SKIP_SCRIPTS or stem.startswith("test_"):
        return False
    if 'if __name__ == "__main__"' in text or "argparse" in text:
        return True
    # Shebang + click/typer less common here
    return False


def _argv_script_stems() -> dict[str, list[str]]:
    """Map script stem → list of peer command ids that invoke it."""
    mapping: dict[str, list[str]] = {}
    for cmd in pc.COMMANDS:
        for tok in cmd.argv:
            if not tok.endswith(".py"):
                continue
            p = Path(tok)
            stem = p.stem
            mapping.setdefault(stem, []).append(cmd.id)
        # peer wrapper often hides script — compounds don't list argv scripts
    # Also parse scripts/peer case lines: exec python3 scripts/FOO.py
    peer_sh = ROOT / "scripts" / "peer"
    if peer_sh.is_file():
        try:
            body = peer_sh.read_text(encoding="utf-8", errors="replace")
        except OSError:
            body = ""
        for m in re.finditer(
            r"^\s*([a-z0-9-]+)\)\s+exec python3 (?:\"?\$[A-Z_]*ROOT\"?/)?scripts/([a-zA-Z0-9_]+)\.py",
            body,
            flags=re.M,
        ):
            cmd_id, stem = m.group(1), m.group(2)
            mapping.setdefault(stem, []).append(cmd_id)
        for m in re.finditer(
            r"^\s*([a-z0-9-]+)\)\s+exec python3 scripts/([a-zA-Z0-9_]+)\.py",
            body,
            flags=re.M,
        ):
            cmd_id, stem = m.group(1), m.group(2)
            mapping.setdefault(stem, []).append(cmd_id)
    return mapping


def _log_script_counts() -> Counter[str]:
    text = ""
    for p in (cbuilder.PEER_LOG, cbuilder.IMPROVE_LOG):
        text += cbuilder._log_tail(p) + "\n"
    return Counter(re.findall(r"python3\s+scripts/([a-zA-Z0-9_]+)\.py", text))


def build_coverage() -> dict[str, Any]:
    mapping = _argv_script_stems()
    log_counts = _log_script_counts()
    cli_scripts: list[Path] = sorted(
        p for p in (ROOT / "scripts").glob("*.py") if _script_is_cli(p)
    )
    wrapped: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for path in cli_scripts:
        stem = path.stem
        cmds = sorted(set(mapping.get(stem) or []))
        hits = int(log_counts.get(stem) or 0)
        row = {
            "script": f"scripts/{path.name}",
            "stem": stem,
            "peer_commands": cmds,
            "log_hits": hits,
        }
        if cmds:
            wrapped.append(row)
        else:
            gaps.append(row)

    # Prefer gaps with log hits
    gaps.sort(key=lambda r: (-int(r["log_hits"]), r["stem"]))
    wrapped.sort(key=lambda r: r["stem"])

    # Layer snapshot for registry
    layers: dict[str, list[str]] = {L: [] for L in LAYERS}
    unlayered: list[str] = []
    for cmd in pc.COMMANDS:
        tag_set = set(cmd.tags) | {cmd.category}
        layer = None
        for L in LAYERS:
            if L in cmd.tags or L.replace("-", "_") in cmd.tags:
                layer = L
                break
        if layer is None:
            layer = LAYER_BY_CATEGORY.get(cmd.category)
        if layer and layer in layers:
            layers[layer].append(cmd.id)
        else:
            unlayered.append(cmd.id)

    harvest_gaps = [g.__dict__ for g in cbuilder.probe_gaps()]

    return {
        "needle": NEEDLE,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_cli_scripts": len(cli_scripts),
        "n_wrapped": len(wrapped),
        "n_gaps": len(gaps),
        "wrapped": wrapped,
        "gaps": gaps,
        "layers": layers,
        "unlayered": unlayered,
        "harvest": harvest_gaps,
        "policy": (
            "Agents execute ./scripts/peer <id>; Command Builder adds recipes; "
            "coverage gaps are Backlog candidates — not Active flood."
        ),
    }


def write_coverage_md(cov: dict[str, Any]) -> Path:
    lines = [
        "# Command coverage",
        "",
        f"_Generated {cov['ts']}_ · Needle `{NEEDLE}`",
        "",
        "Agents **execute** `./scripts/peer <id>`. Gaps = CLI scripts without a peer wrapper "
        "(rank by log hits). Plan: `notes/COMMAND_ECOSYSTEM_PLAN.md`.",
        "",
        "## Snapshot",
        "",
        f"- CLI scripts: **{cov['n_cli_scripts']}**",
        f"- Wrapped: **{cov['n_wrapped']}**",
        f"- Unwrapped gaps: **{cov['n_gaps']}**",
        f"- Peer commands: **{len(pc.COMMANDS)}** · compounds: **{len(pc.COMPOUND_STEPS)}**",
        "",
        "## Layers",
        "",
    ]
    for L in LAYERS:
        ids = cov.get("layers", {}).get(L) or []
        lines.append(f"- **{L}** ({len(ids)}): {', '.join(f'`{i}`' for i in ids[:24])}"
                     + ("…" if len(ids) > 24 else ""))
    if cov.get("unlayered"):
        lines.append(
            f"- **unlayered** ({len(cov['unlayered'])}): "
            + ", ".join(f"`{i}`" for i in cov["unlayered"][:20])
        )
    lines.extend(["", "## Top unwrapped gaps (by log hits)", ""])
    top = (cov.get("gaps") or [])[:15]
    if not top:
        lines.append("_No gaps — all CLI scripts have a peer mapping (or none are CLI)._")
    else:
        lines.append("| Script | Log hits | Suggested peer id |")
        lines.append("|--------|----------|-------------------|")
        for g in top:
            sug = g["stem"].replace("_", "-")
            lines.append(
                f"| `{g['script']}` | {g['log_hits']} | `./scripts/peer {sug}` |"
            )
    lines.extend(
        [
            "",
            "## Harvest (Command Builder)",
            "",
        ]
    )
    harvest = cov.get("harvest") or []
    if not harvest:
        lines.append("_No mechanical harvest gaps._")
    else:
        for h in harvest[:8]:
            lines.append(
                f"- **[{h.get('severity')}]** {h.get('title')} — {h.get('suggestion')}"
            )
    lines.extend(
        [
            "",
            "## Workflow",
            "",
            "```bash",
            "./scripts/peer command-coverage   # regenerate this doc",
            "./scripts/peer commands-cycle     # wake Command Builder",
            "./scripts/peer commands-list --pivotal",
            "```",
            "",
        ]
    )
    COVERAGE_MD.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return COVERAGE_MD


def write_coverage(*, enqueue: bool = False, top_n: int = 5) -> dict[str, Any]:
    cov = build_coverage()
    COVERAGE_JSON.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_JSON.write_text(json.dumps(cov, indent=2) + "\n", encoding="utf-8")
    write_coverage_md(cov)
    if enqueue:
        cov["enqueued"] = enqueue_top_gaps(cov, top_n=top_n)
    return cov


def enqueue_top_gaps(cov: dict[str, Any], *, top_n: int = 5) -> list[str]:
    """Append Backlog lines for top unwrapped + harvest gaps (dedupe)."""
    lines_out: list[str] = []
    candidates: list[str] = []
    for g in (cov.get("gaps") or [])[:top_n]:
        if int(g.get("log_hits") or 0) <= 0 and top_n <= 5:
            # still include zero-hit if we need fill — prefer hit>0
            continue
        sug = str(g["stem"]).replace("_", "-")
        candidates.append(
            f"- [ ] **[command-builder] Wrap `{g['script']}`** — "
            f"add `./scripts/peer {sug}` (log_hits={g.get('log_hits', 0)}) — "
            f"Needle `{NEEDLE}`"
        )
    # fill from zero-hit gaps if needed
    if len(candidates) < top_n:
        for g in cov.get("gaps") or []:
            if len(candidates) >= top_n:
                break
            sug = str(g["stem"]).replace("_", "-")
            line = (
                f"- [ ] **[command-builder] Wrap `{g['script']}`** — "
                f"add `./scripts/peer {sug}` (log_hits={g.get('log_hits', 0)}) — "
                f"Needle `{NEEDLE}`"
            )
            if line not in candidates:
                candidates.append(line)
    for h in (cov.get("harvest") or [])[: max(0, top_n - len(candidates))]:
        title = str(h.get("title") or "harvest gap")[:80]
        candidates.append(
            f"- [ ] **[command-builder] {title}** — {h.get('suggestion', '')[:120]} — "
            f"Needle `{NEEDLE}`"
        )

    for path in (WQ, CTX):
        if not path.is_file():
            continue
        body = path.read_text(encoding="utf-8")
        added: list[str] = []
        for line in candidates:
            # dedupe by script or title fragment
            key = line.split("**")[1] if "**" in line else line[:60]
            if key in body:
                continue
            added.append(line)
        if not added:
            continue
        block = "\n".join(added)
        if "## Backlog" in body:
            body = body.replace("## Backlog", f"## Backlog\n{block}", 1)
        else:
            body = body.rstrip() + f"\n\n## Backlog\n{block}\n"
        path.write_text(body, encoding="utf-8")
        lines_out.extend(added)
    return lines_out


def raw_script_tip(text: str) -> str | None:
    """If text looks like a raw python3 scripts/ chain without ./scripts/peer, warn."""
    t = text or ""
    if "python3 scripts/" not in t and "python3  scripts/" not in t:
        return None
    if "./scripts/peer" in t or "scripts/peer " in t:
        return None
    stems = re.findall(r"python3\s+scripts/([a-zA-Z0-9_]+)\.py", t)
    if not stems:
        return None
    return (
        f"raw script chain ({', '.join(stems[:4])}) — prefer ./scripts/peer "
        f"(commands-list --pivotal); missing → commands-cycle"
    )


def self_check_tips() -> list[str]:
    tips: list[str] = []
    tips.append(
        "Command ecosystem: prefer ./scripts/peer — see notes/AGENT_COMMANDS.md · "
        "notes/COMMAND_ECOSYSTEM_PLAN.md · ./scripts/peer command-coverage"
    )
    try:
        if COVERAGE_JSON.is_file():
            cov = json.loads(COVERAGE_JSON.read_text(encoding="utf-8"))
        else:
            cov = build_coverage()
        n_gaps = int(cov.get("n_gaps") or 0)
        hot = [g for g in (cov.get("gaps") or []) if int(g.get("log_hits") or 0) >= 4]
        if hot:
            tips.append(
                f"command-coverage: {len(hot)} hot unwrapped script(s) — "
                f"./scripts/peer commands-cycle (top: {hot[0]['stem']})"
            )
        elif n_gaps > 40:
            tips.append(
                f"command-coverage: {n_gaps} unwrapped CLIs — run command-coverage --enqueue for Backlog"
            )
    except Exception:  # noqa: BLE001
        pass
    try:
        gaps = cbuilder.probe_gaps()
        if gaps:
            tips.append(
                f"Command Builder: {len(gaps)} harvest gap(s) — ./scripts/peer commands-cycle"
            )
    except Exception:  # noqa: BLE001
        pass
    try:
        if DISPATCH_AUDIT_JSON.is_file():
            audit = json.loads(DISPATCH_AUDIT_JSON.read_text(encoding="utf-8"))
            if audit.get("status") in ("improve", "weak"):
                tips.append(
                    f"command-dispatch-audit: {audit.get('status')} "
                    f"(ratio={audit.get('peer_vs_raw_ratio')}) — prefer pre-dispatch/post-cycle"
                )
        promote = mini_app_promote_candidates()
        if int(promote.get("n_candidates") or 0) > 0:
            tips.append(
                f"mini-app-promote: {promote['n_candidates']} candidate(s) — "
                "./scripts/peer commands-cycle"
            )
    except Exception:  # noqa: BLE001
        pass
    return tips


def ensure_niche_task_prefix(task: str) -> str:
    t = (task or "").strip()
    if not t:
        return COMMAND_ECOSYSTEM_PREFIX.strip()
    if "commands-list" in t or "commands-cycle" in t or "Prefer `./scripts/peer`" in t:
        return t
    return COMMAND_ECOSYSTEM_PREFIX + t


DISPATCH_AUDIT_MD = ROOT / "notes" / "COMMAND_DISPATCH_AUDIT.md"
DISPATCH_AUDIT_JSON = ROOT / "notes" / "command_dispatch_audit.json"
HUB_PEER_VERBS_MD = ROOT / "notes" / "HUB_PEER_VERBS.md"


def dispatch_compliance_audit() -> dict[str, Any]:
    """Measure pre-dispatch / post-cycle mentions vs raw agent spawn signals in logs."""
    text = ""
    for p in (cbuilder.PEER_LOG, cbuilder.IMPROVE_LOG):
        text += cbuilder._log_tail(p, max_bytes=120_000) + "\n"
    pre = len(re.findall(r"pre-dispatch|plan-gate", text, flags=re.I))
    post = len(re.findall(r"post-cycle|done-gate", text, flags=re.I))
    raw = len(re.findall(r"python3\s+scripts/", text))
    peer_run = len(re.findall(r"\./scripts/peer\s+[a-z0-9-]+", text))
    ratio = (peer_run / max(1, peer_run + raw)) if (peer_run + raw) else 1.0
    status = "ok" if ratio >= 0.55 or raw < 5 else "improve"
    if pre < 1 and post < 1 and raw > 10:
        status = "weak"
    payload = {
        "needle": NEEDLE,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pre_dispatch_hits": pre,
        "post_cycle_hits": post,
        "raw_python_scripts_hits": raw,
        "peer_command_hits": peer_run,
        "peer_vs_raw_ratio": round(ratio, 3),
        "status": status,
        "hint": (
            "Agents should call ./scripts/peer pre-dispatch before spawn and "
            "post-cycle after land; prefer peer verbs over raw python3 scripts/."
            if status != "ok"
            else "Dispatch/command mix looks healthy in recent log tails."
        ),
    }
    DISPATCH_AUDIT_JSON.parent.mkdir(parents=True, exist_ok=True)
    DISPATCH_AUDIT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Command dispatch audit",
        "",
        f"_Generated {payload['ts']}_ · Needle `{NEEDLE}`",
        "",
        f"**Status:** `{status}` · peer/(peer+raw) ratio = **{payload['peer_vs_raw_ratio']}**",
        "",
        "| Signal | Hits |",
        "|--------|------|",
        f"| pre-dispatch / plan-gate | {pre} |",
        f"| post-cycle / done-gate | {post} |",
        f"| `./scripts/peer …` | {peer_run} |",
        f"| raw `python3 scripts/` | {raw} |",
        "",
        payload["hint"],
        "",
        "```bash",
        "./scripts/peer command-dispatch-audit",
        "./scripts/peer pre-dispatch",
        "./scripts/peer post-cycle",
        "```",
        "",
    ]
    DISPATCH_AUDIT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def mini_app_promote_candidates() -> dict[str, Any]:
    """Registered mini-apps without a peer command → promote to Command Builder."""
    try:
        import peer_agent_mini_apps as ma

        apps = ma.load_registry()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "candidates": []}
    reg = {c.id for c in pc.COMMANDS} | set(pc.COMPOUND_STEPS)
    candidates = []
    for app in apps:
        name = str(app.get("name") or "").strip()
        if not name:
            continue
        sug = name.replace("_", "-")
        if sug in reg or name in reg:
            continue
        candidates.append(
            {
                "name": name,
                "path": app.get("path"),
                "purpose": app.get("purpose"),
                "suggest_peer_id": sug,
                "hint": f"./scripts/peer commands-cycle — wrap scripts/agent_tools/{name}.py as peer {sug}",
            }
        )
    return {
        "ok": True,
        "needle": NEEDLE,
        "n_apps": len(apps),
        "n_candidates": len(candidates),
        "candidates": candidates,
        "policy": "Team-repeated mini-apps must become ./scripts/peer verbs via Command Builder.",
    }


def write_hub_peer_verbs() -> Path:
    """Product-facing hub verbs for Newdrop / external proof."""
    lines = [
        "# Hub peer verbs (product gravity)",
        "",
        f"_Needle `{NEEDLE}`_ · Gravity product: **Newdrop (CaaS)** — `notes/HUB_GRAVITY_CHOICE.md`",
        "",
        "External / product agents should **not** reinvent Automation kit loops.",
        "Run these from the **Automation hub** checkout (or document SSH to CLEAN):",
        "",
        "## Life / dispatch",
        "",
        "| Verb | When |",
        "|------|------|",
        "| `./scripts/peer pre-dispatch` | Before any product agent spawn from hub |",
        "| `./scripts/peer post-cycle` | After land / before DONE claim |",
        "| `./scripts/peer green` | Health gate |",
        "| `./scripts/peer heal-all` | Verify red / mechanical heal |",
        "",
        "## Product / proof",
        "",
        "| Verb | When |",
        "|------|------|",
        "| `./scripts/peer product` | External-proof sprint + registry fanout |",
        "| `./scripts/peer product-status` | Cooldown + queue |",
        "| `./scripts/peer factory-sprint` | Launch external-repo cursor-agent lanes |",
        "| `./scripts/peer progress` | Factory readiness (real outcomes) |",
        "",
        "## Factory AI (local specialists)",
        "",
        "| Verb | When |",
        "|------|------|",
        "| `./scripts/peer niche-mint …` | New closed-world specialist from work gap |",
        "| `./scripts/peer niche-assist-once` | One assist pass on Active head |",
        "| `./scripts/peer factory-dynamics` | CPU/GPU niche balance snapshot |",
        "| `./scripts/peer niche-bank-status` | Bank ready counts |",
        "| `./scripts/peer niche-bank-eval` | Heldout + WQ smoke |",
        "",
        "## Commands ecosystem",
        "",
        "| Verb | When |",
        "|------|------|",
        "| `./scripts/peer commands-list --pivotal` | Discover verbs |",
        "| `./scripts/peer commands-cycle` | Wake Command Builder |",
        "| `./scripts/peer command-coverage` | Coverage matrix |",
        "",
        "## Newdrop note",
        "",
        "Product UI/verify stays **native** (`npm test`, `check:controls`) on the Newdrop repo.",
        "Hub verbs cover factory orchestration + proof lanes — not a second product CLI.",
        "",
        "Link from product AGENTS / AGENT_WORKFLOW: run hub verbs for factory/proof; "
        "keep elegant-statue product work in-repo.",
        "",
    ]
    HUB_PEER_VERBS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return HUB_PEER_VERBS_MD


def orchestrator_command_block() -> str:
    return (
        "## Command ecosystem (mandatory)\n"
        "- Prefer `./scripts/peer <id>` for repetitive work — "
        "`./scripts/peer commands-list --pivotal` / `notes/AGENT_COMMANDS.md`.\n"
        "- Before spawn: `./scripts/peer pre-dispatch`. After land: `./scripts/peer post-cycle`.\n"
        "- If repeating a shell chain or raw `python3 scripts/…`: "
        "`./scripts/peer commands-cycle` (Command Builder) or use an existing id.\n"
        "- Coverage: `./scripts/peer command-coverage` · Plan: `notes/COMMAND_ECOSYSTEM_PLAN.md`.\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Command ecosystem coverage + enqueue")
    ap.add_argument("--write", action="store_true", help="Write COMMAND_COVERAGE.md + JSON")
    ap.add_argument("--enqueue", action="store_true", help="Also enqueue top Backlog gaps")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--tips", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check-text", default="", help="Print raw-script tip for plan text")
    ap.add_argument("--dispatch-audit", action="store_true")
    ap.add_argument("--mini-app-promote", action="store_true")
    ap.add_argument("--hub-verbs", action="store_true", help="Write notes/HUB_PEER_VERBS.md")
    ap.add_argument(
        "--finish",
        action="store_true",
        help="Write coverage + dispatch audit + hub verbs + mini-app promote JSON",
    )
    args = ap.parse_args(argv)

    if args.check_text:
        tip = raw_script_tip(args.check_text)
        print(json.dumps({"tip": tip}))
        return 0
    if args.tips:
        print(json.dumps({"tips": self_check_tips()}, indent=2))
        return 0
    if args.dispatch_audit:
        print(json.dumps(dispatch_compliance_audit(), indent=2))
        return 0
    if args.mini_app_promote:
        print(json.dumps(mini_app_promote_candidates(), indent=2))
        return 0
    if args.hub_verbs:
        path = write_hub_peer_verbs()
        print(f"hub-verbs → {path}")
        return 0

    if args.finish:
        cov = write_coverage(enqueue=False, top_n=args.top)
        write_coverage_md(cov)
        COVERAGE_JSON.write_text(json.dumps(cov, indent=2) + "\n", encoding="utf-8")
        audit = dispatch_compliance_audit()
        promote = mini_app_promote_candidates()
        hub = write_hub_peer_verbs()
        print(
            json.dumps(
                {
                    "coverage": {
                        "wrapped": cov["n_wrapped"],
                        "gaps": cov["n_gaps"],
                    },
                    "dispatch_audit": audit.get("status"),
                    "mini_app_promote": promote.get("n_candidates"),
                    "hub_verbs": str(hub),
                },
                indent=2,
            )
        )
        return 0

    cov = write_coverage(enqueue=args.enqueue, top_n=args.top) if (args.write or args.enqueue) else build_coverage()
    if args.write or args.enqueue:
        write_coverage_md(cov)
        COVERAGE_JSON.write_text(json.dumps(cov, indent=2) + "\n", encoding="utf-8")
    if args.enqueue and "enqueued" not in cov:
        cov["enqueued"] = enqueue_top_gaps(cov, top_n=args.top)
    if args.json or not (args.write or args.enqueue):
        slim = {
            k: cov[k]
            for k in (
                "needle",
                "ts",
                "n_cli_scripts",
                "n_wrapped",
                "n_gaps",
                "enqueued",
            )
            if k in cov
        }
        slim["top_gaps"] = (cov.get("gaps") or [])[:8]
        print(json.dumps(slim, indent=2))
    else:
        print(
            f"command-ecosystem: coverage → {COVERAGE_MD} "
            f"(wrapped={cov['n_wrapped']} gaps={cov['n_gaps']})"
        )
        if cov.get("enqueued"):
            print(f"command-ecosystem: enqueued {len(cov['enqueued'])} Backlog line(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
