#!/usr/bin/env python3
"""Agent gates — executable countermeasures for all agent-vs-human gaps.

Maps each gap in peer_agent_human_gap to a mechanical check (where possible) or
mandatory prompt block (where judgment is required). Run before Plan and before DONE.

Usage:
  python3 scripts/peer_agent_gates.py --plan-gate --role factory_engineer
  python3 scripts/peer_agent_gates.py --done-gate --role factory_engineer \\
      --expected "exit 0" --actual "exit 0"
  python3 scripts/peer_agent_gates.py --write
  ./scripts/peer plan-gate --role ROLE
  ./scripts/peer done-gate --role ROLE --expected "..." --actual "..."
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

AGENT_GATES_MD = ROOT / "notes" / "AGENT_GATES.md"
LAST_PLAN_GATE_JSON = auto.CONFIG_DIR / "plan-gate-last.json"
ALWAYS_READ_ACK_JSON = auto.CONFIG_DIR / "always-read-ack.json"

# Minimal always-read citations the plan must acknowledge (Scope B read-ack).
REQUIRED_READ_ACK_PATHS: tuple[str, ...] = (
    "notes/AGENT_WORKING_MEMORY.md",
    "notes/WORK_QUEUE.md",
    "AGENTS.md",
)
READ_ACK_MAX_AGE_SEC = 3600

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"whsec_[a-zA-Z0-9]+"),
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
)

# Soft findings need agent dispatch to clear — never hard-block plan-gate.
# "last cycle verify" / adapt_stale are chicken-egg: agents must dispatch to clear.
_SOFT_SELF_CORRECTION = (
    "noop",
    "fingerprint",
    "dirty tree",
    "queue did not advance",
    "last cycle verify",
    "adapt_stale",
    "verify failed",
    "dispatch held",
    "verify gate fail",
    "tree broken",
    "tests red",
)


def _normalize_read_paths(paths: list[str] | tuple[str, ...] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in paths or []:
        for part in str(raw).split(","):
            rel = part.strip().replace("\\", "/").lstrip("./")
            if not rel or rel in seen:
                continue
            seen.add(rel)
            out.append(rel)
    return out


def write_always_read_ack(
    paths: list[str] | tuple[str, ...] | None,
    *,
    role_id: str = "",
    plan_text: str = "",
    path: Path | None = None,
) -> Path:
    """Record that the agent opened / cited always-read SoT paths before edit."""
    cited = _normalize_read_paths(paths)
    if plan_text:
        for req in REQUIRED_READ_ACK_PATHS:
            if req in plan_text and req not in cited:
                cited.append(req)
        # Also accept backtick citations of any ALWAYS_READ_PATHS
        try:
            import peer_memory_span as ms

            for p in ms.ALWAYS_READ_PATHS:
                if p in plan_text and p not in cited:
                    cited.append(p)
        except Exception:  # noqa: BLE001
            pass
    out = path or ALWAYS_READ_ACK_JSON
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": time.time(),
        "role": role_id,
        "paths": cited,
        "ack": True,
        "needle": "OVERSEER_AGENT_AMNESIA_RESEARCH_2026_09_07",
        "no_pay": True,
    }
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out


def load_always_read_ack(
    *,
    path: Path | None = None,
    max_age_sec: int = READ_ACK_MAX_AGE_SEC,
    extra_paths: list[str] | None = None,
    plan_text: str = "",
) -> tuple[bool, list[str], str]:
    """Merge ack file + CLI paths + plan citations; check required always-read."""
    cited: list[str] = []
    p = path or ALWAYS_READ_ACK_JSON
    detail_bits: list[str] = []
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            ts = float((data or {}).get("ts") or 0)
            age = time.time() - ts
            if ts > 0 and age <= max_age_sec:
                cited.extend(_normalize_read_paths((data or {}).get("paths") or []))
                detail_bits.append(f"ack-file age={int(age)}s")
            else:
                detail_bits.append(f"ack-file stale ({int(age)}s)")
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            detail_bits.append(f"ack-file bad ({exc})")
    else:
        detail_bits.append("no ack-file")
    cited.extend(_normalize_read_paths(extra_paths))
    if plan_text:
        for req in REQUIRED_READ_ACK_PATHS:
            if req in plan_text and req not in cited:
                cited.append(req)
        try:
            import peer_memory_span as ms

            for ap in ms.ALWAYS_READ_PATHS:
                if ap in plan_text and ap not in cited:
                    cited.append(ap)
        except Exception:  # noqa: BLE001
            pass
        detail_bits.append("plan-text scanned")
    cited = _normalize_read_paths(cited)
    missing = [r for r in REQUIRED_READ_ACK_PATHS if r not in cited]
    if missing:
        return (
            False,
            cited,
            f"missing citations: {', '.join(missing)} ({'; '.join(detail_bits)})",
        )
    return True, cited, f"cited {len(cited)} path(s) ({'; '.join(detail_bits)})"


def _librarian_receipt_gate(
    *,
    prefer_librarian: bool | None = None,
    prefer_why: str = "",
    read_ack_ok: bool = False,
    soft_mode: bool | None = None,
) -> GateResult:
    """When prefer_librarian, require fact-query receipt or always-read ack (soft→hard).

    Default soft_mode=True (warn) so pre-dispatch never deadlocks. Flip to hard with
    ``--hard-librarian`` or ``PEER_AMNESIA_GATE=hard`` once agents attach receipts.
    """
    import peer_fact_librarian as fl

    if prefer_librarian is None:
        prefer_librarian, prefer_why = fl.should_prefer_librarian()
    ok_receipt, _receipt, receipt_detail = fl.load_fact_query_receipt()
    if soft_mode is None:
        soft_mode = True

    satisfied = ok_receipt or read_ack_ok
    if not prefer_librarian:
        status = "pass"
        detail = f"prefer_librarian=false — {prefer_why or 'Always-read may suffice'}"
        if ok_receipt:
            detail += f"; {receipt_detail}"
    elif satisfied:
        status = "pass"
        how = receipt_detail if ok_receipt else "always-read ack satisfies receipt"
        detail = f"prefer_librarian=true — {how}"
    elif soft_mode:
        status = "warn"
        detail = (
            f"prefer_librarian=true — soft→require pending: need fact-query receipt "
            f"or always-read ack ({receipt_detail}); use --hard-librarian to block"
        )
    else:
        status = "fail"
        detail = (
            f"prefer_librarian=true — require fact-query receipt or --read-ack "
            f"({receipt_detail})"
        )
    return GateResult(
        gap="Librarian receipt",
        weakness="Amnesia / pack stuffing",
        status=status,
        detail=detail[:220],
        command='./scripts/peer fact-query "…" · plan-gate --read-ack PATH',
    )


def _read_ack_gate(
    *,
    read_ack_ok: bool,
    detail: str,
    prefer_librarian: bool = False,
    soft_mode: bool | None = None,
) -> GateResult:
    if soft_mode is None:
        soft_mode = True
    if read_ack_ok:
        status = "pass"
    elif soft_mode:
        status = "warn"
    else:
        status = "fail"
    _ = prefer_librarian  # reserved: hard-only when prefer + PEER_AMNESIA_GATE=hard
    return GateResult(
        gap="Read-ack",
        weakness="Skips Always-read SoT",
        status=status,
        detail=detail[:200],
        command=(
            "./scripts/peer plan-gate --read-ack "
            "notes/AGENT_WORKING_MEMORY.md,notes/WORK_QUEUE.md,AGENTS.md"
        ),
    )


def _soft_self_correction(title: str, evidence: str = "") -> bool:
    blob = f"{title} {evidence}".lower()
    return any(m in blob for m in _SOFT_SELF_CORRECTION)


@dataclass
class GateResult:
    gap: str
    weakness: str
    status: str  # pass | warn | fail | manual
    detail: str
    command: str

    def format_line(self) -> str:
        icon = {"pass": "✓", "warn": "!", "fail": "✗", "manual": "→"}.get(self.status, "?")
        return f"- [{icon}] **{self.gap}** ({self.weakness}) — {self.detail} · `{self.command}`"


@dataclass
class GateReport:
    phase: str
    role_id: str
    results: list[GateResult] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(r.status == "fail" for r in self.results)

    @property
    def warn_count(self) -> int:
        return sum(1 for r in self.results if r.status == "warn")

    def format_summary(self) -> str:
        lines = [
            f"## Agent gate — {self.phase} ({self.role_id or 'any'})",
            "",
            "**Always-read:** open `notes/AGENT_WORKING_MEMORY.md` + Active "
            "`notes/WORK_QUEUE.md` before acting — chat memory is not SoT.",
            "",
        ]
        for r in self.results:
            lines.append(r.format_line())
        lines.append("")
        if self.blocked:
            lines.append("**BLOCKED** — fix fail rows before editing.")
        elif self.warn_count:
            lines.append(f"**WARN** — {self.warn_count} row(s); address or document before DONE.")
        else:
            lines.append("**Mechanical checks OK** — complete manual rows in persona block.")
        return "\n".join(lines)


def _team_context_fresh(*, max_age_sec: int = 7200) -> tuple[bool, str]:
    path = ROOT / "notes" / "TEAM_CONTEXT.md"
    if not path.is_file():
        return False, "TEAM_CONTEXT.md missing"
    age = time.time() - path.stat().st_mtime
    if age > max_age_sec:
        return False, f"stale {int(age)}s — run team-context --write"
    return True, f"fresh ({int(age)}s old)"


def _last_cycle_ok() -> tuple[bool, str]:
    path = auto.CONFIG_DIR / "peer-loop-state.json"
    if not path.is_file():
        return False, "no peer-loop-state.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "unreadable loop state"
    lc = data.get("last_cycle") if isinstance(data, dict) else None
    if not isinstance(lc, dict):
        return False, "last_cycle missing"
    if lc.get("verify_ok") is False:
        ft = str(lc.get("failure_type") or "").strip().lower()
        note = str(lc.get("note") or "").lower()
        # Soft stall types: heal/dispatch must proceed (never forever-block primary).
        # OVERSEER_AGENT_EXIT_SOFT_VERIFY_OK_2026_09_04 — agent_exit_soft is Episodic warn.
        if ft in (
            "adapt_stale",
            "deferred",
            "timeout",
            "keep_working",
            "not_ready",
            "agent_exit_soft",
        ):
            return True, f"warn: verify_ok=false ({ft}) — dispatch to clear"
        if "adapt_stale" in note or "adapt" in note:
            return True, "warn: verify_ok=false (adapt) — dispatch to clear"
        # Continuous keep-working / verify deferred is intentional — not a tree red.
        if (
            "deferred" in note
            or "not-ready" in note
            or "not ready" in note
            or "keep-working" in note
            or "keep working" in note
        ):
            return True, "warn: verify_ok=false (deferred) — dispatch to clear"
        # Agent exit ≠ tree red — do not forever-block Episodic; Self-correction softens.
        if "cursor-agent" in note or "non-zero" in note:
            return True, "warn: verify_ok=false (agent exit) — dispatch to clear"
        # Hard test/self-check fails still fail Episodic; Self-correction softens them.
        return False, "last_cycle.verify_ok=false"
    return True, "last_cycle present"


def _queue_drift_ok() -> tuple[bool, str]:
    drift = auto.sync_queue_drift(auto.load_context_md(), auto.load_work_queue_md())
    if drift:
        return False, f"{len(drift)} drift line(s) — sync-queue"
    return True, "WORK_QUEUE ↔ context synced"


def _worktree_pool_ok() -> tuple[bool, str]:
    """Pool floor check without forking ``python3 peer_worktree.py list``.

    Pre-dispatch / plan-gate called this every tick; subprocess was ~50–78ms vs
    in-process ``list_worktrees`` ~1–2ms (~35–40×). Same count semantics as CLI
    line count (one WorktreeEntry per worktree).
    """
    try:
        import peer_worktree as wt

        count = len(wt.list_worktrees(ROOT))
        floor = auto.parallel_peer_floor()
        if count < floor:
            return False, f"pool={count} < floor={floor} — ensure-pool"
        return True, f"worktrees={count}"
    except (OSError, RuntimeError) as exc:
        return False, str(exc)[:80]


def _open_miss_assignments() -> tuple[int, str]:
    try:
        import peer_work_assign as wa

        items = wa.list_open_assignments()
        miss = [a for a in items if str(a.get("when", "")).lower() == "miss"]
        if miss:
            return len(miss), f"{len(miss)} assignment(s) when=miss"
        return 0, "no when=miss assignments"
    except Exception as exc:  # noqa: BLE001
        return 0, f"assign check skipped ({exc})"


def _human_only_queue_items() -> tuple[int, str]:
    red_markers = ("paid newsletter", "paid ads", "phase 6", "human only", "human-only")
    open_items = auto.open_work_items().open_items
    hits = [i for i in open_items if any(m in i.lower() for m in red_markers)]
    if hits:
        return len(hits), f"{len(hits)} RED/human-only queue item(s) open"
    return 0, "no human-only launch items in active slice"


def _secret_scan_staged() -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return True, "no staged scan"
        names = [n.strip() for n in proc.stdout.splitlines() if n.strip()]
        for name in names:
            if name.startswith(".env"):
                return False, f"staged {name} — never commit secrets"
            path = ROOT / name
            if not path.is_file() or path.stat().st_size > 200_000:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    return False, f"secret pattern in staged {name}"
        return True, f"staged {len(names)} file(s) clean"
    except OSError as exc:
        return True, f"scan skipped ({exc})"


def _refresh_team_context() -> None:
    try:
        import peer_team_context as tc

        tc.write_team_context()
    except Exception:  # noqa: BLE001
        pass


def _collect_prompt_blocks(*, role_id: str, phase: str) -> list[str]:
    blocks: list[str] = []
    try:
        import peer_memory_span as ms

        blocks.append(ms.format_always_read_block())
    except Exception:  # noqa: BLE001
        blocks.append(
            "**Always-read:** `notes/AGENT_WORKING_MEMORY.md` · "
            "`notes/WORK_QUEUE.md` · `AGENTS.md` — do not rely on chat memory."
        )
    if phase == "plan":
        try:
            import peer_hallucination_guard as hg

            blocks.append(hg.format_strategy_checklist())
            blocks.append(hg.STRATEGIZE_TEMPLATE)
        except Exception:  # noqa: BLE001
            pass
        try:
            import peer_agent_human_gap as gap

            blocks.append(gap.format_human_gap_block(compact=True))
        except Exception:  # noqa: BLE001
            pass
        try:
            import peer_idea_synthesis as idea

            blocks.append(idea.format_idea_synthesis_block(role_id=role_id or None))
        except Exception:  # noqa: BLE001
            pass
        try:
            import peer_critical_thinking as ct

            blocks.append("**Plan gate questions:**")
            for i, q in enumerate(ct.PLAN_QUESTIONS[:3], 1):
                blocks.append(f"{i}. {q}")
        except Exception:  # noqa: BLE001
            pass
    else:
        try:
            import peer_output_compare as oc

            blocks.append("**Done gate — compare before DONE:**")
            for q in oc.COMPARE_QUESTIONS[:2]:
                blocks.append(f"- {q}")
        except Exception:  # noqa: BLE001
            pass
        try:
            import peer_critical_thinking as ct

            blocks.append("**Done gate questions:**")
            for i, q in enumerate(ct.DONE_QUESTIONS[:3], 1):
                blocks.append(f"{i}. {q}")
        except Exception:  # noqa: BLE001
            pass
    return blocks


def run_plan_gate(
    *,
    role_id: str = "",
    refresh: bool = True,
    quick: bool = True,
    read_ack_paths: list[str] | None = None,
    plan_text: str = "",
    write_ack: bool = False,
    soft_librarian: bool | None = None,
) -> GateReport:
    if refresh:
        _refresh_team_context()

    report = GateReport(phase="plan", role_id=role_id)
    import peer_agent_human_gap as gap

    # Mechanical checks mapped to gap rows (by human strength key)
    checks: dict[str, tuple[bool, str]] = {}

    ok, detail = _team_context_fresh()
    checks["Long-term memory"] = (ok, detail)

    ok, detail = _last_cycle_ok()
    checks["Episodic recall"] = (ok, detail)

    ok, detail = _queue_drift_ok()
    checks["Institutional memory"] = (ok, detail)

    ok, detail = _worktree_pool_ok()
    checks["Parallel cognition"] = (ok, detail)

    miss_n, detail = _open_miss_assignments()
    checks["Time awareness"] = (miss_n == 0, detail)

    red_n, detail = _human_only_queue_items()
    checks["Stakeholder judgment"] = (red_n == 0, detail)

    ok, detail = _secret_scan_staged()
    checks["Secret hygiene"] = (ok, detail)

    try:
        import peer_self_diagnose as sd

        findings = sd.run_instant_diagnosis(quick=quick, role_id=role_id)
        critical = [f for f in findings if f.severity in ("critical", "high")]
        soft = [f for f in critical if _soft_self_correction(f.title, f.evidence)]
        hard = [f for f in critical if not _soft_self_correction(f.title, f.evidence)]
        # Autonomy: noop/fingerprint alone must NOT block dispatch (deadlock).
        if hard:
            checks["Self-correction"] = (False, hard[0].title[:100])
        elif soft:
            checks["Self-correction"] = (True, f"warn: {soft[0].title[:80]} — dispatch to clear")
        else:
            checks["Self-correction"] = (True, "diagnose clean (quick)")
    except Exception as exc:  # noqa: BLE001
        checks["Self-correction"] = (False, str(exc)[:80])

    manual_gaps = frozenset(
        {
            "Ground truth sense",
            "Reality check",
            "Skepticism",
            "Attention to detail",
            "Execution bias",
            "Scope discipline",
            "Safety intuition",
            "Tool building",
            "Creativity",
            "Delegation",
            "Accountability",
            "Consistency",
        }
    )

    for human, weak, sym, fix, cmd in gap.GAP_ROWS:
        cmd_primary = cmd.split(" · ")[0].strip()
        if human in checks:
            ok, detail = checks[human]
            status = "pass" if ok else "fail"
            if human == "Stakeholder judgment" and red_n:
                status = "warn"
            if human == "Self-correction" and ok and detail.lower().startswith("warn:"):
                status = "warn"
            report.results.append(
                GateResult(
                    gap=human,
                    weakness=weak,
                    status=status,
                    detail=detail,
                    command=cmd_primary,
                )
            )
        else:
            status = "manual"
            if human == "Creativity":
                detail = "write idea block if proposing novelty"
            elif human == "Ground truth sense":
                detail = "write hallucination strategy before edit"
            elif human in manual_gaps:
                detail = sym[:80]
            else:
                detail = sym[:80]
            report.results.append(
                GateResult(
                    gap=human,
                    weakness=weak,
                    status=status,
                    detail=detail,
                    command=cmd_primary,
                )
            )

    # Scope B amnesia combat: read-ack + librarian-receipt (soft→require when prefer)
    if write_ack or read_ack_paths or plan_text.strip():
        write_always_read_ack(
            read_ack_paths,
            role_id=role_id,
            plan_text=plan_text,
        )
    read_ok, _cited, read_detail = load_always_read_ack(
        extra_paths=read_ack_paths,
        plan_text=plan_text,
    )
    prefer = False
    prefer_why = ""
    try:
        import peer_fact_librarian as fl

        prefer, prefer_why = fl.should_prefer_librarian()
    except Exception as exc:  # noqa: BLE001
        prefer_why = f"prefer check failed ({exc})"
    soft_mode = soft_librarian
    if soft_mode is None:
        env = (os.environ.get("PEER_AMNESIA_GATE") or "").strip().lower()
        if env in ("hard", "require"):
            soft_mode = False
        elif env in ("soft", "warn"):
            soft_mode = True
        else:
            # Safe default: soft warn. Escalate: --hard-librarian / PEER_AMNESIA_GATE=hard
            # (prefer_librarian still surfaces require-ready wording in detail).
            soft_mode = True
    report.results.append(
        _read_ack_gate(
            read_ack_ok=read_ok,
            detail=read_detail,
            prefer_librarian=prefer,
            soft_mode=soft_mode,
        )
    )
    report.results.append(
        _librarian_receipt_gate(
            prefer_librarian=prefer,
            prefer_why=prefer_why,
            read_ack_ok=read_ok,
            soft_mode=soft_mode,
        )
    )

    # Command ecosystem — soft warn on raw python3 scripts/ chains (OVERSEER_COMMAND_ECOSYSTEM_PLAN)
    try:
        import command_ecosystem as ceco

        tip = ceco.raw_script_tip(plan_text)
        if tip:
            report.results.append(
                GateResult(
                    gap="Tool building",
                    weakness="Raw script chain instead of peer command",
                    status="warn",
                    detail=tip[:200],
                    command="./scripts/peer commands-cycle",
                )
            )
    except Exception:  # noqa: BLE001
        pass

    report.blocks = _collect_prompt_blocks(role_id=role_id, phase="plan")
    try:
        import peer_fact_librarian as fl

        report.blocks.append(fl.format_hot_librarian_block())
    except Exception:  # noqa: BLE001
        pass
    report.blocks.append(
        "**Commands:** Prefer `./scripts/peer <id>` "
        "(`./scripts/peer commands-list --pivotal`). "
        "Missing recipe → `./scripts/peer commands-cycle`. "
        "Coverage: `./scripts/peer command-coverage`."
    )
    report.blocks.append(
        "**Amnesia combat (Scope B):** when prefer_librarian, attach a fresh "
        "`fact-query` receipt **or** `--read-ack` citing "
        "`notes/AGENT_WORKING_MEMORY.md`, `notes/WORK_QUEUE.md`, `AGENTS.md` "
        "before first edit. DOMAIN map: `notes/DOMAIN_OWNERS.md`."
    )

    LAST_PLAN_GATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    LAST_PLAN_GATE_JSON.write_text(
        json.dumps(
            {
                "ts": time.time(),
                "role": role_id,
                "blocked": report.blocked,
                "warn": report.warn_count,
                "fail": sum(1 for r in report.results if r.status == "fail"),
                "prefer_librarian": prefer,
                "read_ack_ok": read_ok,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return report


def last_verify_expected_actual() -> tuple[str, str]:
    """Read expected/actual verify lines from peer-loop last_cycle when present."""
    path = auto.CONFIG_DIR / "peer-loop-state.json"
    if not path.is_file():
        return "", ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", ""
    lc = data.get("last_cycle") if isinstance(data, dict) else None
    if not isinstance(lc, dict):
        return "", ""
    expected = str(lc.get("expected_verify") or lc.get("verify_expected") or "")
    if lc.get("verify_ok") is True:
        actual = str(lc.get("verify_detail") or lc.get("tests_detail") or "verify_ok=true")
    else:
        actual = str(lc.get("verify_detail") or lc.get("failure_type") or "")
    return expected.strip(), actual.strip()


def run_done_gate(
    *,
    role_id: str = "",
    expected: str = "",
    actual: str = "",
    quick: bool = True,
) -> GateReport:
    if not expected.strip() or not actual.strip():
        exp_fb, act_fb = last_verify_expected_actual()
        expected = expected.strip() or exp_fb
        actual = actual.strip() or act_fb

    report = GateReport(phase="done", role_id=role_id)

    try:
        import peer_self_diagnose as sd

        findings = sd.run_instant_diagnosis(quick=quick, role_id=role_id)
        critical = [f for f in findings if f.severity in ("critical", "high")]
        report.results.append(
            GateResult(
                gap="Self-correction",
                weakness="Blind to logic errors",
                status="fail" if critical else "pass",
                detail=f"{len(critical)} critical/high" if critical else "diagnose clean",
                command="./scripts/peer diagnose",
            )
        )
    except Exception as exc:  # noqa: BLE001
        report.results.append(
            GateResult(
                gap="Self-correction",
                weakness="Blind to logic errors",
                status="warn",
                detail=str(exc)[:80],
                command="./scripts/peer diagnose",
            )
        )

    ok, detail = _queue_drift_ok()
    report.results.append(
        GateResult(
            gap="Institutional memory",
            weakness="Chat-only teaching",
            status="pass" if ok else "fail",
            detail=detail,
            command="./scripts/peer sync-queue",
        )
    )

    compare_status = "manual"
    compare_detail = "provide --expected and --actual"
    if expected.strip() and actual.strip():
        try:
            import peer_output_compare as oc

            result = oc.compare_outputs(expected=expected, actual=actual)
            compare_status = "pass" if result.match else "fail"
            compare_detail = result.summary[:120]
        except Exception as exc:  # noqa: BLE001
            compare_status = "warn"
            compare_detail = str(exc)[:80]

    report.results.append(
        GateResult(
            gap="Reality check",
            weakness="No embodied world model",
            status=compare_status,
            detail=compare_detail,
            command="./scripts/peer output-compare",
        )
    )

    report.results.append(
        GateResult(
            gap="Accountability",
            weakness="No blame, no ownership",
            status="manual",
            detail="post GLink DONE with paths + expected_vs_actual",
            command="peer_agent_comms bus.jsonl",
        )
    )

    report.results.append(
        GateResult(
            gap="Creativity",
            weakness="Generic ideas / no novelty",
            status="manual",
            detail="idea-record if you proposed novelty this cycle",
            command="./scripts/peer idea-record",
        )
    )

    report.blocks = _collect_prompt_blocks(role_id=role_id, phase="done")
    return report


def write_agent_gates_md() -> Path:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines = [
        "# Agent gates — executable countermeasures",
        "",
        f"_Updated {now}_ · mechanical checks for agent-vs-human gaps",
        "",
        "## Commands",
        "",
        "```bash",
        "./scripts/peer plan-gate --role factory_engineer   # before first edit",
        "./scripts/peer done-gate --role factory_engineer \\",
        '  --expected "exit 0" --actual "exit 0"            # before DONE',
        "./scripts/peer pre-dispatch                        # includes plan-gate",
        "./scripts/peer post-cycle                          # includes done-gate",
        "```",
        "",
        "## Plan gate (mechanical)",
        "",
        "- Refresh TEAM_CONTEXT",
        "- Queue drift scan",
        "- Diagnose quick (block on critical/high)",
        "- Worktree pool floor",
        "- Secret pattern scan on staged files",
        "- **Read-ack** — plan cites Always-read paths "
        "(`AGENT_WORKING_MEMORY`, `WORK_QUEUE`, `AGENTS.md`)",
        "- **Librarian receipt** — when prefer_librarian, require fresh "
        "`fact-query` receipt **or** always-read ack (soft→hard)",
        "- Print hallucination strategy + human gap + idea synthesis blocks",
        "",
        "```bash",
        "./scripts/peer fact-query \"noop plan-gate\"   # writes receipt",
        "./scripts/peer plan-gate --role factory_engineer \\",
        "  --read-ack notes/AGENT_WORKING_MEMORY.md,notes/WORK_QUEUE.md,AGENTS.md",
        "./scripts/peer domain-owners --write           # notes/DOMAIN_OWNERS.md",
        "```",
        "",
        "## Done gate (mechanical)",
        "",
        "- Diagnose quick",
        "- Queue drift",
        "- Output compare when --expected/--actual provided",
        "- Done self-check + learn-record reminders",
        "",
        "_Gap matrix: notes/AGENT_VS_HUMAN.md_ · amnesia: `notes/AGENT_AMNESIA_RESEARCH.md` Scope B",
    ]
    AGENT_GATES_MD.parent.mkdir(parents=True, exist_ok=True)
    AGENT_GATES_MD.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return AGENT_GATES_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Executable agent-vs-human gate runner")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--plan-gate", action="store_true")
    parser.add_argument("--done-gate", action="store_true")
    parser.add_argument("--role", default="")
    parser.add_argument("--expected", default="")
    parser.add_argument("--actual", default="")
    parser.add_argument("--no-refresh", action="store_true")
    parser.add_argument("--full", action="store_true", help="Full diagnose (not quick)")
    parser.add_argument(
        "--read-ack",
        action="append",
        default=[],
        help="Always-read path(s) opened/cited (comma-ok; repeatable)",
    )
    parser.add_argument(
        "--plan-text",
        default="",
        help="Plan body text — must cite Always-read paths (read-ack gate)",
    )
    parser.add_argument(
        "--plan-file",
        type=Path,
        default=None,
        help="Read plan text from file for read-ack citations",
    )
    parser.add_argument(
        "--write-ack",
        action="store_true",
        help="Persist always-read ack from --read-ack / --plan-text",
    )
    parser.add_argument(
        "--soft-librarian",
        action="store_true",
        help="Force soft (warn) librarian-receipt even when prefer_librarian",
    )
    parser.add_argument(
        "--hard-librarian",
        action="store_true",
        help="Force hard (fail) librarian-receipt / read-ack when missing",
    )
    args = parser.parse_args()
    role = args.role.strip() or os.environ.get("PEER_ROLE", "").strip() or "orchestrator"

    plan_text = (args.plan_text or "").strip()
    if args.plan_file and args.plan_file.is_file():
        try:
            plan_text = args.plan_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass

    soft_librarian: bool | None = None
    if args.soft_librarian:
        soft_librarian = True
    elif args.hard_librarian:
        soft_librarian = False

    if args.plan_gate:
        report = run_plan_gate(
            role_id=role,
            refresh=not args.no_refresh,
            quick=not args.full,
            read_ack_paths=list(args.read_ack or []),
            plan_text=plan_text,
            write_ack=bool(args.write_ack or args.read_ack or plan_text),
            soft_librarian=soft_librarian,
        )
        print(report.format_summary())
        for block in report.blocks:
            if block.strip():
                print("")
                print(block)
        return 1 if report.blocked else 0

    if args.done_gate:
        report = run_done_gate(
            role_id=role,
            expected=args.expected,
            actual=args.actual,
            quick=not args.full,
        )
        print(report.format_summary())
        for block in report.blocks:
            if block.strip():
                print("")
                print(block)
        return 1 if report.blocked else 0

    path = write_agent_gates_md()
    print(f"agent-gates: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
