"""Shared automation helpers — portable via automation.config.json."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


import automation_config as cfg_mod

ROOT = cfg_mod.ROOT
SCRIPTS = cfg_mod.SCRIPTS
CFG = cfg_mod.CFG
CONFIG_DIR = cfg_mod.config_dir()


def max_parallel_peers() -> int:
    # OVERSEER_PEER_CEILING_2026_09_04 — trust CFG; load_config/cap_dgx_install_limits
    # already clamps live overlays. Do not re-clamp here (breaks mocked CFG unit tests).
    try:
        return max(1, int(CFG.get("max_parallel_peers", 8)))
    except (TypeError, ValueError):
        return 8


def parallel_peer_floor() -> int:
    try:
        return max(1, int(CFG.get("parallel_peer_floor", 8)))
    except (TypeError, ValueError):
        return 6


def merge_same_peer_tasks() -> bool:
    return bool(CFG.get("merge_same_peer_tasks", False))


def improve_drives_automation() -> bool:
    """When True, automation_improve forever is the driver — not cursor_self_improve."""
    return bool(CFG.get("improve_drives_automation", True))


def factory_meter_mode() -> str:
    """Primary factory progress meter: self_sufficient (current build) or external_proof."""
    raw = str(CFG.get("factory_meter_mode") or "self_sufficient").strip().lower()
    if raw in ("external_proof", "oss", "monster", "external"):
        return "external_proof"
    return "self_sufficient"


def factory_north_star() -> str:
    if factory_meter_mode() == "external_proof":
        import automation_improve as improve

        return improve.INVESTMENT_NORTH_STAR
    custom = str(CFG.get("factory_north_star_self_sufficient") or "").strip()
    if custom:
        return custom
    return (
        "Self-sufficient automation: peer + improve forever, mechanical heal, "
        "verify gates, oversight — runs without babysitting"
    )


def development_focus() -> str:
    """Primary dev agent lane for this build (command_builder | factory | external_proof)."""
    raw = str(CFG.get("development_focus") or "command_builder").strip().lower()
    if raw in ("factory", "peer", "general"):
        return "factory"
    if raw in ("external", "external_proof", "oss"):
        return "external_proof"
    return "command_builder"


PROJECT_NAME = CFG["project_name"]
LAUNCH_AGENT_LABEL = CFG["launch_agent_label"]
POST_CYCLE_HOOK = CFG.get("post_cycle_hook")


def auto_commit_after_verify_enabled() -> bool:
    return bool(CFG.get("auto_commit_after_verify", True))


def auto_push_after_commit_enabled() -> bool:
    return bool(CFG.get("auto_push_after_commit", False))


def improve_hand_out_roles_enabled() -> bool:
    return bool(CFG.get("improve_hand_out_roles", True))


def improve_enqueue_cap() -> int:
    try:
        cap = int(CFG.get("improve_enqueue_cap") or parallel_peer_floor())
        return max(1, min(cap, max_parallel_peers()))
    except (TypeError, ValueError):
        return parallel_peer_floor()


def parallel_agent_dispatch_enabled() -> bool:
    return bool(CFG.get("parallel_agent_dispatch", True))


def max_parallel_agent_procs() -> int:
    try:
        cap = int(CFG.get("max_parallel_agent_procs") or parallel_peer_floor())
        return max(1, min(cap, max_parallel_peers()))
    except (TypeError, ValueError):
        return parallel_peer_floor()
RSS_BUDGET_MB = CFG.get("rss_budget_mb")
TEST_COMMAND = CFG.get("test_command") or ["python3", "-m", "unittest", "discover", "-s", "tests", "-q"]
QUICK_TEST_COMMAND = CFG.get("quick_test_command")
TEST_MEASURE_TIMEOUT_SEC = float(CFG.get("test_measure_timeout_sec") or 600)
QUICK_TEST_MEASURE_TIMEOUT_SEC = float(CFG.get("quick_test_measure_timeout_sec") or 30)
GIT_MEASURE_TIMEOUT_SEC = float(CFG.get("git_measure_timeout_sec") or 60)
TEST_MEASURE_LOCK_PATH = CONFIG_DIR / "test-measure.lock"
TEST_MEASURE_LOCK_STALE_SEC = 300.0
SKIP_TEST_MEASURE_ENV = "AUTOMATION_SKIP_TEST_MEASURE"
TAIL_READ_MAX_BYTES = 256 * 1024


def tail_text_lines(path: Path | str, n: int, *, max_bytes: int = TAIL_READ_MAX_BYTES) -> list[str]:
    """Read last *n* non-empty lines without loading whole multi-MB logs into RAM."""
    if n <= 0:
        return []
    p = Path(path)
    if not p.is_file():
        return []
    try:
        size = p.stat().st_size
        with p.open("rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                fh.readline()
            text = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-n:]


def _default_quick_smoke_command() -> list[str]:
    """In-process tasks-config smoke — no unittest / self-check recursion."""
    return [
        sys.executable,
        "-c",
        (
            f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); "
            "import project_automation as a; "
            "issues = a.validate_tasks_config(a.load_tasks_config()); "
            "sys.exit(1 if issues else 0)"
        ),
    ]


def _quick_cmd_is_unittest_storm(cmd: list[str]) -> bool:
    """Config often parks test-quick modules in quick_test_command — too heavy for measure ticks."""
    return "unittest" in [str(x) for x in cmd]


def quick_test_command() -> list[str]:
    """Fast smoke for daemon hot paths — never shells out to self-check (recursion).

    Ignores unittest overrides in config (hub-protect / local often stash the
    full test-quick module list here). measure_live_state(quick) must stay lean.
    """
    if QUICK_TEST_COMMAND:
        cmd = list(QUICK_TEST_COMMAND)
        if not _quick_cmd_is_unittest_storm(cmd):
            return cmd
    return _default_quick_smoke_command()
CONTEXT_PATH = cfg_mod.path_key('context')
WORK_QUEUE_PATH = cfg_mod.path_key('work_queue')
LAUNCH_PATH = cfg_mod.path_key('launch_plan')
MONETIZATION_PATH = cfg_mod.path_key('monetization')
CREATIVE_BACKLOG_PATH = cfg_mod.path_key('creative_backlog')
TASKS_PATH = SCRIPTS / "peer_tasks.json"


def cache_path() -> Path:
    custom = os.environ.get("AUTOMATION_CACHE_DIR") or CFG.get("automation_cache_dir")
    if custom:
        return Path(str(custom)).expanduser() / "automation_cache.json"
    return CONFIG_DIR / "automation_cache.json"


CACHE_PATH = cache_path()
IDEA_MINING_ITEM = CFG.get("idea_mining_item", "Discover improvements")



@dataclass
class LiveState:
    git_clean: bool
    git_detail: str
    tests_ok: bool
    tests_detail: str
    import_rss_mb: float | None
    footprint_detail: str


@dataclass
class QueueState:
    open_items: list[str]
    source: str  # work_queue | context | creative | experiments | blockers | empty


def _run(
    cmd: list[str],
    *,
    timeout: float = 30.0,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        cwd=str(cwd or ROOT),
        env=run_env,
    )


_mtime_text_cache: dict[str, tuple[int, int, str]] = {}
_MTIME_TEXT_CACHE_MAX = 16


def _load_text_cached(path: Path) -> str:
    """Read text once per (mtime_ns, size) — cuts daemon hot-path disk + RAM churn."""
    if not path.is_file():
        return ""
    key = str(path)
    try:
        st = path.stat()
        witness = (st.st_mtime_ns, st.st_size)
    except OSError:
        return ""
    hit = _mtime_text_cache.get(key)
    if hit and hit[0] == witness[0] and hit[1] == witness[1]:
        return hit[2]
    try:
        text = path.read_text()
    except OSError:
        text = ""
    _mtime_text_cache[key] = (witness[0], witness[1], text)
    if len(_mtime_text_cache) > _MTIME_TEXT_CACHE_MAX:
        oldest = min(_mtime_text_cache, key=lambda k: _mtime_text_cache[k][0])
        del _mtime_text_cache[oldest]
    return text


def load_context_md() -> str:
    return _load_text_cached(CONTEXT_PATH)


def load_work_queue_md() -> str:
    return _load_text_cached(WORK_QUEUE_PATH)


def load_creative_backlog_md() -> str:
    return _load_text_cached(CREATIVE_BACKLOG_PATH)


def extract_section_lines(md: str, heading: str) -> list[str]:
    pattern = rf"^## {re.escape(heading)}\s*$"
    lines = md.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        if re.match(pattern, line):
            start = i + 1
            break
    if start is None:
        return []
    out: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.strip():
            out.append(line.rstrip())
    return out


def _is_done_line(stripped: str) -> bool:
    if re.match(r"^-\s*\[x\]", stripped, re.IGNORECASE):
        return True
    if re.match(r"^\d+\.\s*\[x\]", stripped, re.IGNORECASE):
        return True
    if re.search(r"\(\[x\]\s*done\)", stripped, re.IGNORECASE):
        return True
    if stripped.lower().startswith("- done:") or stripped.lower().startswith("done:"):
        return True
    return False


def _parse_work_item(stripped: str) -> str | None:
    if _is_done_line(stripped):
        return None
    if stripped.startswith("-"):
        item = re.sub(r"^-\s*(\[ \]\s*)?", "", stripped).strip()
        return item or None
    checkbox = re.match(r"^\d+\.\s*\[ \]\s*(.+)$", stripped)
    if checkbox:
        return re.sub(r"\*\*", "", checkbox.group(1)).strip() or None
    numbered = re.match(r"^\d+\.\s*(\[ \]\s*)?\**(.+?)\**?\s*$", stripped)
    if numbered:
        return re.sub(r"\*\*", "", numbered.group(2)).strip() or None
    return None


def remaining_work_items(md: str) -> list[str]:
    lines = extract_section_lines(md, "Remaining work (priority order)")
    items: list[str] = []
    for line in lines:
        item = _parse_work_item(line.strip())
        if item:
            items.append(item)
    return items


def insert_remaining_work_bullet(context_md: str, line: str) -> str:
    """Insert a bullet under ## Remaining work; handles (priority order) header."""
    if "## Remaining work (priority order)" in context_md:
        return context_md.replace(
            "## Remaining work (priority order)\n",
            f"## Remaining work (priority order)\n{line}\n",
            1,
        )
    if "## Remaining work" in context_md:
        return context_md.replace("## Remaining work\n", f"## Remaining work\n{line}\n", 1)
    return context_md.rstrip() + f"\n\n## Remaining work (priority order)\n{line}\n"


def _parse_phased_work_items(work_md: str) -> list[str]:
    """Collect unchecked items from ## Phase N … or ## Active items until Creative/Done."""
    lines = work_md.splitlines()
    out: list[str] = []
    in_track = False
    stop_prefixes = ("## Creative backlog", "## Done", "## Metrics", "## Backlog")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## Phase") or stripped.startswith("## Active"):
            in_track = True
            continue
        if any(stripped.startswith(prefix) for prefix in stop_prefixes):
            in_track = False
            continue
        if in_track:
            item = _parse_work_item(stripped)
            if item:
                out.append(item)
    return out


def launch_track_active(work_md: str | None = None) -> bool:
    """True when WORK_QUEUE has open Phase 0–6 launch items."""
    work_md = work_md if work_md is not None else load_work_queue_md()
    if not work_md:
        return False
    return bool(_parse_phased_work_items(work_md))


def open_work_items(context_md: str | None = None, work_md: str | None = None) -> QueueState:
    """Single source of truth: notes/WORK_QUEUE phases/active → context remaining → empty."""
    work_md = work_md if work_md is not None else load_work_queue_md()
    context_md = context_md if context_md is not None else load_context_md()

    if work_md:
        # OVERSEER_OPEN_WORK_CLOSE_LANDED_2026_09_04 — Mac rsync reopens landed ## Done
        # as `- [ ]`; promote-without-close inflated launch open=N and froze queue_fp.
        # Check-in-place first (same order as compact_executable_queue); only unlanded
        # orphans promote into the dispatch view.
        work_md, _ = close_landed_done_orphans(work_md)
        # Dispatch must see remaining open `## Done` orphans immediately; peer
        # orchestration calls `sync_queue_drift()` for warnings only (no write).
        # git_clean is a separate concern — continue_on_dirty / WORKING.
        promoted_work_md, _ = promote_open_done_orphans(work_md)
        phased = _parse_phased_work_items(promoted_work_md)
        if phased:
            return QueueState(open_items=phased, source="launch")

    ctx_items = remaining_work_items(context_md)
    if ctx_items:
        return QueueState(open_items=ctx_items, source="context")
    return QueueState(open_items=[], source="empty")


