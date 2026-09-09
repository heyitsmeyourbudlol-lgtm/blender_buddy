#!/usr/bin/env python3
"""Forever CLEAN fanout — never let compression research agents die idle.

Needle: OVERSEER_COMPRESSION_KEEP_ALIVE_2026_09_05

- Expands roles toward max_parallel_peers
- Free desktop cursor-agent waves only ($0 — never paid API)
- Respawns when count drops below floor
- Mandate: max unique-param efficiency (S≈100), min RAM @ NVFP4, no data prune
- Hands off to compression_auto_train when research gates go green

Guard (wave-55): when train_unlocked=false / RECIPE TRAIN-LOCKED / T4 NO-GO,
fail-closed skip T4 shard fanout + keep-alive waves that invent Shard-* theater
(2026-09-06 03:00Z flood · bus hand n=96). Needle: OVERSEER_KEEP_ALIVE_TRAIN_LOCK_GUARD_2026_09_05

RSS (wave-keep): lazy-import heavy dispatch modules; RAM-gate before
build_assignments; gc after waves. Needle: COMPRESSION_KEEP_ALIVE_LEAN_IDLE_2026_09_06

RSS (wave-unload): one_wave left ~424MB sticky anon heap (peer_* /
automation_improve / project_automation stay in sys.modules). After each
wave + idle tick: drop wave-only modules, clear dispatch caches, malloc_trim.
Needle: COMPRESSION_KEEP_ALIVE_WAVE_UNLOAD_2026_09_07

RSS (skip-boot-wave): on service restart, skip one_wave when cursor-agent
count already ≥ boot_floor (min(env,16) when train unlocked) — avoids
cap=24 storm + sticky heap. Needle: COMPRESSION_KEEP_ALIVE_SKIP_BOOT_WAVE_2026_09_07

Staff RAM heal: when agents < floor and RAM blocks dispatch, one rebalance
(ballast purge) before skip — stops Staff miss theater under full swap without
Shard/T4 invent. Needle: OVERSEER_KEEP_ALIVE_STAFF_RAM_HEAL_2026_09_07
"""

from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
os.chdir(ROOT)

os.environ.setdefault("PEER_AGENT_LOCAL", "1")
# Snapshot caller entitlement BEFORE force — receipt must fail-closed if paid was
# requested (CLI/service Environment=PEER_LOOP_PAID_API=1). Import then heals to $0.
_PEER_LOOP_PAID_API_PREFLIGHT = os.environ.get("PEER_LOOP_PAID_API")
# Free path only — never opt into API-key billing.
os.environ.pop("PEER_LOOP_PAID_API", None)
os.environ["PEER_LOOP_PAID_API"] = "0"

NEEDLE = "OVERSEER_COMPRESSION_KEEP_ALIVE_2026_09_05"
GUARD_NEEDLE = "OVERSEER_KEEP_ALIVE_TRAIN_LOCK_GUARD_2026_09_05"
UNLOCK_NEEDLE = "OVERSEER_COMPRESSION_TRAIN_UNLOCK_2026_09_05"
LEAN_NEEDLE = "COMPRESSION_KEEP_ALIVE_LEAN_IDLE_2026_09_06"
UNLOAD_NEEDLE = "COMPRESSION_KEEP_ALIVE_WAVE_UNLOAD_2026_09_07"
MANDATE = (
    "NORTH STAR (mandatory): 1B logical → ~10M unique @ NVFP4 (S≈100). "
    "Minimize unique params U and resident RAM despite high logical N — "
    "share experts, SVD-TieStack, LoRA deltas, BitDistill; hot dtype NVFP4; "
    "1-bit cold only; NO data/example/token prune. "
    "Do everything in your power for the most efficient model. "
    "Advance recipe TRAIN-LOCK (T4 done); when gates green, compression_auto_train starts the model. "
    "If results stall, compression_result_watch heals — stay on desktop login $0 only."
)

