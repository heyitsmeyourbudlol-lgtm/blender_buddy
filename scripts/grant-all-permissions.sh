#!/usr/bin/env bash
# One-shot macOS permission setup — trigger every prompt we can + open all Settings panes.
# Double-click grant-all-permissions.command or: ./scripts/grant-all-permissions.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SWIFT_HELPER="$ROOT/scripts/trigger-tcc.swift"
OSASCRIPT="/usr/bin/osascript"
CURSOR_APP="/Applications/Cursor.app"
TERMINAL_APP="/System/Applications/Utilities/Terminal.app"

red() { printf '\033[0;31m%s\033[0m\n' "$*"; }
green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "$*"; }
bold() { printf '\033[1m%s\033[0m\n' "$*"; }

PLIST="${HOME}/Library/LaunchAgents/$(python3 "$ROOT/scripts/automation_config.py" launch_agent_label 2>/dev/null || echo com.togi.peer-loop).plist"
LAUNCHAGENT_PY=""
if [[ -f "$PLIST" ]]; then
  LAUNCHAGENT_PY="$(/usr/bin/plutil -extract ProgramArguments.0 raw -o - "$PLIST" 2>/dev/null || true)"
fi
CURRENT_PY="$(command -v python3 || true)"
CURRENT_SHELL_APP="$(ps -o comm= -p $PPID 2>/dev/null | xargs || echo unknown)"

open_privacy() {
  local pane="$1"
  open "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_${pane}" 2>/dev/null \
    || open "x-apple.systempreferences:com.apple.preference.security?Privacy_${pane}" 2>/dev/null \
    || true
  sleep 0.5
}

reveal_binaries() {
  bold "Revealing binaries in Finder (drag into Settings if needed):"
  for target in "$CURSOR_APP" "$TERMINAL_APP" "$OSASCRIPT" "$CURRENT_PY" "$LAUNCHAGENT_PY"; do
    [[ -n "$target" && -e "$target" ]] || continue
    echo "  → $target"
    open -R "$target" 2>/dev/null || true
    sleep 0.3
  done
}

trigger_for() {
  local label="$1"
  shift
  yellow "Triggering prompts for: $label"
  "$@" 2>/dev/null || true
  sleep 1
}

run_swift_triggers() {
  local extra="${1:-}"
  swift "$SWIFT_HELPER" $extra 2>&1 | while read -r line; do echo "    $line"; done
}

bold "═══════════════════════════════════════════════════════════"
bold "  One-time macOS permission setup (approve each dialog ONCE)"
bold "═══════════════════════════════════════════════════════════"
echo
echo "Running from: $CURRENT_SHELL_APP"
echo "This opens all Privacy panes and triggers every prompt macOS allows."
echo "Full Disk Access cannot auto-prompt — you add apps manually in that pane."
echo
read -r -p "Press Enter to start (have System Settings ready)…"
echo

bold "Step 1/4 — Opening System Settings panes…"
open_privacy "Accessibility"
open_privacy "PostEvent"
open_privacy "Automation"
open_privacy "AllFiles"
open_privacy "FilesAndFolders"
open_privacy "DeveloperTool"
open_privacy "ListenEvent"
open "/System/Applications/System Settings.app" 2>/dev/null || true
sleep 1

bold "Step 2/4 — Triggering permission dialogs…"
echo "(Click Allow / OK on each macOS dialog as it appears)"
echo

trigger_for "this shell ($CURRENT_SHELL_APP)" run_swift_triggers "--files --automation"

if [[ -n "$CURRENT_PY" ]]; then
  trigger_for "python3 ($CURRENT_PY)" \
    env SWIFT_HELPER="$SWIFT_HELPER" "$CURRENT_PY" -c "
import subprocess, os
swift = os.environ['SWIFT_HELPER']
subprocess.run(['swift', swift, '--files', '--automation'], check=False)
"

fi

