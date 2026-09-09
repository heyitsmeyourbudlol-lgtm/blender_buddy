#!/usr/bin/env python3
"""Suggest the next ram-park step from session context and send it to Cursor chat.

Peer loop (`--peer`, default): clever/non-obvious reclaim first (CREATIVE_RECLAIM),
then obvious queue, then idea mining. Stops only when `## Loop: exhausted` and
metrics are green — not when `## Status: complete`.

Usage:
  python3 scripts/cursor_self_improve.py              # paste + Enter, or stop if done
  python3 scripts/cursor_self_improve.py --peer       # parallel peer prompt (default if 2+ items)
  python3 scripts/cursor_self_improve.py --dry-run
  python3 scripts/cursor_self_improve.py --quick      # cache tests/RSS until git changes
  python3 scripts/cursor_self_improve.py --clipboard-only
  python3 scripts/peer_orchestrate.py --self-check    # automation health audit
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import textwrap
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

DEFAULT_APP = "Cursor"


def _with_harness_memory(body: str) -> str:
    """Prefix last_cycle retrospect + optional trend hint when present."""
    import peer_transcript as pt

    memory = pt.format_harness_memory()
    if not memory:
        return body
    return f"{memory}\n\n{body}"


def build_suggestion(context_md: str, live: auto.LiveState, queue: auto.QueueState) -> str:
    rules = auto.extract_rules(context_md)
    live_block = " · ".join([live.git_detail, live.tests_detail, live.footprint_detail])

    if queue.open_items:
        next_items = queue.open_items[:3]
    else:
        next_items = auto.blocker_items(context_md, live)[:3]

    task_lines = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(next_items))
    rules_short = "; ".join(rules[:3]) if rules else "consent + compress + Cursor protected"

    body = textwrap.dedent(
        f"""\
        Continue {auto.PROJECT_NAME} self-improve cycle. Live checks: {live_block}

        Constraints: {rules_short}.

        Do next:
        {task_lines}

        Implement (don't just plan). Run tests after changes. Keep cold import under budget when rss_budget_mb is set in automation.config.json.
        When done, check off items in scripts/self_improve_context.md and notes/WORK_QUEUE.md or set ## Status: complete.
        """
    ).strip()
    return _with_harness_memory(body)


def build_peer_suggestion(*, force: bool = False, quick: bool = False, loop: bool = False) -> str:
    import peer_orchestrate as po

    body = po.format_prompt(po.build_plan(force=force, quick=quick, include_creative=force, loop=loop))
    if body.startswith("Nothing to orchestrate"):
        return body
    return _with_harness_memory(body)


def send_to_cursor(
    text: str,
    *,
    app_name: str,
    press_enter: bool,
    fresh_chat: bool = False,
    use_clipboard: bool = False,
) -> tuple[bool, str]:
    """Inject into Cursor chat; clipboard paste only when opted in."""
    import peer_cursor

    return peer_cursor.send_to_cursor(
        text,
        app_name=app_name,
        press_enter=press_enter,
        fresh_chat=fresh_chat,
        use_clipboard=use_clipboard,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Suggest next step and send to Cursor chat")
    parser.add_argument("--dry-run", action="store_true", help="Print suggestion only")
    parser.add_argument("--no-enter", action="store_true", help="Paste but do not press Return")
    parser.add_argument("--force", action="store_true", help="Send even when nothing left to improve")
    parser.add_argument("--peer", action="store_true", help="Use peer orchestrator (parallel agent tasks)")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Peer loop: after blocking queue, pull creative backlog + CREATIVE_RECLAIM experiments",
    )
    parser.add_argument(
        "--no-loop",
        action="store_true",
        help="Disable peer loop (legacy stop on ## Status: complete)",
    )
    parser.add_argument("--linear", action="store_true", help="Force single-thread prompt (no peers)")
    parser.add_argument("--quick", action="store_true", help="Reuse cached tests/RSS until git changes")
    parser.add_argument(
        "--clipboard-only",
        action="store_true",
        help="Opt-in: copy prompt to clipboard; do not activate Cursor",
    )
    parser.add_argument(
        "--cursor-ui",
        action="store_true",
        help="Opt-in: activate Cursor and inject via AX (steals focus)",
    )
    parser.add_argument(
        "--forever",
        action="store_true",
        help="Forever loop: dispatch peer prompt → wait for commit → ram install → repeat",
    )
    parser.add_argument("--app", default=DEFAULT_APP, help=f"App name (default: {DEFAULT_APP})")
    parser.add_argument("--update-context", action="store_true", help="Print JSON snapshot of live signals")
    args = parser.parse_args()

    if args.forever:
        import peer_loop

        paid_api = bool(args.paid_api or os.environ.get("PEER_LOOP_PAID_API") == "1")
        if paid_api:
            mode = "terminal"
            clipboard = False
        elif args.cursor_ui:
            mode = "direct-ui"
            clipboard = False
        elif args.clipboard_only or os.environ.get("CURSOR_MINIMIZED") == "1":
            mode = "clipboard"
            clipboard = True
        else:
            mode = "background"
            clipboard = False
        return peer_loop.run_forever(
            quick=args.quick,
            mode=mode,
            clipboard_only=clipboard,
            press_enter=not args.no_enter,
            daemon=False,
            from_transcript=True,
            done_timeout_sec=peer_loop.DEFAULT_DONE_TIMEOUT_SEC,
            paid_api=paid_api,
        )

    context_md = auto.load_context_md()
    work_md = auto.load_work_queue_md()
    queue = auto.open_work_items(context_md, work_md)
    live = auto.measure_live_state(quick=args.quick)
    use_peer = args.peer or (not args.linear and len(queue.open_items) >= 2)
    loop = args.loop or (use_peer and not args.no_loop)
    reason = auto.stop_reason(context_md, live, queue, loop=loop)

    if args.update_context:
        import json

        snap = auto.live_snapshot(live, queue)
        snap["success_metrics_ok"] = auto.success_metrics_ok(live)
        snap["should_stop"] = reason
        snap["loop_exhausted"] = auto.loop_marked_exhausted(context_md)
        snap["has_loop_work"] = auto.has_loop_work(context_md, work_md, live=live)
        snap["queue_drift"] = auto.sync_queue_drift(context_md, work_md)
        print(json.dumps(snap, indent=2))
        return 0

    if reason and not args.force and not loop:
        print(f"Nothing left to improve — stopping. ({reason})")
        print(f"  {live.git_detail} · {live.tests_detail} · {live.footprint_detail}")
        if queue.open_items:
            print(f"  (queue has {len(queue.open_items)} open item(s) — use --force to send anyway)")
        if auto.has_loop_work(context_md, work_md, live=live):
            print("  (peer loop still has work — use: cursor_self_improve.py --peer)")
        return 0

    if reason and not args.force and loop:
        print(f"Peer loop done — {reason}")
        print(f"  {live.git_detail} · {live.tests_detail} · {live.footprint_detail}")
        return 0

    if reason and not args.force and args.peer and not loop:
        blockers = auto.blocker_items(context_md, live, loop=False)
        if not queue.open_items and not blockers:
            print(f"Status complete — no peer loop. ({reason})")
            print("  Use --peer without --no-loop to continue clever pipeline.")
            return 0

    if use_peer:
        suggestion = build_peer_suggestion(force=args.force, quick=args.quick, loop=loop)
        if suggestion.startswith("Nothing to orchestrate"):
            print(suggestion)
            return 0
    else:
        suggestion = build_suggestion(context_md, live, queue)

    if args.dry_run:
        if reason and args.force:
            print(f"(would stop: {reason}; --force overrides)\n")
        mode = "peer" if use_peer else "linear"
        print(f"(mode: {mode})\n")
        print(suggestion)
        return 0

    if args.clipboard_only:
        if not auto.copy_to_clipboard(suggestion):
            print("failed to copy to clipboard", file=sys.stderr)
            return 1
        print("copied to clipboard (Cursor not activated)")
        print("\n--- prompt ---\n")
        print(suggestion)
        return 0

    if not args.cursor_ui:
        import peer_terminal

        path = peer_terminal.write_prompt_file(suggestion)
        print(f"prompt saved → {path} (background mode — no clipboard, no Cursor UI)")
        print("\n--- prompt ---\n")
        print(suggestion)
        return 0

    ok, msg = send_to_cursor(
        suggestion,
        app_name=args.app,
        press_enter=not args.no_enter,
        use_clipboard=False,
        cursor_ui=True,
    )
    if not ok:
        print(f"Cursor automation failed: {msg}", file=sys.stderr)
        print("\nSuggestion:\n")
        print(suggestion)
        print(
            "\nGrant Accessibility to Terminal/Cursor in "
            "System Settings → Privacy & Security → Accessibility.",
            file=sys.stderr,
        )
        return 1

    print(msg)
    print("\n--- sent ---\n")
    print(suggestion)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
