#!/usr/bin/env bash
# Pull Automation repo from DGX Spark — Mac stays read-only mirror; no local unittest.
set -euo pipefail

HOST="${DGX_SSH_HOST:-CLEAN}"
REMOTE="${DGX_REMOTE_ROOT:-/home/arnavrastogi}/Automation/"
LOCAL="$(cd "$(dirname "$0")/.." && pwd)/"
CAP="${DGX_MAC_UNITTEST_CAP:-15}"

# Never spawn verify/tests on Mac during sync.
export RAM_AUTOMATION_NO_SUBTEST=1
export AUTOMATION_SKIP_TEST_MEASURE=1

count="$(pgrep -lf unittest 2>/dev/null | wc -l | tr -d ' ')"
if [ "${count:-0}" -gt "$CAP" ]; then
  echo "$(date '+%F %T')  sync skipped — mac unittest storm ($count)" >> "${HOME}/.config/automation-hub/dgx-sync.log"
  pkill -9 -f 'Python -m unittest' 2>/dev/null || true
  exit 0
fi

# -u: never clobber newer Mac edits (offload/watch fixes mid-session).
rsync -azu \
  --exclude .git --exclude .worktrees --exclude __pycache__ --exclude node_modules --exclude .DS_Store \
  "${HOST}:${REMOTE}" "${LOCAL}" 2>/dev/null || true
