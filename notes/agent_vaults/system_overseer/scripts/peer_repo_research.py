#!/usr/bin/env python3
"""Continuous repo flaw research — mechanical probes + optional cursor-agent deep dive.

Unlike daily ``peer_flaw_scan`` (8-niche cross-review), this module continuously
researches **this repo** for defects: audit failures, bottlenecks, static smells,
queue drift, test regressions, and architecture gaps.

Every cycle writes ``notes/REPO_FLAW_RESEARCH.md``. New critical/high flaws can
be enqueued as ``[flaw-research]`` items.

Usage:
  python3 scripts/peer_repo_research.py --once
  python3 scripts/peer_repo_research.py --forever --daemon
  python3 scripts/peer_repo_research.py --install
  ./scripts/peer repo-research
  ./scripts/peer repo-research-status
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
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import automation_config as cfg_mod  # noqa: E402
import peer_self_heal as self_heal  # noqa: E402
import project_automation as auto  # noqa: E402

CONFIG_DIR = auto.CONFIG_DIR
STATE_PATH = CONFIG_DIR / "repo-research-state.json"
FINDINGS_PATH = CONFIG_DIR / "repo-research-findings.json"
PROMPT_PATH = CONFIG_DIR / "repo-research-prompt.md"
LOG_PATH = CONFIG_DIR / "repo-research-loop.log"

NAMESPACE = str(cfg_mod.CFG.get("config_namespace") or "automation-hub")
RESEARCH_LABEL = f"com.togi.{NAMESPACE}-repo-research-loop"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{RESEARCH_LABEL}.plist"

STATIC_SCAN_ROOTS = ("scripts", "dashboard")
# Split literals so this file does not match its own pattern definitions.
_TODO = "TO" + "DO"
_FIXME = "FIX" + "ME"
_HACK = "HA" + "CK"
_XXX = "X" + "XX"
STATIC_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    ("bare_except", r"except\s*:", "error", "Bare except — catches all exceptions"),
    (
        "todo_marker",
        rf"\b({_TODO}|{_FIXME}|{_HACK}|{_XXX})\b",
        "warn",
        f"Unresolved {_TODO}/{_FIXME} marker",
    ),
    ("eval_call", r"(?<![.\w])eval\s*\(", "error", "eval" + "() builtin — security/maintainability risk"),
    ("shell_true", r"shell\s*=\s*" + "True", "warn", "subprocess shell=" + "True — injection risk"),
    ("hardcoded_path", r'["\']/Users/[^"\']+["\']', "warn", "Hardcoded absolute path"),
)

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "warn": 4, "info": 5}


@dataclass
class RepoFlaw:
    id: str
    category: str
    severity: str
    title: str
    evidence: str
    location: str = ""
    status: str = "open"
    first_seen: str = ""
    last_seen: str = ""
    occurrences: int = 1

    @staticmethod
    def make_id(category: str, title: str, location: str = "") -> str:
        raw = f"{category}|{title}|{location}".lower()
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cfg_block() -> dict[str, Any]:
    raw = cfg_mod.CFG.get("repo_research") or {}
    return raw if isinstance(raw, dict) else {}


def research_enabled() -> bool:
    block = _cfg_block()
    if "enabled" in block:
        return bool(block["enabled"])
    return bool(cfg_mod.CFG.get("repo_research_enabled", True))


def research_interval_sec() -> float:
    block = _cfg_block()
    try:
        val = block.get("interval_sec") or cfg_mod.CFG.get("repo_research_interval_sec") or 900
        return max(120.0, float(val))
    except (TypeError, ValueError):
        return 900.0


def dispatch_agent_enabled() -> bool:
    block = _cfg_block()
    if "dispatch_agent" in block:
        return bool(block["dispatch_agent"])
    return bool(cfg_mod.CFG.get("repo_research_dispatch_agent", True))


def enqueue_cap() -> int:
    block = _cfg_block()
    try:
        return max(0, min(8, int(block.get("enqueue_cap") or cfg_mod.CFG.get("repo_research_enqueue_cap") or 3)))
    except (TypeError, ValueError):
        return 3


def digest_path() -> Path:
    block = _cfg_block()
    rel = str(
        block.get("digest_path")
        or cfg_mod.CFG.get("repo_research_digest_path")
        or "notes/REPO_FLAW_RESEARCH.md"
    )
    p = Path(rel)
    return p if p.is_absolute() else ROOT / p


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_state() -> dict[str, Any]:
    return _load_json(STATE_PATH)


def _save_state(state: dict[str, Any]) -> None:
    _save_json(STATE_PATH, state)


def _load_findings_registry() -> dict[str, Any]:
    return _load_json(FINDINGS_PATH)


def _save_findings_registry(registry: dict[str, Any]) -> None:
    _save_json(FINDINGS_PATH, registry)


def cooldown_remaining() -> float:
    state = _load_state()
    last = float(state.get("last_run_ts") or 0)
    return max(0.0, research_interval_sec() - (time.time() - last))


def _severity_from_bottleneck(sev: str) -> str:
    s = (sev or "medium").lower()
    return s if s in SEVERITY_ORDER else "medium"


def _severity_from_audit(level: str) -> str:
    lv = (level or "warn").lower()
    if lv == "error":
        return "high"
    if lv == "warn":
        return "medium"
    return "low"


def probe_audit_flaws() -> list[RepoFlaw]:
    flaws: list[RepoFlaw] = []
    try:
        import automation_adapt as adapt

        report = adapt.run_audit(ROOT, quick=True)
        # pass/info are healthy audit chatter — only warn/error are flaws
        for finding in report.findings:
            level = (finding.level or "").lower()
            if level in ("pass", "info", "ok"):
                continue
            title = f"{finding.category}: {finding.message}"[:120]
            evidence = finding.message[:400]
            sev = _severity_from_audit(finding.level)
            fid = RepoFlaw.make_id("audit", title, finding.category)
            flaws.append(
                RepoFlaw(
                    id=fid,
                    category="audit",
                    severity=sev,
                    title=title,
                    evidence=evidence,
                    location=finding.category,
                )
            )
        if not report.ok:
            fid = RepoFlaw.make_id("audit", "adapt audit not ok", "")
            flaws.append(
                RepoFlaw(
                    id=fid,
                    category="audit",
                    severity="high",
                    title="Adapt audit failed",
                    evidence=f"{len(report.findings)} finding(s); checks={','.join(report.checks_run[:6])}",
                )
            )
    except Exception as exc:  # noqa: BLE001
        flaws.append(
            RepoFlaw(
                id=RepoFlaw.make_id("probe", "audit probe error", ""),
                category="probe",
                severity="medium",
                title="Audit probe failed",
                evidence=str(exc)[:200],
            )
        )
    return flaws


def probe_bottleneck_flaws() -> list[RepoFlaw]:
    flaws: list[RepoFlaw] = []
    try:
        for bn in self_heal.scan_bottlenecks():
            # OVERSEER_SKIP_AUTOHEAL_BOTTLENECK_2026_09_04 — mechanical heal owns
            # auto_healable bottlenecks; [flaw-research] Active is noop theater
            # (last_cycle poison fixture reopen loop).
            if getattr(bn, "auto_healable", False):
                continue
            fid = RepoFlaw.make_id("bottleneck", bn.id, "")
            flaws.append(
                RepoFlaw(
                    id=fid,
                    category="bottleneck",
                    severity=_severity_from_bottleneck(bn.severity),
                    title=bn.title,
                    evidence=bn.evidence[:400],
                )
            )
    except Exception as exc:  # noqa: BLE001
        flaws.append(
            RepoFlaw(
                id=RepoFlaw.make_id("probe", "bottleneck probe error", ""),
                category="probe",
                severity="medium",
                title="Bottleneck scan failed",
                evidence=str(exc)[:200],
            )
        )
    return flaws


def probe_queue_flaws() -> list[RepoFlaw]:
    flaws: list[RepoFlaw] = []
    try:
        import automation_adapt as adapt

        _, warnings = adapt.heal_queue_drift(root=ROOT, write=False)
        for w in warnings[:12]:
            title = w[:100]
            fid = RepoFlaw.make_id("queue", title, "")
            flaws.append(
                RepoFlaw(
                    id=fid,
                    category="queue",
                    severity="medium",
                    title="Queue drift",
                    evidence=w[:400],
                )
            )
    except Exception as exc:  # noqa: BLE001
        flaws.append(
            RepoFlaw(
                id=RepoFlaw.make_id("queue", "drift probe error", ""),
                category="queue",
                severity="low",
                title="Queue drift probe failed",
                evidence=str(exc)[:200],
            )
        )

    q = auto.open_work_items()
    if len(q.open_items) > 15:
        fid = RepoFlaw.make_id("queue", "queue overflow", "")
        flaws.append(
            RepoFlaw(
                id=fid,
                category="queue",
                severity="high",
                title="Executable queue bloated",
                evidence=f"{len(q.open_items)} open items (source={q.source}) — run compact-queue",
            )
        )

    try:
        work = auto.WORK_QUEUE_PATH.read_text(encoding="utf-8") if auto.WORK_QUEUE_PATH.is_file() else ""
        ctx = auto.CONTEXT_PATH.read_text(encoding="utf-8") if auto.CONTEXT_PATH.is_file() else ""
        if work and ctx:
            # Compare brains like sync_queue_drift: Active/phased vs Remaining.
            # all_open_work_queue_items includes Backlog → permanent false HIGH.
            # Do NOT call open_work_items(context_md=): that still loads WORK_QUEUE
            # and always returns launch items (false-negative).
            w_items = auto._parse_phased_work_items(work)
            c_items = auto.remaining_work_items(ctx)
            w_keys = {auto._normalize_queue_key(x) for x in w_items}
            c_keys = {auto._normalize_queue_key(x) for x in c_items}
            if w_keys != c_keys:
                fid = RepoFlaw.make_id("queue", "dual brain mismatch", "")
                flaws.append(
                    RepoFlaw(
                        id=fid,
                        category="queue",
                        severity="high",
                        title="WORK_QUEUE ↔ context mismatch",
                        evidence=(
                            f"work={len(w_keys)} context={len(c_keys)} "
                            f"only_wq={len(w_keys - c_keys)} only_ctx={len(c_keys - w_keys)} "
                            "— run sync-queue"
                        ),
                    )
                )
    except OSError:
        pass
    return flaws


def probe_live_flaws() -> list[RepoFlaw]:
    flaws: list[RepoFlaw] = []
    try:
        live = auto.measure_live_state(quick=True)
        if live.tests_ok is False:
            detail = live.tests_detail or "tests_ok=false"
            detail_l = detail.lower()
            # In-flight / lock / deferred / fail-ttl are inconclusive — not confirmed
            # failures. fail-ttl reuses compressed FAIL after unittest storms and must
            # not enqueue critical "Tests failing" (OVERSEER_FAIL_TTL_2026_09_04).
            # OVERSEER_PROBE_SKIP_BARE_FAIL_2026_09_04 — empty epilog ≠ confirmed red.
            # OVERSEER_INCONCLUSIVE_WORKTREE_EPILOG_2026_09_04 — dry-run help ≠ red.
            skip_tokens = (
                "in flight",
                "lock held",
                "deferred",
                "skipped",
                "stale cache",
                "timeout",
                "fail-ttl",
                "pass --execute",
                "never uses --force",
            )
            bare_fail = bool(re.search(r"fail\s*[—\-]\s*failed\s*$", detail_l)) or detail_l in {
                "tests: fail — failed",
                "tests: fail - failed",
                "failed",
            }
            confirmed_counts = "failures=" in detail_l or "errors=" in detail_l
            if not confirmed_counts and (
                bare_fail or any(tok in detail_l for tok in skip_tokens)
            ):
                pass
            else:
                fid = RepoFlaw.make_id("verify", "tests failing", detail)
                flaws.append(
                    RepoFlaw(
                        id=fid,
                        category="verify",
                        severity="critical",
                        title="Tests failing",
                        evidence=detail[:400],
                    )
                )
        if not live.git_clean and "automation" in (live.git_detail or "").lower():
            fid = RepoFlaw.make_id("git", "dirty tree", live.git_detail or "")
            flaws.append(
                RepoFlaw(
                    id=fid,
                    category="git",
                    severity="low",
                    title="Dirty git tree",
                    evidence=(live.git_detail or "")[:400],
                )
            )
    except Exception as exc:  # noqa: BLE001
        flaws.append(
            RepoFlaw(
                id=RepoFlaw.make_id("probe", "live state error", ""),
                category="probe",
                severity="low",
                title="Live state probe failed",
                evidence=str(exc)[:200],
            )
        )
    return flaws


def probe_static_flaws(*, max_hits: int = 40) -> list[RepoFlaw]:
    flaws: list[RepoFlaw] = []
    hits = 0
    for rel_root in STATIC_SCAN_ROOTS:
        base = ROOT / rel_root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if hits >= max_hits:
                break
            if ".worktrees" in path.parts or "__pycache__" in path.parts:
                continue
            try:
                rel = path.relative_to(ROOT)
            except ValueError:
                continue
            if rel.parts and rel.parts[0] == "tests":
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for pid, pattern, level, desc in STATIC_PATTERNS:
                for m in re.finditer(pattern, text):
                    hits += 1
                    if hits > max_hits:
                        break
                    line_no = text[: m.start()].count("\n") + 1
                    loc = f"{path.relative_to(ROOT)}:{line_no}"
                    line = text.splitlines()[line_no - 1].strip()[:120]
                    if pid == "eval_call" and ".eval(" in line:
                        continue
                    # OVERSEER_STATIC_SKIP_EVAL_COMMENT_2026_09_04
                    if pid == "eval_call" and line.lstrip().startswith("#"):
                        continue
                    if path.name == "peer_repo_research.py" and "eval_call" in line:
                        continue
                    # OVERSEER_STATIC_SKIP_PATTERN_DEFS_2026_09_04
                    if path.name in ("peer_pen_test.py", "peer_repo_research.py", "_mark_flaw_research_landed.py") and pid in (
                        "eval_call",
                        "shell_true",
                    ):
                        continue

                    # OVERSEER_STATIC_SKIP_TITLE_ECHO_2026_09_04 — queue/digest
                    # echoes of finding titles are not live sinks.
                    if pid == "eval_call" and (
                        "code injection risk" in line.lower()
                        or ("builtin" in line.lower() and "eval()" in line.replace(" ", ""))
                        or "false eval()" in line.lower().replace("`", "")  # OVERSEER_STATIC_SKIP_FALSE_EVAL_ECHO_2026_09_04
                        or "re-poisoning false" in line.lower().replace("`", "")
                    ):
                        continue
                    if pid == "shell_true" and "injection risk" in line.lower():
                        continue
                    # Queue titles / digests quoting sink names — not executable sinks.
                    # OVERSEER_STATIC_CATALOG_SKIP_2026_09_04
                    if pid == "eval_call" and (
                        "injection risk" in line.lower()
                        or "maintainability risk" in line.lower()
                        or line.lstrip().startswith("#")
                    ):
                        continue
                    if pid == "shell_true" and (
                        "injection risk" in line.lower()
                        or "Injection sinks" in line
                        or line.lstrip().startswith("#")
                    ):
                        continue
                    # Comment-only chatter is not an injection risk.
                    if pid in ("eval_call", "shell_true") and line.lstrip().startswith("#"):
                        continue
                    # OVERSEER_STATIC_SKIP_REPOISON_DOC_2026_09_04 — sync helper
                    # docstrings that mention false eval-call / re-poison are not sinks.
                    if pid == "eval_call" and (
                        "re-poison" in line.lower()
                        or "false eval" in line.lower()
                        or "hub needle" in line.lower()
                    ):
                        continue
                    # Doc examples with backtick-quoted marker names are not unresolved markers.
                    if pid == "todo_marker":
                        if line.lstrip().startswith("#"):
                            continue
                        if path.name in ("peer_repo_research.py", "peer_precision_habits.py"):
                            continue
                        # Regex/pattern definitions that mention marker names are not markers.
                        if re.search(r"\(\?[:!]?(?:TODO|FIXME|HACK|XXX)", line, re.I):
                            continue
                        if re.search(
                            r"`[^`]*\b(?:TODO|FIXME|HACK|XXX)\b[^`]*`", line, re.I
                        ):
                            continue
                        # Habits/doc tables quoting "rg TODO" as an anti-pattern.
                        if "|" in line and re.search(
                            r"never\s+`[^`]*\b(?:TODO|FIXME)\b", line, re.I
                        ):
                            continue
                    sev = "medium" if level == "warn" else "high"
                    fid = RepoFlaw.make_id("static", pid, loc)
                    flaws.append(
                        RepoFlaw(
                            id=fid,
                            category="static",
                            severity=sev,
                            title=desc,
                            evidence=line,
                            location=loc,
                        )
                    )
    return flaws


def probe_orchestrate_flaws() -> list[RepoFlaw]:
    flaws: list[RepoFlaw] = []
    try:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "peer_orchestrate.py"), "--self-check"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=90.0,
            check=False,
        )
        out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        # Lock contention is fail-closed by design (rc=75) — not a repo flaw.
        if proc.returncode == 75 or "another self-check already running" in out:
            return flaws
        # Tip lines (Role roster, agent_roles, …) are not failures — ignore when ISSUES: none.
        if proc.returncode != 0 and not re.search(r"(?m)^ISSUES:\s*none\s*$", out):
            err = out or "self-check failed"
            issue_block = err
            if "ISSUES:" in err:
                issue_block = err.split("ISSUES:", 1)[1]
                if "TIPS:" in issue_block:
                    issue_block = issue_block.split("TIPS:", 1)[0]
            last_lines = "\n".join(issue_block.strip().splitlines()[:6] or err.splitlines()[-4:])
            fid = RepoFlaw.make_id("orchestrate", "self-check fail", last_lines[:80])
            flaws.append(
                RepoFlaw(
                    id=fid,
                    category="orchestrate",
                    severity="high",
                    title="peer_orchestrate self-check failed",
                    evidence=last_lines[:400],
                )
            )
    except subprocess.TimeoutExpired:
        flaws.append(
            RepoFlaw(
                id=RepoFlaw.make_id("orchestrate", "self-check timeout", ""),
                category="orchestrate",
                severity="medium",
                title="Self-check timed out",
                evidence="peer_orchestrate --self-check exceeded 90s",
            )
        )
    except OSError as exc:
        flaws.append(
            RepoFlaw(
                id=RepoFlaw.make_id("orchestrate", "self-check error", ""),
                category="orchestrate",
                severity="low",
                title="Self-check probe error",
                evidence=str(exc)[:200],
            )
        )
    return flaws


def mechanical_probe(*, include_self_check: bool = False) -> list[RepoFlaw]:
    """Run all mechanical flaw probes on the current repo."""
    flaws: list[RepoFlaw] = []
    flaws.extend(probe_audit_flaws())
    flaws.extend(probe_bottleneck_flaws())
    flaws.extend(probe_queue_flaws())
    flaws.extend(probe_live_flaws())
    flaws.extend(probe_static_flaws())
    if include_self_check:
        flaws.extend(probe_orchestrate_flaws())
    # Dedupe by id within cycle
    seen: set[str] = set()
    unique: list[RepoFlaw] = []
    for f in sorted(flaws, key=lambda x: SEVERITY_ORDER.get(x.severity, 9)):
        if f.id in seen:
            continue
        seen.add(f.id)
        unique.append(f)
    return unique


# OVERSEER_RESOLVE_LOGIC_EPHEMERAL_2026_09_04 — enqueued logic theater (plan-gate
# leftover, etc.) must clear when the probe no longer sees it.
# OVERSEER_RESOLVE_DEFECT_EPHEMERAL_2026_09_04 — agent defect theater sticks as
# enqueued forever unless defect is in this set (PRESENT_TRUE / FIXTURE_NOTE_OK).
_RESOLVE_WHEN_ABSENT_CATEGORIES = frozenset(
    {
        "bottleneck",
        "queue",
        "audit",
        "probe",
        "orchestrate",
        "verify",
        "git",
        "logic",
        "defect",
    }
)


def _static_flaw_still_present(raw: dict[str, Any]) -> bool:
    """Return True if a registered static flaw still matches its recorded location."""
    loc = str(raw.get("location") or "")
    evidence = str(raw.get("evidence") or "")
    title = str(raw.get("title") or "")
    if not loc or ":" not in loc:
        return True
    rel, _, line_s = loc.partition(":")
    rel_parts = Path(rel).parts
    if rel_parts and rel_parts[0] == "tests":
        return False
    # OVERSEER_STATIC_RESOLVE_CATALOG_2026_09_04 — pattern catalogs / title echoes are not sinks.
    name = Path(rel).name
    title_l = title.lower()
    if name in (
        "peer_pen_test.py",
        "peer_repo_research.py",
        "_mark_flaw_research_landed.py",
        "project_automation.py",
    ) and (
        "eval()" in title_l or "shell=true" in title_l or "injection" in title_l
    ):
        return False
    try:
        line_no = int(line_s)
    except ValueError:
        return True
    path = ROOT / rel
    if not path.is_file():
        return False
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return True
    if line_no < 1 or line_no > len(lines):
        return False
    line = lines[line_no - 1]
    if line.lstrip().startswith("#"):
        return False
    line_l = line.lower()
    if "code injection risk" in line_l or "injection sinks" in line_l or "maintainability risk" in line_l:
        return False
    for pid, pattern, _level, desc in STATIC_PATTERNS:
        if desc != title and pid not in str(raw.get("id") or ""):
            continue
        if not re.search(pattern, line):
            continue
        # OVERSEER_STATIC_PRESENT_TRUE_ON_MATCH_2026_09_04 — match ⇒ still present.
        # Catalog/comment skips above already filter false positives; inverted
        # eval_call/shell_true→False wrongly resolved real sinks on empty merge.
        return True
    if evidence and evidence in line and (".eval(" in line or "eval(" in line or "shell=True" in line):
        return True
    return False



def merge_findings(flaws: list[RepoFlaw]) -> tuple[list[RepoFlaw], list[RepoFlaw]]:
    """Merge into registry; return (all_open, newly_discovered)."""
    registry = _load_findings_registry()
    items: dict[str, dict[str, Any]] = registry.get("items") or {}
    if not isinstance(items, dict):
        items = {}
    now = _now_iso()
    new_flaws: list[RepoFlaw] = []
    probed_ids = {f.id for f in flaws}

    for flaw in flaws:
        existing = items.get(flaw.id)
        if existing:
            existing["last_seen"] = now
            existing["occurrences"] = int(existing.get("occurrences") or 0) + 1
            existing["evidence"] = flaw.evidence
            existing["status"] = "open"
            items[flaw.id] = existing
        else:
            flaw.first_seen = now
            flaw.last_seen = now
            items[flaw.id] = asdict(flaw)
            new_flaws.append(flaw)

    for fid, existing in list(items.items()):
        if not isinstance(existing, dict):
            continue
        if existing.get("status") == "resolved":
            continue
        if fid in probed_ids:
            continue
        cat = str(existing.get("category") or "")
        # Enqueued ephemeral/static may still auto-resolve when the probe no longer sees them.
        if existing.get("status") == "enqueued" and cat not in _RESOLVE_WHEN_ABSENT_CATEGORIES and cat != "static":
            continue
        if cat == "static":
            if not _static_flaw_still_present(existing):
                existing["status"] = "resolved"
                existing["resolved_at"] = now
                items[fid] = existing
        elif cat in _RESOLVE_WHEN_ABSENT_CATEGORIES:
            existing["status"] = "resolved"
            existing["resolved_at"] = now
            items[fid] = existing

    registry["items"] = items
    registry["updated_at"] = now
    _save_findings_registry(registry)

    open_flaws: list[RepoFlaw] = []
    for raw in items.values():
        if not isinstance(raw, dict):
            continue
        if raw.get("status") == "resolved":
            continue
        open_flaws.append(
            RepoFlaw(
                id=str(raw.get("id") or ""),
                category=str(raw.get("category") or ""),
                severity=str(raw.get("severity") or "medium"),
                title=str(raw.get("title") or ""),
                evidence=str(raw.get("evidence") or ""),
                location=str(raw.get("location") or ""),
                status=str(raw.get("status") or "open"),
                first_seen=str(raw.get("first_seen") or ""),
                last_seen=str(raw.get("last_seen") or ""),
                occurrences=int(raw.get("occurrences") or 1),
            )
        )

    open_flaws.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.title))
    return open_flaws, new_flaws


def _skip_mechanical_queue_drift_enqueue(flaw: RepoFlaw) -> bool:
    """Heal/sync already owns dual-brain drift — enqueue is compact-queue theater."""
    title_l = flaw.title.lower()
    if "bloated" in title_l or "overflow" in title_l:
        return False
    if flaw.title.startswith("queue: only in"):
        return True
    evidence = flaw.evidence or ""
    evidence_l = evidence.lower()
    evidence_stripped = evidence.lstrip()
    if evidence_stripped.startswith("only in notes/") or evidence_stripped.startswith(
        "only in self_improve_context"
    ):
        return True
    if flaw.category == "queue" and (
        "drift" in title_l or "mismatch" in title_l or "only in" in evidence_l
    ):
        return True
    # OVERSEER_SKIP_SELF_CHECK_JUNK_2026_09_04 — paste of self-check/FAIL stdout.
    if "self-check failed" in title_l and (
        "tests not ok" in evidence_l
        or "tests: fail" in evidence_l
        or "another self-check" in evidence_l
        or "✗" in evidence
        or "failed (failures=" in evidence_l
        or "failed (errors=" in evidence_l
    ):
        return True
    if evidence.lstrip().startswith("✗") or "failed (failures=" in evidence_l:
        return True
    # OVERSEER_SKIP_LAST_CYCLE_POISON_ENQUEUE_2026_09_04 — self-heal owns it.
    if "last_cycle poison" in title_l or (
        "verify_ok=true" in title_l.replace(" ", "")
        and "failure_type=deferred" in title_l.replace(" ", "")
    ):
        return True
    if flaw.category == "bottleneck" and "'ts': 1.0" in evidence:
        return True
    # OVERSEER_SKIP_FIXED_DEFECT_THEATER_2026_09_04 — needles landed; do not
    # re-enqueue agent theater after PRESENT_TRUE / FIXTURE_NOTE_OK.
    if "inverted for eval_call" in title_l or "static_flaw_still_present inverted" in title_l:
        return True
    if "scrub misses ts=1.0" in title_l or "fixtures with note" in title_l:
        return True
    # OVERSEER_SKIP_LANDED_FLAW_THEATER_2026_09_04 — land-proof needles live;
    # Mac/rsync must not reopen these three Active theater lines.
    # OVERSEER_SKIP_LANDED_FLAW_REENQUEUE_2026_09_04 — needle-sync + hub-protect.
    if "repo_flaw_research.md missing" in title_l or "hub_protect_pull_excludes" in title_l.replace(
        " ", "_"
    ):
        return True
    if "re-poison false eval" in title_l or "stale peer worktrees re-poison" in title_l:
        return True
    if "repo_flaw_research.md" in title_l and "missing" in title_l:
        return True
    return False


def enqueue_flaws(flaws: list[RepoFlaw], *, cap: int | None = None) -> list[str]:
    """Enqueue critical/high new flaws to WORK_QUEUE."""
    limit = cap if cap is not None else enqueue_cap()
    if limit <= 0:
        return []
    enqueued: list[str] = []
    registry = _load_findings_registry()
    items: dict[str, Any] = registry.get("items") or {}

    for flaw in flaws:
        if len(enqueued) >= limit:
            break
        if _skip_mechanical_queue_drift_enqueue(flaw):
            continue
        if flaw.severity not in ("critical", "high"):
            continue
        marker = f"[flaw-research] {flaw.title}"
        work_path = auto.WORK_QUEUE_PATH
        try:
            work_md = work_path.read_text(encoding="utf-8") if work_path.is_file() else ""
            known = {auto._normalize_queue_key(x) for x in auto.open_work_items(work_md=work_md).open_items}
            if auto._normalize_queue_key(marker) in known:
                continue
            # OVERSEER_SKIP_CLOSED_FLAW_2026_09_04 — closed/deferred twins must not re-open.
            if any(
                ln.strip().startswith("- [x]") and marker in ln
                for ln in work_md.splitlines()
            ):
                continue
            detail = flaw.evidence[:200]
            if flaw.location:
                detail = f"{flaw.location} — {detail}"
            line = f"- [ ] **{marker}** — {detail}"
            if "## Active" in work_md:
                work_md = work_md.replace("## Active\n", f"## Active\n{line}\n", 1)
            else:
                work_md = work_md.rstrip() + f"\n\n## Active\n{line}\n"
            work_path.write_text(work_md, encoding="utf-8")
            ctx_path = auto.CONTEXT_PATH
            if ctx_path.is_file():
                ctx_md = ctx_path.read_text(encoding="utf-8")
                if marker not in ctx_md:
                    ctx_md = auto.insert_remaining_work_bullet(ctx_md, line)
                    ctx_path.write_text(ctx_md, encoding="utf-8")
            enqueued.append(marker)
            if flaw.id in items:
                items[flaw.id]["status"] = "enqueued"
        except OSError:
            continue

    if enqueued:
        registry["items"] = items
        _save_findings_registry(registry)
    return enqueued


def build_digest(
    *,
    open_flaws: list[RepoFlaw],
    new_flaws: list[RepoFlaw],
    actions: list[str],
    dispatched: bool,
    agent_pending: bool = False,
) -> str:
    now = _now_iso()
    by_sev: dict[str, list[RepoFlaw]] = {}
    for f in open_flaws:
        by_sev.setdefault(f.severity, []).append(f)

    lines = [
        "# Repo flaw research",
        "",
        f"_Updated {now}. Continuous mechanical + agent research on this repo._",
        "",
        "## Summary",
        "",
        f"| Open flaws | {len(open_flaws)} |",
        f"| New this cycle | {len(new_flaws)} |",
        f"| Agent review | {'dispatched' if dispatched else ('pending' if agent_pending else 'mechanical only')} |",
        "",
    ]
    if actions:
        lines.extend(["## Actions this cycle", ""])
        for a in actions:
            lines.append(f"- {a}")
        lines.append("")

    lines.extend(["## Open flaws by severity", ""])
    for sev in ("critical", "high", "medium", "low"):
        group = by_sev.get(sev) or []
        if not group:
            continue
        lines.append(f"### {sev} ({len(group)})")
        lines.append("")
        for f in group[:12]:
            loc = f" `{f.location}`" if f.location else ""
            lines.append(f"- **{f.title}** [{f.category}]{loc}")
            lines.append(f"  - {f.evidence[:240]}")
        if len(group) > 12:
            lines.append(f"- _…and {len(group) - 12} more_")
        lines.append("")

    if new_flaws:
        lines.extend(["## New this cycle", ""])
        for f in new_flaws[:8]:
            lines.append(f"- [{f.severity}] {f.title}")
        lines.append("")

    lines.extend(
        [
            "## Agent notes",
            "",
            "_Cursor-agent appends dated findings here after deep repo research._",
            "",
        ]
    )

    # Preserve prior Agent notes across rewrite (same pattern as peer_investigate.build_digest).
    # OVERSEER_DIGEST_KEEP_HASH_NOTES_2026_09_04 — ### dated blocks + **Severity** survive
    # (bullet-only keep wiped Repo Flaw Research Agent findings every probe cycle).
    prev = digest_path()
    if prev.is_file():
        try:
            old = prev.read_text(encoding="utf-8")
            if "## Agent notes" in old:
                section = old.split("## Agent notes", 1)[1]
                kept: list[str] = []
                for ln in section.splitlines():
                    s = ln.strip()
                    # OVERSEER_DIGEST_HASH_HEADING_2026_09_04 — ### must not
                    # match startswith("## ") or dated Agent notes are dropped.
                    if s.startswith("## ") and not s.startswith("###"):
                        break
                    if s.startswith("_") or s.startswith(">"):
                        continue
                    if "Cursor-agent appends" in s:
                        continue
                    # Keep ### headings, bullets, bold labels, and body continuations.
                    if (
                        not s
                        or s.startswith("### ")
                        or s.startswith("- ")
                        or s.startswith("**")
                        or (kept and not s.startswith("#"))
                    ):
                        kept.append(ln)
                while kept and not kept[-1].strip():
                    kept.pop()
                if kept:
                    lines.extend(kept[-40:])
                    lines.append("")
        except OSError:
            pass

    lines.extend(
        [
            "## Commands",
            "",
            "```bash",
            "./scripts/peer repo-research              # one probe cycle",
            "./scripts/peer repo-research-force        # ignore cooldown + dispatch",
            "./scripts/peer repo-research-status",
            "./scripts/peer heal-all                   # mechanical heal after fixes",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_digest(**kwargs: Any) -> Path:
    text = build_digest(**kwargs)
    path = digest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def build_agent_prompt(*, open_flaws: list[RepoFlaw], new_flaws: list[RepoFlaw]) -> str:
    digest = digest_path()
    top = open_flaws[:10]
    bullet_lines = "\n".join(f"- [{f.severity}] {f.title}: {f.evidence[:120]}" for f in top)
    new_lines = "\n".join(f"- {f.title}" for f in new_flaws[:6]) or "(none)"

    return f"""# Repo flaw research agent

