#!/usr/bin/env python3
"""Comms improve forever — research + enqueue efficient agent communication upgrades.

Separate from ``automation_improve`` (OSS factory). This daemon:

- Researches A2A / bus / MCP / encoding patterns (``automation_comms_research``)
- Audits GLink bus + per-agent vaults (``peer_agent_comms``)
- Writes COMMS_HORIZON + execute prompts
- Enqueues **comms-kit work only** (GLink schema, bus, vaults, protocol docs)
- Wakes peer loop — does **not** replace factory improve

Usage:
  python3 scripts/automation_comms_improve.py --forever --write --research
  python3 scripts/automation_comms_improve.py --install
  python3 scripts/automation_comms_improve.py --status
  ./scripts/peer comms-improve-status
"""

from __future__ import annotations

import argparse
import json
import os
import re
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

import automation_comms_research as comms_research  # noqa: E402
import automation_config as cfg_mod  # noqa: E402
import project_automation as auto  # noqa: E402

ROOT = auto.ROOT
CONFIG_DIR = auto.CONFIG_DIR
PLAN_PATH = CONFIG_DIR / "automation-comms-improve-plan.md"
EXECUTE_PATH = CONFIG_DIR / "automation-comms-improve-execute.md"
COMBINED_PATH = CONFIG_DIR / "automation-comms-improve.md"
HORIZON_PATH = CONFIG_DIR / "COMMS_HORIZON.md"
HORIZON_REPO_PATH = ROOT / "notes" / "COMMS_HORIZON.md"
LOG_PATH = CONFIG_DIR / "comms-improve-loop.log"
STATE_PATH = CONFIG_DIR / "comms-improve-state.json"

COMMS_IMPROVE_LABEL = (
    f"com.togi.{auto.CFG.get('config_namespace', 'automation-hub')}-comms-improve-loop"
)
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{COMMS_IMPROVE_LABEL}.plist"

NORTH_STAR = (
    "Minimum tokens + maximum signal between 8 niches: structured GLink bus, "
    "per-agent vaults, targeted REQ/ACK — never English standups on the hot path."
)

COMMS_KIT_MARKERS = (
    "glink",
    "peer_agent_comms",
    "agent-comms",
    "bus.jsonl",
    "agent comms",
    "communication",
    "comms improve",
    "comms_improve",
    "comms_trends",
    "message bus",
    "shared bus",
    "shared memory",
    "vault",
    "a2a",
    "mcp",
    "encoding",
    "msgpack",
    "blackboard",
    "gibberlink",
    "ggwave",
    "protocol",
    "STAT",
    "REQ",
    "ACK",
)

SELF_TARGET_MARKERS = (
    "automation_comms_improve",
    "comms improve forever",
    "comms horizon",
    "comms_improve",
    "notes/comms_horizon",
)

GOALS = ("efficiency", "better", "smooth", "ease")

FALLBACK_POLL_SEC = 300.0
ENQUEUE_CAP = 2

# Self-test gate: comms improve only enqueues / wakes peer when these pass.
COMMS_SELF_TEST_MODULES = (
    "tests.test_automation_comms_improve",
    "tests.test_automation_comms_research",
    "tests.test_peer_agent_comms",
)


@dataclass
class CommsVerifyResult:
    ok: bool
    unittest_ok: bool
    smoke_ok: bool
    detail: str
    failures: list[str] = field(default_factory=list)


def comms_self_test_required() -> bool:
    return bool(auto.CFG.get("comms_improve_self_test_required", True))


def _run_comms_unittest_suite() -> tuple[bool, list[str]]:
    """Run comms-kit unit tests from repo root; return (ok, failure_lines)."""
    cmd = [sys.executable, "-m", "unittest", *COMMS_SELF_TEST_MODULES, "-q"]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return True, []

    failures: list[str] = []
    blob = (proc.stderr or proc.stdout or "").strip()
    for line in blob.splitlines():
        line = line.strip()
        if line and ("FAIL" in line or "ERROR" in line or "Error" in line):
            failures.append(line)
    if not failures and blob:
        failures.append(blob.splitlines()[-1])
    if not failures:
        failures.append(f"unittest exit {proc.returncode}")
    return False, failures[:5]


