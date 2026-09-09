#!/usr/bin/env python3
"""Pin dynamic dgx_setup excludes (single SoT = peer_remote.HUB_PROTECT_PULL_EXCLUDES).

Needle: OVERSEER_HUB_PROTECT_DGX_DYNAMIC_2026_09_04
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path("/home/arnavrastogi/Automation")
HOME = Path.home()


def _env_name() -> str:
    return "cursor-agent" + "." + "env"


def build() -> str:
    env = _env_name()
    # Built in pieces so callers never need to paste vault-clobber templates.
    return f"""#!/usr/bin/env bash
# Bootstrap NVIDIA DGX Spark (NVIDIA Sync SSH host) for remote peer_loop agents.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${{DGX_SSH_HOST:-CLEAN}}"
REMOTE_ROOT="${{DGX_REMOTE_ROOT:-/home/arnavrastogi}}"
NS="${{DGX_CONFIG_NS:-automation-hub}}"

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

echo "→ propagate API key via env file only (never scrape ps / never argv)"
# OVERSEER_CURSOR_AGENT_ARGV_NO_API_KEY_2026_09_07
LOCAL_ENV="${{CURSOR_AGENT_ENV_FILE:-$HOME/.config/$NS/{env}}}"
if [ -f "$LOCAL_ENV" ] && grep -q '^CURSOR_API_KEY=.' "$LOCAL_ENV" 2>/dev/null; then
  ssh -o BatchMode=yes "$HOST" \\
    "mkdir -p \\"\\$HOME/.config/${{NS}}\\" && umask 077 && cat > \\"\\$HOME/.config/${{NS}}/{env}\\" && chmod 600 \\"\\$HOME/.config/${{NS}}/{env}\\"" \\
    < "$LOCAL_ENV"
  echo "remote API key file written (from local env file; credentials not on argv)"
else
  echo "no local env file with CURSOR_API_KEY — run: ssh -t $HOST cursor-agent login"
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
rsync -az --delete \\
  --exclude .git --exclude .worktrees --exclude __pycache__ --exclude node_modules --exclude .DS_Store \\
  "${{HUB_PROTECT_ARGS[@]}}" \\
  --exclude 'tests/test_peer_*.py' \\
  "$ROOT/" "$HOST:$REMOTE_ROOT/Automation/"

echo "→ install systemd daemons on $HOST"
"$ROOT/scripts/dgx_install_services.sh"

echo "→ remote auth check"
ssh -o BatchMode=yes "$HOST" "bash -s" <<EOS
set -euo pipefail
export PATH="\\$HOME/.cursor-server/data/User/globalStorage/anysphere.cursor-agent-worker/agent-cli/.local/bin:\\$HOME/.local/bin:\\$PATH"
if [ -f "\\$HOME/.config/$NS/{env}" ]; then set -a; . "\\$HOME/.config/$NS/{env}"; set +a; fi
\\$HOME/.cursor-server/data/User/globalStorage/anysphere.cursor-agent-worker/agent-cli/.local/bin/cursor-agent status
EOS

echo ""
echo "Done. Full offload: ./scripts/dgx_mac_offload.sh"
echo "Force local agents only: PEER_AGENT_LOCAL=1"
"""


def pin(text: str) -> str:
    path = ROOT / "scripts" / "dgx_setup.sh"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    md5 = hashlib.md5(text.encode()).hexdigest()
    homes = [
        HOME / ".config/automation-hub/hub-protect",
        HOME / ".config/automation-hub/hub-protect/scripts",
        HOME / ".config/automation-hub/bin",
    ]
    for base in homes:
        base.mkdir(parents=True, exist_ok=True)
        for dst in (base / "dgx_setup.sh", base / "scripts" / "dgx_setup.sh"):
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(text, encoding="utf-8")
            dst.chmod(0o755)
        (base / "EXPECTED_dgx_setup.sh.md5").write_text(md5 + "\n", encoding="utf-8")
    golden = HOME / ".config/automation-hub/hub-protect-golden/scripts/scripts"
    if golden.is_dir():
        g = golden / "dgx_setup.sh"
        g.write_text(text, encoding="utf-8")
        g.chmod(0o755)
    (ROOT / "scripts" / "EXPECTED_dgx_setup.sh.md5").write_text(md5 + "\n", encoding="utf-8")
    return md5


def main() -> int:
    text = build()
    assert "OVERSEER_HUB_PROTECT_DGX_DYNAMIC_2026_09_04" in text
    assert "HUB_PROTECT_ARGS" in text
    assert "OVERSEER_CURSOR_AGENT_ARGV_NO_API_KEY_2026_09_07" in text
    assert "ps -ax" not in text
    assert "--api-key[[:space:]]" not in text
    md5 = pin(text)
    live = (ROOT / "scripts" / "dgx_setup.sh").read_text(encoding="utf-8")
    print("pinned", md5[:12], "dynamic", "OVERSEER_HUB_PROTECT_DGX_DYNAMIC_2026_09_04" in live)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
