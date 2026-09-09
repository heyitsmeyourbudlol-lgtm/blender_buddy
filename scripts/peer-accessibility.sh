#!/usr/bin/env bash
# Enable Accessibility for peer-loop direct inject (osascript → System Events AX + keystrokes).
#
# macOS requires a one-time GUI toggle — SIP blocks silent TCC grants.
# Usage:
#   ./scripts/peer-accessibility.sh          # open Settings + print steps + verify
#   ./scripts/peer-accessibility.sh --verify # test only (no Settings)
#   ./scripts/peer-accessibility.sh --open   # open Settings panes only
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OSASCRIPT="/usr/bin/osascript"
PLIST="${HOME}/Library/LaunchAgents/$(python3 "$ROOT/scripts/automation_config.py" launch_agent_label).plist"

# Python used by LaunchAgent (if installed), else current interpreter.
LAUNCHAGENT_PY=""
if [[ -f "$PLIST" ]]; then
  LAUNCHAGENT_PY="$(/usr/bin/plutil -extract ProgramArguments.0 raw -o - "$PLIST" 2>/dev/null || true)"
fi
CURRENT_PY="$(command -v python3 || true)"

red() { printf '\033[0;31m%s\033[0m\n' "$*"; }
green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
bold() { printf '\033[1m%s\033[0m\n' "$*"; }

test_post_event() {
  swift -e 'import CoreGraphics; print(CGPreflightPostEventAccess())' 2>/dev/null | grep -qi '^true$'
}

test_system_events() {
  "$OSASCRIPT" -e '
tell application "System Events"
  try
    get name of first process whose frontmost is true
    return "ok"
  on error
    return "denied"
  end try
end tell' 2>/dev/null | grep -q '^ok$'
}

open_settings() {
  # Accessibility (required; Post Event is nested here on Sequoia+)
  open "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Accessibility" 2>/dev/null \
    || open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null \
    || open "/System/Applications/System Settings.app"
  sleep 0.4
  # Post Event (keystroke synthesis — separate TCC bucket on macOS 15+)
  open "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_PostEvent" 2>/dev/null \
    || open "x-apple.systempreferences:com.apple.preference.security?Privacy_PostEvent" 2>/dev/null \
    || true
  sleep 0.3
  # Automation — Cursor + System Events
  open "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Automation" 2>/dev/null \
    || open "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation" 2>/dev/null \
    || true
}

request_post_event_listing() {
  # CGRequestPostEventAccess registers osascript in Accessibility > Post Event on Sequoia+
  swift - 2>/dev/null <<'SWIFT' || true
import CoreGraphics
_ = CGRequestPostEventAccess()
SWIFT
}

print_steps() {
  bold "Peer loop direct inject — one-time Accessibility setup"
  echo
  echo "Peer loop runs: LaunchAgent → Python → osascript → System Events (AX set value + Return)."
  echo "Grant BOTH entries below (macOS 26 / SIP enabled — GUI click required):"
  echo
  bold "1. System Settings → Privacy & Security → Accessibility"
  echo "   Click + and add (⌘⇧G to paste path):"
  echo "     • $OSASCRIPT          (com.apple.osascript) — required"
  if [[ -n "$LAUNCHAGENT_PY" && "$LAUNCHAGENT_PY" != "$OSASCRIPT" ]]; then
    echo "     • $LAUNCHAGENT_PY     (LaunchAgent Python) — recommended"
  fi
  if [[ -n "$CURRENT_PY" && "$CURRENT_PY" != "$LAUNCHAGENT_PY" && "$CURRENT_PY" != "$OSASCRIPT" ]]; then
    echo "     • $CURRENT_PY         (current shell Python) — if testing from terminal"
  fi
  echo "   Also enable Cursor if listed."
  echo
  bold "1b. Same pane → Post Event (macOS 15+ / Tahoe)"
  echo "   Expand Accessibility; under Post Event enable osascript (and Python if listed)."
  echo "   Keystroke error 1002 means Post Event is off even when Accessibility looks on."
  echo
  bold "2. System Settings → Privacy & Security → Automation (optional but helps)"
  echo "   Ensure osascript / Python may control Cursor and System Events."
  echo
  bold "Quick reveal in Finder (drag into Accessibility + list):"
  echo "   open -R $OSASCRIPT"
  if [[ -n "$LAUNCHAGENT_PY" ]]; then
    echo "   open -R $LAUNCHAGENT_PY"
  fi
  echo
  echo "After toggling ON, run:  $ROOT/scripts/peer-accessibility.sh --verify"
  echo "Or restart peer loop:     python3 $ROOT/scripts/peer_loop.py --install"
}

cmd="${1:-}"

case "$cmd" in
  --verify)
    if test_post_event; then
      green "OK — Post Event granted (cursor-ui inject may work)."
      exit 0
    fi
    if test_system_events; then
      red "System Events readable but Post Event not granted."
      echo "On macOS 15+, check Privacy & Security → Accessibility → Post Event for osascript."
    else
      red "Accessibility not granted for $OSASCRIPT."
    fi
    print_steps
    exit 1
    ;;
  --open)
    request_post_event_listing
    open_settings
    open -R "$OSASCRIPT" 2>/dev/null || true
    [[ -n "$LAUNCHAGENT_PY" ]] && open -R "$LAUNCHAGENT_PY" 2>/dev/null || true
    print_steps
    ;;
  --help|-h)
    echo "Usage: $0 [--verify | --open | --help]"
    ;;
  *)
    request_post_event_listing
    open_settings
    open -R "$OSASCRIPT" 2>/dev/null || true
    [[ -n "$LAUNCHAGENT_PY" ]] && open -R "$LAUNCHAGENT_PY" 2>/dev/null || true
    print_steps
    echo
    if test_post_event; then
      green "Already OK — no click needed."
      exit 0
    fi
    red "Waiting for you to enable Accessibility (see steps above)."
    echo "Re-run: $0 --verify"
    exit 1
    ;;
esac