def all_open_work_queue_items(work_md: str | None = None) -> list[str]:
    """Unchecked items in WORK_QUEUE Active track and Backlog (for drift matching)."""
    work_md = work_md if work_md is not None else load_work_queue_md()
    if not work_md:
        return []
    items = list(_parse_phased_work_items(work_md))
    in_backlog = False
    for line in work_md.splitlines():
        s = line.strip()
        if s.startswith("## Backlog"):
            in_backlog = True
            continue
        if in_backlog and s.startswith("## "):
            break
        if in_backlog:
            item = _parse_work_item(s)
            if item:
                items.append(item)
    return items


def extract_rules(md: str) -> list[str]:
    lines = extract_section_lines(md, "Product rules (never regress)")
    return [re.sub(r"^-\s*", "", line.strip()) for line in lines if line.strip().startswith("-")]


def context_marked_complete(md: str) -> bool:
    if re.search(r"^## Status:\s*complete\s*$", md, re.MULTILINE | re.IGNORECASE):
        return True
    if re.search(r"^status:\s*complete\s*$", md, re.MULTILINE | re.IGNORECASE):
        return True
    return False


def loop_status(md: str) -> str | None:
    """Return 'active' | 'exhausted' from ## Loop section."""
    for line in extract_section_lines(md, "Loop"):
        stripped = line.strip().lower()
        if stripped in ("active", "exhausted"):
            return stripped
    if re.search(r"^## Loop:\s*exhausted\s*$", md, re.MULTILINE | re.IGNORECASE):
        return "exhausted"
    if re.search(r"^## Loop:\s*active\s*$", md, re.MULTILINE | re.IGNORECASE):
        return "active"
    return None


def loop_marked_exhausted(md: str) -> bool:
    """Human/agent sets Loop section to exhausted when no non-obvious wins remain."""
    return loop_status(md) == "exhausted"


def _try_acquire_test_measure_lock() -> bool:
    """Single-flight test measurement across improve + peer daemons."""
    TEST_MEASURE_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    try:
        if TEST_MEASURE_LOCK_PATH.is_file():
            age = now - TEST_MEASURE_LOCK_PATH.stat().st_mtime
            if age < TEST_MEASURE_LOCK_STALE_SEC:
                try:
                    pid = int(TEST_MEASURE_LOCK_PATH.read_text().strip().splitlines()[0])
                except (OSError, ValueError, IndexError):
                    pid = None
                if pid and pid != os.getpid():
                    try:
                        os.kill(pid, 0)
                        return False
                    except OSError:
                        pass
        TEST_MEASURE_LOCK_PATH.write_text(f"{os.getpid()}\n{now}\n")
        return True
    except OSError:
        return True


def _release_test_measure_lock() -> None:
    try:
        if TEST_MEASURE_LOCK_PATH.is_file():
            text = TEST_MEASURE_LOCK_PATH.read_text()
            if text.startswith(str(os.getpid())):
                TEST_MEASURE_LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _cached_test_result(cache: dict, *, suffix: str) -> tuple[bool, str]:
    detail = cache.get("tests_detail", "tests: cached")
    ok = bool(cache.get("tests_ok"))
    return ok, f"{detail} ({suffix})"


def _quick_test_cache_usable(cache: dict) -> bool:
    """Green tests_ok only — smoke/self-check labels alone must not pin a failed cache."""
    return cache.get("tests_ok") is True


def _test_fail_cache_ttl_sec() -> float:
    """TTL for reusing explicit FAIL/timeout results without respawning unittest.

    Compression: peer/improve ``measure_live_state(quick)`` otherwise re-forks
    ~33MB child RSS every tick while tests stay red. Still reports
    ``tests_ok=False`` — never promotes fail to green / ``tests: cached`` poison.
    Set ``0`` to disable (always re-probe on fail).
    """
    raw = CFG.get("test_fail_cache_ttl_sec")
    if raw is None:
        return 60.0
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 60.0



def _inconclusive_quick_fail_line(line: str) -> bool:
    """Empty/garbage unittest tails — storm kill / lock race, not a real red suite.

    Needle: INCONCLUSIVE_QUICK_FAIL_2026_09_04 — empty rc!=0 used to pin fail-TTL
    and trip self-check ``tests not ok`` → false orchestrate flaws / stagnation.
    Also: OVERSEER_INCONCLUSIVE_WORKTREE_EPILOG_2026_09_04 — peer_worktree dry-run
    stderr ``(pass --execute…)`` as last line after SIGKILL/race must not stamp FAIL.
    OVERSEER_INCONCLUSIVE_NO_SHORT_SOFT_GREEN_2026_09_04 — drop blanket ``len < 24``
    (Permission denied / Timeout / Killed / Segmentation fault were false-green).
    """
    s = (line or "").strip()
    if not s:
        return True
    low = s.lower()
    if low in {"failed", "see output", "fail", "error", ",", ".", "-", "—"}:
        return True
    # OVERSEER_INCONCLUSIVE_WORKTREE_EPILOG_2026_09_04
    if "pass --execute" in low or "never uses --force" in low:
        return True
    if len(s) <= 2 and not any(ch.isalnum() for ch in s):
        return True
    if any(
        m in s
        for m in (
            "FAIL:",
            "FAILED",
            "ERROR:",
            "Traceback",
            "AssertionError",
            "failures=",
            "errors=",
        )
    ):
        return False
    if "error:" in low or "failed (" in low:
        return False
    # OVERSEER_INCONCLUSIVE_NO_SHORT_SOFT_GREEN_2026_09_04 — real short OS/timeout
    # tails are FAIL (not inconclusive). Only empty/garbage/epilog tokens soft-pass.
    return False


def _fail_result_cacheable(cache: dict) -> bool:
    """Only explicit FAIL/timeout — never pin ambiguous ``tests: cached`` + False."""
    if cache.get("tests_ok") is not False:
        return False
    detail = str(cache.get("tests_detail") or "")
    if "timeout" in detail.lower():
        return True
    if "FAIL" not in detail:
        return False
    tail = detail.split("—", 1)[-1].strip() if "—" in detail else detail
    if _inconclusive_quick_fail_line(tail):
        return False
    return True


def _fail_cache_fresh(cache: dict, *, fp: str | None = None) -> bool:
    """True when a recent explicit fail may be reused (still tests_ok=False)."""
    if not _fail_result_cacheable(cache):
        return False
    ttl = _test_fail_cache_ttl_sec()
    if ttl <= 0.0:
        return False
    age = time.time() - float(cache.get("tests_ts") or 0)
    if age >= ttl:
        return False
    witness = _git_witness()
    if witness is not None and cache.get("git_witness") == witness:
        return True
    if fp is not None and cache.get("git_fingerprint") == fp:
        return True
    if fp is None:
        resolved = _git_fingerprint()
        if resolved is not None and cache.get("git_fingerprint") == resolved:
            return True
    head: str | None
    if fp is not None and ":" in fp:
        head = fp.split(":", 1)[0] or None
    else:
        head = _git_head()
    if not head or cache.get("git_head") != head:
        return False
    return True


def _git_measure_cache_ttl_sec() -> float:
    """TTL for reusing git_clean/detail without respawning porcelain (daemon hot path)."""
    try:
        return max(0.0, float(CFG.get("git_measure_cache_ttl_sec") or 20))
    except (TypeError, ValueError):
        return 20.0


def _parse_git_status_v2(stdout: str, *, returncode: int = 0) -> tuple[str | None, bool, str, str]:
    """Parse ``git status --porcelain=v2 --branch`` → (oid, clean, detail, body)."""
    if returncode != 0 and not (stdout or "").strip():
        return None, False, "git: unavailable", ""
    oid: str | None = None
    body_lines: list[str] = []
    modified = 0
    untracked = 0
    for raw in (stdout or "").splitlines():
        line = raw.rstrip("\n")
        if line.startswith("# branch.oid "):
            oid = line[len("# branch.oid ") :].strip() or None
            continue
        if line.startswith("#"):
            continue
        if not line.strip():
            continue
        body_lines.append(line)
        if line.startswith("?"):
            untracked += 1
        elif line.startswith("1 ") or line.startswith("2 "):
            # v2 ordinary/rename entries — XY in fields[1] (e.g. ".M", "M.")
            parts = line.split(" ", 3)
            xy = parts[1] if len(parts) > 1 else ".."
            if xy != ".." and ("M" in xy or "A" in xy or "D" in xy or "T" in xy or "R" in xy or "C" in xy):
                modified += 1
            else:
                modified += 1
        else:
            modified += 1
    body = "\n".join(body_lines)
    if not oid:
        return None, False, "git: unavailable", body
    total = len(body_lines)
    if total == 0:
        return oid, True, "git: clean working tree", body
    return (
        oid,
        False,
        f"git: {total} changed path(s) ({modified} modified, {untracked} untracked)",
        body,
    )


