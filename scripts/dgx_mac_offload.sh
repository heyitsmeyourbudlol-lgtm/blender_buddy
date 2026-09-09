#!/usr/bin/env bash
# Stop Automation Hub daemons on Mac; keep repo synced from DGX Spark (CLEAN).
set -euo pipefail

HOST="${DGX_SSH_HOST:-CLEAN}"
LOCAL_AUTOMATION="$(cd "$(dirname "$0")/.." && pwd)"
UID_NUM="$(id -u)"
PLIST_DIR="$HOME/Library/LaunchAgents"
OFFLOAD_DIR="$PLIST_DIR/offloaded-disabled"
MARKER_DIR="${HOME}/.config/automation-hub"
MARKER="$MARKER_DIR/mac-offloaded"
SYNC_LABEL="com.togi.automation-hub-dgx-sync"
WATCH_LABEL="com.togi.automation-hub-dgx-watch"
SYNC_PLIST="$PLIST_DIR/$SYNC_LABEL.plist"
WATCH_PLIST="$PLIST_DIR/$WATCH_LABEL.plist"
SYNC_SCRIPT="$LOCAL_AUTOMATION/scripts/dgx_sync_pull.sh"
WATCH_SCRIPT="$LOCAL_AUTOMATION/scripts/dgx_watch.py"

# Current labels + legacy hub-* names (either may exist on disk).
AUTOMATION_AGENTS=(
  com.togi.automation-peer-loop
  com.togi.automation-improve-loop
  com.togi.automation-oversight-loop
  com.togi.automation-repo-research-loop
  com.togi.automation-hub-peer-loop
  com.togi.automation-hub-peer-loop-fallback
  com.togi.automation-hub-improve-loop
  com.togi.automation-hub-improve-loop-fallback
  com.togi.automation-hub-comms-improve-loop
  # Keep Mac-local dashboard UI (:8765) — do not park/disable under offload.
  # com.togi.automation-hub-dashboard
  com.togi.automation-hub-repo-research-loop
  com.togi.automation-hub-oversight-loop
  com.togi.ram-peer-loop
)

echo "== Mac offload → DGX Spark ($HOST) =="

mkdir -p "$OFFLOAD_DIR" "$MARKER_DIR"

echo "→ ensure remote loops on $HOST"
ssh -o BatchMode=yes -o ConnectTimeout=15 "$HOST" 'bash -s' <<'EOS' || echo "WARN: could not start remote services (SSH?)"
set -euo pipefail
for s in peer-loop improve-loop oversight-loop repo-research-loop dashboard; do
  systemctl --user enable --now "$s.service" 2>/dev/null || systemctl --user start "$s.service" 2>/dev/null || true
done
systemctl --user is-active peer-loop improve-loop oversight-loop repo-research-loop dashboard 2>/dev/null || true
EOS

# Marker first so dgx_watch treats Mac loops as rogue immediately.
date -u +"%Y-%m-%dT%H:%M:%SZ" >"$MARKER"
echo "offload_host=$HOST" >>"$MARKER"

for label in "${AUTOMATION_AGENTS[@]}"; do
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  launchctl disable "gui/$UID_NUM/$label" 2>/dev/null || true
  if [ -f "$PLIST_DIR/$label.plist" ]; then
    cp "$PLIST_DIR/$label.plist" "$OFFLOAD_DIR/$label.plist"
    # Park plist so heal/install cannot bootstrap mid-offload.
    mv -f "$PLIST_DIR/$label.plist" "$OFFLOAD_DIR/$label.plist"
  fi
  echo "stopped+parked $label"
done

# Stop local cursor-agent peer cycles (not Cursor IDE / Application Support workers).
# OVERSEER_NO_HARDCODED_CURSOR_AGENT_PATH_2026_09_05 — $HOME-portable; no /Users/... literals.
pkill -f 'cursor-agent.*Niche agent' 2>/dev/null || true
pkill -f "${HOME}/.local/bin/cursor-agent" 2>/dev/null || true
pkill -f 'cursor-agent' 2>/dev/null || true

# Orphaned Mac script children from the stopped daemons.
for pat in \
  'scripts/peer_loop.py' \
  'scripts/automation_improve.py' \
  'scripts/peer_oversight.py' \
  'scripts/peer_repo_research.py' \
  'scripts/peer_pen_test.py' \
  'scripts/peer_worktree.py' \
  'Python -m unittest'
do
  pkill -f "$pat" 2>/dev/null || true
done

# Stop My Machines local worker for RAM repo (offloaded; macOS ram-* daemons stay).
while read -r pid _; do
  [ -n "${pid:-}" ] && kill "$pid" 2>/dev/null || true
done < <(pgrep -lf 'cursor-agent.*worker start' 2>/dev/null | grep "worker-dir ${HOME}/ram" || true)

echo "stopped local peer agents + ram worker (Cursor IDE / RamTransfer worker unchanged)"

echo "→ install pull-sync LaunchAgent (every 60s from DGX)"
chmod +x "$SYNC_SCRIPT"

cat > "$SYNC_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${SYNC_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${SYNC_SCRIPT}</string>
  </array>
  <key>StartInterval</key>
  <integer>60</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${HOME}/.config/automation-hub/dgx-sync.log</string>
  <key>StandardErrorPath</key>
  <string>${HOME}/.config/automation-hub/dgx-sync.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$UID_NUM/$SYNC_LABEL" 2>/dev/null || true
launchctl enable "gui/$UID_NUM/$SYNC_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$SYNC_PLIST"
echo "sync agent: $SYNC_LABEL"

echo "→ install DGX watch LaunchAgent"
chmod +x "$WATCH_SCRIPT"
cat > "$WATCH_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${WATCH_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Library/Frameworks/Python.framework/Versions/3.14/bin/python3</string>
    <string>${WATCH_SCRIPT}</string>
    <string>--forever</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${HOME}/.config/automation-hub/dgx-watch.log</string>
  <key>StandardErrorPath</key>
  <string>${HOME}/.config/automation-hub/dgx-watch.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>RAM_AUTOMATION_NO_SUBTEST</key>
    <string>1</string>
    <key>AUTOMATION_SKIP_TEST_MEASURE</key>
    <string>1</string>
  </dict>
</dict>
</plist>
PLIST

launchctl bootout "gui/$UID_NUM/$WATCH_LABEL" 2>/dev/null || true
launchctl enable "gui/$UID_NUM/$WATCH_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$WATCH_PLIST"
python3 "$WATCH_SCRIPT" || true
echo "watch agent: $WATCH_LABEL"

echo "→ initial sync from DGX"
("$SYNC_SCRIPT" || true)

echo ""
echo "Mac automation daemons stopped. Work runs on $HOST."
echo "macOS-only (stay local): Cursor, Chrome, ram-park, ram-guard, ram-gauge-hotkey, sync/watch"
echo "Marker: $MARKER"
echo "Re-enable Mac daemons: ./scripts/dgx_mac_restore.sh"