# Modules pulled only for fanout / gates — safe to drop between ticks (re-imported on demand).
_WAVE_UNLOAD_PREFIXES: tuple[str, ...] = (
    "peer_parallel_dispatch",
    "peer_roles",
    "peer_terminal",
    "peer_worktree",
    "peer_agent_",
    "peer_transcript",
    "peer_memory_span",
    "peer_team_context",
    "peer_persona",
    "peer_critical",
    "peer_hallucination",
    "peer_idea",
    "peer_output",
    "peer_precision",
    "peer_playbook",
    "peer_self_",
    "peer_land_hold",
    "peer_last_cycle",
    "peer_flaw",
    "peer_dual",
    "peer_project_learning",
    "peer_remote",
    "peer_work_assign",
    "automation_improve",
    "automation_adapt",
    "automation_config",
    "dgx_ram_",
    "dgx_shm_",
    "project_automation",
    "compression_auto_train",
    "factory_progress",
    "factory_grid",
)


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}", flush=True)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def train_unlocked(*, root: Path | None = None) -> bool:
    """Fail-closed: True only with explicit unlock evidence.

    Without train_unlock.json train_unlocked=true **or** the auto-train recipe
    banner (``**{UNLOCK_NEEDLE}** · auto-train · train_unlocked=true``), returns
    False (TRAIN-LOCKED / T4 NO-GO / train_unlocked=false).

    Needle: OVERSEER_KEEP_ALIVE_UNLOCK_BANNER_ONLY_2026_09_08 — mere mentions of
    the unlock needle / historical ``train_unlocked=true`` in steward prose must
    **not** flip this gate (recipe_lock_steward false-positive fix).
    """
    base = root or ROOT
    unlock_path = base / "notes" / "compression_artifacts" / "train_unlock.json"
    if unlock_path.is_file():
        try:
            data = json.loads(unlock_path.read_text(encoding="utf-8"))
            if data.get("train_unlocked") is True:
                return True
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    recipe = _read(base / "notes" / "COMPRESSION_TRAIN_RECIPE.md")
    # Require auto-train stamp banner from compression_auto_train.stamp_recipe_unlocked
    # — not a prose citation of the needle + historical true stamp.
    banner = f"**{UNLOCK_NEEDLE}**"
    if banner in recipe and "auto-train" in recipe and "train_unlocked=true" in recipe.replace(" ", "").lower():
        return True
    ready = _read(base / "notes" / "COMPRESSION_TRAIN_READY.md")
    if banner in ready and "train_unlocked=true" in ready.replace(" ", "").lower():
        return True
    return False


def enqueue_t4_shard_fanout(
    n: int = 48,
    *,
    root: Path | None = None,
    ts: str | None = None,
) -> list[str]:
    """Enqueue ``[compression-train] Shard-NN T4 microbench`` lines (WQ + context).

    Fail-closed: when ``train_unlocked`` is false / TRAIN-LOCKED / T4 NO-GO,
    return [] and write nothing (prevents 03:00Z-style backlog flood).
    """
    base = root or ROOT
    if not train_unlocked(root=base):
        log(
            f"{GUARD_NEEDLE} enqueue_t4_shard_fanout: SKIP n={n} "
            "(train_unlocked=false / TRAIN-LOCKED / T4 NO-GO)"
        )
        return []
    stamp = ts or time.strftime("%Y-%m-%d %H:%M")
    lines: list[str] = []
    for i in range(1, max(0, int(n)) + 1):
        lines.append(
            f"- [ ] [compression-train] Shard-{i:02d} T4 microbench "
            f"— pack/U sweep ({stamp}Z) {NEEDLE}"
        )
    if not lines:
        return []
    written: list[str] = []
    for rel in ("notes/WORK_QUEUE.md", "scripts/self_improve_context.md"):
        path = base / rel
        text = path.read_text(encoding="utf-8") if path.is_file() else "# queue\n"
        changed = False
        for line in lines:
            key = line.split("—")[0].strip()
            if key and key in text:
                continue
            if not text.endswith("\n"):
                text += "\n"
            text += line + "\n"
            changed = True
            if line not in written:
                written.append(line)
        if changed:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    return written