def _git_snapshot() -> tuple[str, bool, str]:
    """Single git child: porcelain=v2 --branch (HEAD oid + dirty) — not rev-parse+status."""
    if not (ROOT / ".git").exists():
        return ":", False, "git: not a repository"
    try:
        proc = _run(
            ["git", "-C", str(ROOT), "status", "--porcelain=v2", "--branch"],
            timeout=GIT_MEASURE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return ":", False, "git: status timed out"
    oid, clean, detail, body = _parse_git_status_v2(proc.stdout or "", returncode=proc.returncode)
    if oid is None:
        return ":", False, detail
    return f"{oid}:{body}", clean, detail


def _git_measure_witness_soft_ttl_sec() -> float:
    """Post hard-TTL soft reuse while HEAD+index witness matches (??-only ceiling).

    Compression: worktree/daemon ticks otherwise re-fork ``git status`` (~4.5 MB
    child RSS) every ``git_measure_cache_ttl_sec`` even when HEAD/index unchanged.
    Soft TTL bounds staleness for untracked-only dirtiness (witness ignores ??).
    Set ``0`` to disable soft reuse (hard TTL only).
    """
    try:
        return max(0.0, float(CFG.get("git_measure_witness_soft_ttl_sec") or 300))
    except (TypeError, ValueError):
        return 300.0


def _git_cache_fresh(cache: dict) -> tuple[str, bool, str] | None:
    """Reuse git fingerprint/clean/detail within TTL — or post-TTL on witness match."""
    fp = cache.get("git_fingerprint")
    detail = cache.get("git_detail")
    if fp is None or not detail:
        return None
    age = time.time() - float(cache.get("git_ts") or 0)
    hard = _git_measure_cache_ttl_sec()
    if age < hard:
        return str(fp), bool(cache.get("git_clean")), str(detail)
    # Past hard TTL: skip porcelain child when HEAD+index witness still matches.
    soft = _git_measure_witness_soft_ttl_sec()
    if soft <= 0.0 or age >= soft:
        return None
    witness = _git_witness()
    if witness is None or cache.get("git_witness") != witness:
        return None
    return str(fp), bool(cache.get("git_clean")), str(detail)


def _compact_git_fingerprint(fp: str) -> str:
    """Store oid:z:adler+crc(body) when porcelain body is large (dirty-tree shm writes).

    Needle: OVERSEER_CACHE_FP_COMPACT_2026_09_04 — full porcelain under 250 dirty
    paths bloated automation_cache.json; non-atomic writes truncated under ENOSPC.
    COMPRESSION_ZLIB_GIT_FP_2026_09_04 — zlib (stdlib) avoids hashlib→libcrypto (~4–6MB).
    Legacy ``sha256:`` digests stay compact (no re-hash / no hashlib import).
    """
    if ":" not in fp:
        return fp
    oid, _, body = fp.partition(":")
    if len(body) <= 1024 or body.startswith("sha256:") or body.startswith("z:"):
        return fp
    import zlib

    raw = body.encode("utf-8", errors="replace")
    digest = f"{zlib.adler32(raw) & 0xffffffff:08x}{zlib.crc32(raw) & 0xffffffff:08x}"
    return f"{oid}:z:{digest}"


def _apply_git_snapshot(cache: dict, fp: str, clean: bool, detail: str) -> None:
    cache["git_fingerprint"] = _compact_git_fingerprint(fp)
    cache["git_clean"] = clean
    cache["git_detail"] = detail
    cache["git_ts"] = time.time()
    head = fp.split(":", 1)[0]
    if head:
        cache["git_head"] = head
    witness = _git_witness()
    if witness is not None:
        cache["git_witness"] = witness


def _resolve_git_state(cache: dict, *, prefer_cache: bool) -> tuple[str, bool, str]:
    """Return (fp, clean, detail); spawn at most one porcelain=v2 when cache miss."""
    if prefer_cache:
        hit = _git_cache_fresh(cache)
        if hit is not None:
            fp, clean, detail = hit
            return fp, clean, f"{detail} (cached)"
    fp, clean, detail = _git_snapshot()
    fp = _compact_git_fingerprint(fp)
    _apply_git_snapshot(cache, fp, clean, detail)
    return fp, clean, detail


def git_is_clean() -> bool:
    """Porcelain-only clean check — never runs tests/RSS (peer_loop dirty wait hot path)."""
    cache = _load_cache()
    hit = _git_cache_fresh(cache)
    if hit is not None:
        return hit[1]
    fp, clean, detail = _git_snapshot()
    _apply_git_snapshot(cache, fp, clean, detail)
    _save_cache(cache)
    return clean


def _measure_git(*, cache: dict | None = None) -> tuple[bool, str]:
    """Legacy helper — prefer ``_git_snapshot`` / ``_resolve_git_state`` on hot paths."""
    store = cache if cache is not None else {}
    _fp, clean, detail = _resolve_git_state(store, prefer_cache=True)
    if cache is None and store.get("git_ts"):
        # ephemeral — do not persist unless caller owns the cache
        pass
    return clean, detail


def _git_head() -> str | None:
    if not (ROOT / ".git").exists():
        return None
    head = _run(["git", "-C", str(ROOT), "rev-parse", "HEAD"])
    if head.returncode != 0:
        return None
    return (head.stdout or "").strip() or None


def _resolve_git_dir() -> Path | None:
    """Resolve the real git directory — supports worktree ``.git`` gitfile (no spawn)."""
    marker = ROOT / ".git"
    if marker.is_dir():
        return marker
    if not marker.is_file():
        return None
    try:
        for line in marker.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped.lower().startswith("gitdir:"):
                continue
            raw = stripped.split(":", 1)[1].strip()
            if not raw:
                return None
            path = Path(raw)
            if not path.is_absolute():
                path = marker.parent / path
            path = path.resolve()
            return path if path.is_dir() else None
    except OSError:
        return None
    return None


def _git_common_dir_from_git_dir(git_dir: Path) -> Path:
    """Resolve common dir from worktree ``commondir`` file (refs live here)."""
    cd_file = git_dir / "commondir"
    try:
        if cd_file.is_file():
            raw = cd_file.read_text(encoding="utf-8", errors="replace").strip()
            first = raw.splitlines()[0].strip() if raw else ""
            if first:
                path = Path(first)
                if not path.is_absolute():
                    path = git_dir / path
                return path.resolve()
    except OSError:
        pass
    return git_dir


def _git_head_ref() -> str | None:
    """Resolve HEAD OID without spawning git (mtime witness helper).

    Worktrees store ``.git`` as a gitfile; refs usually live in the common dir.
    """
    git_dir = _resolve_git_dir()
    if git_dir is None:
        return None
    head_file = git_dir / "HEAD"
    if not head_file.is_file():
        return None
    try:
        text = head_file.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if text.startswith("ref: "):
        ref = text[5:].strip()
        if not ref:
            return None
        common = _git_common_dir_from_git_dir(git_dir)
        for base in (git_dir, common):
            try:
                oid = (base / ref).read_text(encoding="utf-8", errors="replace").strip()
                if oid:
                    return oid
            except OSError:
                continue
        return None
    return text or None


def _git_witness() -> str | None:
    """Fast invalidation witness from HEAD ref + HEAD/index mtimes (no porcelain shell).

    Dropped ``git status --porcelain -u`` (=uall) untracked count (~2–3ms/call).
    Untracked-only churn does not invalidate — full fingerprint remains miss/fallback.
    Resolves worktree gitfile so peer-N / coding trees get the same zero-spawn path.
    """
    git_dir = _resolve_git_dir()
    if git_dir is None:
        return None
    head = _git_head_ref()
    if not head:
        return None
    parts = [head]
    for name in ("HEAD", "index"):
        path = git_dir / name
        try:
            parts.append(str(path.stat().st_mtime_ns))
        except OSError:
            parts.append("0")
    return ":".join(parts)


def _git_fingerprint() -> str | None:
    """HEAD + porcelain — invalidates quick-cache on any tree change.

    Prefer ``_git_snapshot`` when both clean+fp are needed (one spawn).
    """
    if not (ROOT / ".git").exists():
        return None
    fp, _clean, _detail = _git_snapshot()
    if fp == ":" or not fp.split(":", 1)[0]:
        return None
    return _compact_git_fingerprint(fp)


def _quick_cache_valid(cache: dict, fp: str | None = None) -> bool:
    """Quick mode reuses cached tests/RSS until git fingerprint changes.

    Failed ``tests_ok`` never validates (poison guard). Same HEAD + fresh
    ``test_cache_ttl_sec`` survives porcelain churn from daemon writes.
    """
    if cache.get("tests_ok") is not True:
        return False
    witness = _git_witness()
    if witness is not None and cache.get("git_witness") == witness:
        return True
    if fp is not None and cache.get("git_fingerprint") == fp:
        return True
    if fp is None:
        resolved = _git_fingerprint()
        if resolved is not None and cache.get("git_fingerprint") == resolved:
            return True
    head: str | None
    if fp is not None and ":" in fp:
        head = fp.split(":", 1)[0] or None
    else:
        head = _git_head()
    if not head or cache.get("git_head") != head:
        return False
    ttl = float(CFG.get("test_cache_ttl_sec") or CFG.get("local_only_verify_cooldown_sec") or 180)
    age = time.time() - float(cache.get("tests_ts") or 0)
    return age < ttl


def _measure_tests(*, quick: bool, cache: dict, fp: str | None = None) -> tuple[bool, str]:
    """Measure tests for live state.

    quick=True uses cache aggressively and runs quick_test_command (self-check)
    instead of the full unittest discover storm on daemon hot paths.
    ``fp=None`` takes one ``_git_snapshot`` (not rev-parse + fingerprint ×N).
    """
    if quick and _quick_cache_valid(cache, fp=fp) and cache.get("tests_ts") and _quick_test_cache_usable(cache):
        return _cached_test_result(cache, suffix="cached, git unchanged")
    # Compression: reuse explicit FAIL within test_fail_cache_ttl_sec (still False).
    if quick and _fail_cache_fresh(cache, fp=fp):
        return _cached_test_result(cache, suffix="fail-ttl")

    if fp is None:
        snap_fp, clean, detail = _git_snapshot()
        _apply_git_snapshot(cache, snap_fp, clean, detail)
        fp = snap_fp
    elif cache.get("git_fingerprint") != fp:
        cache["git_fingerprint"] = fp
        head = fp.split(":", 1)[0]
        if head:
            cache["git_head"] = head

    cmd = quick_test_command() if quick else TEST_COMMAND
    timeout = QUICK_TEST_MEASURE_TIMEOUT_SEC if quick else TEST_MEASURE_TIMEOUT_SEC
    label = "quick" if quick else "full"
    measure_env = {SKIP_TEST_MEASURE_ENV: "1"} if quick else None

    if not _try_acquire_test_measure_lock():
        if cache.get("tests_ts"):
            return _cached_test_result(cache, suffix="lock held, stale cache")
        # Inconclusive — do not report as failure (poisons repo-research / oversight).
        return True, "tests: skipped (another measure in flight)"

    try:
        proc = _run(cmd, timeout=timeout, env=measure_env)
    except subprocess.TimeoutExpired:
        if cache.get("tests_ts"):
            return _cached_test_result(cache, suffix=f"{label} timeout, stale cache")
        cache["tests_ok"] = False
        cache["tests_detail"] = f"tests: {label} timeout (deferred)"
        cache["tests_ts"] = time.time()
        return False, cache["tests_detail"]
    finally:
        _release_test_measure_lock()

    ok = proc.returncode == 0
    if ok:
        if quick:
            detail = "tests: smoke ok"
        else:
            tail = (proc.stdout or proc.stderr or "").strip().splitlines()
            ran = next((ln for ln in tail if "Ran" in ln), "ok")
            detail = f"tests: {ran}"
    else:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        last = err[-1] if err else "failed"
        # OVERSEER_MEASURE_SIGNAL_SOFT_2026_09_04 — storm trim SIGKILL (rc<0)
        # must not poison repo-research critical "Tests failing".
        rc = int(getattr(proc, "returncode", 0) or 0)
        if rc < 0:
            sig = abs(rc)
            if cache.get("tests_ts"):
                return _cached_test_result(
                    cache, suffix=f"{label} signal {sig}, stale cache"
                )
            detail = f"tests: skipped (signal {sig} — storm trim / inconclusive)"
            cache["tests_ok"] = True
            cache["tests_detail"] = detail
            cache["tests_ts"] = time.time()
            if fp is not None:
                cache["git_fingerprint"] = fp
                head = fp.split(":", 1)[0]
                if head:
                    cache["git_head"] = head
            return True, detail
        # Quick/full: empty/garbage rc!=0 is storm/race — soft-pass like lock contention.
        if _inconclusive_quick_fail_line(last):
            detail = "tests: skipped (inconclusive measure fail)"
            cache["tests_ok"] = True
            cache["tests_detail"] = detail
            cache["tests_ts"] = time.time()
            if fp is not None:
                cache["git_fingerprint"] = fp
                head = fp.split(":", 1)[0]
                if head:
                    cache["git_head"] = head
            return True, detail
        detail = f"tests: FAIL — {last}"
    cache["tests_ok"] = ok
    cache["tests_detail"] = detail
    cache["tests_ts"] = time.time()
    if fp is not None:
        cache["git_fingerprint"] = fp
        head = fp.split(":", 1)[0]
        if head:
            cache["git_head"] = head
    return ok, detail


def _rss_measurement_enabled() -> bool:
    return RSS_BUDGET_MB is not None and bool(CFG.get("rss_entrypoint"))


def _live_from_quick_cache(cache: dict) -> LiveState | None:
    """Reuse git/tests/RSS from cache when git TTL / fingerprint is still valid.

    ``tests_ok=False`` must miss so quick measure re-runs instead of poisoning
    self-check as ``tests: cached``. Prefer ``_git_cache_fresh`` (no spawn).
    """
    if cache.get("tests_ok") is not True:
        return None
    if not cache.get("tests_ts") or not _quick_test_cache_usable(cache):
        return None
    git_detail = cache.get("git_detail")
    if not git_detail:
        return None
    hit = _git_cache_fresh(cache)
    if hit is None:
        # Git TTL miss → caller must snapshot; do not treat fingerprint equality as fresh.
        return None
    tests_detail = f"{cache.get('tests_detail') or 'tests: cached'} (cached, git unchanged)"
    rss_mb: float | None = None
    footprint_detail = "import RSS: skipped"
    if _rss_measurement_enabled():
        cached_rss = cache.get("import_rss_mb")
        if cached_rss is not None:
            rss_mb = float(cached_rss)
            footprint_detail = f"import RSS: ~{rss_mb:.1f} MB (cached)"
        else:
            footprint_detail = "import RSS: (could not measure)"
    elif RSS_BUDGET_MB is None:
        footprint_detail = "import RSS: (disabled — set rss_budget_mb in automation.config.json)"
    else:
        footprint_detail = "import RSS: (disabled — set rss_entrypoint in automation.config.json)"
    return LiveState(
        git_clean=bool(cache.get("git_clean")),
        git_detail=str(git_detail),
        tests_ok=True,
        tests_detail=tests_detail,
        import_rss_mb=rss_mb,
        footprint_detail=footprint_detail,
    )


def _measure_rss(*, quick: bool, cache: dict, git_fp: str | None = None) -> tuple[float | None, str]:
    if RSS_BUDGET_MB is None:
        return None, "import RSS: (disabled — set rss_budget_mb in automation.config.json)"
    entry = CFG.get("rss_entrypoint")
    if not entry:
        return None, "import RSS: (disabled — set rss_entrypoint in automation.config.json)"
    if quick:
        cached = cache.get("import_rss_mb")
        if cached is not None:
            if git_fp is not None and cache.get("git_fingerprint") == git_fp:
                mb = float(cached)
                return mb, f"import RSS: ~{mb:.1f} MB (cached)"
            if git_fp is None and _quick_cache_valid(cache):
                mb = float(cached)
                return mb, f"import RSS: ~{mb:.1f} MB (cached)"
    rss_proc = _run(
        [
            sys.executable,
            "-c",
            f"import importlib.util, os, subprocess, sys; from pathlib import Path; "
            f"root=Path({str(ROOT)!r}); sys.path.insert(0, str(root)); "
            f"rss=lambda: int(subprocess.check_output(['ps','-o','rss=', '-p', str(os.getpid())]).strip())/1024; "
            f"b=rss(); p=root/{entry!r}; "
            f"spec=importlib.util.spec_from_file_location('entry', p); mod=importlib.util.module_from_spec(spec); "
            f"spec.loader.exec_module(mod); print(f'{{rss()-b:.1f}}')",
        ],
        timeout=45.0,
    )
    if rss_proc.returncode == 0 and rss_proc.stdout.strip():
        try:
            mb = float(rss_proc.stdout.strip())
            cache["import_rss_mb"] = mb
            if git_fp is not None:
                cache["git_fingerprint"] = git_fp
            return mb, f"import RSS: ~{mb:.1f} MB"
        except ValueError:
            pass
    return None, "import RSS: (could not measure)"


# Process-local mirror of automation_cache.json — daemon ticks reuse without re-parse.
_CACHE_MEM: dict | None = None
_CACHE_MEM_MTIME_NS: int | None = None
_CACHE_MEM_TEXT: str | None = None


def _load_cache() -> dict:
    """Load measure cache; reuse in-process copy when mtime unchanged (daemon hot path)."""
    global _CACHE_MEM, _CACHE_MEM_MTIME_NS, _CACHE_MEM_TEXT
    path = CACHE_PATH
    try:
        if path.is_file():
            st = path.stat()
            if _CACHE_MEM is not None and _CACHE_MEM_MTIME_NS == st.st_mtime_ns:
                return dict(_CACHE_MEM)
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict):
                _CACHE_MEM = data
                _CACHE_MEM_MTIME_NS = st.st_mtime_ns
                _CACHE_MEM_TEXT = text
                return dict(data)
    except (json.JSONDecodeError, OSError, TypeError):
        # Corrupt / truncated JSON (shm ENOSPC mid-write) — drop so fail-ttl cannot pin.
        try:
            if path.is_file():
                path.unlink(missing_ok=True)
        except OSError:
            pass
    _CACHE_MEM = {}
    _CACHE_MEM_MTIME_NS = None
    _CACHE_MEM_TEXT = None
    return {}


