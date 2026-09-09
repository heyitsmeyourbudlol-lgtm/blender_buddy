#!/usr/bin/env python3
"""Dual research agents — efficiency + output — sync findings into improve + peer loop.

Two lanes run **every cycle** (mechanical probe → digest → enqueue → optional agent):

| Lane | Focus | Digest |
|------|-------|--------|
| efficiency | Hot paths, per-worker yield, latency, queue discipline | notes/EFFICIENCY_RESEARCH.md |
| output | Monster software, OSS factory, irreversible artifacts | notes/OUTPUT_RESEARCH.md |

Combined handoff for the team + cursor-agent + automation_improve: notes/RESEARCH_SYNC.md

Retention: both lanes active until output research stops adding marginal value vs
efficiency-only — then retire output lane (see notes/RESEARCH_SYNC.md policy).

Usage:
  python3 scripts/peer_dual_research.py --once
  python3 scripts/peer_dual_research.py --forever --daemon
  ./scripts/peer dual-research
  ./scripts/peer dual-research-status
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Literal

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import automation_config as cfg_mod  # noqa: E402
import project_automation as auto  # noqa: E402

CONFIG_DIR = auto.CONFIG_DIR
STATE_PATH = CONFIG_DIR / "dual-research-state.json"
FINDINGS_PATH = CONFIG_DIR / "dual-research-findings.json"
PROMPT_PATH = CONFIG_DIR / "dual-research-prompt.md"
LOG_PATH = CONFIG_DIR / "dual-research-loop.log"

NAMESPACE = str(cfg_mod.CFG.get("config_namespace") or "automation-hub")
RESEARCH_LABEL = f"com.togi.{NAMESPACE}-dual-research-loop"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{RESEARCH_LABEL}.plist"

Lane = Literal["efficiency", "output"]

EFFICIENCY_DIGEST = ROOT / "notes" / "EFFICIENCY_RESEARCH.md"
OUTPUT_DIGEST = ROOT / "notes" / "OUTPUT_RESEARCH.md"
SYNC_DIGEST = ROOT / "notes" / "RESEARCH_SYNC.md"

_THEATER_MARKERS = (
    "time bomb",
    "crown-era",
    "competition ladder",
    "meta-exit",
    "shared primitives",
    "true artificial superintelligence",
    "philosophy",
    "strategy essay",
)


@dataclass
class ResearchFinding:
    id: str
    lane: Lane
    severity: str
    title: str
    evidence: str
    action: str
    enqueue_title: str = ""
    status: str = "open"
    first_seen: str = ""
    last_seen: str = ""

    @staticmethod
    def make_id(lane: str, title: str) -> str:
        raw = f"{lane}|{title}".lower()
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class LaneReport:
    lane: Lane
    findings: list[ResearchFinding] = field(default_factory=list)
    new_findings: list[ResearchFinding] = field(default_factory=list)
    enqueued: list[str] = field(default_factory=list)


def _cfg_block() -> dict[str, Any]:
    raw = cfg_mod.CFG.get("dual_research") or {}
    return raw if isinstance(raw, dict) else {}


def research_enabled() -> bool:
    block = _cfg_block()
    if "enabled" in block:
        return bool(block["enabled"])
    return bool(cfg_mod.CFG.get("dual_research_enabled", True))


def research_interval_sec() -> float:
    block = _cfg_block()
    try:
        val = block.get("interval_sec") or cfg_mod.CFG.get("dual_research_interval_sec") or 600
        return max(120.0, float(val))
    except (TypeError, ValueError):
        return 600.0


def dispatch_agent_enabled() -> bool:
    block = _cfg_block()
    if "dispatch_agent" in block:
        return bool(block["dispatch_agent"])
    return bool(cfg_mod.CFG.get("dual_research_dispatch_agent", True))


def enqueue_cap_per_lane() -> int:
    block = _cfg_block()
    try:
        return max(0, min(4, int(block.get("enqueue_cap") or cfg_mod.CFG.get("dual_research_enqueue_cap") or 2)))
    except (TypeError, ValueError):
        return 2


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


def _load_registry() -> dict[str, Any]:
    return _load_json(FINDINGS_PATH)


def _save_registry(registry: dict[str, Any]) -> None:
    _save_json(FINDINGS_PATH, registry)


def _open_queue_items() -> list[str]:
    try:
        return list(auto.open_work_items().open_items)
    except Exception:  # noqa: BLE001
        return []


def _loop_state() -> dict[str, Any]:
    path = CONFIG_DIR / "peer-loop-state.json"
    data = _load_json(path)
    return data.get("last_cycle") or {}


def _is_theater(item: str) -> bool:
    low = item.lower()
    return any(m in low for m in _THEATER_MARKERS)


def probe_efficiency() -> list[ResearchFinding]:
    """Mechanical efficiency lane — per-worker yield, hot paths, queue discipline."""
    findings: list[ResearchFinding] = []
    items = _open_queue_items()
    open_n = len(items)
    theater_n = sum(1 for i in items if _is_theater(i))

    if open_n > 12:
        findings.append(
            ResearchFinding(
                id=ResearchFinding.make_id("efficiency", "queue bloated"),
                lane="efficiency",
                severity="high",
                title="Executable queue bloated",
                evidence=f"{open_n} open items — workers re-read noise each cycle",
                action="./scripts/peer compact-queue — cap Active to 12 executable items",
                enqueue_title="Compact queue to 12 executable file-scoped items",
            )
        )

    if theater_n >= 3:
        findings.append(
            ResearchFinding(
                id=ResearchFinding.make_id("efficiency", "queue theater"),
                lane="efficiency",
                severity="medium",
                title="Strategy theater in Active queue",
                evidence=f"{theater_n} theater-like items dilute worker context",
                action="Demote non-executable lines; rewrite top items with file paths + verify",
                enqueue_title="Demote strategy theater — rewrite top 8 as file-scoped tasks",
            )
        )

    if bool(cfg_mod.CFG.get("role_pool_expand", False)) and auto.max_parallel_peers() >= 16:
        findings.append(
            ResearchFinding(
                id=ResearchFinding.make_id("efficiency", "role sharding"),
                lane="efficiency",
                severity="medium",
                title="Role sharding wastes few-worker cycles",
                evidence="role_pool_expand duplicates niches — poor yield when agent count is low",
                action='Set role_pool_expand: false; cap max_parallel_peers at 4–8 for unique niches',
                enqueue_title="Disable role_pool_expand — unique niche per worker",
            )
        )

    last = _loop_state()
    if last.get("noop"):
        findings.append(
            ResearchFinding(
                id=ResearchFinding.make_id("efficiency", "noop loop"),
                lane="efficiency",
                severity="high",
                title="Noop loop — zero queue advance",
                evidence="Last ok cycle left queue fingerprint unchanged",
                action="./scripts/peer noop-break — compact, poke, investigate",
                enqueue_title="Break noop loop — advance or shrink queue",
            )
        )

    if last.get("verify_ok") is False:
        findings.append(
            ResearchFinding(
                id=ResearchFinding.make_id("efficiency", "verify block"),
                lane="efficiency",
                severity="critical",
                title="Verify gate blocking dispatch",
                evidence=last.get("note") or "verify_ok=false in last_cycle",
                action="./scripts/peer heal-all — fix verify before next agent dispatch",
                enqueue_title="Fix verify gate — unblock worker dispatch",
            )
        )

    try:
        import peer_loop as pl

        wake = pl.effective_continuous_wake_sec(open_queue_count=open_n)
        if wake <= 5 and open_n <= 8:
            findings.append(
                ResearchFinding(
                    id=ResearchFinding.make_id("efficiency", "hyper wake"),
                    lane="efficiency",
                    severity="low",
                    title="Hyper wake with small queue",
                    evidence=f"continuous_wake_sec={wake} with {open_n} open items — overhead > yield",
                    action="Raise continuous_wake_sec when queue ≤8; run pre-dispatch not spin",
                    enqueue_title="Tune wake interval — pre-dispatch over hyper poll",
                )
            )
    except (TypeError, ValueError, Exception):  # noqa: BLE001
        pass

    findings.append(
        ResearchFinding(
            id=ResearchFinding.make_id("efficiency", "pre-dispatch"),
            lane="efficiency",
            severity="info",
            title="Pre-dispatch multiplies per-worker yield",
            evidence="compact → check → ensure-pool before every cursor-agent spawn",
            action="./scripts/peer pre-dispatch",
            enqueue_title="",
        )
    )
    return findings


def probe_output() -> list[ResearchFinding]:
    """Mechanical output lane — monster factory or self-sufficiency (mode-dependent)."""
    findings: list[ResearchFinding] = []
    items = _open_queue_items()
    # Init before try — except path must not UnboundLocalError on these names.
    has_external = False
    has_artifact = False
    mode = auto.factory_meter_mode()

    try:
        import factory_progress as fp

        prog = fp.compute_factory_progress()
        pct = float(prog.pct)
        if mode == "self_sufficient":
            suff = next((d for d in prog.dimensions if d.id == "self_sufficiency"), None)
            if suff and float(suff.score) < 0.75:
                findings.append(
                    ResearchFinding(
                        id=ResearchFinding.make_id("output", "self sufficiency gap"),
                        lane="output",
                        severity="high",
                        title="Self-sufficiency meter below proven threshold",
                        evidence=suff.evidence[:200],
                        action="./scripts/peer standup — peer + improve + self-heal + verify-gate",
                        enqueue_title="Prove improve→peer closed loop",
                    )
                )
            elif pct < 75:
                findings.append(
                    ResearchFinding(
                        id=ResearchFinding.make_id("output", "factory low"),
                        lane="output",
                        severity="medium",
                        title="Factory progress below self-sufficient target",
                        evidence=f"factory_progress={pct:.0f}% — external OSS deferred this build",
                        action="./scripts/peer progress",
                        enqueue_title="",
                    )
                )
            return findings

        has_external = any("external proof" in i.lower() or "native verify" in i.lower() for i in items)
        has_artifact = any("irreversible artifact" in i.lower() for i in items)

        ext_dim = next((d for d in prog.dimensions if d.id == "external_proof"), None)
        if pct < 60:
            findings.append(
                ResearchFinding(
                    id=ResearchFinding.make_id("output", "factory low"),
                    lane="output",
                    severity="high",
                    title="Factory progress below monster threshold",
                    evidence=f"factory_progress={pct:.0f}% — investment thesis unvalidated",
                    action="./scripts/peer progress — pick one registry repo for adapt→verify→PR",
                    enqueue_title="External proof sprint — one registry repo to irreversible PR",
                )
            )
        if ext_dim and float(ext_dim.score) < 0.5:
            findings.append(
                ResearchFinding(
                    id=ResearchFinding.make_id("output", "external proof gap"),
                    lane="output",
                    severity="high",
                    title="Zero completed external proof loops",
                    evidence=ext_dim.evidence[:200],
                    action="Run factory-sprint on CPT, CaaS, or RAM registry entry",
                    enqueue_title="External proof: adapt + native verify on one registry target",
                )
            )
    except Exception as exc:  # noqa: BLE001
        findings.append(
            ResearchFinding(
                id=ResearchFinding.make_id("output", "factory probe fail"),
                lane="output",
                severity="medium",
                title="Factory progress probe failed",
                evidence=str(exc)[:200],
                action="python3 scripts/factory_progress.py --json",
                enqueue_title="",
            )
        )
        # self_sufficient: do not fall through to registry External-proof enqueue.
        if mode == "self_sufficient":
            return findings

    if not has_external:
        findings.append(
            ResearchFinding(
                id=ResearchFinding.make_id("output", "no external queue"),
                lane="output",
                severity="medium",
                title="No external proof item in Active queue",
                evidence="Workers default to hub kit polish — not OSS monster factory",
                action="Enqueue one registry target with adapt + native verify + worktree scope",
                enqueue_title="External proof: adapt + native verify on CPT — registry status=unaudited",
            )
        )

    if not has_artifact:
        findings.append(
            ResearchFinding(
                id=ResearchFinding.make_id("output", "artifact gate"),
                lane="output",
                severity="medium",
                title="Irreversible artifact gate not enforced",
                evidence="Peer success should mean PR-shaped diff on external or hub repo",
                action="Add irreversible artifact check to peer_loop post-verify hook",
                enqueue_title="Irreversible artifact gate — peer success = merged diff or PR note",
            )
        )

    registry_path = ROOT / "repos" / "registry.json"
    if registry_path.is_file():
        try:
            reg = json.loads(registry_path.read_text(encoding="utf-8"))
            entries = reg.get("repos") or reg if isinstance(reg, list) else []
            if isinstance(reg, dict):
                entries = reg.get("repos") or list(reg.values())
            unaudited = [
                e for e in entries
                if isinstance(e, dict) and str(e.get("status", "")).lower() in ("unaudited", "needs-kit-install")
            ]
            if unaudited:
                name = str(unaudited[0].get("name") or unaudited[0].get("id") or "registry target")
                findings.append(
                    ResearchFinding(
                        id=ResearchFinding.make_id("output", f"registry {name}"),
                        lane="output",
                        severity="high",
                        title=f"Registry target ready for monster sprint: {name}",
                        evidence=f"status={unaudited[0].get('status')} — factory idle on external repo",
                        action=f"adapt→native verify→worktree PR on {name}",
                        enqueue_title=f"External proof: adapt + native verify on {name}",
                    )
                )
        except (OSError, json.JSONDecodeError):
            pass

    return findings


def merge_findings(lane: Lane, probed: list[ResearchFinding]) -> tuple[list[ResearchFinding], list[ResearchFinding]]:
    registry = _load_registry()
    items: dict[str, Any] = registry.setdefault("items", {})
    now = _now_iso()
    new: list[ResearchFinding] = []
    open_list: list[ResearchFinding] = []

    for f in probed:
        raw = items.get(f.id)
        if raw:
            f.status = str(raw.get("status") or "open")
            f.first_seen = str(raw.get("first_seen") or now)
            f.last_seen = now
            items[f.id] = {**raw, **asdict(f), "last_seen": now}
        else:
            f.first_seen = now
            f.last_seen = now
            items[f.id] = asdict(f)
            if f.severity not in ("info",):
                new.append(f)
        if f.status != "resolved":
            open_list.append(f)

    registry["updated"] = now
    _save_registry(registry)
    return open_list, new


def _queue_has_title(title: str) -> bool:
    """True when title is already on the queue — open OR checked-off.

    Open-only checks re-enqueue after [x] (noop: same item returns every
    dual-research cycle when probe_efficiency briefly fires again).
    """
    if not title:
        return True
    low = title.lower()
    if any(low in item.lower() for item in _open_queue_items()):
        return True
    work_path = auto.WORK_QUEUE_PATH
    try:
        md = work_path.read_text(encoding="utf-8") if work_path.is_file() else ""
    except OSError:
        return False
    return low in md.lower()


def _enqueue_line(marker: str, detail: str, *, registry_ids: list[str] | None = None) -> bool:
    """Append one executable item to WORK_QUEUE + context (synced)."""
    work_path = auto.WORK_QUEUE_PATH
    try:
        work_md = work_path.read_text(encoding="utf-8") if work_path.is_file() else ""
        known = {auto._normalize_queue_key(x) for x in auto.open_work_items(work_md=work_md).open_items}
        if auto._normalize_queue_key(marker) in known:
            return False
        line = f"- [ ] **{marker}** — {detail[:200]}"
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
        if registry_ids:
            registry = _load_registry()
            items = registry.get("items") or {}
            for rid in registry_ids:
                if rid in items and isinstance(items[rid], dict):
                    items[rid]["status"] = "enqueued"
            registry["items"] = items
            _save_registry(registry)
        return True
    except OSError:
        return False


def enqueue_findings(findings: list[ResearchFinding], *, lane: Lane) -> list[str]:
    cap = enqueue_cap_per_lane()
    if cap <= 0:
        return []
    prefix = "efficiency-research" if lane == "efficiency" else "output-research"
    enqueued: list[str] = []
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

    for f in sorted(findings, key=lambda x: severity_order.get(x.severity, 9)):
        if len(enqueued) >= cap:
            break
        title = f.enqueue_title.strip()
        if not title or _queue_has_title(title):
            continue
        marker = f"[{prefix}] {title}"
        if _enqueue_line(marker, f.evidence[:200], registry_ids=[f.id]):
            enqueued.append(marker)
    return enqueued


def build_lane_digest(
    *,
    lane: Lane,
    open_findings: list[ResearchFinding],
    new_findings: list[ResearchFinding],
    actions: list[str],
    enqueued: list[str],
) -> str:
    title = "Efficiency research" if lane == "efficiency" else "Output research"
    role = "Efficiency Research Agent" if lane == "efficiency" else "Output Research Agent"
    focus = (
        "Per-worker yield, hot paths, latency, queue discipline, pre-dispatch"
        if lane == "efficiency"
        else "Monster software, OSS factory, external proof, irreversible artifacts"
    )
    lines = [
        f"# {title}",
        "",
        f"_Updated {_now_iso()}_ · **{role}**",
        "",
        f"> **Focus:** {focus} — findings feed `notes/RESEARCH_SYNC.md`, "
        "`automation_improve`, and peer orchestrator prompts.",
        "",
        "## This cycle",
        "",
    ]
    if actions:
        for a in actions:
            lines.append(f"- {a}")
    else:
        lines.append("- (no actions)")
    if enqueued:
        lines.append("")
        lines.append("## Enqueued")
        for e in enqueued:
            lines.append(f"- {e[:120]}")
    lines.extend(["", "## Open findings", ""])
    if open_findings:
        for f in open_findings[:12]:
            if f.severity == "info":
                continue
            lines.append(f"- **[{f.severity}]** {f.title}")
            lines.append(f"  - Evidence: {f.evidence[:160]}")
            lines.append(f"  - Action: {f.action[:160]}")
    else:
        lines.append("- (none)")
    if new_findings:
        lines.extend(["", "## New this cycle", ""])
        for f in new_findings[:6]:
            lines.append(f"- [{f.severity}] {f.title}")
    lines.extend(["", "## Agent notes", "", "_Deep research agent appends dated bullets here._", ""])
    return "\n".join(lines) + "\n"


def build_sync_digest(
    eff: LaneReport,
    out: LaneReport,
    *,
    dispatched: bool = False,
) -> str:
    lines = [
        "# Research sync — team handoff",
        "",
        f"_Updated {_now_iso()}_ · both lanes · dispatched={dispatched}",
        "",
        "> **For:** peer orchestrator, cursor-agent, automation_improve, full 8-worker team.",
        "> Efficiency + output research run **synchronously** each cycle.",
        "",
        "## Efficiency lane (speed × yield)",
        "",
    ]
    for f in eff.findings[:5]:
        if f.severity == "info":
            continue
        lines.append(f"- **[{f.severity}]** {f.title} — {f.action[:100]}")
    lines.extend(["", "## Output lane (monster factory)", ""])
    for f in out.findings[:5]:
        if f.severity == "info":
            continue
        lines.append(f"- **[{f.severity}]** {f.title} — {f.action[:100]}")
    lines.extend([
        "",
        "## Executable enqueue (improve + peer)",
        "",
    ])
    for e in eff.enqueued + out.enqueued:
        lines.append(f"- {e[:120]}")
    if not eff.enqueued and not out.enqueued:
        lines.append("- (none this cycle)")
    lines.extend([
        "",
        "## Team instructions",
        "",
        "1. **Orchestrator** — read this file + lane digests before Phase 1 Plan.",
        "2. **Factory Engineer** — implement efficiency findings (hot path, queue, pre-dispatch).",
        "3. **OSS Integration Architect** — implement output findings (external proof, PR).",
        "4. **Queue Steward** — ensure enqueued `[efficiency-research]` / `[output-research]` items stay executable.",
        "5. **Improve loop** — `./scripts/peer improve --write --research` consumes sync on next tick.",
        "",
        "## Linked digests",
        "",
        f"- Efficiency: `{EFFICIENCY_DIGEST.relative_to(ROOT)}`",
        f"- Output: `{OUTPUT_DIGEST.relative_to(ROOT)}`",
        f"- Industry trends: `notes/AUTOMATION_TRENDS.md`",
        "",
    ])
    return "\n".join(lines) + "\n"


AGENT_NOTES_STUB = "_Deep research agent appends dated bullets here._"
_LANE_TEMPLATE_HEADINGS = frozenset(
    {
        "",
        "This cycle",
        "Enqueued",
        "Open findings",
        "New this cycle",
        "Agent notes",
    }
)


def _section_map(text: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, section-including-heading) pairs; preamble heading is ''."""
    chunks: list[tuple[str, str]] = []
    cur_h = ""
    buf: list[str] = []
    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            chunks.append((cur_h, "".join(buf)))
            cur_h = line[3:].strip()
            buf = [line]
        else:
            buf.append(line)
    chunks.append((cur_h, "".join(buf)))
    return chunks


