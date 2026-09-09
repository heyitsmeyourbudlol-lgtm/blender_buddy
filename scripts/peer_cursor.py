"""Cursor UI automation for peer loop — fresh chat, direct inject, submit."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import project_automation as auto

DEFAULT_APP = "Cursor"
FRESH_CHAT_TURN_THRESHOLD = 80
FRESH_CHAT_PROMPT_CHARS = 10_000
DISPATCH_COOLDOWN_SEC = 90.0

OSASCRIPT_PATH = "/usr/bin/osascript"
OSASCRIPT_BUNDLE = "com.apple.osascript"


def _launchagent_python() -> str:
    plist = os.path.expanduser(f"~/Library/LaunchAgents/{auto.LAUNCH_AGENT_LABEL}.plist")
    if not os.path.isfile(plist):
        return ""
    try:
        proc = subprocess.run(
            ["/usr/bin/plutil", "-extract", "ProgramArguments.0", "raw", "-o", plist],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (proc.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def accessibility_hint() -> str:
    py = _launchagent_python() or sys.executable
    if accessibility_available() and not keystroke_available():
        extra = (
            " System Events OK but keystrokes blocked — enable Post Event for "
            f"{OSASCRIPT_PATH} under Accessibility (macOS 15+)."
        )
    else:
        extra = ""
    return (
        "Direct inject needs Accessibility + Post Event: System Settings → Privacy & Security → "
        f"Accessibility — add {OSASCRIPT_PATH} (required) and {py} (LaunchAgent).{extra} "
        f"Run: {os.path.dirname(__file__)}/peer-accessibility.sh"
    )


def accessibility_available() -> bool:
    """True when System Events is readable (Accessibility partially granted)."""
    script = """
tell application "System Events"
    try
        get name of first process whose frontmost is true
        return "ok"
    on error
        return "denied"
    end try