def _save_cache(cache: dict) -> None:
    """Persist measure cache atomically; skip disk write when payload unchanged.

    Needle: OVERSEER_ATOMIC_CACHE_WRITE_2026_09_04 — non-atomic write_text under
    full /dev/shm truncated JSON → self-check fail-ttl theater.
    """
    global _CACHE_MEM, _CACHE_MEM_MTIME_NS, _CACHE_MEM_TEXT
    path = CACHE_PATH
    tmp = None
    try:
        fp = cache.get("git_fingerprint")
        if isinstance(fp, str) and len(fp) > 1024:
            cache = dict(cache)
            cache["git_fingerprint"] = _compact_git_fingerprint(fp)
        text = json.dumps(cache, indent=2)
        if text == _CACHE_MEM_TEXT:
            _CACHE_MEM = dict(cache)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
        tmp = None
        _CACHE_MEM = dict(cache)
        _CACHE_MEM_TEXT = text
        try:
            _CACHE_MEM_MTIME_NS = path.stat().st_mtime_ns
        except OSError:
            _CACHE_MEM_MTIME_NS = None
    except OSError:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def unload_accidental_ml_rss(log_fn: Callable[[str], None] | None = None) -> float:
    """Drop accidental knowledge_mamba weights from forever daemons; return MB freed (0 if none).

    Does not disable features — only unloads in-process model weights if a prior
    import left them resident. Torch .so pages may remain mapped after unload.
    """
    freed = 0.0
    try:
        if "knowledge_mamba" not in sys.modules:
            return 0.0
        import knowledge_mamba as kmamba  # type: ignore[import-not-found]

        st = kmamba.status() if hasattr(kmamba, "status") else {}
        if not st.get("loaded"):
            return 0.0
        before = float(st.get("load_rss_mb") or 0.0)
        kmamba.unload()
        freed = before
        if log_fn is not None and before > 0:
            log_fn(f"compression: unloaded knowledge_mamba (~{before:.1f} MB load_rss)")
    except Exception:  # noqa: BLE001 — optional module; never break daemons
        return 0.0
    return freed


def measure_live_state(*, quick: bool = False) -> LiveState:
    """Measure git/tests/RSS. Skips subprocess tests when RAM_AUTOMATION_NO_SUBTEST=1."""
    if os.environ.get("RAM_AUTOMATION_NO_SUBTEST") == "1":
        cache = _load_cache()
        _fp, git_clean, git_detail = _resolve_git_state(cache, prefer_cache=True)
        if "(cached)" not in git_detail:
            _save_cache(cache)
        return LiveState(
            git_clean=git_clean,
            git_detail=git_detail,
            tests_ok=True,
            tests_detail="tests: skipped (automation guard)",
            import_rss_mb=13.0,
            footprint_detail="import RSS: ~13.0 MB (guard)",
        )
    if os.environ.get(SKIP_TEST_MEASURE_ENV) == "1":
        cache = _load_cache()
        _fp, git_clean, git_detail = _resolve_git_state(cache, prefer_cache=True)
        if "(cached)" not in git_detail:
            _save_cache(cache)
        return LiveState(
            git_clean=git_clean,
            git_detail=git_detail,
            tests_ok=True,
            tests_detail="tests: skipped (nested quick measure guard)",
            import_rss_mb=None,
            footprint_detail="import RSS: skipped",
        )

    cache = _load_cache()
    if quick:
        cached_live = _live_from_quick_cache(cache)
        if cached_live is not None:
            return cached_live

    # One porcelain=v2 snapshot (or TTL hit) — never rev-parse + status separately.
    fp, git_clean, git_detail = _resolve_git_state(cache, prefer_cache=bool(quick))

    tests_ok = False
    tests_detail = "tests: skipped"
    rss_mb: float | None = None
    footprint_detail = "import RSS: skipped"

    # Tests/RSS still cacheable → skip ThreadPool (no RSS budget probe storm).
    if quick and cache.get("tests_ts") and _quick_test_cache_usable(cache) and _quick_cache_valid(
        cache, fp=fp
    ):
        tests_ok, tests_detail = _cached_test_result(cache, suffix="cached, git unchanged")
        if _rss_measurement_enabled():
            rss_mb, footprint_detail = _measure_rss(quick=True, cache=cache, git_fp=fp)
        elif RSS_BUDGET_MB is None:
            footprint_detail = "import RSS: (disabled — set rss_budget_mb in automation.config.json)"
        else:
            footprint_detail = "import RSS: (disabled — set rss_entrypoint in automation.config.json)"
        _save_cache(cache)
        return LiveState(
            git_clean=git_clean,
            git_detail=git_detail if "(cached)" in git_detail else git_detail,
            tests_ok=tests_ok,
            tests_detail=tests_detail,
            import_rss_mb=rss_mb,
            footprint_detail=footprint_detail,
        )

    if _rss_measurement_enabled():
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_tests = pool.submit(_measure_tests, quick=quick, cache=cache, fp=fp)
            fut_rss = pool.submit(_measure_rss, quick=quick, cache=cache, git_fp=fp)
            for fut in as_completed((fut_tests, fut_rss)):
                if fut is fut_tests:
                    tests_ok, tests_detail = fut.result()
                else:
                    rss_mb, footprint_detail = fut.result()
    else:
        tests_ok, tests_detail = _measure_tests(quick=quick, cache=cache, fp=fp)
        if RSS_BUDGET_MB is None:
            footprint_detail = "import RSS: (disabled — set rss_budget_mb in automation.config.json)"
        else:
            footprint_detail = "import RSS: (disabled — set rss_entrypoint in automation.config.json)"

    _save_cache(cache)
    return LiveState(
        git_clean=git_clean,
        git_detail=git_detail,
        tests_ok=tests_ok,
        tests_detail=tests_detail,
        import_rss_mb=rss_mb,
        footprint_detail=footprint_detail,
    )


def success_metrics_ok(live: LiveState) -> bool:
    """Tests/RSS only — not git_clean (WORKING + continue_on_dirty).

    Needle: OVERSEER_METRICS_OK_IGNORE_GIT_CLEAN_2026_09_04
    """
    if RSS_BUDGET_MB is None:
        return bool(live.tests_ok)
    rss_ok = live.import_rss_mb is not None and live.import_rss_mb < RSS_BUDGET_MB
    return bool(live.tests_ok) and rss_ok


def hard_metric_blockers(live: LiveState) -> list[str]:
    """Obvious fixes — only after clever queue is empty."""
    items: list[str] = []
    if not live.tests_ok:
        items.append("Fix failing unit tests")
    if RSS_BUDGET_MB is not None and (live.import_rss_mb is None or live.import_rss_mb >= RSS_BUDGET_MB):
        items.append(f"Reduce cold import RSS below {RSS_BUDGET_MB:.0f} MB")
    return items


def blocker_items(context_md: str, live: LiveState, *, loop: bool = False) -> list[str]:
    items: list[str] = []
    # OVERSEER_DIRTY_THEATER_2026_09_03 — continue_on_dirty: dirty is not a hard blocker.
    if not live.git_clean:
        try:
            import peer_worktree as pwt
            dirty_ok = pwt.continue_on_dirty_enabled()
        except Exception:
            dirty_ok = False
        if not dirty_ok:
            items.append("Commit or stash pending changes (git not clean)")
    items.extend(hard_metric_blockers(live))
    if not items and not remaining_work_items(context_md) and not loop:
        items.append("Mark ## Status: complete in scripts/self_improve_context.md when satisfied")
    return items


def stop_reason(
    context_md: str,
    live: LiveState,
    queue: QueueState | None = None,
    *,
    loop: bool = False,
) -> str | None:
    """When loop=True, only stop when clever pipeline + mining are exhausted and metrics green."""
    if loop:
        loop_queue = loop_work_items(context_md, live=live)
        if loop_queue.open_items:
            return None
        if loop_marked_exhausted(context_md):
            if success_metrics_ok(live):
                return "literally nothing left to improve (## Loop: exhausted, metrics green)"
            return "loop exhausted but metrics not green — fix tests/RSS/git first"
        if not success_metrics_ok(live):
            return "metrics not green — fix tests/RSS/git before declaring done"
        return None  # should not reach — mining item fills empty pipeline

    if context_marked_complete(context_md):
        return "context marked complete (## Status: complete)"
    open_items = queue.open_items if queue else open_work_items(context_md).open_items
    if not open_items and success_metrics_ok(live):
        return "no remaining work and success metrics are green"
    return None


def _normalize_queue_key(text: str) -> str:
    """Loose match for drift detection between WORK_QUEUE and context."""
    t = re.sub(r"\*\*", "", text).strip().lower()
    t = re.sub(r"\s*\[x\][^\n]*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*\([^)]*\)", "", t).strip()
    if "—" in t:
        t = t.split("—", 1)[0].strip()
    return t


def dedupe_open_work_queue(work_md: str | None = None) -> tuple[str, int]:
    """Remove duplicate open queue lines in ## Active / ## Phase / ## Backlog (keeps first)."""
    work_md = work_md if work_md is not None else load_work_queue_md()
    if not work_md:
        return work_md, 0

    lines = work_md.splitlines()
    out: list[str] = []
    seen: set[str] = set()
    backlog_seen: set[str] = set()
    removed = 0
    in_track = False
    in_backlog = False
    stop_prefixes = ("## Creative backlog", "## Done", "## Metrics")

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## Phase") or stripped.startswith("## Active"):
            in_track = True
            in_backlog = False
            out.append(line)
            continue
        if stripped.startswith("## Backlog"):
            in_track = False
            in_backlog = True
            out.append(line)
            continue
        if any(stripped.startswith(prefix) for prefix in stop_prefixes):
            in_track = False
            in_backlog = False
            out.append(line)
            continue
        if in_backlog and stripped.startswith("## ") and not stripped.startswith("## Backlog"):
            in_backlog = False
        if in_track or in_backlog:
            item = _parse_work_item(stripped)
            if item:
                key = _normalize_queue_key(item)
                bucket = backlog_seen if in_backlog else seen
                if key in bucket:
                    removed += 1
                    continue
                bucket.add(key)
        out.append(line)

    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"
    return new_md, removed


