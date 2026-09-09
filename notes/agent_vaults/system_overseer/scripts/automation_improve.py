#!/usr/bin/env python3
"""Driver: harden the *work* automation so it can amplify top-tier OSS into monsters.

Investment thesis: this kit is **capex** — a robust outcome machine that will later
ingest elite open-source projects, run native verify, isolate work in worktrees/PRs,
and leave irreversible artifacts. Improve forever must enqueue only **executable
factory work** toward that capability — never strategy essays, ASI chrome, or
self-polish of this file.

Hard rule: **improve does not improve itself.** Forever ticks heal and enqueue
work-kit upgrades for peer_loop / adapt / verify / worktrees. Horizon/prompts are
status output only.

Usage:
  python3 scripts/automation_improve.py              # plan + execute prompts
  python3 scripts/automation_improve.py --plan       # plan only (no code yet)
  python3 scripts/automation_improve.py --execute    # execute prompt (after plan)
  python3 scripts/automation_improve.py --write      # save prompts under ~/.config/<namespace>/
  python3 scripts/automation_improve.py --json       # machine-readable signals + prompts
  python3 scripts/automation_improve.py --research   # include industry trends in prompts
  python3 scripts/automation_improve.py --forever    # heal → enqueue → wake peer
  python3 scripts/automation_improve.py --install    # LaunchAgent daemon (improve forever)
  python3 scripts/automation_improve.py --uninstall  # remove improve LaunchAgent
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import textwrap
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import automation_config as cfg_mod  # noqa: E402
import project_automation as auto  # noqa: E402


class _LazyAdapt:
    """Defer automation_adapt (~+6 MB) until heal/audit — continuous stays lean."""

    _mod = None

    def __getattr__(self, name: str):
        if type(self)._mod is None:
            import automation_adapt as _adapt  # noqa: E402

            type(self)._mod = _adapt
        return getattr(type(self)._mod, name)


class _LazyTrendResearch:
    """Defer automation_research (~+3 MB) until --research / trend merge."""

    _mod = None

    def __getattr__(self, name: str):
        if type(self)._mod is None:
            import automation_research as _tr  # noqa: E402

            type(self)._mod = _tr
        return getattr(type(self)._mod, name)


adapt = _LazyAdapt()
trend_research = _LazyTrendResearch()

ROOT = auto.ROOT
CONFIG_DIR = auto.CONFIG_DIR
PLAN_PATH = CONFIG_DIR / "automation-improve-plan.md"
EXECUTE_PATH = CONFIG_DIR / "automation-improve-execute.md"
COMBINED_PATH = CONFIG_DIR / "automation-improve.md"
WRITE_PROMPTS_FP_PATH = CONFIG_DIR / "improve-prompts.fp"
HORIZON_PATH = CONFIG_DIR / "IMPROVE_HORIZON.md"
HORIZON_REPO_PATH = ROOT / "notes" / "IMPROVE_HORIZON.md"
HORIZON_JSON_PATH = CONFIG_DIR / "improve-horizon.json"
LOG_PATH = CONFIG_DIR / "improve-loop.log"
IMPROVE_LABEL = f"com.togi.{auto.CFG.get('config_namespace', 'automation-hub')}-improve-loop"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{IMPROVE_LABEL}.plist"
REGISTRY_PATH = ROOT / "repos" / "registry.json"

GOALS = ("monster", "better", "faster", "smoother", "easier")
# Investment north star — factory that amplifies top-tier OSS (not ASI theater).
INVESTMENT_NORTH_STAR = (
    "Robust outcome machine: adapt → native verify → worktree/PR isolation → "
    "irreversible artifact on top-tier open source — repeatedly, without babysitting"
)
# Legacy ASI string kept for dashboard/rubric compatibility (secondary meter only).
ASI_NORTH_STAR = (
    "100% true Artificial Super Intelligence (ASI) — "
    "generalization, autonomy, and orchestration beyond any system achievable by today's standards"
)
# Display scale for raw→pct only (NOT a cap preventing ASI).
ASI_SCALE_PCT = 100
# Backward-compat alias (prefer ASI_SCALE_PCT).
ASI_LOCAL_CEILING_PCT = ASI_SCALE_PCT
_LAST_CYCLE_KEYS = (
    "ts",
    "rc",
    "verify_ok",
    "queue_fp",
    "queue_fp_before",
    "noop",
    "git_head",
    "note",
)
# Event wait heartbeat when forever — keep driving work kit without busy-spin.
CONTINUOUS_WAKE_SEC = float(auto.CFG.get("improve_wake_sec") or 60.0)
FALLBACK_POLL_SEC = 300.0
ENQUEUE_CAP = 2  # legacy default; prefer improve_enqueue_cap()


def improve_enqueue_cap() -> int:
    return auto.improve_enqueue_cap()
LOCAL_CYCLE_TIMEOUT_SEC = 90.0


def improve_continuous_wake_sec() -> float:
    """Short heartbeat when factory work remains — matches peer continuous keep-working.

    Floor is 15s so DGX overlays (improve_continuous_wake_sec=3) cannot restore
    hyper poll after dgx_install_services.sh copies scripts/dgx_speed.local.json.
    """
    try:
        return max(
            15.0,
            float(
                auto.CFG.get("improve_continuous_wake_sec")
                or auto.CFG.get("continuous_wake_sec")
                or 15.0
            ),
        )
    except (TypeError, ValueError):
        return 15.0


def improve_idle_wake_sec() -> float:
    try:
        return max(30.0, float(auto.CFG.get("improve_idle_wake_sec") or auto.CFG.get("improve_wake_sec") or 120.0))
    except (TypeError, ValueError):
        return 120.0


def improve_continuous_min_cycle_sec() -> float:
    try:
        return max(10.0, float(auto.CFG.get("improve_continuous_min_cycle_sec") or 10.0))
    except (TypeError, ValueError):
        return 10.0


# Floor between forever ticks when idle (no open work).
MIN_CYCLE_GAP_SEC = float(auto.CFG.get("improve_min_cycle_sec") or 45.0)
# Dirty tree blocks peer dispatch — treat as NOW factory work (worktrees/commit).
GIT_UNBLOCK_PRIORITY = 4

# Work kit allowlist — improve may enqueue / heal toward these only.
WORK_KIT_MARKERS = (
    "peer_loop",
    "peer_orchestrate",
    "peer_transcript",
    "peer_terminal",
    "peer_worktree",
    "run_peer_tasks",
    "peer_tasks",
    "cursor_self_improve",
    "worktree",
    "verify",
    "orchestrat",
    "template_match",
    "coordinator",
    "noop backoff",
    "last_cycle",
    "self-check",
    "self-heal",
    "harness",
    "mcp",
    "adapt",
    "queue",
    "loop gate",
    "peer matching",
    "hot path",
    "parallel task",
    "subagent",
    "maximize peers",
    "registry",
    "external",
    "open source",
    "oss",
    "native verify",
    "irreversible",
    "artifact",
    "pull request",
    "dirty tree",
    "dirty-tree",
    "unblock dirty",
    "single peer",
    "launchagent",
    "monster",
    "factory",
    "peer_flaw_scan",
    "flaw scan",
    "flaw_scan",
    "peer_debrief",
    "debrief",
    "peer_agent_board",
    "agent board",
    "agent_roles",
    "optimization unit",
    "operating_system",
    "SOP_INDEX",
    "DEBRIEF_LOG",
)

# Self / meta / strategy denylist — never enqueue as peer work.
SELF_TARGET_MARKERS = (
    "automation_improve",
    "improve forever",
    "improve prompt",
    "improve cli",
    "improve launchagent",
    "horizon board",
    "horizon cosmetic",
    "asi board",
    "asi 100%",
    "[asi 100%]",
    "true artificial superintelligence",
    "crown-era",
    "time bomb",
    "competition ladder",
    "exit readiness",
    "meta-exit",
    "shared primitives",  # strategy essay form — use concrete auth/billing tasks instead
    "philosophy",
    "automation_comms_improve",
    "comms improve forever",
    "comms horizon",
    "comms_improve",
    "notes/comms_horizon",
    "notes/comms_trends",
    "notes/loop_strategy",
)


@dataclass
class Opportunity:
    category: str  # asi | speed | smooth | ease | efficiency | better
    title: str
    detail: str
    priority: int = 50


@dataclass
class AsiProgress:
    pct: int
    label: str
    scale: int  # display scale for raw→pct (100); not a philosophical cap
    raw: float
    dimensions: list[dict[str, Any]]
    phases: list[dict[str, Any]] = field(default_factory=list)
    current_phase_id: str = ""
    next_plan: str | None = None

    @property
    def ceiling(self) -> int:
        """Alias for scale (legacy JSON / dashboard keys)."""
        return self.scale


@dataclass
class ImproveSignals:
    live: dict[str, Any]
    audit_ok: bool
    audit_warnings: list[str]
    audit_errors: list[str]
    queue_drift: list[str]
    loop_state: dict[str, Any]
    trend_report: dict[str, Any] = field(default_factory=dict)
    research_sync: str = ""
    opportunities: list[Opportunity] = field(default_factory=list)


def _script_text(name: str) -> str:
    path = SCRIPTS / name
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _dim(name: str, score: float, weight: float, evidence: str) -> dict[str, Any]:
    return {
        "name": name,
        "score": max(0.0, min(1.0, float(score))),
        "weight": float(weight),
        "evidence": evidence,
    }


def _asi_progress_bar(pct: int, width: int = 20) -> str:
    """Fill proportional to displayed pct on a 0–100 scale."""
    filled = int(round(width * max(0, min(100, pct)) / 100.0))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def compute_asi_progress(signals: ImproveSignals) -> AsiProgress:
    """Phased rubric toward ASI — runtime-honest criteria; complete one phase, plan the next."""
    from asi_rubric import compute_asi_rubric

    result = compute_asi_rubric(signals)
    return AsiProgress(
        pct=result.pct,
        label=result.label,
        scale=ASI_SCALE_PCT,
        raw=result.raw,
        dimensions=result.dimensions,
        phases=result.phases,
        current_phase_id=result.current_phase_id,
        next_plan=result.next_plan,
    )


def _empty_improve_signals() -> ImproveSignals:
    return ImproveSignals(
        live={},
        audit_ok=False,
        audit_warnings=[],
        audit_errors=[],
        queue_drift=[],
        loop_state={},
    )


# Deprecated empty-signals ASI snapshot — was eager at import and always pulled
# asi_rubric (~+3 MB sticky RSS) into every improve/dashboard consumer.
# COMPRESSION_LAZY_ASI_EMPTY_2026_09_04 — resolve only on attribute access.
def __getattr__(name: str) -> Any:
    if name in ("_ASI_EMPTY", "ASI_PROGRESS_PCT", "ASI_PROGRESS_LABEL"):
        snap = compute_asi_progress(_empty_improve_signals())
        if name == "_ASI_EMPTY":
            return snap
        if name == "ASI_PROGRESS_PCT":
            return snap.pct
        return snap.label
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _opp_blob(opp: Opportunity) -> str:
    return f"{opp.category} {opp.title} {opp.detail}".lower()


def is_self_target(opp: Opportunity) -> bool:
    """True when the opportunity is meta/strategy/ASI chrome — not factory work."""
    if opp.category == "asi":
        return True
    blob = _opp_blob(opp)
    return any(marker in blob for marker in SELF_TARGET_MARKERS)


def is_work_kit_target(opp: Opportunity) -> bool:
    """True when the opportunity hardens the OSS-monster factory (peer/adapt/verify/worktree)."""
    if is_self_target(opp):
        return False
    blob = _opp_blob(opp)
    return any(marker in blob for marker in WORK_KIT_MARKERS)


def _registry_factory_gaps() -> list[Opportunity]:
    """Surface unaudited / needs-kit registry entries as external-proof work."""
    if auto.factory_meter_mode() != "external_proof":
        return []
    if not REGISTRY_PATH.is_file():
        return []
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    repos = data.get("repos") if isinstance(data, dict) else None
    if not isinstance(repos, list):
        return []
    gaps: list[Opportunity] = []
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        name = str(repo.get("name") or repo.get("path") or "").strip()
        status = str(repo.get("status") or "").lower()
        priority_label = str(repo.get("priority") or "")
        if not name or name.lower() in ("automation hub",):
            continue
        if status in ("unaudited", "needs-kit-install", "git") or priority_label == "ship":
            gaps.append(
                Opportunity(
                    category="monster",
                    title=f"External proof: adapt + native verify on {name}",
                    detail=(
                        f"registry status={status or '?'} — run automation_adapt on that repo; "
                        "use its native verify; prefer worktree/PR isolation; leave an irreversible artifact."
                    ),
                    priority=16 if status in ("needs-kit-install", "active-loop-running") else 22,
                )
            )
        if len(gaps) >= 3:
            break
    return gaps


def _factory_default_opportunities() -> list[Opportunity]:
    """When green: enqueue factory readiness — not kit cosmetics."""
    if auto.factory_meter_mode() == "self_sufficient":
        opps = [
            Opportunity(
                category="speed",
                title="Command Builder — compound one repetitive dev loop",
                detail=(
                    "Run ./scripts/peer commands-build; edit ONLY peer_commands.py + scripts/peer; "
                    "finish with ./scripts/peer commands-sync. See notes/COMMAND_BUILDER.md."
                ),
                priority=8,
            ),
            Opportunity(
                category="smooth",
                title="Prove improve→peer closed loop",
                detail=(
                    "Improve forever must hand_out roles, enqueue kit work, and wake peer every cycle "
                    "without human poke. Confirm in improve-loop.log + peer-loop-state last_cycle."
                ),
                priority=12,
            ),
            Opportunity(
                category="smooth",
                title="Self-heal clears bottlenecks without human",
                detail=(
                    "./scripts/peer self-heal --write — zero high-severity registry entries; "
                    "mechanical heals for daemons, drift, locks, noop stall."
                ),
                priority=14,
            ),
            Opportunity(
                category="speed",
                title="Pre-dispatch before every agent spawn",
                detail=(
                    "compact → check → ensure-pool — raise per-cycle yield; "
                    "avoid hyper-wake spin when queue is small."
                ),
                priority=18,
            ),
            Opportunity(
                category="smooth",
                title="Oversight + playbook on stagnation events",
                detail=(
                    "peer_oversight_events triggers dispatch on noop/verify/daemon drift; "
                    "AGENT_ERROR_PLAYBOOK records fixes from self-heal."
                ),
                priority=22,
            ),
        ]
        return opps
    return [
        Opportunity(
            category="monster",
            title="External proof target — one OSS adapt→verify→worktree loop",
            detail=(
                "Pick one top-tier OSS (or registry entry). Run adapt → native verify → "
                "worktree PR isolation twice without human babysitting. peer_loop / adapt / peer_worktree."
            ),
            priority=14,
        ),
        Opportunity(
            category="smooth",
            title="Irreversible artifact gate in peer_loop",
            detail=(
                "Cycle success = PR-shaped diff or verify advance that changes queue fingerprint — "
                "not prompt rewrite / noop. Wire into peer_loop last_cycle + noop backoff."
            ),
            priority=18,
        ),
        Opportunity(
            category="speed",
            title="Worktree isolation for disjoint Implement peers",
            detail=(
                "peer_worktree: spawn/use parallel trees so dirty main tree cannot stall dispatch; "
                "maximize parallel Task peers on independent scopes."
            ),
            priority=24,
        ),
        Opportunity(
            category="smooth",
            title="Single peer LaunchAgent for Automation Hub",
            detail=(
                "One peer_loop daemon owns this kit outcome path — stop dual-brain with a sibling "
                "ram-peer-loop copy; keep scripts/peer_loop.py as source of truth."
            ),
            priority=26,
        ),
    ]

def _parse_done_item(stripped: str) -> str | None:
    if not auto._is_done_line(stripped):
        return None
    text = re.sub(r"^-\s*\[x\]\s*", "", stripped, flags=re.IGNORECASE)
    text = re.sub(r"^\d+\.\s*\[x\]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\*\*", "", text).strip()
    return text or None


def queue_known_keys(*, work_md: str | None = None, context_md: str | None = None) -> set[str]:
    """Normalized keys for open + done items (skip re-enqueue / re-plan)."""
    work_md = work_md if work_md is not None else auto.load_work_queue_md()
    context_md = context_md if context_md is not None else auto.load_context_md()
    keys: set[str] = set()
    for md in (work_md, context_md):
        if not md:
            continue
        for line in md.splitlines():
            stripped = line.strip()
            done = _parse_done_item(stripped)
            if done:
                keys.add(auto._normalize_queue_key(done))
                continue
            open_item = auto._parse_work_item(stripped)
            if open_item:
                keys.add(auto._normalize_queue_key(open_item))
    return keys


def _trend_already_shipped(raw: dict[str, Any], known: set[str]) -> bool:
    theme = str(raw.get("title", "") or raw.get("theme", ""))
    detail = str(raw.get("detail", "") or raw.get("opportunity", ""))
    for blob in (theme, detail, f"{theme} {detail}"):
        if blob and auto._normalize_queue_key(blob) in known:
            return True
        # Fuzzy: any known key that shares a strong token from the theme
        norm = auto._normalize_queue_key(blob)
        if not norm:
            continue
        for key in known:
            if len(key) >= 12 and (key in norm or norm in key):
                return True
    return False


def filter_work_opportunities(opps: list[Opportunity]) -> list[Opportunity]:
    """Drop self/meta targets; keep work-kit upgrades (and non-enqueue advisory items stay ranked separately)."""
    return [o for o in opps if is_work_kit_target(o)]


def _insert_bullet_under_heading(md: str, heading_prefix: str, bullet: str) -> str:
    """Insert a `- [ ]` bullet under the first matching ## heading; dedupe by normalize key."""
    lines = md.splitlines()
    item_text = auto._parse_work_item(bullet.strip()) or bullet
    norm = auto._normalize_queue_key(item_text)
    out: list[str] = []
    i = 0
    inserted = False
    while i < len(lines):
        line = lines[i]
        out.append(line)
        if not inserted and line.strip().startswith(heading_prefix):
            i += 1
            section: list[str] = []
            while i < len(lines) and not lines[i].startswith("## "):
                section.append(lines[i])
                i += 1
            for existing in section:
                parsed = auto._parse_work_item(existing.strip()) or _parse_done_item(existing.strip())
                if parsed and auto._normalize_queue_key(parsed) == norm:
                    out.extend(section)
                    inserted = True
                    break
            if not inserted:
                # Keep blank lead-in; append bullet before next heading
                if section and section[-1].strip() == "":
                    body, trail = section[:-1], [""]
                else:
                    body, trail = section, [""]
                out.extend(body)
                if body and body[-1].strip() != "":
                    pass
                out.append(bullet)
                out.extend(trail)
                inserted = True
            continue
        i += 1
    if not inserted:
        out.extend(["", heading_prefix.rstrip(), "", bullet, ""])
    return "\n".join(out).rstrip() + "\n"


