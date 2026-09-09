#!/usr/bin/env bash
# Open Automation on CLEAN via Cursor Remote SSH.
# Extension host + language servers run on DGX; Mac keeps a thinner UI.
set -euo pipefail
HOST="${DGX_SSH_HOST:-CLEAN}"
REMOTE_PATH="${DGX_REMOTE_ROOT:-/home/arnavrastogi}/Automation"
BIN="/Applications/Cursor.app/Contents/Resources/app/bin/cursor"
# Must use --folder-uri. Passing the vscode-remote URI as a path arg makes Cursor
# open a local relative file under the current workspace instead of Remote-SSH.
URI="vscode-remote://ssh-remote+${HOST}${REMOTE_PATH}"
echo "Opening $URI"
echo "(Close local Automation window after remote connects to free ~1–3GB extension-host RAM.)"
if [ -x "$BIN" ]; then
  exec "$BIN" --new-window --folder-uri "$URI"
fi
# Prefer explicit URL open; Launch Services may prompt to disambiguate file vs URL.
open "$URI"