def extract_heading_body(text: str, heading: str) -> str:
    """Return markdown body under ``## heading`` until the next ``## `` or EOF."""
    marker = f"## {heading}"
    idx = text.find(marker)
    if idx < 0:
        return ""
    rest = text[idx + len(marker) :]
    nxt = rest.find("\n## ")
    body = rest if nxt < 0 else rest[:nxt]
    return body.strip()


def merge_lane_digest(existing: str, new_text: str) -> str:
    """Keep Agent notes + extra research sections across mechanical digest rewrites."""
    if not existing.strip():
        return new_text
    old = _section_map(existing)
    new = _section_map(new_text)
    extras = [(h, b) for h, b in old if h not in _LANE_TEMPLATE_HEADINGS]
    old_notes = next((b for h, b in old if h == "Agent notes"), "")
    old_notes_body = old_notes.split("\n", 1)[-1].strip() if old_notes else ""
    notes_real = bool(old_notes_body) and AGENT_NOTES_STUB not in old_notes_body.splitlines()[:3]
    out: list[str] = []
    extras_inserted = False
    for heading, body in new:
        if heading == "Agent notes":
            if not extras_inserted:
                for _, extra in extras:
                    out.append(extra.rstrip() + "\n\n")
                extras_inserted = True
            if notes_real:
                out.append("## Agent notes\n\n" + old_notes_body.rstrip() + "\n")
            else:
                out.append(body)
        else:
            out.append(body)
    result = "".join(out)
    return result if result.endswith("\n") else result + "\n"


