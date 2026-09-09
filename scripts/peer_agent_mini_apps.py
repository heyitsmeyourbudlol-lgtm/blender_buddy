#!/usr/bin/env python3
"""Agent mini apps — self-built tools when repetition beats manual work.

Any niche may build a small single-purpose script under scripts/agent_tools/
when no existing peer command fits. Promote to ./scripts/peer via Command Builder
when the whole team repeats the loop.

Usage:
  python3 scripts/peer_agent_mini_apps.py --write
  python3 scripts/peer_agent_mini_apps.py --block --role verify_runner
  python3 scripts/peer_agent_mini_apps.py --scaffold --name diff_tail --purpose "Compare log tails"
  ./scripts/peer mini-apps
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
AGENT_TOOLS_DIR = SCRIPTS / "agent_tools"
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

MINI_APPS_MD = ROOT / "notes" / "AGENT_MINI_APPS.md"
REGISTRY_PATH = auto.CONFIG_DIR / "agent-mini-apps.json"

MINI_APP_MANDATE = """**Mini apps** — build tools for yourself when needed (every agent):

You are allowed — and expected — to build **small single-purpose applications** when:
- You repeat the same manual steps **2+ cycles**, and
- No `./scripts/peer` command or existing script already solves it, and
- A ≤200-line script with `--help` + one test is faster than another essay.

**Not** a license for kit bloat — build the **smallest** app that removes your repetition."""

WHEN_TO_BUILD: tuple[str, ...] = (
    "Same grep/diff/measure loop appeared twice in your debrief or GLink notes.",
    "Expected-vs-actual compare needs a niche-specific formatter (build on peer_output_compare).",
    "You need a read-only probe (status, tail, count) before you can pinpoint a fix.",
    "Command Builder backlog is full but **you** need the tool **this cycle** in your niche scope.",
)

WHEN_NOT_TO_BUILD: tuple[str, ...] = (
    "One-off task — inline shell is enough.",
    "A peer compound already exists — use `./scripts/peer commands-list --pivotal`.",
    "The app would edit queue, strategy, or cross-niche orchestration (wrong persona).",
    "No test and no `--help` — that is a scratch script, not a mini app.",
)

MINI_APP_RULES = """**Mini app rules (non-negotiable):**

| Rule | Detail |
|------|--------|
| **Location** | `scripts/agent_tools/<snake_name>.py` only |
| **Interface** | `argparse` + `--help`; stdin/stdout friendly |
| **Size** | Target ≤200 lines; split if larger |
| **Deps** | Stdlib + existing repo imports — no new pip deps without Safety |
| **Secrets** | Never embed tokens; env vars only |
| **Test** | `tests/test_agent_tools_<name>.py` or row in `tests/test_agent_tools.py` |
| **Register** | `./scripts/peer mini-apps --register --name X --purpose "..."` |
| **Promote** | Team repeats it → Command Builder adds `./scripts/peer` compound |"""

SCAFFOLD_TEMPLATE = '''#!/usr/bin/env python3
"""{purpose}

Agent mini app — built for niche self-serve. See notes/AGENT_MINI_APPS.md.

Usage:
  python3 scripts/agent_tools/{name}.py --help
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="{purpose}")
    parser.add_argument("--example", action="store_true", help="Example flag — replace me")
    args = parser.parse_args()
    if args.example:
        print("ok")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

NICHE_MINI_APPS: dict[str, tuple[str, ...]] = {
    "verify_runner": (
        "Mini app: parse first failing test line from unittest output.",
        "Mini app: flake classifier (env vs code) from two run captures.",
    ),
    "factory_engineer": (
        "Mini app: dispatch timeline from peer-loop-status + bus tail.",
    ),
    "adapt_specialist": (
        "Mini app: diff adapt audit JSON between two runs.",
    ),
    "queue_steward": (
        "Mini app: WORK_QUEUE ↔ self_improve_context line diff.",
    ),
    "communications_engineer": (
        "Mini app: byte count on vault summary hot path.",
    ),
    "compression_engineer": (
        "Mini app: RSS delta from two ram-status snapshots.",
    ),
    "command_builder": (
        "Promote proven agent_tools scripts to peer_commands compounds.",
    ),
    "orchestrator": (
        "Do not build mini apps in Plan — assign niche peer to build in their scope.",
    ),
}


def base_role_id(role_id: str) -> str:
    rid = str(role_id or "").strip()
    m = re.match(r"^(.+)_L\d+$", rid)
    return m.group(1) if m else rid


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", name.strip().lower()).strip("_")
    return slug or "tool"


