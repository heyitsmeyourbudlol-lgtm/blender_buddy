"""Terminal dispatch for peer loop — cursor-agent CLI in background subprocess.

Hard-locked to desktop login ($0). API-key billing is never chosen by this kit
(``force_free_desktop_auth``). Never activates Cursor.app, clipboard, or keystrokes.
"""

from __future__ import annotations

import errno
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

import peer_remote
import project_automation as auto

ROOT = auto.ROOT
PROMPT_PATH = auto.CONFIG_DIR / "next-peer-prompt.md"
AGENT_LOG_PATH = auto.CONFIG_DIR / "peer-agent.log"
DEFAULT_AGENT_TIMEOUT_SEC = 7200.0
AGENT_ENV_PATH = auto.CONFIG_DIR / "cursor-agent.env"
# OVERSEER_CURSOR_AGENT_ARGV_E2BIG_2026_09_05 — cursor-agent takes the prompt as
# argv; flaw-scan / cold-memory blobs exceed OS ARG_MAX (Errno 7). Soft-cap and
# fall back to a short pointer that tells the agent to read PROMPT_PATH.
ARGV_PROMPT_SOFT_MAX = 12_000
# Tiny bodies (e.g. unittest "test prompt") must not clobber a live argv-pointer
# payload mid-flight. OVERSEER_PEER_PROMPT_CLOBBER_GUARD_2026_09_05
PROMPT_CLOBBER_GUARD_MAX_NEW = 64

PAID_API_WARNING = (
    "CURSOR_API_KEY is configured — cursor-agent bills API quota. "
    "Pass --paid-api to opt in; background default uses desktop login only."
)

# OVERSEER_FORCE_FREE_DESKTOP_2026_09_05 — never bill API quota from this kit.
_FORCE_FREE_ENV = "AUTOMATION_FORCE_FREE_DESKTOP"


def force_free_desktop_auth() -> bool:
    """Hard lock: desktop login only ($0). Paid API path is never chosen.

    Default **True**. ``AUTOMATION_FORCE_FREE_DESKTOP=0`` is ignored when config
    ``force_free_desktop_auth`` is true (kit default).
    """
    try:
        if bool(auto.CFG.get("force_free_desktop_auth", True)):
            return True
    except Exception:  # noqa: BLE001
        return True
    env = (os.environ.get(_FORCE_FREE_ENV) or "1").strip().lower()
    return env not in ("0", "false", "no", "off")


def paid_api_forbidden() -> bool:
    return force_free_desktop_auth()


def resolve_prompt_path(path: Path | None = None) -> Path:
    """Return prompt dest — ``AUTOMATION_PEER_PROMPT_PATH`` overrides live hub path."""
    if path is not None:
        return path
    override = (os.environ.get("AUTOMATION_PEER_PROMPT_PATH") or "").strip()
    if override:
        return Path(override)
    return PROMPT_PATH


def _prompt_force_write() -> bool:
    return os.environ.get("AUTOMATION_PEER_PROMPT_FORCE") == "1"


def would_clobber_live_prompt(dest: Path, text: str) -> bool:
    """True when a tiny write would erase a large live next-peer-prompt.md."""
    if _prompt_force_write():
        return False
    if len(text) > PROMPT_CLOBBER_GUARD_MAX_NEW:
        return False
    try:
        live = PROMPT_PATH.resolve()
        target = dest.resolve()
    except OSError:
        return False
    if target != live:
        return False
    try:
        if not dest.is_file():
            return False
        return dest.stat().st_size > ARGV_PROMPT_SOFT_MAX
    except OSError:
        return False


def require_paid_api_opt_in() -> bool:
    """True when caller explicitly opted into paid API dispatch.

    Always False when ``force_free_desktop_auth`` is on (kit default — never bill).
    """
    if force_free_desktop_auth():
        return False
    return os.environ.get("PEER_LOOP_PAID_API") == "1"


def api_key_configured() -> bool:
    """True when CURSOR_API_KEY is set in cursor-agent.env (paid billing path)."""
    if not AGENT_ENV_PATH.is_file():
        return False
    for line in AGENT_ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "CURSOR_API_KEY" and value.strip():
            return True
    return False


def auth_fix_hint() -> str:
    return (
        f"Run `cursor-agent login` once for desktop auth ($0), or set CURSOR_API_KEY in "
        f"{AGENT_ENV_PATH} and pass --paid-api (bills quota). "
        f"Background default: peer_loop.py --forever --background (local-only if not logged in)."
    )


