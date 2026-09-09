#!/usr/bin/env bash
# Bootstrap NVIDIA DGX Spark (NVIDIA Sync SSH host) for remote peer_loop agents.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${DGX_SSH_HOST:-CLEAN}"
REMOTE_ROOT="${DGX_REMOTE_ROOT:-/home/arnavrastogi}"
NS="${DGX_CONFIG_NS:-automation-hub}"

echo "== DGX Spark remote agent setup =="
echo "host: $HOST"
echo "remote_root: $REMOTE_ROOT"

if ! ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" 'echo ok' >/dev/null 2>&1; then
  echo "ERROR: cannot ssh to $HOST — open NVIDIA Sync and connect first." >&2
  exit 1
fi

echo "→ repair Linux cursor-agent symlink on $HOST"
ssh -o BatchMode=yes "$HOST" "bash -s" <<'EOS'
set -euo pipefail
BASE="$HOME/.cursor-server/data/User/globalStorage/anysphere.cursor-agent-worker/agent-cli/.local"
mkdir -p "$BASE/bin"
LINUX_VER=""
for v in "$BASE/share/cursor-agent/versions"/*; do
  [ -f "$v/node" ] || continue
  if file "$v/node" | grep -q 'ARM aarch64'; then
    LINUX_VER="$(basename "$v")"
    break
  fi
done
if [ -z "$LINUX_VER" ]; then
  echo "ERROR: no Linux aarch64 cursor-agent build found on remote" >&2
  exit 1
fi
ln -sf "$BASE/share/cursor-agent/versions/$LINUX_VER/cursor-agent" "$BASE/bin/cursor-agent"
echo "cursor-agent → $LINUX_VER"
EOS

echo "→ propagate API key from local worker (if present)"
KEY="$(
  ps -ax -o command= 2>/dev/null \
    | grep -E 'cursor-agent.*worker start' \
    | sed -n 's/.*--api-key[[:space:]]\([^[:space:]]*\).*/\1/p' \
    | head -1
)"
if [ -n "$KEY" ]; then
  ssh -o BatchMode=yes "$HOST" "bash -s" "$NS" "$KEY" <<'EOS'
set -euo pipefail
NS="$1"
KEY="$2"
mkdir -p "$HOME/.config/$NS"
umask 077
printf '%s\n' "CURSOR_API_KEY=$KEY" > "$HOME/.config/$NS/cursor-agent.env"
EOS
  echo "remote API key file written"
else
  echo "no local worker API key found — run: ssh -t $HOST cursor-agent login"
fi

echo "→ sync Automation repo"
# OVERSEER_HUB_PROTECT_PUSH_2026_09_04 — never --delete WORKING hub-protect needles on DGX.
# OVERSEER_HUB_PROTECT_DGX_SETUP_2026_09_04 — keep excludes == peer_remote.HUB_PROTECT_PULL_EXCLUDES.
# OVERSEER_HUB_PROTECT_DGX_DYNAMIC_2026_09_04 — single source of truth; never hardcode vault list
# (static --exclude lists drift when agents append to peer_remote mid-cycle → false test FAIL).
# scripts/restore-hub-protect.sh · scripts/beat-mac-clobber.sh (literal mentions for live_bad)
HUB_PROTECT_ARGS=()
while IFS= read -r rel; do
  [ -n "$rel" ] || continue
  HUB_PROTECT_ARGS+=(--exclude "$rel")
done < <(
  python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path(r'''$ROOT''') / 'scripts'))
import peer_remote
for rel in peer_remote.HUB_PROTECT_PULL_EXCLUDES:
    print(rel)
"
)
rsync -az --delete \
  --exclude .git --exclude .worktrees --exclude __pycache__ --exclude node_modules --exclude .DS_Store \
  "${HUB_PROTECT_ARGS[@]}" \
  --exclude 'tests/test_peer_*.py' \
  "$ROOT/" "$HOST:$REMOTE_ROOT/Automation/"

echo "→ install systemd daemons on $HOST"
"$ROOT/scripts/dgx_install_services.sh"

echo "→ remote auth check"
ssh -o BatchMode=yes "$HOST" "bash -s" <<EOS
set -euo pipefail
export PATH="\$HOME/.cursor-server/data/User/globalStorage/anysphere.cursor-agent-worker/agent-cli/.local/bin:\$HOME/.local/bin:\$PATH"
if [ -f "\$HOME/.config/$NS/cursor-agent.env" ]; then set -a; . "\$HOME/.config/$NS/cursor-agent.env"; set +a; fi
\$HOME/.cursor-server/data/User/globalStorage/anysphere.cursor-agent-worker/agent-cli/.local/bin/cursor-agent status
EOS

echo ""
echo "Done. Full offload: ./scripts/dgx_mac_offload.sh"
echo "Force local agents only: PEER_AGENT_LOCAL=1"