def _run_local_cycle_bounded(*, log_fn: Callable[[str], None]) -> list[str]:
    """Spawn local verify in its own process group; kill the group on timeout."""
    actions: list[str] = []

    def _local_log(msg: str) -> None:
        log_fn(f"mechanical local: {msg}")

    cmd = [
        sys.executable,
        "-c",
        (
            "import sys; sys.path.insert(0, %r); "
            "import run_peer_tasks as r; "
            "r.run_local_cycle(quick=True, log_fn=print)"
        )
        % str(SCRIPTS),
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=LOCAL_CYCLE_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        actions.append("local-cycle: timeout")
        log_fn(f"mechanical: local cycle timed out after {LOCAL_CYCLE_TIMEOUT_SEC:.0f}s")
        return actions

    for line in (stdout or "").splitlines()[-5:]:
        _local_log(line)
    if proc.returncode != 0:
        tail = (stderr or stdout or "").strip().splitlines()
        if tail:
            _local_log(tail[-1])
        actions.append(f"local-cycle: rc={proc.returncode}")
        log_fn(f"mechanical: local cycle rc={proc.returncode}")
    else:
        actions.append("local-cycle: ok")
        log_fn("mechanical: local cycle ok")
    return actions


def apply_mechanical(
    signals: ImproveSignals,
    *,
    log_fn: Callable[[str], None],
    run_verify: bool = True,
) -> list[str]:
    """Local work-kit heals — never treats rewriting improve prompts as success."""
    actions: list[str] = []
    try:
        import peer_self_heal as self_heal

        if self_heal.self_heal_enabled():
            report = self_heal.run_cycle(write=True, log_fn=log_fn)
            for act in report.actions:
                actions.append(f"self-heal: {act}")
            if report.bottlenecks:
                log_fn(
                    f"self-heal: {len(report.bottlenecks)} bottleneck(s), "
                    f"{len(report.actions)} heal action(s)"
                )
    except Exception as exc:  # noqa: BLE001
        log_fn(f"self-heal: scan/heal failed ({exc})")

    # Autonomy: clear noop stall + wake peer so plan-gate cannot deadlock.
    try:
        state_path = auto.CONFIG_DIR / "peer-loop-state.json"
        if state_path.is_file():
            data = json.loads(state_path.read_text(encoding="utf-8"))
            lc = data.get("last_cycle") if isinstance(data, dict) else None
            if isinstance(lc, dict) and lc.get("noop"):
                removed, _ = auto.compact_executable_queue(write=True, max_active=12)
                wake_peer(log_fn=log_fn)
                lc["noop"] = False
                lc["noop_cleared_by_improve"] = True
                data["last_cycle"] = lc
                state_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                actions.append(f"noop-break: compact={removed}; peer woken")
                log_fn("mechanical: noop stall cleared — peer woken")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"mechanical: noop-break failed ({exc})")

    # Application autonomy — product forge when active; scrub orphans when not.
    # OVERSEER_SCRUB_ORPHAN_FORGE_IMPROVE_2026_09_04 — stop_forge left CaaS
    # agents running; improve only dispatched while active → never scrubbed.
    try:
        import peer_product_forge as forge

        if forge.forge_active():
            report = forge.run_forge_cycle(log_fn=log_fn, dispatch=True)
            launched = int(report.get("launched") or 0)
            if launched:
                actions.append(f"product-forge: +{launched}")
                log_fn(f"mechanical: product-forge +{launched}")
        else:
            scrubbed = forge.scrub_orphan_forge_agents(log_fn=log_fn)
            if scrubbed:
                actions.append(f"product-forge: scrubbed {scrubbed} orphan(s)")
                log_fn(f"mechanical: product-forge scrubbed {scrubbed}")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"mechanical: product-forge ({exc})")

    # Never idle on open work: adapt gate/agent stalls every improve tick.
    try:
        import peer_error_adapt as err_adapt

        drive = err_adapt.ensure_driving(log_fn=log_fn, quick=True)
        for act in (drive.get("actions") or [])[:4]:
            actions.append(f"error-adapt:{act}")
        if drive.get("actions"):
            log_fn(f"mechanical: error-adapt {', '.join(str(a) for a in drive['actions'][:4])}")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"mechanical: error-adapt ({exc})")

    # Compression: skip automation_adapt import when no drift + recent fresh check.
    if not signals.queue_drift and adapt_heal_check_fresh():
        log_fn("mechanical: adapt heal TTL-skip (no import)")
        actions.append("adapt-heal: ttl-skip")
    else:
        try:
            if signals.queue_drift:
                healed, _warns = adapt.heal_queue_drift(root=ROOT, write=True)
                for a in healed:
                    actions.append(f"queue-drift: {a}")
                    log_fn(f"mechanical: {a}")
                if not healed:
                    actions.append("queue-drift: checked (no write)")
                    log_fn("mechanical: queue drift present but nothing written")
        except Exception as exc:  # noqa: BLE001
            log_fn(f"mechanical: queue drift heal failed ({exc})")

        try:
            if adapt.should_re_adapt(ROOT):
                # Subprocess: long-lived improve must not keep pre-refuse-null save_adapt_state.
                report = adapt.run_heal_fresh(write=True, quick=True)
                msg = f"adapt heal fresh ({len(report.actions)} action(s))"
                actions.append(msg)
                log_fn(f"mechanical: {msg}")
            else:
                mark_adapt_heal_check()
                log_fn("mechanical: adapt fingerprint fresh — skip heal")
        except Exception as exc:  # noqa: BLE001
            log_fn(f"mechanical: adapt heal failed ({exc})")

    if not run_verify:
        # Errors must not delay autonomy — bypass verify cooldown when failing/blocked.
        bypass = False
        try:
            import peer_error_adapt as err_adapt

            if err_adapt.never_delay_on_error():
                import peer_transcript as transcript

                st = transcript.load_state()
                lc = st.get("last_cycle") if isinstance(st.get("last_cycle"), dict) else {}
                if isinstance(lc, dict) and lc.get("verify_ok") is False:
                    bypass = True
                else:
                    import peer_oversight_events as oevents

                    if oevents.scan_live_error_hits(max_age_sec=90.0):
                        bypass = True
                if bypass:
                    err_adapt.clear_autonomy_delays(log_fn=log_fn, reason="verify-cooldown-bypass")
                    log_fn("mechanical: verify cooldown bypassed — error present")
        except Exception:  # noqa: BLE001
            bypass = False
        if not bypass:
            actions.append("local-cycle: skipped (verify cooldown)")
            log_fn("mechanical: local cycle skipped (verify cooldown)")
            return actions

    # OVERSEER_IMPROVE_SKIP_LOCAL_CYCLE_SWARM_2026_09_04 — under agent swarm,
    # run_local_cycle only burns quiet-wait (≤90s) then defers. That blocks
    # wake-peer evidence → factory self-sufficient loops crater. Skip; peer
    # heal-all verifies when quiet.
    try:
        import peer_parallel_dispatch as ppd
        import run_peer_tasks as rpt

        agent_cap, _max_tests = rpt._verify_quiet_limits()
        agents = len(ppd.find_agent_procs())
        if agents > agent_cap:
            actions.append(f"local-cycle: skipped (swarm agents={agents}/{agent_cap})")
            log_fn(
                f"mechanical: local cycle skipped — swarm agents={agents}/{agent_cap} "
                "(would only defer after quiet-wait)"
            )
            return actions
    except Exception:  # noqa: BLE001
        pass

    try:
        actions.extend(_run_local_cycle_bounded(log_fn=log_fn))
    except Exception as exc:  # noqa: BLE001
        log_fn(f"mechanical: local cycle failed ({exc})")

    return actions