def cursor_count() -> int:
    """Staff floor SoT: peer ``cursor-agent -p`` only — not worker daemons.

    Bare ``grep cursor-agent`` counted worker-server / worker-start and inflated
    the floor toward 8 while ``effective_hub_running`` stayed ~0–1, so
    ``one_wave`` launched cap−1 niches and OOM-killed (rc=-9).
    Needle: OVERSEER_KEEP_ALIVE_STAFF_P_COUNT_2026_09_07
    """
    try:
        import peer_parallel_dispatch as pp

        return len(pp.find_agent_procs(fresh=True))
    except Exception:  # noqa: BLE001
        out = subprocess.getoutput(
            "ps -u \"$USER\" -o cmd= | grep '[c]ursor-agent' | grep -c -- ' -p' || true"
        )
        try:
            return int(out.strip() or "0")
        except ValueError:
            return 0


# Cooldown for Staff RAM heal (seconds). Module-level so forever loop + one_wave share it.
_STAFF_RAM_HEAL_COOLDOWN_SEC = 120.0
_last_staff_ram_heal_mono: float = 0.0


def maybe_heal_ram_for_staff_floor(*, floor: int | None = None) -> dict[str, object]:
    """If below Staff floor and RAM blocks dispatch, purge ballast once (cooldown).

    Needle: OVERSEER_KEEP_ALIVE_STAFF_RAM_HEAL_2026_09_07
    Does not spawn agents / Shard / T4 — only ``dgx_ram_fill.rebalance_ram``.
    """
    global _last_staff_ram_heal_mono
    out: dict[str, object] = {
        "attempted": False,
        "healed": False,
        "skipped": "ok",
        "agents": 0,
        "floor": 0,
        "dispatch_allowed_before": True,
        "dispatch_allowed_after": True,
    }
    try:
        import dgx_ram_budget as budget
        import project_automation as auto

        agents = cursor_count()
        eff_floor = int(floor) if floor is not None else int(
            os.environ.get("FANOUT_RESPAWN_BELOW", "48")
        )
        if train_unlocked():
            eff_floor = min(eff_floor, 16)
        try:
            eff_floor = min(eff_floor, int(auto.max_parallel_agent_procs()))
        except Exception:  # noqa: BLE001
            pass
        out["agents"] = agents
        out["floor"] = eff_floor
        before = bool(budget.dispatch_allowed())
        out["dispatch_allowed_before"] = before
        out["dispatch_allowed_after"] = before
        if agents >= eff_floor:
            out["skipped"] = "at_floor"
            return out
        if before:
            out["skipped"] = "dispatch_ok"
            return out
        now = time.monotonic()
        if (now - _last_staff_ram_heal_mono) < _STAFF_RAM_HEAL_COOLDOWN_SEC:
            out["skipped"] = "cooldown"
            return out
        _last_staff_ram_heal_mono = now
        out["attempted"] = True
        out["skipped"] = None
        try:
            import dgx_ram_fill as fill

            fill.rebalance_ram(log_fn=lambda m: log(f"staff-ram-heal: {m}"))
        except Exception as exc:  # noqa: BLE001
            log(f"staff-ram-heal rebalance soft-fail: {exc}")
            out["skipped"] = f"rebalance_err:{type(exc).__name__}"
            return out
        after = bool(budget.dispatch_allowed())
        out["dispatch_allowed_after"] = after
        out["healed"] = after
        log(
            f"OVERSEER_KEEP_ALIVE_STAFF_RAM_HEAL_2026_09_07 "
            f"agents={agents} floor={eff_floor} dispatch_after={after}"
        )
        return out
    except Exception as exc:  # noqa: BLE001
        out["skipped"] = f"soft:{type(exc).__name__}"
        return out


def _fuel_title_key(line: str) -> str:
    """Title after checkbox — so ``[x]`` acceptance still satisfies fuel stock.

    Needle: OVERSEER_COMPRESSION_FUEL_CHECKBOX_BLIND_2026_09_07
    Prior bug: matching ``- [ ] …`` meant closing to ``[x]`` re-opened theater.
    """
    head = line.split("—", 1)[0].strip()
    if head.startswith("- ["):
        # "- [ ] title" / "- [x] title" → "title"
        close = head.find("]")
        if close >= 0:
            return head[close + 1 :].strip()
    return head