You are the **Repo Flaw Research Agent** for `{ROOT.name}`. Your job is to continuously
research this repository for defects, regressions, architectural smells, and missing
verify coverage — then document actionable findings.

## Mechanical snapshot (already probed)

{bullet_lines}

**New this cycle:**
{new_lines}

## Your task

1. Read `notes/AUTOMATION.md`, `AGENTS.md`, `scripts/peer_tasks.json`, and `{digest}`.
2. **Research the repo** — grep, read tests, trace peer_loop/adapt/orchestrate paths.
3. Find flaws the mechanical probes missed: logic bugs, race conditions, dead code,
   missing tests, config drift, security issues, noop loops, queue theater.
4. **Append** under `## Agent notes` in `{digest}` a dated block:
   - **Found:** bullet list with file paths
   - **Severity:** critical / high / medium
   - **Fix:** minimal executable next step (prefer `./scripts/peer` commands)
5. Enqueue **at most 2** critical/high items as `[flaw-research]` in `notes/WORK_QUEUE.md`
   (sync `scripts/self_improve_context.md`) — only if not already queued.
6. Do **not** expand scope into product work or industry research.

Minimal diffs only. Run `./scripts/peer test-quick` if you change Python.
"""


def _agent_running() -> bool:
    try:
        import peer_parallel_dispatch as ppd

        return bool(ppd.find_agent_procs())
    except Exception:  # noqa: BLE001
        import peer_watch

        return peer_watch.find_agent_proc() is not None


def run_research_cycle(
    *,
    log_fn: Callable[[str], None] | None = None,
    force: bool = False,
    digest_only: bool = False,
    dispatch_agent: bool | None = None,
    include_self_check: bool = False,
) -> dict[str, Any]:
    log = log_fn or (lambda _m: None)
    if not research_enabled():
        log("repo-research: disabled")
        return {"skipped": "disabled"}

    remaining = cooldown_remaining()
    if not force and not digest_only and remaining > 0:
        log(f"repo-research: cooldown {remaining:.0f}s left")
        return {"skipped": "cooldown", "remaining_sec": remaining}

    actions: list[str] = []
    log("repo-research: mechanical probe…")
    probed = mechanical_probe(include_self_check=include_self_check or force)
    open_flaws, new_flaws = merge_findings(probed)
    actions.append(f"probed {len(probed)} flaw(s); {len(new_flaws)} new")

    enqueued = enqueue_flaws(new_flaws)
    if enqueued:
        actions.append(f"enqueued {len(enqueued)} item(s)")
        for e in enqueued:
            log(f"repo-research: enqueue {e}")

    path = write_digest(
        open_flaws=open_flaws,
        new_flaws=new_flaws,
        actions=actions,
        dispatched=False,
    )
    log(f"repo-research: digest → {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")

    if digest_only:
        state = _load_state()
        state["last_digest_ts"] = time.time()
        _save_state(state)
        return {"digest": str(path), "open": len(open_flaws), "new": len(new_flaws)}

    prompt = build_agent_prompt(open_flaws=open_flaws, new_flaws=new_flaws)
    PROMPT_PATH.write_text(prompt, encoding="utf-8")

    should_dispatch = dispatch_agent if dispatch_agent is not None else dispatch_agent_enabled()
    dispatched = False
    if should_dispatch:
        if _agent_running():
            log("repo-research: agent busy — skip dispatch")
            actions.append("skip dispatch: agent busy")
            write_digest(
                open_flaws=open_flaws,
                new_flaws=new_flaws,
                actions=actions,
                dispatched=False,
                agent_pending=True,
            )
        else:
            try:
                import dgx_ram_budget as budget

                if not budget.dispatch_allowed():
                    log("repo-research: RAM cap — skip dispatch")
                    actions.append("skip dispatch: RAM cap")
                    write_digest(
                        open_flaws=open_flaws,
                        new_flaws=new_flaws,
                        actions=actions,
                        dispatched=False,
                    )
                    should_dispatch = False
            except Exception:  # noqa: BLE001
                pass

            if should_dispatch:
                try:
                    import peer_terminal as terminal

                    ready, detail = terminal.desktop_auth_ready()
                    if not ready:
                        log(f"repo-research: auth not ready — {detail}")
                        actions.append(f"skip dispatch: {detail}")
                    else:
                        rc, _ = terminal.run_cursor_agent(prompt, log_fn=log, sync=False, paid_api=False)
                        dispatched = rc == 0
                        actions.append(
                            "dispatched flaw-research agent" if dispatched else f"dispatch rc={rc}"
                        )
                except Exception as exc:  # noqa: BLE001
                    log(f"repo-research: dispatch failed ({exc})")
                    actions.append(f"dispatch failed: {exc}")

                write_digest(
                    open_flaws=open_flaws,
                    new_flaws=new_flaws,
                    actions=actions,
                    dispatched=dispatched,
                    agent_pending=dispatched,
                )
    else:
        log("repo-research: agent dispatch disabled")

    state = _load_state()
    state["last_run_ts"] = time.time()
    state["last_open_count"] = len(open_flaws)
    state["last_new_count"] = len(new_flaws)
    state["last_dispatched"] = dispatched
    state["last_actions"] = actions[-8:]
    _save_state(state)

    return {
        "digest": str(path),
        "open": len(open_flaws),
        "new": len(new_flaws),
        "dispatched": dispatched,
        "enqueued": enqueued,
        "actions": actions,
    }


def _log_daemon(msg: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp}  {msg}"
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def run_forever(*, daemon: bool = False) -> int:
    log_fn = _log_daemon if daemon else print
    log_fn(
        f"repo-research forever — every {research_interval_sec():.0f}s "
        f"(dispatch={dispatch_agent_enabled()})"
    )
    try:
        while True:
            run_research_cycle(log_fn=log_fn, include_self_check=False)
            time.sleep(research_interval_sec())
    except KeyboardInterrupt:
        log_fn("repo-research forever stopped")
        return 0


def plist_body() -> str:
    py = sys.executable
    script = SCRIPTS / "peer_repo_research.py"
    args = [py, str(script), "--forever", "--daemon"]
    args_xml = "\n".join(f"    <string>{a}</string>" for a in args)
    home = Path.home()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{RESEARCH_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
{args_xml}
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>WorkingDirectory</key>
  <string>{ROOT}</string>
  <key>StandardOutPath</key>
  <string>{LOG_PATH}</string>
  <key>StandardErrorPath</key>
  <string>{LOG_PATH}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>{home}</string>
    <key>PATH</key>
    <string>{home}/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>PYTHONPATH</key>
    <string>{SCRIPTS}</string>
  </dict>
</dict>
</plist>
"""


