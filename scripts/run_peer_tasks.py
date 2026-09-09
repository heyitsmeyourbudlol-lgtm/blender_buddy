#!/usr/bin/env python3
"""Execute scripted verify/self-check steps for local-only peer loop."""

from __future__ import annotations

import argparse
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import project_automation as auto  # noqa: E402

# Mirror peer_orchestrate.SELF_CHECK_LOCK_BUSY_RC — avoid eager po (~+9.7MB) on verify path.
# COMPRESSION_LAZY_RPT_PO_2026_09_04
# OVERSEER_RPT_PO_LAZY_ALIAS_2026_09_04 — tests patch ``rpt.po``; keep alias without
# paying import cost until first attribute access.
SELF_CHECK_LOCK_BUSY_RC = 75


class _LazyPo:
    _mod = None

    def __getattr__(self, name: str):
        if type(self)._mod is None:
            import peer_orchestrate as _po_mod

            type(self)._mod = _po_mod
        return getattr(type(self)._mod, name)


po = _LazyPo()

# Failure classes persisted on peer-loop-state last_cycle.failure_type
VERIFY_FAILURE_TYPES = ("tests", "self-check", "timeout", "adapt_stale", "other")
ADAPT_STALE_FAILURE = "adapt_stale"
VERIFY_LOCK_PATH = auto.CONFIG_DIR / "verify.lock"
# OVERSEER_SCRUB_ORPHAN_FORGE_VERIFY_2026_09_04
# OVERSEER_SELF_CHECK_CAP_DEFER
VERIFY_LOCK_STALE_SEC = 600.0

_TEST_MARKERS = (
    "unittest",
    "pytest",
    "npm test",
    "pnpm test",
    "yarn test",
    "cargo test",
    "go test",
    " discover -s tests",
    "/tests",
    "\\tests",
    " test",
)


def _is_recursive_adapt_command(cmd: str) -> bool:
    low = cmd.lower()
    if "automation_adapt" not in low:
        return False
    return any(flag in low for flag in ("--audit", "--heal", "--write"))



def _lean_split_verify_commands(cmds: list[str]) -> list[str]:
    """Split combined multi-module unittest one-liners (storm-trim -9 guard).

    Needle: OVERSEER_LEAN_SPLIT_VERIFY_LOAD_2026_09_04
    """
    out: list[str] = []
    for c in cmds:
        raw = str(c).strip()
        if not raw:
            continue
        if "unittest" in raw and raw.count("tests.") > 1:
            try:
                parts = shlex.split(raw)
            except ValueError:
                parts = raw.split()
            modules = [p for p in parts if p.startswith("tests.")]
            quiet = "-q" in parts
            for mod in modules:
                cmd = f"python3 -m unittest {mod}"
                if quiet:
                    cmd += " -q"
                if cmd not in out:
                    out.append(cmd)
            continue
        if raw not in out:
            out.append(raw)
    return out


def load_verify_commands() -> list[str]:
    override = auto.CFG.get("verify_commands")
    if isinstance(override, list) and override:
        cmds = [str(c) for c in override if str(c).strip()]
    else:
        cfg = auto.load_tasks_config()
        cmds = [c for c in (cfg.get("verify_commands") or []) if c]
    cmds = [c for c in cmds if not _is_recursive_adapt_command(str(c))]
    return _lean_split_verify_commands(cmds)


def _verify_quiet_limits() -> tuple[int, int]:
    """Agent/unittest caps for verify quiet-wait — not the dispatch swarm cap.

    ``verify_quiet_max_agents`` (default 2, clamped 0–2) decides when hub verify
    may run under a live cursor-agent pool. Using ``max_parallel_agent_procs``
    made quiet-wait always pass under a full swarm.
    """
    try:
        if "verify_quiet_max_agents" in auto.CFG:
            agent_cap = int(auto.CFG.get("verify_quiet_max_agents"))
        else:
            agent_cap = 2
        agent_cap = max(0, min(2, agent_cap))
    except (TypeError, ValueError):
        agent_cap = 2
    try:
        max_tests = max(0, int(auto.CFG.get("verify_quiet_max_unittest") or 2))
    except (TypeError, ValueError):
        max_tests = 2
    return agent_cap, max_tests