if [[ -n "$LAUNCHAGENT_PY" && "$LAUNCHAGENT_PY" != "$CURRENT_PY" ]]; then
  trigger_for "LaunchAgent python ($LAUNCHAGENT_PY)" \
    "$LAUNCHAGENT_PY" -c "
import subprocess
subprocess.run(['swift', '$SWIFT_HELPER', '--files', '--automation'], check=False)
"
fi

trigger_for "osascript ($OSASCRIPT)" \
  "$OSASCRIPT" -e '
tell application "System Events"
  try
    get name of first process whose frontmost is true
  end try
end tell
try
  tell application "Cursor" to get name
end try
'

trigger_for "file access probes" bash -c '
for d in "$HOME/Desktop" "$HOME/Documents" "$HOME/Downloads" \
  "$HOME/Library/Application Support/Cursor" "$HOME/.config"; do
  [[ -d "$d" ]] && ls "$d" >/dev/null 2>&1 && echo "    probed: $d"
done
'

bold "Step 3/4 — Manual toggles (cannot auto-prompt)"
echo
bold "In the open Settings panes, enable ALL of these (one time):"
echo
echo "  Accessibility (+ Post Event):"
echo "    ☑ Cursor.app"
echo "    ☑ Terminal.app  (or iTerm if you use it)"
echo "    ☑ $OSASCRIPT"
[[ -n "$CURRENT_PY" ]] && echo "    ☑ $CURRENT_PY"
[[ -n "$LAUNCHAGENT_PY" && "$LAUNCHAGENT_PY" != "$CURRENT_PY" ]] && echo "    ☑ $LAUNCHAGENT_PY"
echo "    ☑ Post Event → osascript (under Accessibility, macOS 15+)"
echo
echo "  Automation:"
echo "    ☑ Allow Terminal/Python/osascript → control Cursor + System Events"
echo
echo "  Full Disk Access:"
echo "    ☑ Cursor.app"
echo "    ☑ Terminal.app"
echo
echo "  Files and Folders:"
echo "    ☑ Cursor + Terminal → Desktop, Documents, Downloads"
echo
echo "  Developer Tools (if listed):"
echo "    ☑ Cursor, Terminal"
echo
echo "  Input Monitoring (if listed):"
echo "    ☑ Cursor, osascript"
echo

reveal_binaries

echo
yellow "IMPORTANT — also run from Cursor's built-in terminal so Cursor gets file prompts:"
echo "  cd $ROOT && ./scripts/grant-all-permissions.sh --cursor-only"
echo

if [[ "${1:-}" == "--cursor-only" ]]; then
  bold "Cursor-terminal pass — triggering for Cursor parent process…"
  run_swift_triggers "--files --automation"
  echo "Done. Enable Cursor in the panes if new entries appeared."
  exit 0
fi

bold "Step 4/4 — Verify"
read -r -p "Press Enter after you've enabled everything above…"
echo

pass=0
fail=0

check() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    green "  ✓ $name"
    pass=$((pass + 1))
  else
    red "  ✗ $name"
    fail=$((fail + 1))
  fi
}

check "osascript → System Events" \
  "$OSASCRIPT" -e 'tell application "System Events" to get name of first process whose frontmost is true'

check "Post Event (keystrokes)" \
  swift -e 'import CoreGraphics; exit(CGPreflightPostEventAccess() ? 0 : 1)'

check "Desktop readable" test -r "$HOME/Desktop"
check "Documents readable" test -r "$HOME/Documents"
check "Cursor App Support readable" test -r "$HOME/Library/Application Support/Cursor"

echo
if [[ $fail -eq 0 ]]; then
  green "All checks passed — you should rarely see permission prompts now."
else
  yellow "$fail check(s) still failing — re-open the matching Settings pane and enable the app listed above."
  echo "Re-run verify: $ROOT/scripts/peer-accessibility.sh --verify"
fi
echo
echo "Peer loop (no Accessibility needed):  python3 $ROOT/scripts/peer_loop.py --forever --background"
echo "Optional UI inject verify:           $ROOT/scripts/peer-accessibility.sh --verify"
