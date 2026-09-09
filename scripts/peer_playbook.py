#!/usr/bin/env python3
"""Agent error playbook — instant fixes + self-updating catalog.

Matches errors/bottlenecks/stagnation to mechanical `./scripts/peer` recipes.
When something new is spotted, append to the registry and regenerate the markdown.

Usage:
  python3 scripts/peer_playbook.py --lookup "verify gate FAIL"
  python3 scripts/peer_playbook.py --from-cycle
  python3 scripts/peer_playbook.py --sync
  python3 scripts/peer_playbook.py --status
  ./scripts/peer playbook-lookup "noop cycle"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import zlib
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

PLAYBOOK_MD = ROOT / "notes" / "AGENT_ERROR_PLAYBOOK.md"
REGISTRY_PATH = auto.CONFIG_DIR / "playbook-entries.json"

_ERROR_HINTS = (
    "error",
    "fail",
    "timeout",
    "traceback",
    "exception",
    "blocked",
    "stopped",
    "stale",
    "drift",
    "noop",
    "verify",
    "unittest",
)


@dataclass
class PlaybookEntry:
    id: str
    symptom: str
    signatures: list[str]
    mechanical_fix: list[str]
    agent_fix: str
    owner: str = "factory_engineer"
    severity: str = "medium"
    source: str = "seed"
    hit_count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    status: str = "active"  # active | draft

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> PlaybookEntry:
        return cls(
            id=str(raw.get("id") or ""),
            symptom=str(raw.get("symptom") or ""),
            signatures=[str(s) for s in raw.get("signatures") or []],
            mechanical_fix=[str(c) for c in raw.get("mechanical_fix") or []],
            agent_fix=str(raw.get("agent_fix") or ""),
            owner=str(raw.get("owner") or "factory_engineer"),
            severity=str(raw.get("severity") or "medium"),
            source=str(raw.get("source") or "seed"),
            hit_count=int(raw.get("hit_count") or 0),
            first_seen=str(raw.get("first_seen") or ""),
            last_seen=str(raw.get("last_seen") or ""),
            status=str(raw.get("status") or "active"),
        )


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _slug(text: str, *, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:max_len] or "unknown"


def _looks_like_error(text: str) -> bool:
    low = text.lower()
    if len(text.strip()) < 12:
        return False
    if "skip duplicate" in low or "enqueue:" in low and "skip" in low:
        return False
    return any(h in low for h in _ERROR_HINTS)


def seed_entries() -> list[PlaybookEntry]:
    """Canonical fixes — mirrors peer_self_heal + oversight stagnation signals."""
    ts = _now_iso()
    rows: list[tuple[str, str, list[str], list[str], str, str, str]] = [
        (
            "verify_gate_fail",
            "Verify gate FAIL — tree broken or tests red",
            ["verify gate fail", "verify_ok=false", "verify_ok'] is false", "failure_type: tests"],
            ["./scripts/peer heal-all", "./scripts/peer test-quick", "./scripts/peer autonomous-repair"],
            "Read first failing test line; minimal fix; re-run verify-gate. Do not skip hooks.",
            "verify_runner",
            "critical",
        ),
        (
            "noop_cycle",
            "Noop cycle — queue fingerprint unchanged after ok verify",
            ["noop cycle", "noop=true", "queue fingerprint unchanged", "noop backoff"],
            ["./scripts/peer noop-break", "./scripts/peer compact-queue", "./scripts/peer poke"],
            "Demote theater queue lines; land one minimal diff that changes queue_fp or factory %.",
            "queue_steward",
            "medium",
        ),
        (
            "daemon_peer_stopped",
            "Peer loop daemon not running",
            ["peer-loop daemon stopped", "daemon_peer_stopped", "peer loop inactive"],
            ["./scripts/peer install", "./scripts/peer status"],
            "Confirm LaunchAgent loaded; check peer-loop.log; fix startup error if kickstart fails.",
            "factory_engineer",
            "critical",
        ),
        (
            "daemon_improve_stopped",
            "Improve loop daemon not running",
            ["improve-loop daemon stopped", "daemon_improve_stopped"],
            ["./scripts/peer improve-install", "./scripts/peer improve-status"],
            "Check improve-loop.log; ensure improve daemon writes horizon.",
            "factory_engineer",
            "critical",
        ),
        (
            "queue_drift",
            "WORK_QUEUE ↔ self_improve_context mismatch",
            ["queue drift", "dual-brain", "work_queue ↔", "sync-queue"],
            ["./scripts/peer sync-queue", "./scripts/peer queue-status"],
            "Make open items identical in both files; never edit only one.",
            "queue_steward",
            "high",
        ),
        (
            "queue_bloat",
            "Queue bloat — too many open items",
            ["queue bloat", "queue severe bloat", "queue above compact cap"],
            ["./scripts/peer compact-queue", "./scripts/peer sync-queue"],
            "Demote duplicates and strategy theater; cap Active to 12 executable items.",
            "queue_steward",
            "high",
        ),
        (
            "verify_storm",
            "Verify lock / timeout storm",
            ["verify storm", "verify.lock", "verify timeout", "stale_verify_lock"],
            ["./scripts/peer autonomous-repair", "./scripts/peer verify-gate-quick"],
            "Clear stale locks only via autonomous-repair; fix root test failure.",
            "verify_runner",
            "high",
        ),
        (
            "unittest_storm",
            "Unittest timeout storm",
            ["unittest storm", "timeoutexpired", "timed out after", "unittest/verify timeout"],
            ["./scripts/peer autonomous-repair", "./scripts/peer test-quick"],
            "Fix slow/hanging test; extend cache only as temporary relief.",
            "verify_runner",
            "high",
        ),
        (
            "adapt_stale",
            "Adapt fingerprint stale after git changes",
            ["adapt stale", "adapt audit not ok", "should_re_adapt"],
            ["./scripts/peer adapt", "./scripts/peer audit"],
            "Run adapt heal; fix audit warnings in automation.config / profiles.",
            "adapt_specialist",
            "medium",
        ),
        (
            "cursor_auth",
            "Cursor auth not ready — cannot dispatch agent",
            ["cursor auth not ready", "cursor_agent_auth", "auth not ready"],
            [],
            "Human: run `cursor-agent login` in terminal; do not enqueue code fixes for auth.",
            "factory_engineer",
            "high",
        ),
        (
            "ram_dispatch_blocked",
            "RAM cap blocking cursor-agent dispatch",
            ["ram dispatch blocked", "dispatch blocked", "ram cap"],
            ["./scripts/peer ram-purge", "./scripts/peer ram-status"],
            "Rebalance RAM; trim daemon RSS before forcing dispatch.",
            "compression_engineer",
            "medium",
        ),
        (
            "repo_flaw_critical",
            "Critical repo flaws from mechanical research",
            ["critical repo flaw", "flaw-research", "[flaw-research]"],
            ["./scripts/peer repo-research-digest", "./scripts/peer heal-all"],
            "Fix highest-severity flaw with minimal diff + test-quick.",
            "factory_engineer",
            "critical",
        ),
        (
            "git_head_stuck",
            "Git HEAD unchanged while WORKING — no landed diffs",
            ["git head unchanged", "agents not landing diffs"],
            ["./scripts/peer pre-dispatch", "./scripts/peer post-cycle"],
            "Land smallest diff; run post-cycle verify before marking done.",
            "factory_engineer",
            "high",
        ),
        (
            "factory_flat",
            "Factory readiness flat — no progress",
            ["factory readiness flat", "harness rubric flat", "stagnation"],
            ["./scripts/peer green", "./scripts/peer progress", "./scripts/peer heal-all"],
            "Pick one factory outcome (verify green, queue advance, external proof).",
            "factory_engineer",
            "medium",
        ),
        (
            "verify_fail_hold",
            "Last cycle verify failed — dispatch held",
            [
                "verify_fail_hold",
                "failure_type: self-check",
                "failure_type=self-check",
                "type=self-check",
            ],
            ["./scripts/peer autonomous-repair", "./scripts/peer check"],
            "When failure_type=self-check: fix peer_orchestrate self-check first. If failure_type=tests, use verify_fail_tests instead.",
            "verify_runner",
            "high",
        ),
        (
            "verify_fail_tests",
            "Last cycle verify failed — type=tests (not self-check)",
            [
                "verify_fail_tests",
                "failure_type=tests",
                "failure_type: tests",
                "type=tests",
                "verify had 1 failure(s); type=tests",
                "unittest fail",
            ],
            [
                "./scripts/peer autonomous-repair",
                "./scripts/peer test-quick",
                "./scripts/peer verify-gate-quick",
            ],
            "Read first FAIL/ERROR/AssertionError line; minimal test fix; re-run test-quick. Do NOT chase self-check when failure_type=tests.",
            "verify_runner",
            "high",
        ),
        (
            "dual_brain_ram_peer",
            "Dual-brain: ram-peer-loop alongside hub",
            ["dual_brain_ram_peer", "ram-peer-loop"],
            ["./scripts/peer stop-ram-peer"],
            "Use automation-hub peer loop only.",
            "factory_engineer",
            "high",
        ),
        (
            "improve_not_waking_peer",
            "Improve loop not waking peer",
            ["improve_not_waking_peer", "peer-turn.signal"],
            ["./scripts/peer poke", "./scripts/peer improve-status"],
            "Ensure improve loop touches peer-turn.signal after plan write.",
            "factory_engineer",
            "medium",
        ),
        (
            "plan_gate_chicken_egg",
            "Plan-gate chicken-egg — verify_ok=false forever skips primary",
            [
                "skip primary",
                "plan-gate still hard-blocked",
                "plan-gate BLOCKED",
                "intelligence: skip primary",
            ],
            [
                "./scripts/peer sync-queue",
                "./scripts/peer adapt",
                "./scripts/peer heal-all",
                "./scripts/peer poke",
            ],
            "Soft Episodic/Self-correction = keep dispatching. Seed real verify; never idle on chicken-egg. Read notes/AGENT_SURVIVAL.md.",
            "factory_engineer",
            "critical",
        ),
        (
            "queue_junk_self_check_paste",
            "Corrupt WORK_QUEUE Active line from pasted self-check/FAIL stdout",
            [
                "peer_orchestrate self-check failed",
                "✗ tests not ok",
                "tests: FAIL — failed",
                "=== automation self-check ===",
            ],
            ["./scripts/peer sync-queue", "./scripts/peer compact-queue"],
            "Delete truncated junk Active lines; never paste CLI stdout into queue titles. Sync both queue files.",
            "queue_steward",
            "high",
        ),
        (
            "adapt_stale_mislabel_queue",
            "Queue drift mislabeled as ADAPT_STALE",
            [
                "verify ADAPT_STALE: queue",
                "category=queue",
                "only in notes/WORK_QUEUE",
            ],
            ["./scripts/peer sync-queue", "./scripts/peer adapt"],
            "Queue errors are Institutional memory — sync-queue first. adapt_state only for fingerprint.",
            "adapt_specialist",
            "high",
        ),
        (
            "peer_quiet_kickstart",
            "Peer loop quiet >3m — poke does not wake",
            ["peer log silent", "peer_log_age", "event wait"],
            ["./scripts/peer poke", "./scripts/peer install"],
            "launchctl kickstart -k gui/$(id -u)/com.togi.<ns>-peer-loop when poke no-ops.",
            "factory_engineer",
            "high",
        ),
        (
            "namespace_oversight_drop",
            "Oversight LaunchAgent missing after config_namespace flip",
            [
                "oversight missing",
                "automation-hub-oversight",
                "automation-oversight",
                "config_namespace",
            ],
            ["./scripts/peer oversight-install", "./scripts/peer install-all"],
            "Reinstall oversight for live config_namespace; bootout rogue twin labels.",
            "factory_engineer",
            "high",
        ),
        (
            "agent_exit_not_tree_red",
            "cursor-agent non-zero stamped verify_ok=false without red tests",
            ["cursor-agent non-zero", "cursor-agent exit", "agent exit"],
            ["./scripts/peer test-quick", "./scripts/peer poke"],
            "Re-verify; soft Episodic — keep working unless test-quick actually fails.",
            "verify_runner",
            "medium",
        ),
    ]
    return [
        PlaybookEntry(
            id=rid,
            symptom=symptom,
            signatures=sigs,
            mechanical_fix=fixes,
            agent_fix=agent,
            owner=owner,
            severity=sev,
            source="seed",
            first_seen=ts,
            last_seen=ts,
        )
        for rid, symptom, sigs, fixes, agent, owner, sev in rows
    ]


def _load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.is_file():
        return {"entries": [e.to_dict() for e in seed_entries()], "version": 1}
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        if not isinstance(data.get("entries"), list):
            data["entries"] = []
        return data
    except (OSError, json.JSONDecodeError):
        return {"entries": [e.to_dict() for e in seed_entries()], "version": 1}


def _save_registry(data: dict[str, Any]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_entries(*, merge_seed: bool = True) -> list[PlaybookEntry]:
    data = _load_registry()
    by_id = {str(e.get("id")): PlaybookEntry.from_dict(e) for e in data.get("entries") or [] if e.get("id")}
    if merge_seed:
        for seed in seed_entries():
            if seed.id not in by_id:
                by_id[seed.id] = seed
            elif seed.id == "noop_cycle" and by_id[seed.id].severity == "critical":
                by_id[seed.id] = PlaybookEntry.from_dict(
                    {**by_id[seed.id].to_dict(), "severity": "medium"}
                )
    return list(by_id.values())


def save_entries(entries: list[PlaybookEntry]) -> None:
    data = _load_registry()
    data["entries"] = [e.to_dict() for e in entries]
    data["updated_at"] = _now_iso()
    _save_registry(data)


def _signature_match(text: str, signature: str) -> bool:
    if not signature:
        return False
    low = text.lower()
    sig = signature.lower()
    if sig.startswith("re:"):
        try:
            return bool(re.search(sig[3:], text, re.IGNORECASE))
        except re.error:
            return sig[3:].lower() in low
    return sig in low


def match_text(text: str, *, entries: list[PlaybookEntry] | None = None) -> list[PlaybookEntry]:
    entries = entries if entries is not None else load_entries()
    hits: list[PlaybookEntry] = []
    for entry in entries:
        if entry.status == "draft" and entry.hit_count == 0:
            continue
        if any(_signature_match(text, sig) for sig in entry.signatures):
            hits.append(entry)
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    hits.sort(key=lambda e: (order.get(e.severity, 9), -e.hit_count))
    return hits


def match_many(texts: list[str], *, limit: int = 8) -> list[PlaybookEntry]:
    seen: set[str] = set()
    out: list[PlaybookEntry] = []
    for text in texts:
        if not text:
            continue
        for entry in match_text(text):
            if entry.id in seen:
                continue
            seen.add(entry.id)
            out.append(entry)
            if len(out) >= limit:
                return out
    return out


def match_bottleneck_id(bottleneck_id: str) -> PlaybookEntry | None:
    for entry in load_entries():
        if entry.id == bottleneck_id:
            return entry
        if any(bottleneck_id.lower() in sig.lower() for sig in entry.signatures):
            return entry
    return None


def bump_hits(entry_ids: list[str]) -> None:
    if not entry_ids:
        return
    entries = load_entries(merge_seed=False)
    ids = set(entry_ids)
    ts = _now_iso()
    changed = False
    for entry in entries:
        if entry.id in ids:
            entry.hit_count += 1
            entry.last_seen = ts
            changed = True
    if changed:
        save_entries(entries)


def record_observation(
    text: str,
    *,
    mechanical_fix: list[str] | None = None,
    agent_fix: str = "",
    owner: str = "factory_engineer",
    severity: str = "medium",
    source: str = "auto",
) -> PlaybookEntry:
    """Add playbook row when novel; bump hits when known."""
    text = text.strip()
    if not text:
        raise ValueError("empty observation")

    existing = match_text(text)
    if existing:
        bump_hits([existing[0].id])
        return existing[0]

    if not _looks_like_error(text):
        # COMPRESSION_ZLIB_PLAYBOOK_OBS_ID_2026_09_04 — zlib keeps playbook
        # import libcrypto-free (~5.7MB); same 10-hex width as prior sha256 slice.
        _raw = text.encode()
        _obs = f"{zlib.adler32(_raw) & 0xffffffff:08x}{zlib.crc32(_raw) & 0xffffffff:08x}"[:10]
        entry = PlaybookEntry(
            id=f"obs_{_obs}",
            symptom=text[:120],
            signatures=[text[:80].lower()],
            mechanical_fix=mechanical_fix or ["./scripts/peer heal-all"],
            agent_fix=agent_fix or "Investigate root cause; add permanent fix; run test-quick.",
            owner=owner,
            severity=severity,
            source=source,
            hit_count=1,
            first_seen=_now_iso(),
            last_seen=_now_iso(),
            status="draft",
        )
    else:
        entry = PlaybookEntry(
            id=f"obs_{_slug(text)}",
            symptom=text[:120],
            signatures=[text[:80].lower()],
            mechanical_fix=mechanical_fix or ["./scripts/peer heal-all", "./scripts/peer green"],
            agent_fix=agent_fix or "Diagnose, minimal diff, verify-gate, sync queue.",
            owner=owner,
            severity=severity,
            source=source,
            hit_count=1,
            first_seen=_now_iso(),
            last_seen=_now_iso(),
            status="draft",
        )

    entries = load_entries(merge_seed=False)
    if any(e.id == entry.id for e in entries):
        bump_hits([entry.id])
        return entry
    entries.append(entry)
    save_entries(entries)
    sync_markdown()
    return entry


def ingest_from_bottlenecks(bottlenecks: list[Any]) -> list[PlaybookEntry]:
    matched: list[PlaybookEntry] = []
    novel: list[str] = []
    for bn in bottlenecks:
        bid = getattr(bn, "id", None) or (bn.get("id") if isinstance(bn, dict) else None)
        title = getattr(bn, "title", None) or (bn.get("title") if isinstance(bn, dict) else "")
        if not bid:
            continue
        entry = match_bottleneck_id(str(bid))
        if entry:
            matched.append(entry)
        else:
            novel.append(f"{bid}: {title}")
    if matched:
        bump_hits([e.id for e in matched])
    for text in novel:
        record_observation(text, source="self-heal", severity="medium")
    return matched


def ingest_from_context(ctx: dict[str, Any]) -> list[PlaybookEntry]:
    """Ingest stagnation reasons, bottlenecks, last cycle, log tails."""
    texts: list[str] = []
    last = ctx.get("last_cycle") or {}
    if last.get("failure_type"):
        texts.append(f"failure_type: {last['failure_type']}")
    if last.get("summary"):
        texts.append(str(last["summary"]))
    for bn in ctx.get("bottlenecks") or []:
        texts.append(str(bn.get("title") or bn.get("id") or ""))
        texts.append(str(bn.get("evidence") or ""))
    for ln in (ctx.get("peer_log_tail") or [])[-20:]:
        if _looks_like_error(ln):
            texts.append(ln)
    for ln in (ctx.get("improve_log_tail") or [])[-10:]:
        if _looks_like_error(ln):
            texts.append(ln)
    if ctx.get("stall_reason"):
        texts.append(str(ctx["stall_reason"]))

    matched = match_many(texts)
    if matched:
        bump_hits([e.id for e in matched])

    seen_ids = {e.id for e in matched}
    for text in texts:
        if not text or len(text.strip()) < 20:
            continue
        if match_text(text):
            continue
        if _looks_like_error(text):
            entry = record_observation(text[:200], source="cycle-ingest")
            if entry.id not in seen_ids:
                matched.append(entry)
                seen_ids.add(entry.id)
    return matched


def format_instant_fixes(entries: list[PlaybookEntry], *, max_entries: int = 6) -> str:
    if not entries:
        return "- Run `./scripts/peer heal-all` then `./scripts/peer green`"
    lines: list[str] = []
    for entry in entries[:max_entries]:
        cmds = " · ".join(f"`{c}`" for c in entry.mechanical_fix[:3]) or "(agent only)"
        lines.append(f"- **{entry.symptom}** → {cmds}")
        if entry.agent_fix:
            lines.append(f"  - Agent: {entry.agent_fix[:160]}")
    return "\n".join(lines)


def format_prompt_block(entries: list[PlaybookEntry]) -> str:
    if not entries:
        return ""
    return (
        "## Instant fixes (playbook)\n\n"
        f"{format_instant_fixes(entries)}\n\n"
        f"Full catalog: `notes/AGENT_ERROR_PLAYBOOK.md` · lookup: `./scripts/peer playbook-lookup \"<error>\"`\n"
    )


def sync_markdown(*, entries: list[PlaybookEntry] | None = None) -> Path:
    entries = entries if entries is not None else load_entries()
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    entries = sorted(entries, key=lambda e: (order.get(e.severity, 9), e.id))

    lines = [
        "# Agent error playbook",
        "",
        "Symptom → instant mechanical fix → agent escalation. **Auto-updated** from self-heal, oversight, and cycle ingest.",
        "",
        "Lookup: `./scripts/peer playbook-lookup \"<error text>\"` · Sync: `./scripts/peer playbook-sync`",
        "",
        "## Quick reference (run first)",
        "",
        "| Situation | Run immediately |",
        "|-----------|-----------------|",
        "| Anything unknown / red tree | `./scripts/peer heal-all` |",
        "| Noop / queue stuck | `./scripts/peer noop-break` |",
        "| After agent lands diff | `./scripts/peer post-cycle` |",
        "| Before cursor-agent | `./scripts/peer pre-dispatch` |",
        "| Verify red | `./scripts/peer autonomous-repair` → `./scripts/peer test-quick` |",
        "",
        "## Catalog",
        "",
        "| ID | Severity | Symptom | Mechanical fix | Agent fix | Owner |",
        "|----|----------|---------|----------------|-----------|-------|",
    ]
    for e in entries:
        fixes = "<br>".join(e.mechanical_fix[:3]) or "—"
        agent = e.agent_fix.replace("|", "\\|")[:100]
        sym = e.symptom.replace("|", "\\|")[:80]
        lines.append(
            f"| `{e.id}` | {e.severity} | {sym} | {fixes} | {agent} | {e.owner} |"
        )

    drafts = [e for e in entries if e.status == "draft"]
    if drafts:
        lines.extend(["", "## Draft (auto-spotted — promote after verified fix)", ""])
        for e in drafts:
            lines.append(f"- `{e.id}`: {e.symptom} (seen {e.hit_count}x, source={e.source})")

    lines.extend(
        [
            "",
            "## When you spot something new",
            "",
            "1. Run mechanical fix from table above.",
            "2. If novel, add: `./scripts/peer playbook-add \"symptom text\" --fix heal-all`",
            "3. Or let oversight/self-heal auto-ingest on next cycle.",
            "",
            f"_Updated { _now_iso() } · registry: `{REGISTRY_PATH}`_",
            "",
        ]
    )
    PLAYBOOK_MD.parent.mkdir(parents=True, exist_ok=True)
    PLAYBOOK_MD.write_text("\n".join(lines), encoding="utf-8")
    return PLAYBOOK_MD


def add_entry_manual(
    symptom: str,
    *,
    fix_commands: list[str],
    agent_fix: str = "",
    owner: str = "factory_engineer",
    severity: str = "medium",
) -> PlaybookEntry:
    entry = PlaybookEntry(
        id=f"manual_{_slug(symptom)}",
        symptom=symptom,
        signatures=[symptom.lower(), _slug(symptom)],
        mechanical_fix=fix_commands,
        agent_fix=agent_fix or "Apply minimal fix; test-quick; sync queue.",
        owner=owner,
        severity=severity,
        source="manual",
        hit_count=1,
        first_seen=_now_iso(),
        last_seen=_now_iso(),
        status="active",
    )
    entries = load_entries(merge_seed=False)
    entries = [e for e in entries if e.id != entry.id]
    entries.append(entry)
    save_entries(entries)
    sync_markdown(entries=entries)
    return entry


def status_text() -> str:
    entries = load_entries()
    drafts = sum(1 for e in entries if e.status == "draft")
    return (
        f"entries: {len(entries)} (drafts: {drafts})\n"
        f"registry: {REGISTRY_PATH}\n"
        f"markdown: {PLAYBOOK_MD}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent error playbook")
    parser.add_argument("--lookup", metavar="TEXT", help="Match error text to fixes")
    parser.add_argument("--from-cycle", action="store_true", help="Ingest from live peer context")
    parser.add_argument("--sync", action="store_true", help="Regenerate notes/AGENT_ERROR_PLAYBOOK.md")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--add", metavar="SYMPTOM", help="Add manual playbook entry")
    parser.add_argument("--fix", action="append", default=[], help="Mechanical fix command (repeatable)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.status:
        print(status_text())
        return 0

    if args.sync:
        path = sync_markdown()
        print(f"synced → {path}")
        return 0

    if args.lookup:
        hits = match_text(args.lookup)
        if args.json:
            print(json.dumps([h.to_dict() for h in hits], indent=2))
        else:
            print(format_instant_fixes(hits) if hits else "No match — try `./scripts/peer heal-all`")
        if hits:
            bump_hits([h.id for h in hits[:1]])
        return 0

    if args.from_cycle:
        import peer_investigate as investigate

        ctx = investigate.collect_context()
        hits = ingest_from_context(ctx)
        sync_markdown()
        if args.json:
            print(json.dumps({"matched": len(hits), "entries": [h.id for h in hits]}, indent=2))
        else:
            print(f"ingested {len(hits)} match(es)")
            print(format_instant_fixes(hits))
        return 0

    if args.add:
        fixes = args.fix or ["./scripts/peer heal-all"]
        entry = add_entry_manual(args.add, fix_commands=fixes)
        print(f"added `{entry.id}` → {PLAYBOOK_MD}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