def enqueue_work_opportunities(
    signals: ImproveSignals,
    *,
    log_fn: Callable[[str], None],
    cap: int | None = None,
) -> list[str]:
    """Push work-kit NOW/NEXT opps into WORK_QUEUE + context; skip self-targets."""
    if cap is None:
        cap = improve_enqueue_cap()
    inserted: list[str] = []
    work_path = auto.WORK_QUEUE_PATH
    ctx_path = auto.CONTEXT_PATH if hasattr(auto, "CONTEXT_PATH") else ROOT / "scripts" / "self_improve_context.md"
    # Resolve paths via adapt helpers when available
    try:
        ctx_path, work_path = adapt._queue_paths(ROOT)
    except Exception:  # noqa: BLE001
        pass

    work_md = auto.load_work_queue_md() if work_path.is_file() else ""
    context_md = auto.load_context_md() if ctx_path.is_file() else ""
    known = queue_known_keys(work_md=work_md, context_md=context_md)

    candidates = [
        o
        for o in signals.opportunities
        if is_work_kit_target(o) and _horizon_tier(o.priority) in ("NOW", "NEXT")
    ]
    for opp in candidates:
        if len(inserted) >= cap:
            break
        title = opp.title
        # Strip leading [trend] for cleaner queue lines
        display = re.sub(r"^\[trend\]\s*", "", title, flags=re.IGNORECASE).strip()
        line_body = f"**{display}** — {opp.detail}"
        norm = auto._normalize_queue_key(line_body)
        if norm in known or auto._normalize_queue_key(display) in known:
            log_fn(f"enqueue: skip duplicate {display[:60]}")
            continue
        bullet = f"- [ ] {line_body}"
        work_md = _insert_bullet_under_heading(work_md, "## Active", bullet)
        context_md = _insert_bullet_under_heading(
            context_md, "## Remaining work", bullet
        )
        known.add(norm)
        known.add(auto._normalize_queue_key(display))
        inserted.append(display)
        log_fn(f"enqueue: {display[:80]}")

    if inserted:
        work_path.parent.mkdir(parents=True, exist_ok=True)
        ctx_path.parent.mkdir(parents=True, exist_ok=True)
        work_path.write_text(work_md if work_md.endswith("\n") else work_md + "\n")
        ctx_path.write_text(context_md if context_md.endswith("\n") else context_md + "\n")
    return inserted


_horizon_json_phase_cache: tuple[tuple[int, int], str | None] | None = None


def _load_previous_asi_phase_id() -> str | None:
    """Read last written horizon JSON for phase-transition detection (before overwrite)."""
    global _horizon_json_phase_cache
    if not HORIZON_JSON_PATH.is_file():
        return None
    try:
        st = HORIZON_JSON_PATH.stat()
        witness = (st.st_mtime_ns, st.st_size)
    except OSError:
        return None
    if _horizon_json_phase_cache and _horizon_json_phase_cache[0] == witness:
        return _horizon_json_phase_cache[1]
    try:
        data = json.loads(HORIZON_JSON_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        _horizon_json_phase_cache = (witness, None)
        return None
    asi = data.get("asi")
    if not isinstance(asi, dict):
        _horizon_json_phase_cache = (witness, None)
        return None
    pid = asi.get("current_phase_id")
    phase_id = str(pid) if pid else None
    _horizon_json_phase_cache = (witness, phase_id)
    return phase_id


def _queue_paths_for_enqueue() -> tuple[Path, Path]:
    work_path = auto.WORK_QUEUE_PATH
    ctx_path = (
        auto.CONTEXT_PATH
        if hasattr(auto, "CONTEXT_PATH")
        else ROOT / "scripts" / "self_improve_context.md"
    )
    try:
        ctx_path, work_path = adapt._queue_paths(ROOT)
    except Exception:  # noqa: BLE001
        pass
    return ctx_path, work_path


def _insert_phase_queue_bullet(
    *,
    display: str,
    detail: str,
    dedupe_keys: list[str],
    log_fn: Callable[[str], None],
) -> str | None:
    """Insert one Active / Remaining-work bullet if none of the dedupe keys match."""
    ctx_path, work_path = _queue_paths_for_enqueue()
    work_md = work_path.read_text(encoding="utf-8") if work_path.is_file() else ""
    context_md = ctx_path.read_text(encoding="utf-8") if ctx_path.is_file() else ""
    known = queue_known_keys(work_md=work_md, context_md=context_md)

    line_body = f"**{display}** — {detail}"
    norms = [auto._normalize_queue_key(line_body), auto._normalize_queue_key(display)]
    norms.extend(auto._normalize_queue_key(k) for k in dedupe_keys)
    if any(n in known for n in norms):
        log_fn(f"enqueue: skip duplicate phase plan ({display[:60]})")
        return None

    bullet = f"- [ ] {line_body}"
    work_md = _insert_bullet_under_heading(work_md, "## Active", bullet)
    context_md = _insert_bullet_under_heading(context_md, "## Remaining work", bullet)
    work_path.parent.mkdir(parents=True, exist_ok=True)
    ctx_path.parent.mkdir(parents=True, exist_ok=True)
    work_path.write_text(work_md if work_md.endswith("\n") else work_md + "\n")
    ctx_path.write_text(context_md if context_md.endswith("\n") else context_md + "\n")
    log_fn(f"enqueue: phase plan ({display[:80]})")
    return display


def enqueue_phase_plan(
    signals: ImproveSignals,
    *,
    log_fn: Callable[[str], None],
    previous_phase_id: str | None = None,
) -> str | None:
    """Keep autonomy continuous: plan active phase; on MET→advance, plan the next section.

    Call with ``previous_phase_id`` captured *before* ``write_horizon`` so transitions
    are visible after the horizon JSON is overwritten.
    """
    from asi_rubric import format_phase_advance_plan, work_kit_plan_for_phase

    asi = compute_asi_progress(signals)
    phase_id = asi.current_phase_id
    if not phase_id:
        return None

    prev = previous_phase_id
    advanced = bool(prev and prev != phase_id)

    if advanced:
        # Asymptotic phase 5 is not factory work — never enqueue.
        if phase_id == "general_autonomy" or prev == "general_autonomy":
            log_fn("enqueue: skip asymptotic general_autonomy advance")
            return None
        detail = format_phase_advance_plan(prev, phase_id)
        display = f"[factory:{phase_id}] {prev} complete → next"
        probe = Opportunity("smooth", display, detail, 15)
        blob = detail.lower()
        if not is_work_kit_target(probe) and not any(
            m in blob for m in ("peer", "verify", "worktree", "adapt", "queue", "orchestr")
        ):
            log_fn(f"enqueue: skip non-factory phase advance ({phase_id})")
            return None
        return _insert_phase_queue_bullet(
            display=display,
            detail=detail,
            dedupe_keys=[
                f"factory phase advance {prev} to {phase_id}",
                f"asi phase advance {prev} to {phase_id}",
            ],
            log_fn=log_fn,
        )

    plan = asi.next_plan or work_kit_plan_for_phase(phase_id)
    if not plan:
        return None
    # Skip re-planning asymptotic general_autonomy theater every tick.
    if phase_id == "general_autonomy":
        log_fn("enqueue: skip asymptotic general_autonomy plan (not factory work)")
        return None
    display = f"[factory:{phase_id}] Harden active capability"
    probe = Opportunity("smooth", display, plan, 15)
    blob = plan.lower()
    if not is_work_kit_target(probe) and not any(
        m in blob for m in ("peer", "verify", "worktree", "adapt", "queue", "orchestr")
    ):
        log_fn(f"enqueue: skip non-factory phase plan ({phase_id})")
        return None
    return _insert_phase_queue_bullet(
        display=display,
        detail=plan,
        dedupe_keys=[f"factory phase {phase_id}", f"asi phase {phase_id}"],
        log_fn=log_fn,
    )


def wake_peer(*, log_fn: Callable[[str], None]) -> None:
    try:
        import automation_team as team

        hint = team.team_wake_hint()
        if hint:
            log_fn(hint)
    except Exception:  # noqa: BLE001
        pass
    try:
        import peer_transcript as transcript

        transcript.SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        transcript.SIGNAL_PATH.touch()
        log_fn(f"wake peer: touched {transcript.SIGNAL_PATH.name}")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"wake peer: failed ({exc})")