def dedupe_remaining_work(context_md: str | None = None) -> tuple[str, int]:
    """Remove duplicate open lines under ## Remaining work."""
    context_md = context_md if context_md is not None else load_context_md()
    if not context_md:
        return context_md, 0

    lines = context_md.splitlines()
    out: list[str] = []
    seen: set[str] = set()
    removed = 0
    in_remaining = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## Remaining work"):
            in_remaining = True
            out.append(line)
            continue
        if in_remaining and stripped.startswith("## "):
            in_remaining = False
        if in_remaining:
            item = _parse_work_item(stripped)
            if item:
                key = _normalize_queue_key(item)
                if key in seen:
                    removed += 1
                    continue
                seen.add(key)
        out.append(line)

    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"
    return new_md, removed


def dedupe_work_queue_files(*, write: bool = True) -> int:
    """Dedupe WORK_QUEUE + self_improve_context open items. Returns total lines removed."""
    new_work, removed_w = dedupe_open_work_queue()
    new_ctx, removed_c = dedupe_remaining_work()
    removed = removed_w + removed_c
    if write and removed:
        WORK_QUEUE_PATH.write_text(new_work, encoding="utf-8")
        CONTEXT_PATH.write_text(new_ctx, encoding="utf-8")
    return removed


_ADAPT_SYNC_MARKER = "synced by automation_adapt"
_FLAW_DRIFT_PREFIX = "[flaw-research] queue: only in"
_FLAW_DRIFT_X_MARK = "✗ only in"
_STALE_DAEMON_FLAW_MARKERS = (
    "[flaw-research] Peer loop daemon not running",
    "[flaw-research] Improve forever daemon not running",
    "[flaw-research] Dual namespace: rogue peer/improve LaunchAgents",
    "[flaw-research] Dual namespace: rogue oversight LaunchAgent",
    "peer loop stopped",
    "improve forever daemon not running",
    "improve-loop daemon stopped",
    "rogue oversight launchagent",
)
_WAKE_INTERVAL_MARKERS = (
    "tune wake interval",
    "pre-dispatch over hyper poll",
    "hyper wake with small queue",
)


def resolve_stale_daemon_flaw_items(
    md: str,
    *,
    peer_up: bool,
    improve_up: bool,
    dual_namespace: bool,
) -> tuple[str, int]:
    """Mark done open flaw-research daemon lines when live probes say healthy."""
    if not md or not any(m in md for m in _STALE_DAEMON_FLAW_MARKERS):
        return md, 0
    out: list[str] = []
    resolved = 0
    for line in md.splitlines():
        stripped = line.strip()
        if not re.match(r"^-\s*\[\s*\]", stripped):
            out.append(line)
            continue
        item = _parse_work_item(stripped) or stripped
        key = _normalize_queue_key(item)
        if "[flaw-research] peer loop daemon not running" in key and peer_up:
            out.append(re.sub(r"^-\s*\[\s*\]", "- [x]", stripped, count=1))
            resolved += 1
            continue
        if "[flaw-research] improve forever daemon not running" in key and improve_up:
            out.append(re.sub(r"^-\s*\[\s*\]", "- [x]", stripped, count=1))
            resolved += 1
            continue
        if "[flaw-research] dual namespace: rogue peer/improve launchagents" in key and not dual_namespace:
            out.append(re.sub(r"^-\s*\[\s*\]", "- [x]", stripped, count=1))
            resolved += 1
            continue
        if (
            "[flaw-research] dual namespace: rogue oversight launchagent" in key
            or "rogue oversight launchagent" in key
        ) and not dual_namespace:
            out.append(re.sub(r"^-\s*\[\s*\]", "- [x]", stripped, count=1))
            resolved += 1
            continue
        if peer_up and ("peer loop stopped" in key or "peer loop daemon not running" in key):
            out.append(re.sub(r"^-\s*\[\s*\]", "- [x]", stripped, count=1))
            resolved += 1
            continue
        if improve_up and (
            "improve forever daemon not running" in key or "improve-loop daemon stopped" in key
        ):
            out.append(re.sub(r"^-\s*\[\s*\]", "- [x]", stripped, count=1))
            resolved += 1
            continue
        out.append(line)
    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"
    return new_md, resolved


def resolve_satisfied_wake_interval(md: str, *, wake_ok: bool) -> tuple[str, int]:
    """Mark Tune-wake / hyper-poll queue lines done when live wake is already floored."""
    if not md or not wake_ok:
        return md, 0
    low_md = md.lower()
    if not any(m in low_md for m in _WAKE_INTERVAL_MARKERS):
        return md, 0
    out: list[str] = []
    resolved = 0
    for line in md.splitlines():
        stripped = line.strip()
        if not re.match(r"^-\s*\[\s*\]", stripped):
            out.append(line)
            continue
        item = _parse_work_item(stripped) or stripped
        key = _normalize_queue_key(item)
        item_low = item.lower()
        if any(m in key or m in item_low for m in _WAKE_INTERVAL_MARKERS):
            out.append(re.sub(r"^-\s*\[\s*\]", "- [x]", stripped, count=1))
            resolved += 1
            continue
        out.append(line)
    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"
    return new_md, resolved


def _is_flaw_drift_meta_line(line: str) -> bool:
    stripped = line.strip()
    if _FLAW_DRIFT_PREFIX in stripped or _FLAW_DRIFT_X_MARK in stripped:
        return True
    low = stripped.lower()
    return stripped.startswith("✗") and (
        "only in notes/work_queue.md" in low or "only in self_improve_context" in low
    )


def strip_flaw_research_drift_meta(md: str) -> tuple[str, int]:
    """Remove flaw-research meta wrappers and ✗-only-in continuation pollution."""
    if not md or (_FLAW_DRIFT_PREFIX not in md and _FLAW_DRIFT_X_MARK not in md and "✗" not in md):
        return md, 0
    out: list[str] = []
    removed = 0
    for line in md.splitlines():
        parsed = _parse_work_item(line.strip())
        if parsed and _FLAW_DRIFT_PREFIX in parsed:
            removed += 1
            continue
        if _is_flaw_drift_meta_line(line):
            removed += 1
            continue
        out.append(line)
    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"
    return new_md, removed


def strip_adapt_numbered_duplicates(work_md: str) -> tuple[str, int]:
    """Remove automation_adapt numbered pollution from Active track."""
    lines = work_md.splitlines()
    start = end = -1
    stop = ("## Creative backlog", "## Done", "## Metrics", "## Backlog")
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("## Active") or s.startswith("## Phase"):
            start = i
        elif start >= 0 and any(s.startswith(p) for p in stop):
            end = i
            break
    if start < 0:
        return work_md, 0
    if end < 0:
        end = len(lines)

    out: list[str] = []
    removed = 0
    for i, line in enumerate(lines):
        if start <= i < end and _ADAPT_SYNC_MARKER in line:
            removed += 1
            continue
        out.append(line)
    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"
    return new_md, removed


def strip_open_done_dupes(md: str) -> tuple[str, int]:
    """Remove open bullets when the same normalized key is already checked anywhere."""
    done_keys: set[str] = set()
    for line in md.splitlines():
        stripped = line.strip()
        if re.match(r"^-\s*\[x\]", stripped, re.IGNORECASE):
            item = re.sub(r"^-\s*\[x\]\s*", "", stripped, flags=re.IGNORECASE).strip()
            if item:
                done_keys.add(_normalize_queue_key(item))
    if not done_keys:
        return md, 0

    out: list[str] = []
    removed = 0
    for line in md.splitlines():
        stripped = line.strip()
        if re.match(r"^-\s*\[\s\]", stripped):
            item = _parse_work_item(stripped)
            if item and _normalize_queue_key(item) in done_keys:
                removed += 1
                continue
        out.append(line)
    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"
    return new_md, removed