def _run_comms_smoke_checks() -> tuple[bool, list[str]]:
    """Import + minimal API calls — catches broken installs without full unittest."""
    failures: list[str] = []
    try:
        report = comms_research.build_comms_report(refresh=False)
        if not isinstance(report, dict) or "gap_count" not in report:
            failures.append("comms_research.build_comms_report shape invalid")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"comms_research smoke: {exc}")

    try:
        signals = gather_signals(quick=True, research=False)
        if not isinstance(signals.opportunities, list):
            failures.append("gather_signals opportunities not a list")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"gather_signals smoke: {exc}")

    try:
        import peer_agent_comms as comms

        status = comms.status_dict()
        if not isinstance(status, dict):
            failures.append("peer_agent_comms.status_dict not dict")
        else:
            schema = status.get("schema") if isinstance(status.get("schema"), dict) else {}
            validators = schema.get("validators") if isinstance(schema.get("validators"), dict) else {}
            materialize = schema.get("materialize") if isinstance(schema.get("materialize"), dict) else {}
            for key in (
                "pri",
                "ttl",
                "re",
                "sum_tx_alias",
                "sum_nested",
                "stat_op_aliases",
                "stat_asn",
                "stat_git",
                "last_ack",
                "open_threads",
                "req_self",
                "prefer_ph",
            ):
                if key not in validators:
                    failures.append(f"peer_agent_comms.glink_schema missing validators.{key}")
            if "role_board" not in materialize:
                failures.append("peer_agent_comms.glink_schema missing materialize.role_board")
            if "open_reqs_mcp" not in materialize:
                failures.append("peer_agent_comms.glink_schema missing materialize.open_reqs_mcp")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"peer_agent_comms smoke: {exc}")

    return len(failures) == 0, failures


def verify_comms_kit(*, log_fn: Callable[[str], None] | None = None) -> CommsVerifyResult:
    """Green-light gate: unittest + smoke must pass before comms improve ships work."""
    log = log_fn or (lambda _msg: None)
    unittest_ok, ut_failures = _run_comms_unittest_suite()
    if unittest_ok:
        log("self-test: unittest OK")
    else:
        for line in ut_failures:
            log(f"self-test: unittest FAIL — {line}")

    smoke_ok, smoke_failures = _run_comms_smoke_checks()
    if smoke_ok:
        log("self-test: smoke OK")
    else:
        for line in smoke_failures:
            log(f"self-test: smoke FAIL — {line}")

    ok = unittest_ok and smoke_ok
    failures = ut_failures + smoke_failures
    if ok:
        detail = "green light — comms kit self-tests passed"
    else:
        detail = "red light — fix comms kit before enqueue/implement"
    return CommsVerifyResult(
        ok=ok,
        unittest_ok=unittest_ok,
        smoke_ok=smoke_ok,
        detail=detail,
        failures=failures,
    )


def comms_improve_enabled() -> bool:
    return bool(auto.CFG.get("comms_improve_enabled", True))


def _wake_sec() -> float:
    try:
        return max(15.0, float(auto.CFG.get("comms_improve_wake_sec") or 90.0))
    except (TypeError, ValueError):
        return 90.0


def _continuous_wake_sec() -> float:
    """Active sidecar heartbeat — floor 15s so hub/DGX overlays (comms=3|8) cannot hyper-poll.

    Peer shallow floor is 30s; improve continuous floor is 15s. A 5s/8s comms sidecar
    churns ~2–6× more than those loops for no queue yield (pre-dispatch > spin).
    """
    try:
        return max(
            15.0,
            float(auto.CFG.get("comms_improve_continuous_wake_sec") or 30.0),
        )
    except (TypeError, ValueError):
        return 30.0


def _min_cycle_sec() -> float:
    try:
        return max(10.0, float(auto.CFG.get("comms_improve_min_cycle_sec") or 30.0))
    except (TypeError, ValueError):
        return 30.0