def is_auth_error(text: str) -> bool:
    lower = text.lower()
    return "authentication required" in lower or "not logged in" in lower or "agent login" in lower


_AUTH_READY_TTL_SEC = 30.0
_auth_ready_cache: tuple[float, bool, str] | None = None


def cursor_agent_auth_ready() -> tuple[bool, str]:
    """Return (ready, detail). Never exposes secret values."""
    global _auth_ready_cache
    now = time.time()
    if _auth_ready_cache and now - _auth_ready_cache[0] < _AUTH_READY_TTL_SEC:
        return _auth_ready_cache[1], _auth_ready_cache[2]

    # FORCE FREE: never treat API key as auth-ready (would enable paid path).
    if api_key_configured() and not force_free_desktop_auth():
        result = (True, f"CURSOR_API_KEY configured in {AGENT_ENV_PATH} (paid API — requires --paid-api)")
        _auth_ready_cache = (now, result[0], result[1])
        return result

    agent = find_cursor_agent()
    if agent is None:
        result = (False, "cursor-agent binary not found")
        _auth_ready_cache = (now, result[0], result[1])
        return result

    try:
        proc = subprocess.run(
            [str(agent), "status"],
            env=agent_subprocess_env(),
            capture_output=True,
            text=True,
            timeout=15.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        result = (False, "cursor-agent status timed out — local-only until login works")
        _auth_ready_cache = (now, result[0], result[1])
        return result
    out = (proc.stdout or proc.stderr or "").strip()
    if proc.returncode == 0 and out and not is_auth_error(out):
        result = (True, "cursor-agent desktop login ($0)")
    elif is_auth_error(out):
        result = (False, "cursor-agent not logged in")
    else:
        tail = out.splitlines()[-1] if out else "cursor-agent status failed"
        result = (False, tail)
    _auth_ready_cache = (now, result[0], result[1])
    return result


def desktop_auth_ready() -> tuple[bool, str]:
    """Desktop login only — ignores CURSOR_API_KEY when force_free is on."""
    if api_key_configured() and not force_free_desktop_auth():
        return False, "CURSOR_API_KEY set — use --paid-api for API billing path"
    return cursor_agent_auth_ready()


def agent_subprocess_env() -> dict[str, str]:
    """Env for cursor-agent — HOME + optional ~/.config/ram-park/cursor-agent.env.

    Credentials (``CURSOR_API_KEY``) must live here only — never on process argv
    (``ps`` exposes argv to every local user). FORCE FREE strips the key so the
    subprocess cannot take the paid API path.
    """
    env = os.environ.copy()
    env.setdefault("HOME", str(Path.home()))
    comp = auto.CFG.get("compression")
    if isinstance(comp, dict):
        if comp.get("python_no_bytecode"):
            env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        arena = comp.get("malloc_arena_max")
        if arena is not None:
            env.setdefault("MALLOC_ARENA_MAX", str(arena))
        node_mb = comp.get("node_max_old_space_mb")
        if node_mb is not None:
            prev = env.get("NODE_OPTIONS", "")
            cap = f"--max-old-space-size={int(node_mb)}"
            env["NODE_OPTIONS"] = f"{prev} {cap}".strip() if prev else cap
    if AGENT_ENV_PATH.is_file():
        for line in AGENT_ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key:
                env[key] = value.strip()
    if force_free_desktop_auth():
        env.pop("CURSOR_API_KEY", None)
    return env


def assert_cursor_agent_argv_safe(argv: Sequence[str]) -> list[str]:
    """Refuse spawn argv that would expose API credentials via ``ps``.

    OVERSEER_CURSOR_AGENT_ARGV_NO_API_KEY_2026_09_07 — never pass ``--api-key``
    or ``CURSOR_API_KEY=...`` on the command line; use :func:`agent_subprocess_env`.
    Does not scan prompt bodies (false positives); only flag/assignment forms.
    """
    safe = list(argv)
    for arg in safe:
        if arg == "--api-key" or arg.startswith("--api-key="):
            raise ValueError(
                "SECURITY: refuse --api-key on cursor-agent argv; "
                "pass credentials via CURSOR_API_KEY in env / cursor-agent.env only"
            )
        if arg.startswith("CURSOR_API_KEY="):
            raise ValueError(
                "SECURITY: refuse CURSOR_API_KEY= on cursor-agent argv; "
                "use agent_subprocess_env / cursor-agent.env only"
            )
    return safe


def build_cursor_agent_cmd(agent: Path | str, argv_prompt: str) -> list[str]:
    """Build local ``cursor-agent -p`` argv with credential-on-argv guard."""
    return assert_cursor_agent_argv_safe(
        [str(agent), "-p", "--force", "--output-format", "text", argv_prompt]
    )


def find_cursor_agent() -> Path | None:
    env = os.environ.get("CURSOR_AGENT_BIN")
    if env:
        path = Path(env).expanduser()
        if path.is_file():
            return path
    found = shutil.which("cursor-agent")
    if found:
        return Path(found)
    default = Path.home() / ".local/bin/cursor-agent"
    if default.is_file():
        return default
    return None


def write_prompt_file(text: str, *, path: Path | None = None) -> Path:
    """Persist peer prompt. Guards live hub file against tiny test clobbers."""
    dest = resolve_prompt_path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if would_clobber_live_prompt(dest, text):
        # Keep large live payload; unittest / blocked-path saves must not erase it.
        return dest
    dest.write_text(text)
    return dest


def argv_safe_prompt(prompt: str, *, path: Path | None = None) -> str:
    """Return prompt text safe for cursor-agent argv (or a file pointer).

    Always persists ``prompt`` to ``path`` (default ``PROMPT_PATH`` / env override)
    unless the live-prompt clobber guard refuses a tiny overwrite. When the body
    exceeds ``ARGV_PROMPT_SOFT_MAX``, return a short instruction that points at
    the on-disk file so spawn cannot hit Errno 7 / E2BIG.
    """
    dest = resolve_prompt_path(path)
    write_prompt_file(prompt, path=dest)
    if len(prompt) <= ARGV_PROMPT_SOFT_MAX:
        return prompt
    return (
        f"Read the full peer prompt at `{dest}` (markdown, already on disk). "
        "Execute that file end-to-end; do not ask for clarification — begin work."
    )


def append_agent_log(header: str, stdout: str, stderr: str) -> None:
    AGENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AGENT_LOG_PATH.open("a") as fh:
        fh.write(f"\n--- {header} ---\n")
        if stdout:
            fh.write(stdout)
        if stderr:
            fh.write("\nSTDERR:\n")
            fh.write(stderr)
        fh.write("\n")


def run_cursor_agent(
    prompt: str,
    *,
    log_fn: Callable[[str], None],
    timeout_sec: float = DEFAULT_AGENT_TIMEOUT_SEC,
    paid_api: bool = False,
    cwd: Path | None = None,
    sync: bool = True,
    prefer_remote: bool = False,
) -> tuple[int, bool]:
    """Run cursor-agent -p in repo root (or ``cwd``); never activates Cursor.app.

    ``prefer_remote`` opts a role into DGX/SSH when an ssh host is resolvable,
    even if global ``agent_remote.enabled`` is false (see peer_remote.should_dispatch_remote).
    """
    # Hard lock: ignore caller paid_api / API key — desktop only ($0).
    if force_free_desktop_auth():
        if paid_api or require_paid_api_opt_in() or api_key_configured():
            log_fn(
                "terminal: FORCE FREE — ignoring paid API / API key; "
                "desktop login only ($0)"
            )
        paid_api = False

    try:
        if peer_remote.should_dispatch_remote(prefer_remote=prefer_remote):
            return peer_remote.run_remote_cursor_agent(
                prompt,
                log_fn=log_fn,
                timeout_sec=timeout_sec,
                paid_api=False if force_free_desktop_auth() else (
                    paid_api or api_key_configured() or require_paid_api_opt_in()
                ),
                cwd=cwd,
                sync=sync,
            )
    except Exception as exc:  # noqa: BLE001
        log_fn(f"remote: dispatch unavailable ({exc}) — falling back to local")

    has_key = api_key_configured()
    if force_free_desktop_auth():
        # Never take the API-key billing branch.
        has_key = False
    elif has_key and not paid_api and not require_paid_api_opt_in():
        log_fn(f"terminal: blocked — {PAID_API_WARNING}")
        write_prompt_file(prompt)
        log_fn(f"terminal: prompt saved → {PROMPT_PATH}")
        return 1, False

    ready, detail = (cursor_agent_auth_ready() if has_key else desktop_auth_ready())
    if not ready:
        log_fn(f"terminal: auth not ready — {detail}")
        write_prompt_file(prompt)
        log_fn(f"terminal: prompt saved → {PROMPT_PATH}")
        return 1, True

    agent = find_cursor_agent()
    if agent is None:
        log_fn("terminal: cursor-agent not found (set CURSOR_AGENT_BIN or install Cursor CLI)")
        write_prompt_file(prompt)
        log_fn(f"terminal: prompt saved → {PROMPT_PATH}")
        return 1, False

    write_prompt_file(prompt)
    billing = "desktop login ($0)" if force_free_desktop_auth() or not has_key else "paid API"
    work = (cwd or ROOT).resolve()
    argv_prompt = argv_safe_prompt(prompt)
    if argv_prompt is not prompt:
        log_fn(
            f"terminal: prompt {len(prompt)} chars → file pointer "
            f"({len(argv_prompt)} chars argv) · {PROMPT_PATH}"
        )
    log_fn(f"terminal: cursor-agent ({len(prompt)} chars) — {billing} · cwd={work}")

    cmd = build_cursor_agent_cmd(agent, argv_prompt)

    def _spawn_sync() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            assert_cursor_agent_argv_safe(cmd),
            cwd=str(work),
            env=agent_subprocess_env(),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )

    if not sync:
        try:
            subprocess.Popen(
                assert_cursor_agent_argv_safe(cmd),
                cwd=str(work),
                env=agent_subprocess_env(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            if exc.errno != errno.E2BIG:
                raise
            # Race: soft-max missed; force pointer and retry once.
            cmd[-1] = argv_safe_prompt(prompt)  # re-write; still may be long if soft max wrong
            if len(cmd[-1]) > ARGV_PROMPT_SOFT_MAX:
                cmd[-1] = (
                    f"Read the full peer prompt at `{PROMPT_PATH}` (markdown). "
                    "Execute that file end-to-end; begin work."
                )
            subprocess.Popen(
                assert_cursor_agent_argv_safe(cmd),
                cwd=str(work),
                env=agent_subprocess_env(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            log_fn("terminal: cursor-agent launched (background, E2BIG→file pointer)")
        else:
            log_fn("terminal: cursor-agent launched (background)")
        return 0, False

    try:
        proc = _spawn_sync()
    except OSError as exc:
        if exc.errno != errno.E2BIG:
            raise
        log_fn("terminal: E2BIG spawning cursor-agent — retry via file pointer")
        cmd[-1] = (
            f"Read the full peer prompt at `{PROMPT_PATH}` (markdown). "
            "Execute that file end-to-end; begin work."
        )
        proc = _spawn_sync()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    append_agent_log(stamp, proc.stdout or "", proc.stderr or "")

    if proc.returncode == 0:
        log_fn("terminal: cursor-agent finished ok")
        return 0, False

    combined = (proc.stderr or proc.stdout or "").strip()
    tail = combined.splitlines()
    auth_failed = is_auth_error(combined)
    log_fn(f"terminal: cursor-agent exit {proc.returncode} — {tail[-1] if tail else 'see peer-agent.log'}")
    if auth_failed:
        log_fn(f"terminal: {auth_fix_hint()}")
    return proc.returncode, auth_failed


def dispatch_via_terminal(
    text: str,
    *,
    log_fn: Callable[[str], None],
    state: dict[str, Any] | None = None,
    record_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    paid_api: bool = False,
    cwd: Path | None = None,
) -> tuple[int, bool]:
    rc, auth_failed = run_cursor_agent(text, log_fn=log_fn, paid_api=paid_api, cwd=cwd)
    if rc == 0 and state is not None and record_fn is not None:
        state = record_fn(state)
        import peer_transcript as transcript

        transcript.save_state(state)
    return rc, auth_failed


def find_agent_proc() -> Any | None:
    """First running peer cursor-agent (delegates to peer_parallel_dispatch)."""
    try:
        import peer_parallel_dispatch as ppd

        return ppd.find_agent_proc()
    except Exception:  # noqa: BLE001
        return None


def count_agent_procs() -> int:
    try:
        import peer_parallel_dispatch as ppd

        return len(ppd.find_agent_procs())
    except Exception:  # noqa: BLE001
        return 0