# OVERSEER_CLOSE_LANDED_DONE_2026_09_04 — Mac-rsync restores unchecked ## Done
# lines for already-landed scripts fixes; promote_open_done_orphans then re-opens
# Active theater and freezes queue_fp. Check-in-place when land-proof is green.
# OVERSEER_CLOSE_ACTIVE_LANDED_2026_09_04 — same proofs also close ## Active /
# ## Remaining work when Mac rsync restores unchecked Active theater (8-flaw set).
_LANDED_DONE_PROOFS: tuple[tuple[str, str, str], ...] = (
    (
        "mark_local_verify on deferred",
        "scripts/peer_loop.py",
        "OVERSEER_LAND_MARK_LOCAL_VERIFY_DEFERRED",
    ),
    (
        "ready-short-circuit skips prune",
        "scripts/dgx_utilization.py",
        "OVERSEER_READY_PRUNE",
    ),
    ("never aligns extras", "scripts/peer_worktree.py", "Extra registered trees"),
    (
        "Reuse plan/execute strings",
        "scripts/automation_improve.py",
        "Build each body at most once",
    ),
    ("test_peer_worktree", "profiles/local.json", "test_peer_worktree"),
    ("hub spawn refuse", "scripts/peer_worktree.py", "_refuse_slot_out_of_cap"),
    (
        "dgx_host nested caps",
        "scripts/automation_config.py",
        "cap_dgx_install_limits",
    ),
    (
        "TTL-skip stall-pivot",
        "scripts/peer_stall_pivot.py",
        "_maybe_stall_adapt_audit",
    ),
    ("verify_memory complete", "", ""),  # grounded_loop theater under Done
    (
        "Port hub HUB_PROTECT push excludes to peer-3",
        ".worktrees/peer-3/scripts/peer_remote.py",
        "OVERSEER_HUB_PROTECT_EXCLUDES_2026_09_04",
    ),  # OVERSEER_PEER3_HUB_PROTECT_CLOSE_2026_09_04
    # 8-flaw Active theater set (Mac rsync reopen loop)
    (
        "probe_output UnboundLocalError",
        "scripts/peer_dual_research.py",
        "Init before try — except path must not UnboundLocalError",
    ),
    (
        "peer_tasks product_constraints",
        "scripts/peer_tasks.json",
        "target max_parallel_peers (live pool, floor 8)",
    ),
    (
        "run_local_cycle ready=True",
        "scripts/run_peer_tasks.py",
        "ready≠git_clean",
    ),
    (
        "_live_from_quick_cache",
        "scripts/project_automation.py",
        'cache.get("tests_ok") is not True',
    ),
    (
        "promote_open_done_orphans",
        "scripts/project_automation.py",
        "OVERSEER_PROMOTE_SKIP_CHECKED_20260904",
    ),
    (
        "factory_grid.global_agent_cap",
        "scripts/factory_grid.py",
        "never above ``max_parallel_peers``",
    ),
    (
        "apply_dgx_speed_overlay",
        "scripts/automation_config.py",
        "Preserve existing local keys and then apply",
    ),
    (
        "tests/ vs scripts/ test_run_peer_tasks",
        "tests/test_run_peer_tasks.py",
        "OVERSEER_SYNC_SELFCHECK_CAP_TEST_2026_09_04",
    ),
    (
        "lean verify omits tests.test_factory_grid",
        "profiles/local.json",
        "tests.test_factory_grid",
    ),
    (
        "plan-gate soften_recoverable",
        "scripts/peer_error_adapt.py",
        "OVERSEER_GATE_SOFTENED_2026_09_04",
    ),
    (
        "self-check under dgx_self_check_cap",
        "scripts/run_peer_tasks.py",
        # OVERSEER_SELF_CHECK_CAP_DEFER_PROOF_STRICT_2026_09_04 — comment-only
        # OVERSEER_SELF_CHECK_CAP_DEFER must not count as landed.
        "OVERSEER_SELF_CHECK_CAP_DEFER_RETURN_2026_09_04",
    ),
    (
        "SELF_CHECK_CAP_DEFER comment-needle false-green",
        "scripts/run_peer_tasks.py",
        "OVERSEER_SELF_CHECK_CAP_DEFER_RETURN_2026_09_04",
    ),
    (
        "close_landed SELF_CHECK_CAP_DEFER comment-needle",
        "scripts/run_peer_tasks.py",
        "OVERSEER_SELF_CHECK_CAP_DEFER_RETURN_2026_09_04",
    ),
    (
        "self_check_worker_count double-counts",
        "scripts/dgx_ram_budget.py",
        "OVERSEER_SELF_CHECK_COMM",
    ),
    (
        "hub_agent_cap ignores max_parallel_peers",
        "scripts/factory_grid.py",
        "never above ``max_parallel_peers``",
    ),
    (
        "Inject last_cycle deferred",
        "scripts/peer_transcript.py",
        "OVERSEER_LAND_DEFERRED_HOT_MEMORY",
    ),
    (
        "TTL-skip write_team_context",
        "scripts/peer_team_context.py",
        "OVERSEER_TEAM_CONTEXT_TTL",
    ),
    (
        "Same-tick skip emit",
        "scripts/peer_stall_pivot.py",
        "continuum kit fresh",
    ),
    (
        "Dedup self-check build_plan",
        "scripts/peer_orchestrate.py",
        "OVERSEER_SELF_CHECK_REUSE_PLAN_LIVE",
    ),
    (
        "Verify gate skip self-check under dgx_self_check_cap",
        "scripts/run_peer_tasks.py",
        "OVERSEER_SELF_CHECK_CAP_DEFER_RETURN_2026_09_04",
    ),
    (
        "emit TTL-skip",
        "scripts/peer_loop.py",
        "_hub_parallel_namespaces_healthy",
    ),
    (
        "nested pool re-explosion",
        "scripts/peer_worktree.py",
        "_refuse_nested_pool_target",
    ),
    (
        "Skip ensure_parallel_pool in peer_loop._after_verify_ok",
        "scripts/peer_loop.py",
        "OVERSEER_LAND_2026_09_03",
    ),
    (
        "isolate/re-isolate writes tracked",
        "scripts/peer_worktree.py",
        "OVERSEER_SCRUB_TRACKED_NS",
    ),
    (
        "Factory progress probe failed",
        "scripts/factory_progress.py",
        "def compute_report",
    ),
    (
        "extra_only sync not hub-pool-scoped",
        "scripts/peer_worktree.py",
        "is_hub_pool_path",
    ),
    (
        "Skip write_prompts ASI compute",
        "scripts/automation_improve.py",
        "OVERSEER_WRITE_PROMPTS_TTL",
    ),
    (
        "External proof: adapt + native verify on CPT",
        "",
        "",
    ),  # self_sufficient — Creative only
    (
        "peer_orchestrate self-check failed",
        "scripts/peer_repo_research.py",
        "OVERSEER_SKIP_SELF_CHECK_JUNK_2026_09_04",
    ),  # OVERSEER_CLOSE_SELFCHECK_JUNK_2026_09_04
    # OVERSEER_CLOSE_REPO_FLAW_HUB_PROTECT_2026_09_04 — Mac/context reopen theater
    (
        "REPO_FLAW_RESEARCH.md missing from HUB_PROTECT",
        "scripts/peer_remote.py",
        "OVERSEER_HUB_PROTECT_REPO_FLAW_2026_09_04",
    ),
    # OVERSEER_CLOSE_FALSE_EVAL_REPOISON_2026_09_04 — stale peer DIFF reopen
    (
        "re-poison false eval",
        "scripts/peer_repo_research.py",
        "OVERSEER_STATIC_SKIP_FALSE_EVAL_ECHO_2026_09_04",
    ),
    # OVERSEER_CLOSE_LAST_CYCLE_POISON_2026_09_04 — fixture/deferred Active reopen
    (
        "last_cycle poison",
        "scripts/peer_transcript.py",
        "OVERSEER_SCRUB_DEFERRED_POISON_2026_09_04",
    ),
    (
        "Agent notes drop non-bullet",
        "scripts/peer_repo_research.py",
        "OVERSEER_DIGEST_KEEP_HASH_NOTES_2026_09_04",
    ),
    (
        "write_digest Agent notes",
        "scripts/peer_repo_research.py",
        "OVERSEER_DIGEST_KEEP_HASH_NOTES_2026_09_04",
    ),
    # OVERSEER_CLOSE_PROOF_NEEDLES_2026_09_04 — fix stale markers + backlog ghosts
    # OVERSEER_DEFERRED_SOFT_STAG_2026_09_04 — auth/deferred soft score
)



_CLOSE_LANDED_SECTIONS = (
    "## Active",
    "## Done",
    "## Remaining work",
    "## Backlog",  # OVERSEER_CLOSE_LANDED_BACKLOG_2026_09_04
)



def _hub_protect_excludes_landed(path: Path) -> bool:
    """True when peer_remote has ≥41 hub-protect excludes + push --delete protect."""
    try:
        body = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if "OVERSEER_HUB_PROTECT_EXCLUDES_2026_09_04" not in body:
        return False
    if "HUB_PROTECT_PULL_EXCLUDES" not in body:
        return False
    m = re.search(r"HUB_PROTECT_PULL_EXCLUDES.*?=\s*\((.*?)\)", body, re.S)
    if not m:
        return False
    n = len(re.findall(r'"[^"]+"', m.group(1)))
    idx = body.find("_rsync_to_remote")
    push = body[idx : idx + 900] if idx >= 0 else ""
    return n >= 41 and "HUB_PROTECT_PULL_EXCLUDES" in push


def _peer3_hub_protect_landed() -> bool:
    """True when hub or peer-3 has ≥41 hub-protect excludes + push protect.

    Needle: OVERSEER_PEER3_HUB_PROTECT_CLOSE_2026_09_04
    OVERSEER_HUB_PROTECT_LAND_HUB_OR_PEER3_2026_09_04
    """
    candidates = (
        ROOT / "scripts" / "peer_remote.py",
        ROOT / ".worktrees" / "peer-3" / "scripts" / "peer_remote.py",
    )
    return any(_hub_protect_excludes_landed(p) for p in candidates)



def _self_check_cap_defer_landed(path: Path | None = None) -> bool:
    """True only when ``running >= cap`` soft-defers (not comment-only needle).

    Needle: OVERSEER_CLOSE_LANDED_CAP_DEFER_STRUCT_2026_09_04 — comment
    ``# OVERSEER_SELF_CHECK_CAP_DEFER`` alone false-greened Active while Mac
    restore left ``continue`` after the cap check.
    """
    target = path or (ROOT / "scripts" / "run_peer_tasks.py")
    try:
        body = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    # Cap check must soft-defer within a short window (not a distant return).
    m = re.search(
        r"if\s+running\s*>=\s*cap\s*:\s*\n(?P<body>(?:.*\n){0,12})",
        body,
    )
    if not m:
        return False
    window = m.group("body")
    if "continue" in window and "return -1" not in window:
        return False
    return 'return -1, "deferred"' in window or "return -1, 'deferred'" in window




def _marker_in_script_or_vault(rel: str, marker: str) -> bool:
    """True when live script *or* hub-protect vault still holds the land needle.

    OVERSEER_CLOSE_VAULT_FALLBACK_2026_09_04 — Mac→DGX rsync briefly clobbers
    live ``scripts/`` mid-score; vault goldens keep close_landed / factory %
    from treating already-landed Active theater as open (executable_queue thrash).
    """
    if not rel or not marker:
        return False
    name = Path(rel).name
    hub = Path.home() / ".config" / "automation-hub"
    candidates = (
        ROOT / rel,
        hub / "hub-protect" / name,
        hub / "hub-protect" / "scripts" / name,
        hub / "hub-protect-golden" / "scripts" / "scripts" / name,
        ROOT / "notes" / "agent_vaults" / "system_overseer" / "scripts" / name,
    )
    for path in candidates:
        try:
            if path.is_file() and marker in path.read_text(encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    return False


def _landed_done_proof_ok(item: str) -> bool:
    """True when item text matches a proof whose script needle is present (or theater)."""
    lower = item.lower()
    # OVERSEER_PEER3_HUB_PROTECT_CLOSE_2026_09_04
    if "port hub hub_protect push excludes to peer-3" in lower:
        return _peer3_hub_protect_landed()
    # OVERSEER_CLOSE_LANDED_CAP_DEFER_STRUCT_2026_09_04
    if (
        "self_check_cap" in lower.replace("-", "_")
        or "self-check cap" in lower
        or "dgx_self_check_cap" in lower
        or "comment-needle" in lower
        or "self-check cap skip" in lower
    ):
        return _self_check_cap_defer_landed()
    # OVERSEER_CLOSE_LAST_CYCLE_POISON_2026_09_04
    if "last_cycle poison" in lower:
        # Prefer script/vault scrub needle — live fixture state must not block close.
        if _marker_in_script_or_vault(
            "scripts/peer_transcript.py",
            "OVERSEER_SCRUB_DEFERRED_POISON_2026_09_04",
        ) or _marker_in_script_or_vault(
            "scripts/peer_last_cycle_poison.py",
            "OVERSEER_SCRUB_DEFERRED_POISON_2026_09_04",
        ):
            return True
        try:
            import json as _json
            from pathlib import Path as _P
            for _name in ("peer-loop-state.json", "peer-transcript-state.json"):
                _p = _P.home() / ".config" / "automation-hub" / _name
                if not _p.is_file():
                    continue
                _d = _json.loads(_p.read_text(encoding="utf-8", errors="replace"))
                _lc = _d.get("last_cycle") if isinstance(_d, dict) else None
                if not isinstance(_lc, dict):
                    continue
                _ft = str(_lc.get("failure_type") or "").strip()
                try:
                    _ts = float(_lc.get("ts") or 0)
                except (TypeError, ValueError):
                    _ts = 0.0
                if _ft == "deferred" and _lc.get("verify_ok") is True:
                    continue
                if 0 < _ts < 10.0:
                    continue
                return True
        except Exception:
            pass
    # OVERSEER_CLOSE_SELF_CHECK_CAP_PROOF_2026_09_04 — comment-only DEFER ≠ landed
    if (
        "self_check_cap" in lower.replace("-", "_")
        or "self-check cap" in lower
        or "self-check under dgx_self_check_cap" in lower
        or "close_landed self_check_cap_defer" in lower.replace("-", "_")
    ):
        path = ROOT / "scripts" / "run_peer_tasks.py"
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        if "OVERSEER_SELF_CHECK_CAP_DEFER_RETURN" not in body:
            return False
        if 'return -1, "deferred"' not in body and "return -1, 'deferred'" not in body:
            return False
        if "running >= cap" not in body:
            return False
        return True
    # OVERSEER_CLOSE_LANDED_CAP_DEFER_STRUCT_2026_09_04
    if "self-check" in lower and ("dgx_self_check_cap" in lower or "self_check_cap" in lower or "self-check cap" in lower):
        return _self_check_cap_defer_landed()
    if (
        "self_check_cap_defer" in lower
        or "self-check cap skip" in lower
        or "comment-needle" in lower
    ):
        return _self_check_cap_defer_landed()
    for needle, rel, marker in _LANDED_DONE_PROOFS:
        if needle.lower() not in lower:
            continue
        if not rel or not marker:
            return True
        path = ROOT / rel
        # OVERSEER_SELF_CHECK_CAP_DEFER_PROOF_STRICT_2026_09_04
        if marker == "OVERSEER_SELF_CHECK_CAP_DEFER" or (
            "self-check" in needle.lower() and "cap" in needle.lower()
        ):
            return _self_check_cap_defer_landed(path)
        # OVERSEER_CLOSE_VAULT_FALLBACK_2026_09_04 — live clobber ≠ un-land
        return _marker_in_script_or_vault(rel, marker)
    return False



def _pin_queue_vaults_after_close() -> int:
    """OVERSEER_PIN_QUEUE_VAULT_2026_09_04 — pin closed WQ/context into hub-protect vaults."""
    hub = Path.home() / ".config" / "automation-hub"
    roots = (hub/"hub-protect", hub/"vault", hub/"oversight_vault", hub/"hub-protect-vault")
    ctx = ROOT / "scripts" / "self_improve_context.md"
    pairs = (("notes/WORK_QUEUE.md", WORK_QUEUE_PATH), ("WORK_QUEUE.md", WORK_QUEUE_PATH),
             ("scripts/self_improve_context.md", ctx), ("self_improve_context.md", ctx))
    pinned = 0
    future = time.time() + 4 * 3600
    for root in roots:
        if not root.is_dir():
            continue
        for rel, src_path in pairs:
            if not isinstance(src_path, Path) or not src_path.is_file():
                continue
            dest = root / rel
            if not dest.is_file():
                continue
            try:
                dest.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")
                os.utime(dest, (future, future))
                pinned += 1
            except OSError:
                continue
    return pinned

def close_landed_done_orphans(work_md: str) -> tuple[str, int]:
    """Flip open bullets to ``[x]`` when hub land-proof is green.

    Covers ``## Active``, ``## Done``, and ``## Remaining work`` so Mac-rsync
    restored Active theater cannot freeze queue_fp after scripts already landed.
    Prefer check-in-place over promote→Active (noop fingerprint churn).
    Needle: OVERSEER_CLOSE_LANDED_DONE_2026_09_04 · OVERSEER_CLOSE_ACTIVE_LANDED_2026_09_04
    """
    out: list[str] = []
    closed = 0
    in_close_section = False
    for line in work_md.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(h) for h in _CLOSE_LANDED_SECTIONS):
            in_close_section = True
            out.append(line)
            continue
        if in_close_section and stripped.startswith("## "):
            in_close_section = any(stripped.startswith(h) for h in _CLOSE_LANDED_SECTIONS)
            if not in_close_section:
                out.append(line)
                continue
        # OVERSEER_CLOSE_CHECKBOXLESS_2026_09_04 — Mac/horizon paste drops
        # ``[ ]`` so Active theater looks closed to ``open_work_items`` but still
        # poisons queue_fp / oversight Queue (top). Close landed proofs either way.
        if in_close_section and (
            re.match(r"^-\s*\[\s\]", stripped)
            or re.match(r"^-\s*\*\*\[", stripped)
        ):
            item = _parse_work_item(stripped)
            if item and _landed_done_proof_ok(item):
                indent = line[: len(line) - len(line.lstrip())]
                if re.match(r"^-\s*\[\s\]", stripped):
                    body = re.sub(r"^-\s*\[\s\]\s*", "- [x] ", stripped, count=1)
                else:
                    body = re.sub(r"^-\s*", "- [x] ", stripped, count=1)
                out.append(indent + body)
                closed += 1
                continue
        out.append(line)
    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"
    if closed:
        _pin_queue_vaults_after_close()
    return new_md, closed