def _fuel_line_present(text: str, line: str) -> bool:
    """True if open or closed queue row already covers this fuel title."""
    title = _fuel_title_key(line)
    if not title:
        return False
    if title in text:
        return True
    # Exact open key (legacy)
    key = line.split("—", 1)[0].strip()
    return bool(key) and key in text


def _has_queue_structure(text: str) -> bool:
    """True when md has Active / Remaining / Phase — not headerless fuel orphans."""
    for line in text.splitlines():
        s = line.strip()
        if (
            s.startswith("## Active")
            or s.startswith("## Remaining work")
            or s.startswith("## Phase")
        ):
            return True
    return False


def _insert_fuel_under_active(text: str, line: str) -> str:
    """Insert one fuel bullet under ``## Active`` (create heading if missing)."""
    bullet = line if line.startswith("- ") else f"- {line}"
    lines = text.splitlines()
    active_idx: int | None = None
    for i, raw in enumerate(lines):
        if raw.strip().startswith("## Active"):
            active_idx = i
            break
    if active_idx is None:
        # Structured twin may only have Remaining — prepend Active for fuel.
        body = text.lstrip("\n")
        return f"## Active\n{bullet}\n\n{body}".rstrip() + "\n"
    out: list[str] = []
    inserted = False
    i = 0
    while i < len(lines):
        out.append(lines[i])
        if i == active_idx and not inserted:
            i += 1
            if i < len(lines) and lines[i].strip() == "":
                out.append(lines[i])
                i += 1
            out.append(bullet)
            inserted = True
            continue
        i += 1
    if not inserted:
        return text.rstrip() + f"\n\n## Active\n{bullet}\n"
    return "\n".join(out).rstrip() + "\n"


def ensure_queue_fuel(*, root: Path | None = None) -> list[str]:
    """Keep both queue files stocked so the loop never idles empty.

    Fail-closed under TRAIN lock: do not add compression-train T4 fuel that
    drives Shard-* invent theater while train_unlocked=false.

    Closed ``[x]`` rows with the same title count as stocked (do not reopen).

    OVERSEER_ENSURE_QUEUE_FUEL_SECTION_2026_09_07 — insert only under
    ``## Active``; refuse headerless writes (empty/whitespace twin must not
    become a ~356B fuel-only clobber invisible to open_work_items).
    """
    base = root or ROOT
    if not train_unlocked(root=base):
        log(
            f"{GUARD_NEEDLE} ensure_queue_fuel: SKIP "
            "(train_unlocked=false — no T4 keep-alive fuel)"
        )
        return []
    ts = time.strftime("%Y-%m-%d %H:%M")
    lines = [
        f"- [ ] [compression-train] Keep-alive fuel — T4 / recipe lock / min-RAM @ NVFP4 ({ts}Z) {NEEDLE}",
        f"- [ ] [compression-train] Efficiency pass — cut unique U; raise S toward 100; measure pack bytes ({ts}Z)",
        f"- [ ] [research-speed] Staff CLEAN fanout — respawn if agents < floor ({ts}Z)",
    ]
    added: list[str] = []
    for rel in ("notes/WORK_QUEUE.md", "scripts/self_improve_context.md"):
        path = base / rel
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if not _has_queue_structure(text):
            log(
                f"{GUARD_NEEDLE} ensure_queue_fuel: SKIP headerless {rel} "
                "(refuse fuel-only clobber — heal twin from WQ first)"
            )
            continue
        changed = False
        for line in lines:
            if _fuel_line_present(text, line):
                continue
            text = _insert_fuel_under_active(text, line)
            changed = True
            if line not in added:
                added.append(line)
        if changed:
            path.write_text(text, encoding="utf-8")
            log(f"queue fuel → {rel}")
    return added