def preserve_sync_lane(existing: str, new_text: str, heading: str) -> str:
    """Keep previous lane bullets when the new mechanical digest lane is empty."""
    new_body = extract_heading_body(new_text, heading)
    if any(ln.startswith("- ") for ln in new_body.splitlines()):
        return new_text
    old_body = extract_heading_body(existing, heading)
    if not any(ln.startswith("- ") for ln in old_body.splitlines()):
        return new_text
    marker = f"## {heading}"
    idx = new_text.find(marker)
    if idx < 0:
        return new_text
    after = new_text[idx + len(marker) :]
    nxt = after.find("\n## ")
    replacement = marker + "\n\n" + old_body.rstrip() + "\n"
    if nxt < 0:
        return new_text[:idx] + replacement
    end = idx + len(marker) + nxt
    return new_text[:idx] + replacement + new_text[end:]


def merge_sync_digest(existing: str, new_text: str) -> str:
    if not existing.strip():
        return new_text
    text = new_text
    for heading in (
        "Efficiency lane (speed × yield)",
        "Output lane (monster factory)",
        "Team instructions",
    ):
        text = preserve_sync_lane(existing, text, heading)
    return text


def write_digests(eff: LaneReport, out: LaneReport, *, dispatched: bool = False) -> list[Path]:
    paths: list[Path] = []
    EFFICIENCY_DIGEST.parent.mkdir(parents=True, exist_ok=True)
    eff_text = build_lane_digest(
        lane="efficiency",
        open_findings=eff.findings,
        new_findings=eff.new_findings,
        actions=[f"probed {len(eff.findings)} finding(s); {len(eff.new_findings)} new"],
        enqueued=eff.enqueued,
    )
    try:
        old_eff = EFFICIENCY_DIGEST.read_text(encoding="utf-8") if EFFICIENCY_DIGEST.is_file() else ""
    except OSError:
        old_eff = ""
    EFFICIENCY_DIGEST.write_text(merge_lane_digest(old_eff, eff_text), encoding="utf-8")
    paths.append(EFFICIENCY_DIGEST)

    out_text = build_lane_digest(
        lane="output",
        open_findings=out.findings,
        new_findings=out.new_findings,
        actions=[f"probed {len(out.findings)} finding(s); {len(out.new_findings)} new"],
        enqueued=out.enqueued,
    )
    try:
        old_out = OUTPUT_DIGEST.read_text(encoding="utf-8") if OUTPUT_DIGEST.is_file() else ""
    except OSError:
        old_out = ""
    OUTPUT_DIGEST.write_text(merge_lane_digest(old_out, out_text), encoding="utf-8")
    paths.append(OUTPUT_DIGEST)

    sync_text = build_sync_digest(eff, out, dispatched=dispatched)
    try:
        old_sync = SYNC_DIGEST.read_text(encoding="utf-8") if SYNC_DIGEST.is_file() else ""
    except OSError:
        old_sync = ""
    SYNC_DIGEST.write_text(merge_sync_digest(old_sync, sync_text), encoding="utf-8")
    paths.append(SYNC_DIGEST)
    return paths


