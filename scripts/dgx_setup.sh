#!/usr/bin/env bash
# Bootstrap NVIDIA DGX Spark (NVIDIA Sync SSH host) for remote peer_loop agents.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${DGX_SSH_HOST:-CLEAN}"
REMOTE_ROOT="${DGX_REMOTE_ROOT:-/home/arnavrastogi}"
NS="${DGX_CONFIG_NS:-automation-hub}"
REMOTE_AGENT_BASE='$HOME/.cursor-server/data/User/globalStorage/anysphere.cursor-agent-worker/agent-cli/.local'

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

echo "→ propagate CURSOR_API_KEY via env file only (never scrape ps / never argv)"
# OVERSEER_CURSOR_AGENT_ARGV_NO_API_KEY_2026_09_07 — My Machines workers put
# --api-key on argv (Cursor product); we must NOT scrape that into scripts or
# pass the key as ssh/bash positional args (also visible in ps).
LOCAL_ENV="${CURSOR_AGENT_ENV_FILE:-$HOME/.config/$NS/cursor-agent.env}"
if [ -f "$LOCAL_ENV" ] && grep -q '^CURSOR_API_KEY=.' "$LOCAL_ENV" 2>/dev/null; then
  # File body on ssh stdin only — key never appears on local/remote process argv.
  ssh -o BatchMode=yes "$HOST" \
    "mkdir -p \"\$HOME/.config/${NS}\" && umask 077 && cat > \"\$HOME/.config/${NS}/cursor-agent.env\" && chmod 600 \"\$HOME/.config/${NS}/cursor-agent.env\"" \
    < "$LOCAL_ENV"
  echo "remote cursor-agent.env written (from local env file; credentials not on argv)"
else
  echo "no local $LOCAL_ENV with CURSOR_API_KEY — run: ssh -t $HOST cursor-agent login"
  echo "(do not scrape --api-key from ps; rotate any key that was previously exposed)"
fi

echo "→ sync Automation repo"
# OVERSEER_HUB_PROTECT_PUSH_2026_09_04 — never --delete WORKING hub-protect needles on DGX.
# OVERSEER_HUB_PROTECT_DGX_SETUP_2026_09_04 — keep excludes == peer_remote.HUB_PROTECT_PULL_EXCLUDES.
# Keep in sync with peer_remote.HUB_PROTECT_PULL_EXCLUDES (+ Mac dgx_setup path).
rsync -az --delete \
  --exclude .git --exclude .worktrees --exclude __pycache__ --exclude node_modules --exclude .DS_Store \
  --exclude notes/PEN_TEST.md \
  --exclude notes/WORK_QUEUE.md \
  --exclude notes/SYSTEM_OVERSIGHT.md \
  --exclude notes/AUTOMATION_DIGEST.md \
  --exclude notes/REPO_FLAW_RESEARCH.md \
  --exclude scripts/self_improve_context.md \
  --exclude repos/registry.json \
  --exclude automation.config.json \
  --exclude automation.config.local.json \
  --exclude scripts/dgx_ram_budget.py \
  --exclude scripts/dgx_utilization.py \
  --exclude scripts/dgx_setup.sh \
  --exclude scripts/run_peer_tasks.py \
  --exclude scripts/peer_loop.py \
  --exclude scripts/factory_grid.py \
  --exclude scripts/factory_progress.py \
  --exclude scripts/project_automation.py \
  --exclude scripts/automation_config.py \
  --exclude scripts/automation_adapt.py \
  --exclude scripts/automation_improve.py \
  --exclude scripts/peer_error_adapt.py \
  --exclude scripts/peer_worktree.py \
  --exclude scripts/peer_dual_research.py \
  --exclude scripts/peer_orchestrate.py \
  --exclude scripts/peer_remote.py \
  --exclude scripts/peer_oversight.py \
  --exclude scripts/peer_self_heal.py \
  --exclude scripts/peer_stall_pivot.py \
  --exclude scripts/peer_land_hold.py \
  --exclude scripts/peer_team_context.py \
  --exclude scripts/peer_product_forge.py \
  --exclude scripts/peer_pen_test.py \
  --exclude scripts/restore-hub-protect.sh \
  --exclude scripts/beat-mac-clobber.sh \
  --exclude scripts/peer_tasks.json \
  --exclude tests/test_dgx_ram_budget.py \
  --exclude tests/test_run_peer_tasks.py \
  --exclude tests/test_factory_grid.py \
  --exclude tests/test_factory_progress.py \
  --exclude tests/test_automation.py \
  --exclude tests/test_oversight_stagnation_fixes.py \
  --exclude tests/test_peer_pen_test.py \
  --exclude tests/test_peer_worktree.py \
  --exclude tests/test_peer_error_adapt.py \
  --exclude tests/test_peer_product_forge.py \
  --exclude tests/test_peer_remote.py \
  --exclude tests/test_peer_repo_research.py \
  --exclude scripts/peer_repo_research.py \
  --exclude scripts/_mark_flaw_research_landed.py \
  --exclude scripts/peer_transcript.py \
  --exclude scripts/peer_oversight_events.py \
  --exclude scripts/dgx_resource_priority.py \
  --exclude tests/test_dgx_resource_priority.py \
  --exclude scripts/peer_last_cycle_poison.py \
  --exclude tests/test_peer_last_cycle_poison.py \
  --exclude tests/test_peer_self_heal.py \
  --exclude notes/agent_vaults/ \
  --exclude dist/automation-kit-*.tar.gz \
  --exclude notes/BITNET_FACTCHECK.md \
  --exclude notes/NVFP4_LOCK_APPLICABILITY.md \
  --exclude tests/test_adapt_dirty_head_only.py \
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