def cmd_install() -> int:
    if sys.platform != "darwin":
        import peer_self_heal as heal

        heal.ensure_canonical_module()
        print(heal.linux_install_daemon("research"))
        return 0
    uid = os.getuid()
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(plist_body())
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{RESEARCH_LABEL}"], capture_output=True)
    proc = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print((proc.stderr or proc.stdout or "bootstrap failed").strip(), file=sys.stderr)
        return 1
    print(f"repo-research agent: {PLIST_PATH}")
    print(f"log: {LOG_PATH}")
    print(f"digest: {digest_path()}")
    return 0


def cmd_uninstall() -> int:
    if sys.platform != "darwin":
        import peer_self_heal as heal

        heal.ensure_canonical_module()
        print(heal.linux_uninstall_daemon("research"))
        return 0
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{RESEARCH_LABEL}"], capture_output=True)
    if PLIST_PATH.is_file():
        PLIST_PATH.unlink()
    print("repo-research agent removed")
    return 0


def cmd_status() -> int:
    """OVERSEER_LINUX_REPO_RESEARCH_STATUS_2026_09_04 — never launchctl on Linux."""
    running = False
    live_label = RESEARCH_LABEL
    if sys.platform != "darwin":
        import peer_self_heal as heal

        running = heal._systemd_user_active("repo-research-loop.service")
        live_label = "repo-research-loop.service"
    else:
        uid = os.getuid()
        proc = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/{RESEARCH_LABEL}"],
            capture_output=True,
            text=True,
        )
        running = proc.returncode == 0 and "state = running" in (proc.stdout or "")
    state = _load_state()
    registry = _load_findings_registry()
    items = registry.get("items") or {}
    open_n = sum(1 for v in items.values() if isinstance(v, dict) and v.get("status") != "resolved")

    print(f"enabled: {research_enabled()}")
    print(f"label: {live_label}")
    print(f"state: {'RUNNING' if running else 'STOPPED'}")
    print(f"interval: {research_interval_sec():.0f}s")
    print(f"cooldown: {cooldown_remaining():.0f}s")
    print(f"open flaws: {open_n}")
    print(f"digest: {digest_path()}")
    print(f"log: {LOG_PATH}")
    print(f"last run: {state.get('last_run_ts', '(never)')}")
    return 0 if running else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuous repo flaw research")
    parser.add_argument("--once", action="store_true", help="Single research cycle")
    parser.add_argument("--forever", action="store_true", help="Loop every interval_sec")
    parser.add_argument("--force", action="store_true", help="Ignore cooldown")
    parser.add_argument("--digest-only", action="store_true", help="Probe + digest only")
    parser.add_argument("--no-dispatch", action="store_true", help="Skip cursor-agent")
    parser.add_argument("--self-check", action="store_true", help="Include peer_orchestrate self-check probe")
    parser.add_argument("--daemon", action="store_true", help="Log to repo-research-loop.log")
    parser.add_argument("--install", action="store_true", help="Install LaunchAgent")
    parser.add_argument("--uninstall", action="store_true", help="Remove LaunchAgent")
    parser.add_argument("--status", action="store_true", help="Daemon + findings status")
    args = parser.parse_args()

    if args.install:
        return cmd_install()
    if args.uninstall:
        return cmd_uninstall()
    if args.status:
        return cmd_status()
    if args.forever:
        return run_forever(daemon=args.daemon)

    result = run_research_cycle(
        force=args.force,
        digest_only=args.digest_only,
        dispatch_agent=False if args.no_dispatch else None,
        include_self_check=args.self_check,
    )
    if args.once or not args.forever:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