def build_assignments(n: int) -> list:
    import peer_roles as roles
    import project_automation as auto

    tasks = auto.load_tasks_config()
    pool = roles.load_roles_expanded(tasks, target=n)
    out = []
    for i, role in enumerate(pool):
        niche = getattr(role, "niche_task", None) or role.id
        item = (
            f"**{NEEDLE} fanout #{i}** — {niche}\n\n"
            f"{MANDATE}\n\n"
            "Pick one open [compression-train]/[research-speed]/[fact-check]/[bitnet-research] "
            "queue item; land minimal diff + unittest if code; sync WORK_QUEUE ↔ self_improve_context. "
            "Prefer probes that raise S or cut RAM bytes over kit theater. "
            "FORBIDDEN while TRAIN locked: enqueue Shard-* / T4 microbench fanout invent."
        )
        out.append(
            roles.RoleAssignment(
                role=role,
                score=10.0 - (i * 0.01),
                item=item,
                standby=False,
            )
        )
    return out


def _malloc_trim() -> bool:
    """Return pages to the OS after large temporary allocations (Linux glibc)."""
    try:
        import ctypes

        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
        return True
    except Exception:  # noqa: BLE001
        return False


def _should_unload_module(name: str) -> bool:
    if name == "compression_keep_alive" or name.startswith("compression_keep_alive."):
        return False
    return any(name == p or name.startswith(p) for p in _WAVE_UNLOAD_PREFIXES)


def _clear_wave_caches() -> None:
    """Drop known caches before unloading modules (feature-preserving)."""
    try:
        import peer_parallel_dispatch as pp

        pp._agent_procs_cache = None
    except Exception:  # noqa: BLE001
        pass
    try:
        import project_automation as auto

        for attr in (
            "_GIT_CACHE",
            "_LIVE_CACHE",
            "_QUICK_LIVE_CACHE",
            "_AUDIT_SUMMARY_MEMO",
            "_TASKS_CONFIG_CACHE",
        ):
            if hasattr(auto, attr):
                setattr(auto, attr, None)
    except Exception:  # noqa: BLE001
        pass
    try:
        import peer_transcript as pt

        if hasattr(pt, "_LATEST_TRANSCRIPT_CACHE"):
            pt._LATEST_TRANSCRIPT_CACHE = None
    except Exception:  # noqa: BLE001
        pass


def prune_wave_rss(*, reason: str = "wave") -> dict[str, int | str]:
    """Unload fanout-only modules + malloc_trim. Returns unload counts for tests/logs.

    Needle: COMPRESSION_KEEP_ALIVE_WAVE_UNLOAD_2026_09_07
    """
    _clear_wave_caches()
    gc.collect()
    dropped = 0
    for name in list(sys.modules):
        if _should_unload_module(name):
            sys.modules.pop(name, None)
            dropped += 1
    gc.collect()
    trimmed = _malloc_trim()
    gc.collect()
    if reason:
        log(f"{UNLOAD_NEEDLE} prune reason={reason} dropped={dropped} trim={int(bool(trimmed))}")
    return {"dropped": dropped, "trim": int(bool(trimmed)), "reason": reason}


def _prune_after_wave() -> None:
    """Best-effort RSS trim after a dispatch wave (feature-preserving)."""
    prune_wave_rss(reason="after_wave")


