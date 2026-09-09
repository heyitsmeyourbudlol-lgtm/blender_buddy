"""Remote cursor-agent dispatch via SSH (e.g. NVIDIA DGX Spark / NVIDIA Sync host)."""

from __future__ import annotations

import os
import shlex
import subprocess
import threading
from pathlib import Path
from typing import Callable

import project_automation as auto

ROOT = auto.ROOT
_SYNC_LOCK = threading.Lock()

_DEFAULT_EXCLUDES = (
    ".git",
    ".worktrees",
    "__pycache__",
    "node_modules",
    ".DS_Store",
    "*.pyc",
    # Host-local identity — Mac automation vs DGX automation-hub must not clobber.
    "automation.config.json",
)


def _cfg() -> dict:
    raw = auto.CFG.get("agent_remote")
    return raw if isinstance(raw, dict) else {}


def remote_enabled() -> bool:
    """Global remote dispatch gate (``agent_remote.enabled`` / ``dgx_host.primary``).

    Unchanged for callers that want whole-kit remote mode. Per-role DGX preference
    should use :func:`should_dispatch_remote` with ``prefer_remote=True`` instead.
    """
    if os.environ.get("PEER_AGENT_LOCAL") == "1":
        return False
    dgx = auto.CFG.get("dgx_host")
    if isinstance(dgx, dict) and dgx.get("primary") is False:
        return False
    cfg = _cfg()
    if cfg.get("enabled"):
        return bool(str(cfg.get("ssh_host") or "").strip())
    if isinstance(dgx, dict) and dgx.get("primary"):
        return bool(str(dgx.get("ssh_host") or cfg.get("ssh_host") or "CLEAN").strip())
    return False


def should_dispatch_remote(*, prefer_remote: bool = False) -> bool:
    """Whether this agent launch should go over SSH (e.g. DGX).

    * ``PEER_AGENT_LOCAL=1`` always forces local.
    * ``prefer_remote=True`` (per-role): dispatch remote when an SSH host is
      resolvable via :func:`ssh_host` / ``dgx_host``, even if
      ``agent_remote.enabled`` is false. Honors ``dgx_host.primary is False``.
    * Otherwise falls back to :func:`remote_enabled` (global mode).
    """
    if os.environ.get("PEER_AGENT_LOCAL") == "1":
        return False
    if prefer_remote:
        # Role wants DGX: allow if we can resolve an ssh host
        host = ssh_host()
        dgx = auto.CFG.get("dgx_host")
        if isinstance(dgx, dict) and dgx.get("primary") is False:
            return False
        if host or (isinstance(dgx, dict) and (dgx.get("ssh_host") or dgx.get("primary"))):
            return True
        return False
    return remote_enabled()


def ssh_host() -> str:
    """Resolved SSH host for remote dispatch.

    Prefers ``agent_remote.ssh_host``, then ``dgx_host.ssh_host``, then ``CLEAN``.
    """
    host = str(_cfg().get("ssh_host") or "").strip()
    if host:
        return host
    dgx = auto.CFG.get("dgx_host")
    if isinstance(dgx, dict):
        host = str(dgx.get("ssh_host") or "").strip()
        if host:
            return host
    return "CLEAN"


def local_root() -> Path:
    custom = _cfg().get("local_root")
    if custom:
        return Path(str(custom)).expanduser().resolve()
    return Path.home().resolve()


def remote_root() -> str:
    return str(_cfg().get("remote_root") or "/home/arnavrastogi").rstrip("/")


def remote_agent_bin() -> str:
    return str(
        _cfg().get("cursor_agent_bin")
        or "$HOME/.cursor-server/data/User/globalStorage/anysphere.cursor-agent-worker/agent-cli/.local/bin/cursor-agent"
    )


def remote_config_namespace() -> str:
    return str(_cfg().get("config_namespace") or auto.CFG.get("config_namespace") or "automation-hub")