def _has_continuous_work(signals: ImproveSignals) -> bool:
    """True when improve should keep cycling like peer continuous mode."""
    work_opps = [o for o in signals.opportunities if is_work_kit_target(o)]
    if work_opps:
        return True
    try:
        queue = auto.loop_work_items()
        return bool(queue.open_items)
    except Exception:  # noqa: BLE001
        live_items = signals.live.get("open_items") if isinstance(signals.live, dict) else None
        return bool(live_items)


def improve_wake_timeout(*, has_work: bool, elapsed: float) -> float:
    """Event wait: short heartbeat when work remains; longer when idle."""
    base = improve_continuous_wake_sec() if has_work else improve_idle_wake_sec()
    min_gap = improve_continuous_min_cycle_sec() if has_work else MIN_CYCLE_GAP_SEC
    if elapsed < min_gap:
        return max(base, min_gap - elapsed)
    return base


_LOOP_STATE_PATH = CONFIG_DIR / "peer-loop-state.json"
_loop_state_cache: tuple[tuple[int, int], dict[str, Any]] | None = None


def _load_loop_state() -> dict[str, Any]:
    """Peer-loop state — mtime witness cache cuts JSON parse on improve hot path."""
    global _loop_state_cache
    path = _LOOP_STATE_PATH
    if not path.is_file():
        return {}
    try:
        st = path.stat()
        witness = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if _loop_state_cache and _loop_state_cache[0] == witness:
        return _loop_state_cache[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        data = {}
    _loop_state_cache = (witness, data)
    return data


_SCRIPTS_DIR = ROOT / "scripts"
_TESTS_DIR = ROOT / "tests"
_script_inventory_cache: tuple[tuple[int, int, int, int], dict[str, int]] | None = None


def _script_inventory_witness() -> tuple[int, int, int, int]:
    """Dir mtime/size witness — glob scripts/tests only on cache miss."""
    parts: list[int] = []
    for base in (_SCRIPTS_DIR, _TESTS_DIR):
        try:
            st = base.stat()
            parts.extend([st.st_mtime_ns, st.st_size])
        except OSError:
            parts.extend([0, 0])
    return (parts[0], parts[1], parts[2], parts[3])


def _script_inventory() -> dict[str, int]:
    global _script_inventory_cache
    witness = _script_inventory_witness()
    if _script_inventory_cache and _script_inventory_cache[0] == witness:
        return _script_inventory_cache[1]
    scripts_dir = _SCRIPTS_DIR
    tests_dir = _TESTS_DIR
    py_scripts = list(scripts_dir.glob("*.py")) if scripts_dir.is_dir() else []
    py_tests = list(tests_dir.glob("test_*.py")) if tests_dir.is_dir() else []
    inv = {
        "scripts": len(py_scripts),
        "test_modules": len(py_tests),
    }
    _script_inventory_cache = (witness, inv)
    return inv


def _read_cached_audit() -> tuple[bool, list[str], list[str]]:
    """Read last adapt audit from disk — digest hot path avoids re-scanning the tree."""
    path = CONFIG_DIR / "adapt-audit.json"
    if not path.is_file():
        return True, [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False, [], ["audit cache unreadable"]
    ok = bool(data.get("ok", True))
    warnings: list[str] = []
    errors: list[str] = []
    for raw in data.get("findings") or []:
        if not isinstance(raw, dict):
            continue
        level = str(raw.get("level") or "")
        msg = f"[{raw.get('category', '?')}] {raw.get('message', '')}"
        if level == "error":
            errors.append(msg)
        elif level == "warn":
            warnings.append(msg)
    return ok, warnings, errors


# Compression: stamp after fingerprint-fresh heal check.
# COMPRESSION_ADAPT_TTL_2026_09_04 — TTL-skip adapt audit/heal imports on forever ticks.
# Half-stamp (call sites without helpers) caused NameError every improve cycle.
_ADAPT_HEAL_CHECK_PATH = CONFIG_DIR / "improve-adapt-heal-check.ts"
_ADAPT_AUDIT_CACHE_PATH = CONFIG_DIR / "adapt-audit.json"


def improve_adapt_cache_ttl_sec() -> float:
    """TTL for cached adapt-audit / heal-fresh checks (seconds)."""
    try:
        raw = auto.CFG.get("improve_adapt_cache_ttl_sec")
        if raw is None:
            return 60.0
        return max(5.0, float(raw))
    except (TypeError, ValueError):
        return 60.0


def adapt_audit_cache_fresh() -> bool:
    """True when adapt-audit.json exists and is younger than TTL."""
    path = _ADAPT_AUDIT_CACHE_PATH
    if not path.is_file():
        return False
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return age < improve_adapt_cache_ttl_sec()


def should_live_adapt_audit() -> bool:
    """True when forever tick should run a live adapt audit (not TTL cache)."""
    return not adapt_audit_cache_fresh()


# OVERSEER_ADAPT_HEAL_HELPERS_2026_09_04 — hub half-stamp had call sites for
# adapt_heal_check_fresh / mark_adapt_heal_check without defs → NameError every
# apply_mechanical tick ("mechanical: failed (...)"); peer-6 had helpers.
# Without these, improve forever still cycles but adapt TTL-skip is broken and
# stamp overlays can leave hub unable to skip heal imports cleanly.
def adapt_heal_check_fresh() -> bool:
    """True when a fingerprint-fresh heal skip was recorded within TTL."""
    path = _ADAPT_HEAL_CHECK_PATH
    if not path.is_file():
        return False
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return age < improve_adapt_cache_ttl_sec()


def mark_adapt_heal_check() -> None:
    """Record fingerprint-fresh heal skip so next ticks can TTL-skip adapt import."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _ADAPT_HEAL_CHECK_PATH.write_text(f"{time.time()}\n", encoding="utf-8")
    except OSError:
        pass


def gather_signals(
    *,
    quick: bool = True,
    research: bool = False,
    refresh_trends: bool = False,
    digest_only: bool = False,
    audit: bool = True,
    live_state: auto.LiveState | None = None,
) -> ImproveSignals:
    if live_state is not None:
        queue = auto.loop_work_items(live=live_state)
        live = auto.live_snapshot(live_state, queue)
    else:
        live_state = auto.measure_live_state(quick=quick)
        queue = auto.loop_work_items(live=live_state)
        live = auto.live_snapshot(live_state, queue)

    context_md = auto.load_context_md()
    work_md = auto.load_work_queue_md()
    drift = auto.sync_queue_drift(context_md, work_md)

    audit_warnings: list[str] = []
    audit_errors: list[str] = []
    audit_ok = True
    if digest_only or not audit:
        audit_ok, audit_warnings, audit_errors = _read_cached_audit()
    else:
        try:
            audit_report = adapt.run_audit(ROOT, quick=quick, audit_self=False)
            audit_ok = audit_report.ok
            audit_warnings = [f"[{f.category}] {f.message}" for f in audit_report.warnings()]
            audit_errors = [f"[{f.category}] {f.message}" for f in audit_report.errors()]
        except Exception as exc:  # noqa: BLE001
            audit_ok = False
            audit_errors.append(f"audit failed: {exc}")

    loop_state = _load_loop_state()
    trend_report: dict[str, Any] = {}
    if not digest_only and (research or refresh_trends):
        trend_report = trend_research.build_trend_report(refresh=refresh_trends)
        if refresh_trends:
            trend_research.write_trends_md(trend_report)

    research_sync = ""
    if not digest_only and audit:
        try:
            import peer_dual_research as dr

            if dr.cooldown_remaining() <= 0:
                dr.run_research_cycle(log_fn=lambda _m: None, digest_only=True, force=True)
            research_sync = dr.load_sync_brief()
        except Exception:  # noqa: BLE001
            pass

    signals = ImproveSignals(
        live=live,
        audit_ok=audit_ok,
        audit_warnings=audit_warnings,
        audit_errors=audit_errors,
        queue_drift=drift,
        loop_state=loop_state,
        trend_report=trend_report,
        research_sync=research_sync,
    )
    if digest_only:
        signals.opportunities = []
    else:
        signals.opportunities = rank_opportunities(signals, trend_report=trend_report)
    return signals


def _merge_trend_opportunities(
    opps: list[Opportunity],
    trend_report: dict[str, Any],
    *,
    known: set[str] | None = None,
) -> list[Opportunity]:
    if not trend_report:
        return opps
    known = known if known is not None else queue_known_keys()
    seen_titles = {o.title.lower() for o in opps}
    for raw in trend_research.trends_to_opportunities(trend_report):
        title = str(raw.get("title", ""))
        if title.lower() in seen_titles:
            continue
        if _trend_already_shipped(raw, known):
            continue
        cand = Opportunity(
            category=str(raw.get("category", "ease")),
            title=title,
            detail=str(raw.get("detail", "")),
            priority=int(raw.get("priority", 50)),
        )
        if is_self_target(cand):
            continue
        opps.append(cand)
    return opps


def _merge_research_opportunities(
    opps: list[Opportunity],
    *,
    known: set[str] | None = None,
) -> list[Opportunity]:
    try:
        import peer_dual_research as dr
    except ImportError:
        return opps
    known = known if known is not None else queue_known_keys()
    seen_titles = {o.title.lower() for o in opps}
    for raw in dr.findings_to_opportunities(known=known):
        title = str(raw.get("title", ""))
        if not title or title.lower() in seen_titles:
            continue
        cand = Opportunity(
            category=str(raw.get("category", "efficiency")),
            title=title,
            detail=str(raw.get("detail", "")),
            priority=int(raw.get("priority", 30)),
        )
        if is_self_target(cand):
            continue
        opps.append(cand)
        seen_titles.add(title.lower())
    return opps


def rank_opportunities(signals: ImproveSignals, *, trend_report: dict[str, Any] | None = None) -> list[Opportunity]:
    opps: list[Opportunity] = []
    known = queue_known_keys()

    if not signals.live.get("tests_ok"):
        opps.append(Opportunity(
            category="smooth",
            title="Fix failing tests",
            detail=signals.live.get("tests", "tests not ok"),
            priority=5,
        ))

    # Dirty tree — continue_on_dirty keeps coding; still prefer hygiene / worktree.
    if not signals.live.get("git_clean"):
        opps.append(Opportunity(
            category="smooth",
            title="Unblock dirty tree for peer_loop dispatch",
            detail=(
                f"{signals.live.get('git', 'dirty tree')} — continue_on_dirty keeps coding "
                "(worktree isolate or dirty-main fallback). Still commit/stash WIP when safe."
            ),
            priority=GIT_UNBLOCK_PRIORITY,
        ))

    for err in signals.audit_errors:
        if "only in self_improve_context" in err or "only in notes/WORK_QUEUE" in err:
            continue
        opps.append(Opportunity(
            category="smooth",
            title="Resolve audit error",
            detail=err,
            priority=10,
        ))

    for warn in signals.audit_warnings:
        if "drift" in warn.lower():
            opps.append(Opportunity(
                category="smooth",
                title="Fix automation drift",
                detail=warn,
                priority=15,
            ))
        elif "stale" in warn.lower() or "fingerprint" in warn.lower():
            # Cached audit can still say "fingerprint stale" after heal; only
            # enqueue when live should_re_adapt() is true (OVERSEER_READAPT_GATE).
            if adapt.should_re_adapt(ROOT):
                opps.append(Opportunity(
                    category="efficiency",
                    title="Re-adapt after git changes",
                    detail=f"{warn} — run ./scripts/peer adapt",
                    priority=20,
                ))
        else:
            opps.append(Opportunity(
                category="ease",
                title="Clear audit warning",
                detail=warn,
                priority=35,
            ))

    for d in signals.queue_drift:
        if "only in self_improve_context" in d or "only in notes/WORK_QUEUE" in d:
            continue
        opps.append(Opportunity(
            category="smooth",
            title="Sync WORK_QUEUE ↔ context",
            detail=d,
            priority=12,
        ))

    last = signals.loop_state.get("last_cycle") or {}
    if last.get("noop"):
        opps.append(Opportunity(
            category="efficiency",
            title="Break noop loop — shrink queue to executable factory work",
            detail=(
                "Last cycle ok but queue fingerprint unchanged. Drop strategy essays; "
                "advance via worktree PR / verify that changes the queue — peer_loop + peer_worktree."
            ),
            priority=11,
        ))
    if last.get("verify_ok") is False:
        opps.append(Opportunity(
            category="smooth",
            title="Fix post-agent verify gate",
            detail=last.get("note") or "verify failed after last agent cycle",
            priority=9,
        ))

    opps.extend(_registry_factory_gaps())

    inv = _script_inventory()
    if inv["test_modules"] < max(3, inv["scripts"] // 4):
        opps.append(Opportunity(
            category="ease",
            title="Expand automation test coverage",
            detail=(
                f"{inv['test_modules']} test modules for {inv['scripts']} scripts — "
                "add tests for peer_loop / orchestrate / verify / worktree hot paths."
            ),
            priority=40,
        ))

    work_relevant = [o for o in opps if is_work_kit_target(o)]
    if not work_relevant:
        opps.extend(_factory_default_opportunities())

    opps = _merge_trend_opportunities(
        opps, trend_report or signals.trend_report, known=known
    )
    opps = _merge_research_opportunities(opps, known=known)
    try:
        import automation_team as team

        team_titles = {o.title.lower() for o in opps}
        for to in team.rank_team_opportunities(known):
            if to.title.lower() in team_titles:
                continue
            opps.append(
                Opportunity(
                    category=to.category,
                    title=to.title,
                    detail=to.detail,
                    priority=to.priority,
                )
            )
            team_titles.add(to.title.lower())
    except Exception:  # noqa: BLE001
        pass
    # Board-only ASI destination — never enqueued (category asi → self_target).
    # OVERSEER_ASI_KEEP_AFTER_TRIM_2026_09_04 — priority 99 must survive [:12] factory trim.
    asi_board = Opportunity(
        category="asi",
        title="[ASI 100%] True artificial superintelligence",
        detail=(
            f"{ASI_NORTH_STAR}. Secondary meter only — investment north star is the "
            f"OSS monster factory: {INVESTMENT_NORTH_STAR}."
        ),
        priority=99,
    )
    opps.sort(key=lambda o: o.priority)
    trimmed = opps[:12]
    if not any(o.category == "asi" for o in trimmed):
        trimmed.append(asi_board)
    return trimmed



def build_plan_prompt(signals: ImproveSignals) -> str:
    work_opps = [o for o in signals.opportunities if is_work_kit_target(o)]
    show = work_opps or signals.opportunities
    opp_lines = "\n".join(
        f"        {i + 1}. **[{o.category}]** {o.title} — {o.detail}"
        for i, o in enumerate(show[:8])
    )
    live = signals.live
    asi = compute_asi_progress(signals)
    trend_block = ""
    if signals.trend_report:
        gaps = signals.trend_report.get("gap_count", 0)
        partials = signals.trend_report.get("partial_count", 0)
        trend_block = textwrap.dedent(
            f"""

        ## Industry trends (factory patterns)

        - Curated patterns: {signals.trend_report.get("curated_count", 0)} · gaps: {gaps} · partial: {partials}
        - Prefer worktrees, native verify, self-healing CI — patterns that harden external-repo delivery
        - Read `notes/AUTOMATION_TRENDS.md`; skip polish that does not raise P(success on hard OSS)
        """
        )
    research_block = ""
    if signals.research_sync:
        brief = signals.research_sync.strip()
        if len(brief) > 1200:
            brief = brief[:1180] + "\n… [truncated]"
        research_block = textwrap.dedent(
            f"""

        ## Dual research sync (efficiency + output)

        Read `notes/RESEARCH_SYNC.md` — both lanes run synchronously each cycle.
        Findings enqueue as `[efficiency-research]` / `[output-research]` for peer dispatch.

        ```
        {brief}
        ```
        """
        )
    body = textwrap.dedent(
        f"""\
        # Automation improvement — PLAN FIRST (OSS monster factory)

        **Investment north star:** {INVESTMENT_NORTH_STAR}

        **Secondary meter (not the mission):** `{asi.label}` — harness health only; never chase ASI chrome.

        **Goal this cycle:** One irreversible factory step — adapt/native-verify/worktree/PR capability
        that will later amplify top-tier open source. No strategy essays. No horizon cosmetics.

        **Non-negotiable:** Orchestration between agents yields results fastest — **never tackle anything solo.**
        **Maximize parallel Task subagents** — **8 workers, one niche each** — launch full peer set in ONE message.

        Do **not** write code in this phase. Produce a short, actionable plan only.

        ## Current signals

        - Git: {live.get("git", "?")}
        - Tests: {live.get("tests", "?")}
        - Queue source: {live.get("queue_source", "?")} ({len(live.get("open_items") or [])} open)
        - Adapt audit: {"ok" if signals.audit_ok else "issues"}
        - Queue drift: {len(signals.queue_drift)} warning(s){trend_block}{research_block}

        ## Ranked factory opportunities (work-kit only)

        {opp_lines}

        ## Plan requirements

        1. Read `notes/OPERATING_SYSTEM.md`, `notes/AGENT_ROLES.md`, `notes/AUTOMATION.md`, `notes/PEER_ORCHESTRATION.md`.
        2. Pick disjoint-scope **executable** items — dirty-tree unblock, worktrees, native verify, external proof, flaw scan, debriefs.
        3. Reject queue/philosophy items that peers cannot ship as diffs.
        4. Output: **Problem**, **Peer batch (8 niches)**, **Files**, **Verify**, **Irreversible artifact**, **Risks**.
        5. Prefer minimal diffs in `scripts/` — extend peer_loop / adapt / worktree / verify / flaw_scan / debrief.
        6. If only one change fits, still spawn parallel Verify + niche peers — never solo implement.
        7. Success = factory readiness up, not ASI % up.

        ## Success criteria

        - Measurable factory win (dispatch unblocked, worktree path real, external adapt works, noop broken)
        - `python3 scripts/peer_orchestrate.py --self-check` stays green
        - `python3 scripts/automation_adapt.py --audit --quick` stays green
        """
    ).strip()
    try:
        import automation_team as team

        return body + "\n\n" + team.format_team_block(quick=True)
    except Exception:  # noqa: BLE001
        return body


def build_execute_prompt(signals: ImproveSignals, *, plan_path: Path | None = None) -> str:
    plan_ref = str(plan_path) if plan_path and plan_path.is_file() else "the plan you just wrote"
    work_opps = [o for o in signals.opportunities if is_work_kit_target(o)]
    top = (work_opps or signals.opportunities)[:3]
    focus = "\n".join(f"        - [{o.category}] {o.title}" for o in top) or "        - (follow approved plan)"
    asi = compute_asi_progress(signals)

    exec_body = textwrap.dedent(
        f"""\
        # Automation improvement — EXECUTE (OSS monster factory)

        **Investment north star:** {INVESTMENT_NORTH_STAR}

        **Secondary meter:** `{asi.label}` — ignore as a goal; ship factory capability.

        Implement {plan_ref}. **No plan-only markdown** — land working diffs via **parallel peers**.

        **Non-negotiable:** Do **not** implement solo. **8 workers, one niche each** — launch the full peer set in **one** message, then Safety/Verify.

        ## Focus (factory opportunities)

        {focus}

        ## Execution rules

        1. **Maximize parallel Task peers** — 8 niche Task peers for independent scopes (`notes/AGENT_ROLES.md`).
        2. **Team setup** — flaw scan when due; debriefs on noop/fail; Queue Steward syncs WORK_QUEUE.
        3. **Minimal diff** — smallest change that raises external-outcome readiness.
        4. **Verify always** after merge:
           - `python3 scripts/peer_orchestrate.py --self-check`
           - `python3 -m unittest discover -s tests -q`
           - `python3 scripts/automation_adapt.py --audit --quick`
        5. Sync `notes/WORK_QUEUE.md` ↔ `scripts/self_improve_context.md` if queue items change.
        6. Run `./scripts/peer adapt` when automation scripts or profiles change.
        7. peer_loop auto-commits after verify — do not commit manually unless fixing a message.
        8. **Artifact** — leave something irreversible (behavior change, worktree path, verify gate) — not a prompt rewrite.

        ## Dimensions (local steps toward the monster factory)

        - **Monster** — adapt + native verify + worktree/PR on an external/registry target
        - **Faster** — less wall time per cycle (cache, parallel peers, skip redundant probes)
        - **Smoother** — no dirty-tree deadlock, no noop thrash, single peer daemon
        - **Easier** — clearer defaults for foreign repos
        - **Better** — stronger tests on peer_loop / adapt / worktree / verify

        Never treat ASI % as mission complete. Orchestrate peers now — never solo.
        """
    ).strip()
    try:
        import automation_team as team

        return exec_body + "\n\n" + team.format_team_block(quick=True)
    except Exception:  # noqa: BLE001
        return exec_body


def build_combined_prompt(signals: ImproveSignals) -> str:
    plan_body = build_plan_prompt(signals)
    execute_body = build_execute_prompt(signals, plan_path=PLAN_PATH)
    return plan_body + "\n\n---\n\n" + execute_body


def write_prompts_ttl_sec() -> float:
    """Skip ASI rebuild when fingerprint+files are fresh (default 120s)."""
    try:
        raw = auto.CFG.get("write_prompts_ttl_sec")
        if raw is None:
            return 120.0
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 120.0


def _signals_prompt_fingerprint(signals: ImproveSignals) -> str:
    """Stable fingerprint of signals that affect plan/execute prompt bodies.

    COMPRESSION_ZLIB_WRITE_PROMPTS_FP_2026_09_04 — zlib adler+crc (16 hex)
    keeps improve path libcrypto-free; collision resistance not required for
    write_prompts TTL skip (same as queue_fingerprint).
    OVERSEER_IMPROVE_HUB_ZLIB_FP_2026_09_04 — hub must carry this needle so
    run_improve_poll_cache does not swap the full peer-6 improve body (which
    poisoned CONFIG_DIR via peer research path-insert).
    """
    import zlib

    payload = {
        "audit_ok": signals.audit_ok,
        "audit_warnings": list(signals.audit_warnings or []),
        "audit_errors": list(signals.audit_errors or []),
        "queue_drift": list(signals.queue_drift or []),
        "live": signals.live if isinstance(signals.live, dict) else {},
        "opps": [
            (o.category, o.title, o.detail, o.priority) for o in (signals.opportunities or [])
        ],
        "research_sync": signals.research_sync or "",
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    raw = blob.encode("utf-8")
    return f"{zlib.adler32(raw) & 0xffffffff:08x}{zlib.crc32(raw) & 0xffffffff:08x}"


def _write_prompts_cache_fresh(
    fp: str, *, want_plan: bool, want_execute: bool, want_combined: bool
) -> bool:
    """True when on-disk prompts + fp match and TTL has not expired."""
    ttl = write_prompts_ttl_sec()
    if ttl <= 0:
        return False
    needed: list[Path] = []
    if want_plan or want_combined:
        needed.append(PLAN_PATH)
    if want_execute or want_combined:
        needed.append(EXECUTE_PATH)
    if want_combined:
        needed.append(COMBINED_PATH)
    if not needed or not all(p.is_file() for p in needed):
        return False
    if not WRITE_PROMPTS_FP_PATH.is_file():
        return False
    try:
        data = json.loads(WRITE_PROMPTS_FP_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if str(data.get("fp") or "") != fp:
        return False
    try:
        ts = float(data.get("ts") or 0)
    except (TypeError, ValueError):
        return False
    return (time.time() - ts) < ttl


def _save_write_prompts_fp(fp: str) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        WRITE_PROMPTS_FP_PATH.write_text(
            json.dumps({"fp": fp, "ts": time.time()}) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _write_text_if_changed(path: Path, text: str) -> bool:
    """Write ``text`` only when bytes differ. Return True if the file changed."""
    try:
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.write_text(text, encoding="utf-8")
    return True


def write_prompts(
    signals: ImproveSignals,
    *,
    plan: bool,
    execute: bool,
    combined: bool,
) -> list[str]:
    """Write plan/execute/combined prompts.

    Build each body at most once (combined reuses plan+execute strings — avoids
    4× ``compute_asi_progress`` / ``asi_rubric`` via ``build_combined_prompt``).
    Skip rewrite when on-disk bytes already match.
    OVERSEER_WRITE_PROMPTS_TTL_2026_09_04 — skip ASI rebuild when fp+TTL fresh.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fp = _signals_prompt_fingerprint(signals)
    if _write_prompts_cache_fresh(
        fp, want_plan=plan, want_execute=execute, want_combined=combined
    ):
        out: list[str] = []
        if plan or combined:
            out.append(str(PLAN_PATH))
        if execute or combined:
            out.append(str(EXECUTE_PATH))
        if combined:
            out.append(str(COMBINED_PATH))
        return out
    written: list[str] = []
    plan_body: str | None = None
    execute_body: str | None = None
    if plan or combined:
        plan_body = build_plan_prompt(signals)
    if execute or combined:
        execute_body = build_execute_prompt(signals, plan_path=PLAN_PATH)
    if plan or combined:
        assert plan_body is not None
        _write_text_if_changed(PLAN_PATH, plan_body + "\n")
        written.append(str(PLAN_PATH))
    if execute or combined:
        assert execute_body is not None
        _write_text_if_changed(EXECUTE_PATH, execute_body + "\n")
        written.append(str(EXECUTE_PATH))
    if combined:
        assert plan_body is not None and execute_body is not None
        combined_body = plan_body + "\n\n---\n\n" + execute_body
        _write_text_if_changed(COMBINED_PATH, combined_body + "\n")
        written.append(str(COMBINED_PATH))
    _save_write_prompts_fp(fp)
    return written


def _horizon_tier(priority: int) -> str:
    if priority >= 90:
        return "ASI"
    if priority <= 20:
        return "NOW"
    if priority <= 40:
        return "NEXT"
    return "HORIZON"


def _horizon_tiers() -> tuple[tuple[str, str, str], ...]:
    if auto.factory_meter_mode() == "self_sufficient":
        return (
            (
                "NOW",
                "NOW — prove self-sufficiency",
                "Daemons, improve→peer loop, verify, self-heal, noop break — no external OSS required",
            ),
            (
                "NEXT",
                "NEXT — harden autonomy",
                "Oversight events, playbook, pre-dispatch, queue hygiene, flaw scan",
            ),
            (
                "HORIZON",
                "OVER THE HORIZON — deferred",
                "External OSS proof + registry monster sprints — after self-sufficient meter is green",
            ),
            (
                "ASI",
                "100% ASI — secondary destination (not the mission)",
                "Harness meter only — current build targets self-sufficient automation",
            ),
        )
    return (
        ("NOW", "NOW — unblock factory first", "Dirty tree, verify fail, noop, external proof blockers"),
        ("NEXT", "NEXT — ship this week", "Worktrees, single daemon, artifact gates, registry adapt"),
        ("HORIZON", "OVER THE HORIZON — bigger bets", "Industry-shaped direction; only if it raises external P(success)"),
        (
            "ASI",
            "100% ASI — secondary destination (not the mission)",
            "Harness meter only — investment north star is the OSS monster factory",
        ),
    )


def build_horizon_markdown(signals: ImproveSignals, *, cycle: int | None = None) -> str:
    """Human-readable major-changes-over-the-horizon board."""
    live = signals.live
    asi = compute_asi_progress(signals)
    bar = _asi_progress_bar(asi.pct)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    by_tier: dict[str, list[Opportunity]] = {"NOW": [], "NEXT": [], "HORIZON": [], "ASI": []}
    for o in signals.opportunities:
        by_tier[_horizon_tier(o.priority)].append(o)

    meter_mode = auto.factory_meter_mode()
    north = auto.factory_north_star()
    north_heading = (
        "## Current build — self-sufficient automation"
        if meter_mode == "self_sufficient"
        else "## Investment north star — OSS monster factory"
    )
    north_blurb = (
        "Improve forever enqueues **executable kit work** only "
        "(peer loop, verify, self-heal, oversight, queue hygiene). "
        "External OSS proof is deferred until the self-sufficient meter is green."
        if meter_mode == "self_sufficient"
        else (
            "Improve forever enqueues **executable factory work** only "
            "(adapt / native verify / worktrees / peer dispatch). "
            "Strategy essays and ASI chrome are not work."
        )
    )

    lines = [
        "# Improve horizon — major changes coming",
        "",
        f"_Updated {now}_"
        + (f" · cycle {cycle}" if cycle is not None else "")
        + " · rewritten each improve forever tick",
        "",
        north_heading,
        "",
        f"**Target:** {north}",
        "",
        north_blurb,
        "",
        "## Secondary meter — harness rubric (not the mission)",
        "",
        f"**Progress (phased rubric):** `{asi.pct}%`  `{bar}`  **not the investment goal**",
        "",
        f"_{asi.label}_",
        "",
        f"_Legacy ASI destination (board only): {ASI_NORTH_STAR}_",
        "",
        "## Live",
        "",
        f"| Signal | Value |",
        f"|--------|-------|",
        f"| Git | {live.get('git', '?')} |",
        f"| Tests | {live.get('tests', '?')} |",
        f"| Queue | {live.get('queue_source', '?')} · {len(live.get('open_items') or [])} open |",
        f"| Adapt audit | {'ok' if signals.audit_ok else 'ISSUES'} |",
        f"| Drift warnings | {len(signals.queue_drift)} |",
        f"| Harness rubric | {asi.pct}% (secondary) |",
        f"| Active phase | `{asi.current_phase_id or '—'}` |",
        "",
        "## Phased rubric (secondary)",
        "",
        "Complete one phase, then plan the next. "
        f"`pct = (completed phases + active phase partial) / 4 × 100` — "
        "phase 5 (general autonomy) is asymptotic. "
        "See `notes/ASI_RUBRIC.md`. Prefer factory opportunities in NOW/NEXT over chasing this meter.",
        "",
    ]
    if asi.next_plan:
        lines.append(f"**Next plan:** {asi.next_plan}")
        lines.append("")
    for phase in asi.phases:
        status = phase.get("status", "?")
        title = phase.get("title", phase.get("id", "phase"))
        score = float(phase.get("score", 0))
        icon = {"complete": "✓", "active": "→", "locked": "·", "asymptotic": "∞"}.get(status, "?")
        lines.append(f"### {icon} {title} ({status}, {score:.0%})")
        lines.append("")
        if phase.get("summary"):
            lines.append(f"_{phase['summary']}_")
            lines.append("")
        for c in phase.get("criteria") or []:
            cs = float(c.get("score", 0))
            mark = "x" if cs >= 1.0 else " "
            lines.append(
                f"- [{mark}] **{c.get('title', c.get('id', ''))}** — {c.get('evidence', '')}"
            )
        lines.append("")
    lines.extend([f"_raw={asi.raw:.3f} → {asi.pct}%_", ""])

    if signals.audit_errors:
        lines.append("### Audit errors")
        for e in signals.audit_errors[:5]:
            lines.append(f"- {e}")
        lines.append("")

    for tier, title, blurb in _horizon_tiers():
        items = by_tier.get(tier) or []
        lines.append(f"## {title}")
        lines.append("")
        lines.append(f"_{blurb}_")
        lines.append("")
        if not items:
            lines.append("_None this cycle._")
            lines.append("")
            continue
        for i, o in enumerate(items, 1):
            lines.append(f"{i}. **[{o.category}]** {o.title}")
            lines.append(f"   - {o.detail}")
            lines.append(f"   - priority `{o.priority}`")
        lines.append("")

    trends = signals.trend_report or {}
    if trends:
        lines.append("## Industry map")
        lines.append("")
        lines.append(
            f"Curated **{trends.get('curated_count', 0)}** · "
            f"gaps **{trends.get('gap_count', 0)}** · "
            f"partial **{trends.get('partial_count', 0)}**"
        )
        lines.append("")
        for raw in trends.get("trends") or []:
            if raw.get("kit_status") == "have":
                continue
            status = str(raw.get("kit_status", "?")).upper()
            lines.append(f"- **[{status}]** {raw.get('theme')}: {raw.get('opportunity')}")
        lines.append("")
        lines.append("Full sources: `notes/AUTOMATION_TRENDS.md`")
        lines.append("")

    open_items = live.get("open_items") or []
    if open_items:
        lines.append("## Queue peek")
        lines.append("")
        for item in open_items[: auto.max_parallel_peers()]:
            lines.append(f"- {item}")
        lines.append("")

    try:
        import automation_team as team

        lines.append(team.format_team_block(quick=True))
        lines.append("")
    except Exception:  # noqa: BLE001
        pass

    lines.extend([
        "## Where to dig",
        "",
        f"- Combined prompt: `{COMBINED_PATH}`",
        f"- Plan only: `{PLAN_PATH}`",
        f"- Execute: `{EXECUTE_PATH}`",
        f"- Loop log: `{LOG_PATH}`",
        "",
        "```bash",
        "./scripts/peer improve-status   # horizon + daemon",
        "./scripts/peer improve-watch    # live refresh of this board",
        "```",
        "",
    ])
    return "\n".join(lines)


def horizon_payload(signals: ImproveSignals, *, cycle: int | None = None) -> dict[str, Any]:
    """Machine-readable horizon board (includes ASI progress meter)."""
    asi = compute_asi_progress(signals)
    return {
        "updated_at": datetime.now().isoformat(),
        "cycle": cycle,
        "live": signals.live,
        "audit_ok": signals.audit_ok,
        "opportunities": [asdict(o) for o in signals.opportunities],
        "tiers": {
            "NOW": [asdict(o) for o in signals.opportunities if _horizon_tier(o.priority) == "NOW"],
            "NEXT": [asdict(o) for o in signals.opportunities if _horizon_tier(o.priority) == "NEXT"],
            "HORIZON": [asdict(o) for o in signals.opportunities if _horizon_tier(o.priority) == "HORIZON"],
            "ASI": [asdict(o) for o in signals.opportunities if _horizon_tier(o.priority) == "ASI"],
        },
        "asi": {
            "north_star": ASI_NORTH_STAR,
            "investment_north_star": INVESTMENT_NORTH_STAR,
            "progress_pct": asi.pct,
            "progress_label": asi.label,
            "scale": asi.scale,
            "ceiling": asi.scale,  # legacy alias — display scale only, not a cap
            "raw": asi.raw,
            "dimensions": asi.dimensions,
            "phases": asi.phases,
            "current_phase_id": asi.current_phase_id,
            "next_plan": asi.next_plan,
            "formula": "(completed phases + active partial) / 4 × 100",
            "achievable_today": False,
            "role": "secondary_harness_meter",
        },
        "investment_north_star": INVESTMENT_NORTH_STAR,
        "trend_report": {
            "curated_count": (signals.trend_report or {}).get("curated_count"),
            "gap_count": (signals.trend_report or {}).get("gap_count"),
            "partial_count": (signals.trend_report or {}).get("partial_count"),
        },
    }


def write_horizon(signals: ImproveSignals, *, cycle: int | None = None) -> list[str]:
    """Write horizon board to config dir + notes/ for visibility in the repo."""
    text = build_horizon_markdown(signals, cycle=cycle)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    HORIZON_PATH.write_text(text + "\n")
    written.append(str(HORIZON_PATH))
    try:
        HORIZON_REPO_PATH.parent.mkdir(parents=True, exist_ok=True)
        HORIZON_REPO_PATH.write_text(text + "\n")
        written.append(str(HORIZON_REPO_PATH))
    except OSError:
        pass
    payload = horizon_payload(signals, cycle=cycle)
    HORIZON_JSON_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    written.append(str(HORIZON_JSON_PATH))
    return written


def format_horizon_dashboard(signals: ImproveSignals | None = None) -> str:
    """Terminal-friendly board (no markdown tables)."""
    if signals is None and HORIZON_PATH.is_file():
        return HORIZON_PATH.read_text()
    if signals is None:
        return "(no horizon yet — run ./scripts/peer improve --write --research)"
    return build_horizon_markdown(signals)


def signals_to_dict(signals: ImproveSignals) -> dict[str, Any]:
    asi = compute_asi_progress(signals)
    return {
        "goals": list(GOALS),
        "investment_north_star": INVESTMENT_NORTH_STAR,
        "asi_north_star": ASI_NORTH_STAR,
        "asi_progress_pct": asi.pct,
        "asi_progress_label": asi.label,
        "asi_scale": asi.scale,
        "asi_ceiling": asi.scale,  # legacy alias — display scale only
        "asi_raw": asi.raw,
        "asi_dimensions": asi.dimensions,
        "asi_phases": asi.phases,
        "asi_current_phase_id": asi.current_phase_id,
        "asi_next_plan": asi.next_plan,
        "asi_achievable_today": False,
        "live": signals.live,
        "audit_ok": signals.audit_ok,
        "audit_warnings": signals.audit_warnings,
        "audit_errors": signals.audit_errors,
        "queue_drift": signals.queue_drift,
        "loop_state": signals.loop_state,
        "opportunities": [asdict(o) for o in signals.opportunities],
        "work_kit_opportunities": [asdict(o) for o in signals.opportunities if is_work_kit_target(o)],
        "inventory": _script_inventory(),
        "trend_report": signals.trend_report,
    }


def _log(msg: str, *, daemon: bool) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    if daemon:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as fh:
            fh.write(line + "\n")
    else:
        print(line, flush=True)


def run_improve_cycle(
    *,
    quick: bool,
    research: bool,
    refresh_trends: bool,
    log_fn,
    cycle: int | None = None,
    run_verify: bool = True,
) -> ImproveSignals:
    """One forever-loop tick: signal → filter → mechanical heal → enqueue → wake peer."""
    try:
        import dgx_resource_priority as rp

        if rp.guard_development(log_fn=log_fn):
            log_fn("improve: infra BEEP — skip cycle (RAM/GPU first)")
            # Compression: never pull adapt/research while RAM/GPU is critical.
            return gather_signals(
                quick=quick, research=False, refresh_trends=False, audit=False
            )
    except ImportError:
        pass
    live_audit = should_live_adapt_audit()
    signals = gather_signals(
        quick=quick,
        research=research or refresh_trends,
        refresh_trends=refresh_trends,
        audit=live_audit,
    )
    if not live_audit:
        log_fn(
            f"improve: adapt audit TTL-skip "
            f"(age ok <{improve_adapt_cache_ttl_sec():.0f}s — no adapt import)"
        )
    # Capture phase id before horizon overwrite so MET → next-phase is detectable.
    previous_phase_id = _load_previous_asi_phase_id()
    paths = write_prompts(signals, plan=True, execute=True, combined=True)
    horizon_paths = write_horizon(signals, cycle=cycle)

    # OVERSEER_IMPROVE_WAKE_BEFORE_VERIFY_2026_09_04 — wake before mechanical
    # local-cycle so improve→peer evidence stays fresh even when verify blocks.
    if _has_continuous_work(signals):
        try:
            wake_peer(log_fn=log_fn)
            log_fn("continuous: early wake before mechanical verify")
        except Exception as exc:  # noqa: BLE001
            log_fn(f"continuous: early wake failed ({exc})")

    try:
        mech = apply_mechanical(signals, log_fn=log_fn, run_verify=run_verify)
        if mech:
            log_fn(f"mechanical: {len(mech)} action(s)")
        # Only real verify pass arms cooldown — skipped/deferred must not.
        if run_verify and any(a == "local-cycle: ok" for a in mech):
            try:
                import peer_transcript as transcript

                transcript.mark_local_verify()
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        log_fn(f"mechanical: failed ({exc})")

    enqueued: list[str] = []
    try:
        import automation_team as team

        handed = team.hand_out_worker_pool(log_fn=log_fn, signals=signals)
        if handed:
            log_fn(f"hand_out: {len(handed)} niche(s) active on board")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"hand_out: failed ({exc})")

    try:
        phase_plan = enqueue_phase_plan(
            signals, log_fn=log_fn, previous_phase_id=previous_phase_id
        )
        if phase_plan:
            enqueued.append(phase_plan)
        work_items = enqueue_work_opportunities(signals, log_fn=log_fn)
        enqueued.extend(work_items)
        if enqueued:
            log_fn(f"enqueue: {len(enqueued)} item(s)")
        else:
            log_fn("enqueue: nothing new for work kit")
        try:
            import automation_engine as engine

            engine.emit("improve.cycle.end", {"enqueued": bool(enqueued), "count": len(enqueued)})
        except Exception:  # noqa: BLE001
            pass
        if _has_continuous_work(signals):
            wake_peer(log_fn=log_fn)
            log_fn("continuous: improve keep-driving — peer woken (work remains)")
        else:
            # OVERSEER_IDLE_HEARTBEAT_WAKE_2026_09_04 — healthy idle (Active empty)
            # used to skip wake → improve-loop.log aged past 1800s → factory
            # self_sufficiency tanked + stagnation overseer fan-out. Heartbeat
            # keeps "wake peer" / drive evidence fresh without enqueue theater.
            wake_peer(log_fn=log_fn)
            log_fn("idle: improve heartbeat wake (healthy idle)")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"enqueue: failed ({exc})")

    top = [o for o in signals.opportunities if is_work_kit_target(o)][:3]
    if not top:
        top = signals.opportunities[:3]
    summary = "; ".join(f"[{o.category}] {o.title}" for o in top) or "(no opportunities)"
    now_n = sum(1 for o in signals.opportunities if _horizon_tier(o.priority) == "NOW")
    next_n = sum(1 for o in signals.opportunities if _horizon_tier(o.priority) == "NEXT")
    hor_n = sum(1 for o in signals.opportunities if _horizon_tier(o.priority) == "HORIZON")
    work_n = sum(1 for o in signals.opportunities if is_work_kit_target(o))
    log_fn(
        f"improve cycle — prompts {len(paths)}; horizon NOW={now_n} NEXT={next_n} "
        f"HORIZON={hor_n}; work-kit={work_n}"
    )
    log_fn(f"horizon board → {horizon_paths[0]}")
    log_fn(f"top: {summary}")
    return signals