def one_wave(target: int) -> tuple[int, bool]:
    # Fail-closed: locked TRAIN + empty Active + n=96 fanout → Shard theater flood.
    if not train_unlocked():
        log(
            f"{GUARD_NEEDLE} one_wave: SKIP fanout target={target} "
            "(train_unlocked=false / T4 NO-GO — no Shard-* invent)"
        )
        return 0, False

    # RAM gate BEFORE build_assignments — avoid allocating n× mandate prompts under pressure.
    # Needle: COMPRESSION_KEEP_ALIVE_LEAN_IDLE_2026_09_06
    # Staff RAM heal: purge ballast once when below floor before skip.
    # Needle: OVERSEER_KEEP_ALIVE_STAFF_RAM_HEAL_2026_09_07
    try:
        import dgx_ram_budget as budget

        if not budget.dispatch_allowed():
            heal = maybe_heal_ram_for_staff_floor(floor=int(os.environ.get("FANOUT_RESPAWN_BELOW", "48")))
            if not budget.dispatch_allowed():
                log(
                    f"{LEAN_NEEDLE} RAM block mode={budget.ram_mode()} — skip wave "
                    f"(pre-build; staff_heal={heal.get('skipped') or heal.get('healed')})"
                )
                return 0, False
            log(f"{LEAN_NEEDLE} staff-ram-heal cleared dispatch — continue wave")
    except Exception as exc:  # noqa: BLE001
        log(f"ram budget soft-skip: {exc}")

    ensure_queue_fuel()
    import peer_parallel_dispatch as pp
    import project_automation as auto

    assignments = build_assignments(target)
    # Clamp to agent-proc cap too — peers=96 + FANOUT_TARGET=24 OOM-kills waves
    # (exit -9) so Staff CLEAN never reaches floor. Needle: OVERSEER_COMPRESSION_KEEP_ALIVE_2026_09_05
    cap = min(
        len(assignments),
        target,
        int(auto.max_parallel_peers()),
        int(auto.max_parallel_agent_procs()),
    )
    try:
        import dgx_ram_budget as budget

        cap = min(cap, int(budget.ram_agent_cap()))
    except Exception as exc:  # noqa: BLE001
        log(f"ram budget soft-skip: {exc}")

    worktrees = sorted(
        (ROOT / ".worktrees").glob("peer-*"),
        key=lambda p: int(p.name.split("-")[-1]) if p.name.split("-")[-1].isdigit() else 0,
    )
    # Deficit-only fill: never storm-launch cap−already when already is undercounted.
    # Default batch=1 avoids wave-58 OOM (rc=-9) when Staff is one short of floor.
    # Needle: OVERSEER_KEEP_ALIVE_STAFF_DEFICIT_BATCH_2026_09_07
    running = cursor_count()
    deficit = max(0, int(cap) - int(running))
    if deficit <= 0:
        log(f"wave skip — running={running} >= cap={cap} billing=desktop_free")
        return 0, True
    batch = min(
        deficit,
        max(1, int(os.environ.get("FANOUT_STAFF_FILL_BATCH", "1"))),
    )
    hub_run = 0
    try:
        hub_run = int(pp.effective_hub_running())
    except Exception:  # noqa: BLE001
        hub_run = 0
    # run_parallel slots = max_workers − effective_hub_running → size for exact batch.
    mw = max(1, hub_run + batch)
    log(
        f"wave start cap={cap} running={running} hub_run={hub_run} "
        f"deficit={deficit} batch={batch} mw={mw} worktrees={len(worktrees)} "
        f"billing=desktop_free"
    )
    try:
        return pp.run_parallel_niche_cycle(
            assignments[: max(batch, mw)],
            worktrees=worktrees[: max(batch, mw)] if worktrees else None,
            log_fn=log,
            paid_api=False,
            max_workers=mw,
        )
    finally:
        del assignments
        _prune_after_wave()


def research_gates_green() -> bool:
    """Delegate to auto-train module when present."""
    try:
        import compression_auto_train as cat

        return bool(cat.research_complete())
    except Exception:
        ready = (ROOT / "notes" / "COMPRESSION_TRAIN_READY.md").read_text(encoding="utf-8")
        recipe = (ROOT / "notes" / "COMPRESSION_TRAIN_RECIPE.md").read_text(encoding="utf-8")
        t4_ok = ("T4" in ready) and any(
            s in ready for s in ("T4 | **Done", "T4 | **PASS", "T4 quality/scale path | **GO")
        )
        # Prefer explicit unlock needle
        if "OVERSEER_COMPRESSION_TRAIN_UNLOCK" in recipe or "train_unlocked: true" in recipe:
            return True
        return t4_ok and ("Status:** **LOCKED" in recipe)


def _paid_api_flag_on(raw: str | None) -> bool:
    """True when env value opts into paid API (fail-closed treats unknown as off)."""
    v = str(raw if raw is not None else "0").strip().lower()
    return v not in ("0", "", "false", "no", "off")