# Hub-protect vault needles — never let Mac→DGX inbound rsync rewind WORKING lands.
# Keep in sync with ~/.config/automation-hub/bin/restore-hub-protect.sh rel list
# and scripts/dgx_setup.sh push excludes (OVERSEER_HUB_PROTECT_PUSH_2026_09_04).
# OVERSEER_HUB_PROTECT_EXCLUDES_2026_09_04 — include queue twin + forge path so
# Mac --delete-before cannot reopen Active theater or Path("<darwin-home>").
HUB_PROTECT_PULL_EXCLUDES: tuple[str, ...] = (
    # OVERSEER_HUB_PROTECT_EXCLUDES_2026_09_04 — queue/digest/forge must not rewind
    "notes/PEN_TEST.md",
    # OVERSEER_HUB_PROTECT_FORGE_2026_09_04 — full WORKING + queue twins
    "notes/WORK_QUEUE.md",
    "notes/SYSTEM_OVERSIGHT.md",
    # OVERSEER_HUB_PROTECT_REPO_FLAW_2026_09_04 — Agent notes + digest must not rewind
    # OVERSEER_STAG_EVENT_REMOTE_2026_09_04 — stagnation land: keep pull-protect
    "notes/REPO_FLAW_RESEARCH.md",
    "notes/AUTOMATION_DIGEST.md",
    "scripts/self_improve_context.md",
    "repos/registry.json",
    "automation.config.json",
    "automation.config.local.json",
    "scripts/dgx_ram_budget.py",
    "scripts/dgx_utilization.py",
    "scripts/dgx_setup.sh",
    "scripts/run_peer_tasks.py",
    "scripts/peer_loop.py",
    "scripts/factory_grid.py",
    "scripts/factory_progress.py",
    "tests/test_factory_progress.py",
    "scripts/project_automation.py",
    "scripts/automation_config.py",
    "scripts/automation_adapt.py",
    "tests/test_adapt_dirty_head_only.py",
    "scripts/automation_improve.py",
    "scripts/peer_error_adapt.py",
    "scripts/peer_worktree.py",
    "scripts/peer_dual_research.py",
    "scripts/peer_orchestrate.py",
    "scripts/peer_remote.py",
    "tests/test_peer_self_heal.py",
    "scripts/peer_oversight.py",
    "scripts/peer_self_heal.py",
    # OVERSEER_HUB_PROTECT_VAULT_2026_09_04 — Mac must not rewind vault SOT
    "notes/agent_vaults/",
    "scripts/peer_stall_pivot.py",
    "scripts/peer_land_hold.py",
    "scripts/peer_team_context.py",
    "scripts/peer_product_forge.py",
    "scripts/peer_pen_test.py",
    # OVERSEER_PROTECT_TRANSCRIPT_SCRUB_2026_09_04 — scrub helpers must not rewind
    "scripts/peer_transcript.py",
    "scripts/peer_oversight_events.py",
    # OVERSEER_PROTECT_RESOURCE_PRIORITY_2026_09_04 — Path-local import + hub poll
    "scripts/dgx_resource_priority.py",
    "tests/test_dgx_resource_priority.py",
    # OVERSEER_PROTECT_RESTORE_SCRIPT_2026_09_04 — restore needles must not rewind
    "scripts/restore-hub-protect.sh",
    # OVERSEER_PROTECT_BEAT_MAC_2026_09_04
    "scripts/beat-mac-clobber.sh",
    "scripts/peer_tasks.json",
    "tests/test_peer_pen_test.py",
    "tests/test_peer_worktree.py",
    "tests/test_dgx_ram_budget.py",
    "tests/test_run_peer_tasks.py",
    "tests/test_factory_grid.py",
    "tests/test_peer_error_adapt.py",
    "tests/test_peer_product_forge.py",
    "tests/test_peer_remote.py",
    "tests/test_automation.py",
    "tests/test_oversight_stagnation_fixes.py",
    "tests/test_peer_repo_research.py",
    "scripts/peer_repo_research.py",
    "scripts/_mark_flaw_research_landed.py",
    # OVERSEER_PROTECT_POISON_SOT_2026_09_04
    "scripts/peer_last_cycle_poison.py",
    "tests/test_peer_last_cycle_poison.py",
    # OVERSEER_HUB_PROTECT_DIST_EXPORT_2026_09_04 — Mac must not reintro privacy-bad kit tars
    "dist/automation-kit-*.tar.gz",
    # OVERSEER_HUB_PROTECT_BITNET_FACTCHECK_2026_09_05 — Wave-15 ledger must not rewind
    "notes/BITNET_FACTCHECK.md",
    "notes/NVFP4_LOCK_APPLICABILITY.md",
)


def rsync_excludes() -> tuple[str, ...]:
    raw = _cfg().get("rsync_excludes")
    if isinstance(raw, list) and raw:
        return tuple(str(x) for x in raw)
    return _DEFAULT_EXCLUDES


def translate_path(path: Path) -> str:
    """Map a local absolute path to the remote workspace root."""
    resolved = path.expanduser().resolve()
    root = local_root()
    try:
        rel = resolved.relative_to(root)
    except ValueError:
        return f"{remote_root()}/{resolved.name}"
    return f"{remote_root()}/{rel.as_posix()}"


