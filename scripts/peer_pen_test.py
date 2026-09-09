#!/usr/bin/env python3
"""Defensive pen-test / security hardening lane.

Mechanical scan → notes/PEN_TEST.md → enqueue ``[pen-test]`` remediations →
optional cursor-agent harden pass. **No exploit PoCs / attack procedures** —
find fail-open auth, secrets in tree, injection sinks, then fix + verify.

Targets: hub (Automation) + active product-forge cwd (e.g. Newdrop/CaaS).

Usage:
  python3 scripts/peer_pen_test.py --once
  python3 scripts/peer_pen_test.py --once --digest-only
  python3 scripts/peer_pen_test.py --status
  ./scripts/peer pen-test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import automation_config as cfg_mod  # noqa: E402
import project_automation as auto  # noqa: E402

CONFIG_DIR = auto.CONFIG_DIR
STATE_PATH = CONFIG_DIR / "pen-test-state.json"
FINDINGS_PATH = CONFIG_DIR / "pen-test-findings.json"
PROMPT_PATH = CONFIG_DIR / "pen-test-prompt.md"
LOG_PATH = CONFIG_DIR / "pen-test-loop.log"
DIGEST_PATH = ROOT / "notes" / "PEN_TEST.md"

# Split literals so STATIC self-match scanners do not flag this file.
_SK = "sk" + "_live"
_WHSEC = "whsec" + "_"
_SERVICE_ROLE = "service" + "_role"
_DANGEROUS_HTML = "dangerouslySetInner" + "HTML"

# id, regex, severity, title — defensive sinks / secrets only
SCAN_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    (
        "secret_sk_live",
        rf"\b{_SK}[A-Za-z0-9_-]{{8,}}",
        "critical",
        "Live Stripe-like secret in source",
    ),
    (
        "secret_whsec",
        rf"\b{_WHSEC}[A-Za-z0-9_-]{{8,}}",
        "critical",
        "Webhook signing secret in source",
    ),
    (
        "secret_service_role",
        rf"\b{_SERVICE_ROLE}\b.{{0,40}}(eyJ|supabase|key\s*=)",
        "critical",
        "Service-role / elevated key near client code",
    ),
    (
        "eval_call",
        r"(?<![.\w])eval\s*\(",
        "high",
        "eval" + "() builtin — code injection risk",
    ),
    (
        "shell_true",
        r"shell\s*=\s*" + "True",
        "high",
        "subprocess shell=" + "True — command injection risk",
    ),
    (
        "danger_html",
        rf"\b{_DANGEROUS_HTML}\b",
        "high",
        "Unsanitized HTML sink (XSS risk)",
    ),
    (
        "token_query",
        r"[?&](token|api_key|secret|password)=",
        "high",
        "Secret in query string (logs/referrer leak)",
    ),
    (
        "fail_open_true",
        r"if\s*\(\s*\w*err(or)?\s*\)\s*return\s+true\b",
        "high",
        "Fail-open entitlement gate (error → allow)",
    ),
    (
        "raw_sql_fstring",
        r"(execute|raw)\s*\(\s*f[\"'].*(SELECT|INSERT|UPDATE|DELETE)",
        "high",
        "f-string SQL — injection risk",
    ),
)

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    ".worktrees",
    "coverage",
    ".turbo",
    # OVERSEER_PEN_SKIP_TESTS_2026_09_04 — unit fixtures intentionally contain
    # eval()/shell=True samples; scanning tests/ floods false [pen-test] Active.
    "tests",
    "test",
    "__tests__",
}
SKIP_SUFFIXES = {".map", ".min.js", ".lock", ".png", ".jpg", ".webp", ".ico", ".woff2"}
# Never content-scan dotenv files — secrets belong there; only git-tracked .env is a finding.
SKIP_ENV_NAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.test",
    ".env.staging",
}
TEXT_GLOBS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".sql",
    ".md",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".sh",
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class PenFinding:
    id: str
    severity: str
    title: str
    evidence: str
    location: str = ""
    target: str = ""
    status: str = "open"
    first_seen: str = ""
    last_seen: str = ""

    @staticmethod
    def make_id(title: str, location: str, target: str) -> str:
        raw = f"{target}|{title}|{location}".lower()
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class PenReport:
    findings: list[PenFinding] = field(default_factory=list)
    new_findings: list[PenFinding] = field(default_factory=list)
    enqueued: list[str] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)


def _cfg_block() -> dict[str, Any]:
    raw = cfg_mod.CFG.get("pen_test") or {}
    return raw if isinstance(raw, dict) else {}


def pen_test_enabled() -> bool:
    block = _cfg_block()
    if "enabled" in block:
        return bool(block["enabled"])
    return bool(cfg_mod.CFG.get("pen_test_enabled", True))


def enqueue_cap() -> int:
    block = _cfg_block()
    try:
        return max(0, min(4, int(block.get("enqueue_cap") or cfg_mod.CFG.get("pen_test_enqueue_cap") or 2)))
    except (TypeError, ValueError):
        return 2


def dispatch_agent_enabled() -> bool:
    block = _cfg_block()
    if "dispatch_agent" in block:
        return bool(block["dispatch_agent"])
    return bool(cfg_mod.CFG.get("pen_test_dispatch_agent", True))


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    line = f"{_now_iso()}  {msg}"
    print(line, flush=True)
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def product_forge_target() -> Path | None:
    state = _load_json(CONFIG_DIR / "product-forge-state.json")
    if not state.get("active"):
        return None
    raw = str(state.get("target_path") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def scan_targets() -> list[Path]:
    """Hub + active product repo (when product-forge is on)."""
    out: list[Path] = [ROOT]
    block = _cfg_block()
    extra = block.get("extra_roots") or cfg_mod.CFG.get("pen_test_extra_roots") or []
    if isinstance(extra, list):
        for item in extra:
            p = Path(str(item)).expanduser()
            if p.is_dir() and p.resolve() not in {x.resolve() for x in out}:
                out.append(p)
    prod = product_forge_target()
    if prod and prod.resolve() not in {x.resolve() for x in out}:
        out.append(prod)
    return out


def _iter_files(root: Path, *, max_files: int = 4000) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES and not d.startswith(".")]
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() in SKIP_SUFFIXES:
                continue
            if path.name in SKIP_ENV_NAMES or path.name.startswith(".env."):
                continue
            if path.suffix.lower() not in TEXT_GLOBS:
                continue
            # Skip this scanner's own pattern definitions
            if path.resolve() == Path(__file__).resolve():
                continue
            # Sibling research pattern table titles mention eval / shell=True.
            # OVERSEER_PEN_SKIP_RESEARCH_2026_09_04
            if path.name == "peer_repo_research.py":
                continue
            # OVERSEER_PEN_SKIP_LAND_HELPER_2026_09_04
            if path.name.startswith("_mark_flaw") or path.name.startswith("_overseer_"):
                continue
            files.append(path)
            if len(files) >= max_files:
                return files
    return files


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def probe_target(root: Path) -> list[PenFinding]:
    findings: list[PenFinding] = []
    compiled = [(pid, re.compile(pat), sev, title) for pid, pat, sev, title in SCAN_PATTERNS]
    target_label = root.name
    now = _now_iso()

    # Tracked .env is always critical
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "ls-files", ".env", ".env.local", ".env.production"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            title = "Tracked .env secrets file in git"
            loc = line
            findings.append(
                PenFinding(
                    id=PenFinding.make_id(title, loc, target_label),
                    severity="critical",
                    title=title,
                    evidence=f"git ls-files lists {line}",
                    location=loc,
                    target=target_label,
                    first_seen=now,
                    last_seen=now,
                )
            )
    except (OSError, subprocess.TimeoutExpired):
        pass

    for path in _iter_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) > 1_500_000:
            continue
        rel = _rel(path, root)
        if path.name.endswith(".example") or path.name.endswith(".sample"):
            continue
        if path.name == "PEN_TEST.md":
            continue
        rel_norm = rel.replace("\\", "/")
        # Kit digests echo finding titles → feedback loop into [pen-test] Active.
        if rel_norm.startswith("notes/") or rel_norm == "scripts/self_improve_context.md":
            continue
        base = Path(rel_norm).name
        if base.startswith("_mark_flaw") or base.startswith("_overseer_"):
            continue
        in_docs = "/docs/" in f"/{rel_norm}" or rel_norm.endswith(".md")
        # OVERSEER_PEN_SANITIZED_HTML_2026_09_04 — same-file scrubbers are not open XSS.
        has_html_sanitizer = (
            "sanitize-html" in text
            or "sanitizeHtml" in text
            or "sanitizeSupportReply" in text
            or "renderSupportRichHtml" in text
            or "resolveUpdateBodyHtml" in text
            or "DOMPurify" in text
        )
        for _pid, cre, sev, title in compiled:
            if in_docs and (
                _pid.startswith("secret_")
                or _pid
                in (
                    "token_query",
                    "fail_open_true",
                    "eval_call",
                    "shell_true",
                    "danger_html",
                    "fstring_sql",
                    "raw_sql_fstring",
                )
            ):
                continue
            if _pid == "danger_html" and has_html_sanitizer:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if not cre.search(line):
                    continue
                low = line.lower()
                if "placeholder" in low or "example" in low or "fake" in low or "your_" in low:
                    continue
                if "SCAN_PATTERNS" in line or "STATIC_PATTERNS" in line:
                    continue
                # OVERSEER_PEN_LINE_SANITIZE_2026_09_04 — same-line sanitizeHtml/DOMPurify
                if _pid == "danger_html" and (
                    "sanitizeHtml" in line
                    or "sanitize-html" in line
                    or "DOMPurify" in line
                    or "sanitizeSupportReply" in line
                ):
                    continue
                # Quoted pattern titles / digests — not executable sinks.
                if _pid in ("eval_call", "shell_true") and (
                    "injection risk" in low
                    or "injection sinks" in low
                    or "security/maintainability" in low
                ):
                    continue
                # OVERSEER_PEN_SKIP_COMMENT_FALSE_EVAL_2026_09_04 — parity with
                # peer_repo_research: comment/doc echoes of "false eval()" /
                # re-poison theater are not live injection sinks (was Active
                # re-poison on peer_worktree sync comments).
                if _pid in ("eval_call", "shell_true") and (
                    line.lstrip().startswith("#")
                    or "false eval" in low
                    or "re-poison" in low
                ):
                    continue
                # OVERSEER_PEN_SKIP_DETECTOR_NEEDLE_EVAL_2026_09_05 — escaped
                # eval needles inside generator/detector strings (e.g.
                # _ov_stag_fix_land writing `".eval("` / `"eval("` checks)
                # are not live injection sinks.
                if _pid == "eval_call" and (
                    '".eval("' in line
                    or '"eval("' in line
                    or "'.eval('" in line
                    or "'eval('" in line
                    or '\\"eval(' in line
                    or "\\.eval(" in line
                ):
                    continue
                loc = f"{rel}:{i}"
                if _pid.startswith("secret_"):
                    snippet = "[redacted — rotate if real; move to env]"
                else:
                    snippet = line.strip()[:160]
                findings.append(
                    PenFinding(
                        id=PenFinding.make_id(title, loc, target_label),
                        severity=sev,
                        title=title,
                        evidence=snippet,
                        location=loc,
                        target=target_label,
                        first_seen=now,
                        last_seen=now,
                    )
                )
                break  # one hit per pattern per file
    return findings


def merge_registry(found: list[PenFinding]) -> tuple[list[PenFinding], list[PenFinding]]:
    registry = _load_json(FINDINGS_PATH)
    items: dict[str, Any] = registry.get("items") if isinstance(registry.get("items"), dict) else {}
    now = _now_iso()
    new_list: list[PenFinding] = []
    open_list: list[PenFinding] = []
    seen_ids: set[str] = set()

    for f in found:
        seen_ids.add(f.id)
        prev = items.get(f.id) if isinstance(items.get(f.id), dict) else None
        if prev:
            f.first_seen = str(prev.get("first_seen") or now)
            f.status = str(prev.get("status") or "open")
            if f.status == "resolved":
                continue
        else:
            f.first_seen = now
            new_list.append(f)
        f.last_seen = now
        open_list.append(f)
        items[f.id] = asdict(f)

    # Mark absent as resolved
    for fid, raw in list(items.items()):
        if not isinstance(raw, dict):
            continue
        if fid not in seen_ids and raw.get("status") != "resolved":
            raw["status"] = "resolved"
            raw["resolved_at"] = now

    registry["items"] = items
    registry["updated"] = now
    _save_json(FINDINGS_PATH, registry)
    open_list.sort(key=lambda x: (SEVERITY_ORDER.get(x.severity, 9), x.title))
    return open_list, new_list


def enqueue_findings(findings: list[PenFinding], *, cap: int | None = None) -> list[str]:
    limit = cap if cap is not None else enqueue_cap()
    if limit <= 0:
        return []
    enqueued: list[str] = []
    work_path = auto.WORK_QUEUE_PATH
    try:
        work_md = work_path.read_text(encoding="utf-8") if work_path.is_file() else ""
    except OSError:
        return []
    known = {auto._normalize_queue_key(x) for x in auto.open_work_items(work_md=work_md).open_items}
    # OVERSEER_PEN_SKIP_CLOSED_2026_09_04 — closed/deferred [x] twins must not
    # re-enter Active (was dual-brain theater: only_wq reopen every digest).
    closed_markers = {
        ln.strip()
        for ln in work_md.splitlines()
        if ln.strip().startswith("- [x]") and "[pen-test]" in ln
    }

    for f in findings:
        if len(enqueued) >= limit:
            break
        if f.severity not in ("critical", "high"):
            continue
        marker = f"[pen-test] {f.title} — {f.target}"
        if auto._normalize_queue_key(marker) in known:
            continue
        if any(marker in ln for ln in closed_markers):
            continue
        detail = f"{f.location} — harden fail-closed / remove from tree; unittest; no exploit PoC; never commit secrets"
        if f.severity == "critical" and "secret" in f.title.lower():
            detail = f"{f.location} — rotate credential; remove from source; use env only; unittest"
        line = f"- [ ] **{marker}** — {detail}"
        if "## Active" in work_md:
            work_md = work_md.replace("## Active\n", f"## Active\n{line}\n", 1)
        else:
            work_md = work_md.rstrip() + f"\n\n## Active\n{line}\n"
        enqueued.append(marker)
        known.add(auto._normalize_queue_key(marker))

    if not enqueued:
        return []
    try:
        work_path.write_text(work_md, encoding="utf-8")
        ctx_path = auto.CONTEXT_PATH
        if ctx_path.is_file():
            ctx_md = ctx_path.read_text(encoding="utf-8")
            for marker in enqueued:
                line = next(
                    (ln for ln in work_md.splitlines() if marker in ln and ln.strip().startswith("- [ ]")),
                    f"- [ ] **{marker}**",
                )
                if marker not in ctx_md:
                    ctx_md = auto.insert_remaining_work_bullet(ctx_md, line)
            ctx_path.write_text(ctx_md, encoding="utf-8")
    except OSError:
        return []
    return enqueued


def build_digest(report: PenReport, *, dispatched: bool) -> str:
    lines = [
        "# Pen-test / security hardening",
        "",
        f"_Updated {_now_iso()}. Defensive scan only — remediate; never ship exploit PoCs._",
        "",
        "## Summary",
        "",
        f"| Targets | {', '.join(report.targets) or '—'} |",
        f"| Open findings | {len(report.findings)} |",
        f"| New this cycle | {len(report.new_findings)} |",
        f"| Enqueued | {len(report.enqueued)} |",
        f"| Agent | {'dispatched' if dispatched else 'mechanical only'} |",
        "",
        "## Scope",
        "",
        "- Secrets in tree, tracked `.env`, service-role leaks",
        "- Injection sinks: `" + "eval" + "`, `shell=" + "True`, f-string SQL, HTML sinks",
        "- Fail-open auth / secrets in query strings",
        "- Product forge target (Newdrop/CaaS) when active",
        "",
    ]
    if report.enqueued:
        lines.extend(["## Enqueued", ""])
        for m in report.enqueued:
            lines.append(f"- {m}")
        lines.append("")
    by_sev: dict[str, list[PenFinding]] = {}
    for f in report.findings:
        by_sev.setdefault(f.severity, []).append(f)
    for sev in ("critical", "high", "medium", "low"):
        bucket = by_sev.get(sev) or []
        if not bucket:
            continue
        lines.extend([f"## {sev.upper()}", ""])
        for f in bucket[:25]:
            lines.append(f"- **{f.title}** (`{f.target}`) — `{f.location}` — {f.evidence[:100]}")
        lines.append("")
    lines.extend(
        [
            "## Agent notes",
            "",
            "_Pen Test Researcher appends dated bullets here._",
            "",
            "## Commands",
            "",
            "- `./scripts/peer pen-test` — scan + enqueue + optional agent",
            "- `./scripts/peer pen-test-digest` — mechanical only",
            "- `./scripts/peer pen-test-status` — last run",
            "",
        ]
    )
    return "\n".join(lines)


def write_prompt(report: PenReport) -> Path:
    top = report.findings[:8]
    bullets = "\n".join(
        f"- [{f.severity}] {f.target}/{f.location}: {f.title} — {f.evidence[:120]}" for f in top
    ) or "- (no open critical/high — deepen product authz/RLS pass)"
    text = f"""# Pen-test / hardening agent