def run_forever(
    *,
    quick: bool = True,
    research: bool = True,
    refresh_trends: bool = False,
    daemon: bool = False,
    wake_sec: float = CONTINUOUS_WAKE_SEC,
) -> int:
    """Event-driven forever loop: heal work kit + enqueue + wake peer."""
    log_fn = lambda msg: _log(msg, daemon=daemon)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    log_fn(
        f"improve forever — work-kit driver; continuous≤{improve_continuous_wake_sec():.0f}s "
        f"idle≤{improve_idle_wake_sec():.0f}s (event OR heartbeat); research={research}; "
        f"min gap {improve_continuous_min_cycle_sec():.0f}s active / {MIN_CYCLE_GAP_SEC:.0f}s idle"
    )
    watcher = None
    try:
        import peer_transcript as transcript

        transcript.SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        transcript.SIGNAL_PATH.touch(exist_ok=True)
        watcher = transcript.PeerEventWatcher()
        # No repo git watch — horizon/prompt writes must not self-wake the loop.
        if watcher.setup(repo_root=None):
            log_fn(f"event-driven: kqueue + {transcript.SIGNAL_PATH.name} (no git self-wake)")
        else:
            watcher = None
            log_fn(f"no kqueue — fallback sleep {wake_sec:.0f}s")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"event watch unavailable ({exc}) — fallback sleep")
        watcher = None

    cycle = 0
    last_has_work = True
    try:
        while True:
            cycle += 1
            cycle_started = time.monotonic()
            signals: ImproveSignals | None = None
            try:
                import peer_transcript as transcript

                cooldown = transcript.local_verify_cooldown_remaining()
            except Exception:  # noqa: BLE001
                cooldown = 0.0
            run_verify = cooldown <= 0
            if not run_verify:
                log_fn(
                    f"cycle {cycle} — drive work kit "
                    f"(verify cooldown {cooldown:.0f}s left; continuous prompts/heal/enqueue)"
                )
            else:
                log_fn(f"cycle {cycle} — drive work kit (heal → enqueue → wake)")
            try:
                signals = run_improve_cycle(
                    quick=quick,
                    research=research,
                    refresh_trends=refresh_trends and cycle == 1,
                    log_fn=log_fn,
                    cycle=cycle,
                    run_verify=run_verify,
                )
            except Exception as exc:  # noqa: BLE001 — never die the forever loop
                log_fn(f"cycle error (continuing): {exc}")
                signals = None

            try:
                import dgx_resource_priority as rp

                if rp.enabled() and not rp.development_allowed():
                    has_work = False
                    last_has_work = False
                else:
                    has_work = _has_continuous_work(signals) if signals is not None else last_has_work
                    last_has_work = has_work
            except ImportError:
                has_work = _has_continuous_work(signals) if signals is not None else last_has_work
                last_has_work = has_work
            min_gap = improve_continuous_min_cycle_sec() if has_work else MIN_CYCLE_GAP_SEC

            if watcher is not None and getattr(watcher, "available", False):
                drained = watcher.drain()
                if drained:
                    log_fn(f"drained {drained} self-wake event(s)")
                elapsed = time.monotonic() - cycle_started
                wait_timeout = improve_wake_timeout(has_work=has_work, elapsed=elapsed)
                event = watcher.wait(timeout=wait_timeout)
                # Spurious residual wakes inside the min gap: re-wait unless real turn/signal.
                while (
                    event.reason not in ("transcript", "signal")
                    and time.monotonic() - cycle_started < min_gap
                ):
                    rem = min_gap - (time.monotonic() - cycle_started)
                    if rem <= 0:
                        break
                    event = watcher.wait(timeout=rem)
                mode = "continuous" if has_work else "idle"
                log_fn(f"wake reason={event.reason} ({mode}, next≤{wait_timeout:.0f}s)")
            else:
                wait_timeout = improve_wake_timeout(
                    has_work=has_work,
                    elapsed=time.monotonic() - cycle_started,
                )
                time.sleep(wait_timeout if wait_timeout else FALLBACK_POLL_SEC)
                log_fn(f"wake reason=fallback ({'continuous' if has_work else 'idle'})")
    except KeyboardInterrupt:
        log_fn("improve forever stopped (KeyboardInterrupt)")
        return 0
    finally:
        if watcher is not None:
            try:
                watcher.close()
            except Exception:  # noqa: BLE001
                pass
    return 0


