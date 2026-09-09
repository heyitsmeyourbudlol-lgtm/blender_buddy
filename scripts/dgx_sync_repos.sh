#!/usr/bin/env bash
# Rsync priority factory repos from Mac → DGX Spark (paths match registry.json).
set -euo pipefail

HOST="${DGX_SSH_HOST:-CLEAN}"
LOCAL_ROOT="${DGX_LOCAL_ROOT:-/Users/togi}"
REMOTE_ROOT="${DGX_REMOTE_ROOT:-/home/arnavrastogi}"

REPOS=(CPT CaaS ram Doc2Api falcon-ai MATTERNTHREAD)

EXCLUDES=(
  --exclude .git
  --exclude __pycache__
  --exclude .next
  --exclude dist
  --exclude build
  --exclude .worktrees
)

# Set WITH_NODE_MODULES=1 to sync node_modules for JS repos (uses RAM on DGX).
if [ "${WITH_NODE_MODULES:-0}" = "1" ]; then
  echo "including node_modules (heavy)"
else
  EXCLUDES+=(--exclude node_modules)
fi

echo "== DGX repo sync: Mac → $HOST =="

for name in "${REPOS[@]}"; do
  src="$LOCAL_ROOT/$name"
  if [ ! -d "$src" ]; then
    echo "skip: $src (not found)"
    continue
  fi
  echo "→ $name"
  rsync -az "${EXCLUDES[@]}" "$src/" "$HOST:$REMOTE_ROOT/$name/"
done

echo "done — factory-fanout can probe ~/CPT ~/CaaS ~/ram on DGX"