def load_sync_brief(*, max_chars: int = 3500) -> str:
    """Short brief for peer_orchestrate + automation_improve injection."""
    if not SYNC_DIGEST.is_file():
        return ""
    try:
        text = SYNC_DIGEST.read_text(encoding="utf-8")
    except OSError:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n\n… [truncated]\n"


def findings_to_opportunities(*, known: set[str] | None = None) -> list[dict[str, Any]]:
    """Convert open registry findings → improve-loop opportunities."""
    known = known or set()
    registry = _load_registry()
    items = registry.get("items") or {}
    out: list[dict[str, Any]] = []
    severity_pri = {"critical": 8, "high": 14, "medium": 22, "low": 35}

    for raw in items.values():
        if not isinstance(raw, dict) or raw.get("status") == "resolved":
            continue
        title = str(raw.get("enqueue_title") or raw.get("title") or "").strip()
        if not title:
            continue
        key = title.lower()
        if key in known:
            continue
        lane = str(raw.get("lane") or "efficiency")
        category = "efficiency" if lane == "efficiency" else "monster"
        sev = str(raw.get("severity") or "medium")
        out.append({
            "category": category,
            "title": title,
            "detail": str(raw.get("evidence") or raw.get("action") or "")[:240],
            "priority": severity_pri.get(sev, 30),
            "lane": lane,
        })
    out.sort(key=lambda x: int(x.get("priority") or 50))
    return out[:8]