def plist_body() -> str:
    py = sys.executable
    script = SCRIPTS / "automation_improve.py"
    args = [py, str(script), "--forever", "--daemon", "--write", "--research"]
    args_xml = "\n".join(f"    <string>{a}</string>" for a in args)
    home = Path.home()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{IMPROVE_LABEL}</string>
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


def _cmd_install_body(*, force: bool = False) -> int:
    """Bootstrap improve LaunchAgent without taking the daemon-heal flock (caller may hold it)."""
    if sys.platform != "darwin":
        import peer_self_heal as heal

        heal.ensure_canonical_module()
        print(heal.linux_install_daemon("improve"))
        return 0
    global IMPROVE_LABEL, PLIST_PATH, LOG_PATH
    import automation_config as cfg_mod

    cfg = cfg_mod.load_config()
    ns = str(cfg.get("config_namespace") or "automation")
    IMPROVE_LABEL = f"com.togi.{ns}-improve-loop"
    PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{IMPROVE_LABEL}.plist"
    live_dir = Path.home() / ".config" / ns
    LOG_PATH = live_dir / "improve-loop.log"

    uid = os.getuid()
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(plist_body())
    import peer_self_heal as heal

    heal.ensure_canonical_module()
    if not force and heal._launchctl_running(IMPROVE_LABEL):
        print(f"improve loop agent: {PLIST_PATH}")
        print(f"log: {LOG_PATH}")
        print(f"already running ({IMPROVE_LABEL}) — plist refreshed; skip bootout")
        print("runs forever — plan→execute improve prompts (event + 60s heartbeat)")
        return 0
    if not force and heal._launchctl_loaded(IMPROVE_LABEL):
        nudge = heal._kickstart(IMPROVE_LABEL)
        print(f"improve loop agent: {PLIST_PATH}")
        print(f"log: {LOG_PATH}")
        print(f"already loaded ({IMPROVE_LABEL}) — {nudge}; skip bootout")
        if heal._wait_launchctl_running(IMPROVE_LABEL, attempts=4, delay_sec=0.4):
            return 0
        print("WARNING: kickstart did not yield PID — try force rebootstrap", file=sys.stderr)
        return 1
    if force or heal._launchctl_loaded(IMPROVE_LABEL):
        subprocess.run(["launchctl", "bootout", f"gui/{uid}/{IMPROVE_LABEL}"], capture_output=True)
        time.sleep(1.0)
    proc = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "bootstrap failed").strip()
        if "already" in err.lower() or "in use" in err.lower():
            nudge = heal._kickstart(IMPROVE_LABEL)
            print(f"improve loop agent: {PLIST_PATH}")
            print(f"log: {LOG_PATH}")
            print(f"bootstrap race — {nudge}")
            return 0 if heal._wait_launchctl_running(IMPROVE_LABEL, attempts=4, delay_sec=0.4) else 1
        print(err, file=sys.stderr)
        return 1
    print(f"improve loop agent: {PLIST_PATH}")
    print(f"log: {LOG_PATH}")
    print("runs forever — plan→execute improve prompts (event + 60s heartbeat)")
    return 0