def billing_desktop_free_receipt() -> dict:
    """Fail-closed $0 desktop billing receipt for Finance / keep-alive smoke.

    Keep-alive forces ``PEER_LOOP_PAID_API=0`` at import and passes
    ``paid_api=False`` to wave dispatch. Receipt must still detect a paid
    *preflight* request (caller/service set ``PEER_LOOP_PAID_API=1`` before
    import) — otherwise ``--check`` always greenwashes after the stomp.
    Also fails closed if current env is re-set to paid after import (unittest).
    No secrets. Needle: finance_billing keep-alive.
    """
    raw_now = os.environ.get("PEER_LOOP_PAID_API", "0")
    preflight = _PEER_LOOP_PAID_API_PREFLIGHT
    current_off = not _paid_api_flag_on(raw_now)
    preflight_off = not _paid_api_flag_on(preflight)
    # billing_ok only when neither preflight nor current requests paid.
    billing_ok = current_off and preflight_off
    return {
        "billing_path": "desktop_free",
        "paid_api": False,  # policy never claims paid path for keep-alive
        "peer_loop_paid_api_forced_off": current_off,
        "peer_loop_paid_api_preflight_off": preflight_off,
        "billing_ok": billing_ok,
    }


def check_status(*, root: Path | None = None) -> dict:
    """Non-destructive keep-alive acceptance snapshot (QA smoke — no fanout).

    File/artifact reads only — never runs T0–T3 unittest suites (those belong to
    ``compression_auto_train --check``). Needle: OVERSEER_COMPRESSION_KEEP_ALIVE_2026_09_05.
    """
    base = root or ROOT
    recipe = _read(base / "notes" / "COMPRESSION_TRAIN_RECIPE.md")
    ready = _read(base / "notes" / "COMPRESSION_TRAIN_READY.md")
    art = base / "notes" / "compression_artifacts"
    s_arith = None
    pack_bytes = None
    stress_status = None
    t4_north = None
    t4_path = art / "t4_scale_result.json"
    stress_path = art / "stress_bars.json"
    if t4_path.is_file():
        try:
            t4 = json.loads(t4_path.read_text(encoding="utf-8"))
            t4_north = t4.get("north_star_s_cleared")
            rows = t4.get("results") or []
            if rows:
                s_arith = rows[0].get("s_arith")
                pack_bytes = rows[0].get("nvfp4_bytes")
        except (OSError, json.JSONDecodeError, TypeError, IndexError):
            pass
    if stress_path.is_file():
        try:
            stress = json.loads(stress_path.read_text(encoding="utf-8"))
            stress_status = stress.get("status")
            bar = (stress.get("bars") or {}).get("nvfp4_pack_bytes") or {}
            if bar.get("pack_bytes") is not None:
                pack_bytes = bar.get("pack_bytes")
            s_bar = (stress.get("bars") or {}).get("S_ge_100_or_recipe_floor") or {}
            if s_bar.get("S") is not None:
                s_arith = s_bar.get("S")
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    unlocked = train_unlocked(root=base)
    recipe_ok = "**Status:** **LOCKED**" in recipe
    t4_done = bool(t4_north) or any(
        s in ready for s in ("T4 | **Done", "T4 | **PASS", "T4 quality/scale path | **GO")
    )
    # Lightweight gate proxy — do not import compression_auto_train / run probes.
    gates = unlocked and recipe_ok and t4_done
    agents = cursor_count() if base == ROOT else 0
    floor = int(os.environ.get("FANOUT_RESPAWN_BELOW", "48"))
    if unlocked:
        floor = min(floor, 16)
    # Effective floor cannot exceed launchable agent-proc cap (Staff CLEAN false FAIL).
    try:
        import project_automation as auto

        floor = min(floor, int(auto.max_parallel_agent_procs()))
    except Exception:
        pass
    billing = billing_desktop_free_receipt()
    return {
        "needle": NEEDLE,
        "train_unlocked": unlocked,
        "recipe_locked": recipe_ok,
        "t4_done": t4_done,
        "research_gates_green": gates,
        "agents": agents,
        "floor": floor,
        "agents_ge_floor": agents >= floor if base == ROOT else None,
        "S_arith": s_arith,
        "nvfp4_pack_bytes": pack_bytes,
        "stress_status": stress_status,
        "north_star_s_ok": (s_arith is not None and float(s_arith) >= 100.0),
        "wave": False,
        "billing_path": billing["billing_path"],
        "paid_api": billing["paid_api"],
        "peer_loop_paid_api_forced_off": billing["peer_loop_paid_api_forced_off"],
        "peer_loop_paid_api_preflight_off": billing["peer_loop_paid_api_preflight_off"],
        "billing_ok": billing["billing_ok"],
        "hint": "pass --check (no fanout/no probes) | bare/default = forever",
    }