def _free_desktop_saturate_ignore_agents() -> bool:
    """True when free-desktop intentionally holds agents at the floor.

    ``trim_agents_over_cap=false`` + free-desktop cap means agents stay near 8
    forever. Quiet-wait must not forever-defer on ``agents>verify_quiet_max``
    (T10-04 verify-deferred / local_only theater). Unittest + self-check caps
    still apply. Needle: ``OVERSEER_T10_04_FREE_DESKTOP_VERIFY_QUIET_2026_09_08``.
    """
    return auto.CFG.get("trim_agents_over_cap", True) is False


def _beat_mac_hub_protect_before_verify(*, log_fn=print) -> None:
    """Restore hub-protect needles before verify so Mac rsync cannot red the gate.

    Needle: OVERSEER_VERIFY_BEAT_MAC_2026_09_04

    Live Mac→DGX thrash rewrites ``scripts/peer_remote.py`` every few seconds and
    drops ``notes/WORK_QUEUE.md`` from ``HUB_PROTECT_PULL_EXCLUDES``. That makes
    ``tests.test_peer_remote`` fail mid-verify even though vault+beat are healthy.
    Refresh vault needles immediately before the gate.
    """
    restored = 0
    vault = Path.home() / ".config" / "automation-hub" / "hub-protect"
    required: dict[str, tuple[str, ...]] = {
        "peer_remote.py": (
            "notes/WORK_QUEUE.md",
            "notes/REPO_FLAW_RESEARCH.md",
            "OVERSEER_HUB_PROTECT_EXCLUDES_2026_09_04",
        ),
        # OVERSEER_BEAT_TRANSCRIPT_MERGE_AND_2026_09_04 — Mac partial keeps STATE_SAVE but drops merge.
        "peer_transcript.py": (
            "def _merge_preserve_cycle_memory",
            "OVERSEER_SAVE_PRESERVE_LAST_CYCLE_2026_09_04",
        ),
    }
    for rel, needles in required.items():
        live_p = SCRIPTS / rel
        src = vault / rel
        if not src.is_file():
            alt = vault / "scripts" / rel
            src = alt if alt.is_file() else src
        if not src.is_file():
            continue
        try:
            body0 = live_p.read_text(encoding="utf-8", errors="replace") if live_p.is_file() else ""
        except OSError:
            body0 = ""
        missing = [n for n in needles if n not in body0]
        if not missing:
            continue
        try:
            live_p.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            restored += 1
            log_fn(f"verify: restored hub-protect {rel} (missing {missing[0]})")
        except OSError as exc:
            log_fn(f"verify: hub-protect restore {rel} failed ({exc})")
    # Needle: OVERSEER_BEAT_TRANSCRIPT_MERGE_AND_2026_09_04
    bin_beat = Path.home() / ".config" / "automation-hub" / "bin" / "beat-mac-clobber.sh"
    scripts_beat = SCRIPTS / "beat-mac-clobber.sh"
    beat = scripts_beat
    for candidate in (bin_beat, scripts_beat):
        if candidate.is_file():
            try:
                body = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                body = ""
            if "def _merge_preserve_cycle_memory" in body or "OVERSEER_BEAT_TRANSCRIPT_MERGE_AND_2026_09_04" in body:
                beat = candidate
                break
    if beat.is_file():
        try:
            proc = subprocess.run(
                ["bash", str(beat)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=45.0,
                check=False,
            )
            if proc.returncode == 0:
                log_fn("verify: beat-mac hub-protect refresh before gate")
            elif (proc.stderr or proc.stdout or "").strip():
                tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1]
                log_fn(f"verify: beat-mac rc={proc.returncode} — {tail}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            log_fn(f"verify: beat-mac skipped ({exc})")
    if restored:
        log_fn(f"verify: hub-protect needle restore count={restored}")
        # OVERSEER_ADAPT_SYNC_AFTER_HUB_PROTECT_2026_09_04 — restore dirties
        # scripts/ porcelain; sync fingerprint so adapt_stale does not reopen.
        try:
            import automation_adapt as adapt

            if adapt.sync_git_fingerprint(ROOT):
                log_fn("verify: synced adapt fingerprint after hub-protect restore")
        except Exception as exc:  # noqa: BLE001
            log_fn(f"verify: adapt fingerprint sync skipped ({exc})")


def _prepare_verify_lane(*, log_fn=print) -> None:
    """Trim unittest + self-check storms so hub verify is not force-killed mid-run."""
    # OVERSEER_VERIFY_BEAT_MAC_2026_09_04 — Mac clobber window must not red verify.
    try:
        _beat_mac_hub_protect_before_verify(log_fn=log_fn)
    except Exception:  # noqa: BLE001
        pass

    try:
        import dgx_ram_budget as budget

        trim_cap = int(auto.CFG.get("verify_trim_unittest_cap") or 2)
        killed = budget.trim_unittest_storm(cap=max(0, trim_cap))
        if killed:
            log_fn(f"verify: trimmed {killed} unittest worker(s) before gate")
        sc_cap = int(auto.CFG.get("verify_trim_self_check_cap") or auto.CFG.get("dgx_self_check_cap") or 2)
        killed_sc = budget.trim_self_check_storm(cap=max(0, sc_cap))
        if killed_sc:
            log_fn(f"verify: trimmed {killed_sc} self-check worker(s) before gate")
    except Exception:  # noqa: BLE001
        pass

    # OVERSEER_SCRUB_ORPHAN_FORGE_VERIFY_CALL_2026_09_04 — inactive forge leaves
    # CaaS cursor-agents (ppid=1) that keep agents>quiet_cap → forever deferred.
    try:
        import peer_product_forge as forge

        if not forge.forge_active():
            n = forge.scrub_orphan_forge_agents(log_fn=log_fn)
            if n:
                log_fn(f"verify: scrubbed {n} orphan product-forge agent(s)")
    except Exception:  # noqa: BLE001
        pass


def _wait_verify_quiet(*, log_fn=print, timeout_sec: float | None = None) -> bool:
    """Wait until agent/unittest/self-check load is low enough for hub verify. Returns False to defer."""
    try:
        import peer_parallel_dispatch as ppd
        import dgx_ram_budget as budget
    except Exception:  # noqa: BLE001
        return True

    if timeout_sec is None:
        try:
            # Prefer fast defer over 10m lock-starvation when unittest swarm is up.
            timeout_sec = float(auto.CFG.get("verify_quiet_timeout_sec") or 90.0)
        except (TypeError, ValueError):
            timeout_sec = 90.0
    agent_cap, max_tests = _verify_quiet_limits()
    try:
        max_sc = max(0, int(auto.CFG.get("verify_quiet_max_self_check") or auto.CFG.get("dgx_self_check_cap") or 2))
    except (TypeError, ValueError):
        max_sc = 2
    try:
        trim_cap = int(auto.CFG.get("verify_trim_unittest_cap") or max_tests)
    except (TypeError, ValueError):
        trim_cap = max_tests
    try:
        sc_trim = int(auto.CFG.get("verify_trim_self_check_cap") or max_sc)
    except (TypeError, ValueError):
        sc_trim = max_sc
    deadline = time.time() + max(15.0, timeout_sec)
    while time.time() < deadline:
        # Agents often respawn unittest/self-check during the wait — re-trim each tick or
        # heal-all sits deferred with unittest=12 after only trimming once.
        try:
            killed = budget.trim_unittest_storm(cap=max(0, trim_cap))
            if killed:
                log_fn(f"verify: re-trimmed {killed} unittest worker(s) during quiet-wait")
        except Exception:  # noqa: BLE001
            pass
        try:
            killed_sc = budget.trim_self_check_storm(cap=max(0, sc_trim))
            if killed_sc:
                log_fn(f"verify: re-trimmed {killed_sc} self-check worker(s) during quiet-wait")
        except Exception:  # noqa: BLE001
            pass
        agents = len(ppd.find_agent_procs())
        tests = budget.unittest_worker_count()
        self_checks = budget.self_check_worker_count()
        ignore_agents = _free_desktop_saturate_ignore_agents()
        agents_ok = ignore_agents or agents <= agent_cap
        if agents_ok and tests <= max_tests and self_checks <= max_sc:
            if agents or tests or self_checks:
                if ignore_agents and agents > agent_cap:
                    log_fn(
                        f"verify: quiet (free-desktop saturate — agents={agents} "
                        f"ignored; unittest={tests}, self-check={self_checks})"
                    )
                else:
                    log_fn(
                        f"verify: quiet (agents={agents}, unittest={tests}, "
                        f"self-check={self_checks})"
                    )
            return True
        time.sleep(3.0)
    agents = len(ppd.find_agent_procs())
    tests = budget.unittest_worker_count()
    self_checks = budget.self_check_worker_count()
    if _free_desktop_saturate_ignore_agents() and tests <= max_tests and self_checks <= max_sc:
        # Race: agents-only load under free-desktop — do not defer.
        log_fn(
            f"verify: quiet (free-desktop saturate — agents={agents} ignored; "
            f"unittest={tests}, self-check={self_checks})"
        )
        return True
    log_fn(
        f"verify: deferred — swarm active (agents={agents}/{agent_cap}, "
        f"unittest={tests}/{max_tests}, self-check={self_checks}/{max_sc})"
    )
    return False


def classify_verify_failure(cmd: str, *, timed_out: bool = False) -> str:
    """Map a verify command (and outcome) to tests | self-check | timeout | other."""
    if timed_out:
        return "timeout"
    lower = cmd.lower()
    if "self-check" in lower:
        return "self-check"
    if any(marker in lower for marker in _TEST_MARKERS):
        return "tests"
    return "other"


def _try_acquire_verify_lock() -> bool:
    """Single-flight verify across improve + peer daemons. Stale locks are stolen."""
    VERIFY_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    try:
        if VERIFY_LOCK_PATH.is_file():
            age = now - VERIFY_LOCK_PATH.stat().st_mtime
            if age < VERIFY_LOCK_STALE_SEC:
                try:
                    pid = int(VERIFY_LOCK_PATH.read_text().strip().splitlines()[0])
                except (OSError, ValueError, IndexError):
                    pid = None
                if pid and pid != os.getpid():
                    try:
                        os.kill(pid, 0)
                        return False  # holder alive
                    except OSError:
                        pass  # stale pid
        VERIFY_LOCK_PATH.write_text(f"{os.getpid()}\n{now}\n")
        return True
    except OSError:
        return True


def _release_verify_lock() -> None:
    try:
        if VERIFY_LOCK_PATH.is_file():
            text = VERIFY_LOCK_PATH.read_text()
            if text.startswith(str(os.getpid())):
                VERIFY_LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _adapt_audit_blocks_verify(*, log_fn=print) -> tuple[bool, str | None]:
    """Quick adapt audit before verify PASS — fail fast on stale fingerprint."""
    try:
        import automation_adapt as adapt

        report = adapt.run_audit(ROOT, quick=True)
    except Exception as exc:  # noqa: BLE001
        log_fn(f"verify ADAPT_STALE: audit probe failed — {exc}")
        return True, ADAPT_STALE_FAILURE

    for finding in report.findings:
        if finding.level != "warn" or finding.category != "adapt_state":
            continue
        msg = (finding.message or "").lower()
        if "fingerprint stale" in msg or "verify_commands drift" in msg:
            log_fn(f"verify ADAPT_STALE: {finding.message}")
            return True, ADAPT_STALE_FAILURE
    for finding in report.findings:
        # Queue drift is Institutional-memory / sync-queue — not adapt fingerprint.
        # Mapping it to ADAPT_STALE forever-blocks dispatch while heal runs adapt.
        if finding.level == "error" and finding.category == "adapt_state":
            log_fn(f"verify ADAPT_STALE: {finding.category}: {finding.message}")
            return True, ADAPT_STALE_FAILURE
        if finding.level == "error" and finding.category == "queue":
            log_fn(f"verify queue drift (non-blocking): {finding.message[:120]}")
    return False, None


def _run_cmd_group(cmd: str, *, timeout: float) -> subprocess.CompletedProcess[str]:
    """Run verify cmd in its own process group so timeouts cannot orphan children.

    OVERSEER_VERIFY_PROTECT_REGISTER_2026_09_04 — register session leader so
    trim_unittest_storm cannot force-kill hub verify mid-gate (rc=-9 theater).
    """
    argv = shlex.split(cmd)
    proc = subprocess.Popen(
        argv,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        import dgx_ram_budget as budget

        budget.register_verify_protect(proc.pid)
    except Exception:  # noqa: BLE001
        pass
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, 9)  # force-kill process group on timeout
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        raise
    finally:
        try:
            import dgx_ram_budget as budget

            budget.unregister_verify_protect(proc.pid)
        except Exception:  # noqa: BLE001
            pass
    return subprocess.CompletedProcess(argv, proc.returncode or 0, stdout, stderr)


def run_verify_commands(*, log_fn=print) -> tuple[int, str | None]:
    """Run configured verify commands.

    Returns (failure_count, primary_failure_type). primary_failure_type is None
    when all commands pass; otherwise the first failure's class.

    Quiet-wait runs *before* taking the single-flight lock so a 600s swarm
    sleep cannot starve heal-all / peer verify (verify_storm root cause).
    """
    _prepare_verify_lane(log_fn=log_fn)
    if not _wait_verify_quiet(log_fn=log_fn):
        return -1, "deferred"
    if not _try_acquire_verify_lock():
        log_fn("verify: skipped — another verify already running")
        # Not success — peer_loop must not treat lock-skip as verify_ok / auto-commit.
        return -1, "deferred"
    failures = 0
    failure_type: str | None = None
    try:
        try:
            import automation_adapt as adapt

            synced = adapt.sync_notes_only_fingerprint(ROOT)
            log_fn(
                "verify: notes-only fingerprint synced"
                if synced
                else "verify: notes-only fingerprint ok"
            )
            # OVERSEER_SYNC_VERIFY_CMDS_2026_09_04 — heal drift before ADAPT_STALE
            vc_synced = adapt.sync_verify_commands_state(ROOT)
            log_fn(
                "verify: verify_commands adapt-state synced"
                if vc_synced
                else "verify: verify_commands adapt-state ok"
            )
        except Exception as exc:  # noqa: BLE001
            log_fn(f"verify: notes-only fingerprint skip ({exc})")
        blocked, block_kind = _adapt_audit_blocks_verify(log_fn=log_fn)
        if blocked:
            return 1, block_kind
        for cmd in load_verify_commands():
            if "self-check" in cmd.lower():
                try:
                    import dgx_ram_budget as budget

                    # OVERSEER_SELF_CHECK_CAP_DEFER_RETURN_2026_09_04 — never
                    # `continue` past self-check under cap (false PASS / failures=0).
                    cap = max(1, int(auto.CFG.get("dgx_self_check_cap") or 2))
                    running = budget.self_check_worker_count()
                    if running >= cap:
                        log_fn(
                            f"verify: deferred — self-check cap "
                            f"({running} running ≥ cap {cap}; not a green skip)"
                        )
                        return -1, "deferred"
                except Exception:  # noqa: BLE001
                    pass
            log_fn(f"verify: {cmd}")
            try:
                proc = _run_cmd_group(cmd, timeout=600.0)
            except subprocess.TimeoutExpired:
                failures += 1
                kind = classify_verify_failure(cmd, timed_out=True)
                if failure_type is None:
                    failure_type = kind
                log_fn(f"verify TIMEOUT: {cmd}")
                continue
            if proc.returncode != 0:
                out = ((proc.stdout or "") + (proc.stderr or "")).strip()
                if "self-check" in cmd.lower() and (
                    proc.returncode == SELF_CHECK_LOCK_BUSY_RC
                    or "SKIP: another self-check already running" in out
                ):
                    log_fn("verify: deferred — self-check lock held")
                    return -1, "deferred"
                # OVERSEER_VERIFY_FORCEKILL_DEFER_2026_09_04 — storm trim / OOM
                # force-kill (rc<0, esp -9) is not a red test; matches adapt audit
                # OVERSEER_AUDIT_FORCEKILL_SKIP. Hard-FAIL poisoned verify_ok=false.
                if int(proc.returncode or 0) < 0:
                    log_fn(
                        f"verify: deferred — signal kill rc={proc.returncode} "
                        f"({cmd[:70]}; storm trim theater)"
                    )
                    return -1, "deferred"
                failures += 1
                kind = classify_verify_failure(cmd)
                if failure_type is None:
                    failure_type = kind
                tail = out.splitlines()
                log_fn(f"verify FAIL ({proc.returncode}): {tail[-1] if tail else cmd}")
    finally:
        _release_verify_lock()
    return failures, failure_type


def _clear_deferred_stamp_after_ready(*, log_fn=print) -> bool:
    """OVERSEER_VERIFY_CLEAR_DEFERRED_2026_09_07 — green ready clears soft deferred.

    Soft-skip leaves ``verify_ok=False`` + ``failure_type=deferred``. heal-all /
    ``run_local_cycle`` ready used to leave that stamp forever → oversight WAITING
    + Non-noop delivery flat theater. Clear only soft deferred (never stamp
    verify_ok=True while failure_type=deferred — poison).

    Mutate ``last_cycle`` in place — do **not** ``record_cycle_outcome`` with
    ``local_only=True`` (that was T10-04 theater: overwrote countable agent
    cycles and never bumped ``non_noop_by_day``). Needle:
    ``OVERSEER_T10_04_CLEAR_DEFERRED_NO_LOCAL_ONLY_2026_09_08``.
    """
    try:
        import peer_last_cycle_poison as lc_poison
        import peer_transcript as transcript
    except Exception:  # noqa: BLE001
        return False
    state = transcript.load_state()
    lc = state.get("last_cycle")
    if not isinstance(lc, dict) or not lc:
        return False
    fixed = lc_poison.sanitize_last_cycle(lc)
    if fixed is not None and fixed is not lc:
        state["last_cycle"] = fixed
        lc = fixed
        transcript.save_state(state)
    ft = str(lc.get("failure_type") or "").strip()
    if ft != "deferred":
        return False
    # Poison pair must not be "cleared" into green+deferred — sanitize first.
    if lc.get("verify_ok") is True:
        return False
    lc["verify_ok"] = True
    lc.pop("failure_type", None)
    prev_note = str(lc.get("note") or "").strip()
    cleared_note = "verify-gate cleared deferred soft-skip"
    lc["note"] = (
        f"{prev_note}; {cleared_note}" if prev_note and cleared_note not in prev_note else cleared_note
    )
    state["last_cycle"] = lc
    transcript.save_state(state)
    log_fn("verify: cleared deferred soft-skip stamp after ready")
    return True


def run_verify_gate(*, log_fn=print, retry_once: bool = True) -> tuple[int, str | None, int]:
    """Post-agent verify with optional single retry before hold.

    Returns (failure_count, failure_type, retries_used).
    """
    failures, failure_type = run_verify_commands(log_fn=log_fn)
    if failures == -1 and failure_type == "deferred":
        return -1, "deferred", 0
    retries_used = 0
    if failures and retry_once:
        log_fn(
            f"verify: retry once after {failures} failure(s)"
            + (f" [{failure_type}]" if failure_type else "")
        )
        retries_used = 1
        failures, failure_type = run_verify_commands(log_fn=log_fn)
    # Needle: OVERSEER_VERIFY_CLEAR_DEFERRED_2026_09_07
    if failures == 0:
        _clear_deferred_stamp_after_ready(log_fn=log_fn)
    return failures, failure_type, retries_used


def run_local_cycle(*, quick: bool, log_fn=print) -> tuple[int, bool]:
    """Local-only peer loop tick — no LLM, no clipboard, no UI."""
    # Use module ``po`` alias (lazy) so tests can patch ``rpt.po.build_plan``.
    plan = po.build_plan(quick=quick, loop=True)
    live = auto.measure_live_state(quick=quick)

    if plan.stop:
        # Idle ≠ verify pass — never ready=True without run_verify_commands.
        # Prior path returned ready on metrics alone → auto_commit_after_verify.
        log_fn(f"local: idle — {plan.stop_reason}")
        return 0, False

    log_fn(f"local: queue ({len(plan.tasks)} tasks) — verify gate")
    failures, failure_type = run_verify_commands(log_fn=log_fn)
    # deferred (-1) is soft skip — swarm/lock — not a verify FAIL (heal-all [FAIL] storm).
    if failures == -1 and failure_type == "deferred":
        log_fn("local: verify deferred — swarm/lock; not a gate failure")
        return 0, False
    if failures:
        kind = f" [{failure_type}]" if failure_type else ""
        log_fn(f"local: verify had {failures} failure(s){kind}")
        return 1, False

    # ready iff verify gate passed — not git_clean (notes-dirty digest ticks
    # must not stamp verify_ok=False / dispatch-held theater).
    # OVERSEER_LAND_2026_09_04 — hub-protect needle: ready≠git_clean
    # Needle: OVERSEER_READY_IGNORE_GIT_CLEAN_2026_09_04
    # OVERSEER_VERIFY_CLEAR_DEFERRED_2026_09_07 — ready clears soft deferred stamp
    _clear_deferred_stamp_after_ready(log_fn=log_fn)
    return 0, True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scripted peer verify tasks")
    parser.add_argument("--quick", action="store_true", help="Cache tests/RSS until git changes")
    parser.add_argument("--json", action="store_true", help="Print plan JSON only")
    args = parser.parse_args()

    if args.json:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "peer_orchestrate.py"), "--json", "--loop"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60.0,
            check=False,
        )
        print(proc.stdout or proc.stderr or "")
        return proc.returncode

    rc, _ready = run_local_cycle(quick=args.quick)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