def build_agent_prompt(*, eff: LaneReport, out: LaneReport) -> str:
    eff_lines = "\n".join(
        f"- [{f.severity}] {f.title}: {f.evidence[:100]}" for f in eff.findings[:8] if f.severity != "info"
    ) or "(none)"
    out_lines = "\n".join(
        f"- [{f.severity}] {f.title}: {f.evidence[:100]}" for f in out.findings[:8] if f.severity != "info"
    ) or "(none)"

    return f"""# Dual research agents — efficiency + output (synchronous)

You are **two research personas in one cycle**, working with the full automation team.
Findings must flow into structure: digests → RESEARCH_SYNC → WORK_QUEUE → automation_improve.

## Persona A — Efficiency Research Agent
**Mission:** Make every worker faster — hot paths, cache, queue discipline, pre-dispatch, latency.
Mechanical snapshot:
{eff_lines}

## Persona B — Output Research Agent
**Mission:** Build immense software — external proof, OSS monster factory, irreversible artifacts.
Mechanical snapshot:
{out_lines}

## Your task (both personas — one response)

1. Read `notes/EFFICIENCY_RESEARCH.md`, `notes/OUTPUT_RESEARCH.md`, `notes/RESEARCH_SYNC.md`,
   `notes/AUTOMATION.md`, `notes/IMPROVE_HORIZON.md`, `scripts/peer_tasks.json`.
2. **Efficiency persona:** Research 1–2 concrete speed wins (file-scoped). Append under
   `## Agent notes` in `notes/EFFICIENCY_RESEARCH.md` with dated bullets + `./scripts/peer` commands.
3. **Output persona:** Research 1 breakthrough toward impossible-before software (registry repo or hub).
   Append under `## Agent notes` in `notes/OUTPUT_RESEARCH.md`.
4. Update `notes/RESEARCH_SYNC.md` — refresh Team instructions if priorities shifted.
5. Enqueue **at most 2** executable items total (`[efficiency-research]` / `[output-research]`)
   in `notes/WORK_QUEUE.md` — sync `scripts/self_improve_context.md`. File paths required.
6. Do **not** edit `automation_improve.py` — improve loop reads sync on next tick.

Minimal diffs. Run `./scripts/peer test-quick` if you change Python.
"""


