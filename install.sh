#!/usr/bin/env bash
# Install peer automation kit into a target repo (merge, not overwrite blindly).
set -euo pipefail

TARGET=""
PROFILE=""
FORCE_SCRIPTS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --force-scripts) FORCE_SCRIPTS=1; shift ;;
    -*) echo "Unknown option: $1"; exit 1 ;;
    *) TARGET="$1"; shift ;;
  esac
done

if [[ -z "$TARGET" || ! -d "$TARGET" ]]; then
  echo "Usage: $0 [--profile generic|automation|ram|caas|node|python|rust|go] [--force-scripts] /path/to/target-repo"
  exit 1
fi

KIT="$(cd "$(dirname "$0")" && pwd)"
TARGET="$(cd "$TARGET" && pwd)"

echo "Installing peer automation from $KIT into: $TARGET"

copy_merge() {
  local src="$1" dst="$2"
  if [[ -f "$dst" && "$FORCE_SCRIPTS" -eq 0 ]]; then
    echo "  skip (exists): $dst"
  else
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    echo "  $( [[ -f "$dst" && "$FORCE_SCRIPTS" -eq 1 ]] && echo updated || echo added): $dst"
  fi
}

for f in automation.config.json AGENTS.md LAUNCH.md IMPORT.md; do
  copy_merge "$KIT/$f" "$TARGET/$f"
done

mkdir -p "$TARGET/profiles"
cp -R "$KIT/profiles/." "$TARGET/profiles/"
echo "  synced: $TARGET/profiles/"

for f in "$KIT"/scripts/*; do
  [[ -f "$f" ]] || continue
  base="$(basename "$f")"
  copy_merge "$f" "$TARGET/scripts/$base"
  chmod +x "$TARGET/scripts/$base" 2>/dev/null || true
done

for f in "$KIT"/notes/*; do
  [[ -f "$f" ]] || continue
  base="$(basename "$f")"
  copy_merge "$f" "$TARGET/notes/$base"
done

for f in "$KIT"/tests/*; do
  [[ -f "$f" ]] || continue
  base="$(basename "$f")"
  copy_merge "$f" "$TARGET/tests/$base"
done

mkdir -p "$TARGET/repos"
copy_merge "$KIT/repos/registry.json" "$TARGET/repos/registry.json"

if [[ -d "$KIT/dashboard" ]]; then
  mkdir -p "$TARGET/dashboard"
  # merge dashboard tree (server + static) without clobbering custom static
  while IFS= read -r -d '' f; do
    rel="${f#"$KIT/"}"
    copy_merge "$f" "$TARGET/$rel"
  done < <(find "$KIT/dashboard" -type f -print0)
fi

if [[ -f "$KIT/.cursor/rules/plan-to-peer-tasks.mdc" ]]; then
  mkdir -p "$TARGET/.cursor/rules"
  copy_merge "$KIT/.cursor/rules/plan-to-peer-tasks.mdc" "$TARGET/.cursor/rules/plan-to-peer-tasks.mdc"
fi

if [[ -f "$KIT/.cursor/hooks.json" ]]; then
  mkdir -p "$TARGET/.cursor"
  copy_merge "$KIT/.cursor/hooks.json" "$TARGET/.cursor/hooks.json"
fi

if [[ -n "$PROFILE" ]]; then
  python3 - <<PY
import json
from pathlib import Path
p = Path("$TARGET/automation.config.json")
cfg = json.loads(p.read_text()) if p.is_file() else {}
cfg["task_profile"] = "$PROFILE"
slug = Path("$TARGET").name.lower().replace(" ", "-")
cfg.setdefault("project_name", slug)
cfg.setdefault("project_slug", slug)
cfg.setdefault("config_namespace", slug)
cfg.setdefault("launch_agent_label", f"com.togi.{slug}-peer-loop")
p.write_text(json.dumps(cfg, indent=2) + "\n")
print(f"  set task_profile=$PROFILE in automation.config.json")
PY
fi

echo
echo "Done. Next:"
echo "  1. Edit $TARGET/automation.config.json (or run adapt to auto-detect)"
echo "  2. cd $TARGET && python3 scripts/automation_adapt.py --heal --write"
echo "  3. cd $TARGET && python3 scripts/peer_orchestrate.py --self-check"
echo "  4. ./scripts/peer check"
