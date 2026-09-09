#!/usr/bin/env python3
"""Launch up to N parallel cursor-agent processes — one niche + worktree each."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
import contextlib
import fcntl
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import peer_roles as roles
import peer_terminal as terminal
import peer_worktree as wt
import project_automation as auto

ROOT = auto.ROOT


@dataclass(frozen=True)
class AgentProc:
    pid: int
    etime: str = ""
    state: str = ""


def _etime_seconds(etime: str) -> float:
    """Parse ps etime ([[dd-]hh:]mm:ss) into seconds — longest = oldest agent."""
    if not etime:
        return 0.0
    text = etime.strip()
    day_sec = 0
    if "-" in text:
        days, _, text = text.partition("-")
        try:
            day_sec = int(days) * 86400
        except ValueError:
            day_sec = 0
    parts = text.split(":")
    try:
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return day_sec + h * 3600 + m * 60 + s
        if len(parts) == 2:
            m, s = int(parts[0]), int(parts[1])
            return day_sec + m * 60 + s
        if len(parts) == 1:
            return day_sec + int(parts[0])
    except ValueError:
        return 0.0
    return 0.0


DISPATCH_LOCK = auto.CONFIG_DIR / "parallel-dispatch.lock"


@contextlib.contextmanager
def _dispatch_flock(*, timeout_sec: float = 30.0):
    DISPATCH_LOCK.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout_sec
    with open(DISPATCH_LOCK, "a+", encoding="utf-8") as lock_fp:
        while True:
            try:
                fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() >= deadline:
                    raise TimeoutError("parallel dispatch flock timeout")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)


def parallel_agent_dispatch_enabled() -> bool:
    return bool(auto.CFG.get("parallel_agent_dispatch", True))


def max_parallel_agent_procs() -> int:
    try:
        cap = int(auto.CFG.get("max_parallel_agent_procs") or auto.parallel_peer_floor())
        return max(1, min(cap, auto.max_parallel_peers()))
    except (TypeError, ValueError):
        return auto.parallel_peer_floor()


def _is_ide_worker_daemon(cmd: str) -> bool:
    """True for IDE ``worker-server`` / argv ``worker`` — not peer ``-p`` agents.

    Install paths contain ``cursor-agent-worker``; a bare ``\"worker\" in cmd``
    false-negative excludes every agent and breaks ``trim_agents_over_cap``
    (~20GB RSS invisible to the finder on DGX).
    """
    if "worker-server" in cmd:
        return True
    for tok in cmd.split():
        if tok.rsplit("/", 1)[-1] == "worker":
            return True
    return False


def _agent_proc_from_cmdline(cmd: str, pid: int) -> AgentProc | None:
    if "cursor-agent" not in cmd:
        return None
    if _is_ide_worker_daemon(cmd):
        return None
    if not re.search(r"(^|\s)-p(\s|$)", cmd):
        return None

    state = ""
    status_path = Path(f"/proc/{pid}/status")
    try:
        for line in status_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("State:"):
                bits = line.split()
                if len(bits) > 1:
                    state = bits[1]
                break
    except OSError:
        pass
    return AgentProc(pid=pid, etime="", state=state)


def _find_agent_procs_proc() -> list[AgentProc]:
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return []
    out: list[AgentProc] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            pid = int(entry.name)
        except ValueError:
            continue
        cmdline_path = entry / "cmdline"
        try:
            raw = cmdline_path.read_bytes()
        except OSError:
            continue
        if not raw:
            continue
        cmd = raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
        proc = _agent_proc_from_cmdline(cmd, pid)
        if proc is not None:
            out.append(proc)
    return out


def _find_agent_procs_ps() -> list[AgentProc]:
    try:
        proc = subprocess.run(
            ["ps", "-ax", "-o", "pid=,etime=,state=,command="],
            capture_output=True,
            text=True,
            timeout=8.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0 or not proc.stdout:
        return []
    out: list[AgentProc] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or "cursor-agent" not in line:
            continue
        if _is_ide_worker_daemon(line):
            continue
        if not re.search(r"(^|\s)-p(\s|$)", line):
            continue
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        out.append(AgentProc(pid=pid, etime=parts[1], state=parts[2]))
    return out


_AGENT_PROCS_TTL_SEC = 2.0
_agent_procs_cache: tuple[float, list[AgentProc]] | None = None


def find_agent_procs(*, fresh: bool = False) -> list[AgentProc]:
    """All background ``cursor-agent -p`` peer cycles (not worker daemons)."""
    global _agent_procs_cache
    now = time.time()
    if not fresh and _agent_procs_cache and now - _agent_procs_cache[0] < _AGENT_PROCS_TTL_SEC:
        return _agent_procs_cache[1]

    procs: list[AgentProc]
    try:
        import peer_remote

        if peer_remote.remote_enabled():
            dgx = auto.CFG.get("dgx_host")
            on_primary_linux = (
                isinstance(dgx, dict)
                and dgx.get("primary")
                and sys.platform == "linux"
            )
            if not on_primary_linux:
                count = peer_remote.count_remote_agent_procs()
                if count > 0:
                    # Remote count affects cap math only — do not inject fake PIDs into trim.
                    _agent_procs_cache = (now, [])
                    return []
    except Exception:  # noqa: BLE001
        pass
    if sys.platform == "linux":
        procs = _find_agent_procs_proc()
        if procs or Path("/proc").is_dir():
            _agent_procs_cache = (now, procs)
            return procs
    procs = _find_agent_procs_ps()
    _agent_procs_cache = (now, procs)
    return procs


def trim_agents_over_cap(*, log_fn: Callable[[str], None] | None = None) -> int:
    """SIGKILL oldest excess cursor-agents when over global cap (drain legacy swarms)."""
    if not auto.CFG.get("trim_agents_over_cap", True):
        return 0
    cap = max_parallel_agent_procs()
    try:
        import dgx_ram_budget as budget

        cap = min(cap, budget.ram_agent_cap())
    except Exception:  # noqa: BLE001
        pass
    procs = sorted(find_agent_procs(), key=lambda p: _etime_seconds(p.etime), reverse=True)
    if len(procs) <= cap:
        return 0
    killed = 0
    for proc in procs[cap:]:
        if proc.pid <= 0:
            continue
        try:
            os.kill(proc.pid, signal.SIGKILL)
            killed += 1
        except OSError:
            pass
    if killed and log_fn:
        log_fn(f"parallel: trimmed {killed} excess agent(s) ({len(procs)} > {cap})")
    return killed


def find_agent_proc() -> AgentProc | None:
    """First running peer cursor-agent (compat with peer_watch)."""
    procs = find_agent_procs()
    return procs[0] if procs else None


def _proc_cwd(pid: int) -> Path | None:
    """Resolve process cwd — Linux /proc, macOS lsof (no /proc).

    OVERSEER_PROC_CWD_MAC_LSOF_2026_09_04 — Darwin ``Path('/proc/N/cwd').resolve()``
    returns a fake ``/proc/N/cwd`` path (not the real cwd). Forge scrub then
    killed 0 orphans while 20+ CaaS agents kept verify permanently deferred.
    """
    if pid <= 0:
        return None
    if sys.platform.startswith("linux"):
        link = Path(f"/proc/{pid}/cwd")
        try:
            return link.resolve()
        except OSError:
            return None
    # macOS / BSD — lsof -Fn name line is ``n/path``
    try:
        out = subprocess.check_output(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            text=True,
            errors="replace",
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        if line.startswith("n") and len(line) > 1:
            raw = line[1:].strip()
            if raw and raw != "(unknown)":
                try:
                    return Path(raw).resolve()
                except OSError:
                    return Path(raw)
    return None


def count_agents_under(root: Path) -> int:
    """Agents whose cwd is under ``root`` (Linux /proc; else counts all)."""
    root = root.resolve()
    n = 0
    for proc in find_agent_procs():
        if proc.pid <= 0:
            continue
        cwd = _proc_cwd(proc.pid)
        if cwd is None:
            continue
        try:
            cwd.relative_to(root)
            n += 1
        except ValueError:
            continue
    return n


def count_agents_outside(*, hub_worktree_root: Path) -> int:
    """Agents not running in hub parallel worktrees."""
    hub_worktree_root = hub_worktree_root.resolve()
    outside = 0
    for proc in find_agent_procs():
        if proc.pid <= 0:
            outside += 1
            continue
        cwd = _proc_cwd(proc.pid)
        if cwd is None:
            continue
        try:
            cwd.relative_to(hub_worktree_root)
        except ValueError:
            outside += 1
    return outside


def hub_dispatch_cap() -> int:
    """Hub niche launch cap — always ≤ worker_pool_size (typically 8), never floor=48."""
    try:
        pool = roles.worker_pool_size()
    except Exception:  # noqa: BLE001
        pool = roles.DEFAULT_HUB_WORKER_POOL
    procs = max_parallel_agent_procs()
    try:
        import factory_grid as fg

        if fg.grid_enabled():
            return max(1, min(fg.hub_agent_cap(), pool, procs))
    except Exception:  # noqa: BLE001
        pass
    return max(1, min(procs, pool))


def effective_hub_running() -> int:
    try:
        import factory_grid as fg

        if fg.grid_enabled():
            return count_agents_under(fg.hub_worktree_root())
    except Exception:  # noqa: BLE001
        pass
    local = len(find_agent_procs())
    try:
        import peer_remote

        if peer_remote.remote_enabled():
            dgx = auto.CFG.get("dgx_host")
            on_primary_linux = (
                isinstance(dgx, dict) and dgx.get("primary") and sys.platform == "linux"
            )
            if not on_primary_linux:
                return local + peer_remote.count_remote_agent_procs()
    except Exception:  # noqa: BLE001
        pass
    return local


def _niche_verify_command() -> str:
    cmd = auto.quick_test_command()
    if cmd:
        return " ".join(str(x) for x in cmd)
    return "python3 -m unittest discover -s tests -q"


def build_niche_prompt(asn: roles.RoleAssignment, *, cwd: Path) -> str:
    """Single-role prompt — no orchestrator, implement only this niche."""
    role = asn.role
    read_paths = list(dict.fromkeys([*role.reads]))
    try:
        import peer_team_context as tc

        read_paths = tc.shared_read_paths(extra=list(read_paths))
        team_block = tc.format_team_snapshot(max_chars=2500)
    except Exception:  # noqa: BLE001
        team_block = ""
        learn_block = ""
    memory_section = ""
    try:
        import peer_memory_span as ms

        pack = ms.format_memory_pack(
            role_id=role.id,
            assignment=str(asn.item or ""),
            include_cold=True,
        )
        if pack.strip():
            memory_section = f"\n{pack.strip()}\n"
    except Exception:  # noqa: BLE001
        pass
    try:
        import peer_persona_rules as pr

        persona_block = pr.format_persona_rules_block(
            role.id, fallback_job_title=role.job_title
        )
    except Exception:  # noqa: BLE001
        persona_block = ""
    reads = "\n".join(f"- {r}" for r in read_paths[:16]) if read_paths else "- notes/TEAM_CONTEXT.md"
    team_section = ""
    if team_block.strip():
        team_section = f"""