def _agent_running() -> bool:
    try:
        import peer_parallel_dispatch as ppd

        return bool(ppd.find_agent_procs())
    except Exception:  # noqa: BLE001
        return False


def _run_lane(lane: Lane) -> LaneReport:
    probe_fn = probe_efficiency if lane == "efficiency" else probe_output
    probed = probe_fn()
    open_f, new_f = merge_findings(lane, probed)
    enqueued = enqueue_findings(new_f or open_f, lane=lane)
    return LaneReport(lane=lane, findings=open_f, new_findings=new_f, enqueued=enqueued)


def run_research_cycle(
    *,
    log_fn: Callable[[str], None] | None = None,
    force: bool = False,
    digest_only: bool = False,
    dispatch_agent: bool | None = None,
) -> dict[str, Any]:
    log = log_fn or (lambda _m: None)
    if not research_enabled():
        log("dual-research: disabled")
        return {"skipped": "disabled"}

    state = _load_state()
    last_ts = float(state.get("last_cycle_ts") or 0)
    remaining = research_interval_sec() - (time.time() - last_ts)
    if not force and not digest_only and remaining > 0:
        log(f"dual-research: cooldown {remaining:.0f}s left")
        return {"skipped": "cooldown", "remaining_sec": remaining}

    log("dual-research: probing both lanes synchronously…")
    eff_report = LaneReport(lane="efficiency")
    out_report = LaneReport(lane="output")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(_run_lane, "efficiency"): "efficiency",
            pool.submit(_run_lane, "output"): "output",
        }
        for fut in as_completed(futures):
            lane = futures[fut]
            try:
                report = fut.result()
                if lane == "efficiency":
                    eff_report = report
                else:
                    out_report = report
            except Exception as exc:  # noqa: BLE001
                log(f"dual-research: {lane} probe error — {exc}")

    paths = write_digests(eff_report, out_report, dispatched=False)
    log(f"dual-research: sync → {SYNC_DIGEST.relative_to(ROOT)}")

    if digest_only:
        state["last_cycle_ts"] = time.time()
        state["last_digest_ts"] = time.time()
        _save_state(state)
        return {
            "efficiency": len(eff_report.findings),
            "output": len(out_report.findings),
            "enqueued": len(eff_report.enqueued) + len(out_report.enqueued),
            "digests": [str(p) for p in paths],
        }

    prompt = build_agent_prompt(eff=eff_report, out=out_report)
    PROMPT_PATH.write_text(prompt, encoding="utf-8")

    should_dispatch = dispatch_agent if dispatch_agent is not None else dispatch_agent_enabled()
    dispatched = False
    if should_dispatch and not _agent_running():
        try:
            import dgx_ram_budget as budget

            if budget.dispatch_allowed():
                import peer_terminal as terminal

                ready, detail = terminal.desktop_auth_ready()
                if not ready:
                    log(f"dual-research: auth not ready — {detail}")
                else:
                    rc, _ = terminal.run_cursor_agent(prompt, log_fn=log, sync=False, paid_api=False)
                    dispatched = rc == 0
                    log(f"dual-research: agent dispatch rc={rc}")
            else:
                log("dual-research: RAM cap — skip dispatch")
        except Exception as exc:  # noqa: BLE001
            log(f"dual-research: dispatch error — {exc}")
    elif should_dispatch:
        log("dual-research: agent busy — skip dispatch")

    write_digests(eff_report, out_report, dispatched=dispatched)
    state["last_cycle_ts"] = time.time()
    state["last_dispatch"] = dispatched
    state["eff_open"] = len(eff_report.findings)
    state["out_open"] = len(out_report.findings)
    _save_state(state)

    try:
        import automation_engine as engine

        engine.emit(
            "research.cycle.end",
            {
                "efficiency_open": len(eff_report.findings),
                "output_open": len(out_report.findings),
                "enqueued": len(eff_report.enqueued) + len(out_report.enqueued),
                "dispatched": dispatched,
            },
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "efficiency": len(eff_report.findings),
        "output": len(out_report.findings),
        "new_efficiency": len(eff_report.new_findings),
        "new_output": len(out_report.new_findings),
        "enqueued": eff_report.enqueued + out_report.enqueued,
        "dispatched": dispatched,
        "digests": [str(p) for p in paths],
    }


