#!/usr/bin/env bash
# Install systemd user services on DGX Spark — runs all Automation Hub daemons remotely.
set -euo pipefail

HOST="${DGX_SSH_HOST:-CLEAN}"
REMOTE_ROOT="${DGX_REMOTE_ROOT:-/home/arnavrastogi}"
AUTOMATION="$REMOTE_ROOT/Automation"
NS="${DGX_CONFIG_NS:-automation-hub}"
PY="${DGX_PYTHON:-/home/arnavrastogi/miniconda3/bin/python3}"

echo "== DGX Spark — install automation daemons =="
echo "host: $HOST · repo: $AUTOMATION"

ssh -o BatchMode=yes "$HOST" "bash -s" "$REMOTE_ROOT" "$NS" "$PY" <<'EOS'
set -euo pipefail
REMOTE_ROOT="$1"
NS="$2"
PY="$3"
AUTOMATION="$REMOTE_ROOT/Automation"
CFG="$HOME/.config/$NS"
AGENT_BIN='$HOME/.cursor-server/data/User/globalStorage/anysphere.cursor-agent-worker/agent-cli/.local/bin'
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR" "$CFG"

# Daemons run ON the DGX — agents are local, not SSH-bounced from Mac.
# Merge overlay into local.json and cap peer/grid ≤8 (never cp-clobber max=48).
# Prefer function call: Mac rsync often strips hub CLI `--apply-dgx-speed-overlay`
# while leaving apply_dgx_speed_overlay() merge+clamp intact.
"$PY" -c "
import sys
from pathlib import Path
sys.path.insert(0, '$AUTOMATION/scripts')
from automation_config import apply_dgx_speed_overlay
root = Path('$AUTOMATION')
overlay = root / 'scripts' / 'dgx_speed.local.json'
if not overlay.is_file():
    overlay = root / 'dgx_speed.local.json'
local = root / 'automation.config.local.json'
apply_dgx_speed_overlay(root=root, overlay_path=overlay, local_path=local)
print(f'applied dgx speed overlay → {local}')
"

write_unit() {
  local name="$1"
  shift
  cat > "$UNIT_DIR/$name.service" <<UNIT
[Unit]
Description=Automation Hub — $name
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$AUTOMATION
Environment=HOME=$HOME
Environment=PYTHONPATH=$AUTOMATION/scripts
Environment=PATH=$AGENT_BIN:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=PEER_LOOP_PAID_API=1
Environment=PEER_AGENT_LOCAL=1
ExecStart=$PY $*
Restart=always
RestartSec=15
StandardOutput=append:$CFG/$name.log
StandardError=append:$CFG/$name.log

[Install]
WantedBy=default.target
UNIT
}

write_unit "peer-loop" \
  "$AUTOMATION/scripts/peer_loop.py" --forever --daemon --quick --background --paid-api

write_unit "improve-loop" \
  "$AUTOMATION/scripts/automation_improve.py" --forever --daemon --write --research

write_unit "comms-improve-loop" \
  "$AUTOMATION/scripts/automation_comms_improve.py" --forever --daemon --write --research

write_unit "dashboard" \
  "$AUTOMATION/dashboard/server.py" --host 0.0.0.0 --port 8765

systemctl --user daemon-reload
for svc in peer-loop improve-loop comms-improve-loop dashboard; do
  systemctl --user enable "$svc.service"
  systemctl --user restart "$svc.service"
done

# Survive logout (may require sudo once on the DGX).
if command -v loginctl >/dev/null 2>&1; then
  loginctl enable-linger "$(whoami)" 2>/dev/null || true
fi

echo ""
echo "systemd user services:"
systemctl --user --no-pager status peer-loop.service improve-loop.service comms-improve-loop.service dashboard.service \
  | grep -E 'Active:|●' || true
EOS

echo ""
echo "DGX daemons installed. Dashboard: http://$(ssh -o BatchMode=yes "$HOST" hostname -I 2>/dev/null | awk '{print $1}'):8765"
echo "Or SSH tunnel: ssh -L 8765:127.0.0.1:8765 $HOST"