def load_registry() -> list[dict]:
    if not REGISTRY_PATH.is_file():
        return []
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        return list(data.get("apps") or []) if isinstance(data, dict) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_registry(apps: list[dict]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated": time.time(), "apps": apps}
    REGISTRY_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def register_mini_app(
    name: str,
    *,
    purpose: str,
    role_id: str = "",
    path: str = "",
) -> Path:
    slug = _slug(name)
    rel = path or f"scripts/agent_tools/{slug}.py"
    entry = {
        "name": slug,
        "purpose": purpose.strip()[:300],
        "path": rel,
        "role_id": role_id,
        "registered": time.time(),
    }
    apps = [a for a in load_registry() if a.get("name") != slug]
    apps.append(entry)
    save_registry(apps)
    return REGISTRY_PATH


def scaffold_mini_app(name: str, *, purpose: str) -> Path:
    slug = _slug(name)
    AGENT_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    target = AGENT_TOOLS_DIR / f"{slug}.py"
    if target.is_file():
        raise FileExistsError(f"mini app already exists: {target}")
    text = SCAFFOLD_TEMPLATE.format(name=slug, purpose=purpose.strip() or slug.replace("_", " "))
    target.write_text(text, encoding="utf-8")
    target.chmod(target.stat().st_mode | 0o111)
    return target


def format_niche_mini_apps(role_id: str) -> str:
    base = base_role_id(role_id)
    tips = NICHE_MINI_APPS.get(base, ())
    if not tips:
        return "- If you repeat a probe/diff twice, scaffold under scripts/agent_tools/."
    return "\n".join(f"- {t}" for t in tips)


def format_registry_summary(*, max_entries: int = 8) -> str:
    apps = load_registry()
    if not apps:
        return "- _No registered mini apps yet — build when repetition hurts._"
    lines: list[str] = []
    for row in apps[-max_entries:]:
        lines.append(
            f"- `{row.get('path', '?')}` — {row.get('purpose', '')[:80]} "
            f"(by {row.get('role_id') or '?'})"
        )
    return "\n".join(lines)


def format_mini_apps_block(*, role_id: str | None = None) -> str:
    lines = [
        "## Mini apps (build tools for yourself when needed)",
        "",
        MINI_APP_MANDATE,
        "",
        MINI_APP_RULES,
        "",
        "**Build when:**",
        "",
    ]
    for i, w in enumerate(WHEN_TO_BUILD, 1):
        lines.append(f"{i}. {w}")
    lines.extend(["", "**Do not build when:**", ""])
    for i, w in enumerate(WHEN_NOT_TO_BUILD, 1):
        lines.append(f"{i}. {w}")
    lines.extend(["", "**Registered mini apps:**", format_registry_summary(), ""])
    if role_id:
        lines.extend(["**Your niche:**", format_niche_mini_apps(role_id), ""])
    lines.append(
        "_Scaffold:_ `./scripts/peer mini-apps --scaffold --name my_tool --purpose \"...\"` · "
        "_Run:_ `python3 scripts/agent_tools/my_tool.py --help`"
    )
    return "\n".join(lines).strip()


def write_mini_apps_md() -> Path:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines = [
        "# Agent mini apps — self-built tools",
        "",
        f"_Updated {now}_ · any agent · build when repetition beats manual work",
        "",
        MINI_APP_MANDATE,
        "",
        MINI_APP_RULES,
        "",
        "## Build when",
        "",
    ]
    for i, w in enumerate(WHEN_TO_BUILD, 1):
        lines.append(f"{i}. {w}")
    lines.extend(["", "## Do not build when", ""])
    for i, w in enumerate(WHEN_NOT_TO_BUILD, 1):
        lines.append(f"{i}. {w}")
    lines.extend(["", "## Workflow", "", "```bash"])
    lines.append("./scripts/peer mini-apps --scaffold --name diff_tail --purpose \"Compare log tails\"")
    lines.append("python3 scripts/agent_tools/diff_tail.py --help")
    lines.append(
        "./scripts/peer mini-apps --register --name diff_tail --role verify_runner --purpose \"...\""
    )
    lines.append("python3 -m unittest tests.test_agent_tools_diff_tail -q  # add test")
    lines.append("# Team repeats it → Command Builder → ./scripts/peer commands-sync")
    lines.extend(["```", "", "## Registered apps", "", format_registry_summary(max_entries=20), ""])
    lines.extend(["", "## Niche examples", ""])
    for rid in sorted(NICHE_MINI_APPS):
        title = rid.replace("_", " ").title()
        lines.append(f"### {title}")
        lines.append(format_niche_mini_apps(rid))
        lines.append("")
    MINI_APPS_MD.parent.mkdir(parents=True, exist_ok=True)
    MINI_APPS_MD.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return MINI_APPS_MD


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent mini apps — self-built tools")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--block", action="store_true")
    parser.add_argument("--role", default="")
    parser.add_argument("--scaffold", action="store_true")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--name", default="")
    parser.add_argument("--purpose", default="")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        for row in load_registry():
            print(f"{row.get('name')}: {row.get('path')} — {row.get('purpose', '')[:60]}")
        return 0

    if args.scaffold:
        if not args.name:
            print("mini-apps --scaffold requires --name", file=sys.stderr)
            return 1
        try:
            path = scaffold_mini_app(args.name, purpose=args.purpose or args.name)
        except FileExistsError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"scaffolded: {path}")
        return 0

    if args.register:
        if not args.name or not args.purpose:
            print("mini-apps --register requires --name and --purpose", file=sys.stderr)
            return 1
        path = register_mini_app(
            args.name,
            purpose=args.purpose,
            role_id=args.role,
        )
        print(f"registered: {path}")
        return 0

    if args.block:
        print(format_mini_apps_block(role_id=args.role or None))
        return 0

    path = write_mini_apps_md()
    print(f"mini-apps: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