def cooldown_remaining() -> float:
    state = _load_state()
    last_ts = float(state.get("last_cycle_ts") or 0)
    return max(0.0, research_interval_sec() - (time.time() - last_ts))


def plist_body() -> str:
    py = sys.executable
    script = SCRIPTS / "peer_dual_research.py"
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
    """OVERSEER_LINUX_DUAL_RESEARCH_STATUS_2026_09_04 — systemd on Linux."""
    if sys.platform != "darwin":
        import peer_self_heal as heal

        heal.ensure_canonical_module()
        print(heal.linux_install_daemon("dual-research"))
        print(f"log: {LOG_PATH}")
        print(f"sync: {SYNC_DIGEST}")
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
    print(f"dual-research: {PLIST_PATH}")
    print(f"log: {LOG_PATH}")
    print(f"sync: {SYNC_DIGEST}")
    return 0


def cmd_uninstall() -> int:
    """OVERSEER_LINUX_DUAL_RESEARCH_STATUS_2026_09_04 — systemd on Linux."""
    if sys.platform != "darwin":
        import peer_self_heal as heal

        heal.ensure_canonical_module()
        print(heal.linux_uninstall_daemon("dual-research"))
        return 0
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{RESEARCH_LABEL}"], capture_output=True)
    if PLIST_PATH.is_file():
        PLIST_PATH.unlink()
    print("dual-research agent removed")
    return 0


