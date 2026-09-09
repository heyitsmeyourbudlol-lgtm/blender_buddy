#!/usr/bin/env python3
"""Automation overseer — cursor-agent reviews the kit and keeps you updated.

Mechanical self-heal fixes daemons, locks, drift. This module adds:
1. A **mechanical digest** (`notes/AUTOMATION_DIGEST.md`) every cycle — always written.
2. Optional **cursor-agent review** — deferred to event-based `./scripts/peer oversight` when stagnation detected.

Default focus: `automation_improve` (peer_loop, improve forever, verify, orchestrate, self-heal).

Usage:
  python3 scripts/peer_investigate.py --once
  python3 scripts/peer_investigate.py --digest-only   # update digest, no agent
  ./scripts/peer investigate
  ./scripts/peer digest
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import automation_config as cfg_mod  # noqa: E402
import peer_self_heal as self_heal  # noqa: E402
import peer_watch  # noqa: E402
import project_automation as auto  # noqa: E402

CONFIG_DIR = auto.CONFIG_DIR
STATE_PATH = CONFIG_DIR / "investigate-state.json"
REPORT_PATH = CONFIG_DIR / "investigate-report.md"
PROMPT_PATH = CONFIG_DIR / "investigate-prompt.md"
PEER_LOG = CONFIG_DIR / "peer-loop.log"
IMPROVE_LOG = CONFIG_DIR / "improve-loop.log"
HORIZON_MD = ROOT / "notes" / "IMPROVE_HORIZON.md"
_horizon_excerpt_cache: tuple[tuple[int, int], str] | None = None


def _horizon_excerpt() -> str:
    """First 35 lines of horizon board — cached by file witness to cut digest RSS."""
    global _horizon_excerpt_cache
    if not HORIZON_MD.is_file():
        return ""
    try:
        st = HORIZON_MD.stat()
        witness = (st.st_mtime_ns, st.st_size)
    except OSError:
        return ""
    if _horizon_excerpt_cache and _horizon_excerpt_cache[0] == witness:
        return _horizon_excerpt_cache[1]
    try:
        text = HORIZON_MD.read_text(encoding="utf-8")
        excerpt = "\n".join(text.splitlines()[:35])
    except OSError:
        excerpt = ""
    _horizon_excerpt_cache = (witness, excerpt)
    return excerpt


def investigate_enabled() -> bool:
    return bool(cfg_mod.CFG.get("investigate_enabled", True))


def investigate_focus() -> str:
    """automation_improve | product — default automation kit oversight."""
    raw = str(cfg_mod.CFG.get("investigate_focus") or "automation_improve").strip().lower()
    return raw if raw in ("automation_improve", "product") else "automation_improve"


def digest_path() -> Path:
    rel = str(cfg_mod.CFG.get("investigate_digest_path") or "notes/AUTOMATION_DIGEST.md")
    p = Path(rel)
    return p if p.is_absolute() else ROOT / p


def investigate_interval_sec() -> float:
    try:
        return max(300.0, float(cfg_mod.CFG.get("investigate_interval_sec") or 1800))
    except (TypeError, ValueError):
        return 1800.0


def dispatch_agent_enabled() -> bool:
    return bool(cfg_mod.CFG.get("investigate_dispatch_agent", True))


def autonomous_execution_enabled() -> bool:
    return bool(cfg_mod.CFG.get("autonomous_execution", True))


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _on_cooldown(state: dict[str, Any]) -> float:
    last = float(state.get("last_run_ts") or 0)
    elapsed = time.time() - last
    remaining = investigate_interval_sec() - elapsed
    return max(0.0, remaining)


def _tail_lines(path: Path, n: int = 24) -> list[str]:
    if not path.is_file():
        return []
    try:
        return auto.tail_text_lines(path, n)
    except OSError:
        return []


def _agent_running() -> bool:
    try:
        import peer_parallel_dispatch as ppd

        return bool(ppd.find_agent_procs())
    except Exception:  # noqa: BLE001
        return peer_watch.find_agent_proc() is not None


def _daemon_status() -> dict[str, bool]:
    snap = self_heal.daemon_status_snapshot()
    return {
        "peer_loop": snap["peer_loop"],
        "improve_loop": snap["improve_loop"],
        "dual_namespace": snap.get("dual_namespace", False),
    }


def _collect_kit_metrics(
    *,
    live: auto.LiveState | None = None,
    daemons: dict[str, bool] | None = None,
    bottlenecks: list[Any] | None = None,
) -> dict[str, Any]:
    """Improve / factory / rubric signals for the human digest."""
    metrics: dict[str, Any] = {}
    try:
        live_state = live or auto.measure_live_state(quick=True)
        metrics["tests_ok"] = live_state.tests_ok
        metrics["tests_detail"] = live_state.tests
        metrics["git_detail"] = live_state.git
    except Exception as exc:  # noqa: BLE001
        metrics["live_error"] = str(exc)[:120]
        live_state = None

    if daemons is None:
        daemons = _daemon_status()
    metrics["daemons"] = daemons

    try:
        import factory_progress as fp

        live_dict: dict[str, Any] | None = None
        if live_state is not None:
            queue = auto.open_work_items()
            live_dict = auto.live_snapshot(live_state, queue)
        prog = fp.compute_factory_progress(live=live_dict, daemons=daemons, bottlenecks=bottlenecks)
        metrics["factory_pct"] = prog.pct
        metrics["factory_label"] = prog.label
        metrics["factory_blockers"] = list(prog.blockers[:5])
    except Exception as exc:  # noqa: BLE001
        metrics["factory_error"] = str(exc)[:120]

    try:
        import automation_improve as improve
        import asi_rubric as asi

        signals = improve.gather_signals(
            quick=True,
            research=False,
            digest_only=True,
            live_state=live_state,
        )
        rubric = asi.compute_asi_rubric(signals)
        metrics["asi_pct"] = rubric.pct
        metrics["active_phase"] = rubric.current_phase_id
        metrics["phase_plan"] = (rubric.next_plan or "")[:300]
        metrics["audit_ok"] = signals.audit_ok
        metrics["queue_drift"] = len(signals.queue_drift)
    except Exception as exc:  # noqa: BLE001
        metrics["rubric_error"] = str(exc)[:120]

    excerpt = _horizon_excerpt()
    if excerpt:
        metrics["horizon_excerpt"] = excerpt

    return metrics


def collect_context() -> dict[str, Any]:
    """Live automation snapshot for digest + agent prompt."""
    live_state = auto.measure_live_state(quick=True)
    snap = peer_watch.collect_snapshot(live=live_state)
    daemons = _daemon_status()
    bottlenecks = self_heal.scan_bottlenecks(daemons=daemons)
    open_items = auto.open_work_items()
    state: dict[str, Any] = {}
    try:
        import peer_transcript as transcript

        state = transcript.load_state()
    except Exception:  # noqa: BLE001
        pass

    ram: dict[str, Any] = {}
    try:
        import dgx_ram_budget as budget

        stats = budget.mem_stats()
        ram = {
            "used_gb": round(budget.enforced_used_gb(stats=stats), 1),
            "soft_cap_gb": budget.ram_max_used_gb(),
            "hard_cap_gb": budget.ram_hard_max_used_gb(),
            "dispatch_allowed": budget.dispatch_allowed(stats=stats),
            "agent_cap": budget.ram_agent_cap(),
        }
    except Exception:  # noqa: BLE001
        pass

    kit = _collect_kit_metrics(live=live_state, daemons=daemons, bottlenecks=bottlenecks)
    rule_pending = 0
    try:
        import peer_rule_shutdown as rshut

        rule_pending = rshut.pending_count()
    except Exception:  # noqa: BLE001
        pass
    return {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "focus": investigate_focus(),
        "phase": snap.phase,
        "phase_detail": snap.phase_detail,
        "daemon_running": snap.daemon_running,
        "auth_ready": snap.auth_ready,
        "auth_detail": snap.auth_detail,
        "git_clean": snap.git_clean,
        "git_detail": snap.git_detail,
        "queue_count": snap.queue_count,
        "queue_source": snap.queue_source,
        "queue_preview": snap.queue_preview,
        "last_cycle_summary": snap.last_cycle_summary,
        "noop_backoff_sec": snap.noop_backoff_sec,
        "open_items": open_items.open_items[:10],
        "last_cycle": state.get("last_cycle") if isinstance(state.get("last_cycle"), dict) else {},
        "stall_reason": state.get("stall_reason"),
        "bottlenecks": [
            {
                "id": b.id,
                "severity": b.severity,
                "title": b.title,
                "evidence": b.evidence[:160],
            }
            for b in bottlenecks[:12]
        ],
        "rule_proposals_pending": rule_pending,
        "ram": ram,
        "kit": kit,
        "peer_log_tail": _tail_lines(PEER_LOG),
        "improve_log_tail": _tail_lines(IMPROVE_LOG, 16),
    }


def _health_emoji(ctx: dict[str, Any]) -> str:
    kit = ctx.get("kit") or {}
    daemons = kit.get("daemons") or {}
    last = ctx.get("last_cycle") or {}
    if not daemons.get("peer_loop") or not daemons.get("improve_loop"):
        return "🔴"
    if last.get("verify_ok") is False or ctx.get("phase") in ("STOPPED", "WAITING"):
        return "🟡"
    if last.get("noop") or int(ctx.get("queue_count") or 0) > 20:
        return "🟡"
    return "🟢"


def build_mechanical_digest(
    ctx: dict[str, Any],
    *,
    actions: list[str],
    dispatched: bool,
    agent_pending: bool = False,
) -> str:
    """Human-readable status update — written every cycle even without cursor-agent."""
    kit = ctx.get("kit") or {}
    daemons = kit.get("daemons") or {}
    last = ctx.get("last_cycle") or {}
    bn = ctx.get("bottlenecks") or []
    health = _health_emoji(ctx)

    lines = [
        "# Automation digest",
        "",
        f"_Updated {ctx.get('ts')}_ · focus=`{ctx.get('focus')}` · overseer {health}",
        "",
        "> Mechanical snapshot refreshes every investigate cycle. "
        "Cursor reviews are **event-based** via `./scripts/peer oversight` (stagnation, not timer).",
        "",
        "## At a glance",
        "",
        f"| Signal | Value |",
        f"|--------|-------|",
        f"| Peer loop | {'RUNNING' if daemons.get('peer_loop') else '**STOPPED**'} |",
        f"| Improve loop | {'RUNNING' if daemons.get('improve_loop') else '**STOPPED**'} |",
        f"| Phase | **{ctx.get('phase')}** — {ctx.get('phase_detail', '')[:80]} |",
        f"| Queue | {ctx.get('queue_count')} open ({ctx.get('queue_source')}) |",
        f"| Last cycle | {ctx.get('last_cycle_summary') or '(none)'} |",
        f"| Tests | {kit.get('tests_detail', '?')} |",
        f"| Git | {kit.get('git_detail', ctx.get('git_detail', '?'))} |",
        f"| Harness rubric | {kit.get('asi_pct', '?')}% · phase `{kit.get('active_phase', '?')}` |",
        f"| Factory readiness | {kit.get('factory_pct', '?')}% |",
        f"| Bottlenecks | {len(bn)} open |",
        f"| Rule proposals | {ctx.get('rule_proposals_pending', 0)} pending |",
        f"| Agent review | {'dispatched' if dispatched else ('pending' if agent_pending else 'digest only')} |",
        "",
    ]

    if kit.get("phase_plan"):
        lines.extend(["## Active improve phase", "", kit["phase_plan"], ""])

    if bn:
        lines.extend(["## Bottlenecks (self-heal)", ""])
        for b in bn[:8]:
            lines.append(f"- **[{b['severity']}]** {b['title']} — {b['evidence'][:100]}")
        lines.append("")

    try:
        import peer_playbook as playbook

        pb_hits = playbook.match_many(
            [b.get("title", "") for b in bn]
            + [str((ctx.get("last_cycle") or {}).get("failure_type") or "")]
            + [str((ctx.get("last_cycle") or {}).get("summary") or "")]
        )
        if pb_hits:
            lines.extend(["## Instant fixes (playbook)", "", playbook.format_instant_fixes(pb_hits), ""])
    except Exception:  # noqa: BLE001
        pass

    if ctx.get("queue_preview"):
        lines.extend(["## Queue (top)", ""])
        for item in ctx.get("queue_preview") or []:
            lines.append(f"- {item}")
        lines.append("")

    if actions:
        lines.extend(["## This cycle (mechanical)", ""])
        for a in actions:
            lines.append(f"- {a}")
        lines.append("")

    lines.extend(
        [
            "## Agent notes",
            "",
            "_Cursor-agent appends here when dispatched. Leave prior entries; add dated bullet._",
            "",
        ]
    )

    prev = digest_path()
    if prev.is_file():
        try:
            old = prev.read_text(encoding="utf-8")
            if "## Agent notes" in old:
                section = old.split("## Agent notes", 1)[1]
                # Keep prior agent bullets (skip boilerplate lines)
                kept: list[str] = []
                for ln in section.splitlines():
                    s = ln.strip()
                    if s.startswith("_") or s.startswith(">"):
                        continue
                    if s.startswith("- ") and "Cursor-agent appends" not in s:
                        kept.append(ln)
                if kept:
                    lines.extend(kept[-12:])
                    lines.append("")
        except OSError:
            pass

    lines.extend(
        [
            "## Commands",
            "",
            "```bash",
            "./scripts/peer digest              # refresh this file",
            "./scripts/peer investigate-force   # agent review now",
            "./scripts/peer improve-status      # horizon board",
            "./scripts/peer self-heal-status    # bottleneck registry",
            "./scripts/peer watch               # live peer dashboard",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def build_investigation_prompt(ctx: dict[str, Any]) -> str:
    """Cursor-agent prompt — automation kit review + human update."""
    bn_lines = [
        f"- [{b['severity']}] {b['title']}: {b['evidence']}"
        for b in ctx.get("bottlenecks") or []
    ] or ["- (none — still validate loops are advancing)"]

    queue_lines = [f"- {x[:100]}" for x in ctx.get("open_items") or []] or ["- (empty)"]
    peer_tail = "\n".join(f"  {ln}" for ln in ctx.get("peer_log_tail") or []) or "  (no log)"
    improve_tail = "\n".join(f"  {ln}" for ln in ctx.get("improve_log_tail") or []) or "  (no log)"
    kit = ctx.get("kit") or {}
    daemons = kit.get("daemons") or {}
    last = ctx.get("last_cycle") or {}
    digest = digest_path()

    if investigate_focus() == "product":
        mission = (
            "Pick **one product win**: external proof on a registry repo, native verify, irreversible artifact."
        )
    else:
        mission = (
            "Your mission is a **near-perfect automation setup**: peer_loop + improve forever + self-heal + "
            "verify gates + orchestrate + worktrees running smoothly with minimal noop and no dual-brain stall."
        )

    pb_block = ""
    try:
        import peer_playbook as playbook

        pb_block = playbook.format_prompt_block(
            playbook.match_many(
                [b.get("title", "") for b in ctx.get("bottlenecks") or []]
                + [str(last.get("failure_type") or ""), str(last.get("summary") or "")]
            )
        )
    except Exception:  # noqa: BLE001
        pass

    return f"""# Automation overseer (scheduled review)