def cmd_install(*, force: bool = False) -> int:
    import peer_self_heal as heal

    heal.ensure_canonical_module()
    with heal._daemon_heal_flock():
        return _cmd_install_body(force=force)


def cmd_uninstall() -> int:
    if sys.platform != "darwin":
        import peer_self_heal as heal

        heal.ensure_canonical_module()
        print(heal.linux_uninstall_daemon("improve"))
        return 0
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{IMPROVE_LABEL}"], capture_output=True)
    if PLIST_PATH.is_file():
        PLIST_PATH.unlink()
    print("improve loop agent removed")
    return 0


def cmd_status() -> int:
    import peer_self_heal as heal

    running = heal._improve_daemon_running()
    print(f"label: {IMPROVE_LABEL}")
    print(f"state: {'RUNNING' if running else 'STOPPED'}")
    print(f"driver: {'automation_improve (improve_drives_automation)' if auto.improve_drives_automation() else 'legacy cursor_self_improve + improve'}")
    print(f"log: {LOG_PATH}")
    print(f"horizon: {HORIZON_PATH}")
    print(f"repo board: {HORIZON_REPO_PATH}")
    print()
    if HORIZON_PATH.is_file():
        print(HORIZON_PATH.read_text())
    elif LOG_PATH.is_file():
        print("(horizon not written yet — waiting for next cycle)")
        print("recent log:")
        for line in auto.tail_text_lines(LOG_PATH, 8):
            print(f"  {line}")
    return 0 if running else 1