def cmd_status() -> int:
    """OVERSEER_LINUX_DUAL_RESEARCH_STATUS_2026_09_04 — never launchctl on Linux."""
    running = False
    live_label = RESEARCH_LABEL
    if sys.platform != "darwin":
        import peer_self_heal as heal

        running = heal._systemd_user_active("dual-research-loop.service")
        live_label = "dual-research-loop.service"
    else:
        uid = os.getuid()
        proc = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/{RESEARCH_LABEL}"],
            capture_output=True,
            text=True,
        )
        running = proc.returncode == 0 and "state = running" in (proc.stdout or "")
    state = _load_state()
    print(f"enabled: {research_enabled()}")
    print(f"label: {live_label}")
    print(f"running: {running}")
    print(f"interval_sec: {research_interval_sec()}")
    print(f"cooldown_remaining: {cooldown_remaining():.0f}s")
    print(f"last_dispatch: {state.get('last_dispatch')}")
    print(f"eff_open: {state.get('eff_open')} out_open: {state.get('out_open')}")
    print(f"sync: {SYNC_DIGEST}")
    return 0


def run_forever(*, daemon: bool = False) -> int:
    if daemon:
        os.setsid()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        line = f"{_now_iso()} {msg}\n"
        try:
            with LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass

    log("dual-research forever start")
    while True:
        try:
            run_research_cycle(log_fn=log, force=False)
        except Exception as exc:  # noqa: BLE001
            log(f"dual-research error: {exc}")
        time.sleep(research_interval_sec())


def main() -> int:
    parser = argparse.ArgumentParser(description="Dual research agents — efficiency + output")
    parser.add_argument("--once", action="store_true", help="One research cycle")
    parser.add_argument("--forever", action="store_true", help="Forever loop")
    parser.add_argument("--daemon", action="store_true", help="Detach (with --forever)")
    parser.add_argument("--digest-only", action="store_true", help="Mechanical probe only — no agent")
    parser.add_argument("--force", action="store_true", help="Ignore cooldown")
    parser.add_argument("--no-dispatch", action="store_true", help="Skip cursor-agent dispatch")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.install:
        return cmd_install()
    if args.uninstall:
        return cmd_uninstall()
    if args.status:
        return cmd_status()
    if args.forever:
        return run_forever(daemon=args.daemon)
    report = run_research_cycle(
        force=args.force,
        digest_only=args.digest_only,
        dispatch_agent=False if args.no_dispatch else None,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