end tell
"""
    proc = _run_osascript(script)
    return proc.returncode == 0 and (proc.stdout or "").strip() == "ok"


def keystroke_available() -> bool:
    """True when Post Event TCC allows keystroke synthesis (non-invasive preflight)."""
    proc = subprocess.run(
        ["swift", "-e", "import CoreGraphics; print(CGPreflightPostEventAccess())"],
        capture_output=True,
        text=True,
        timeout=8.0,
        check=False,
    )
    return proc.returncode == 0 and (proc.stdout or "").strip().lower() == "true"


def _run_osascript(script: str, *, timeout: float = 25.0) -> subprocess.CompletedProcess[str]:
    """Run AppleScript from a temp file (avoids -e parsing issues with «class …» etc.)."""
    fd, path = tempfile.mkstemp(suffix=".applescript", prefix="ram-peer-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(script)
        return subprocess.run(
            ["osascript", path],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _applescript_posix_path(path: str) -> str:
    return path.replace("\\", "\\\\").replace('"', '\\"')


def _write_prompt_tempfile(text: str) -> tuple[Path, Path]:
    """Return temp dir and prompt file path (caller deletes dir)."""
    tmpdir = Path(tempfile.mkdtemp(prefix="ram-peer-"))
    prompt_path = tmpdir / "prompt.txt"
    prompt_path.write_text(text, encoding="utf-8")
    return tmpdir, prompt_path


def _clipboard_bytes() -> bytes:
    proc = subprocess.run(["pbpaste"], capture_output=True, check=False)
    return proc.stdout or b""


def _set_clipboard_bytes(data: bytes) -> None:
    subprocess.run(["pbcopy"], input=data, check=False)


def _inject_via_transient_paste(
    prompt_path: Path,
    *,
    app_name: str,
    press_enter: bool,
    cursor_ui: bool,
) -> tuple[bool, str]:
    """Paste via Cmd+V using a transient clipboard copy (restored before return)."""
    text = prompt_path.read_text(encoding="utf-8")
    saved = _clipboard_bytes()
    try:
        _set_clipboard_bytes(text.encode("utf-8"))
        enter_block = ""
        if press_enter:
            enter_block = """
  delay 0.12
  keystroke return"""
        activate_block = ""
        if cursor_ui:
            activate_block = f'''
tell application "{app_name}" to activate
delay 0.35'''
        script = f'''{activate_block}
tell application "System Events"
  tell process "{app_name}"
    set frontmost to true
    keystroke "a" using {{command down}}
    delay 0.05
    keystroke "v" using {{command down}}
  end tell{enter_block}
end tell
return "ok"
'''
        proc = _run_osascript(script, timeout=45.0)
        out = (proc.stdout or "").strip()
        if proc.returncode == 0 and out == "ok":
            return True, "submitted to Cursor chat (clipboard restored)"
        err = (proc.stderr or proc.stdout or "osascript failed").strip()
        return False, err
    finally:
        _set_clipboard_bytes(saved)


def _inject_via_ax(
    prompt_path: Path,
    *,
    app_name: str,
    press_enter: bool,
    cursor_ui: bool,
) -> tuple[bool, str]:
    """Submit prompt to Cursor chat — transient paste (clipboard restored after)."""
    return _inject_via_transient_paste(
        prompt_path, app_name=app_name, press_enter=press_enter, cursor_ui=cursor_ui
    )


def open_fresh_chat(*, app_name: str = DEFAULT_APP) -> tuple[bool, str]:
    """Open a new Cursor agent chat (Cmd+Shift+L) before injecting."""
    script = f'''
tell application "{app_name}" to activate
delay 0.45
tell application "System Events"
  tell process "{app_name}"
    set frontmost to true
  end tell
  keystroke "l" using {{command down, shift down}}
  delay 0.55
end tell
'''
    proc = _run_osascript(script)
    if proc.returncode == 0:
        return True, "opened fresh Cursor chat (Cmd+Shift+L)"
    err = (proc.stderr or proc.stdout or "osascript failed").strip()
    return False, err


def inject_text_to_cursor(
    text: str,
    *,
    app_name: str = DEFAULT_APP,
    press_enter: bool = True,
    fresh_chat: bool = False,
    cursor_ui: bool = False,
) -> tuple[bool, str]:
    """Inject prompt into Cursor chat — only when --cursor-ui / --direct-ui opted in."""
    if not cursor_ui:
        return False, "cursor-ui inject disabled — use --clipboard-only (default) or pass --cursor-ui"
    if os.environ.get("CURSOR_MINIMIZED") == "1":
        return False, "CURSOR_MINIMIZED=1 — use --clipboard-only for manual paste"

    notes: list[str] = []
    if fresh_chat:
        ok, msg = open_fresh_chat(app_name=app_name)
        notes.append(msg)
        if not ok:
            return False, f"fresh chat failed: {msg}"

    tmpdir, prompt_path = _write_prompt_tempfile(text)
    try:
        ok, msg = _inject_via_ax(
            prompt_path, app_name=app_name, press_enter=press_enter, cursor_ui=cursor_ui
        )
    finally:
        for child in tmpdir.iterdir():
            child.unlink(missing_ok=True)
        tmpdir.rmdir()

    if not ok:
        return False, f"{msg} — {accessibility_hint()}"

    if press_enter:
        msg = f"{msg} and pressed Return"
    if notes:
        return True, f"{notes[0]}; {msg}"
    return True, msg


def paste_clipboard_to_cursor(
    *,
    app_name: str = DEFAULT_APP,
    press_enter: bool = True,
    fresh_chat: bool = False,
    cursor_ui: bool = False,
) -> tuple[bool, str]:
    """Legacy: paste system clipboard into Cursor (Cmd+V). Opt-in / fallback only."""
    if not cursor_ui:
        return False, "cursor-ui paste disabled — use --clipboard-only (default) or pass --cursor-ui"
    if os.environ.get("CURSOR_MINIMIZED") == "1":
        return True, "clipboard ready (CURSOR_MINIMIZED=1 — paste manually with ⌘V)"

    notes: list[str] = []
    if fresh_chat:
        ok, msg = open_fresh_chat(app_name=app_name)
        notes.append(msg)
        if not ok:
            return False, f"fresh chat failed: {msg}"

    enter_line = "keystroke return" if press_enter else ""
    script = f'''
tell application "{app_name}" to activate
delay 0.35
tell application "System Events"
  tell process "{app_name}"
    set frontmost to true
  end tell
  keystroke "a" using command down
  delay 0.08
  keystroke "v" using command down
  delay 0.15
  {enter_line}
end tell
'''
    proc = _run_osascript(script)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "osascript failed").strip()
        return False, f"{err} — {accessibility_hint()}"

    paste_msg = "pasted into Cursor chat" + (" and pressed Return" if press_enter else "")
    if notes:
        return True, f"{notes[0]}; {paste_msg}"
    return True, paste_msg


def send_to_cursor(
    text: str | None = None,
    *,
    app_name: str = DEFAULT_APP,
    press_enter: bool = True,
    fresh_chat: bool = False,
    use_clipboard: bool = False,
    cursor_ui: bool = False,
) -> tuple[bool, str]:
    """Dispatch to Cursor: clipboard by default; AX inject only with cursor_ui=True."""
    if use_clipboard or text is None:
        return paste_clipboard_to_cursor(
            app_name=app_name,
            press_enter=press_enter,
            fresh_chat=fresh_chat,
            cursor_ui=cursor_ui,
        )
    return inject_text_to_cursor(
        text,
        app_name=app_name,
        press_enter=press_enter,
        fresh_chat=fresh_chat,
        cursor_ui=cursor_ui,
    )


def should_open_fresh_chat(*, turn_count: int, prompt_chars: int) -> bool:
    if turn_count >= FRESH_CHAT_TURN_THRESHOLD:
        return True
    if prompt_chars >= FRESH_CHAT_PROMPT_CHARS:
        return True
    return False


def dispatch_cooldown_elapsed(state: dict[str, Any], *, cooldown_sec: float = DISPATCH_COOLDOWN_SEC) -> bool:
    last = float(state.get("last_dispatch_ts") or 0)
    if last <= 0:
        return True
    return (time.time() - last) >= cooldown_sec


def record_dispatch(state: dict[str, Any]) -> dict[str, Any]:
    state = dict(state)
    state["last_dispatch_ts"] = time.time()
    return state