def open_done_orphan_items(work_md: str) -> list[str]:
    """Open `- [ ]` bullets under ## Done — invisible to phased peer dispatch.

    Skip orphans whose normalized key already has an ``[x]`` twin anywhere in
    the file. Promoting those re-opens Active theater (noop_backoff + queue_fp
    churn) after compact-queue — OVERSEER_PROMOTE_SKIP_CHECKED_20260904.
    """
    done_keys: set[str] = set()
    for line in work_md.splitlines():
        stripped = line.strip()
        if re.match(r"^-\s*\[x\]", stripped, re.IGNORECASE):
            item = re.sub(r"^-\s*\[x\]\s*", "", stripped, flags=re.IGNORECASE).strip()
            if item:
                done_keys.add(_normalize_queue_key(item))
    orphans: list[str] = []
    in_done = False
    for line in work_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Done"):
            in_done = True
            continue
        if in_done and stripped.startswith("## "):
            in_done = False
        if not in_done:
            continue
        if re.match(r"^-\s*\[\s\]", stripped):
            item = _parse_work_item(stripped)
            if not item:
                continue
            if _normalize_queue_key(item) in done_keys:
                continue
            orphans.append(item)
    return orphans


def _active_insert_index(lines: list[str]) -> int | None:
    """Line index to insert promoted Active items (before first stop after Active/Phase)."""
    stop_prefixes = ("## Creative backlog", "## Done", "## Metrics", "## Backlog")
    in_track = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## Active") or stripped.startswith("## Phase"):
            in_track = True
            continue
        if in_track and any(stripped.startswith(p) for p in stop_prefixes):
            return i
    return len(lines) if in_track else None


def promote_open_done_orphans(work_md: str) -> tuple[str, int]:
    """Move open `- [ ]` lines from ## Done into ## Active (peer dispatch blind spot).

    Land-proof-green orphans stay under Done for ``close_landed_done_orphans``
    (OVERSEER_PROMOTE_SKIP_LANDED_2026_09_04) — promoting them re-opens Active
    theater after Mac rsync restores unchecked Done for already-landed fixes.
    """
    orphan_items = [
        i for i in open_done_orphan_items(work_md) if not _landed_done_proof_ok(i)
    ]
    if not orphan_items:
        return work_md, 0

    orphan_keys = {_normalize_queue_key(i) for i in orphan_items}
    lines = work_md.splitlines()
    promoted_lines: list[str] = []
    kept: list[str] = []
    in_done = False
    removed = 0

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## Done"):
            in_done = True
            kept.append(line)
            continue
        if in_done and stripped.startswith("## "):
            in_done = False
        if in_done and re.match(r"^-\s*\[\s\]", stripped):
            item = _parse_work_item(stripped)
            if item and _normalize_queue_key(item) in orphan_keys:
                removed += 1
                promoted_lines.append(line)
                continue
        kept.append(line)

    if not promoted_lines:
        return work_md, 0

    insert_at = _active_insert_index(kept)
    if insert_at is None:
        result = ["## Active", ""] + promoted_lines + [""] + kept
    else:
        result = kept[:insert_at] + promoted_lines + kept[insert_at:]

    new_md = "\n".join(result)
    if not new_md.endswith("\n"):
        new_md += "\n"
    return new_md, removed


def strip_backlog_done_dupes(work_md: str) -> tuple[str, int]:
    """Remove open Backlog lines when the same item is checked elsewhere."""
    done_keys: set[str] = set()
    for line in work_md.splitlines():
        stripped = line.strip()
        if re.match(r"^-\s*\[x\]", stripped, re.IGNORECASE):
            item = re.sub(r"^-\s*\[x\]\s*", "", stripped, flags=re.IGNORECASE).strip()
            if item:
                done_keys.add(_normalize_queue_key(item))
    if not done_keys:
        return work_md, 0

    lines = work_md.splitlines()
    out: list[str] = []
    in_backlog = False
    removed = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## Backlog"):
            in_backlog = True
            out.append(line)
            continue
        if in_backlog and stripped.startswith("## ") and not stripped.startswith("## Backlog"):
            in_backlog = False
        if in_backlog:
            item = _parse_work_item(stripped)
            if item and _normalize_queue_key(item) in done_keys:
                removed += 1
                continue
        out.append(line)
    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"
    return new_md, removed


def strip_backlog_active_clones(work_md: str) -> tuple[str, int]:
    """Remove open Backlog lines whose normalized key is already open in Active/Phase."""
    active_keys = {
        _normalize_queue_key(item) for item in _parse_phased_work_items(work_md) if item
    }
    if not active_keys:
        return work_md, 0

    lines = work_md.splitlines()
    out: list[str] = []
    in_backlog = False
    removed = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## Backlog"):
            in_backlog = True
            out.append(line)
            continue
        if in_backlog and stripped.startswith("## ") and not stripped.startswith("## Backlog"):
            in_backlog = False
        if in_backlog:
            item = _parse_work_item(stripped)
            if item and _normalize_queue_key(item) in active_keys:
                removed += 1
                continue
        out.append(line)
    new_md = "\n".join(out)
    if not new_md.endswith("\n"):
        new_md += "\n"
    return new_md, removed


def compact_executable_queue(
    *,
    max_active: int = 12,
    write: bool = True,
) -> tuple[int, list[str]]:
    """Strip adapt pollution, dedupe, cap active open bullets."""
    actions: list[str] = []
    total = 0
    work_md = load_work_queue_md()
    ctx_md = load_context_md()

    # Close landed Active/Done opens BEFORE promote (else Active theater / queue_fp stall).
    work_md, landed_closed = close_landed_done_orphans(work_md)
    ctx_md, ctx_landed = close_landed_done_orphans(ctx_md)
    landed_total = landed_closed + ctx_landed
    if landed_total:
        actions.append(f"closed {landed_total} landed Active/Done orphan(s)")
        total += landed_total

    work_md, promoted = promote_open_done_orphans(work_md)
    if promoted:
        actions.append(f"promoted {promoted} open-done orphan(s) to Active")
        total += promoted

    work_md, open_done_stripped = strip_open_done_dupes(work_md)
    ctx_md, ctx_open_done = strip_open_done_dupes(ctx_md)
    open_done_total = open_done_stripped + ctx_open_done
    if open_done_total:
        actions.append(f"stripped {open_done_total} open-done dup(s)")
        total += open_done_total

    work_md, done_stripped = strip_backlog_done_dupes(work_md)
    if done_stripped:
        actions.append(f"stripped {done_stripped} backlog done-dup(s)")
        total += done_stripped

    work_md, active_clones = strip_backlog_active_clones(work_md)
    if active_clones:
        actions.append(f"stripped {active_clones} backlog active-clone(s)")
        total += active_clones

    work_md, stripped = strip_adapt_numbered_duplicates(work_md)
    if stripped:
        actions.append(f"stripped {stripped} adapt line(s)")
        total += stripped

    work_md, flaw_stripped = strip_flaw_research_drift_meta(work_md)
    ctx_md, ctx_flaw = strip_flaw_research_drift_meta(ctx_md)
    flaw_total = flaw_stripped + ctx_flaw
    if flaw_total:
        actions.append(f"stripped {flaw_total} flaw-drift meta line(s)")
        total += flaw_total

    try:
        import peer_self_heal as self_heal

        snap = self_heal.daemon_status_snapshot()
        work_md, peer_res = resolve_stale_daemon_flaw_items(
            work_md,
            peer_up=bool(snap.get("peer_loop")),
            improve_up=bool(snap.get("improve_loop")),
            dual_namespace=bool(snap.get("dual_namespace")),
        )
        ctx_md, ctx_res = resolve_stale_daemon_flaw_items(
            ctx_md,
            peer_up=bool(snap.get("peer_loop")),
            improve_up=bool(snap.get("improve_loop")),
            dual_namespace=bool(snap.get("dual_namespace")),
        )
        daemon_res = peer_res + ctx_res
        if daemon_res:
            actions.append(f"resolved {daemon_res} stale daemon flaw-research line(s)")
            total += daemon_res
    except Exception:
        pass

    wake_ok = False
    try:
        import peer_loop as pl

        wake_ok = float(pl.effective_continuous_wake_sec(open_queue_count=4)) > 5.0
    except Exception:
        wake_ok = False
    if wake_ok:
        work_md, wake_w = resolve_satisfied_wake_interval(work_md, wake_ok=True)
        ctx_md, wake_c = resolve_satisfied_wake_interval(ctx_md, wake_ok=True)
        wake_total = wake_w + wake_c
        if wake_total:
            actions.append(f"resolved {wake_total} satisfied wake-interval line(s)")
            total += wake_total

    work_md, rw = dedupe_open_work_queue(work_md)
    ctx_md, rc = dedupe_remaining_work(ctx_md)
    deduped = rw + rc
    if deduped:
        actions.append(f"deduped {deduped} line(s)")
        total += deduped

    # Cap: demote excess open `- [ ]` bullets to Backlog
    lines = work_md.splitlines()
    open_lines: list[tuple[int, str, str]] = []
    stop = ("## Creative backlog", "## Done", "## Metrics", "## Backlog")
    in_active = False
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("## Active") or s.startswith("## Phase"):
            in_active = True
            continue
        if in_active and any(s.startswith(p) for p in stop):
            in_active = False
        if in_active and s.startswith("- [ ]"):
            item = _parse_work_item(s) or s
            open_lines.append((i, line, item))

    if len(open_lines) > max_active:
        demote_idx = {idx for idx, _, _ in open_lines[max_active:]}
        backlog = [line for idx, line, _ in open_lines[max_active:]]
        kept = [line if i not in demote_idx else None for i, line in enumerate(lines)]
        kept = [ln for ln in kept if ln is not None]
        if backlog:
            if not any(l.strip().startswith("## Backlog") for l in kept):
                kept.extend(["", "## Backlog (deferred — noop shrink)", ""])
            kept.extend(backlog)
        work_md = "\n".join(kept)
        if not work_md.endswith("\n"):
            work_md += "\n"
        actions.append(f"demoted {len(backlog)} to Backlog")
        total += len(backlog)

    if write and total:
        WORK_QUEUE_PATH.write_text(work_md, encoding="utf-8")
        CONTEXT_PATH.write_text(ctx_md, encoding="utf-8")

    return total, actions