You are the **Automation Overseer** for {auto.PROJECT_NAME}. {mission}

The human reads **`{digest.relative_to(ROOT) if digest.is_relative_to(ROOT) else digest}`** — keep them updated.

## Snapshot ({ctx.get('ts')})
- Peer daemon: {'RUNNING' if daemons.get('peer_loop') else 'STOPPED'}
- Improve daemon: {'RUNNING' if daemons.get('improve_loop') else 'STOPPED'}
- Phase: **{ctx.get('phase')}** — {ctx.get('phase_detail')}
- Queue: {ctx.get('queue_count')} open · last_cycle noop={last.get('noop')} verify_ok={last.get('verify_ok')}
- Harness rubric: {kit.get('asi_pct', '?')}% · active phase `{kit.get('active_phase', '?')}`
- Factory readiness: {kit.get('factory_pct', '?')}%
- Audit ok: {kit.get('audit_ok', '?')} · drift warnings: {kit.get('queue_drift', '?')}

## Bottlenecks
{chr(10).join(bn_lines)}

## Queue
{chr(10).join(queue_lines)}

## Recent peer-loop log
{peer_tail}

## Recent improve-loop log
{improve_tail}

{pb_block}
## Required deliverables
1. **Read** `notes/AUTOMATION.md`, `notes/PEER_ORCHESTRATION.md`, `AGENTS.md`, `notes/AGENT_ERROR_PLAYBOOK.md`, and the current digest at `{digest}`.
2. **Survey** the full kit: daemons, noop loops, verify failures, queue drift, RAM caps, adapt audit.
3. **Fix one** highest-impact automation gap with a minimal verified diff (scripts/tests only unless external proof is explicitly queued).
4. **Update the digest** — under `## Agent notes` in `{digest}`, append a dated bullet block:
   - **Status:** green / yellow / red (one word)
   - **What you checked:** 2–3 sentences
   - **What you fixed:** file(s) + outcome, or "nothing — blocked because …"
   - **Needs human:** only if truly blocked (auth, secret, product decision)