def cmd_watch(*, interval: float = 5.0) -> int:
    """Live refresh of the horizon board in the terminal."""
    clear = "\033[2J\033[H"
    try:
        while True:
            sys.stdout.write(clear)
            sys.stdout.write(f"improve-watch · refresh every {interval:.0f}s · Ctrl+C quit\n\n")
            if HORIZON_PATH.is_file():
                sys.stdout.write(HORIZON_PATH.read_text())
            else:
                sys.stdout.write("(waiting for first improve cycle to write horizon…)\n")
            if LOG_PATH.is_file():
                sys.stdout.write("\n--- recent log ---\n")
                for line in auto.tail_text_lines(LOG_PATH, 6):
                    sys.stdout.write(line + "\n")
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nimprove-watch stopped")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan and execute improvements to the automation kit",
    )
    parser.add_argument("--plan", action="store_true", help="Plan phase only")
    parser.add_argument("--execute", action="store_true", help="Execute phase only")
    parser.add_argument("--write", action="store_true", help="Save prompt(s) under config dir")
    parser.add_argument("--json", action="store_true", help="JSON output (signals + prompts)")
    parser.add_argument("--quick", action="store_true", default=True, help="Quick metrics (default)")
    parser.add_argument("--full", action="store_true", help="Full metrics probe (slower)")
    parser.add_argument("--research", action="store_true", help="Include industry trends in prompts")
    parser.add_argument("--refresh-trends", action="store_true", help="Fetch HN headlines before planning")
    parser.add_argument("--forever", action="store_true", help="Forever loop: rewrite improve prompts")
    parser.add_argument("--daemon", action="store_true", help="Log to improve-loop.log (with --forever)")
    parser.add_argument("--wake-sec", type=float, default=CONTINUOUS_WAKE_SEC, help="Heartbeat wake seconds")
    parser.add_argument("--install", action="store_true", help="Install improve forever LaunchAgent")
    parser.add_argument("--uninstall", action="store_true", help="Remove improve forever LaunchAgent")
    parser.add_argument("--status", action="store_true", help="Show improve forever daemon status")
    parser.add_argument("--watch", action="store_true", help="Live refresh IMPROVE_HORIZON board")
    parser.add_argument("--watch-interval", type=float, default=5.0, help="Seconds between watch refreshes")
    args = parser.parse_args()

    if args.install:
        return cmd_install()
    if args.uninstall:
        return cmd_uninstall()
    if args.status:
        return cmd_status()
    if args.watch:
        return cmd_watch(interval=args.watch_interval)

    quick = not args.full

    if args.forever:
        return run_forever(
            quick=quick,
            research=args.research or True,
            refresh_trends=args.refresh_trends,
            daemon=args.daemon,
            wake_sec=args.wake_sec,
        )

    signals = gather_signals(
        quick=quick,
        research=args.research or args.refresh_trends,
        refresh_trends=args.refresh_trends,
    )

    plan_only = args.plan and not args.execute
    execute_only = args.execute and not args.plan
    combined = not args.plan and not args.execute

    if args.write:
        paths = write_prompts(
            signals,
            plan=plan_only or combined,
            execute=execute_only or combined,
            combined=combined,
        )
        for p in paths:
            print(f"wrote {p}")
        for p in write_horizon(signals):
            print(f"wrote {p}")

    if args.json:
        payload: dict[str, Any] = signals_to_dict(signals)
        if plan_only or combined:
            payload["plan_prompt"] = build_plan_prompt(signals)
        if execute_only or combined:
            payload["execute_prompt"] = build_execute_prompt(signals, plan_path=PLAN_PATH)
        print(json.dumps(payload, indent=2))
        return 0

    if plan_only:
        print(build_plan_prompt(signals))
    elif execute_only:
        print(build_execute_prompt(signals, plan_path=PLAN_PATH))
    else:
        print(build_combined_prompt(signals))

    if not args.write:
        print(f"\n(save with --write → {CONFIG_DIR}/)", file=sys.stderr)

    return 1 if signals.audit_errors and execute_only else 0


if __name__ == "__main__":
    raise SystemExit(main())