## Team snapshot (operational — queue/live/factory)

{team_block.strip()}
"""
    persona_section = f"\n{persona_block.strip()}\n" if persona_block.strip() else ""
    return f"""# Niche agent — {role.job_title}

You are **only** the **{role.job_title}**. Do not orchestrate other roles or re-plan the full queue.

**Model:** {role.model}
**Subagent type:** {role.subagent_type}
**Role id:** `{role.id}`
**Working directory:** `{cwd}`
{team_section}{persona_section}{memory_section}
## Your assignment (own this scope only)
{asn.item}

## Responsibilities
{role.responsibilities or "Land a minimal scoped diff."}

## Read first (full list — do not skip)
{reads}

## Rules
0. **Diagnose first** — `./scripts/peer plan-gate --role {role.id}` (or `./scripts/peer diagnose`); fix fail rows before edits.
0b. **Strategize** — write hallucination defy block (evidence path, falsifier, verify) before edit.
1. **Think first** — answer Plan gate + self-check questions before editing.
2. **Pinpoint** — name file:line needle; ≤3 files read; touch ≤1 file before targeted verify.
3. **Compare** — state expected verify output; diff actual before DONE (`./scripts/peer output-compare`).
3b. **Human gaps** — scan AGENT_VS_HUMAN; run countermeasure for applicable rows.
3c. **Ideate** — new proposals need ≥2 anchors + `./scripts/peer idea-articulate`; record with `idea-record`.
4. **Memory** — read Hot/Warm/Cold tiers above; `memory-record` facts you must not forget.
5. **Assign** — delegate when faster: `./scripts/peer eta` then `./scripts/peer assign --from {role.id} --to ROLE --task "..."`
6. **Learn** — `./scripts/peer learn-record --role {role.id} --text "..."` when done.
7. **Mini app** — repeat manual steps twice → `./scripts/peer mini-apps --scaffold --name tool --purpose "..."`
8. Minimal diff — match repo conventions; stay in your niche scope.
9. Run verify from repo root before done: `{_niche_verify_command()}`
10. Post GLink DONE with cycle_id + paths + {{expected_vs_actual}} when finished.
10b. **Done gate** — `./scripts/peer done-gate --role {role.id} --expected "..." --actual "..."` before DONE.