5. Run verify: `python3 -m unittest discover -s tests -q` (or project test_command).

Do **not** enqueue strategy essays or comms theater. Executable automation kit work only.
"""


def write_digest(ctx: dict[str, Any], *, actions: list[str], dispatched: bool, agent_pending: bool = False) -> Path:
    text = build_mechanical_digest(ctx, actions=actions, dispatched=dispatched, agent_pending=agent_pending)
    path = digest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    REPORT_PATH.write_text(text, encoding="utf-8")
    try:
        import automation_adapt as adapt

        adapt.sync_git_fingerprint(ROOT)
    except Exception:  # noqa: BLE001
        pass
    return path


def _oversight_handles_cursor_agents() -> bool:
    try:
        import peer_oversight as oversight
        import peer_oversight_events as events

        return (
            oversight.oversight_enabled()
            and oversight.dispatch_agent_enabled()
            and events.agent_dispatch_mode() == "event"
        )
    except Exception:  # noqa: BLE001
        return False


def run_investigation_once(
    *,
    log_fn: Callable[[str], None] | None = None,
    dispatch_agent: bool | None = None,
    force: bool = False,
    digest_only: bool = False,
) -> dict[str, Any]:
    """One overseer tick: heal → digest → optional cursor-agent review."""
    log = log_fn or (lambda _m: None)
    if not investigate_enabled():
        log("investigate: disabled in config")
        return {"skipped": "disabled"}

    state = _load_state()
    remaining = _on_cooldown(state)
    if not force and not digest_only and remaining > 0:
        log(f"investigate: cooldown {remaining:.0f}s left")
        return {"skipped": "cooldown", "remaining_sec": remaining}

    actions: list[str] = []
    ctx = collect_context()

    if autonomous_execution_enabled() and not digest_only:
        try:
            daemons = _daemon_status()
            if not daemons.get("peer_loop"):
                import peer_self_heal as sh

                msg = sh._heal_peer_daemon({})
                actions.append(f"auto: {msg}")
                log(f"investigate: {msg}")
            if not daemons.get("improve_loop"):
                import peer_self_heal as sh

                msg = sh._heal_improve_daemon({})
                actions.append(f"auto: {msg}")
                log(f"investigate: {msg}")
        except Exception as exc:  # noqa: BLE001
            log(f"investigate: daemon auto-install failed ({exc})")

    if not digest_only:
        try:
            report = self_heal.run_cycle(write=True, log_fn=log)
            if report.actions:
                actions.extend(f"self-heal: {a}" for a in report.actions)
                log(f"investigate: self-heal {len(report.actions)} action(s)")
        except Exception as exc:  # noqa: BLE001
            log(f"investigate: self-heal failed ({exc})")

        last = ctx.get("last_cycle") or {}
        if last.get("noop") or int(ctx.get("queue_count") or 0) > 15:
            try:
                removed, compact_actions = auto.compact_executable_queue(write=True)
                if removed:
                    msg = f"compact: {removed} line(s)"
                    actions.append(msg)
                    for act in compact_actions:
                        actions.append(f"compact: {act}")
                    log(f"investigate: {msg}")
            except Exception as exc:  # noqa: BLE001
                log(f"investigate: compact failed ({exc})")

    ctx = collect_context()
    digest_file = write_digest(ctx, actions=actions, dispatched=False)
    log(f"investigate: digest → {digest_file.relative_to(ROOT) if digest_file.is_relative_to(ROOT) else digest_file}")

    if digest_only:
        state["last_digest_ts"] = time.time()
        _save_state(state)
        return {"digest": str(digest_file), "actions": actions}

    prompt = build_investigation_prompt(ctx)
    PROMPT_PATH.write_text(prompt, encoding="utf-8")

    should_dispatch = dispatch_agent if dispatch_agent is not None else dispatch_agent_enabled()
    deferred_to_oversight = False
    if should_dispatch and _oversight_handles_cursor_agents():
        log("investigate: cursor-agent deferred to oversight (event/stagnation)")
        actions.append("agent deferred: oversight event mode")
        should_dispatch = False
        deferred_to_oversight = True
    dispatched = False
    if should_dispatch:
        if _agent_running():
            log("investigate: cursor-agent already running — skip dispatch")
            actions.append("skip dispatch: agent busy")
            write_digest(ctx, actions=actions, dispatched=False, agent_pending=True)
        else:
            try:
                import dgx_ram_budget as budget

                if not budget.dispatch_allowed():
                    log("investigate: RAM soft cap — skip agent dispatch")
                    actions.append("skip dispatch: RAM cap")
                    should_dispatch = False
                    write_digest(ctx, actions=actions, dispatched=False)
            except Exception:  # noqa: BLE001
                pass

            if should_dispatch:
                try:
                    import peer_terminal as terminal

                    ready, detail = terminal.desktop_auth_ready()
                    if not ready:
                        log(f"investigate: auth not ready — {detail}")
                        actions.append(f"skip dispatch: {detail}")
                        write_digest(ctx, actions=actions, dispatched=False)
                    else:
                        rc, _auth_fail = terminal.run_cursor_agent(
                            prompt,
                            log_fn=log,
                            sync=False,
                            paid_api=False,
                        )
                        dispatched = rc == 0
                        actions.append(
                            "dispatched cursor-agent (background)" if dispatched else f"dispatch rc={rc}"
                        )
                        write_digest(ctx, actions=actions, dispatched=dispatched, agent_pending=dispatched)
                except Exception as exc:  # noqa: BLE001
                    log(f"investigate: dispatch failed ({exc})")
                    actions.append(f"dispatch failed: {exc}")
                    write_digest(ctx, actions=actions, dispatched=False)
    else:
        if deferred_to_oversight:
            log(
                "investigate: digest only — factory+oversight own cursor-agent "
                "(oversight.agent_dispatch_mode=event; parallel_agent_dispatch stays on)"
            )
        else:
            log("investigate: agent dispatch disabled — digest only")

    state["last_run_ts"] = time.time()
    state["last_phase"] = ctx.get("phase")
    state["last_dispatched"] = dispatched
    state["last_actions"] = actions[-8:]
    state["last_focus"] = investigate_focus()
    _save_state(state)
    return {
        "dispatched": dispatched,
        "actions": actions,
        "phase": ctx.get("phase"),
        "digest": str(digest_file),
        "focus": investigate_focus(),
    }


def run_forever(*, daemon: bool = False) -> int:
    log_fn = print if not daemon else lambda msg: _log_daemon(msg)
    log_fn(
        f"investigate forever — focus={investigate_focus()} · every {investigate_interval_sec():.0f}s "
        f"(dispatch={dispatch_agent_enabled()})"
    )
    try:
        while True:
            run_investigation_once(log_fn=log_fn)
            time.sleep(investigate_interval_sec())
    except KeyboardInterrupt:
        log_fn("investigate forever stopped")
        return 0


def _log_daemon(msg: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp}  {msg}"
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = CONFIG_DIR / "investigate-loop.log"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Automation overseer — digest + cursor-agent review")
    parser.add_argument("--once", action="store_true", help="Single overseer tick")
    parser.add_argument("--forever", action="store_true", help="Loop every investigate_interval_sec")
    parser.add_argument("--force", action="store_true", help="Ignore cooldown")
    parser.add_argument("--digest-only", action="store_true", help="Refresh digest only; no agent")
    parser.add_argument("--no-dispatch", action="store_true", help="Digest + heal; no cursor-agent")
    parser.add_argument("--daemon", action="store_true", help="Log to investigate-loop.log")
    parser.add_argument("--status", action="store_true", help="Show last overseer state")
    args = parser.parse_args()

    if args.status:
        state = _load_state()
        remaining = _on_cooldown(state)
        print(f"enabled: {investigate_enabled()}")
        print(f"focus: {investigate_focus()}")
        print(f"interval: {investigate_interval_sec():.0f}s")
        print(f"cooldown remaining: {remaining:.0f}s")
        print(f"last run: {state.get('last_run_ts', '(never)')}")
        print(f"last phase: {state.get('last_phase', '?')}")
        print(f"digest: {digest_path()}")
        print(f"report: {REPORT_PATH}")
        return 0

    if args.forever:
        return run_forever(daemon=args.daemon)

    result = run_investigation_once(
        force=args.force,
        digest_only=args.digest_only,
        dispatch_agent=False if args.no_dispatch else None,
        log_fn=_log_daemon if args.daemon else print,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