def translate_text(text: str) -> str:
    """Rewrite local absolute paths inside prompts for the remote host."""
    local = str(local_root())
    remote = remote_root()
    if local == remote:
        return text
    return text.replace(local, remote)


def _ssh_base() -> list[str]:
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        ssh_host(),
    ]


def _hub_dirty_relpaths(local_dir: Path) -> list[str]:
    """Paths with local hub changes — exclude from inbound rsync (CLEAN clock skew defeats -u)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(local_dir), "status", "--porcelain", "-uall"],
            capture_output=True,
            text=True,
            timeout=30.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    paths: list[str] = []
    for line in (proc.stdout or "").splitlines():
        if len(line) < 4:
            continue
        rest = line[3:].strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1].strip()
        if rest.startswith('"') and rest.endswith('"'):
            rest = rest[1:-1]
        if rest:
            paths.append(rest)
    return paths


def _rsync_to_remote(local_dir: Path, remote_dir: str, *, log_fn: Callable[[str], None]) -> bool:
    excludes: list[str] = []
    for item in rsync_excludes():
        excludes.extend(["--exclude", item])
    # OVERSEER_HUB_PROTECT_PUSH_2026_09_04 — push --delete must not wipe DGX
    # WORKING hub-protect needles (Mac sync was reopening Active theater).
    for item in HUB_PROTECT_PULL_EXCLUDES:
        excludes.extend(["--exclude", item])
    src = str(local_dir).rstrip("/") + "/"
    dest = f"{ssh_host()}:{remote_dir.rstrip('/')}/"
    cmd = ["rsync", "-az", "--delete", *excludes, src, dest]
    log_fn(f"remote: rsync → hub-protect excludes={len(HUB_PROTECT_PULL_EXCLUDES)}")
    log_fn(f"remote: rsync → {ssh_host()}:{remote_dir}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600.0, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_fn(f"remote: rsync push failed ({exc})")
        return False
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        log_fn(f"remote: rsync push exit {proc.returncode} — {tail[-1] if tail else 'see peer-agent.log'}")
        return False
    return True


def _rsync_from_remote(local_dir: Path, remote_dir: str, *, log_fn: Callable[[str], None]) -> bool:
    excludes: list[str] = []
    for item in rsync_excludes():
        excludes.extend(["--exclude", item])
    # Always exclude hub-protect vault needles (Mac rsync --delete-before clobber).
    for item in HUB_PROTECT_PULL_EXCLUDES:
        excludes.extend(["--exclude", item])
    dirty = _hub_dirty_relpaths(local_dir)
    for rel in dirty:
        excludes.extend(["--exclude", rel])
    if dirty:
        log_fn(f"remote: rsync ← protect {len(dirty)} hub-dirty path(s)")
    log_fn(f"remote: rsync ← hub-protect excludes={len(HUB_PROTECT_PULL_EXCLUDES)}")
    src = f"{ssh_host()}:{remote_dir.rstrip('/')}/"
    dest = str(local_dir).rstrip("/") + "/"
    # --update + dirty-path excludes (CLEAN clock skew defeats mtime -u alone).
    cmd = ["rsync", "-azu", *excludes, src, dest]
    log_fn(f"remote: rsync ← {ssh_host()}:{remote_dir}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600.0, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_fn(f"remote: rsync pull failed ({exc})")
        return False
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        log_fn(f"remote: rsync pull exit {proc.returncode} — {tail[-1] if tail else 'see peer-agent.log'}")
        return False
    return True


def sync_tree(local_dir: Path, *, log_fn: Callable[[str], None], direction: str) -> bool:
    """Sync the project root (not just one worktree) to avoid parallel rsync races."""
    sync_root = ROOT.resolve()
    remote_dir = translate_path(sync_root)
    with _SYNC_LOCK:
        if direction == "push":
            return _rsync_to_remote(sync_root, remote_dir, log_fn=log_fn)
        if direction == "pull":
            return _rsync_from_remote(sync_root, remote_dir, log_fn=log_fn)
    return False


def sync_project(*, log_fn: Callable[[str], None], direction: str) -> bool:
    """Public entry — sync full repo root once."""
    return sync_tree(ROOT, log_fn=log_fn, direction=direction)


def remote_auth_ready() -> tuple[bool, str]:
    """Check cursor-agent auth on the remote host (never exposes secrets)."""
    ns = remote_config_namespace()
    agent = remote_agent_bin()
    script = (
        f"if [ -f \"$HOME/.config/{ns}/cursor-agent.env\" ]; then "
        f"grep -q '^CURSOR_API_KEY=' \"$HOME/.config/{ns}/cursor-agent.env\" && "
        f"echo '__API_KEY__' && exit 0; fi; "
        f"export PATH=\"$HOME/.cursor-server/data/User/globalStorage/"
        f"anysphere.cursor-agent-worker/agent-cli/.local/bin:$HOME/.local/bin:$PATH\"; "
        f"{agent} status 2>&1"
    )
    try:
        proc = subprocess.run(
            _ssh_base() + [script],
            capture_output=True,
            text=True,
            timeout=20.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, f"ssh {ssh_host()} status timed out"
    out = (proc.stdout or proc.stderr or "").strip()
    if "__API_KEY__" in out:
        return True, f"remote {ssh_host()} CURSOR_API_KEY configured"
    lower = out.lower()
    if proc.returncode == 0 and out and "not logged in" not in lower and "authentication required" not in lower:
        return True, f"remote {ssh_host()} cursor-agent ready"
    if "not logged in" in lower or "authentication required" in lower:
        return False, f"remote {ssh_host()} cursor-agent not logged in — run scripts/dgx_setup.sh"
    tail = out.splitlines()[-1] if out else f"ssh exit {proc.returncode}"
    return False, tail


def count_remote_agent_procs() -> int:
    """Count remote ``cursor-agent -p`` peer cycles."""
    script = "pgrep -af 'cursor-agent' 2>/dev/null | grep -E '(^| )-p( |$)' | grep -v worker | wc -l"
    try:
        proc = subprocess.run(
            _ssh_base() + [script],
            capture_output=True,
            text=True,
            timeout=12.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if proc.returncode != 0:
        return 0
    try:
        return max(0, int((proc.stdout or "0").strip()))
    except ValueError:
        return 0


def run_remote_cursor_agent(
    prompt: str,
    *,
    log_fn: Callable[[str], None],
    timeout_sec: float,
    paid_api: bool,
    cwd: Path | None = None,
    sync: bool = True,
) -> tuple[int, bool]:
    """Sync tree, run cursor-agent on remote host, pull changes back.

    ``sync=False`` means fire-and-forget agent launch (do not wait up to
    ``timeout_sec``). Tree rsync before/after still follows config when the
    caller waits (``sync=True``).
    """
    import peer_terminal as terminal

    work = (cwd or ROOT).resolve()
    remote_cwd = translate_path(work)
    remote_prompt = translate_text(prompt)

    ready, detail = remote_auth_ready()
    if not ready:
        log_fn(f"remote: auth not ready — {detail}")
        terminal.write_prompt_file(prompt)
        log_fn(f"remote: prompt saved → {terminal.PROMPT_PATH}")
        return 1, True

    wait_for_agent = sync
    # Push tree before any remote agent so background launches still see fresh code.
    if bool(_cfg().get("sync_before_dispatch", True)):
        if not sync_project(log_fn=log_fn, direction="push"):
            log_fn("remote: push failed — aborting dispatch")
            terminal.write_prompt_file(prompt)
            return 1, False
        # Product forge / external cwd: also push that tree (hub sync alone misses it).
        try:
            work_res = work.resolve()
            root_res = ROOT.resolve()
            # OVERSEER_PRODUCT_CWD_ISDIR_2026_09_04 — skip phantom paths (tests / missing trees)
            if (
                work_res != root_res
                and root_res not in work_res.parents
                and work_res.is_dir()
            ):
                prod_remote = translate_path(work_res)
                if not _rsync_to_remote(work_res, prod_remote, log_fn=log_fn):
                    log_fn(f"remote: product cwd push failed — {work_res.name}")
                    return 1, False
        except OSError as exc:
            log_fn(f"remote: product cwd push ({exc})")
            return 1, False

    ns = remote_config_namespace()
    agent = remote_agent_bin()
    # OVERSEER_CURSOR_AGENT_ARGV_E2BIG_2026_09_05 — never put huge prompts on the
    # SSH/argv command line (shlex.quote + ARG_MAX → Errno 7). Always land the
    # body on the remote prompt file; argv only carries a short pointer when large.
    remote_prompt_rel = f"$HOME/.config/{ns}/next-peer-prompt.md"
    soft_max = getattr(terminal, "ARGV_PROMPT_SOFT_MAX", 12_000)
    if len(remote_prompt) > soft_max:
        write_remote = (
            f"mkdir -p \"$HOME/.config/{ns}\" && cat > \"$HOME/.config/{ns}/next-peer-prompt.md\""
        )
        try:
            wproc = subprocess.run(
                _ssh_base() + [write_remote],
                input=remote_prompt,
                capture_output=True,
                text=True,
                timeout=60.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            log_fn(f"remote: prompt file write failed — {exc}")
            terminal.write_prompt_file(prompt)
            return 1, False
        if wproc.returncode != 0:
            tail = ((wproc.stderr or wproc.stdout or "").strip().splitlines() or [""])[-1]
            log_fn(f"remote: prompt file write failed — {tail}")
            return wproc.returncode or 1, False
        argv_prompt = (
            f"Read the full peer prompt at {remote_prompt_rel} (markdown, already on disk). "
            "Execute that file end-to-end; do not ask for clarification — begin work."
        )
        log_fn(
            f"remote: prompt {len(prompt)} chars → file pointer "
            f"({len(argv_prompt)} chars argv) · {remote_prompt_rel}"
        )
    else:
        argv_prompt = remote_prompt
    quoted_prompt = shlex.quote(argv_prompt)
    paid_flag = ""
    try:
        import peer_terminal as _pt

        free_locked = _pt.force_free_desktop_auth()
    except Exception:  # noqa: BLE001
        free_locked = True
    if free_locked:
        paid_api = False
        paid_flag = "export PEER_LOOP_PAID_API=0; export AUTOMATION_FORCE_FREE_DESKTOP=1; "
    elif paid_api or os.environ.get("PEER_LOOP_PAID_API") == "1":
        paid_flag = "export PEER_LOOP_PAID_API=1; "
    env_prefix = (
        f"export PATH=\"$HOME/.cursor-server/data/User/globalStorage/"
        f"anysphere.cursor-agent-worker/agent-cli/.local/bin:$HOME/.local/bin:$PATH\"; "
        f"if [ -f \"$HOME/.config/{ns}/cursor-agent.env\" ]; then "
        f"set -a; . \"$HOME/.config/{ns}/cursor-agent.env\"; set +a; fi; "
        f"{paid_flag}"
    )
    # OVERSEER_CURSOR_AGENT_ARGV_NO_API_KEY_2026_09_07 — credentials via sourced
    # cursor-agent.env only; never --api-key / CURSOR_API_KEY= on the remote argv.
    terminal.assert_cursor_agent_argv_safe(
        [agent, "-p", "--force", "--output-format", "text", argv_prompt]
    )
    agent_cmd = (
        f"cd {shlex.quote(remote_cwd)} && "
        f"{agent} -p --force --output-format text {quoted_prompt}"
    )
    log_fn(f"remote: cursor-agent on {ssh_host()} ({len(prompt)} chars) · cwd={remote_cwd}")

    if not wait_for_agent:
        # Background on remote so improve/forge never block on a 2h SSH wait.
        bg_script = (
            f"{env_prefix}"
            f"nohup bash -lc {shlex.quote(agent_cmd)} "
            f">/tmp/peer-remote-agent.log 2>&1 </dev/null & echo $!"
        )
        try:
            proc = subprocess.run(
                _ssh_base() + [bg_script],
                capture_output=True,
                text=True,
                timeout=min(90.0, max(15.0, timeout_sec if timeout_sec < 120 else 60.0)),
                check=False,
            )
        except subprocess.TimeoutExpired:
            log_fn("remote: background launch timed out (ssh)")
            return 1, False
        if proc.returncode != 0:
            tail = ((proc.stderr or proc.stdout or "").strip().splitlines() or [""])[-1]
            log_fn(f"remote: background launch failed — {tail}")
            return proc.returncode or 1, False
        pid = (proc.stdout or "").strip().splitlines()
        log_fn(
            f"remote: cursor-agent launched (background)"
            + (f" pid={pid[-1]}" if pid else "")
        )
        return 0, False

    remote_script = f"set -e; {env_prefix}{agent_cmd}"
    try:
        proc = subprocess.run(
            _ssh_base() + [remote_script],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log_fn(f"remote: cursor-agent timed out after {timeout_sec:.0f}s")
        return 1, False

    terminal.append_agent_log(f"remote {ssh_host()}", proc.stdout or "", proc.stderr or "")

    if bool(_cfg().get("sync_after_dispatch", True)):
        sync_project(log_fn=log_fn, direction="pull")

    combined = (proc.stderr or proc.stdout or "").strip()
    auth_failed = terminal.is_auth_error(combined)
    if proc.returncode == 0:
        log_fn(f"remote: cursor-agent finished ok on {ssh_host()}")
        return 0, False

    tail = combined.splitlines()
    log_fn(
        f"remote: cursor-agent exit {proc.returncode} on {ssh_host()} — "
        f"{tail[-1] if tail else 'see peer-agent.log'}"
    )
    return proc.returncode, auth_failed
