#!/usr/bin/env python3
"""Product drive — keep the factory shipping external proof, not just healing the kit.

Ensures registry product targets stay on the queue, prioritizes them for dispatch,
and launches factory_sprint / factory_fanout when agent capacity allows.

Usage:
  python3 scripts/product_drive.py --once
  ./scripts/peer product
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import automation_config as cfg_mod  # noqa: E402
import project_automation as auto  # noqa: E402

REGISTRY_PATH = ROOT / "repos" / "registry.json"
STATE_PATH = auto.CONFIG_DIR / "product-drive-state.json"

_PRODUCT_MARKERS = (
    "[product]",
    "external proof",
    "newdrop",
    "caas",
    " cpt",
    "cpt ",
    "registry status",
    "adapt + native verify",
    "irreversible artifact",
    "revenue",
    "ship",
    "/users/togi/caas",
    "/users/togi/cpt",
    "/users/togi/ram",
)

_KIT_THEATER = (
    "comms-improve",
    "mamba-scale",
    "knowledge]",
    "48 niches",
    "agent roster",
    "gibberlink",
    "ggwave",
)


def _cfg() -> dict[str, Any]:
    raw = cfg_mod.CFG.get("product_drive")
    return raw if isinstance(raw, dict) else {}


def product_drive_enabled() -> bool:
    if "enabled" in _cfg():
        return bool(_cfg().get("enabled"))
    return bool(cfg_mod.CFG.get("product_drive_enabled", True))


def product_interval_sec() -> float:
    try:
        iv = float(_cfg().get("interval_sec") or cfg_mod.CFG.get("product_drive_interval_sec") or 180)
    except (TypeError, ValueError):
        iv = 180.0
    try:
        import factory_grid as grid

        if grid.grid_enabled():
            iv = min(iv, grid.sprint_interval_sec() * 6)
    except Exception:  # noqa: BLE001
        pass
    return max(30.0, iv)


def ensure_queue_enabled() -> bool:
    return bool(_cfg().get("ensure_queue", cfg_mod.CFG.get("product_ensure_queue", True)))


def product_noop_backoff_sec() -> float:
    try:
        return max(5.0, float(_cfg().get("noop_backoff_sec") or cfg_mod.CFG.get("product_noop_backoff_sec") or 15))
    except (TypeError, ValueError):
        return 15.0


def is_product_item(text: str) -> bool:
    low = text.lower()
    if any(m in low for m in _KIT_THEATER) and "external proof" not in low:
        return False
    return any(m in low for m in _PRODUCT_MARKERS)


def product_priority(text: str) -> int:
    """Lower = dispatch first."""
    low = text.lower()
    if "[product]" in low or "external proof sprint" in low:
        return 0
    if "external proof" in low:
        return 1
    if any(n in low for n in ("newdrop", "caas", "revenue")):
        return 2
    if any(n in low for n in (" cpt", "cpt ", "ram")):
        return 3
    if "adapt + native verify" in low or "irreversible artifact" in low:
        return 4
    if "dgx-speed" in low and "external" in low:
        return 5
    if any(m in low for m in _KIT_THEATER):
        return 80
    return 20


def prioritize_product_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        key = auto._normalize_queue_key(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return sorted(unique, key=lambda t: (product_priority(t), t.lower()))


def has_product_work(items: list[str] | None = None) -> bool:
    if items is None:
        items = auto.open_work_items().open_items
    return any(is_product_item(i) for i in items)


def _load_registry() -> list[dict[str, Any]]:
    if not REGISTRY_PATH.is_file():
        return []
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    repos = data.get("repos") if isinstance(data, dict) else []
    return [r for r in repos if isinstance(r, dict)]


def registry_product_targets(*, limit: int = 3) -> list[dict[str, Any]]:
    """Ship/revenue/unaudited registry repos — exclude Automation hub."""
    status_ok = {"unaudited", "needs-kit-install", "active-loop-running", "git", "active"}
    priority_rank = {"ship": 0, "revenue": 1, "active": 2}
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for repo in _load_registry():
        name = str(repo.get("name") or "").strip()
        if not name or name.lower() == "automation hub":
            continue
        status = str(repo.get("status") or "").lower()
        if status not in status_ok:
            continue
        pri = str(repo.get("priority") or "").lower()
        rank = priority_rank.get(pri, 5)
        status_rank = 0 if status in ("needs-kit-install", "unaudited") else 1
        candidates.append((rank, status_rank, repo))
    candidates.sort(key=lambda x: (x[0], x[1], str(x[2].get("name") or "").lower()))
    return [c[2] for c in candidates[:limit]]


def ensure_product_queue(*, write: bool = True) -> list[str]:
    """Seed [product] external-proof lines when queue lacks product work."""
    if not ensure_queue_enabled():
        return []
    work_path = auto.WORK_QUEUE_PATH
    ctx_path = auto.CONTEXT_PATH
    work_md = work_path.read_text(encoding="utf-8") if work_path.is_file() else ""
    if has_product_work(auto.open_work_items(work_md=work_md).open_items):
        return []

    inserted: list[str] = []
    known = {
        auto._normalize_queue_key(x)
        for x in auto.open_work_items(work_md=work_md).open_items
    }
    for repo in registry_product_targets():
        name = str(repo.get("name") or "").strip()
        status = str(repo.get("status") or "?")
        body = (
            f"**[product] External proof: {name}** — adapt + native verify → "
            f"irreversible artifact (registry {status})"
        )
        if auto._normalize_queue_key(body) in known:
            continue
        bullet = f"- [ ] {body}"
        if "## Active" in work_md:
            work_md = work_md.replace("## Active\n", f"## Active\n{bullet}\n", 1)
        else:
            work_md = work_md.rstrip() + f"\n\n## Active\n{bullet}\n"
        known.add(auto._normalize_queue_key(body))
        inserted.append(name)

    if inserted and write:
        work_path.parent.mkdir(parents=True, exist_ok=True)
        work_path.write_text(work_md if work_md.endswith("\n") else work_md + "\n")
        if ctx_path.is_file():
            ctx_md = ctx_path.read_text(encoding="utf-8")
            ctx_known = {auto._normalize_queue_key(x) for x in auto.remaining_work_items(ctx_md)}
            ctx_bullets: list[str] = []
            for name in inserted:
                for repo in registry_product_targets(limit=6):
                    if str(repo.get("name") or "").strip() != name:
                        continue
                    status = str(repo.get("status") or "?")
                    body = (
                        f"**[product] External proof: {name}** — adapt + native verify → "
                        f"irreversible artifact (registry {status})"
                    )
                    if auto._normalize_queue_key(body) not in ctx_known:
                        ctx_bullets.append(f"- [ ] {body}")
                        ctx_known.add(auto._normalize_queue_key(body))
            if ctx_bullets:
                for bullet in ctx_bullets:
                    ctx_md = auto.insert_remaining_work_bullet(ctx_md, bullet)
                ctx_path.write_text(ctx_md if ctx_md.endswith("\n") else ctx_md + "\n")
    return inserted


def run_product_cycle(*, log_fn: Callable[[str], None] | None = None) -> dict[str, Any]:
    """One product tick: ensure queue → external sprint → registry fanout."""
    log = log_fn or (lambda _m: None)
    if not product_drive_enabled():
        return {"skipped": "disabled"}

    actions: list[str] = []
    seeded = ensure_product_queue(write=True)
    if seeded:
        msg = f"seeded product queue: {', '.join(seeded)}"
        actions.append(msg)
        log(f"product_drive: {msg}")

    forge_launched = 0
    try:
        import peer_product_forge as forge

        if forge.forge_active():
            report = forge.run_forge_cycle(log_fn=log, dispatch=True)
            forge_launched = int(report.get("launched") or 0)
            if forge_launched:
                actions.append(f"product_forge launched {forge_launched} agent(s)")
            elif report.get("skipped"):
                log(f"product_drive: forge ({report.get('skipped')})")
    except Exception as exc:  # noqa: BLE001
        log(f"product_drive: forge failed ({exc})")

    launched = 0
    try:
        import factory_sprint as sprint

        report = sprint.run_sprint_cycle(log_fn=log)
        launched = int(report.get("launched") or 0)
        if launched:
            actions.append(f"factory_sprint launched {launched} agent(s)")
            log(f"product_drive: sprint +{launched}")
        elif report.get("reason"):
            log(f"product_drive: sprint idle ({report.get('reason')})")
    except Exception as exc:  # noqa: BLE001
        log(f"product_drive: sprint failed ({exc})")

    fanout_ok = 0
    try:
        import factory_fanout as fanout

        force = bool(_cfg().get("force_fanout") or cfg_mod.CFG.get("product_drive_fanout"))
        if fanout.fanout_enabled() or force:
            result = fanout.run_fanout(quick=True, limit=4, log_fn=log)
            fanout_ok = int(result.get("ok") or 0)
            if result.get("candidates"):
                actions.append(f"factory_fanout ok={fanout_ok}/{result.get('candidates')}")
    except Exception as exc:  # noqa: BLE001
        log(f"product_drive: fanout failed ({exc})")

    state = _load_state()
    state["last_run_ts"] = time.time()
    state["last_launched"] = launched
    state["last_fanout_ok"] = fanout_ok
    state["last_actions"] = actions[-6:]
    _save_state(state)
    return {"launched": launched, "fanout_ok": fanout_ok, "actions": actions, "seeded": seeded}


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


def cooldown_remaining() -> float:
    last = float(_load_state().get("last_run_ts") or 0)
    return max(0.0, product_interval_sec() - (time.time() - last))


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Keep factory shipping product work")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        print(f"enabled: {product_drive_enabled()}")
        print(f"interval: {product_interval_sec():.0f}s")
        print(f"cooldown: {cooldown_remaining():.0f}s")
        print(f"product_work: {has_product_work()}")
        return 0
    result = run_product_cycle(log_fn=print)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