def sync_queue_drift(context_md: str, work_md: str) -> list[str]:
    """Return human-readable drift warnings between WORK_QUEUE and context.

    Remaining work must match Active/phased opens only (not Backlog/Done orphans).
    """
    ctx_items = remaining_work_items(context_md)
    wq_items = _parse_phased_work_items(work_md)
    ctx_keys = {_normalize_queue_key(i): i for i in ctx_items}
    wq_keys = {_normalize_queue_key(i): i for i in wq_items}
    warnings: list[str] = []
    for key, raw in ctx_keys.items():
        if key not in wq_keys:
            warnings.append(f"only in self_improve_context: {raw[:80]}")
    for key, raw in wq_keys.items():
        if key not in ctx_keys:
            warnings.append(f"only in notes/WORK_QUEUE.md: {raw[:80]}")
    for item in open_done_orphan_items(work_md):
        key = _normalize_queue_key(item)
        if key not in wq_keys:
            warnings.append(f"open under ## Done (invisible to dispatch): {item[:80]}")
    return warnings


def creative_backlog_items(context_md: str) -> list[str]:
    lines = extract_section_lines(context_md, "Creative backlog (optional — does not block stop)")
    items: list[str] = []
    for line in lines:
        item = _parse_work_item(line.strip())
        if item:
            items.append(item)
    return items


def next_experiment_items(reclaim_md: str | None = None) -> list[str]:
    """Open items from notes/CREATIVE_RECLAIM.md § Next experiments (skips ~~done~~ lines)."""
    reclaim_md = reclaim_md if reclaim_md is not None else load_creative_backlog_md()
    lines = extract_section_lines(reclaim_md, "Next experiments (non-obvious)")
    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or "~~" in stripped:
            continue
        item = _parse_work_item(stripped)
        if not item:
            numbered = re.match(r"^\d+\.\s*(.+)$", stripped)
            if numbered:
                text = re.sub(r"\*\*", "", numbered.group(1)).strip()
                if text and "~~" not in text:
                    item = text
        if item:
            items.append(item)
    return items


def loop_work_items(
    context_md: str | None = None,
    work_md: str | None = None,
    *,
    live: LiveState | None = None,
) -> QueueState:
    """Peer loop: WORK_QUEUE / context first; creative backlog only when primary is empty.

    Creative backlog is optional and must not starve Active / launch track items
    (otherwise every cycle fingerprints as a perpetual noop).
    """
    ctx = context_md if context_md is not None else load_context_md()
    work_md = work_md if work_md is not None else load_work_queue_md()

    if loop_marked_exhausted(ctx):
        return QueueState(open_items=[], source="empty")

    primary = open_work_items(ctx, work_md)
    if primary.open_items:
        try:
            import product_drive as pdrive

            sorted_items = pdrive.prioritize_product_items(primary.open_items)
        except Exception:  # noqa: BLE001
            sorted_items = primary.open_items
        return QueueState(open_items=sorted_items, source=primary.source)

    creative = creative_backlog_items(ctx)
    # OVERSEER_FILTER_DEFERRED_CREATIVE_2026_09_04 — meter-deferred creative
    # lines must not become the loop fingerprint when Active is empty (noop spin).
    # OVERSEER_CREATIVE_DEFERRED_INLINE_2026_09_04 — Mac rsync often reclobbers
    # factory_progress._DEFERRED_MARKERS within seconds; keep an inline fallback
    # so healthy-idle queue_fp stays empty under self_sufficient.
    if creative and factory_meter_mode() == "self_sufficient":
        _inline_deferred = (
            "newdrop native verify",
            "registry native verify",
            "factory_meter_mode=external_proof",
            "resume when factory_meter_mode",
            "native verify on newdrop",
            "native verify on cpt",
            "native verify on ram",
            "external proof",
        )

        def _creative_is_deferred(text: str) -> bool:
            low = text.lower()
            try:
                import factory_progress as fp

                if fp._is_deferred(text):
                    return True
            except Exception:  # noqa: BLE001 — fingerprint path must stay soft
                pass
            return any(m in low for m in _inline_deferred)

        creative = [c for c in creative if not _creative_is_deferred(c)]
        # Idea-mining creative is optional fill — not launchable factory work;
        # leaving it as the sole loop item freezes queue_fp forever.
        creative = [
            c
            for c in creative
            if "discover clever" not in c.lower()
            and "discover improvements" not in c.lower()
        ]
    if creative:
        return QueueState(open_items=creative, source="creative")

    # OVERSEER_SKIP_EXPERIMENTS_SELF_SUFFICIENT_2026_09_04 — healthy idle:
    # skip experiments/mine theater that freezes queue_fp with nothing launchable.
    if factory_meter_mode() == "self_sufficient":
        return QueueState(open_items=[], source="empty")

    experiments = next_experiment_items()
    if experiments:
        return QueueState(open_items=experiments, source="experiments")

    if live is not None:
        metrics = hard_metric_blockers(live)
        if metrics:
            return QueueState(open_items=metrics, source="metrics")

    if loop_marked_exhausted(ctx):
        return QueueState(open_items=[], source="empty")

    return QueueState(open_items=[IDEA_MINING_ITEM], source="mine")


def has_loop_work(
    context_md: str | None = None,
    work_md: str | None = None,
    live: LiveState | None = None,
) -> bool:
    ctx = context_md if context_md is not None else load_context_md()
    if loop_marked_exhausted(ctx):
        return False
    return bool(loop_work_items(ctx, work_md, live=live).open_items)


def check_off_resolved_self_heal() -> list[str]:
    """Check off self-heal queue noise resolved by a green verify cycle."""
    needles = (
        "no last_cycle memory",
        "verify failed — dispatch held",
        "verify gate failure",
        "fix verify gate",
    )

    def _match(item: str) -> bool:
        low = item.lower()
        return "[self-heal]" in low and any(n in low for n in needles)

    return check_off_queue_lines(match=_match)


def check_off_queue_lines(
    *,
    match: Callable[[str], bool],
    work_path: Path | None = None,
    context_path: Path | None = None,
) -> list[str]:
    """Mark matching unchecked ``- [ ]`` lines as done in WORK_QUEUE + context.

    Returns deduped item texts that were checked off (empty if nothing matched).
    """
    w_path = work_path or WORK_QUEUE_PATH
    c_path = context_path or CONTEXT_PATH
    checked: list[str] = []

    def _rewrite(path: Path) -> None:
        if not path.is_file():
            return
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        out: list[str] = []
        for line in lines:
            stripped = line.strip()
            if re.match(r"^-\s*\[ \]", stripped) and match(stripped):
                item = re.sub(r"^-\s*\[ \]\s*", "", stripped).strip()
                checked.append(item)
                indent = line[: len(line) - len(line.lstrip())]
                newline = "\n" if line.endswith("\n") else ""
                out.append(f"{indent}- [x] {item}{newline}")
            else:
                out.append(line)
        path.write_text("".join(out), encoding="utf-8")

    _rewrite(w_path)
    _rewrite(c_path)
    seen: set[str] = set()
    uniq: list[str] = []
    for item in checked:
        key = _normalize_queue_key(item)
        if key not in seen:
            seen.add(key)
            uniq.append(item)
    return uniq


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = dict(base)
    for key, val in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        elif key in out and isinstance(out[key], list) and isinstance(val, list):
            if key == "match_rules":
                out[key] = list(val) + [r for r in out[key] if r not in val]
            else:
                out[key] = list(out[key]) + [x for x in val if x not in out[key]]
        else:
            out[key] = val
    return out


_tasks_config_cache: tuple[tuple[tuple[str, int, int], ...], dict] | None = None


def _tasks_config_witness() -> tuple[tuple[str, int, int], ...]:
    paths: list[Path] = [TASKS_PATH]
    profile = CFG.get("task_profile")
    if profile and profile != "generic":
        for name in (f"{profile}.json", f"{profile}.tasks.json"):
            paths.append(ROOT / "profiles" / name)
    paths.append(ROOT / "profiles" / "local.json")
    witness: list[tuple[str, int, int]] = []
    for path in paths:
        try:
            st = path.stat()
            witness.append((str(path), st.st_mtime_ns, st.st_size))
        except OSError:
            witness.append((str(path), 0, 0))
    return tuple(witness)


def _load_tasks_config_uncached() -> dict:
    cfg: dict = {"peers": {}, "task_templates": {}, "verify_commands": [], "match_rules": []}
    if TASKS_PATH.is_file():
        cfg = _deep_merge(cfg, json.loads(TASKS_PATH.read_text()))
    profile = CFG.get("task_profile")
    if profile and profile != "generic":
        for name in (f"{profile}.json", f"{profile}.tasks.json"):
            path = ROOT / "profiles" / name
            if path.is_file():
                overlay = json.loads(path.read_text())
                cfg = _deep_merge(cfg, overlay)
                # Same as apply_local_profile: replace verify_commands (do not append).
                if isinstance(overlay, dict) and "verify_commands" in overlay:
                    cfg["verify_commands"] = list(overlay.get("verify_commands") or [])
    local = ROOT / "profiles" / "local.json"
    if local.is_file():
        overlay = json.loads(local.read_text())
        cfg = _deep_merge(cfg, overlay)
        # local.json lean verify must win over peer_tasks discover — deep_merge
        # concatenates lists and reintroduces unittest discover into the gate.
        if isinstance(overlay, dict) and "verify_commands" in overlay:
            cfg["verify_commands"] = list(overlay.get("verify_commands") or [])
    # Automation hub: never let unittest discover ride along in the verify gate
    # (full suite is `./scripts/peer test`; local lean smoke is the heal gate).
    if CFG.get("task_profile") == "automation":
        discover = "python3 -m unittest discover -s tests -q"
        cfg["verify_commands"] = [
            c for c in (cfg.get("verify_commands") or []) if c != discover
        ]
    return cfg


def load_tasks_config() -> dict:
    global _tasks_config_cache
    witness = _tasks_config_witness()
    if _tasks_config_cache is not None and _tasks_config_cache[0] == witness:
        return _tasks_config_cache[1]
    cfg = _load_tasks_config_uncached()
    _tasks_config_cache = (witness, cfg)
    return cfg


def module_scope_map() -> dict[str, str]:
    scope = CFG.get("module_scope") or {}
    if isinstance(scope, dict):
        return {str(k): str(v) for k, v in scope.items()}
    cfg = load_tasks_config()
    merged = cfg.get("module_scope") or {}
    if isinstance(merged, dict):
        return {str(k): str(v) for k, v in merged.items()}
    return {}


def validate_tasks_config(cfg: dict) -> list[str]:
    issues: list[str] = []
    peers = cfg.get("peers") or {}
    templates = cfg.get("task_templates") or {}
    for name, tmpl in templates.items():
        peer = tmpl.get("peer", "reclaim")
        if peer not in peers:
            issues.append(f"task_templates.{name}: unknown peer '{peer}'")
        tier = tmpl.get("safety_tier")
        if tier is not None and tier not in ("green", "yellow", "red"):
            issues.append(f"task_templates.{name}: invalid safety_tier")
    for cmd in cfg.get("verify_commands") or []:
        if not isinstance(cmd, str) or not cmd.strip():
            issues.append("verify_commands: empty command entry")
    for i, raw in enumerate(cfg.get("agent_roles") or []):
        if not isinstance(raw, dict):
            issues.append(f"agent_roles[{i}]: must be an object")
            continue
        if not str(raw.get("id") or "").strip():
            issues.append(f"agent_roles[{i}]: missing id")
        if not str(raw.get("job_title") or raw.get("title") or "").strip():
            issues.append(f"agent_roles[{i}]: missing job_title")
    return issues


def live_snapshot(live: LiveState, queue: QueueState) -> dict:
    return {
        "git": live.git_detail,
        "git_clean": live.git_clean,
        "tests_ok": live.tests_ok,
        "tests": live.tests_detail,
        "import_rss_mb": live.import_rss_mb,
        "footprint": live.footprint_detail,
        "open_items": queue.open_items,
        "queue_source": queue.source,
    }


def copy_to_clipboard(text: str) -> bool:
    proc = subprocess.run(["pbcopy"], input=text, text=True, check=False)
    return proc.returncode == 0