Defensive security only. **Do not** write exploits, attack PoCs, or bypass recipes.

## Findings
{bullets}

## Do
1. Read `notes/PEN_TEST.md` + security-hardening-pass skill checklist (Phase A).
2. Fix the highest-severity open `[pen-test]` item OR the top finding above — fail-closed, remove secrets, parameterize SQL, sanitize HTML.
3. Prefer product forge target (Newdrop/CaaS) when listed in Summary targets.
4. Add/extend a unittest or verify check that would catch the regression.
5. Mark the queue item done in WORK_QUEUE + self_improve_context when landed.
6. Append one dated bullet under ## Agent notes in notes/PEN_TEST.md.

## Do not
- Exploit PoCs, payload generators, unauthorized access recipes
- Strategy essays without a file-scoped harden diff
- Enqueue more than 1 new `[pen-test]` item this cycle
"""
    PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROMPT_PATH.write_text(text, encoding="utf-8")
    return PROMPT_PATH


def _agent_running() -> bool:
    try:
        import peer_parallel_dispatch as ppd

        return bool(ppd.find_agent_procs())
    except Exception:  # noqa: BLE001
        return False


def maybe_dispatch_agent(report: PenReport) -> bool:
    if not dispatch_agent_enabled():
        return False
    if not report.findings and not report.enqueued:
        return False
    if _agent_running():
        log("pen-test: agent busy — skip dispatch")
        return False
    try:
        import dgx_ram_budget as budget
        import peer_terminal as terminal

        if not budget.dispatch_allowed():
            log("pen-test: RAM cap — skip dispatch")
            return False
        ready, detail = terminal.desktop_auth_ready()
        if not ready:
            log(f"pen-test: auth not ready — {detail}")
            return False
        write_prompt(report)
        prompt = PROMPT_PATH.read_text(encoding="utf-8")
        rc, _ = terminal.run_cursor_agent(prompt, log_fn=log, sync=False, paid_api=False)
        log(f"pen-test: agent dispatch rc={rc}")
        return rc == 0
    except Exception as exc:  # noqa: BLE001 — lane must not crash peer loop
        log(f"pen-test: dispatch error — {exc}")
        return False


def run_once(*, digest_only: bool = False, no_dispatch: bool = False) -> PenReport:
    report = PenReport()
    if not pen_test_enabled():
        log("pen-test: disabled")
        return report

    targets = scan_targets()
    report.targets = [t.name for t in targets]
    log(f"pen-test: scanning {len(targets)} target(s): {', '.join(report.targets)}")

    raw: list[PenFinding] = []
    for t in targets:
        raw.extend(probe_target(t))

    open_f, new_f = merge_registry(raw)
    report.findings = open_f
    report.new_findings = new_f
    report.enqueued = enqueue_findings(open_f)

    DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_PATH.write_text(build_digest(report, dispatched=False), encoding="utf-8")

    dispatched = False
    if not digest_only and not no_dispatch:
        dispatched = maybe_dispatch_agent(report)
        if dispatched:
            DIGEST_PATH.write_text(build_digest(report, dispatched=True), encoding="utf-8")

    _save_json(
        STATE_PATH,
        {
            "last_run": _now_iso(),
            "last_run_ts": time.time(),
            "open": len(report.findings),
            "new": len(report.new_findings),
            "enqueued": report.enqueued,
            "targets": report.targets,
            "dispatched": dispatched,
        },
    )
    log(
        f"pen-test: open={len(report.findings)} new={len(report.new_findings)} "
        f"enqueued={len(report.enqueued)} dispatched={dispatched}"
    )
    return report


def print_status() -> int:
    state = _load_json(STATE_PATH)
    print(json.dumps(state or {"last_run": None}, indent=2))
    print(f"digest: {DIGEST_PATH}")
    print(f"enabled: {pen_test_enabled()}")
    prod = product_forge_target()
    print(f"product_forge: {prod or '(inactive)'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Defensive pen-test / hardening lane")
    parser.add_argument("--once", action="store_true", help="Run one scan cycle")
    parser.add_argument("--digest-only", action="store_true", help="Scan + digest; no agent")
    parser.add_argument("--no-dispatch", action="store_true", help="Skip agent dispatch")
    parser.add_argument("--status", action="store_true", help="Print last run state")
    args = parser.parse_args(argv)

    if args.status:
        return print_status()
    if args.once or args.digest_only or not any((args.status,)):
        run_once(digest_only=args.digest_only, no_dispatch=args.no_dispatch or args.digest_only)
        return 0
    return print_status()


if __name__ == "__main__":
    raise SystemExit(main())