Implement now — no plan-only output.

**Before your first edit:** write strategy block (hallucination guard) + Plan/haystack answers in persona block.
**Before DONE:** answer Done self-check questions; compare expected vs actual; post BLOCK on mismatch.
"""


def _run_one_niche(
    asn: roles.RoleAssignment,
    cwd: Path,
    *,
    log_fn: Callable[[str], None],
    paid_api: bool,
) -> tuple[str, int, bool]:
    role = asn.role
    prompt = build_niche_prompt(asn, cwd=cwd)
    log_fn(f"parallel: launch {role.job_title} · cwd={cwd}")
    rc, auth_failed = terminal.run_cursor_agent(
        prompt,
        log_fn=log_fn,
        paid_api=paid_api,
        cwd=cwd,
    )
    return role.id, rc, auth_failed


def run_parallel_niche_cycle(
    assignments: list[roles.RoleAssignment],
    worktrees: list[Path] | None = None,
    *,
    log_fn: Callable[[str], None],
    paid_api: bool = False,
    max_workers: int | None = None,
) -> tuple[int, bool]:
    """Run up to ``max_workers`` cursor-agent processes in parallel (one niche each)."""
    assignments = [a for a in assignments if not getattr(a, "standby", False)]
    if not assignments:
        log_fn("parallel: no role assignments — skip")
        return 0, False

    cap = max_workers if max_workers is not None else hub_dispatch_cap()
    cap = max(1, min(cap, len(assignments)))
    try:
        import dgx_ram_budget as budget

        cap = min(cap, budget.ram_agent_cap())
        if not budget.dispatch_allowed():
            log_fn(
                f"parallel: RAM mode {budget.ram_mode()} — dispatch blocked "
                f"(footprint {budget.footprint_gb():.1f}GB)"
            )
            trim_agents_over_cap(log_fn=log_fn)
            return 0, False
    except Exception:  # noqa: BLE001
        pass

    try:
        with _dispatch_flock():
            already = effective_hub_running()
            global_running = len(find_agent_procs())
            try:
                import factory_grid as fg

                if fg.grid_enabled() and global_running >= fg.global_agent_cap():
                    log_fn(
                        f"parallel: global cap ({global_running}/{fg.global_agent_cap()}) — skip hub launch"
                    )
                    trim_agents_over_cap(log_fn=log_fn)
                    return 0, False
            except Exception:  # noqa: BLE001
                pass

            if already >= cap:
                log_fn(f"parallel: {already} agent(s) already running — skip launch (cap {cap})")
                return 0, False

            slots = cap - already
            batch = assignments[:slots]
    except TimeoutError:
        log_fn("parallel: dispatch flock busy — skip launch")
        return 0, False

    pool = worktrees or []
    if len(pool) < len(batch):
        try:
            pool = wt.ensure_parallel_pool(count=len(batch), log_fn=log_fn)
        except Exception as exc:  # noqa: BLE001
            log_fn(f"parallel: worktree pool partial ({exc})")

    # Never fall back to hub ROOT — agents on ROOT collide with the daemon tree.
    if len(pool) < len(batch):
        skipped = len(batch) - len(pool)
        log_fn(
            f"parallel: refuse ROOT cwd for {skipped} niche(s) "
            f"(pool={len(pool)} < batch={len(batch)}) — skip launch"
        )
        batch = batch[: len(pool)]
    if not batch:
        log_fn("parallel: no worktree slots — skip launch")
        return 0, False

    try:
        import peer_agent_board as board

        board.record_role_assignments(batch, source="parallel_dispatch")
    except Exception:  # noqa: BLE001
        pass

    log_fn(f"parallel: dispatching {len(batch)} niche agent(s) (cap {cap}, {already} already running)")

    remote_batch = False
    try:
        import peer_remote

        if peer_remote.remote_enabled() and bool(peer_remote._cfg().get("sync_before_dispatch", True)):
            remote_batch = peer_remote.sync_project(log_fn=log_fn, direction="push")
            if not remote_batch:
                log_fn("parallel: remote push failed — aborting batch")
                return 1, False
    except Exception as exc:  # noqa: BLE001
        log_fn(f"parallel: remote pre-sync skipped ({exc})")

    worst_rc = 0
    auth_failed = False
    with ThreadPoolExecutor(max_workers=len(batch)) as executor:
        futures = {}
        for i, asn in enumerate(batch):
            cwd = pool[i].resolve()
            fut = executor.submit(
                _run_one_niche,
                asn,
                cwd,
                log_fn=log_fn,
                paid_api=paid_api,
            )
            futures[fut] = asn.role.job_title

        for fut in as_completed(futures):
            title = futures[fut]
            try:
                _role_id, rc, af = fut.result()
            except Exception as exc:  # noqa: BLE001
                log_fn(f"parallel: {title} failed ({exc})")
                worst_rc = max(worst_rc, 1)
                continue
            worst_rc = max(worst_rc, rc)
            auth_failed = auth_failed or af
            log_fn(f"parallel: {title} finished rc={rc}")

    if remote_batch:
        try:
            import peer_remote

            if bool(peer_remote._cfg().get("sync_after_dispatch", True)):
                peer_remote.sync_project(log_fn=log_fn, direction="pull")
        except Exception as exc:  # noqa: BLE001
            log_fn(f"parallel: remote post-sync failed ({exc})")

    return worst_rc, auth_failed