def _research_every_n_cycles() -> int:
    try:
        return max(1, int(auto.CFG.get("comms_improve_research_interval_cycles") or 8))
    except (TypeError, ValueError):
        return 8


@dataclass
class Opportunity:
    category: str
    title: str
    detail: str
    priority: int = 50


@dataclass
class CommsSignals:
    live: dict[str, Any]
    comms_status: dict[str, Any]
    research: dict[str, Any]
    opportunities: list[Opportunity] = field(default_factory=list)
    bus_sample: list[dict[str, Any]] = field(default_factory=list)
    verify: CommsVerifyResult | None = None


def is_comms_kit_target(opp: Opportunity) -> bool:
    blob = f"{opp.title} {opp.detail}".lower()
    if any(m in blob for m in SELF_TARGET_MARKERS):
        return False
    return any(m in blob for m in COMMS_KIT_MARKERS)


def _log(msg: str, *, daemon: bool) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    if daemon:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    else:
        print(line, flush=True)


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(data: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def gather_signals(*, quick: bool = True, research: bool = False) -> CommsSignals:
    live_state = auto.measure_live_state(quick=quick)
    queue = auto.open_work_items()
    live = auto.live_snapshot(live_state, queue)

    comms_status: dict[str, Any] = {}
    bus_sample: list[dict[str, Any]] = []
    try:
        import peer_agent_comms as comms

        if comms.comms_enabled():
            comms_status = comms.status_dict()
            bus_sample = comms.read_bus(limit=12)
    except Exception as exc:  # noqa: BLE001
        comms_status = {"error": str(exc)}

    report = comms_research.build_comms_report(refresh=False)
    if research:
        report = comms_research.build_comms_report(refresh=True)

    signals = CommsSignals(
        live=live,
        comms_status=comms_status,
        research=report,
        bus_sample=bus_sample,
    )
    signals.opportunities = rank_opportunities(signals)
    return signals


def rank_opportunities(signals: CommsSignals) -> list[Opportunity]:
    opps: list[Opportunity] = []

    bus_n = int(signals.comms_status.get("bus_messages") or 0)
    enabled = bool(signals.comms_status.get("enabled"))
    if not enabled:
        opps.append(
            Opportunity(
                "smooth",
                "Enable GLink agent comms",
                "Set agent_comms_enabled true; run ./scripts/peer comms-init",
                priority=8,
            )
        )
    elif bus_n == 0:
        opps.append(
            Opportunity(
                "smooth",
                "Seed GLink bus with orchestrator STAT",
                "Dispatch peer plan or post STAT lines so agents practice structured comms",
                priority=12,
            )
        )
    elif bus_n > 500:
        opps.append(
            Opportunity(
                "efficiency",
                "Prune or rotate GLink bus.jsonl",
                f"bus has {bus_n} messages — archive tail, materialize SUM into vaults",
                priority=20,
            )
        )

    # Vaults empty?
    for agent in signals.comms_status.get("agents") or []:
        if not isinstance(agent, dict):
            continue
        if int(agent.get("todo") or 0) == 0 and int(agent.get("done") or 0) == 0:
            opps.append(
                Opportunity(
                    "ease",
                    f"Populate vault for {agent.get('job_title')}",
                    f"role `{agent.get('role_id')}` — add todo + SUM via GLink or state.json",
                    priority=35,
                )
            )
            break

    for raw in signals.research.get("gaps") or []:
        if not isinstance(raw, dict):
            continue
        opps.append(
            Opportunity(
                "efficiency",
                f"[comms] {raw.get('theme')}",
                f"{raw.get('opportunity')} — {raw.get('efficiency_note')}",
                priority=int(raw.get("priority") or 40),
            )
        )

    for raw in signals.research.get("partials") or []:
        if not isinstance(raw, dict):
            continue
        opps.append(
            Opportunity(
                "better",
                f"[comms] {raw.get('theme')}",
                f"{raw.get('opportunity')} — {raw.get('efficiency_note')}",
                priority=int(raw.get("priority") or 30),
            )
        )

    # English on bus detector — skip when post_glink already rejects prose (wave-19).
    try:
        import peer_agent_comms as pac

        english_gate = callable(getattr(pac, "_reject_english_heavy", None)) and callable(
            getattr(pac, "validate_glink_payload", None)
        )
    except Exception:  # noqa: BLE001
        english_gate = False
    if not english_gate:
        for msg in signals.bus_sample:
            if not isinstance(msg, dict):
                continue
            p = json.dumps(msg.get("p") or {})
            if len(p) > 200 or re.search(r"\b(the|should|please)\b", p, re.I):
                opps.append(
                    Opportunity(
                        "efficiency",
                        "Bus payload too verbose — enforce GLink codes",
                        "Add validator in peer_agent_comms.post_glink; reject English-heavy p blobs",
                        priority=14,
                    )
                )
                break

    opps.sort(key=lambda o: o.priority)
    return opps


def build_plan_prompt(signals: CommsSignals) -> str:
    top = [o for o in signals.opportunities if is_comms_kit_target(o)][:5]
    focus = "\n".join(f"- [{o.category}] {o.title}: {o.detail}" for o in top) or "- (audit GLink + research)"
    bus_n = signals.comms_status.get("bus_messages", "?")
    return textwrap.dedent(
        f"""\
        # Comms improve — PLAN (communication efficiency only)

        **North star:** {NORTH_STAR}

        **Not in scope:** factory/OSS work, ASI rubric, automation_improve.py edits.

        ## Live comms
        - GLink enabled: {signals.comms_status.get('enabled')}
        - Bus messages: {bus_n}
        - Research gaps: {signals.research.get('gap_count')} · partial: {signals.research.get('partial_count')}

        ## Ranked opportunities
        {focus}

        ## Plan deliverable
        1. Pick **one** comms-kit upgrade (schema, validator, bus prune, vault sync, MCP bridge).
        2. Define measurable efficiency win (tokens, latency, or agent visibility).
        3. List files: `peer_agent_comms.py`, `notes/COMMS_TRENDS.md`, dashboard `/api/comms`.
        4. Do **not** write code in this step.
        """
    )


def build_execute_prompt(signals: CommsSignals) -> str:
    top = [o for o in signals.opportunities if is_comms_kit_target(o)][:3]
    focus = "\n".join(f"- [{o.category}] {o.title}" for o in top)
    return textwrap.dedent(
        f"""\
        # Comms improve — EXECUTE

        **North star:** {NORTH_STAR}

        Implement the approved comms plan. **Parallel peers** on disjoint comms scopes only.

        ## Focus
        {focus}

        ## Rules
        1. Touch only comms kit: `peer_agent_comms.py`, GLink bus/vaults, `automation_comms_*`, dashboard `/api/comms`.
        2. Prefer structured GLink over English in examples and validators.
        3. Update `notes/COMMS_TRENDS.md` when research informs the change.
        4. Run `python3 scripts/automation_comms_improve.py --verify` after edits — **green light only**.
        5. If self-test fails, **do not land** the change; revert or fix until verify passes.
        6. Post a `DIFF` GLink line to the bus describing what changed.
        7. Do **not** commit unless the user asked.
        """
    )


def build_horizon_markdown(signals: CommsSignals, *, cycle: int | None = None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cycle_bit = f" · cycle {cycle}" if cycle else ""
    verify = signals.verify
    if verify is not None:
        if verify.ok:
            verify_line = f"**GREEN** — {verify.detail}"
        else:
            tail = "; ".join(verify.failures[:2]) or verify.detail
            verify_line = f"**RED** — enqueue blocked ({tail})"
    else:
        verify_line = "not run this cycle"
    lines = [
        "# Comms horizon — agent communication efficiency",
        "",
        f"_Updated {now}{cycle_bit}_ · comms improve forever",
        "",
        f"**North star:** {NORTH_STAR}",
        "",
        "## Live",
        "",
        f"| Signal | Value |",
        f"|--------|-------|",
        f"| Self-test | {verify_line} |",
        f"| GLink | enabled={signals.comms_status.get('enabled')} · bus={signals.comms_status.get('bus_messages', 0)} msgs |",
        f"| Research | gaps {signals.research.get('gap_count')} · partial {signals.research.get('partial_count')} |",
        f"| Queue | {signals.live.get('queue_source', '?')} · {len(signals.live.get('open_items') or [])} open |",
        "",
        "## NOW — efficiency first",
        "",
    ]
    now_opps = [o for o in signals.opportunities if is_comms_kit_target(o)][:5]
    if now_opps:
        for i, o in enumerate(now_opps, 1):
            lines.append(f"{i}. **[{o.category}]** {o.title}")
            lines.append(f"   - {o.detail}")
            lines.append(f"   - priority `{o.priority}`")
    else:
        lines.append("_No comms opportunities this cycle._")
    lines.extend(
        [
            "",
            "## GLink REQ → MCP",
            "",
            "Landed on hub `scripts/peer_agent_comms.py` (PROTOCOL_VERSION=1, additive — no bump).",
            "",
            "| Form | Result |",
            "|------|--------|",
            "| `need=mcp:<tool>` | `mcp=1`, `args.tool=<tool>` |",
            "| `need=mcp` + `args.tool` | same after `_normalize_req_need` |",
            "| fixed `vfy\\|adapt\\|heal\\|…` | niche REQ (not MCP) |",
            "| free-text need | **rejected** |",
            "| ACK `cid\\|ref` | closes open REQ (`materialize_open_reqs_mcp`) |",
            "",
            "Disk bus = structured intent; Cursor MCP namespaces = tool execution. "
            "See `notes/COMMS_TRENDS.md` **[HAVE] MCP / tool protocol**.",
            "",
            "## Research map",
            "",
            "See `notes/COMMS_TRENDS.md` · refresh: `python3 scripts/automation_comms_research.py --refresh --write`",
            "",
            "## Commands",
            "",
            "```bash",
            "./scripts/peer comms-improve-status",
            "./scripts/peer comms",
            "./scripts/peer comms-bus",
            "curl http://127.0.0.1:8765/api/comms",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_prompts(signals: CommsSignals) -> list[Path]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    plan = build_plan_prompt(signals)
    execute = build_execute_prompt(signals)
    combined = plan + "\n\n---\n\n" + execute
    PLAN_PATH.write_text(plan + "\n", encoding="utf-8")
    EXECUTE_PATH.write_text(execute + "\n", encoding="utf-8")
    COMBINED_PATH.write_text(combined + "\n", encoding="utf-8")
    return [PLAN_PATH, EXECUTE_PATH, COMBINED_PATH]


def write_horizon(signals: CommsSignals, *, cycle: int | None = None) -> list[Path]:
    text = build_horizon_markdown(signals, cycle=cycle)
    HORIZON_PATH.write_text(text + "\n", encoding="utf-8")
    written = [HORIZON_PATH]
    try:
        HORIZON_REPO_PATH.parent.mkdir(parents=True, exist_ok=True)
        HORIZON_REPO_PATH.write_text(text + "\n", encoding="utf-8")
        written.append(HORIZON_REPO_PATH)
    except OSError:
        pass
    return written


def _normalize_key(text: str) -> str:
    return auto._normalize_queue_key(text)


def enqueue_comms_work(
    signals: CommsSignals,
    *,
    log_fn: Callable[[str], None],
    cap: int = ENQUEUE_CAP,
) -> list[str]:
    inserted: list[str] = []
    work_path = auto.WORK_QUEUE_PATH
    ctx_path = auto.CONTEXT_PATH
    work_md = work_path.read_text(encoding="utf-8") if work_path.is_file() else ""
    context_md = ctx_path.read_text(encoding="utf-8") if ctx_path.is_file() else ""
    # Include [x] done lines — otherwise forever re-promotes landed wave-19 items (noop loop).
    # Also Creative backlog file — Soft demotes park there; Active re-insert freezes queue_fp.
    # Needle: OVERSEER_DEMOTE_KIT_THEATER_ACTIVE_2026_09_08
    try:
        import automation_improve as improve

        known = improve.queue_known_keys(work_md=work_md, context_md=context_md)
        already_shipped = improve._trend_already_shipped
    except Exception:  # noqa: BLE001
        known = {_normalize_key(x) for x in auto.remaining_work_items(work_md)}
        known |= {_normalize_key(x) for x in auto.remaining_work_items(context_md)}

        def already_shipped(raw: dict, keys: set[str]) -> bool:  # type: ignore[misc]
            return False

    try:
        cre_md = auto.load_creative_backlog_md()
        for line in cre_md.splitlines():
            item = auto._parse_work_item(line.strip()) or auto._parse_done_item_text(
                line.strip()
            )
            if item:
                known.add(_normalize_key(item))
    except Exception:  # noqa: BLE001
        pass

    for opp in signals.opportunities:
        if len(inserted) >= cap:
            break
        if not is_comms_kit_target(opp):
            continue
        marker = f"[comms-improve] {opp.title}"
        # Also skip when Active already demoted kit theater with [comms] prefix variants.
        if (
            _normalize_key(marker) in known
            or already_shipped({"title": marker, "detail": opp.detail}, known)
            or already_shipped(
                {"title": f"[comms-improve] [comms] {opp.title}", "detail": opp.detail},
                known,
            )
        ):
            log_fn(f"enqueue: skip duplicate {opp.title[:60]}")
            continue
        # Park under Creative — never Active (kit theater freezes Soft/Top10 queue_fp).
        line = f"- [ ] **{marker}** — {opp.detail}"
        before_w, before_c = work_md, context_md
        work_md = auto._insert_creative_open_lines(
            work_md if work_md.endswith("\n") else work_md + "\n",
            [line],
            annotate=auto._annotate_kit_theater_demote,
        )
        context_md = auto._insert_creative_open_lines(
            context_md if context_md.endswith("\n") else context_md + "\n",
            [line],
            annotate=auto._annotate_kit_theater_demote,
        )
        known.add(_normalize_key(marker))
        known.add(_normalize_key(f"[comms-improve] [comms] {opp.title}"))
        if work_md == before_w and context_md == before_c:
            log_fn(f"enqueue: skip duplicate (creative) {opp.title[:60]}")
            continue
        inserted.append(opp.title)
        log_fn(f"enqueue: creative {opp.title[:70]}")

    if inserted:
        work_path.write_text(work_md, encoding="utf-8")
        ctx_path.write_text(context_md, encoding="utf-8")
    return inserted


def wake_peer(*, log_fn: Callable[[str], None]) -> None:
    try:
        import automation_improve as improve

        improve.wake_peer(log_fn=log_fn)
    except Exception as exc:  # noqa: BLE001
        log_fn(f"wake peer: failed ({exc})")


def run_comms_cycle(
    *,
    quick: bool,
    research: bool,
    log_fn: Callable[[str], None],
    cycle: int | None = None,
    skip_self_test: bool = False,
) -> CommsSignals:
    verify: CommsVerifyResult | None = None
    if comms_self_test_required() and not skip_self_test:
        verify = verify_comms_kit(log_fn=log_fn)
        if not verify.ok:
            log_fn(f"RED LIGHT — skipping enqueue/wake ({verify.detail})")
    elif skip_self_test:
        log_fn("self-test: skipped (--no-self-test)")

    if research:
        try:
            report = comms_research.build_comms_report(refresh=True)
            comms_research.write_comms_trends_md(report)
            log_fn("research: refreshed COMMS_TRENDS")
        except Exception as exc:  # noqa: BLE001
            log_fn(f"research: failed ({exc})")

    signals = gather_signals(quick=quick, research=False)
    signals.verify = verify
    paths = write_prompts(signals)
    horizon_paths = write_horizon(signals, cycle=cycle)

    enqueued: list[str] = []
    if verify is None or verify.ok:
        enqueued = enqueue_comms_work(signals, log_fn=log_fn)
        if enqueued:
            wake_peer(log_fn=log_fn)
    else:
        log_fn("enqueue: blocked — comms self-test failed")

    top = [o for o in signals.opportunities if is_comms_kit_target(o)][:3]
    summary = "; ".join(o.title for o in top) or "(none)"
    log_fn(f"comms cycle — prompts {len(paths)}; enqueued {len(enqueued)}; top: {summary}")
    if horizon_paths:
        log_fn(f"horizon → {horizon_paths[0]}")
    return signals


def run_forever(
    *,
    quick: bool = True,
    research: bool = True,
    daemon: bool = False,
    skip_self_test: bool = False,
) -> int:
    log_fn = lambda msg: _log(msg, daemon=daemon)
    if not comms_improve_enabled():
        log_fn("comms improve disabled (comms_improve_enabled=false)")
        return 0

    log_fn(
        f"comms improve forever — research + GLink audit; "
        f"wake ≤{_continuous_wake_sec():.0f}s active / ≤{_wake_sec():.0f}s idle"
    )

    watcher = None
    try:
        import peer_transcript as transcript

        transcript.SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        transcript.SIGNAL_PATH.touch(exist_ok=True)
        watcher = transcript.PeerEventWatcher()
        if watcher.setup(repo_root=None):
            log_fn(f"event-driven: kqueue + {transcript.SIGNAL_PATH.name}")
    except Exception as exc:  # noqa: BLE001
        log_fn(f"event watch unavailable ({exc})")
        watcher = None

    cycle = 0
    state = _load_state()
    try:
        while True:
            cycle += 1
            cycle_started = time.monotonic()
            do_research = research and (cycle == 1 or cycle % _research_every_n_cycles() == 0)
            log_fn(
                f"cycle {cycle} — comms improve"
                + (" (research refresh)" if do_research else "")
            )
            try:
                run_comms_cycle(
                    quick=quick,
                    research=do_research,
                    log_fn=log_fn,
                    cycle=cycle,
                    skip_self_test=skip_self_test,
                )
            except Exception as exc:  # noqa: BLE001
                log_fn(f"cycle error (continuing): {exc}")

            state["last_cycle"] = cycle
            state["last_ts"] = time.time()
            _save_state(state)

            wait = _continuous_wake_sec()
            elapsed = time.monotonic() - cycle_started
            if elapsed < _min_cycle_sec():
                wait = max(wait, _min_cycle_sec() - elapsed)

            if watcher is not None and getattr(watcher, "available", False):
                event = watcher.wait(timeout=wait)
                log_fn(f"wake reason={event.reason}")
            else:
                time.sleep(wait)
                log_fn("wake reason=fallback")
    except KeyboardInterrupt:
        log_fn("comms improve stopped (KeyboardInterrupt)")
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
    script = SCRIPTS / "automation_comms_improve.py"
    args = [py, str(script), "--forever", "--daemon", "--write", "--research"]
    args_xml = "\n".join(f"    <string>{a}</string>" for a in args)
    home = Path.home()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{COMMS_IMPROVE_LABEL}</string>
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
    # OVERSEER_COMMS_LINUX_INSTALL_2026_09_06 — Linux has no launchctl; mirror improve.
    if comms_self_test_required():
        result = verify_comms_kit(log_fn=print)
        if not result.ok:
            print(f"install blocked: {result.detail}", file=sys.stderr)
            for fail in result.failures:
                print(f"  - {fail}", file=sys.stderr)
            return 1
        print(f"self-test: {result.detail}")
    if sys.platform != "darwin":
        import peer_self_heal as heal

        heal.ensure_canonical_module()
        print(heal.linux_install_daemon("comms-improve"))
        print(f"log: {LOG_PATH}")
        return 0
    uid = os.getuid()
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(plist_body())
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{COMMS_IMPROVE_LABEL}"], capture_output=True)
    proc = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print((proc.stderr or proc.stdout or "bootstrap failed").strip(), file=sys.stderr)
        return 1
    print(f"comms improve agent: {PLIST_PATH}")
    print(f"log: {LOG_PATH}")
    return 0


def cmd_uninstall() -> int:
    # OVERSEER_COMMS_LINUX_INSTALL_2026_09_06 — stop/disable systemd unit on Linux.
    if sys.platform != "darwin":
        import peer_self_heal as heal

        heal.ensure_canonical_module()
        print(heal.linux_uninstall_daemon("comms-improve"))
        return 0
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{COMMS_IMPROVE_LABEL}"], capture_output=True)
    if PLIST_PATH.is_file():
        PLIST_PATH.unlink()
    print("comms improve agent removed")
    return 0


def cmd_status() -> int:
    if sys.platform != "darwin":
        import peer_self_heal as heal

        running = heal._systemd_user_active("comms-improve-loop.service")
        label = "comms-improve-loop.service"
    else:
        uid = os.getuid()
        proc = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/{COMMS_IMPROVE_LABEL}"],
            capture_output=True,
            text=True,
        )
        running = proc.returncode == 0 and "state = running" in (proc.stdout or "")
        label = COMMS_IMPROVE_LABEL
    print(f"label: {label}")
    print(f"state: {'RUNNING' if running else 'STOPPED'}")
    print(f"enabled: {comms_improve_enabled()}")
    print(f"self_test_required: {comms_self_test_required()}")
    if comms_self_test_required():
        result = verify_comms_kit(log_fn=lambda msg: print(f"  {msg}"))
        print(f"verify: {'GREEN' if result.ok else 'RED'} — {result.detail}")
    print(f"log: {LOG_PATH}")
    print(f"horizon: {HORIZON_PATH}")
    print(f"repo board: {HORIZON_REPO_PATH}")
    print(f"factory improve: separate (automation_improve.py)")
    print()
    if HORIZON_PATH.is_file():
        print(HORIZON_PATH.read_text(encoding="utf-8"))
    elif LOG_PATH.is_file():
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
        print("recent log:")
        for line in lines[-8:]:
            print(f"  {line}")
    return 0 if running else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Comms improve forever — communication efficiency")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--research", action="store_true")
    parser.add_argument("--forever", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--verify", action="store_true", help="Run comms kit self-test (green/red light)")
    parser.add_argument("--no-self-test", action="store_true", help="Skip self-test gate for one cycle")
    args = parser.parse_args()

    if args.verify:
        result = verify_comms_kit(log_fn=print)
        print(result.detail)
        for fail in result.failures:
            print(f"  FAIL: {fail}")
        return 0 if result.ok else 1

    if args.install:
        return cmd_install()
    if args.uninstall:
        return cmd_uninstall()
    if args.status:
        return cmd_status()
    if args.forever:
        return run_forever(
            quick=True,
            research=args.research,
            daemon=args.daemon,
            skip_self_test=args.no_self_test,
        )

    signals = gather_signals(quick=True, research=args.research)
    if args.json:
        payload = {
            "north_star": NORTH_STAR,
            "signals": {
                "live": signals.live,
                "comms_status": signals.comms_status,
                "research": {
                    "gap_count": signals.research.get("gap_count"),
                    "partial_count": signals.research.get("partial_count"),
                },
                "opportunities": [asdict(o) for o in signals.opportunities],
            },
            "plan_prompt": build_plan_prompt(signals),
            "execute_prompt": build_execute_prompt(signals),
        }
        print(json.dumps(payload, indent=2))
        return 0

    if args.write:
        write_prompts(signals)
        write_horizon(signals)
        if args.research:
            comms_research.write_comms_trends_md(comms_research.build_comms_report(refresh=True))
        print(f"wrote {COMBINED_PATH}")
        return 0

    if args.plan:
        print(build_plan_prompt(signals))
        return 0
    if args.execute:
        print(build_execute_prompt(signals))
        return 0

    print(build_horizon_markdown(signals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
