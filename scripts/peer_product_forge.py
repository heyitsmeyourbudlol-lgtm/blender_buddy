#!/usr/bin/env python3
"""Product forge — autonomous strong-application mode (vibe-scale, product cwd).

When activated, the factory dispatches cursor-agents **in the product repo**, not the
Automation hub. Greenfield: bootstrap dir + kit + product WORK_QUEUE. Existing repo:
seed forge slices + native verify.

Usage:
  python3 scripts/peer_product_forge.py --start "Newdrop MVP" --profile caas --path ~/Projects/myapp
  python3 scripts/peer_product_forge.py --once
  python3 scripts/peer_product_forge.py --status
  python3 scripts/peer_product_forge.py --stop
  ./scripts/peer product-forge --start "…"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import automation_config as cfg_mod  # noqa: E402
import factory_fanout as fanout  # noqa: E402
import project_automation as auto  # noqa: E402

STATE_PATH = auto.CONFIG_DIR / "product-forge-state.json"
LOG_PATH = auto.CONFIG_DIR / "product-forge.log"

FORGE_SLICE_MARKERS = ("[forge]", "[product-forge]")


def _cfg() -> dict[str, Any]:
    raw = cfg_mod.CFG.get("product_forge")
    return raw if isinstance(raw, dict) else {}


def forge_enabled() -> bool:
    if "enabled" in _cfg():
        return bool(_cfg().get("enabled"))
    return True


def default_profile() -> str:
    return str(_cfg().get("default_profile") or "caas")


def greenfield_parent() -> Path:
    raw = str(_cfg().get("greenfield_parent") or "~/Projects").strip()
    return Path(raw).expanduser().resolve()


def max_forge_agents() -> int:
    try:
        return max(1, min(8, int(_cfg().get("max_agents") or 4)))
    except (TypeError, ValueError):
        return 4


def suppress_hub_while_active() -> bool:
    return bool(_cfg().get("suppress_hub_enqueue_while_active", True))


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def forge_active() -> bool:
    state = _load_state()
    return bool(state.get("active")) and bool(state.get("target_path"))


def active_target() -> Path | None:
    state = _load_state()
    raw = str(state.get("target_path") or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p.resolve() if p.is_dir() else None


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:48] or "product"


def resolve_target_path(*, brief: str, path: str | None, name: str | None) -> Path:
    if path:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = greenfield_parent() / p
        return p.resolve()
    slug = _slug(name or brief)
    return (greenfield_parent() / slug).resolve()


def bootstrap_repo(target: Path, *, profile: str, brief: str) -> list[str]:
    """Create repo dir, git init, install kit, seed queues."""
    import automation_adapt as adapt

    actions: list[str] = []
    target.mkdir(parents=True, exist_ok=True)
    if not (target / ".git").is_dir():
        subprocess.run(["git", "init"], cwd=str(target), capture_output=True, check=False)
        actions.append("git init")
    installed = adapt.install_kit(target, profile=profile)
    actions.extend(installed[:12])
    adapt.run_heal(write=True, target=target, quick=True, force=False)
    actions.append("adapt heal")
    seed_target_queue(target, brief=brief, profile=profile)
    actions.append("seed product queue")
    return actions


def seed_target_queue(target: Path, *, brief: str, profile: str) -> list[str]:
    """Write executable forge slices on the **product** repo queue."""
    wq = target / "notes" / "WORK_QUEUE.md"
    ctx = target / "scripts" / "self_improve_context.md"
    slices = [
        (
            f"**[forge] Scaffold {brief}** — profile `{profile}`; "
            "`npm run build` or native verify green; minimal kit diff"
        ),
        (
            f"**[forge] Core UX** — one screen, one job (elegant statue); "
            "match repo conventions; ship user-visible path"
        ),
        (
            "**[forge] API + data** — one backend route + persistence or stub; "
            "tests for happy path"
        ),
        (
            "**[forge] Auth or billing spike** — only if profile=caas; "
            "fail-closed; no secrets in repo"
        ),
        (
            "**[forge] Deploy smoke** — production or preview URL loads; "
            "record URL in AGENTS.md or README"
        ),
    ]
    if profile != "caas":
        slices = [s for s in slices if "caas" not in s.lower()]

    lines = [
        "# WORK_QUEUE",
        "",
        f"_Product forge — {brief}_",
        "",
        "## Active",
        "",
    ]
    for s in slices:
        lines.append(f"- [ ] {s}")
    lines.append("")
    wq.parent.mkdir(parents=True, exist_ok=True)
    wq.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ctx.parent.mkdir(parents=True, exist_ok=True)
    ctx.write_text(
        "# self_improve_context\n\n## Remaining work (priority order)\n\n"
        + "\n".join(f"- [ ] {s}" for s in slices)
        + "\n",
        encoding="utf-8",
    )
    return slices


def build_forge_prompt(*, brief: str, target: Path, profile: str) -> str:
    wq = target / "notes" / "WORK_QUEUE.md"
    queue_preview = ""
    if wq.is_file():
        queue_preview = wq.read_text(encoding="utf-8", errors="replace")[:2500]

    profile_path = ROOT / "profiles" / f"{profile}.json"
    constraints = ""
    if profile_path.is_file():
        try:
            data = json.loads(profile_path.read_text(encoding="utf-8"))
            pcs = data.get("product_constraints") or []
            if isinstance(pcs, list):
                constraints = "\n".join(f"- {c}" for c in pcs[:6])
        except (OSError, json.JSONDecodeError):
            pass

    return f"""# Product forge — build a strong application