def check_exit_code(status: dict) -> int:
    """Staff fail-closed: non-zero when hub ``agents_ge_floor`` is explicitly false.

    Needle: OVERSEER_KEEP_ALIVE_CHECK_FAIL_CLOSED_2026_09_07
    ``None`` (non-hub / temp tree) stays exit 0 — field is N/A, not a Staff miss.
    Billing soft-miss stays JSON-only (exit still driven by floor).
    """
    if status.get("agents_ge_floor") is False:
        return 1
    return 0


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="print keep-alive acceptance JSON and exit (no fanout / forever loop)",
    )
    args = ap.parse_args()
    if args.check:
        status = check_status()
        print(json.dumps(status, indent=2))
        return check_exit_code(status)

    target = int(os.environ.get("FANOUT_TARGET", "96"))
    floor = int(os.environ.get("FANOUT_RESPAWN_BELOW", "48"))
    poll = int(os.environ.get("FANOUT_POLL_SEC", "25"))
    idle_prune_every = max(1, int(os.environ.get("FANOUT_IDLE_PRUNE_EVERY", "3")))
    try:
        import project_automation as auto

        proc_cap = int(auto.max_parallel_agent_procs())
        target = min(target, proc_cap)
        floor = min(floor, proc_cap)
    except Exception:
        pass
    log(f"{NEEDLE} forever FREE desktop-auth target={target} floor={floor} poll={poll}s")
    log(f"{GUARD_NEEDLE} train_unlocked={train_unlocked()}")
    log(f"{LEAN_NEEDLE} lazy_dispatch=1")
    log(f"{UNLOAD_NEEDLE} wave_unload=1 idle_prune_every={idle_prune_every}")

    # Initial wave only when below boot floor — restart must not storm-spawn
    # n=cap agents (sticky heap + cgroup RSS). Train-unlocked uses the same
    # min(floor,16) as the forever loop. Needle: COMPRESSION_KEEP_ALIVE_SKIP_BOOT_WAVE_2026_09_07
    boot_floor = min(floor, 16) if train_unlocked() else floor
    n0 = cursor_count()
    if n0 < boot_floor:
        one_wave(target)
    else:
        log(
            f"{UNLOAD_NEEDLE} skip_boot_wave n={n0} boot_floor={boot_floor} "
            f"unlocked={train_unlocked()}"
        )
    prune_wave_rss(reason="post_boot")
    ticks = 0

    while True:
        gates = False
        try:
            gates = research_gates_green()
        finally:
            # research_complete may import compression_auto_train — drop after probe.
            prune_wave_rss(reason="after_gates")
        if gates:
            log("research gates GREEN — invoking compression_auto_train")
            try:
                import compression_auto_train as cat

                cat.start_model_if_ready(force=True)
            except Exception as exc:  # noqa: BLE001
                log(f"auto_train error: {exc}")
            finally:
                prune_wave_rss(reason="after_auto_train")
            # Keep a smaller research/verify floor while train runs
            floor = min(floor, 16)

        n = cursor_count()
        unlocked = train_unlocked()
        log(f"watch count={n} floor={floor} train_unlocked={unlocked}")
        if not unlocked:
            # Fail-closed idle: do not respawn n=96 invent waves under TRAIN lock.
            ticks += 1
            if ticks % idle_prune_every == 0:
                prune_wave_rss(reason="idle_locked")
            time.sleep(poll)
            continue
        if n < floor:
            log("below floor — respawn wave")
            ensure_queue_fuel()
            one_wave(target)
            # touch peer wake
            signal = Path.home() / ".config" / "automation-hub" / "peer-turn.signal"
            try:
                signal.parent.mkdir(parents=True, exist_ok=True)
                signal.write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ") + "\n", encoding="utf-8")
            except OSError:
                pass
        else:
            ticks += 1
            if ticks % idle_prune_every == 0:
                prune_wave_rss(reason="idle_above_floor")
        time.sleep(poll)


if __name__ == "__main__":
    raise SystemExit(main())
