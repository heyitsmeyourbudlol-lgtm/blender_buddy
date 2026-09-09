#!/usr/bin/env bash
# Restore Automation Hub LaunchAgents on Mac (undo dgx_mac_offload).
set -euo pipefail

UID_NUM="$(id -u)"
PLIST_DIR="$HOME/Library/LaunchAgents"
OFFLOAD_DIR="$PLIST_DIR/offloaded-disabled"
MARKER="${HOME}/.config/automation-hub/mac-offloaded"

launchctl bootout "gui/$UID_NUM/com.togi.automation-hub-dgx-sync" 2>/dev/null || true
launchctl bootout "gui/$UID_NUM/com.togi.automation-hub-dgx-watch" 2>/dev/null || true
rm -f "$PLIST_DIR/com.togi.automation-hub-dgx-sync.plist"
rm -f "$PLIST_DIR/com.togi.automation-hub-dgx-watch.plist"

RESTORE_LABELS=(
  com.togi.automation-peer-loop
  com.togi.automation-improve-loop
  com.togi.automation-oversight-loop
  com.togi.automation-repo-research-loop
  com.togi.automation-hub-peer-loop
  com.togi.automation-hub-improve-loop
  com.togi.automation-hub-comms-improve-loop
  com.togi.automation-hub-dashboard
  com.togi.ram-peer-loop
)

for label in "${RESTORE_LABELS[@]}"; do
  src=""
  if [ -f "$PLIST_DIR/$label.plist" ]; then
    src="$PLIST_DIR/$label.plist"
  elif [ -f "$OFFLOAD_DIR/$label.plist" ]; then
    cp "$OFFLOAD_DIR/$label.plist" "$PLIST_DIR/$label.plist"
    src="$PLIST_DIR/$label.plist"
  fi
  if [ -n "$src" ]; then
    launchctl enable "gui/$UID_NUM/$label" 2>/dev/null || true
    launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
    launchctl bootstrap "gui/$UID_NUM" "$src" 2>/dev/null || true
    echo "restored $label"
  fi
done

rm -f "$MARKER"

echo "Mac daemons restored. Optional: ssh CLEAN systemctl --user stop peer-loop improve-loop oversight-loop repo-research-loop dashboard"