You are in **vibe-ship mode**: one product repo, minimal meta, maximal user-visible progress.

**Mission:** {brief}
**Repo (cwd):** `{target}`
**Profile:** `{profile}`

## Rules
1. Work **only** in this repo — not the Automation hub.
2. Pick the **top open [forge] item** from the product queue below; land it this session.
3. Match stack conventions; run **native verify** (npm test/build, pytest, etc.) before done.
4. Minimal diff per slice — ship vertical slices like a weekend vibe session, not a kit essay.
5. Update product docs when you change durable truth (README, AGENTS.md).
{f"## Product constraints{chr(10)}{constraints}" if constraints else ""}

## Product queue (read `notes/WORK_QUEUE.md`)
```
{queue_preview or "(seed queue — start with scaffold slice)"}
```

Implement the highest-priority [forge] slice now. Stop with verify output + files touched.
"""


def _hub_enqueue_forge(brief: str, target: Path) -> None:
    marker = f"[product-forge] Active — {brief} @ {target}"
    detail = "Autonomous product mode — agents dispatch in product cwd; ./scripts/peer product-forge --status"
    try:
        work_md = auto.WORK_QUEUE_PATH.read_text(encoding="utf-8") if auto.WORK_QUEUE_PATH.is_file() else ""
        if marker in work_md:
            return
        line = f"- [ ] **{marker}** — {detail}"
        if "## Active" in work_md:
            work_md = work_md.replace("## Active\n", f"## Active\n{line}\n", 1)
        else:
            work_md = work_md.rstrip() + f"\n\n## Active\n{line}\n"
        auto.WORK_QUEUE_PATH.write_text(work_md, encoding="utf-8")
    except OSError:
        pass


def start_forge(
    *,
    brief: str,
    path: str | None = None,
    name: str | None = None,
    profile: str | None = None,
    bootstrap: bool = True,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    log = log_fn or (lambda _m: None)
    if not forge_enabled():
        return {"error": "disabled"}

    prof = (profile or default_profile()).strip()
    target = resolve_target_path(brief=brief, path=path, name=name)
    actions: list[str] = []

    if not target.is_dir() or bootstrap:
        log(f"product-forge: bootstrap {target}")
        actions.extend(bootstrap_repo(target, profile=prof, brief=brief))
    else:
        wq = target / "notes" / "WORK_QUEUE.md"
        text = wq.read_text(encoding="utf-8", errors="replace") if wq.is_file() else ""
        if not any(m in text for m in FORGE_SLICE_MARKERS):
            seed_target_queue(target, brief=brief, profile=prof)
            actions.append("seed forge queue (replaced hub-polluted product queue)")
            log("product-forge: seeded [forge] slices on product repo")
        elif not wq.is_file():
            seed_target_queue(target, brief=brief, profile=prof)
            actions.append("seed queue")

    state = {
        "active": True,
        "brief": brief,
        "target_path": str(target),
        "profile": prof,
        "started_at": time.time(),
        "started_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "last_dispatch": None,
        "dispatches": 0,
    }
    _save_state(state)
    _hub_enqueue_forge(brief, target)
    log(f"product-forge: ACTIVE → {target}")

    try:
        import automation_improve as improve

        improve.wake_peer(log_fn=log)
    except Exception:  # noqa: BLE001
        pass

    return {"active": True, "target": str(target), "profile": prof, "actions": actions}


def stop_forge(*, log_fn: Callable[[str], None] | None = None) -> dict[str, Any]:
    log = log_fn or (lambda _m: None)
    state = _load_state()
    state["active"] = False
    state["stopped_at"] = time.time()
    _save_state(state)
    scrubbed = scrub_orphan_forge_agents(log_fn=log)
    log("product-forge: stopped")
    return {"active": False, "scrubbed": scrubbed}


def scrub_orphan_forge_agents(
    *,
    log_fn: Callable[[str], None] | None = None,
    target: Path | None = None,
) -> int:
    """SIGKILL cursor-agents under product cwd when forge is inactive.

    OVERSEER_SCRUB_ORPHAN_FORGE_2026_09_04 — stop_forge left CaaS agents
    running (ppid=1); quiet-wait then deferred hub verify forever.
    """
    log = log_fn or (lambda _m: None)
    if forge_active():
        return 0
    root = target
    if root is None:
        state = _load_state()
        raw = str(state.get("target_path") or "").strip()
        if raw:
            root = Path(raw).expanduser()
        else:
            # Prefer CAAS_ROOT / ~/CaaS — never hardcode absolute user-home paths.
            # OVERSEER_CAAS_PATH_2026_09_04
            import os as _os

            env_root = (_os.environ.get("CAAS_ROOT") or "").strip()
            candidates: list[Path] = []
            if env_root:
                candidates.append(Path(env_root).expanduser())
            candidates.append(Path.home() / "CaaS")
            for cand in candidates:
                if cand.is_dir():
                    root = cand
                    break
    if root is None or not root.is_dir():
        return 0
    try:
        import peer_parallel_dispatch as ppd
    except Exception:  # noqa: BLE001
        return 0
    root = root.resolve()
    killed = 0
    for proc in list(ppd.find_agent_procs(fresh=True)):
        if proc.pid <= 0:
            continue
        cwd = ppd._proc_cwd(proc.pid)
        if cwd is None:
            continue
        try:
            cwd.resolve().relative_to(root)
        except ValueError:
            continue
        try:
            os.kill(proc.pid, signal.SIGKILL)
            killed += 1
        except OSError:
            pass
    if killed:
        log(f"product-forge: scrubbed {killed} orphan agent(s) under {root.name}")
    return killed


def dispatch_forge_agents(*, log_fn: Callable[[str], None] | None = None) -> dict[str, Any]:
    log = log_fn or (lambda _m: None)
    if not forge_active():
        scrub_orphan_forge_agents(log_fn=log)
        return {"skipped": "inactive"}

    state = _load_state()
    target = active_target()
    if target is None:
        return {"error": "target missing"}

    brief = str(state.get("brief") or "Product")
    profile = str(state.get("profile") or default_profile())
    prompt = build_forge_prompt(brief=brief, target=target, profile=profile)

    try:
        import dgx_ram_budget as budget

        if not budget.dispatch_allowed():
            log("product-forge: RAM cap — skip dispatch")
            return {"skipped": "ram_cap"}
    except Exception:  # noqa: BLE001
        pass

    try:
        import peer_parallel_dispatch as ppd

        # Cap by agents already in the product cwd — not global hub swarm.
        running = int(ppd.count_agents_under(target))
        cap = min(max_forge_agents(), auto.max_parallel_peers())
        remaining = max(0, cap - running)
        if remaining <= 0:
            log(f"product-forge: agent cap ({running}/{cap})")
            return {"skipped": "agent_cap", "running": running}
    except Exception:  # noqa: BLE001
        cap = max_forge_agents()
        remaining = cap
        running = 0

    import peer_terminal as terminal

    ready, detail = terminal.desktop_auth_ready()
    if not ready:
        log(f"product-forge: auth not ready — {detail}")
        return {"skipped": "auth", "detail": detail}

    launched = 0
    # vibe mode: at most 2 per tick, never past remaining headroom
    slots = min(2, remaining)
    paid = os.environ.get("PEER_LOOP_PAID_API") == "1"
    for i in range(slots):
        rc, auth_failed = terminal.run_cursor_agent(
            prompt,
            log_fn=log,
            paid_api=paid,
            cwd=target,
            sync=False,
        )
        launched += 1
        state["last_dispatch"] = time.time()
        state["dispatches"] = int(state.get("dispatches") or 0) + 1
        _save_state(state)
        log(f"product-forge: agent {i + 1} rc={rc} cwd={target.name}")
        if auth_failed or rc != 0:
            break

    return {"launched": launched, "target": str(target), "running_before": running}


def run_forge_cycle(
    *,
    log_fn: Callable[[str], None] | None = None,
    dispatch: bool = True,
) -> dict[str, Any]:
    log = log_fn or (lambda _m: None)
    if not forge_active():
        return {"skipped": "inactive"}
    report: dict[str, Any] = {"active": True, "target": str(active_target() or "")}
    if dispatch:
        report.update(dispatch_forge_agents(log_fn=log))
    return report


def cmd_status() -> int:
    state = _load_state()
    print(f"enabled: {forge_enabled()}")
    print(f"active: {state.get('active')}")
    print(f"brief: {state.get('brief')}")
    print(f"target: {state.get('target_path')}")
    print(f"profile: {state.get('profile')}")
    print(f"dispatches: {state.get('dispatches')}")
    print(f"suppress_hub: {suppress_hub_while_active()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Product forge — autonomous app mode")
    parser.add_argument("--start", metavar="BRIEF", help="Activate forge for this product mission")
    parser.add_argument("--path", help="Repo path (default: ~/Projects/<slug>)")
    parser.add_argument("--name", help="Slug for greenfield dir")
    parser.add_argument("--profile", default=None, help="Task profile (caas, node, python, …)")
    parser.add_argument("--no-bootstrap", action="store_true", help="Use existing repo only")
    parser.add_argument("--once", action="store_true", help="One dispatch cycle if active")
    parser.add_argument("--stop", action="store_true", help="Deactivate forge")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--no-dispatch", action="store_true")
    args = parser.parse_args()

    def log(msg: str) -> None:
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n"
        try:
            with LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass
        print(msg)

    if args.status:
        return cmd_status()
    if args.stop:
        stop_forge(log_fn=log)
        return 0
    if args.start:
        report = start_forge(
            brief=args.start,
            path=args.path,
            name=args.name,
            profile=args.profile,
            bootstrap=not args.no_bootstrap,
            log_fn=log,
        )
        if not args.no_dispatch:
            report.update(dispatch_forge_agents(log_fn=log))
        print(json.dumps(report, indent=2))
        return 0
    if args.once:
        print(json.dumps(run_forge_cycle(log_fn=log, dispatch=not args.no_dispatch), indent=2))
        return 0
    cmd_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
